from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import types
from datetime import datetime, timedelta
import logging
from config import config
from services.database import db
from services import subscription_service
from services.cryptobot import cryptobot
import asyncio

router = Router()
logger = logging.getLogger(__name__)

ONE_TIME_PURCHASES = {
    "single": {"name": "1 видео", "price": config.SINGLE_VIDEO_PRICE, "amount": 1},
    "pack5": {"name": "5 видео", "price": config.PACK_5_VIDEOS_PRICE, "amount": 5},
    "pack10": {"name": "10 видео", "price": config.PACK_10_VIDEOS_PRICE, "amount": 10},
    "pack20": {"name": "20 видео", "price": config.PACK_20_VIDEOS_PRICE, "amount": 20}
}

SUBSCRIPTION_PLANS = {
    "lite": {"name": "Lite (30 дней)", "price": config.LITE_PRICE, "duration": 30, "daily_limit": config.LITE_DAILY_LIMIT},
    "premium": {"name": "Premium (30 дней)", "price": config.PREMIUM_PRICE, "duration": 30, "daily_limit": config.PREMIUM_DAILY_LIMIT}
}

# Кэш для хранения созданных инвойсов
user_invoices = {}

@router.message(Command("buy_videos"))
async def cmd_buy_videos(message: Message):
    """Меню покупки разовых видео"""
    builder = InlineKeyboardBuilder()
    
    for purchase_id, purchase in ONE_TIME_PURCHASES.items():
        builder.add(types.InlineKeyboardButton(
            text=f"🎬 {purchase['name']} - {purchase['price']} руб",
            callback_data=f"buy_{purchase_id}"
        ))
    
    builder.add(types.InlineKeyboardButton(
        text="💎 Перейти на Lite",
        callback_data="subscribe_lite"
    ))
    builder.add(types.InlineKeyboardButton(
        text="💎 Перейти на Premium",
        callback_data="subscribe_premium"
    ))
    
    builder.adjust(1)
    
    await message.answer(
        "🎬 Выберите вариант покупки или подписки:",
        reply_markup=builder.as_markup()
    )

@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    """Меню выбора подписки"""
    builder = InlineKeyboardBuilder()
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        builder.add(types.InlineKeyboardButton(
            text=f"{plan['name']} - {plan['price']} руб",
            callback_data=f"subscribe_{plan_id}"
        ))
    builder.adjust(1)
    
    await message.answer(
        "💎 Выберите тариф подписки:",
        reply_markup=builder.as_markup()
    )

# Обработчик выбора разовой покупки
@router.callback_query(F.data.startswith("buy_"))
async def process_one_time_purchase(callback: CallbackQuery):
    """Обработка выбора разовой покупки"""
    purchase_id = callback.data.split("_")[1]
    purchase = ONE_TIME_PURCHASES.get(purchase_id)
    
    if not purchase:
        await callback.answer("❌ Неизвестный вариант покупки")
        return
    
    user_id = callback.from_user.id
    
    # Получаем курс USDT к рублю
    rate = await cryptobot.get_exchange_rate()
    if not rate:
        await callback.message.answer("⚠️ Не удалось получить курс обмена. Попробуйте позже.")
        return
    
    amount_usdt = round(purchase['price'] / rate, 2)
    
    # Создаем инвойс в CryptoBot
    invoice = await cryptobot.create_invoice(
        amount_usdt,
        user_id,
        description=f"One-time purchase: {purchase['name']}"
    )
    
    if not invoice:
        await callback.message.answer("⚠️ Не удалось создать платеж. Попробуйте позже.")
        return
    
    # Сохраняем информацию об инвойсе
    user_invoices[invoice['invoice_id']] = {
        "user_id": user_id,
        "purchase_id": purchase_id,
        "amount": amount_usdt,
        "status": "created",
        "type": "one_time"
    }
    
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(
        text="💰 Оплатить через CryptoBot",
        url=invoice['pay_url']
    ))
    builder.add(types.InlineKeyboardButton(
        text="✅ Я оплатил",
        callback_data=f"check_payment_{invoice['invoice_id']}"
    ))
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"💳 Оплата: {purchase['name']}\n"
        f"Сумма: {purchase['price']} руб (~{amount_usdt} {config.CRYPTOBOT_CURRENCY})\n"
        f"Сеть: {config.CRYPTOBOT_NETWORK}\n\n"
        "1. Нажмите кнопку '💰 Оплатить через CryptoBot'\n"
        "2. Оплатите счет в боте @CryptoBot\n"
        "3. Вернитесь сюда и нажмите '✅ Я оплатил'",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# Обновляем обработчик проверки платежа
