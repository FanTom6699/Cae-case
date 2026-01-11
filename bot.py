import asyncio
import os
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from database import db

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    await db.create_tables()

    @dp.message(CommandStart())
    async def cmd_start(message: types.Message):
        user_id = message.from_user.id
        # Пытаемся взять @username, если его нет — берем First Name
        username = message.from_user.username or message.from_user.first_name
        
        if await db.user_exists(user_id):
            user_data = await db.get_user(user_id)
            
            builder = ReplyKeyboardBuilder()
            builder.row(types.KeyboardButton(text="📦 Открыть Кейс"), types.KeyboardButton(text="🏎 Мой Гараж"))
            builder.row(types.KeyboardButton(text="💰 Баланс"), types.KeyboardButton(text="🏆 Топ игроков"))

            # Короткое приветствие без лишнего текста
            await message.answer(
                f"👋 **С возвращением, {user_data['username']}!**\n\n"
                f"Твой баланс: `{user_data['coins']}` **Coins**.\n"
                f"Что планируешь делать?",
                reply_markup=builder.as_markup(resize_keyboard=True),
                parse_mode="Markdown"
            )
        else:
            builder = InlineKeyboardBuilder()
            builder.row(types.InlineKeyboardButton(
                text="📝 Зарегистрироваться", 
                callback_data="register_me")
            )

            await message.answer(
                f"Привет, **{username}**! 👋\n\n"
                "Чтобы начать собирать коллекцию машин, тебе нужно зарегистрироваться в системе CarCase.",
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )

    @dp.callback_query(F.data == "register_me")
    async def process_registration(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        # При регистрации сохраняем именно Username (ник)
        username = callback.from_user.username or callback.from_user.first_name

        if not await db.user_exists(user_id):
            await db.add_user(user_id, username)
            
            builder = ReplyKeyboardBuilder()
            builder.row(types.KeyboardButton(text="📦 Открыть Кейс"), types.KeyboardButton(text="🏎 Мой Гараж"))
            builder.row(types.KeyboardButton(text="💰 Баланс"), types.KeyboardButton(text="🏆 Топ игроков"))

            await callback.message.edit_text(
                f"✅ **Регистрация успешна!**\n\n"
                f"Добро пожаловать, `{username}`! На твой счет зачислено **1000 Coins**.\n"
                f"Удачи в открытии кейсов! 🏎💨",
                parse_mode="Markdown"
            )
            await callback.message.answer(
                "Выбери действие в меню ниже:",
                reply_markup=builder.as_markup(resize_keyboard=True)
            )
        else:
            await callback.answer("Ты уже в системе!", show_alert=True)

    @dp.message(F.text == "💰 Баланс")
    async def show_balance(message: types.Message):
        user_data = await db.get_user(message.from_user.id)
        if user_data:
            await message.answer(
                f"💰 Твой баланс: `{user_data['coins']}` **Coins**",
                parse_mode="Markdown"
            )

    try:
        print("🏎 CarCase Bot запущен!")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
