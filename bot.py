import asyncio
import os
import random
import json
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from dotenv import load_dotenv

from database import (
    init_db,
    add_user,
    get_user,
    set_user_coins,
    add_common_case,
    remove_common_case,
    add_car_to_garage,
    get_user_garage,
    update_last_free_case_time,
)

# =========================
# INIT
# =========================

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# =========================
# LOAD CARDS
# =========================

with open("cards.json", "r", encoding="utf-8") as f:
    CARDS = json.load(f)

COMMON_CARDS = [k for k, v in CARDS.items() if v["rarity"] == "Common"]

# =========================
# CONFIG
# =========================

CASE_PRICE_COMMON = 1000
FREE_CASE_COOLDOWN = timedelta(hours=5)

RARITY_UI = {
    "Common": {"emoji": "⚪", "name": "Обычная"},
}

# =========================
# UI HELPERS
# =========================

def header():
    return "🚗 **CarCase**\n━━━━━━━━━━━━"

def footer():
    return "━━━━━━━━━━━━"

def main_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Бесплатный кейс", callback_data="free_case")],
            [InlineKeyboardButton(text="📦 Кейсы", callback_data="shop")],
            [InlineKeyboardButton(text="🚗 Гараж", callback_data="garage")],
            [InlineKeyboardButton(text="💰 Баланс", callback_data="balance")],
            [InlineKeyboardButton(text="ℹ️ Help", callback_data="help")],
        ]
    )

# =========================
# UTILS
# =========================

def get_free_case_status(user):
    last_time = user["last_free_case_time"]
    if not last_time:
        return True, None

    last_dt = datetime.fromisoformat(last_time)
    now = datetime.utcnow()
    diff = now - last_dt

    if diff >= FREE_CASE_COOLDOWN:
        return True, None

    remaining = FREE_CASE_COOLDOWN - diff
    return False, remaining

def format_timedelta(td: timedelta):
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours} ч {minutes} мин"

# =========================
# /start
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    user = get_user(message.from_user.id)

    if not user:
        add_user(message.from_user.id)
        text = (
            f"{header()}\n\n"
            "Добро пожаловать в мир коллекционных автомобилей.\n\n"
            "🎁 **Тебе выдан 1 Обычный кейс.**\n"
            "Используй кнопки ниже.\n\n"
            f"{footer()}"
        )
    else:
        text = (
            f"{header()}\n\n"
            "С возвращением в **CarCase**.\n\n"
            "Выбери действие:\n\n"
            f"{footer()}"
        )

    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="Markdown")

# =========================
# FREE CASE (CALLBACK)
# =========================

@dp.callback_query(F.data == "free_case")
async def free_case_cb(call):
    user = get_user(call.from_user.id)
    available, remaining = get_free_case_status(user)

    if not available:
        await call.message.answer(
            f"{header()}\n\n"
            "⏳ **Бесплатный кейс недоступен**\n\n"
            f"До следующего открытия:\n🕒 {format_timedelta(remaining)}\n\n"
            f"{footer()}",
            parse_mode="Markdown",
        )
        await call.answer()
        return

    # OPEN FREE CASE
    card_id = random.choice(COMMON_CARDS)
    card = CARDS[card_id]

    add_car_to_garage(user["user_id"], card_id, "Common")
    update_last_free_case_time(user["user_id"])

    image = FSInputFile(card["image"])
    rar = RARITY_UI["Common"]

    await call.message.answer_photo(
        image,
        caption=(
            f"{header()}\n\n"
            "🎁 **БЕСПЛАТНЫЙ КЕЙС ОТКРЫТ**\n\n"
            f"🚘 Выпала машина:\n**{card['name_ru']}**\n\n"
            f"Редкость: {rar['emoji']} **{rar['name']}**\n\n"
            f"{footer()}"
        ),
        parse_mode="Markdown",
    )
    await call.answer()

# =========================
# FREE CASE (GROUP / TEXT)
# =========================

