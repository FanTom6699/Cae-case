import asyncio
import os
import random
import time
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from database import db

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

# Список машин по редкостям
CARS = {
    "Common": ["Lada Riva", "Ford Focus", "Hyundai Solaris", "Toyota Corolla"],
    "Rare": ["BMW M3 E46", "Audi RS6", "Subaru Impreza", "Nissan Skyline"],
    "Epic": ["Porsche 911", "Lamborghini Huracan", "Ferrari 458", "McLaren 720S"],
    "Legendary": ["Bugatti Chiron", "Koenigsegg Jesko", "Pagani Huayra", "Ferrari LaFerrari"]
}

def get_random_car():
    rand = random.randint(1, 100)
    if rand <= 2: # 2%
        rarity = "Legendary"
        emoji = "💎"
    elif rand <= 10: # 8%
        rarity = "Epic"
        emoji = "🟣"
    elif rand <= 30: # 20%
        rarity = "Rare"
        emoji = "🔵"
    else: # 70%
        rarity = "Common"
        emoji = "⚪"
    
    car_name = random.choice(CARS[rarity])
    return car_name, rarity, emoji

async def open_case_logic(message: types.Message):
    user_id = message.from_user.id
    if not await db.user_exists(user_id):
        return await message.answer("Сначала зарегистрируйся! Введи /start")

    user_data = await db.get_user(user_id)
    current_time = int(time.time())
    wait_time = 5 * 3600 # 5 часов в секундах
    
    if current_time - user_data['last_case_time'] < wait_time:
        remaining = wait_time - (current_time - user_data['last_case_time'])
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        return await message.answer(f"⏳ Твой гараж еще закрыт! Вернись через **{hours}ч. {minutes}м.**")

    # Процесс открытия
    car_name, rarity, emoji = get_random_car()
    await db.add_car_to_garage(user_id, car_name, rarity)
    await db.update_last_case_time(user_id)

    # Формируем сообщение по твоему запросу
    result_text = (
        f"📦 **Кейс открыт!**\n\n"
        f"Владелец: `{user_data['username']}`\n"
        f"🚗 Машина: **{car_name}**\n"
        f"✨ Редкость: {emoji} **{rarity}**"
    )
    
    await message.answer(result_text, parse_mode="Markdown")

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    await db.create_tables()

    @dp.message(CommandStart())
    async def cmd_start(message: types.Message):
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name
        
        if await db.user_exists(user_id):
            user_data = await db.get_user(user_id)
            builder = ReplyKeyboardBuilder()
            builder.row(types.KeyboardButton(text="📦 Открыть Кейс"), types.KeyboardButton(text="🏎 Мой Гараж"))
            builder.row(types.KeyboardButton(text="💰 Баланс"), types.KeyboardButton(text="🏆 Топ игроков"))

            await message.answer(
                f"👋 **С возвращением, {user_data['username']}!**\n"
                f"Твой баланс: `{user_data['coins']}` **Coins**.",
                reply_markup=builder.as_markup(resize_keyboard=True),
                parse_mode="Markdown"
            )
        else:
            builder = InlineKeyboardBuilder()
            builder.button(text="📝 Зарегистрироваться", callback_data="register_me")
            await message.answer(f"Привет, **{username}**! 👋\nЗарегистрируйся, чтобы начать играть.", reply_markup=builder.as_markup(), parse_mode="Markdown")

    @dp.callback_query(F.data == "register_me")
    async def process_registration(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        username = callback.from_user.username or callback.from_user.first_name
        if not await db.user_exists(user_id):
            await db.add_user(user_id, username)
            builder = ReplyKeyboardBuilder()
            builder.row(types.KeyboardButton(text="📦 Открыть Кейс"), types.KeyboardButton(text="🏎 Мой Гараж"))
            builder.row(types.KeyboardButton(text="💰 Баланс"), types.KeyboardButton(text="🏆 Топ игроков"))
            await callback.message.edit_text(f"✅ Регистрация успешна, `{username}`! Получено 1000 Coins.", parse_mode="Markdown")
            await callback.message.answer("Меню игрока:", reply_markup=builder.as_markup(resize_keyboard=True))

    # Обработка слов: Машина, Машинка, Кейс, и кнопки
    @dp.message(F.text.lower().in_({"машина", "машинка", "кейс", "кейсик", "📦 открыть кейс"}))
    async def open_case_trigger(message: types.Message):
        await open_case_logic(message)

    @dp.message(F.text == "💰 Баланс")
    async def show_balance(message: types.Message):
        user_data = await db.get_user(message.from_user.id)
        if user_data:
            await message.answer(f"💰 Баланс: `{user_data['coins']}` **Coins**", parse_mode="Markdown")

    try:
        print("🏎 CarCase Bot запущен!")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
