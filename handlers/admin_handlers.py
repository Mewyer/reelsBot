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

class UserSearchStates(StatesGroup):
    waiting_for_query = State()

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
        types.InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_users_list"),
        types.InlineKeyboardButton(text="🎬 Генерации", callback_data="admin_generations"),
        types.InlineKeyboardButton(text="✉️ Рассылка", callback_data="admin_broadcast")
    )
    builder.adjust(2)
    
    await message.answer(
        "🛠 Админ-панель:",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "admin_users_list")
async def admin_users_list(callback: CallbackQuery):
    """Показывает список всех пользователей с пагинацией"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    try:
        async with db.pool.acquire() as conn:
            users = await conn.fetch("""
                SELECT user_id, username, full_name 
                FROM users 
                ORDER BY username IS NULL, username ASC, created_at DESC
                LIMIT 100
            """)
        
        if not users:
            await callback.answer("ℹ️ Нет пользователей")
            return
        
        # Создаем клавиатуру с username пользователей
        builder = InlineKeyboardBuilder()
        for user in users:
            username = user['username'] or f"ID:{user['user_id']}"
            builder.add(
                types.InlineKeyboardButton(
                    text=f"@{username}",
                    callback_data=f"user_detail_{user['user_id']}"
                )
            )
        builder.adjust(1)
        
        # Добавляем кнопку "Показать еще" если пользователей много
        if len(users) == 100:
            builder.row(
                types.InlineKeyboardButton(
                    text="⬇️ Показать еще",
                    callback_data="admin_users_list_more"
                )
            )
        
        await callback.message.answer(
            "👥 Список пользователей:",
            reply_markup=builder.as_markup()
        )
        
    except Exception as e:
        logger.error(f"Ошибка в admin_users_list: {e}")
        await callback.message.answer("⚠️ Ошибка при получении списка пользователей")
    finally:
        await callback.answer()


@router.callback_query(F.data.startswith("user_detail_"))
async def show_user_detail(callback: CallbackQuery):
    """Показывает детальную информацию о пользователе"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    try:
        user_id = int(callback.data.split("_")[2])
        await show_user_profile(callback.message, user_id=user_id)
    except Exception as e:
        logger.error(f"Ошибка при показе профиля пользователя: {e}")
        await callback.message.answer("⚠️ Ошибка при загрузке профиля")
    finally:
        await callback.answer()

async def show_user_profile(message: Message, user_data: Optional[dict] = None, user_id: Optional[int] = None):
    """Показывает профиль пользователя с возможностью управления"""
    try:
        if user_data is None and user_id is not None:
            async with db.pool.acquire() as conn:
                user_data = await conn.fetchrow(
                    """
                    SELECT 
                        u.*,
                        p.niche,
                        p.content_style,
                        COUNT(g.id) as generations_count,
                        SUM(CASE WHEN g.status = 'completed' THEN 1 ELSE 0 END) as completed_generations,
                        (SELECT COUNT(*) FROM generations 
                         WHERE user_id = u.user_id AND DATE(created_at) = CURRENT_DATE) as today_generations,
                        (SELECT COUNT(*) FROM generations 
                         WHERE user_id = u.user_id AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)) as month_generations
                    FROM users u
                    LEFT JOIN user_profiles p ON u.user_id = p.user_id
                    LEFT JOIN generations g ON u.user_id = g.user_id
                    WHERE u.user_id = $1
                    GROUP BY u.user_id, p.niche, p.content_style
                    """,
                    user_id
                )
        
        if not user_data:
            await message.answer("⚠️ Пользователь не найден")
            return
        
        # Определяем лимиты в зависимости от типа подписки
        if user_data['subscription_type'] == 'free':
            daily_limit = config.FREE_DAILY_LIMIT
            monthly_limit = config.FREE_MONTHLY_LIMIT
        elif user_data['subscription_type'] == 'lite':
            daily_limit = config.LITE_DAILY_LIMIT
            monthly_limit = config.LITE_MONTHLY_LIMIT
        else:  # premium
            daily_limit = config.PREMIUM_DAILY_LIMIT
            monthly_limit = config.PREMIUM_MONTHLY_LIMIT
        
        # Формируем информацию о пользователе
        username = f"@{user_data['username']}"
        full_name = user_data['full_name'] 
        expire_date = user_data['subscription_expire'].strftime("%d.%m.%Y") if user_data['subscription_expire'] else "нет"
        
        response = [
            "👤 Профиль пользователя:",
            f"🆔 ID: {user_data['user_id']}",
            f"📱 Username: {username}",
            f"👤 Полное имя: {full_name}",
            f"📅 Дата регистрации: {user_data['created_at'].strftime('%d.%m.%Y %H:%M')}",
            f"💎 Подписка: {user_data['subscription_type'].capitalize()}",
            f"📅 Окончание подписки: {expire_date}",
            f"🎬 Генераций сегодня: {user_data['today_generations']}/{daily_limit}",
            f"📅 Генераций в этом месяце: {user_data['month_generations']}/{monthly_limit}",
            f"🎫 Видео-кредиты: {user_data['video_credits']}",
            f"🏷 Ниша: {user_data['niche'] or 'не указана'}",
            f"🎭 Стиль контента: {user_data['content_style'] or 'не указан'}",
            f"🎬 Всего генераций: {user_data['generations_count']}",
            f"✅ Успешных генераций: {user_data['completed_generations']}",
        ]
        
        # Кнопки управления пользователем
        builder = InlineKeyboardBuilder()
        builder.add(
            types.InlineKeyboardButton(
                text="💎 Изменить подписку",
                callback_data=f"admin_manage_sub_{user_data['user_id']}"
            ),
            types.InlineKeyboardButton(
                text="🎥 Добавить кредиты",
                callback_data=f"admin_add_credits_{user_data['user_id']}"
            ),
            types.InlineKeyboardButton(
                text="🎬 Посмотреть генерации",
                callback_data=f"admin_user_gens_{user_data['user_id']}"
            ),
            types.InlineKeyboardButton(
                text="🔙 К списку пользователей",
                callback_data="admin_users_list"
            )
        )
        builder.adjust(1)
        
        await message.answer(
            "\n".join(response),
            reply_markup=builder.as_markup()
        )
    
    except Exception as e:
        logger.error(f"Ошибка при показе профиля пользователя: {e}")
        await message.answer("⚠️ Ошибка при загрузке профиля")


