# ReelsBot - Telegram Bot for Video Generation

## Описание

ReelsBot - это Telegram бот для автоматического создания коротких видеороликов с текстом, озвучкой и фоновым видео. Бот предоставляет:
- Генерацию сценариев с помощью GPT
- Озвучку текста через ElevenLabs
- Создание видео с субтитрами через FFmpeg
- Систему подписок и разовых покупок
- Админ-панель для управления пользователями

## Технические требования

- Сервер с Ubuntu 20.04/22.04 (рекомендуется)
- Python 3.10+
- PostgreSQL 13+
- Redis 6+
- FFmpeg с поддержкой libx264
- Docker (опционально)

## Установка зависимостей

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка базовых зависимостей
sudo apt install -y python3-pip python3-venv git ffmpeg postgresql postgresql-contrib redis-server

# Проверка версии FFmpeg (должна быть не ниже 4.2)
ffmpeg -version

# Установка Docker (опционально)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

```

## Настройка базы данных PostgreSQL
```bash
# Вход в PostgreSQL
sudo -u postgres psql

# В консоли PostgreSQL:
CREATE DATABASE reelsbot;
CREATE USER reelsuser WITH PASSWORD 'your_strong_password';
GRANT ALL PRIVILEGES ON DATABASE reelsbot TO reelsuser;
ALTER DATABASE reelsbot OWNER TO reelsuser;
\q
```

## Настройка Redis
```bash 
# Редактируем конфиг Redis
sudo nano /etc/redis/redis.conf

# Убедитесь что есть следующие параметры:
maxmemory 256mb
maxmemory-policy allkeys-lru

# Перезапускаем Redis
sudo systemctl restart redis
```

## Установка проекта
```bash
# Клонируем репозиторий
git clone https://github.com/Mewyer/reelsBot
cd reelsbot

# Создаем виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Устанавливаем зависимости
pip install -r requirements.txt

# Создаем файл .env
cp .env.example .env
nano .env
```

## Конфигурация (.env)

```bash 
# Telegram
BOT_TOKEN=your_bot_token
ADMIN_IDS=123456789,987654321  # ID админов через запятую

# OpenAI
OPENAI_API_KEY=your_openai_key
OPENAI_BASE_URL=https://api.openai.com/v1
GPT_MODEL=gpt-4-1106-preview

# ElevenLabs
ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_BASE_URL=https://api.elevenlabs.io/v1
DEFAULT_VOICE_ID=your_default_voice_id
MALE_VOICE_ID=your_male_voice_id
FEMALE_VOICE_ID=your_female_voice_id

# Database
POSTGRES_DB=reelsbot
POSTGRES_USER=reelsuser
POSTGRES_PASSWORD=your_strong_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# CryptoBot
CRYPTOBOT_TOKEN=your_cryptobot_token
CRYPTOBOT_API_URL=https://pay.crypt.bot/api
CRYPTOBOT_CURRENCY=USDT
CRYPTOBOT_NETWORK=TRON

# Paths
AUDIO_OUTPUT_DIR=generated_audio
TEMP_DIR=temp
ASSETS_DIR=assets
```

## Инициализация базы данных

```bash 
# Создаем таблицы
python -m alembic upgrade head

# Или вручную (если не используется Alembic)
psql -U reelsuser -d reelsbot -f init_db.sql
```

## Запуск бота
```bash 
# Сборка образа
docker build -t reelsbot .

# Запуск контейнера
docker run -d --name reelsbot \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/assets:/app/assets \
  -v $(pwd)/generated_audio:/app/generated_audio \
  -v $(pwd)/temp:/app/temp \
  --restart unless-stopped \
  reelsbot
```
## Устранение неполадок
- Бот не запускается

   - Проверьте .env файл на наличие всех обязательных переменных

   - Проверьте логи: journalctl -u reelsbot -f

- Проблемы с базой данных

   - Проверьте подключение: psql -U reelsuser -d reelsbot

   - Убедитесь что пользователь имеет права на базу данных

- Ошибки генерации видео

   - Проверьте что FFmpeg установлен: ffmpeg -version

   - Убедитесь что есть свободное место на диске

- Проблемы с оплатой

   - Проверьте токен CryptoBot в .env

   - Убедитесь что бот доступен по HTTPS (необходимо для webhook)
