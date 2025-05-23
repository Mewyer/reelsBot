from aiogram import Router, F
from aiogram.types import Message, FSInputFile, CallbackQuery
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import config
from services import gpt_service, tts_service, video_service
from services.database import db
from utils.file_utils import generate_temp_file_path
from typing import Optional, Dict, Any
import logging
import os

router = Router()

class GenerationStates(StatesGroup):
    waiting_for_prompt = State()

class ProfileStates(StatesGroup):
    waiting_niche = State()
    waiting_style = State()
    waiting_goals = State()
    waiting_tone = State()
    waiting_audience = State()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command with profile initialization"""
    user_id = message.from_user.id
    
    # Check if profile exists
    profile = await db.get_user_profile(user_id)
    if profile:
        await message.answer(
            f"👋 С возвращением, {message.from_user.first_name}!\n"
            "Ваш профиль уже настроен. Можете создать видео: /generate\n"
            "Или изменить профиль: /profile"
        )
        return
    
    # Start profile setup
    await state.set_state(ProfileStates.waiting_niche)
    await message.answer(
        "👋 Добро пожаловать! Давайте настроим ваш профиль.\n\n"
        "📌 В какой нише вы создаете контент? (пример: красота, бизнес, спорт)"
    )

# Profile setup handlers
@router.message(ProfileStates.waiting_niche)
async def process_niche(message: Message, state: FSMContext):
    await state.update_data(niche=message.text)
    await state.set_state(ProfileStates.waiting_style)
    await message.answer(
        "🎬 Какой стиль подачи предпочитаете?\n"
        "(пример: экспертный, развлекательный, вдохновляющий)"
    )

@router.message(ProfileStates.waiting_style)
async def process_style(message: Message, state: FSMContext):
    await state.update_data(content_style=message.text)
    await state.set_state(ProfileStates.waiting_goals)
    await message.answer(
        "🎯 Какие цели у вашего контента?\n"
        "(пример: продажи, обучение, развлечение)"
    )

@router.message(ProfileStates.waiting_goals)
async def process_goals(message: Message, state: FSMContext):
    await state.update_data(goals=message.text)
    await state.set_state(ProfileStates.waiting_tone)
    await message.answer(
        "🗣 Какой тон общения предпочитаете?\n"
        "(пример: дружеский, профессиональный, провокационный)"
    )

@router.message(ProfileStates.waiting_tone)
async def process_tone(message: Message, state: FSMContext):
    await state.update_data(tone_of_voice=message.text)
    await state.set_state(ProfileStates.waiting_audience)
    await message.answer(
        "👥 Опишите вашу целевую аудиторию\n"
        "(пример: женщины 25-35, предприниматели, подростки)"
    )

@router.message(ProfileStates.waiting_audience)
async def process_audience(message: Message, state: FSMContext):
    profile_data = await state.get_data()
    profile_data["target_audience"] = message.text
    
    try:
        await db.save_user_profile(message.from_user.id, profile_data)
        await state.clear()
        
        await message.answer(
            "✅ Профиль успешно сохранен!\n\n"
            "Теперь вы можете создавать персонализированные видео.\n"
            "Отправьте /generate чтобы начать."
        )
    except Exception as e:
        logging.error(f"Failed to save profile: {e}")
        await message.answer(
            "⚠️ Не удалось сохранить профиль. Пожалуйста, попробуйте позже."
        )

@router.message(Command("generate"))
async def cmd_generate(message: Message, state: FSMContext):
    """Handle video generation command"""
    user_id = message.from_user.id
    
    # Check profile exists
    profile = await db.get_user_profile(user_id)
    if not profile:
        await message.answer(
            "ℹ️ Пожалуйста, сначала настройте профиль: /start"
        )
        return
    
    await state.set_state(GenerationStates.waiting_for_prompt)
    await message.answer(
        "💡 Опишите идею для вашего видео (например: '5 лайфхаков для путешествий')"
    )

@router.message(GenerationStates.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    user_id = message.from_user.id
    prompt = message.text
    
    try:
        # Log generation in DB
        gen_id = await db.log_generation(user_id, prompt)
        
        # Get user profile
        profile = await db.get_user_profile(user_id)
        
        await message.answer("⏳ Генерирую сценарий...")
        
        # Generate script
        script = await gpt_service.generate_script(prompt, profile)
        await db.update_generation(gen_id, script=script, status="script_ready")
        
        await message.answer("⏳ Создаю озвучку...")
        
        # Generate audio
        audio_path = generate_temp_file_path("mp3")
        success = await tts_service.generate_audio(script, audio_path)
        if not success:
            raise Exception("TTS generation failed")
        await db.update_generation(gen_id, audio_path=audio_path, status="audio_ready")
        
        await message.answer("⏳ Собираю видео...")
        
        # Generate video
        video_path = generate_temp_file_path("mp4")
        success = await video_service.create_video(script, audio_path, video_path)
        if not success:
            raise Exception("Video generation failed")
        await db.update_generation(gen_id, video_path=video_path, status="completed")
        
        # Send result
        video = FSInputFile(video_path)
        await message.answer_video(video, caption="🎬 Ваше видео готово!")
        
    except Exception as e:
        logging.error(f"Generation failed: {e}")
        await db.update_generation(gen_id, status="failed")
        await message.answer(f"⚠️ Произошла ошибка: {e}")
    
    finally:
        await state.clear()
        # Cleanup temporary files
        for path in [audio_path, video_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logging.error(f"Failed to remove {path}: {e}")