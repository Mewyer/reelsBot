from aiogram import Router, F
from aiogram.types import Message, FSInputFile, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from services import gpt_service, tts_service, video_service
import time
from services.database import db
from datetime import datetime, timedelta
from config import config
from utils.file_utils import generate_temp_file_path
import logging
import os
import asyncio
from aiohttp import ClientConnectorError
import re

router = Router()

class GenerationStates(StatesGroup):
    waiting_for_idea = State()
    waiting_for_style = State()
    waiting_for_background = State()
    previewing_script = State()
    editing_script = State()

class ProfileStates(StatesGroup):
    waiting_niche = State()
    waiting_style = State()
    waiting_goals = State()
    waiting_tone = State()
    waiting_audience = State()

async def check_usage_limit(user_id: int) -> tuple:
    """Check if user has exceeded daily limit"""
    subscription = await db.get_user_subscription(user_id)
    daily_limit = (
        config.PREMIUM_DAILY_LIMIT 
        if subscription == "premium" 
        else config.FREE_DAILY_LIMIT
    )
    
    usage = await db.get_user_usage(user_id)
    credits = await db.get_video_credits(user_id)
    
    # Если есть кредиты, разрешаем генерацию независимо от лимита
    if credits > 0:
        return (True, credits - 1)  # (can_generate, remaining_credits)
    
    return (usage < daily_limit, daily_limit - usage - 1)

async def _get_available_backgrounds():
    backgrounds = []
    bg_dir = "video_assets"
    
    if not os.path.exists(bg_dir):
        os.makedirs(bg_dir, exist_ok=True)
        return backgrounds
    
    for filename in os.listdir(bg_dir):
        if filename.endswith(('.mp4', '.mov', '.avi')):
            name = filename.split('.')[0].replace('_', ' ').capitalize()
            backgrounds.append({
                'filename': filename,
                'name': name,
                'path': os.path.join(bg_dir, filename)
            })
    return backgrounds

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    profile = await db.get_user_profile(user_id)
    
    if profile:
        await message.answer(f"👋 С возвращением, {message.from_user.first_name}!\nВаш профиль уже настроен. Можете создать видео: /generate или посмотреть ваш профиль /status")
        return
    
    await state.set_state(ProfileStates.waiting_niche)
    await message.answer("👋 Добро пожаловать! Давайте настроим ваш профиль.\n\n📌 В какой нише вы создаете контент? (пример: красота, бизнес, спорт)")

@router.message(ProfileStates.waiting_niche)
async def process_niche(message: Message, state: FSMContext):
    await state.update_data(niche=message.text)
    await state.set_state(ProfileStates.waiting_style)
    await message.answer("🎬 Какой стиль подачи предпочитаете?\n(пример: экспертный, развлекательный, вдохновляющий)")

@router.message(ProfileStates.waiting_style)
async def process_style(message: Message, state: FSMContext):
    await state.update_data(content_style=message.text)
    await state.set_state(ProfileStates.waiting_goals)
    await message.answer("🎯 Какие цели у вашего контента?\n(пример: продажи, обучение, развлечение)")

@router.message(ProfileStates.waiting_goals)
async def process_goals(message: Message, state: FSMContext):
    await state.update_data(goals=message.text)
    await state.set_state(ProfileStates.waiting_tone)
    await message.answer("🗣 Какой тон общения предпочитаете?\n(пример: дружеский, профессиональный, провокационный)")

@router.message(ProfileStates.waiting_tone)
async def process_tone(message: Message, state: FSMContext):
    await state.update_data(tone_of_voice=message.text)
    await state.set_state(ProfileStates.waiting_audience)
    await message.answer("👥 Опишите вашу целевую аудиторию\n(пример: женщины 25-35, предприниматели, подростки)")

