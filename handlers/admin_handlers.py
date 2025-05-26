from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import types
from typing import Optional
import logging
import asyncpg
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InputFile
from config import config
import asyncio
from datetime import datetime, timedelta
from services.database import db  # Импортируем экземпляр базы данных

router = Router()
logger = logging.getLogger(__name__)

class AdminSubscriptionStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_subscription_type = State()
    waiting_for_duration = State()

class BroadcastStates(StatesGroup):
    waiting_for_message = State()
    confirm_send = State()


async def check_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return user_id in config.ADMIN_IDS

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Главное меню админ-панели"""
    if not await check_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        return
    
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        types.InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
        types.InlineKeyboardButton(text="🎬 Генерации", callback_data="admin_generations"),
        types.InlineKeyboardButton(text="💎 Подписки", callback_data="admin_subscriptions"),
        types.InlineKeyboardButton(text="✉️ Рассылка", callback_data="admin_broadcast")
    )
    builder.adjust(2)
    
    await message.answer(
        "🛠 Админ-панель:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    """Начало процесса рассылки"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    await callback.message.answer(
        "✉️ Введите сообщение для рассылки (можно с медиа):\n"
        "Поддерживаются текст, фото, видео, документы\n"
        "Или отправьте /cancel для отмены"
    )
    await state.set_state(BroadcastStates.waiting_for_message)
    await callback.answer()

@router.message(BroadcastStates.waiting_for_message, F.text == "/cancel")
async def cancel_broadcast(message: Message, state: FSMContext):
    """Отмена рассылки"""
    await state.clear()
    await message.answer("❌ Рассылка отменена")

@router.message(BroadcastStates.waiting_for_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    """Обработка сообщения для рассылки"""
    # Сохраняем информацию о сообщении
    content = {
        "text": message.html_text if message.text or message.caption else None,
        "media_type": None,
        "media_id": None,
        "has_media": False
    }
    
    # Определяем тип медиа
    if message.photo:
        content["media_type"] = "photo"
        content["media_id"] = message.photo[-1].file_id
        content["has_media"] = True
    elif message.video:
        content["media_type"] = "video"
        content["media_id"] = message.video.file_id
        content["has_media"] = True
    elif message.document:
        content["media_type"] = "document"
        content["media_id"] = message.document.file_id
        content["has_media"] = True
    
    await state.update_data(content=content)
    
    # Создаем кнопки подтверждения
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(text="✅ Отправить", callback_data="confirm_broadcast"),
        types.InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_broadcast")
    )
    
    # Показываем предпросмотр
    preview_text = "📝 Предпросмотр сообщения:\n\n"
    if content["has_media"]:
        preview_text += f"[{content['media_type'].capitalize()}]\n"
    if content["text"]:
        preview_text += content["text"]
    
    if content["has_media"]:
        media = InputFile(content["media_id"])
        if content["media_type"] == "photo":
            await message.answer_photo(
                photo=media,
                caption=preview_text,
                reply_markup=builder.as_markup()
            )
        elif content["media_type"] == "video":
            await message.answer_video(
                video=media,
                caption=preview_text,
                reply_markup=builder.as_markup()
            )
        elif content["media_type"] == "document":
            await message.answer_document(
                document=media,
                caption=preview_text,
                reply_markup=builder.as_markup()
            )
    else:
        await message.answer(
            preview_text,
            reply_markup=builder.as_markup()
        )

@router.callback_query(F.data == "confirm_broadcast")
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и отправка рассылки"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    data = await state.get_data()
    content = data.get("content", {})
    
    if not content:
        await callback.message.answer("⚠️ Ошибка: данные сообщения не найдены")
        await state.clear()
        return
    
    await callback.message.answer("🔄 Начинаю рассылку...")
    
    try:
        # Получаем всех пользователей
        async with db.pool.acquire() as conn:
            users = await conn.fetch("SELECT user_id FROM users")
        
        total_users = len(users)
        success = 0
        failed = 0
        
        # Отправляем сообщение каждому пользователю
        for user in users:
            try:
                if content["has_media"]:
                    media = InputFile(content["media_id"])
                    if content["media_type"] == "photo":
                        await callback.bot.send_photo(
                            chat_id=user["user_id"],
                            photo=media,
                            caption=content["text"]
                        )
                    elif content["media_type"] == "video":
                        await callback.bot.send_video(
                            chat_id=user["user_id"],
                            video=media,
                            caption=content["text"]
                        )
                    elif content["media_type"] == "document":
                        await callback.bot.send_document(
                            chat_id=user["user_id"],
                            document=media,
                            caption=content["text"]
                        )
                else:
                    await callback.bot.send_message(
                        chat_id=user["user_id"],
                        text=content["text"]
                    )
                success += 1
            except Exception as e:
                logger.error(f"Ошибка при отправке пользователю {user['user_id']}: {e}")
                failed += 1
            
            # Небольшая задержка, чтобы не перегружать сервер Telegram
            await asyncio.sleep(0.1)
        
        # Отправляем отчет
        report = (
            "✅ Рассылка завершена\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"✔️ Успешно отправлено: {success}\n"
            f"❌ Не удалось отправить: {failed}"
        )
        await callback.message.answer(report)
    
    except Exception as e:
        logger.error(f"Ошибка при рассылке: {e}")
        await callback.message.answer(f"⚠️ Ошибка при рассылке: {e}")
    finally:
        await state.clear()
        await callback.answer()

