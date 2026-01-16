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
    update_last_case_time,
)

# =========================
# INIT
# =========================

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# =========================
# ЗАГРУЗКА КАРТ
# =========================

with open("cards.json", "r", encoding="utf-8") as f:
    CARDS = json.load(f)

COMMON_CARDS = [k for k, v in CARDS.items() if v["rarity"] == "Common"]

# =========================
# КОНФИГ
# =========================

CASE_PRICE_COMMON = 1000
FREE_CASE_COOLDOWN = timedelta(hours=5)

RARITY_UI = {
    "Common": {"emoji": "⚪", "name": "Обычная"},
}

# =========================
# UI
# =========================

def header():
    return "🚗 **CarCase**\n━━━━━━━━━━━━"

def footer():
    return "━━━━━━━━━━━━"

# =========================
# UTILS
# =========================

def get_free_case_status(user):
    if not user["last_case_time"]:
        return True, None

    last = datetime.fromisoformat(user["last_case_time"])
    now = datetime.utcnow()

    remaining = FREE_CASE_COOLDOWN - (now - last)
    if remaining.total_seconds() <= 0:
        return True, None

    return False, remaining

def format_timedelta(td: timedelta):
    hours, remainder = divmod(int(td.total_seconds()), 3600)
    minutes = remainder // 60
    return f"{hours}ч {minutes}м"

# =========================
# START
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
            "Напиши: **открыть кейс**\n\n"
            f"{footer()}"
        )
    else:
        text = (
            f"{header()}\n\n"
            "С возвращением в CarCase.\n\n"
            "Доступные команды:\n"
            "📦 **кейсы** — магазин кейсов\n"
            "🎁 **открыть кейс** — открыть кейс\n"
            "🚗 **гараж** — твой гараж\n"
            "💰 **баланс** — баланс Coins\n"
            "🎁 **бесплатный кейс** — раз в 5 часов\n\n"
            f"{footer()}"
        )

    await message.answer(text, parse_mode="Markdown")

# =========================
# МАГАЗИН
# =========================

@dp.message(F.text.lower() == "кейсы")
async def shop(message: Message):
    await message.answer(
        f"{header()}\n\n"
        "📦 **МАГАЗИН КЕЙСОВ**\n\n"
        f"📦 Обычный кейс — **{CASE_PRICE_COMMON} Coins**\n"
        "Внутри: ⚪ Обычные машины\n\n"
        "Напиши:\n"
        "**купить обычный**\n\n"
        f"{footer()}",
        parse_mode="Markdown"
    )

# =========================
# ПОКУПКА
# =========================

@dp.message(F.text.lower() == "купить обычный")
async def buy_common(message: Message):
    user = get_user(message.from_user.id)

    if user["coins"] < CASE_PRICE_COMMON:
        await message.answer(
            f"{header()}\n\n"
            "❌ Недостаточно Coins.\n\n"
            f"Нужно: {CASE_PRICE_COMMON}\n"
            f"У тебя: {user['coins']}\n\n"
            f"{footer()}",
            parse_mode="Markdown"
        )
        return

    set_user_coins(user["user_id"], user["coins"] - CASE_PRICE_COMMON)
    add_common_case(user["user_id"], 1)

    await message.answer(
        f"{header()}\n\n"
        "📦 Ты купил **Обычный кейс**.\n\n"
        "Напиши: **открыть кейс**\n\n"
        f"{footer()}",
        parse_mode="Markdown"
    )

# =========================
# ОТКРЫТИЕ КЕЙСА
# =========================

@dp.message(F.text.lower() == "открыть кейс")
async def open_case(message: Message):
    user = get_user(message.from_user.id)

    if user["cases_common"] <= 0:
        await message.answer(
            f"{header()}\n\n"
            "❌ У тебя нет кейсов.\n"
            "Зайди в магазин: **кейсы**\n\n"
            f"{footer()}",
            parse_mode="Markdown"
        )
        return

    remove_common_case(user["user_id"], 1)

    card_id = random.choice(COMMON_CARDS)
    card = CARDS[card_id]

    add_car_to_garage(user["user_id"], card_id, "Common")

    image = FSInputFile(card["image"])
    rar = RARITY_UI["Common"]

    await message.answer_photo(
        image,
        caption=(
            f"{header()}\n\n"
            "🎁 **КЕЙС ОТКРЫТ**\n\n"
            f"🚘 Выпала машина:\n**{card['name_ru']}**\n\n"
            f"Редкость: {rar['emoji']} **{rar['name']}**\n\n"
            f"{footer()}"
        ),
        parse_mode="Markdown"
    )

# =========================
# БЕСПЛАТНЫЙ КЕЙС
# =========================

@dp.message(F.text.lower() == "бесплатный кейс")
async def free_case(message: Message):
    user = get_user(message.from_user.id)

    available, remaining = get_free_case_status(user)

    if not available:
        await message.answer(
            "⏳ Бесплатный кейс недоступен\n"
            f"До следующего открытия: {format_timedelta(remaining)}"
        )
        return

    update_last_case_time(user["user_id"])

    card_id = random.choice(COMMON_CARDS)
    card = CARDS[card_id]

    add_car_to_garage(user["user_id"], card_id, "Common")

    image = FSInputFile(card["image"])

    await message.answer_photo(
        image,
        caption=(
            f"{header()}\n\n"
            "🎁 **БЕСПЛАТНЫЙ КЕЙС**\n\n"
            f"🚘 Выпала машина:\n**{card['name_ru']}**\n\n"
            f"Редкость: ⚪ **Обычная**\n\n"
            f"{footer()}"
        ),
        parse_mode="Markdown",
    )

# =========================
# ГАРАЖ
# =========================

@dp.message(F.text.lower() == "гараж")
async def garage(message: Message):
    user = get_user(message.from_user.id)
    cars = get_user_garage(user["user_id"])

    if not cars:
        await message.answer(
            f"{header()}\n\n"
            "🚗 Твой гараж пуст.\n"
            "Открой кейс.\n\n"
            f"{footer()}",
            parse_mode="Markdown"
        )
        return

    text = f"{header()}\n\n🏁 **ТВОЙ ГАРАЖ**\n"
    for c in cars:
        card = CARDS.get(c["name"])
        if not card:
            continue
        text += f"⚪ {card['name_ru']} (Обычная)\n"

    text += f"\n{footer()}"
    await message.answer(text, parse_mode="Markdown")

# =========================
# БАЛАНС
# =========================

@dp.message(F.text.lower() == "баланс")
async def balance(message: Message):
    user = get_user(message.from_user.id)
    await message.answer(
        f"{header()}\n\n"
        f"💰 Coins: **{user['coins']}**\n"
        f"📦 Обычных кейсов: **{user['cases_common']}**\n\n"
        f"{footer()}",
        parse_mode="Markdown"
    )

# =========================
# RUN
# =========================

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())