@router.message(ProfileStates.waiting_audience)
async def process_audience(message: Message, state: FSMContext):
    profile_data = await state.get_data()
    profile_data["target_audience"] = message.text
    
    try:
        await db.save_user_profile(message.from_user.id, profile_data)
        await state.clear()
        await message.answer("✅ Профиль успешно сохранен!\n\nТеперь вы можете создавать персонализированные видео.\nОтправьте /generate чтобы начать или /status чтобы посмотреть профиль.")
    except Exception as e:
        logging.error(f"Ошибка сохранения профиля: {e}")
        await message.answer("⚠️ Не удалось сохранить профиль. Пожалуйста, попробуйте позже.")

@router.message(Command("generate"))
async def cmd_new_video(message: Message, state: FSMContext):
    user_id = message.from_user.id
    profile = await db.get_user_profile(user_id)
    
    if not profile:
        await message.answer("ℹ️ Пожалуйста, сначала настройте профиль: /start")
        return
    
    # Проверяем лимит
    can_generate, remaining = await check_usage_limit(user_id)
    if not can_generate:
        await message.answer(
            f"⚠️ Вы исчерпали дневной лимит генераций.\n"
            f"Лимит обновится через {_time_until_midnight()}.\n"
            f"Для увеличения лимита рассмотрите премиум подписку: /premium"
        )
        return
    
    await state.set_state(GenerationStates.waiting_for_idea)
    await message.answer("💡 Опишите идею для вашего видео (текстом или голосовым сообщением)\nНапример: '5 лайфхаков для путешествий'")

# Добавляем вспомогательную функциюapprove_script
def _time_until_midnight() -> str:
    now = datetime.now()
    midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    delta = midnight - now
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours} ч. {minutes} мин."

@router.message(GenerationStates.waiting_for_idea)
async def process_idea(message: Message, state: FSMContext):
    if message.voice:
        await message.answer("🔊 Голосовые сообщения пока не поддерживаются. Пожалуйста, отправьте текст.")
        return
    
    await state.update_data(idea=message.text)
    await state.set_state(GenerationStates.waiting_for_style)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Экспертный", callback_data="style_expert")
    builder.button(text="🎭 Развлекательный", callback_data="style_entertain")
    builder.button(text="💡 Вдохновляющий", callback_data="style_inspire")
    builder.button(text="🎥 Кинематографичный", callback_data="style_cinematic")
    builder.adjust(2)
    
    await message.answer("🎬 Выберите стиль для вашего видео:", reply_markup=builder.as_markup())

@router.callback_query(GenerationStates.waiting_for_style, F.data.startswith("style_"))
async def process_style_selection(callback: CallbackQuery, state: FSMContext):
    style_map = {
        "style_expert": "Экспертный",
        "style_entertain": "Развлекательный",
        "style_inspire": "Вдохновляющий",
        "style_cinematic": "Кинематографичный"
    }
    
    style = style_map.get(callback.data, "Экспертный")
    await state.update_data(style=style)
    await callback.message.edit_reply_markup()
    await state.set_state(GenerationStates.waiting_for_background)
    
    backgrounds = await _get_available_backgrounds()
    builder = InlineKeyboardBuilder()
    
    for bg in backgrounds:
        builder.button(text=f"🎥 {bg['name']}", callback_data=f"bg_preview_{bg['filename']}")
    builder.button(text="🚫 Без фона", callback_data="bg_none")
    builder.adjust(2)
    
    await callback.message.answer("🎥 Выберите фон для вашего видео:", reply_markup=builder.as_markup())
    

