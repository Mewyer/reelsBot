from typing import Optional, Dict
from datetime import datetime
from config import config

class ProfileStates:
    WAITING_NICHE = 1
    WAITING_CONTENT_STYLE = 2
    WAITING_GOALS = 3
    WAITING_TONE = 4
    WAITING_AUDIENCE = 5

PROFILE_QUESTIONS = {
    'niche': "📌 В какой нише вы создаете контент? (например: красота, бизнес, спорт)",
    'content_style': "🎬 Какой стиль подачи предпочитаете? (например: экспертный, развлекательный, вдохновляющий)",
    'goals': "🎯 Какие цели у вашего контента? (например: продажи, обучение, развлечение)",
    'tone_of_voice': "🗣 Какой тон общения предпочитаете? (например: дружеский, профессиональный, провокационный)",
    'target_audience': "👥 Опишите вашу целевую аудиторию (например: женщины 25-35, предприниматели, подростки)"
}

async def save_profile_data(user_id: int, field: str, value: str, db_pool) -> bool:
    async with db_pool.acquire() as conn:
        await conn.execute(f"""
            INSERT INTO user_profiles (user_id, {field}, updated_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE
            SET {field} = EXCLUDED.{field}, updated_at = EXCLUDED.updated_at
        """, user_id, value, datetime.now())
    return True

async def get_user_profile(user_id: int, db_pool) -> Optional[Dict]:
    async with db_pool.acquire() as conn:
        profile = await conn.fetchrow(
            "SELECT niche, content_style, goals, tone_of_voice, target_audience FROM user_profiles WHERE user_id = $1",
            user_id
        )
        return dict(profile) if profile else None

async def is_profile_complete(user_id: int, db_pool) -> bool:
    profile = await get_user_profile(user_id, db_pool)
    if not profile:
        return False
    return all(profile.values())

async def generate_profile_prompt(user_id: int, db_pool) -> str:
    profile = await get_user_profile(user_id, db_pool)
    if not profile:
        return ""
    
    prompt_parts = []
    if profile.get('niche'):
        prompt_parts.append(f"Ниша: {profile['niche']}")
    if profile.get('content_style'):
        prompt_parts.append(f"Стиль подачи: {profile['content_style']}")
    if profile.get('goals'):
        prompt_parts.append(f"Цели: {profile['goals']}")
    if profile.get('tone_of_voice'):
        prompt_parts.append(f"Тон общения: {profile['tone_of_voice']}")
    if profile.get('target_audience'):
        prompt_parts.append(f"ЦА: {profile['target_audience']}")
    
    return "\n".join(prompt_parts) if prompt_parts else ""

async def get_next_profile_question(current_state: int) -> Optional[str]:
    questions_order = [
        ('niche', PROFILE_QUESTIONS['niche']),
        ('content_style', PROFILE_QUESTIONS['content_style']),
        ('goals', PROFILE_QUESTIONS['goals']),
        ('tone_of_voice', PROFILE_QUESTIONS['tone_of_voice']),
        ('target_audience', PROFILE_QUESTIONS['target_audience'])
    ]
    
    if current_state < len(questions_order):
        return questions_order[current_state][1]
    return None