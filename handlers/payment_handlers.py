from aiogram import Router
from aiogram.types import Message, PreCheckoutQuery, CallbackQuery
from aiogram.filters import Command, CommandsObject
from aiogram import F
from services import subscription_service

router = Router()

@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    # Здесь должна быть реализация выбора тарифа и инициации платежа
    await message.answer("Доступные подписки:\n\n"
                        "1. Премиум (30 дней) - 299 руб\n"
                        "2. Премиум (90 дней) - 799 руб\n\n"
                        "Выберите тариф /subscribe_1 или /subscribe_2")

@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def process_payment(message: Message, db_pool):
    user_id = message.from_user.id
    amount = message.successful_payment.total_amount // 100
    currency = message.successful_payment.currency
    
    # Определение типа подписки по сумме платежа
    if amount == 299:
        sub_type = "premium"
        duration = 30
    elif amount == 799:
        sub_type = "premium"
        duration = 90
    else:
        await message.answer("Неизвестный тариф подписки")
        return
    
    # Обновление подписки пользователя
    await subscription_service.update_subscription(user_id, sub_type, duration, db_pool)
    await message.answer(f"Подписка активирована на {duration} дней!")