@router.callback_query(GenerationStates.waiting_for_background, F.data.startswith("bg_preview_"))
async def preview_background(callback: CallbackQuery):
    bg_filename = callback.data.replace("bg_preview_", "")
    bg_path = os.path.join("video_assets", bg_filename)
    
    if not os.path.exists(bg_path):
        await callback.answer("⚠️ Фон не найден", show_alert=True)
        return
    
    try:
        video = FSInputFile(bg_path)
        await callback.message.answer_video(
            video,
            caption=f"🎥 Предпросмотр фона: {bg_filename.split('.')[0].replace('_', ' ').capitalize()}",
            width=1080,
            height=1920
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Выбрать этот фон", callback_data=f"bg_select_{bg_filename}")
        builder.button(text="🔍 Посмотреть другие", callback_data="bg_show_all")
        builder.adjust(1)
        
        await callback.message.answer("Нравится этот фон?", reply_markup=builder.as_markup())
    except Exception as e:
        logging.error(f"Ошибка отправки предпросмотра фона: {e}")
        await callback.answer("⚠️ Не удалось отправить предпросмотр", show_alert=True)

@router.callback_query(GenerationStates.waiting_for_background, F.data.startswith("bg_select_"))
async def select_background(callback: CallbackQuery, state: FSMContext):
    bg_filename = callback.data.replace("bg_select_", "")
    await state.update_data(background=bg_filename)
    await callback.message.edit_reply_markup()
    await callback.message.answer("🔄 Генерирую текст для озвучки... Пожалуйста, подождите ⏳")
    
    user_id = callback.from_user.id
    data = await state.get_data()
    
    try:
        profile = await db.get_user_profile(user_id)
        script = await gpt_service.generate_script(
            f"Напиши текст для озвучки видео в {data['style']} стиле. Тема: {data['idea']}",
            profile
        )
        
        if not script:
            raise Exception("Не удалось создать текст для озвучки")
        
        await state.update_data(script=script)
        await state.set_state(GenerationStates.previewing_script)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="👍 Одобрить", callback_data="script_approve")
        builder.button(text="✍️ Редактировать", callback_data="script_edit")
        builder.button(text="🔄 Новый вариант", callback_data="script_regenerate")
        builder.button(text="❌ Отменить", callback_data="script_cancel")
        builder.adjust(1, repeat=True)
        
        await callback.message.answer(
            f"🎬 Текст для озвучки готов!\n\nСтиль: {data['style']}\nТема: {data['idea']}\nФон: {bg_filename.split('.')[0].replace('_', ' ').capitalize()}\n\n{script}",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logging.error(f"Ошибка генерации текста: {str(e)}")
        await callback.message.answer("⚠️ Не удалось создать текст для озвучки")
        await state.clear()

@router.callback_query(GenerationStates.waiting_for_background, F.data == "bg_show_all")
async def show_all_backgrounds(callback: CallbackQuery):
    backgrounds = await _get_available_backgrounds()
    builder = InlineKeyboardBuilder()
    
    for bg in backgrounds:
        builder.button(text=f"🎥 {bg['name']}", callback_data=f"bg_preview_{bg['filename']}")
    builder.button(text="🚫 Без фона", callback_data="bg_none")
    builder.adjust(2)
    
    await callback.message.answer("🎥 Доступные фоны:", reply_markup=builder.as_markup())

@router.callback_query(GenerationStates.waiting_for_background, F.data == "bg_none")
async def select_no_background(callback: CallbackQuery, state: FSMContext):
    await state.update_data(background=None)
    await callback.message.edit_reply_markup()
    
    user_id = callback.from_user.id
    data = await state.get_data()
    
    try:
        profile = await db.get_user_profile(user_id)
        script = await gpt_service.generate_script(
            f"Напиши текст для озвучки видео в {data['style']} стиле. Тема: {data['idea']}",
            profile
        )
        
        if not script:
            raise Exception("Не удалось создать текст для озвучки")
        
        await state.update_data(script=script)
        await state.set_state(GenerationStates.previewing_script)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="👍 Одобрить", callback_data="script_approve")
        builder.button(text="✍️ Редактировать", callback_data="script_edit")
        builder.button(text="🔄 Новый вариант", callback_data="script_regenerate")
        builder.button(text="❌ Отменить", callback_data="script_cancel")
        builder.adjust(1, repeat=True)
        
        await callback.message.answer(
            f"🎬 Текст для озвучки готов!\n\nСтиль: {data['style']}\nТема: {data['idea']}\nФон: Черный\n\n{script}",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logging.error(f"Ошибка генерации текста: {str(e)}")
        await callback.message.answer("⚠️ Не удалось создать текст для озвучки")
        await state.clear()

@router.message(Command("status"))
async def cmd_status(message: Message):
    """Проверка статуса подписки и кредитов"""
    user_id = message.from_user.id
    
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow(
            """SELECT subscription_type, subscription_expire, 
                  COALESCE(video_credits, 0) as video_credits,
                  (SELECT COUNT(*) FROM generations 
                   WHERE user_id = $1 AND DATE(created_at) = CURRENT_DATE) as generations_today
               FROM users WHERE user_id = $1""",
            user_id
        )
        
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        
        limit = (config.PREMIUM_DAILY_LIMIT 
                if user['subscription_type'] == 'premium' 
                else config.FREE_DAILY_LIMIT)
        
        status_msg = [
            f"📊 Ваш Профиль:",
            f"💎 Подписка: {user['subscription_type'].capitalize()}",
            f"📅 Осталось дней: {(user['subscription_expire'] - datetime.now()).days if user['subscription_expire'] else 0}",
            f"🎬 Генераций сегодня: {user['generations_today']}/{limit}",
            f"🎫 Видео-кредитов: {user['video_credits']}",
            f"\nКупить дополнительные видео: /buy_videos"
             f"\nКупить премиум: /subscribe"
        ]
        
        await message.answer("\n".join(status_msg))

@router.callback_query(GenerationStates.previewing_script, F.data == "script_approve")
async def approve_script(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    # Проверяем лимиты и кредиты
    can_generate, remaining = await check_usage_limit(user_id)
    credits = await db.get_video_credits(user_id)
    
    if not can_generate and credits <= 0:
        await callback.message.edit_reply_markup()
        await callback.message.answer(
            f"⚠️ Вы исчерпали дневной лимит генераций.\n"
            f"Лимит обновится через {_time_until_midnight()}.\n"
            f"Вы можете купить дополнительные видео: /buy_videos"
        )
        await state.clear()
        return
    
    await callback.message.edit_reply_markup()
    await callback.message.answer("⏳ Начинаю создание видео...")
    
    data = await state.get_data()
    audio_path = "audio_assets/"
    video_path = None
    
    try:
        # Если нет обычного лимита, но есть кредиты, используем кредит
        if not can_generate and credits > 0:
            await db.use_video_credit(user_id)
            credits -= 1
        
        # Логируем генерацию
        generation_id = await db.log_generation(
            user_id=user_id,
            prompt=f"Style: {data.get('style')}, Idea: {data.get('idea')}",
            status="processing"
        )
        
        voiceover_text = data['script']
        audio_filename = f"audio_{user_id}_{int(time.time())}.mp3"
        audio_path = os.path.join("generated_audio", audio_filename)
        
        os.makedirs("generated_audio", exist_ok=True)
        success = await tts_service.generate_audio(voiceover_text, audio_path)
        
        if not success or not os.path.exists(audio_path):
            raise Exception("Не удалось сгенерировать аудио")
        
        video_path = generate_temp_file_path("mp4")
        success = await video_service.create_video(
            script=data['script'],
            audio_path=audio_path,
            output_path=video_path,
            background=data.get('background')
        )
        
        if not success or not os.path.exists(video_path):
            raise Exception("Не удалось создать видео")
        
        # Обновляем статус генерации
        await db.update_generation(
            generation_id=generation_id,
            script=data['script'],
            audio_path=audio_path,
            video_path=video_path,
            status="completed"
        )
        
        video = FSInputFile(video_path)
        await callback.message.answer_video(
            video, 
            caption="🎬 Ваше видео готово!",
            width=1080,
            height=1920
        )
        
        # Показываем оставшийся лимит/кредиты
        if credits > 0:
            await callback.message.answer(
                f"🔄 Осталось видео-кредитов: {credits}\n"
                f"Купить еще: /buy_videos"
            )
        else:
            _, remaining = await check_usage_limit(user_id)
            await callback.message.answer(
                f"🔄 Осталось генераций сегодня: {remaining}\n"
                f"Лимит обновится через {_time_until_midnight()}"
            )
    except Exception as e:
        logging.error(f"Ошибка создания видео: {str(e)}")
        await callback.message.answer("⚠️ Ошибка при создании видео")
        # Обновляем статус генерации в случае ошибки
        if 'generation_id' in locals():
            await db.update_generation(
                generation_id=generation_id,
                status="failed"
            )
    finally:
        for path in [audio_path, video_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logging.error(f"Ошибка удаления файла {path}: {e}")
        await state.clear()


@router.message(Command("premium"))
async def cmd_premium(message: Message):
    await message.answer(
        "💎 Премиум подписка дает:\n\n"
        f"• {config.PREMIUM_DAILY_LIMIT} генераций в день (вместо {config.FREE_DAILY_LIMIT})\n"
        "• Приоритетную обработку\n"
        "• Доступ к эксклюзивным фонам\n\n"
        "Для оформления подписки введите /subscribe"
    )

@router.callback_query(GenerationStates.previewing_script, F.data == "script_edit")
async def request_script_edit(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Введите ваши правки к сценарию:")
    await state.set_state(GenerationStates.editing_script)

@router.message(GenerationStates.editing_script)
async def process_script_edit(message: Message, state: FSMContext):
    await message.answer("🔄 Применяю ваши правки...")
    
    user_id = message.from_user.id
    data = await state.get_data()
    
    try:
        profile = await db.get_user_profile(user_id)
        improved_script = await gpt_service.improve_script(data['script'], message.text, profile)
        
        if not improved_script:
            raise Exception("Не удалось изменить сценарий")
        
        await state.update_data(script=improved_script)
        await state.set_state(GenerationStates.previewing_script)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="👍 Одобрить", callback_data="script_approve")
        builder.button(text="✍️ Редактировать", callback_data="script_edit")
        builder.button(text="🔄 Новый вариант", callback_data="script_regenerate")
        builder.button(text="❌ Отменить", callback_data="script_cancel")
        builder.adjust(1, repeat=True)
        
        await message.answer(f"🔄 Сценарий обновлен!\n\n{improved_script}", reply_markup=builder.as_markup())
    except Exception as e:
        logging.error(f"Ошибка редактирования: {str(e)}")
        await message.answer("⚠️ Не удалось применить правки")
        await state.set_state(GenerationStates.previewing_script)

@router.callback_query(GenerationStates.previewing_script, F.data == "script_regenerate")
async def regenerate_script(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup()
    await callback.message.answer("🔄 Создаю новый вариант сценария...")
    
    user_id = callback.from_user.id
    data = await state.get_data()
    
    try:
        profile = await db.get_user_profile(user_id)
        script = await gpt_service.generate_script(
            f"Создай сценарий в стиле: {data['style']}\nТема: {data['idea']}",
            profile
        )
        
        if not script:
            raise Exception("Не удалось создать сценарий")
        
        await state.update_data(script=script)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="👍 Одобрить", callback_data="script_approve")
        builder.button(text="✍️ Редактировать", callback_data="script_edit")
        builder.button(text="🔄 Новый вариант", callback_data="script_regenerate")
        builder.button(text="❌ Отменить", callback_data="script_cancel")
        builder.adjust(1, repeat=True)
        
        await callback.message.answer(f"🆕 Новый вариант сценария готов!\n\n{script}", reply_markup=builder.as_markup())
    except Exception as e:
        logging.error(f"Ошибка перегенерации: {str(e)}")
        await callback.message.answer("⚠️ Не удалось создать новый вариант")

@router.callback_query(GenerationStates.previewing_script, F.data == "script_cancel")
async def cancel_generation(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup()
    await callback.message.answer("❌ Создание видео отменено")
    await state.clear()