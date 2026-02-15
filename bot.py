import asyncio
import os
import json
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
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
    get_car_by_id,
)

# =========================
# INIT
# =========================

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# =========================
# DATA
# =========================

with open("cards.json", "r", encoding="utf-8") as f:
    CARDS = json.load(f)

COMMON_CARDS = [k for k, v in CARDS.items() if v["rarity"] == "Common"]

FREE_CASE_COOLDOWN = timedelta(hours=5)
GARAGE_PAGE_SIZE = 5

RARITY_EMOJI = {
    "Common": "⚪",
    "Rare": "🔵",
    "Epic": "🟣",
    "Legendary": "🟡",
}

# =========================
# UI HELPERS
# =========================

def header():
    return "🚗 <b>CarCase</b>\n━━━━━━━━━━━━"

def footer():
    return "━━━━━━━━━━━━"

def main_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Бесплатный кейс", callback_data="menu:free")],
            [InlineKeyboardButton(text="🚗 Гараж", callback_data="menu:garage:0")],
            [InlineKeyboardButton(text="💰 Баланс", callback_data="menu:balance")],
        ]
    )

# =========================
# UTILS
# =========================

def format_timedelta(td: timedelta):
    total = int(td.total_seconds())
    h = total // 3600
    m = (total % 3600) // 60
    return f"{h} ч {m} мин"

def free_case_available(user):
    if not user["last_free_case_time"]:
        return True, None
    last = datetime.fromisoformat(user["last_free_case_time"])
    now = datetime.utcnow()
    diff = now - last
    if diff >= FREE_CASE_COOLDOWN:
        return True, None
    return False, FREE_CASE_COOLDOWN - diff

# =========================
# START
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        add_user(message.from_user.id)

    await message.answer(
        f"{header()}\n\n"
        "Добро пожаловать.\n"
        "Используй меню ниже.\n\n"
        f"{footer()}",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )

# =========================
# BALANCE
# =========================

@dp.callback_query(F.data == "menu:balance")
async def balance(call: CallbackQuery):
    user = get_user(call.from_user.id)
    await call.message.edit_text(
        f"{header()}\n\n"
        f"💰 Coins: <b>{user['coins']}</b>\n"
        f"📦 Обычных кейсов: <b>{user['cases_common']}</b>\n\n"
        f"{footer()}",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await call.answer()

# =========================
# FREE CASE
# =========================

@dp.callback_query(F.data == "menu:free")
async def free_case(call: CallbackQuery):
    user = get_user(call.from_user.id)
    available, remaining = free_case_available(user)

    if not available:
        await call.message.edit_text(
            f"{header()}\n\n"
            "⏳ Бесплатный кейс недоступен\n\n"
            f"Осталось: {format_timedelta(remaining)}\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        await call.answer()
        return

    card_id = random.choice(COMMON_CARDS)
    card = CARDS[card_id]

    add_car_to_garage(user["user_id"], card_id, "Common")
    update_last_free_case_time(user["user_id"])

    image_path = card["image"]
    if not image_path.startswith("/") and not image_path.startswith("."):
        image_path = f"./common/{image_path.split('/')[-1]}"
    
    image = FSInputFile(image_path)

    await call.message.answer_photo(
        image,
        caption=(
            f"{header()}\n\n"
            "🎁 <b>БЕСПЛАТНЫЙ КЕЙС</b>\n\n"
            f"🚘 <b>{card['name_ru']}</b>\n"
            f"Редкость: ⚪ Обычная\n\n"
            f"{footer()}"
        ),
        parse_mode="HTML",
    )
    await call.answer()

# =========================
# GARAGE (PAGINATION)
# =========================

@dp.callback_query(F.data.startswith("menu:garage"))
async def garage(call: CallbackQuery):
    page = int(call.data.split(":")[2])
    user = get_user(call.from_user.id)
    cars = get_user_garage(user["user_id"])

    if not cars:
        await call.message.edit_text(
            f"{header()}\n\n🚗 Гараж пуст\n\n{footer()}",
            reply_markup=main_menu_kb(),
            parse_mode="HTML",
        )
        await call.answer()
        return

    start = page * GARAGE_PAGE_SIZE
    end = start + GARAGE_PAGE_SIZE
    chunk = cars[start:end]

    kb = []
    for car in chunk:
        card = CARDS[car["name"]]
        emoji = RARITY_EMOJI.get(car["rarity"], "❓")
        kb.append([
            InlineKeyboardButton(
                text=f"{emoji} {card['name_ru']}",
                callback_data=f"car:view:{car['id']}"
            )
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"menu:garage:{page-1}"))
    if end < len(cars):
        nav.append(InlineKeyboardButton("➡️", callback_data=f"menu:garage:{page+1}"))

    if nav:
        kb.append(nav)

    kb.append([InlineKeyboardButton("🔙 Меню", callback_data="menu:balance")])

    await call.message.edit_text(
        f"{header()}\n\n🚗 <b>Твой гараж</b>\n\n{footer()}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="HTML",
    )
    await call.answer()


# =========================
# CAR VIEW
# =========================

@dp.callback_query(F.data.startswith("car:view"))
async def car_view(call: CallbackQuery):
    car_id = int(call.data.split(":")[2])
    car = get_car_by_id(car_id)

    if not car or car["user_id"] != call.from_user.id:
        await call.answer("🚗 Машина не найдена", show_alert=True)
        return

    card = CARDS[car["name"]]
    emoji = RARITY_EMOJI.get(car["rarity"], "❓")

    image_path = card["image"]
    if not image_path.startswith("/") and not image_path.startswith("."):
        image_path = f"./common/{image_path.split('/')[-1]}"
    
    image = FSInputFile(image_path)

    await call.message.answer_photo(
        image,
        caption=(
            f"{header()}\n\n"
            f"🚘 <b>{card['name_ru']}</b>\n"
            f"Редкость: {emoji} {car['rarity']}\n\n"
            f"{footer()}"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton("🔙 Назад", callback_data="menu:garage:0")]]
        )
    )
    await call.answer()

# =========================
# GROUP COMMANDS (SAFE)
# =========================

@dp.message(F.chat.type != "private", Command("garage"))
async def garage_group(message: Message):
    await message.answer("🚗 Гараж доступен в личных сообщениях с ботом")


# =========================
# GROUP TEXT TRIGGERS
# =========================

@dp.message(F.chat.type != "private", F.text.lower().regexp(r"(кейс|case|открыть|open)"))
async def group_text_trigger(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        add_user(message.from_user.id)
        user = get_user(message.from_user.id)

    available, remaining = free_case_available(user)

    if not available:
        await message.answer(
            f"⏳ {message.from_user.first_name}, бесплатный кейс недоступен\n\n"
            f"Осталось: {format_timedelta(remaining)}"
        )
        return

    card_id = random.choice(COMMON_CARDS)
    card = CARDS[card_id]

    add_car_to_garage(user["user_id"], card_id, "Common")
    update_last_free_case_time(user["user_id"])

    image_path = card["image"]
    if not image_path.startswith("/") and not image_path.startswith("."):
        image_path = f"./common/{image_path.split('/')[-1]}"
    
    image = FSInputFile(image_path)

    await message.answer_photo(
        image,
        caption=(
            f"{header()}\n\n"
            f"🎁 <b>КЕЙС {message.from_user.first_name}</b>\n\n"
            f"🚘 <b>{card['name_ru']}</b>\n"
            f"Редкость: ⚪ Обычная\n\n"
            f"{footer()}"
        ),
        parse_mode="HTML",
    )

# =========================
# RUN
# =========================

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())