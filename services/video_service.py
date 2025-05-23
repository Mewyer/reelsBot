import subprocess
import os
from pathlib import Path
from config import config
from utils.file_utils import generate_temp_file_path

async def create_video(script: str, audio_path: str, output_path: str) -> bool:
    try:
        # Генерация субтитров
        subtitles_path = generate_temp_file_path("srt")
        await _generate_subtitles(script, audio_path, subtitles_path)
        
        # Сборка видео с помощью ffmpeg
        cmd = [
            "ffmpeg",
            "-y",
            "-i", "assets/background.mp4",  # Фоновое видео
            "-i", audio_path,
            "-vf", f"subtitles={subtitles_path}:force_style='Fontsize=24,PrimaryColour=&HFFFFFF&'",
            "-shortest",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-strict", "experimental",
            output_path
        ]
        
        subprocess.run(cmd, check=True)
        return True
    except Exception as e:
        print(f"Video creation error: {str(e)}")
        return False
    finally:
        # Удаление временных файлов
        for path in [subtitles_path]:
            if path and os.path.exists(path):
                os.remove(path)

async def _generate_subtitles(script: str, audio_path: str, output_path: str):
    # Упрощенная генерация субтитров
    duration = _get_audio_duration(audio_path)
    with open(output_path, 'w') as f:
        f.write("1\n")
        f.write(f"00:00:00,000 --> 00:00:{duration:02d},000\n")
        f.write(script + "\n\n")

def _get_audio_duration(audio_path: str) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", 
        "format=duration", "-of", 
        "default=noprint_wrappers=1:nokey=1", audio_path
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout)