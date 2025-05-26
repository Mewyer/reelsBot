import asyncpg
from asyncpg import Pool, Connection
from config import config
from typing import Optional, Dict, Any, Union
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool: Optional[Pool] = None

    async def connect(self):
        """Initialize connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                user=config.POSTGRES_USER,
                password=config.POSTGRES_PASSWORD,
                database=config.POSTGRES_DB,
                host=config.POSTGRES_HOST,
                port=config.POSTGRES_PORT,
                min_size=1,
                max_size=10
            )
            await self._init_db()
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    async def _init_db(self):
       """Initialize database schema"""
       async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    is_admin BOOLEAN DEFAULT FALSE,
                    subscription_type TEXT DEFAULT 'free',
                    subscription_expire TIMESTAMP,
                    video_credits INTEGER DEFAULT 0,  -- Добавляем новую колонку
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                    niche TEXT,
                    content_style TEXT,
                    goals TEXT,
                    tone_of_voice TEXT,
                    target_audience TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS generations (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                    prompt TEXT NOT NULL,
                    script TEXT,
                    audio_path TEXT,
                    video_path TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_generations_user_id ON generations(user_id);
                CREATE INDEX IF NOT EXISTS idx_generations_created_at ON generations(created_at);
            """)

    # database.py (добавляем новые методы в класс Database)
    async def get_user_usage(self, user_id: int, date: str = None) -> int:
        """Get user's generation count for current day"""
        async with self.pool.acquire() as conn:
            query = """
                SELECT COUNT(*) FROM generations 
                WHERE user_id = $1::bigint 
                AND created_at::date = COALESCE($2::date, CURRENT_DATE)
            """
            return await conn.fetchval(query, user_id, date)

    async def add_video_credits(self, user_id: int, amount: int) -> bool:
        """Добавляет разовые видео-кредиты"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, video_credits)
                VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET
                    video_credits = users.video_credits + EXCLUDED.video_credits,
                    updated_at = NOW()
            """, user_id, amount)
            return True

    async def use_video_credit(self, user_id: int) -> bool:
        """Использует один видео-кредит"""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE users 
                SET video_credits = video_credits - 1 
                WHERE user_id = $1 AND video_credits > 0
                RETURNING 1
            """, user_id)
            return bool(result)

    async def get_video_credits(self, user_id: int) -> int:
        """Получает количество доступных видео-кредитов"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval("""
                SELECT COALESCE(video_credits, 0) FROM users WHERE user_id = $1
            """, user_id)

    async def get_user_subscription(self, user_id: int) -> str:
        """Get user's subscription type"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT subscription_type FROM users WHERE user_id = $1::bigint", 
                user_id
            )

    async def create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        full_name: Optional[str] = None
    ) -> bool:
        """Create or update basic user record"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, username, full_name)
                VALUES ($1::bigint, $2::text, $3::text)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    full_name = EXCLUDED.full_name,
                    updated_at = NOW()
            """, user_id, username, full_name)
            return True

    async def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user profile data"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM user_profiles WHERE user_id = $1::bigint", 
                user_id
            )
            return dict(row) if row else None

    async def save_user_profile(
        self,
        user_id: int,
        profile_data: Dict[str, Any]
    ) -> bool:
        """Save or update user profile"""
        async with self.pool.acquire() as conn:
            await self.create_user(user_id)
            
            await conn.execute("""
                INSERT INTO user_profiles (
                    user_id, niche, content_style, goals, tone_of_voice, target_audience
                ) VALUES (
                    $1::bigint, $2::text, $3::text, $4::text, $5::text, $6::text
                ) ON CONFLICT (user_id) DO UPDATE SET
                    niche = EXCLUDED.niche,
                    content_style = EXCLUDED.content_style,
                    goals = EXCLUDED.goals,
                    tone_of_voice = EXCLUDED.tone_of_voice,
                    target_audience = EXCLUDED.target_audience,
                    updated_at = NOW()
            """, 
                user_id,
                profile_data.get("niche"),
                profile_data.get("content_style"),
                profile_data.get("goals"),
                profile_data.get("tone_of_voice"),
                profile_data.get("target_audience")
            )
            return True

    async def log_generation(
        self,
        user_id: int,
        prompt: str,
        status: str = "pending"
    ) -> int:
        """Log generation request and return generation ID"""
        async with self.pool.acquire() as conn:
            await self.create_user(user_id)
            
            try:
                return await conn.fetchval("""
                    INSERT INTO generations (user_id, prompt, status)
                    VALUES ($1::bigint, $2::text, $3::text)
                    RETURNING id
                """, user_id, str(prompt), status)
            except Exception as e:
                logger.error(f"Failed to log generation: {e}")
                raise Exception(f"Database error: {e}")

    async def update_generation(
        self,
        generation_id: int,
        script: Optional[str] = None,
        audio_path: Optional[str] = None,
        video_path: Optional[str] = None,
        status: Optional[str] = None
    ) -> bool:
        """Update generation record"""
        updates = []
        params = []
        param_count = 1
        
        if script is not None:
            updates.append(f"script = ${param_count}::text")
            params.append(script)
            param_count += 1
        if audio_path is not None:
            updates.append(f"audio_path = ${param_count}::text")
            params.append(audio_path)
            param_count += 1
        if video_path is not None:
            updates.append(f"video_path = ${param_count}::text")
            params.append(video_path)
            param_count += 1
        if status is not None:
            updates.append(f"status = ${param_count}::text")
            params.append(status)
            param_count += 1
            
        if not updates:
            return False
            
        params.append(generation_id)
        query = f"""
            UPDATE generations SET 
                {", ".join(updates)},
                updated_at = NOW()
            WHERE id = ${param_count}::integer
        """
        
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(query, *params)
                return True
            except Exception as e:
                logger.error(f"Failed to update generation: {e}")
                raise Exception(f"Database error: {e}")

db = Database()