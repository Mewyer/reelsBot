from datetime import datetime, timedelta
from config import config
import logging
from services.database import db

logger = logging.getLogger(__name__)

async def get_user_limits_info(user_id: int, db_pool) -> dict:
    """Получение полной информации о лимитах пользователя"""
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            """SELECT 
                  subscription_type, 
                  subscription_expire, 
                  COALESCE(video_credits, 0) as video_credits,
                  (SELECT COUNT(*) FROM generations 
                   WHERE user_id = $1 AND DATE(created_at) = CURRENT_DATE) as generations_today
               FROM users WHERE user_id = $1""",
            user_id
        )
        
        if not user:
            return None
            
        limit = (config.PREMIUM_DAILY_LIMIT 
                if user['subscription_type'] == 'premium' 
                else config.FREE_DAILY_LIMIT)
        
        return {
            "subscription_type": user['subscription_type'],
            "subscription_expire": user['subscription_expire'],
            "daily_limit": limit,
            "generations_today": user['generations_today'],
            "video_credits": user['video_credits'],
            "can_generate": (user['generations_today'] < limit) or (user['video_credits'] > 0)
        }

async def check_user_limits(user_id: int, db_pool) -> tuple:
    """Проверка лимитов пользователя (дневных и месячных)"""
    async with db_pool.acquire() as conn:
        # Получаем информацию о пользователе
        user = await conn.fetchrow(
            "SELECT subscription_type, subscription_expire FROM users WHERE user_id = $1", 
            user_id
        )
        
        if not user:
            return (False, "Пользователь не найден")
            
        # Проверка срока действия подписки
        if user['subscription_expire'] and user['subscription_expire'] < datetime.now():
            await conn.execute(
                "UPDATE users SET subscription_type = 'free' WHERE user_id = $1",
                user_id
            )
            user['subscription_type'] = 'free'
        
        # Получаем лимиты в зависимости от типа подписки
        if user['subscription_type'] == 'free':
            daily_limit = config.FREE_DAILY_LIMIT
            monthly_limit = config.FREE_MONTHLY_LIMIT
        elif user['subscription_type'] == 'lite':
            daily_limit = config.LITE_DAILY_LIMIT
            monthly_limit = config.LITE_MONTHLY_LIMIT
        else:  # premium
            daily_limit = config.PREMIUM_DAILY_LIMIT
            monthly_limit = config.PREMIUM_MONTHLY_LIMIT
        
        # Проверяем дневной лимит
        today = datetime.now().date()
        today_count = await conn.fetchval(
            "SELECT COUNT(*) FROM generations WHERE user_id = $1 AND DATE(created_at) = $2",
            user_id, today
        )
        
        # Проверяем месячный лимит
        month_start = datetime.now().replace(day=1).date()
        month_count = await conn.fetchval(
            "SELECT COUNT(*) FROM generations WHERE user_id = $1 AND DATE(created_at) >= $2",
            user_id, month_start
        )
        
        # Проверяем кредиты
        credits = await conn.fetchval("SELECT COALESCE(video_credits, 0) FROM users WHERE user_id = $1", user_id)
        
        messages = []
        can_generate = False
        
        if today_count >= daily_limit:
            messages.append(f"Достигнут дневной лимит ({today_count}/{daily_limit})")
        else:
            can_generate = True
            
        if month_count >= monthly_limit:
            messages.append(f"Достигнут месячный лимит ({month_count}/{monthly_limit})")
            can_generate = False
            
        if credits > 0:
            can_generate = True
            
        return (can_generate, " ".join(messages) if messages else "Лимиты не превышены")

async def get_usage_info(user_id: int, db_pool) -> dict:
    """Полная информация о лимитах пользователя"""
    async with db_pool.acquire() as conn:
        # Получаем данные о пользователе
        user = await conn.fetchrow(
            """SELECT 
                  subscription_type, 
                  subscription_expire,
                  COALESCE(video_credits, 0) as video_credits
               FROM users 
               WHERE user_id = $1""",
            user_id
        )
        
        if not user:
            return None
        
        # Получаем статистику использования
        usage = await conn.fetchrow(
            """SELECT 
                  COUNT(CASE WHEN DATE(created_at) = CURRENT_DATE THEN 1 END) as today_count,
                  COUNT(CASE WHEN DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE) THEN 1 END) as month_count
               FROM generations 
               WHERE user_id = $1""",
            user_id
        )
        
        # Определяем лимиты
        if user['subscription_type'] == 'free':
            daily_limit = config.FREE_DAILY_LIMIT
            monthly_limit = config.FREE_MONTHLY_LIMIT
        elif user['subscription_type'] == 'lite':
            daily_limit = config.LITE_DAILY_LIMIT
            monthly_limit = config.LITE_MONTHLY_LIMIT
        else:  # premium
            daily_limit = config.PREMIUM_DAILY_LIMIT
            monthly_limit = config.PREMIUM_MONTHLY_LIMIT
        
        return {
            'subscription_type': user['subscription_type'],
            'subscription_expire': user['subscription_expire'],
            'video_credits': user['video_credits'],
            'today_usage': usage['today_count'],
            'month_usage': usage['month_count'],
            'daily_limit': daily_limit,
            'monthly_limit': monthly_limit,
            'daily_remaining': max(0, daily_limit - usage['today_count']),
            'monthly_remaining': max(0, monthly_limit - usage['month_count']),
            'can_generate_today': usage['today_count'] < daily_limit or user['video_credits'] > 0,
            'can_generate_month': usage['month_count'] < monthly_limit or user['video_credits'] > 0
        }

async def update_subscription(user_id: int, sub_type: str, duration_days: int, db_pool):
    """Обновление подписки пользователя"""
    expire_date = datetime.now() + timedelta(days=duration_days)
    async with db.pool.acquire() as conn:
        # Проверяем, есть ли пользователь
        exists = await conn.fetchval(
            "SELECT 1 FROM users WHERE user_id = $1",
            user_id
        )
        
        if not exists:
            # Создаем базовую запись пользователя
            await conn.execute(
                "INSERT INTO users (user_id, subscription_type, subscription_expire) VALUES ($1, $2, $3)",
                user_id, sub_type, expire_date
            )
        else:
            # Обновляем существующую подписку
            await conn.execute(
                "UPDATE users SET subscription_type = $1, subscription_expire = $2 WHERE user_id = $3",
                sub_type, expire_date, user_id
            )
        
        logger.info(f"Updated subscription for user {user_id}: {sub_type} for {duration_days} days")

async def get_user_subscription_info(user_id: int, db_pool) -> dict:
    """Получение информации о подписке пользователя"""
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            """SELECT subscription_type, subscription_expire, 
                  (SELECT COUNT(*) FROM generations 
                   WHERE user_id = $1 AND DATE(created_at) = CURRENT_DATE) as generations_today
               FROM users WHERE user_id = $1""",
            user_id
        )
        
        if not user:
            return None
            
        limit = (config.PREMIUM_DAILY_LIMIT 
                if user['subscription_type'] == 'premium' 
                else config.FREE_DAILY_LIMIT)
        
        return {
            "type": user['subscription_type'],
            "expire_date": user['subscription_expire'],
            "days_left": (user['subscription_expire'] - datetime.now()).days if user['subscription_expire'] else 0,
            "generations_today": user['generations_today'],
            "daily_limit": limit,
            "has_available": user['generations_today'] < limit
        }