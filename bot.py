import asyncio
import os
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from database import db

# Загружаем переменные из .env (который у тебя уже есть в PowerShell)
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    # Инициализация БД
    await db.create_tables()

    @dp.message(CommandStart())
    async def cmd_start(message: types.Message):
        await db.register_user(message.from_user.id, message.from_user.username)
        balance = await db.get_user_balance(message.from_user.id)
        
        builder = ReplyKeyboardBuilder()
        builder.row(types.KeyboardButton(text="📦 Открыть Кейс"), types.KeyboardButton(text="🏎 Мой Гараж"))
        builder.row(types.KeyboardButton(text="💰 Баланс"), types.KeyboardButton(text="🏆 Топ"))

        welcome_msg = (
            f"🏎 **CarCase приветствует тебя, {message.from_user.first_name}!**\n\n"
            f"Твой двигатель прогрет, а в кармане **{balance} Coins**. "
            f"Готов собрать коллекцию, которой позавидуют все? 🏁\n\n"
            f"Жми на кнопку ниже и испытай удачу!"
        )

        await message.answer(
            welcome_msg,
            reply_markup=builder.as_markup(resize_keyboard=True),
            parse_mode="Markdown"
        )

    @dp.message(F.text == "💰 Баланс")
    async def check_balance(message: types.Message):
        balance = await db.get_user_balance(message.from_user.id)
        await message.answer(
            f"💵 На твоем счету: **{balance} Coins**\n"
            f"Трать их с умом... или спусти всё на кейсы! 🚀",
            parse_mode="Markdown"
        )

    # Запуск
    try:
        print("🏎 CarCase Bot запущен!")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
