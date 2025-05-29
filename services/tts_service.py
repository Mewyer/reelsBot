from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings
from config import config
from typing import Optional
import logging
import os
import asyncio
from pathlib import Path
import time
import shutil

logger = logging.getLogger(__name__)

class TTSService:
    def __init__(self):
        self.client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
        self.default_voice_id = config.DEFAULT_VOICE_ID
        self.voice_options = {
            "male": config.MALE_VOICE_ID,  # Добавьте в config.py MALE_VOICE_ID
            "female": config.FEMALE_VOICE_ID  # Добавьте в config.py FEMALE_VOICE_ID
        }
        self.default_model = "eleven_multilingual_v2"
        self.max_retries = 3
        self.retry_delay = 5
        self.output_dir = Path(os.getenv("AUDIO_OUTPUT_DIR", "/tmp/generated_audio"))
        
        try:
            self.output_dir.mkdir(exist_ok=True, parents=True)
            # Тест записи в директорию
            test_file = self.output_dir / "write_test.tmp"
            with open(test_file, "w") as f:
                f.write("test")
            test_file.unlink()
            logger.info(f"Audio output directory ready: {self.output_dir.absolute()}")
        except Exception as e:
            logger.error(f"Failed to initialize output directory: {str(e)}")
            raise RuntimeError("Could not initialize TTS output directory")

    async def generate_audio(
        self,
        text: str,
        output_path: Optional[str] = None,
        voice_id: Optional[str] = None,
        voice_gender: Optional[str] = None  # Добавляем параметр для выбора пола голоса
    ) -> bool:
        """Генерация аудио с проверкой на каждом этапе"""
        if not text or not isinstance(text, str):
            logger.error("Invalid text for TTS")
            return False
            
        # Выбираем голос: если указан voice_id - используем его, иначе по полу, иначе дефолтный
        if voice_id:
            voice_id = voice_id
        elif voice_gender and voice_gender in self.voice_options:
            voice_id = self.voice_options[voice_gender]
        else:
            voice_id = self.default_voice_id
        
        # Генерация пути если не указан
        if not output_path:
            timestamp = int(time.time())
            filename = f"audio_{voice_id}_{timestamp}.mp3"
            output_path = str(self.output_dir / filename)
        else:
            output_path = str(Path(output_path).absolute())

        temp_path = None
        try:
            # Создаем временный файл в той же директории
            temp_path = f"{output_path}.tmp"
            
            for attempt in range(1, self.max_retries + 1):
                try:
                    logger.info(f"Attempt {attempt} to generate audio (text length: {len(text)})")
                    
                    # Генерация аудио
                    response = self.client.text_to_speech.convert(
                        voice_id=voice_id,
                        text=text,
                        model_id=self.default_model,
                        voice_settings=VoiceSettings(
                            stability=0.8,
                            similarity_boost=0.75,
                            style=0.0,
                            speaker_boost=True
                        )
                    )
                    
                    # Запись во временный файл
                    with open(temp_path, "wb") as f:
                        for chunk in response:
                            if chunk:
                                f.write(chunk)
                    
                    # Проверка временного файла
                    if not os.path.exists(temp_path):
                        raise Exception("Temporary audio file was not created")
                        
                    temp_size = os.path.getsize(temp_path)
                    if temp_size == 0:
                        raise Exception("Generated audio file is empty")
                    
                    # Проверка заголовка MP3
                    with open(temp_path, "rb") as f:
                        header = f.read(3)
                        if header != b'ID3' and not header.startswith(b'\xFF\xFB'):
                            raise Exception("Invalid audio file format")
                    
                    # Переносим в итоговый файл
                    shutil.move(temp_path, output_path)
                    logger.info(f"Audio successfully saved to {output_path} (size: {temp_size} bytes)")
                    return True
                    
                except Exception as e:
                    logger.error(f"TTS error on attempt {attempt}: {str(e)}")
                    
                    # Удаляем временный файл если есть
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    
                    if attempt < self.max_retries:
                        delay = self.retry_delay * attempt
                        logger.info(f"Retrying in {delay} seconds...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error("All attempts failed")
                        return await self._try_fallback_service(text, output_path)
            
            return False
            
        except Exception as e:
            logger.error(f"Fatal error in audio generation: {str(e)}", exc_info=True)
            return False
        finally:
            # Убедимся что временный файл удален
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

    async def _try_fallback_service(self, text: str, output_path: str) -> bool:
        """Резервный сервис TTS"""
        try:
            logger.warning("Trying fallback TTS service (gTTS)...")
            try:
                from gtts import gTTS
                
                # Создаем временный файл
                temp_path = f"{output_path}.tmp"
                tts = gTTS(text=text, lang='ru')
                tts.save(temp_path)
                
                # Проверяем результат
                if not os.path.exists(temp_path):
                    raise Exception("Fallback audio file was not created")
                
                file_size = os.path.getsize(temp_path)
                if file_size == 0:
                    raise Exception("Fallback audio file is empty")
                
                # Переносим в итоговый файл
                shutil.move(temp_path, output_path)
                logger.info(f"Fallback audio saved to {output_path} (size: {file_size} bytes)")
                return True
                
            except ImportError:
                logger.error("gTTS not installed, cannot use fallback")
                return False
            except Exception as e:
                logger.error(f"Fallback TTS error: {str(e)}")
                return False
        finally:
            if 'temp_path' in locals() and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

tts_service = TTSService()