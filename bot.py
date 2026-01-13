import asyncio
import os
import random
import json
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from dotenv import load_dotenv

from database import (
    init_db,
    add_user,
    get_user,
    set_user_coins,
    update_user_coins,
    set_daily,
    add_common_case,
    remove_common_case,
    add_car_to_garage,
    get_user_garage
)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# =========================
# Загрузка карт
# =========================

with open("cards.json", "r", encoding="utf-8") as f:
    CARDS = json.load(f)

COMMON_CARDS = [k for k, v in CARDS.items() if v["rarity"] == "Common"]

# =========================
# Конфигурация
# =========================

CASE_PRICE_COMMON = 1000

RARITY_UI = {
    "Common": {"emoji": "⚪", "name": "Обычная"},
}

DAILY_REWARDS = [300, 400, 500, 700, 1000, 1500, 2500]

# =========================
# UI
# =========================

def header():
    return "🚗 **CarCase**\n━━━━━━━━━━━━"

def footer():
    return "━━━━━━━━━━━━"

HELP_TEXT = (
    "🚗 **CarCase — помощь**\n"
    "━━━━━━━━━━━━\n\n"
    "📦 `кейсы` — магазин кейсов\n"
    "📦 `купить обычный` — купить кейс\n"
    "🎁 `открыть кейс` — открыть кейс\n\n"
    "🚘 `гараж` — твои машины\n"
    "💰 `баланс` — твои Coins\n"
    "🎁 `/daily` — ежедневная награда\n\n"
    "Открывай кейсы, собирай машины и зарабатывай Coins.\n"
    "━━━━━━━━━━━━"
)

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
            "Напиши: **открыть кейс**\n\n"
            f"{footer()}"
        )
    else:
        text = (
            f"{header()}\n\n"
            "С возвращением в CarCase.\n\n"
            "Напиши: **кейсы** или **открыть кейс**\n\n"
            f"{footer()}"
        )

    await message.answer(text, parse_mode="Markdown")

# =========================
# Help
# =========================

@dp.message(F.text.lower().in_(["/help", "помощь"]))
async def help_cmd(message: Message):
    await message.answer(HELP_TEXT, parse_mode="Markdown")

# =========================
# Daily
# =========================

@dp.message(Command("daily"))
async def daily(message: Message):
    user = get_user(message.from_user.id)
    now = datetime.utcnow()

    if user["last_daily"]:
        last = datetime.fromisoformat(user["last_daily"])
        if now - last < timedelta(hours=24):
            left = timedelta(hours=24) - (now - last)
            hours, remainder = divmod(int(left.total_seconds()), 3600)
            minutes = remainder // 60
            await message.answer(f"⏳ Ты уже забрал награду\nСледующая через {hours}ч {minutes}м")
            return

        if now - last > timedelta(hours=48):
            streak = 0
        else:
            streak = user["daily_streak"]
    else:
        streak = 0

    reward = DAILY_REWARDS[streak % len(DAILY_REWARDS)]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Забрать", callback_data=f"daily:{message.from_user.id}")]
        ]
    )

    await message.answer(
        f"🎁 **Ежедневная награда**\n\n"
        f"📅 День: **{streak + 1}**\n"
        f"💰 Награда: **{reward} Coins**",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("daily:"))
async def daily_claim(call: CallbackQuery):
    _, uid = call.data.split(":")
    if int(uid) != call.from_user.id:
        await call.answer("Это не твоя награда", show_alert=True)
        return

    user = get_user(call.from_user.id)
    now = datetime.utcnow()

    streak = user["daily_streak"] + 1
    reward = DAILY_REWARDS[(streak - 1) % len(DAILY_REWARDS)]

    update_user_coins(user["user_id"], reward)
    set_daily(user["user_id"], streak, now.isoformat())

    await call.message.edit_text(f"✅ {call.from_user.first_name} забрал **{reward} Coins**", parse_mode="Markdown")

# =========================
# Магазин
# =========================

@dp.message(F.text.lower().in_(["кейсы", "/shop"]))
async def shop(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Напиши /start")
        return

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
# Покупка
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
# Открытие кейса
# =========================

@dp.message(F.text.lower().in_(["открыть кейс", "/open"]))
async def open_case(message: Message):
    user = get_user(message.from_user.id)

    if user["cases_common"] <= 0:
        await message.answer(
            f"{header()}\n\n"
            "У тебя нет кейсов.\n"
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
# Гараж
# =========================

@dp.message(F.text.lower().in_(["мой гараж", "гараж", "/garage"]))
async def garage(message: Message):
    user = get_user(message.from_user.id)
    cars = get_user_garage(user["user_id"])

    if not cars:
        await message.answer(
            f"{header()}\n\n"
            "Твой гараж пуст.\n"
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
# Баланс
# =========================

@dp.message(F.text.lower().in_(["баланс", "/balance"]))
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
# Запуск
# =========================

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
