import asyncio
import time
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import CommandStart, Command

# ================== НАСТРОЙКИ ==================

TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"

FREE_CASE_COOLDOWN = 5 * 60 * 60  # 5 часов

# ================== ПСЕВДО-БАЗА (временно) ==================
# позже спокойно вынесем в database.py

users = {}  # user_id -> dict


def get_user(user_id: int):
    if user_id not in users:
        users[user_id] = {
            "balance": 0,
            "cars": [],
            "last_free_case": 0,
        }
    return users[user_id]


def update_last_free_case_time(user_id: int):
    users[user_id]["last_free_case"] = int(time.time())


# ================== КЛАВИАТУРЫ ==================

def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚗 Гараж", callback_data="garage")],
            [InlineKeyboardButton(text="🎁 Бесплатный кейс", callback_data="free_case")],
        ]
    )


def back_to_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅ Назад", callback_data="menu")]
        ]
    )


# ================== БОТ ==================

bot = Bot(TOKEN)
dp = Dispatcher()


# ================== /start ==================

@dp.message(CommandStart())
async def start(message: Message):
    user = get_user(message.from_user.id)
    await message.answer(
        f"👋 Привет!\n"
        f"💰 Баланс: {user['balance']}\n\n"
        f"Выбери действие:",
        reply_markup=main_menu()
    )


# ================== МЕНЮ ==================

@dp.callback_query(F.callback_data == "menu")
async def menu(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    await callback.message.edit_text(
        f"🏠 Главное меню\n"
        f"💰 Баланс: {user['balance']}",
        reply_markup=main_menu()
    )
    await callback.answer()


# ================== ГАРАЖ ==================

@dp.callback_query(F.callback_data == "garage")
async def garage(callback: CallbackQuery):
    user = get_user(callback.from_user.id)

    if not user["cars"]:
        text = "🚗 Гараж пуст"
    else:
        text = "🚗 Твои машины:\n"
        for car in user["cars"]:
            text += f"• {car}\n"

    await callback.message.edit_text(
        text,
        reply_markup=back_to_menu()
    )
    await callback.answer()


# ================== FREE CASE ==================

@dp.callback_query(F.callback_data == "free_case")
async def free_case(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    now = int(time.time())

    last = user["last_free_case"]
    remaining = FREE_CASE_COOLDOWN - (now - last)

    if remaining > 0:
        left = str(timedelta(seconds=remaining))
        await callback.answer(
            f"⏳ Кейс будет доступен через {left}",
            show_alert=True
        )
        return

    # награда (пока common)
    reward = 200
    user["balance"] += reward
    update_last_free_case_time(callback.from_user.id)

    await callback.message.edit_text(
        f"🎁 Ты открыл бесплатный кейс!\n"
        f"💰 Получено: {reward}\n"
        f"💰 Баланс: {user['balance']}",
        reply_markup=main_menu()
    )
    await callback.answer()


# ================== ЗАПУСК ==================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())