@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery):
    """Проверка оплаты (обновленная версия для работы с разными типами платежей)"""
    invoice_id = int(callback.data.split("_")[2])
    invoice_info = user_invoices.get(invoice_id)
    
    if not invoice_info:
        await callback.answer("❌ Информация о платеже не найдена. Начните заново.")
        return
    
    # Проверяем статус инвойса
    invoice = await cryptobot.check_invoice(invoice_id)
    if not invoice:
        await callback.message.answer("⚠️ Не удалось проверить статус платежа. Попробуйте позже.")
        return
    
    if invoice.get("status") == "paid":
        user_id = callback.from_user.id
        
        if invoice_info['type'] == "one_time":
            # Обработка разовой покупки
            purchase = ONE_TIME_PURCHASES.get(invoice_info['purchase_id'])
            if purchase:
                await db.add_video_credits(user_id, purchase['amount'])
                user_invoices[invoice_id]['status'] = "completed"
                
                await callback.message.edit_text(
                    f"✅ Покупка {purchase['name']} успешно завершена!\n"
                    f"Вы получили {purchase['amount']} дополнительных видео.\n\n"
                    f"Теперь у вас {await db.get_video_credits(user_id)} видео-кредитов."
                )
        else:
            # Обработка подписки (старая логика)
            plan = SUBSCRIPTION_PLANS.get(invoice_info['plan_id'])
            if plan:
                await subscription_service.update_subscription(
                    user_id,
                    "premium",
                    plan["duration"],
                    db.pool
                )
                user_invoices[invoice_id]['status'] = "completed"
                
                await callback.message.edit_text(
                    f"✅ Подписка {plan['name']} активирована!\n"
                    f"Срок действия: {plan['duration']} дней\n\n"
                    "Теперь вы можете создавать больше видео каждый день!"
                )
    else:
        await callback.answer("ℹ️ Платеж еще не получен. Попробуйте позже.")
    
    await callback.answer()


@router.callback_query(F.data.startswith("subscribe_"))
async def process_subscription_selection(callback: CallbackQuery):
    """Обработка выбора тарифа"""
    plan_id = callback.data.split("_")[1]
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    
    if not plan:
        await callback.answer("❌ Неизвестный тариф")
        return
    
    user_id = callback.from_user.id
    
    # Получаем курс USDT к рублю
    rate = await cryptobot.get_exchange_rate()
    if not rate:
        await callback.message.answer("⚠️ Не удалось получить курс обмена. Попробуйте позже.")
        return
    
    amount_usdt = round(plan['price'] / rate, 2)
    
    # Создаем инвойс в CryptoBot
    invoice = await cryptobot.create_invoice(
    amount_usdt,
    user_id,
    description=f"Premium subscription for {plan['name']}"
)
    
    # Сохраняем информацию об инвойсе
    user_invoices[invoice['invoice_id']] = {
        "user_id": user_id,
        "plan_id": plan_id,
        "amount": amount_usdt,
        "status": "created"
    }
    
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(
        text="💰 Оплатить через CryptoBot",
        url=invoice['pay_url']
    ))
    builder.add(types.InlineKeyboardButton(
        text="✅ Я оплатил",
        callback_data=f"check_payment_{invoice['invoice_id']}"
    ))
    builder.adjust(1)
    
    await callback.message.edit_text(
        f"💳 Оплата подписки: {plan['name']}\n"
        f"Сумма: {plan['price']} руб (~{amount_usdt} {config.CRYPTOBOT_CURRENCY})\n"
        f"Сеть: {config.CRYPTOBOT_NETWORK}\n\n"
        "1. Нажмите кнопку '💰 Оплатить через CryptoBot'\n"
        "2. Оплатите счет в боте @CryptoBot\n"
        "3. Вернитесь сюда и нажмите '✅ Я оплатил'",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery):
    """Проверка оплаты"""
    invoice_id = int(callback.data.split("_")[2])
    invoice_info = user_invoices.get(invoice_id)
    
    if not invoice_info:
        await callback.answer("❌ Информация о платеже не найдена. Начните заново.")
        return
    
    plan = SUBSCRIPTION_PLANS.get(invoice_info['plan_id'])
    if not plan:
        await callback.answer("❌ Неизвестный тариф")
        return
    
    user_id = callback.from_user.id
    
    # Проверяем статус инвойса
    invoice = await cryptobot.check_invoice(invoice_id)
    if not invoice:
        await callback.message.answer("⚠️ Не удалось проверить статус платежа. Попробуйте позже.")
        return
    
    if invoice.get("status") == "paid":
        # Активируем подписку
        await subscription_service.update_subscription(
            user_id,
            "premium",
            plan["duration"],
            db.pool
        )
        
        # Обновляем статус инвойса
        user_invoices[invoice_id]['status'] = "completed"
        
        await callback.message.edit_text(
            f"✅ Подписка {plan['name']} активирована!\n"
            f"Срок действия: {plan['duration']} дней\n\n"
            "Теперь вы можете создавать больше видео каждый день!"
        )
    else:
        await callback.answer("ℹ️ Платеж еще не получен. Попробуйте позже.")
    
    await callback.answer()

