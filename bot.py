import asyncio
import math
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command
from dotenv import load_dotenv

from database import (
    init_db,
    add_user,
    get_user,
    get_user_garage,
    add_car_to_garage,
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
# КЛАВИАТУРЫ
# =========================

def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Гараж", callback_data="menu:garage")],
        [InlineKeyboardButton(text="🎁 Бесплатный кейс", callback_data="menu:free")]
    ])


def garage_kb(cars, page: int, total_pages: int):
    keyboard = []

    for car in cars:
        emoji = RARITY_EMOJI.get(car["rarity"], "⚪")
        keyboard.append([
            InlineKeyboardButton(
                text=f"{emoji} {car['name']}",
                callback_data=f"garage:car:{car['id']}"
            )
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅", callback_data=f"garage:page:{page-1}"))

    nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))

    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡", callback_data=f"garage:page:{page+1}"))

    keyboard.append(nav)
    keyboard.append([
        InlineKeyboardButton("⬅ Назад", callback_data="menu:main")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def car_view_kb(car_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("💸 Продать", callback_data=f"garage:sell:{car_id}")],
        [InlineKeyboardButton("⬅ В гараж", callback_data="menu:garage")]
    ])

# =========================
# /start
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        add_user(message.from_user.id)

    await message.answer(
        "🚗 **CarCase**\n\nВыбери действие:",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown"
    )

# =========================
# ГЛАВНОЕ МЕНЮ
# =========================

@dp.callback_query(F.data == "menu:main")
async def back_to_main(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🚗 **CarCase**\n\nВыбери действие:",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown"
    )

# =========================
# ГАРАЖ (СПИСОК + ПАГИНАЦИЯ)
# =========================

@dp.callback_query(F.data.startswith("menu:garage"))
@dp.callback_query(F.data.startswith("garage:page"))
async def open_garage(callback: CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id
    page = 0

    if callback.data.startswith("garage:page"):
        page = int(callback.data.split(":")[2])

    cars_all = get_user_garage(user_id)

    if not cars_all:
        await callback.message.edit_text(
            "🚗 Твой гараж пуст",
            reply_markup=main_menu_kb()
        )
        return

    total_pages = math.ceil(len(cars_all) / PER_PAGE)
    start = page * PER_PAGE
    end = start + PER_PAGE
    cars_page = cars_all[start:end]

    await callback.message.edit_text(
        f"🚗 **ТВОЙ ГАРАЖ**\n"
        f"Страница {page+1} из {total_pages}\n\n"
        f"Выбери машину:",
        reply_markup=garage_kb(cars_page, page, total_pages),
        parse_mode="Markdown"
    )

# =========================
# ПРОСМОТР МАШИНЫ
# =========================

@dp.callback_query(F.data.startswith("garage:car"))
async def view_car(callback: CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id
    car_id = int(callback.data.split(":")[2])

    cars = get_user_garage(user_id)
    car = next((c for c in cars if c["id"] == car_id), None)

    if not car:
        await callback.answer("Машина не найдена", show_alert=True)
        return

    emoji = RARITY_EMOJI.get(car["rarity"], "⚪")
    price = SELL_PRICES.get(car["rarity"], 0)

    await callback.message.edit_text(
        f"🚘 **{car['name']}**\n\n"
        f"Редкость: {emoji}\n"
        f"Цена продажи: 💰 {price} Coins",
        reply_markup=car_view_kb(car_id),
        parse_mode="Markdown"
    )

# =========================
# ПРОДАЖА МАШИНЫ
# =========================

@dp.callback_query(F.data.startswith("garage:sell"))
async def sell_car(callback: CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id
    car_id = int(callback.data.split(":")[2])

    cars = get_user_garage(user_id)
    car = next((c for c in cars if c["id"] == car_id), None)

    if not car:
        await callback.answer("Ошибка", show_alert=True)
        return

    price = SELL_PRICES.get(car["rarity"], 0)
    user = get_user(user_id)
    set_user_coins(user_id, user["coins"] + price)

    # ⚠️ ВАЖНО
    # Тут должна быть функция удаления машины из БД
    # delete_car_from_garage(user_id, car_id)

    await callback.message.edit_text(
        f"✅ Машина продана\n💰 +{price} Coins",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("⬅ В гараж", callback_data="menu:garage")]
        ])
    )

# =========================
# FREE CASE (ЗАГЛУШКА)
# =========================

@dp.callback_query(F.data == "menu:free")
async def free_case(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🎁 Бесплатный кейс\n\n"
        "⏳ Механика будет добавлена следующим шагом",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("⬅ В меню", callback_data="menu:main")]
        ])
    )

# =========================
# RUN
# =========================

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())