@router.callback_query(F.data.startswith("admin_manage_sub_"))
async def admin_manage_subscription(callback: CallbackQuery, state: FSMContext):
    """Управление подпиской пользователя"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    try:
        user_id = int(callback.data.split("_")[3])
        await state.update_data(user_id=user_id)
        
        builder = InlineKeyboardBuilder()
        builder.add(
            types.InlineKeyboardButton(text="💎 Premium", callback_data="sub_type_premium"),
            types.InlineKeyboardButton(text="📱 Lite", callback_data="sub_type_lite"),
            types.InlineKeyboardButton(text="🆓 Free", callback_data="sub_type_free"),
            types.InlineKeyboardButton(text="🔙 Назад", callback_data=f"user_detail_{user_id}")
        )
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"Выберите тариф для пользователя {user_id}:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(AdminSubscriptionStates.waiting_for_subscription_type)
    except Exception as e:
        logger.error(f"Ошибка в admin_manage_subscription: {e}")
        await callback.message.answer("⚠️ Ошибка при управлении подпиской")
    finally:
        await callback.answer()



@router.callback_query(F.data.startswith("admin_user_gens_"))
async def admin_user_generations(callback: CallbackQuery):
    """Показывает генерации конкретного пользователя"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    try:
        user_id = int(callback.data.split("_")[3])
        
        async with db.pool.acquire() as conn:
            user = await conn.fetchrow("SELECT username, full_name FROM users WHERE user_id = $1", user_id)
            generations = await conn.fetch(
                """
                SELECT id, status, created_at, updated_at 
                FROM generations 
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT 20
                """,
                user_id
            )
        
        if not user:
            await callback.message.answer("⚠️ Пользователь не найден")
            return
        
        username = f"@{user['username']}" if user['username'] else f"ID:{user_id}"
        response = [
            f"🎬 Последние генерации пользователя {user['full_name'] or 'Без имени'} {username}:\n"
        ]
        
        for gen in generations:
            gen_info = (
                f"\n🆔 ID генерации: {gen['id']}",
                f"📝 Статус: {gen['status']}",
                f"🕒 Создано: {gen['created_at'].strftime('%d.%m.%Y %H:%M')}",
                f"🔄 Обновлено: {gen['updated_at'].strftime('%d.%m.%Y %H:%M')}",
                "━━━━━━━━━━━━━━━━━━"
            )
            response.extend(gen_info)
        
        # Кнопка возврата
        builder = InlineKeyboardBuilder()
        builder.add(
            types.InlineKeyboardButton(
                text="🔙 Назад к профилю",
                callback_data=f"user_detail_{user_id}"
            )
        )
        
        # Разбиваем длинные сообщения
        current_message = ""
        for part in response:
            if len(current_message) + len(part) > 4000:
                await callback.message.answer(current_message)
                current_message = part
            else:
                current_message += "\n" + part
        
        if current_message:
            await callback.message.answer(
                current_message,
                reply_markup=builder.as_markup()
            )
            
    except Exception as e:
        logger.error(f"Ошибка в admin_user_generations: {e}")
        await callback.message.answer("⚠️ Ошибка при получении генераций")
    finally:
        await callback.answer()

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
    data = await state.get_data()
    user_id = data["user_id"]
    
    if sub_type == "cancel":
        await state.clear()
        await callback.message.answer("❌ Изменение подписки отменено")
        await callback.answer()
        return
    
    await state.update_data(subscription_type=sub_type)
    
    if sub_type == "free":
        # Для бесплатного тарифа сразу применяем изменения
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET subscription_type = 'free', subscription_expire = NULL WHERE user_id = $1",
                user_id
            )
        
        await callback.message.answer(f"✅ Пользователю {user_id} установлен бесплатный тариф")
        await state.clear()
    else:
        # Для премиума и lite запрашиваем срок
        await callback.message.answer(
            f"Введите срок действия подписки в днях для тарифа {sub_type.capitalize()}:\n"
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
        sub_type = data["subscription_type"]
        expire_date = datetime.now() + timedelta(days=duration)
        
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET subscription_type = $1, subscription_expire = $2 WHERE user_id = $3",
                sub_type, expire_date, user_id
            )
        
        await message.answer(
            f"✅ Пользователю {user_id} выдан тариф {sub_type.capitalize()} на {duration} дней\n"
            f"Дата окончания: {expire_date.strftime('%d.%m.%Y')}"
        )
        await state.clear()
    except ValueError:
        await message.answer("⚠️ Неверный формат. Введите положительное число дней")