@router.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast_callback(callback: CallbackQuery, state: FSMContext):
    """Отмена рассылки через кнопку"""
    await state.clear()
    await callback.message.answer("❌ Рассылка отменена")
    await callback.answer()

@router.callback_query(F.data == "admin_users")
async def admin_users_list(callback: CallbackQuery):
    """Показывает список пользователей с пагинацией"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    try:
        # Используем db.pool вместо параметра db_pool
        async with db.pool.acquire() as conn:
            users = await conn.fetch("""
                SELECT 
                    u.user_id, 
                    u.username, 
                    u.full_name, 
                    u.subscription_type, 
                    p.niche, 
                    p.content_style, 
                    p.updated_at,
                    COUNT(g.id) as generations_count
                FROM users u
                LEFT JOIN user_profiles p ON u.user_id = p.user_id
                LEFT JOIN generations g ON u.user_id = g.user_id
                GROUP BY u.user_id, p.niche, p.content_style, p.updated_at
                ORDER BY u.created_at DESC
                LIMIT 50
            """)
        
        if not users:
            await callback.answer("ℹ️ Нет пользователей")
            return
        
        response = ["📊 Список пользователей (последние 50):\n"]
        for user in users:
            username = f"@{user['username']}" if user['username'] else ""
            user_info = (
                f"\n👤 {user['full_name'] or 'Без имени'} {username}\n"
                f"🆔 ID: {user['user_id']}\n"
                f"💎 Подписка: {user['subscription_type']}\n"
                f"🏷 Ниша: {user['niche'] or 'не указана'}\n"
                f"🎭 Стиль: {user['content_style'] or 'не указан'}\n"
                f"🎬 Генераций: {user['generations_count']}\n"
                f"🕒 Обновлено: {user['updated_at'].strftime('%d.%m.%Y %H:%M') if user['updated_at'] else 'никогда'}\n"
                "━━━━━━━━━━━━━━━━━━"
            )
            response.append(user_info)
        
        # Разбиваем длинные сообщения
        current_message = ""
        for part in response:
            if len(current_message) + len(part) > 4000:
                await callback.message.answer(current_message)
                current_message = part
            else:
                current_message += part
        
        if current_message:
            await callback.message.answer(current_message)
        
    except Exception as e:
        logger.error(f"Ошибка в admin_users_list: {e}")
        await callback.message.answer("⚠️ Ошибка при получении списка пользователей")
    finally:
        await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """Показывает статистику бота"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    try:
        async with db.pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(DISTINCT u.user_id) as total_users,
                    COUNT(DISTINCT CASE WHEN u.subscription_type = 'premium' THEN u.user_id END) as premium_users,
                    COUNT(DISTINCT g.id) as total_generations,
                    COUNT(DISTINCT CASE WHEN g.created_at > NOW() - INTERVAL '7 days' THEN g.user_id END) as active_week_users,
                    COUNT(DISTINCT CASE WHEN g.created_at > NOW() - INTERVAL '30 days' THEN g.user_id END) as active_month_users
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
            
            generations_stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
                FROM generations
            """)
        
        response = [
            "📈 Статистика бота:\n",
            f"👥 Всего пользователей: {stats['total_users']}",
            f"💎 Премиум-пользователей: {stats['premium_users']}",
            f"🎬 Всего генераций: {stats['total_generations']}",
            f"   ✔️ Успешных: {generations_stats['completed']}",
            f"   ❌ Ошибок: {generations_stats['failed']}",
            f"🔄 Активных за неделю: {stats['active_week_users']}",
            f"🔄 Активных за месяц: {stats['active_month_users']}\n",
            "🏷 Топ ниш:"
        ]
        
        for niche in niches:
            response.append(f"- {niche['niche']}: {niche['count']}")
        
        await callback.message.answer("\n".join(response))
        
    except Exception as e:
        logger.error(f"Ошибка в admin_stats: {e}")
        await callback.message.answer("⚠️ Ошибка при получении статистики")
    finally:
        await callback.answer()

@router.callback_query(F.data == "admin_subscriptions")
async def admin_subscriptions_menu(callback: CallbackQuery):
    """Меню управления подписками"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    builder = InlineKeyboardBuilder()
    builder.add(
        types.InlineKeyboardButton(text="➕ Выдать подписку", callback_data="admin_grant_subscription"),
        types.InlineKeyboardButton(text="➖ Отменить подписку", callback_data="admin_revoke_subscription"),
        types.InlineKeyboardButton(text="🎫 Добавить видео-кредиты", callback_data="admin_add_credits"),
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
    )
    builder.adjust(1)
    
    await callback.message.edit_text(
        "🛠 Управление подписками:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "admin_grant_subscription")
async def admin_grant_subscription_start(callback: CallbackQuery, state: FSMContext):
    """Начало процесса выдачи подписки"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    await callback.message.answer(
        "Введите ID пользователя, которому хотите выдать подписку:\n"
        "Или отправьте /cancel для отмены"
    )
    await state.set_state(AdminSubscriptionStates.waiting_for_user_id)
    await callback.answer()

@router.message(AdminSubscriptionStates.waiting_for_user_id, F.text == "/cancel")
async def cancel_grant_subscription(message: Message, state: FSMContext):
    """Отмена выдачи подписки"""
    await state.clear()
    await message.answer("❌ Выдача подписки отменена")

@router.message(AdminSubscriptionStates.waiting_for_user_id)
async def process_user_id_for_subscription(message: Message, state: FSMContext):
    """Обработка ID пользователя для выдачи подписки"""
    try:
        user_id = int(message.text)
        await state.update_data(user_id=user_id)
        
        builder = InlineKeyboardBuilder()
        builder.add(
            types.InlineKeyboardButton(text="💎 Премиум", callback_data="sub_type_premium"),
            types.InlineKeyboardButton(text="🆓 Бесплатный", callback_data="sub_type_free"),
            types.InlineKeyboardButton(text="❌ Отменить", callback_data="sub_type_cancel")
        )
        builder.adjust(2)
        
        await message.answer(
            "Выберите тип подписки:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(AdminSubscriptionStates.waiting_for_subscription_type)
    except ValueError:
        await message.answer("⚠️ Неверный формат ID. Введите числовой ID пользователя.")

@router.callback_query(AdminSubscriptionStates.waiting_for_subscription_type, F.data.startswith("sub_type_"))
async def process_subscription_type(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа подписки"""
    sub_type = callback.data.split("_")[2]
    
    if sub_type == "cancel":
        await state.clear()
        await callback.message.answer("❌ Выдача подписки отменена")
        await callback.answer()
        return
    
    await state.update_data(subscription_type="premium" if sub_type == "premium" else "free")
    
    if sub_type == "free":
        # Для бесплатного тарифа сразу применяем изменения
        data = await state.get_data()
        user_id = data["user_id"]
        
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET subscription_type = 'free', subscription_expire = NULL WHERE user_id = $1",
                user_id
            )
        
        await callback.message.answer(
            f"✅ Пользователю {user_id} установлен бесплатный тариф"
        )
        await state.clear()
    else:
        # Для премиума запрашиваем срок
        await callback.message.answer(
            "Введите срок действия подписки в днях (например, 30):\n"
            "Или отправьте /cancel для отмены"
        )
        await state.set_state(AdminSubscriptionStates.waiting_for_duration)
    
    await callback.message.edit_reply_markup()
    await callback.answer()

