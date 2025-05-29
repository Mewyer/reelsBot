import os
from dotenv import load_dotenv
from typing import List

load_dotenv()

class Config:
    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: List[int] = [
        int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") 
        if id.strip().isdigit()
    ]
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # DEBUG, INFO, WARNING, ERROR
    
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    GPT_MODEL: str = os.getenv("GPT_MODEL", "gpt-4-1106-preview")
    
    # ElevenLabs
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_BASE_URL: str = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io/v1")
    DEFAULT_VOICE_ID: str = os.getenv("DEFAULT_VOICE_ID")
    MALE_VOICE_ID: str = os.getenv("MALE_VOICE_ID")
    FEMALE_VOICE_ID: str  = os.getenv("FEMALE_VOICE_ID")
    # Database
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "reelsbot")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "password")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "db")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    
    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    
    # Paths
    AUDIO_OUTPUT_DIR: str = os.getenv("AUDIO_OUTPUT_DIR", "generated_audio")
    TEMP_DIR: str = os.getenv("TEMP_DIR", "temp")
    ASSETS_DIR: str = os.getenv("ASSETS_DIR", "assets")
    
    # Тарифы
    FREE_DAILY_LIMIT = 1
    FREE_MONTHLY_LIMIT = 30
    LITE_DAILY_LIMIT = 5
    LITE_MONTHLY_LIMIT = 150
    PREMIUM_DAILY_LIMIT = 10
    PREMIUM_MONTHLY_LIMIT = 300

    # Цены подписок
    LITE_PRICE = 799
    PREMIUM_PRICE = 1599

    # Цены пакетов видео
    SINGLE_VIDEO_PRICE = 49
    PACK_5_VIDEOS_PRICE = 199
    PACK_10_VIDEOS_PRICE = 349
    PACK_20_VIDEOS_PRICE = 599
    
    # Security
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "")  

    # CryptoBot
    CRYPTOBOT_TOKEN: str = os.getenv("CRYPTOBOT_TOKEN", "")
    CRYPTOBOT_API_URL: str = os.getenv("CRYPTOBOT_API_URL", "https://pay.crypt.bot/api")
    CRYPTOBOT_CURRENCY: str = os.getenv("CRYPTOBOT_CURRENCY", "USDT")
    CRYPTOBOT_NETWORK: str = os.getenv("CRYPTOBOT_NETWORK", "TRON")
    @classmethod
    def validate(cls):
        required = [
            ("BOT_TOKEN", cls.BOT_TOKEN),
            ("OPENAI_API_KEY", cls.OPENAI_API_KEY),
            ("ELEVENLABS_API_KEY", cls.ELEVENLABS_API_KEY),
            ("POSTGRES_PASSWORD", cls.POSTGRES_PASSWORD)
        ]
        
        missing = [name for name, value in required if not value]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

config = Config()
config.validate()