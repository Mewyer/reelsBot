import subprocess
import os
from pathlib import Path
from config import config
from utils.file_utils import generate_temp_file_path
import logging
import math
import re
from typing import Optional

logger = logging.getLogger(__name__)

def extract_captions(full_script: str) -> str:
    """Извлекает текст для субтитров из сценария"""
    caption_lines = []
    lines = full_script.split('\n')
    
    for line in lines:
        line = line.strip()
        if line.startswith("caption:") or line.startswith("Captions:"):
            clean_line = re.sub(r'^(caption:|Captions:)\s*', '', line, flags=re.IGNORECASE)
            if clean_line:
                caption_lines.append(clean_line)
    
    return '\n'.join(caption_lines)

def _has_audio_stream(file_path: str) -> bool:
    """Проверяет, есть ли в файле аудиопоток"""
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=codec_type", 
            "-of", "default=nokey=1:noprint_wrappers=1", file_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.returncode == 0 and result.stdout.strip() == "audio"
    except Exception as e:
        logger.error(f"Ошибка проверки аудиопотока: {str(e)}")
        return False

async def create_video(
    script: str, 
    audio_path: str, 
    output_path: str, 
    background: Optional[str] = None
) -> bool:
    subtitles_path = None
    bg_path = None
    looped_video_path = None
    normalized_audio_path = None
    
    try:
        # Проверяем обязательные параметры
        if not audio_path or not isinstance(audio_path, str):
            raise ValueError("Неверный путь к аудио файлу")
            
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Аудио файл не найден: {audio_path}")
        
        # Нормализуем аудио (увеличиваем громкость)
        normalized_audio_path = generate_temp_file_path("mp3")
        normalize_cmd = [
            "ffmpeg",
            "-y",
            "-i", audio_path,
            "-af", "volume=3.0",
            normalized_audio_path
        ]
        subprocess.run(normalize_cmd, check=True)
        
        # Получаем длительность аудио
        audio_duration = _get_audio_duration(normalized_audio_path)
        
        # Если фон не указан, используем черный фон
        if not background:
            # Создаем черный фон с помощью FFmpeg
            bg_path = generate_temp_file_path("mp4")
            cmd_create_bg = [
                "ffmpeg",
                "-y",
                "-f", "lavfi",
                "-i", "color=c=black:s=1080x1920:d=60",
                "-f", "lavfi",
                "-i", "anullsrc=r=44100:cl=mono",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-t", "60",
                "-shortest",
                bg_path
            ]
            subprocess.run(cmd_create_bg, check=True)
        else:
            # Проверяем и выбираем фон
            bg_path = os.path.join("video_assets", background)
            if not os.path.exists(bg_path):
                raise FileNotFoundError(f"Фоновое видео не найдено: {bg_path}")
            
            # Проверяем длительность фона
            bg_duration = _get_video_duration(bg_path)
            
            # Если видео короче аудио, создаем зацикленную версию
            if bg_duration < audio_duration:
                looped_video_path = generate_temp_file_path("mp4")
                loops = math.ceil(audio_duration / bg_duration) + 1
                
                cmd_loop_video = [
                    "ffmpeg",
                    "-y",
                    "-stream_loop", str(loops),
                    "-i", bg_path,
                    "-c", "copy",
                    "-t", str(audio_duration),
                    looped_video_path
                ]
                subprocess.run(cmd_loop_video, check=True)
                bg_path = looped_video_path

        # Генерация субтитров
        subtitles_path = generate_temp_file_path("srt")
        captions_text = extract_captions(script)
        await _generate_dynamic_subtitles(
            captions_text if captions_text else script, 
            normalized_audio_path, 
            subtitles_path
        )
        
        # Проверяем, есть ли аудио в фоновом видео
        has_bg_audio = _has_audio_stream(bg_path)

        # Формируем фильтры для FFmpeg
        filter_complex = [
            f"[0:v]subtitles='{subtitles_path}':force_style="
            "'Fontsize=12,"
            "PrimaryColour=&HFFFFFF&,"
            "OutlineColour=&H000000&,"
            "BorderStyle=1,"
            "Outline=1,"
            "Shadow=0,"
            "Alignment=2,"
            "MarginV=30,"
            "MarginL=20,MarginR=20,"
            "FontName=Arial,"
            "WrapStyle=1'[v]"
        ]

        # Добавляем аудиофильтры в зависимости от наличия аудио в фоне
        if has_bg_audio:
            filter_complex.extend([
                "[0:a]volume=0.1[bg_audio]",
                "[1:a]volume=1.0[voice_audio]",
                "[bg_audio][voice_audio]amix=inputs=2:duration=first[a]"
            ])
        else:
            filter_complex.append("[1:a]volume=1.0[a]")

        # Формируем полную команду FFmpeg
        cmd = [
            "ffmpeg",
            "-y",
            "-i", bg_path,
            "-i", normalized_audio_path,
            "-filter_complex", ";".join(filter_complex),
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-c:a", "aac",
            "-strict", "experimental",
            "-shortest",
            output_path
        ]
        
        logger.info(f"Выполняем команду ffmpeg: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.debug(f"Вывод ffmpeg: {result.stdout}")
        
        if not os.path.exists(output_path):
            raise Exception("Выходной видеофайл не был создан")
            
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка ffmpeg: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Ошибка создания видео: {str(e)}", exc_info=True)
        return False
    finally:
        # Очистка временных файлов
        for path in [subtitles_path, looped_video_path, normalized_audio_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.error(f"Ошибка удаления временного файла {path}: {e}")
        if bg_path and not background and os.path.exists(bg_path):
            try:
                os.remove(bg_path)
            except Exception as e:
                logger.error(f"Ошибка удаления временного фона: {e}")

async def _generate_dynamic_subtitles(script: str, audio_path: str, output_path: str):
    """Генерация субтитров с разбивкой по времени и переносом строк"""
    try:
        duration = _get_audio_duration(audio_path)
        if duration <= 0:
            raise ValueError("Некорректная длительность аудио")
        
        # Разбиваем текст на части по предложениям
        sentences = [s.strip() for s in re.split(r'[.!?]', script) if s.strip()]
        if not sentences:
            sentences = [script]
        
        # Рассчитываем время для каждого предложения
        segment_duration = duration / len(sentences)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, sentence in enumerate(sentences):
                start_time = i * segment_duration
                end_time = (i + 1) * segment_duration
                
                # Разбиваем длинные строки на 2 части
                words = sentence.split()
                if len(words) > 8:
                    mid = len(words) // 2
                    sentence = ' '.join(words[:mid]) + '\n' + ' '.join(words[mid:])
                
                # Конвертируем время в формат SRT
                def to_srt_time(seconds):
                    ms = int((seconds - int(seconds)) * 1000)
                    s = int(seconds) % 60
                    m = int(seconds // 60) % 60
                    h = int(seconds // 3600)
                    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                
                f.write(f"{i+1}\n")
                f.write(f"{to_srt_time(start_time)} --> {to_srt_time(end_time)}\n")
                f.write(f"{sentence}\n\n")
                
    except Exception as e:
        logger.error(f"Ошибка генерации субтитров: {str(e)}")
        raise

def _get_audio_duration(audio_path: str) -> float:
    """Получение длительности аудиофайла"""
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", 
            "format=duration", "-of", 
            "default=noprint_wrappers=1:nokey=1", audio_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if result.returncode != 0:
            raise Exception(f"Ошибка ffprobe: {result.stderr}")
            
        return float(result.stdout)
    except Exception as e:
        logger.error(f"Ошибка получения длительности аудио: {str(e)}")
        raise

def _get_video_duration(video_path: str) -> float:
    """Получение длительности видеофайла"""
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", 
            "format=duration", "-of", 
            "default=noprint_wrappers=1:nokey=1", video_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if result.returncode != 0:
            raise Exception(f"Ошибка ffprobe: {result.stderr}")
            
        return float(result.stdout)
    except Exception as e:
        logger.error(f"Ошибка получения длительности видео: {str(e)}")
        raise