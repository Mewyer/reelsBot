import logging
from pathlib import Path
from typing import Optional
from config import config

def setup_logging(log_dir: str = "logs", log_file: str = "bot.log"):
    """Настройка системы логирования"""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    formatter = logging.Formatter(log_format)
    
    # Создаем директорию для логов
    log_path = Path(log_dir) / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Основной логгер
    logger = logging.getLogger()
    logger.setLevel(config.LOG_LEVEL)

    # Файловый обработчик
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Уменьшаем логирование для внешних библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("openai").setLevel(logging.WARNING)