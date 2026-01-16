import asyncio
import os
import math
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters import Command
from dotenv import load_dotenv

from database import (
    init_db,
    add_user,
    get_user,
    get_user_garage,
    set_user_coins,
)

# =========================
# INIT
# =========================

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# =========================
# НАСТРОЙКИ
# =========================

PER_PAGE = 5

RARITY_EMOJI = {
    "Common": "⚪",
    "Rare": "🔵",
    "Epic": "🟣",
    "Legendary": "💎",
}

SELL_PRICES = {
    "Common": 200,
    "Rare": 1000,
    "Epic": 5000,
    "Legendary": 50000,
}

# =========================
# КНОПКИ
# =========================

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Гараж", callback_data="garage:0")],
        [InlineKeyboardButton(text="🎁 Бесплатный кейс", callback_data="free_case")]
    ])


def garage_keyboard(cars, page, total_pages):
    kb = []

    for car in cars:
        emoji = RARITY_EMOJI.get(car["rarity"], "⚪")
        kb.append([
            InlineKeyboardButton(
                text=f"{emoji} {car['name']}",
                callback_data=f"car:{car['id']}"
            )
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅", callback_data=f"garage:{page-1}"))

    nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="ignore"))

    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡", callback_data=f"garage:{page+1}"))

    kb.append(nav)
    kb.append([InlineKeyboardButton("⬅ В меню", callback_data="menu")])

    return InlineKeyboardMarkup(inline_keyboard=kb)


def car_keyboard(car_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("💸 Продать", callback_data=f"sell:{car_id}")],
        [InlineKeyboardButton("⬅ В гараж", callback_data="garage:0")]
    ])

# =========================
# START
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    if not get_user(message.from_user.id):
        add_user(message.from_user.id)

    await message.answer(
        "🚗 **CarCase**\n\nВыбери действие:",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

# =========================
# МЕНЮ
# =========================

@dp.callback_query(F.data == "menu")
async def back_to_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "🏠 **Главное меню**",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

# =========================
# ГАРАЖ
# =========================

@dp.callback_query(F.data.startswith("garage:"))
async def garage(callback: CallbackQuery):
    await callback.answer()

    page = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    cars = get_user_garage(user_id)

    if not cars:
        await callback.message.answer("🚗 Твой гараж пуст")
        return

    total_pages = math.ceil(len(cars) / PER_PAGE)
    start = page * PER_PAGE
    end = start + PER_PAGE
    cars_page = cars[start:end]

    await callback.message.answer(
        f"🚗 **ТВОЙ ГАРАЖ**\n"
        f"Страница {page+1} из {total_pages}",
        reply_markup=garage_keyboard(cars_page, page, total_pages),
        parse_mode="Markdown"
    )

# =========================
# ПРОСМОТР МАШИНЫ
# =========================

@dp.callback_query(F.data.startswith("car:"))
async def view_car(callback: CallbackQuery):
    await callback.answer()

    car_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    cars = get_user_garage(user_id)
    car = next((c for c in cars if c["id"] == car_id), None)

    if not car:
        await callback.message.answer("❌ Машина не найдена")
        return

    emoji = RARITY_EMOJI.get(car["rarity"], "⚪")
    price = SELL_PRICES.get(car["rarity"], 0)

    await callback.message.answer(
        f"🚘 **{car['name']}**\n\n"
        f"Редкость: {emoji}\n"
        f"Цена продажи: 💰 {price}",
        reply_markup=car_keyboard(car_id),
        parse_mode="Markdown"
    )

# =========================
# ПРОДАЖА
# =========================

@dp.callback_query(F.data.startswith("sell:"))
async def sell_car(callback: CallbackQuery):
    await callback.answer()

    car_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    cars = get_user_garage(user_id)
    car = next((c for c in cars if c["id"] == car_id), None)

    if not car:
        await callback.message.answer("❌ Ошибка продажи")
        return

    price = SELL_PRICES.get(car["rarity"], 0)
    user = get_user(user_id)

    set_user_coins(user_id, user["coins"] + price)

    # ⚠️ тут позже добавим удаление машины из БД

    await callback.message.answer(
        f"✅ Машина продана\n💰 +{price} Coins",
        reply_markup=main_menu()
    )

# =========================
# FREE CASE (ЗАГЛУШКА)
# =========================

@dp.callback_query(F.data == "free_case")
async def free_case(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "🎁 Бесплатный кейс\n\n⏳ Скоро будет доступен",
        reply_markup=main_menu()
    )

# =========================
# RUN
# =========================

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())