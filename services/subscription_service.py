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

async def check_user_limits(user_id: int, db_pool) -> bool:
    """Проверка лимитов пользователя"""
    async with db_pool.acquire() as conn:
        # Проверка подписки пользователя
        user = await conn.fetchrow(
            "SELECT subscription_type, subscription_expire FROM users WHERE user_id = $1", 
            user_id
        )
        
        if not user:
            return False
            
        # Проверка срока действия подписки
        if user['subscription_expire'] and user['subscription_expire'] < datetime.now():
            await conn.execute(
                "UPDATE users SET subscription_type = 'free' WHERE user_id = $1",
                user_id
            )
            user['subscription_type'] = 'free'
        
        # Проверка дневного лимита
        today = datetime.now().date()
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM generations WHERE user_id = $1 AND DATE(created_at) = $2",
            user_id, today
        )
        
        limit = config.PREMIUM_DAILY_LIMIT if user['subscription_type'] == 'premium' else config.FREE_DAILY_LIMIT
        return count < limit

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