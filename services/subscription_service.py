from datetime import datetime, timedelta
from config import config

async def check_user_limits(user_id: int, db_pool) -> bool:
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
    expire_date = datetime.now() + timedelta(days=duration_days)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET subscription_type = $1, subscription_expire = $2 WHERE user_id = $3",
            sub_type, expire_date, user_id
        )