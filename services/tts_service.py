from elevenlabs import AsyncClient, VoiceSettings
from elevenlabs.api.error import APIError
from config import config
from pathlib import Path
from typing import Optional
import logging
import backoff

logger = logging.getLogger(__name__)

class TTSService:
    def __init__(self):
        self.client = AsyncClient(
            api_key=config.ELEVENLABS_API_KEY,
            base_url=config.ELEVENLABS_BASE_URL,
            timeout=config.REQUEST_TIMEOUT
        )
        self.default_voice_id = config.DEFAULT_VOICE_ID
        self.default_settings = VoiceSettings(
            stability=0.5,
            similarity_boost=0.5
        )

    @backoff.on_exception(
        backoff.expo,
        (APIError, Exception),
        max_tries=3,
        logger=logger
    )
    async def generate_audio(
        self,
        text: str,
        output_path: str,
        voice_id: Optional[str] = None,
        stability: Optional[float] = None,
        similarity_boost: Optional[float] = None
    ) -> bool:
        """
        Generate audio from text using ElevenLabs API
        """
        try:
            voice_id = voice_id or self.default_voice_id
            settings = VoiceSettings(
                stability=stability if stability is not None else self.default_settings.stability,
                similarity_boost=similarity_boost if similarity_boost is not None else self.default_settings.similarity_boost
            )
            
            audio = await self.client.generate(
                text=text,
                voice=voice_id,
                model="eleven_monolingual_v2",
                voice_settings=settings
            )
            
            self._save_audio(audio, output_path)
            return True
            
        except APIError as e:
            logger.error(f"ElevenLabs API error: {e}")
            raise Exception(f"Audio generation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise Exception(f"Audio generation failed: {e}")

    def _save_audio(self, audio: bytes, output_path: str) -> None:
        """Save audio to file with directory creation"""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "wb") as f:
            f.write(audio)
        
        logger.info(f"Audio saved to {output_path}")

tts_service = TTSService()