@router.message(AdminSubscriptionStates.waiting_for_duration, F.text == "/cancel")
async def cancel_subscription_duration(message: Message, state: FSMContext):
    """Отмена установки срока подписки"""
    await state.clear()
    await message.answer("❌ Выдача подписки отменена")

@router.message(AdminSubscriptionStates.waiting_for_duration)
async def process_subscription_duration(message: Message, state: FSMContext):
    """Обработка срока действия подписки"""
    try:
        duration = int(message.text)
        if duration <= 0:
            raise ValueError
        
        data = await state.get_data()
        user_id = data["user_id"]
        expire_date = datetime.now() + timedelta(days=duration)
        
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET subscription_type = 'premium', subscription_expire = $1 WHERE user_id = $2",
                expire_date, user_id
            )
        
        await message.answer(
            f"✅ Пользователю {user_id} выдана премиум подписка на {duration} дней\n"
            f"Дата окончания: {expire_date.strftime('%d.%m.%Y')}"
        )
        await state.clear()
    except ValueError:
        await message.answer("⚠️ Неверный формат. Введите число дней (например, 30)")

@router.callback_query(F.data == "admin_revoke_subscription")
async def admin_revoke_subscription(callback: CallbackQuery):
    """Отмена подписки пользователя"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    await callback.message.answer(
        "Введите ID пользователя, у которого нужно отменить подписку:\n"
        "Или отправьте /cancel для отмены"
    )
    await state.set_state(AdminSubscriptionStates.waiting_for_user_id)
    await callback.answer()

@router.message(AdminSubscriptionStates.waiting_for_user_id)
async def process_revoke_subscription(message: Message, state: FSMContext):
    """Обработка отмены подписки"""
    try:
        user_id = int(message.text)
        
        async with db.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET subscription_type = 'free', subscription_expire = NULL WHERE user_id = $1",
                user_id
            )
        
        if result.split()[1] == '1':
            await message.answer(f"✅ Подписка пользователя {user_id} отменена")
        else:
            await message.answer(f"⚠️ Пользователь {user_id} не найден")
        
        await state.clear()
    except ValueError:
        await message.answer("⚠️ Неверный формат ID. Введите числовой ID пользователя.")

@router.callback_query(F.data == "admin_add_credits")
async def admin_add_credits_start(callback: CallbackQuery, state: FSMContext):
    """Добавление видео-кредитов"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    await callback.message.answer(
        "Введите ID пользователя и количество кредитов через пробел (например: 12345 5):\n"
        "Или отправьте /cancel для отмены"
    )
    await state.set_state(AdminSubscriptionStates.waiting_for_user_id)
    await callback.answer()

