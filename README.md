# Reels Generator Bot 🤖🎬

Бот для автоматической генерации коротких видео в формате Reels/TikTok с использованием AI.

[![Docker](https://img.shields.io/badge/Docker-✓-blue?logo=docker)](https://docs.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-yellow?logo=python)](https://www.python.org/)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-green)](https://docs.aiogram.dev/)

## 🔥 Возможности

- Генерация сценариев через GPT-4
- Автоматическая озвучка через ElevenLabs
- Сборка видео с субтитрами (FFmpeg)
- Персонализация по профилю пользователя
- Система подписок и лимитов
- Админ-панель в Telegram

## 🛠 Технологии

- **Backend**: Python 3.10+ (Aiogram 3)
- **AI**: OpenAI GPT, ElevenLabs TTS
- **DB**: PostgreSQL + Redis
- **Инфра**: Docker, Nginx (опционально)

## 🚀 Быстрый старт

### 1. Требования
- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB+ RAM на сервере

### 2. Установка
```bash
git clone https://github.com/Mewyer/reelsBot
cd reels-bot
touch .env
nano .env  # Заполните ваши ключи
```
### 3. Запуск
```bash 
docker-compose up -d --build
```

### 4. Команды админа
- /admin - Панель управления
- /stats - Статистика использования
- /broadcast - Рассылка сообщений

### 5. Конфигурация .env файла 
```bash 
# Telegram
BOT_TOKEN=ваш_токен_бота
ADMIN_IDS=123,456  # ID через запятую

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1

# ElevenLabs
ELEVENLABS_API_KEY=ваш_ключ
ELEVENLABS_BASE_URL=https://api.elevenlabs.io/v1

# База данных
POSTGRES_PASSWORD=сложный_пароль
```

### 6. Структура проекта 
```bash 
reels-bot/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── requirements.txt
├── services/
│   ├── gpt_service.py
│   ├── tts_service.py
│   ├── database.py
│   └── ...
└── handlers/
    ├── user_handlers.py
    ├── admin_handlers.py
    └── ...
```
### 7. Команды управления
- docker-compose logs -f bot	Просмотр логов
- docker-compose exec db psql -U user reelsbot	Консоль PostgreSQL
- docker-compose down && docker-compose up -d --build	Пересборка

### 8. Команды пользователей
- /start - Начало работы
- /profile - Настройки профиля
- /generate - Создать видео
- /subscribe - Управление подпиской 

### Для разработчиков
``` bash
# Установка для разработки
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
