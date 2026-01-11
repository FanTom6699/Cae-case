import asyncio
import os
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from database import db

# Загрузка настроек
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
        
        if await db.user_exists(user_id):
            # Если пользователь уже есть в базе
            user_data = await db.get_user(user_id)
            
            builder = ReplyKeyboardBuilder()
            builder.row(types.KeyboardButton(text="📦 Открыть Кейс"), types.KeyboardButton(text="🏎 Мой Гараж"))
            builder.row(types.KeyboardButton(text="💰 Баланс"), types.KeyboardButton(text="🏆 Топ игроков"))

            await message.answer(
                f"🏎 **С возвращением на трассу, {user_data['username']}!**\n\n"
                f"Твои тачки заждались в гараже. Готов к новым заездам? 🏁\n"
                f"Твой баланс: `{user_data['coins']}` **Coins**",
                reply_markup=builder.as_markup(resize_keyboard=True),
                parse_mode="Markdown"
            )
        else:
            # Если пользователя нет в базе
            builder = InlineKeyboardBuilder()
            builder.row(types.InlineKeyboardButton(
                text="📝 Зарегистрироваться", 
                callback_data="register_me")
            )

            await message.answer(
                "👋 **Добро пожаловать в CarCase!**\n\n"
                "Это элитный клуб коллекционеров автомобилей. Чтобы начать собирать свой гараж "
                "и открывать кейсы, тебе нужно пройти быструю регистрацию.",
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )

    @dp.callback_query(F.data == "register_me")
    async def process_registration(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        username = callback.from_user.username or callback.from_user.first_name

        if not await db.user_exists(user_id):
            await db.add_user(user_id, username)
            
            builder = ReplyKeyboardBuilder()
            builder.row(types.KeyboardButton(text="📦 Открыть Кейс"), types.KeyboardButton(text="🏎 Мой Гараж"))
            builder.row(types.KeyboardButton(text="💰 Баланс"), types.KeyboardButton(text="🏆 Топ игроков"))

            await callback.message.edit_text(
                f"✅ **Регистрация успешна!**\n\n"
                f"Добро пожаловать в игру, `{username}`! Мы начислили тебе стартовые **1000 Coins**. "
                f"Удачи в открытии кейсов! 🏎💨",
                parse_mode="Markdown"
            )
            # Отправляем клавиатуру новым сообщением, так как edit_text не меняет Reply-клавиатуру
            await callback.message.answer(
                "Воспользуйся меню ниже, чтобы начать играть! ↓",
                reply_markup=builder.as_markup(resize_keyboard=True)
            )
        else:
            await callback.answer("Ты уже зарегистрирован! 🏎", show_alert=True)

    @dp.message(F.text == "💰 Баланс")
    async def show_balance(message: types.Message):
        user_data = await db.get_user(message.from_user.id)
        if user_data:
            await message.answer(
                f"💳 **Твой финансовый счет:**\n\n"
                f"Доступно: `{user_data['coins']}` **Coins**\n"
                f"Трать их с умом! 🚀",
                parse_mode="Markdown"
            )
        else:
            await message.answer("Сначала зарегистрируйся через /start!")

    # Запуск бота
    try:
        print("🏎 CarCase Bot запущен и готов к гонкам!")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