@router.message(AdminSubscriptionStates.waiting_for_user_id)
async def process_add_credits(message: Message, state: FSMContext):
    """Обработка добавления кредитов"""
    try:
        parts = message.text.split()
        if len(parts) != 2:
            raise ValueError
            
        user_id = int(parts[0])
        amount = int(parts[1])
        
        if amount <= 0:
            await message.answer("⚠️ Количество кредитов должно быть положительным числом")
            return
        
        success = await db.add_video_credits(user_id, amount)
        
        if success:
            credits = await db.get_video_credits(user_id)
            await message.answer(
                f"✅ Пользователю {user_id} добавлено {amount} видео-кредитов\n"
                f"Теперь у него {credits} кредитов"
            )
        else:
            await message.answer("⚠️ Не удалось добавить кредиты")
        
        await state.clear()
    except ValueError:
        await message.answer("⚠️ Неверный формат. Введите ID и количество через пробел (например: 12345 5)")

@router.callback_query(F.data == "admin_back")
async def admin_back_to_menu(callback: CallbackQuery):
    """Возврат в главное меню админ-панели"""
    await cmd_admin(callback.message)
    await callback.answer()


@router.callback_query(F.data == "admin_generations")
async def admin_generations(callback: CallbackQuery):
    """Показывает последние генерации"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    try:
        async with db.pool.acquire() as conn:
            generations = await conn.fetch("""
                SELECT 
                    g.id,
                    g.user_id,
                    u.username,
                    g.status,
                    g.created_at,
                    g.updated_at,
                    LENGTH(g.script) as script_length,
                    g.audio_path IS NOT NULL as has_audio,
                    g.video_path IS NOT NULL as has_video
                FROM generations g
                LEFT JOIN users u ON g.user_id = u.user_id
                ORDER BY g.created_at DESC
                LIMIT 30
            """)
        
        if not generations:
            await callback.answer("ℹ️ Нет генераций")
            return
        
        response = ["🎬 Последние генерации (30):\n"]
        for gen in generations:
            username = f"@{gen['username']}" if gen['username'] else ""
            gen_info = (
                f"\n🆔 ID: {gen['id']}",
                f"👤 Пользователь: {username} (ID: {gen['user_id']})",
                f"📝 Статус: {gen['status']}",
                f"📏 Длина скрипта: {gen['script_length']} символов",
                f"🔊 Аудио: {'есть' if gen['has_audio'] else 'нет'}",
                f"🎥 Видео: {'есть' if gen['has_video'] else 'нет'}",
                f"🕒 Создано: {gen['created_at'].strftime('%d.%m.%Y %H:%M')}",
                "━━━━━━━━━━━━━━━━━━"
            )
            response.extend(gen_info)
        
        # Разбиваем длинные сообщения
        current_message = ""
        for part in response:
            if len(current_message) + len(part) > 4000:
                await callback.message.answer(current_message)
                current_message = part
            else:
                current_message += "\n" + part
        
        if current_message:
            await callback.message.answer(current_message)
            
    except Exception as e:
        logger.error(f"Ошибка в admin_generations: {e}")
        await callback.message.answer("⚠️ Ошибка при получении списка генераций")
    finally:
        await callback.answer()