@router.callback_query(F.data == "admin_revoke_subscription")
async def admin_revoke_subscription(callback: CallbackQuery, state: FSMContext):
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

@router.callback_query(F.data.startswith("admin_add_credits_"))
async def admin_add_credits_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления кредитов для конкретного пользователя"""
    if not await check_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    try:
        user_id = int(callback.data.split("_")[3])
        await state.update_data(user_id=user_id)
        
        builder = InlineKeyboardBuilder()
        # Добавляем кнопки для быстрого выбора популярных пакетов
        builder.add(
            types.InlineKeyboardButton(text="1 кредит", callback_data="credits_1"),
            types.InlineKeyboardButton(text="5 кредитов", callback_data="credits_5"),
            types.InlineKeyboardButton(text="10 кредитов", callback_data="credits_10"),
            types.InlineKeyboardButton(text="20 кредитов", callback_data="credits_20"),
            types.InlineKeyboardButton(text="Другое количество", callback_data="credits_custom"),
            types.InlineKeyboardButton(text="🔙 Назад", callback_data=f"user_detail_{user_id}")
        )
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"Выберите количество видео-кредитов для пользователя {user_id}:",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logger.error(f"Ошибка в admin_add_credits_start: {e}")
        await callback.message.answer("⚠️ Ошибка при добавлении кредитов")
    finally:
        await callback.answer()

@router.callback_query(F.data.startswith("credits_"))
async def process_credits_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора количества кредитов"""
    try:
        data = await state.get_data()
        user_id = data["user_id"]
        
        if callback.data == "credits_custom":
            await callback.message.answer(
                "Введите количество видео-кредитов для добавления:\n"
                "Или отправьте /cancel для отмены"
            )
            await state.set_state(AdminSubscriptionStates.waiting_for_duration)
            await callback.message.edit_reply_markup()
            await callback.answer()
            return
        
        amount = int(callback.data.split("_")[1])
        success = await db.add_video_credits(user_id, amount)
        
        if success:
            credits = await db.get_video_credits(user_id)
            await callback.message.edit_text(
                f"✅ Пользователю {user_id} добавлено {amount} видео-кредитов\n"
                f"Теперь у него {credits} кредитов"
            )
        else:
            await callback.message.edit_text("⚠️ Не удалось добавить кредиты")
        
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка при добавлении кредитов: {e}")
        await callback.message.answer("⚠️ Ошибка при добавлении кредитов")
    finally:
        await callback.answer()

@router.message(AdminSubscriptionStates.waiting_for_duration)
async def process_custom_credits(message: Message, state: FSMContext):
    """Обработка ввода пользовательского количества кредитов"""
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
        
        data = await state.get_data()
        user_id = data["user_id"]
        
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
        await message.answer("⚠️ Неверный формат. Введите положительное число")

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
            username = f"@{gen['username']}" if gen['username'] else f"ID:{gen['user_id']}"
            gen_info = (
                f"\n🆔 ID: {gen['id']}",
                f"👤 Пользователь: {username}",
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