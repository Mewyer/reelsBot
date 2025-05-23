import asyncpg
from asyncpg import Pool, Connection
from config import config
from typing import Optional, Dict, Any
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
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                    niche TEXT,
                    content_style TEXT,
                    goals TEXT,
                    tone_of_voice TEXT,
                    target_audience TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS generations (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
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

    async def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user profile data"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM user_profiles WHERE user_id = $1", 
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
            await conn.execute("""
                INSERT INTO user_profiles (
                    user_id, niche, content_style, goals, tone_of_voice, target_audience
                ) VALUES (
                    $1, $2, $3, $4, $5, $6
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
            return await conn.fetchval("""
                INSERT INTO generations (
                    user_id, prompt, status
                ) VALUES ($1, $2, $3)
                RETURNING id
            """, user_id, prompt, status)

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
        
        if script is not None:
            updates.append("script = $1")
            params.append(script)
        if audio_path is not None:
            updates.append("audio_path = $2")
            params.append(audio_path)
        if video_path is not None:
            updates.append("video_path = $3")
            params.append(video_path)
        if status is not None:
            updates.append("status = $4")
            params.append(status)
            
        if not updates:
            return False
            
        params.append(generation_id)
        query = f"""
            UPDATE generations SET 
                {", ".join(updates)},
                updated_at = NOW()
            WHERE id = ${len(params)}
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(query, *params)
            return True

db = Database()