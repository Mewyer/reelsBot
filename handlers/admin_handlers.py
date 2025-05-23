from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import types

from config import config

router = Router()

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("Доступ запрещен")
        return
    
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(
        text="📊 Статистика",
        callback_data="admin_stats")
    )
    builder.add(types.InlineKeyboardButton(
        text="👥 Пользователи",
        callback_data="admin_users")
    )
    builder.add(types.InlineKeyboardButton(
        text="🎬 Генерации",
        callback_data="admin_generations")
    )
    builder.adjust(2)
    
    await message.answer(
        "Админ-панель:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "admin_users")
async def admin_users_list(callback: CallbackQuery, db_pool):
    async with db_pool.acquire() as conn:
        users = await conn.fetch("""
            SELECT u.user_id, u.username, u.full_name, u.subscription_type, 
                   p.niche, p.content_style, p.updated_at,
                   COUNT(g.id) as generations_count
            FROM users u
            LEFT JOIN user_profiles p ON u.user_id = p.user_id
            LEFT JOIN generations g ON u.user_id = g.user_id
            GROUP BY u.user_id, p.niche, p.content_style, p.updated_at
            ORDER BY u.created_at DESC
            LIMIT 50
        """)
    
    if not users:
        await callback.answer("Нет пользователей")
        return
    
    response = "📊 Список пользователей:\n\n"
    for user in users:
        response += (
            f"👤 {user['full_name']} (@{user['username']})\n"
            f"🆔 ID: {user['user_id']}\n"
            f"💎 Подписка: {user['subscription_type']}\n"
            f"🏷 Ниша: {user['niche'] or 'не указана'}\n"
            f"🎭 Стиль: {user['content_style'] or 'не указан'}\n"
            f"🎬 Генераций: {user['generations_count']}\n"
            f"🕒 Обновлено: {user['updated_at'].strftime('%d.%m.%Y') if user['updated_at'] else 'никогда'}\n\n"
        )
    
    # Разбиваем на части если слишком длинное сообщение
    max_length = 4000
    if len(response) > max_length:
        parts = [response[i:i+max_length] for i in range(0, len(response), max_length)]
        for part in parts:
            await callback.message.answer(part)
    else:
        await callback.message.answer(response)
    
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, db_pool):
    async with db_pool.acquire() as conn:
        stats = await conn.fetchrow("""
            SELECT 
                COUNT(DISTINCT u.user_id) as total_users,
                COUNT(DISTINCT CASE WHEN u.subscription_type = 'premium' THEN u.user_id END) as premium_users,
                COUNT(DISTINCT g.id) as total_generations,
                COUNT(DISTINCT g.user_id) as active_users
            FROM users u
            LEFT JOIN generations g ON u.user_id = g.user_id
        """)
        
        niches = await conn.fetch("""
            SELECT niche, COUNT(*) as count 
            FROM user_profiles 
            WHERE niche IS NOT NULL 
            GROUP BY niche 
            ORDER BY count DESC 
            LIMIT 5
        """)
    
    response = (
        "📈 Статистика бота:\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"💎 Премиум-пользователей: {stats['premium_users']}\n"
        f"🎬 Всего генераций: {stats['total_generations']}\n"
        f"🔄 Активных пользователей: {stats['active_users']}\n\n"
        "🏷 Топ ниш:\n"
    )
    
    for niche in niches:
        response += f"- {niche['niche']}: {niche['count']}\n"
    
    await callback.message.answer(response)
    await callback.answer()