@dp.message(
    F.text.lower().in_(["/freecase", "freecase", "free кейс", "бесплатный кейс"])
)
async def free_case_text(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        add_user(message.from_user.id)
        user = get_user(message.from_user.id)

    available, remaining = get_free_case_status(user)

    if not available:
        await message.answer(
            "⏳ Бесплатный кейс недоступен\n"
            f"До следующего открытия: {format_timedelta(remaining)}"
        )
        return

    card_id = random.choice(COMMON_CARDS)
    card = CARDS[card_id]

    add_car_to_garage(user["user_id"], card_id, "Common")
    update_last_free_case_time(user["user_id"])

    await message.answer(
        "🎁 **Бесплатный кейс открыт!**\n\n"
        f"🚘 Выпала машина:\n**{card['name_ru']}**\n"
        f"Редкость: ⚪ Обычная",
        parse_mode="Markdown",
    )

# =========================
# SHOP (TEXT)
# =========================

@dp.message(F.text.lower().in_(["кейсы", "/shop"]))
async def shop(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        add_user(message.from_user.id)
        user = get_user(message.from_user.id)

    await message.answer(
        f"{header()}\n\n"
        "📦 **МАГАЗИН КЕЙСОВ**\n\n"
        f"📦 Обычный кейс — **{CASE_PRICE_COMMON} Coins**\n"
        "Внутри: ⚪ Обычные машины\n\n"
        "Команда:\n**купить обычный**\n\n"
        f"{footer()}",
        parse_mode="Markdown",
    )

# =========================
# BUY COMMON
# =========================

@dp.message(F.text.lower() == "купить обычный")
async def buy_common(message: Message):
    user = get_user(message.from_user.id)

    if user["coins"] < CASE_PRICE_COMMON:
        await message.answer(
            f"❌ Недостаточно Coins\n"
            f"Нужно: {CASE_PRICE_COMMON}\n"
            f"У тебя: {user['coins']}"
        )
        return

    set_user_coins(user["user_id"], user["coins"] - CASE_PRICE_COMMON)
    add_common_case(user["user_id"], 1)

    await message.answer("📦 Ты купил **Обычный кейс**", parse_mode="Markdown")

# =========================
# OPEN COMMON CASE
# =========================

@dp.message(F.text.lower().in_(["открыть кейс", "/open"]))
async def open_case(message: Message):
    user = get_user(message.from_user.id)

    if user["cases_common"] <= 0:
        await message.answer("❌ У тебя нет кейсов")
        return

    remove_common_case(user["user_id"], 1)

    card_id = random.choice(COMMON_CARDS)
    card = CARDS[card_id]

    add_car_to_garage(user["user_id"], card_id, "Common")

    image = FSInputFile(card["image"])

    await message.answer_photo(
        image,
        caption=(
            f"{header()}\n\n"
            "🎁 **КЕЙС ОТКРЫТ**\n\n"
            f"🚘 Выпала машина:\n**{card['name_ru']}**\n\n"
            "Редкость: ⚪ **Обычная**\n\n"
            f"{footer()}"
        ),
        parse_mode="Markdown",
    )

# =========================
# GARAGE
# =========================

@dp.message(F.text.lower().in_(["гараж", "/garage"]))
async def garage(message: Message):
    user = get_user(message.from_user.id)
    cars = get_user_garage(user["user_id"])

    if not cars:
        await message.answer("🚗 Твой гараж пуст")
        return

    text = "🚗 **ТВОЙ ГАРАЖ**\n\n"
    for c in cars:
        card = CARDS.get(c["name"])
        if card:
            text += f"⚪ {card['name_ru']}\n"

    await message.answer(text, parse_mode="Markdown")

# =========================
# BALANCE
# =========================

@dp.message(F.text.lower().in_(["баланс", "/balance"]))
async def balance(message: Message):
    user = get_user(message.from_user.id)
    await message.answer(
        f"💰 Coins: **{user['coins']}**\n"
        f"📦 Обычных кейсов: **{user['cases_common']}**",
        parse_mode="Markdown",
    )

# =========================
# HELP
# =========================

@dp.callback_query(F.data == "help")
async def help_cb(call):
    await call.message.answer(
        f"{header()}\n\n"
        "ℹ️ **Помощь**\n\n"
        "🎁 Бесплатный кейс — раз в 5 часов\n"
        "📦 Кейсы — покупка и открытие\n"
        "🚗 Гараж — твои машины\n"
        "💰 Баланс — Coins\n\n"
        "В группе можно писать:\n"
        "/freecase\n"
        "/open\n"
        "/garage\n"
        "/balance\n\n"
        f"{footer()}",
        parse_mode="Markdown",
    )
    await call.answer()

# =========================
# RUN
# =========================

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