@router.message(Command("status"))
async def cmd_status(message: Message):
    """Проверка статуса подписки и кредитов"""
    user_id = message.from_user.id
    
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow(
            """SELECT subscription_type, subscription_expire, 
                  COALESCE(video_credits, 0) as video_credits,
                  (SELECT COUNT(*) FROM generations 
                   WHERE user_id = $1 AND DATE(created_at) = CURRENT_DATE) as generations_today
               FROM users WHERE user_id = $1""",
            user_id
        )
        
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        
        limit = (config.PREMIUM_DAILY_LIMIT 
                if user['subscription_type'] == 'premium' 
                else config.FREE_DAILY_LIMIT)
        
        status_msg = [
            f"📊 Ваш статус:",
            f"💎 Подписка: {user['subscription_type'].capitalize()}",
            f"📅 Осталось дней: {(user['subscription_expire'] - datetime.now()).days if user['subscription_expire'] else 0}",
            f"🎬 Генераций сегодня: {user['generations_today']}/{limit}",
            f"🎫 Видео-кредитов: {user['video_credits']}",
            f"\nКупить дополнительные видео: /buy_videos"
        ]
        
        await message.answer("\n".join(status_msg))

@router.message(Command("admin_subscribe"))
async def admin_grant_subscription(message: Message, command: CommandObject):
    """Админ-команда для выдачи подписки"""
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("⛔ Доступ запрещен")
        return
    
    if not command.args:
        await message.answer("Использование: /admin_subscribe <user_id> <plan_id>")
        return
    
    try:
        args = command.args.split()
        user_id = int(args[0])
        plan_id = args[1]
        plan = SUBSCRIPTION_PLANS.get(plan_id)
        
        if not plan:
            await message.answer("❌ Неизвестный тариф. Доступные: 1 (30 дней), 2 (90 дней)")
            return
            
        await subscription_service.update_subscription(
            user_id,
            "premium",
            plan["duration"],
            db.pool
        )
        
        await message.answer(
            f"✅ Пользователю {user_id} выдана подписка {plan['name']}"
        )
    except Exception as e:
        logger.error(f"Ошибка выдачи подписки: {e}")
        await message.answer("❌ Ошибка. Формат: /admin_subscribe <user_id> <plan_id>")

async def check_pending_payments():
    """Фоновая задача для проверки pending платежей (обновленная версия)"""
    while True:
        try:
            # Проверяем все неоплаченные инвойсы
            for invoice_id, invoice_info in list(user_invoices.items()):
                if invoice_info['status'] == "created":
                    invoice = await cryptobot.check_invoice(invoice_id)
                    if invoice and invoice.get("status") == "paid":
                        user_id = invoice_info['user_id']
                        
                        if invoice_info['type'] == "one_time":
                            # Обработка разовой покупки
                            purchase = ONE_TIME_PURCHASES.get(invoice_info['purchase_id'])
                            if purchase:
                                await db.add_video_credits(user_id, purchase['amount'])
                                user_invoices[invoice_id]['status'] = "completed"
                                
                                # Уведомляем пользователя
                                try:
                                    await router.bot.send_message(
                                        chat_id=user_id,
                                        text=f"✅ Покупка {purchase['name']} успешно завершена!\n"
                                             f"Вы получили {purchase['amount']} дополнительных видео."
                                    )
                                except Exception as e:
                                    logger.error(f"Error notifying user: {e}")
                        else:
                            # Обработка подписки
                            plan = SUBSCRIPTION_PLANS.get(invoice_info['plan_id'])
                            if plan:
                                await subscription_service.update_subscription(
                                    user_id,
                                    "premium",
                                    plan["duration"],
                                    db.pool
                                )
                                user_invoices[invoice_id]['status'] = "completed"
                                
                                # Уведомляем пользователя
                                try:
                                    await router.bot.send_message(
                                        chat_id=user_id,
                                        text=f"✅ Ваша подписка {plan['name']} активирована!"
                                    )
                                except Exception as e:
                                    logger.error(f"Error notifying user: {e}")
            
            await asyncio.sleep(60)  # Проверяем каждую минуту
        except Exception as e:
            logger.error(f"Error in payment checking task: {e}")
            await asyncio.sleep(60)