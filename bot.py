import asyncio
import os
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

from database import (
    init_db,
    add_user,
    get_user,
    update_user_coins,
    add_car_to_garage,
    get_user_garage,
    update_last_case_time,
)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# =========================
# Конфигурация кейса
# =========================

CASE_COOLDOWN = timedelta(hours=5)

RARITY_EMOJI = {
    "Common": "⚪",
    "Rare": "🔵",
    "Epic": "🟣",
    "Legendary": "💎",
}

# Пример пула машин (оставь свой, если уже есть)
CARS = [
    {"name": "Toyota Camry", "rarity": "Common"},
    {"name": "Honda Civic", "rarity": "Common"},
    {"name": "Ford Focus", "rarity": "Common"},
    {"name": "Volkswagen Golf", "rarity": "Common"},
    {"name": "Hyundai Solaris", "rarity": "Common"},
    {"name": "Kia Rio", "rarity": "Common"},
    {"name": "Lada Vesta", "rarity": "Common"},

    {"name": "Nissan Skyline GT-R", "rarity": "Rare"},
    {"name": "Subaru Impreza", "rarity": "Rare"},
    {"name": "BMW M3 E46", "rarity": "Rare"},
    {"name": "Toyota Supra", "rarity": "Rare"},
    {"name": "Mitsubishi Lancer Evo", "rarity": "Rare"},
    {"name": "Audi TT", "rarity": "Rare"},
]

RARITY_CHANCES = [
    ("Legendary", 1),
    ("Epic", 8),
    ("Rare", 21),
    ("Common", 70),
]

# =========================
# Утилиты
# =========================

def pick_rarity():
    roll = random.randint(1, 100)
    current = 0
    for rarity, chance in RARITY_CHANCES:
        current += chance
        if roll <= current:
            return rarity
    return "Common"

def get_random_car():
    rarity = pick_rarity()
    pool = [c for c in CARS if c["rarity"] == rarity]
    if not pool:
        pool = [c for c in CARS if c["rarity"] == "Common"]
        rarity = "Common"
    car = random.choice(pool)
    return car["name"], rarity

def header():
    return "🚗 **CarCase**\n━━━━━━━━━━━━"

def footer():
    return "━━━━━━━━━━━━"

def rarity_line(rarity):
    return f"{RARITY_EMOJI.get(rarity, '')} **{rarity}**"

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
            "Открывай кейсы.\n"
            "Собирай редкие машины.\n"
            "Продавай и зарабатывай.\n\n"
            "🎁 **Тебе выдан стартовый доступ.**\n"
            "Напиши: **открыть кейс**\n\n"
            f"{footer()}"
        )
    else:
        text = (
            f"{header()}\n\n"
            "С возвращением в мир CarCase.\n\n"
            "Напиши: **открыть кейс** или **мой гараж**\n\n"
            f"{footer()}"
        )

    await message.answer(text, parse_mode="Markdown")

# =========================
# Открытие кейса
# =========================

@dp.message(F.text.lower().in_(["открыть кейс", "кейс", "/open"]))
async def open_case(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(
            f"{header()}\n\n"
            "Ты ещё не зарегистрирован.\n"
            "Напиши **/start**, чтобы начать игру.\n\n"
            f"{footer()}",
            parse_mode="Markdown",
        )
        return

    last_time = user["last_case_time"]
    if last_time:
        last_time = datetime.fromisoformat(last_time)
        if datetime.utcnow() - last_time < CASE_COOLDOWN:
            remaining = CASE_COOLDOWN - (datetime.utcnow() - last_time)
            minutes = int(remaining.total_seconds() // 60)
            await message.answer(
                f"{header()}\n\n"
                "⏳ **Кейс ещё на перезарядке.**\n\n"
                f"Попробуй снова через **{minutes} мин.**\n\n"
                f"{footer()}",
                parse_mode="Markdown",
            )
            return

    car_name, rarity = get_random_car()
    add_car_to_garage(message.from_user.id, car_name, rarity)
    update_last_case_time(message.from_user.id)

    await message.answer(
        f"{header()}\n\n"
        "🎁 **КЕЙС ОТКРЫТ**\n\n"
        "🚘 **Выпала машина:**\n"
        f"**{car_name}**\n\n"
        f"Редкость: {RARITY_EMOJI.get(rarity)} **{rarity}**\n\n"
        f"{footer()}",
        parse_mode="Markdown",
    )

# =========================
# Гараж
# =========================

@dp.message(F.text.lower().in_(["мой гараж", "гараж", "/garage"]))
async def garage(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(
            f"{header()}\n\n"
            "Ты ещё не зарегистрирован.\n"
            "Напиши **/start**, чтобы начать игру.\n\n"
            f"{footer()}",
            parse_mode="Markdown",
        )
        return

    cars = get_user_garage(message.from_user.id)
    if not cars:
        await message.answer(
            f"{header()}\n\n"
            "Твой гараж пуст.\n"
            "Открой кейс, чтобы получить первую машину.\n\n"
            f"{footer()}",
            parse_mode="Markdown",
        )
        return

    grouped = {}
    for car in cars:
        grouped.setdefault(car["rarity"], []).append(car["name"])

    lines = [f"{header()}\n", "🏁 **ТВОЙ ГАРАЖ**\n"]
    for rarity in ["Legendary", "Epic", "Rare", "Common"]:
        if rarity in grouped:
            lines.append(f"\n{RARITY_EMOJI.get(rarity)} **{rarity}**")
            for name in grouped[rarity]:
                lines.append(f"• {name}")

    lines.append(f"\n{footer()}")

    await message.answer("\n".join(lines), parse_mode="Markdown")

# =========================
# Баланс
# =========================

@dp.message(F.text.lower().in_(["баланс", "/balance"]))
async def balance(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(
            f"{header()}\n\n"
            "Ты ещё не зарегистрирован.\n"
            "Напиши **/start**, чтобы начать игру.\n\n"
            f"{footer()}",
            parse_mode="Markdown",
        )
        return

    await message.answer(
        f"{header()}\n\n"
        "💰 **ТВОЙ БАЛАНС**\n\n"
        f"Coins: **{user['coins']}**\n\n"
        f"{footer()}",
        parse_mode="Markdown",
    )

# =========================
# Запуск
# =========================

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
