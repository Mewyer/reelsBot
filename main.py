import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from config import config
from handlers import user_handlers, admin_handlers, payment_handlers
from services.database import db
from utils.logging import setup_logging

async def on_startup(bot: Bot):
    """Initialize services and notify admins"""
    try:
        await db.connect()
        
        for admin_id in config.ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id, 
                    "🤖 Бот успешно запущен!\n"
                    f"Версия: {config.VERSION}\n"
                    f"Модель GPT: {config.GPT_MODEL}"
                )
            except Exception as e:
                logging.error(f"Failed to notify admin {admin_id}: {e}")
    except Exception as e:
        logging.error(f"Startup failed: {e}")
        raise

async def on_shutdown(bot: Bot):
    """Cleanup resources and notify admins"""
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "🛑 Бот выключается...")
        except Exception as e:
            logging.error(f"Failed to notify admin {admin_id}: {e}")
    
    if db.pool:
        await db.pool.close()

async def main():
    """Main application entry point"""
    setup_logging()
    
    # Initialize storage
    redis = Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        decode_responses=True
    )
    storage = RedisStorage(redis)
    
    # Initialize bot
    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher(storage=storage)
    
    # Register handlers
    dp.include_router(user_handlers.router)
    dp.include_router(admin_handlers.router)
    dp.include_router(payment_handlers.router)
    
    # Register lifecycle events
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Start polling
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        handle_signals=True
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())