import asyncio
import json
import os
import random
import time

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
    BotCommand,
)
from aiogram.filters import Command

# ================= НАСТРОЙКИ =================

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "users.json")
CARDS_DIR = os.path.join(BASE_DIR, "cards")

CASE_COOLDOWN = 5 * 60 * 60  # 5 часов

# ================= ДАННЫЕ =================

RARITY_CONFIG = {
    "Обычные": {"chance": 60, "new_rep": 20, "old_rep": 5, "emoji": "⚪"},
    "Редкие": {"chance": 30, "new_rep": 120, "old_rep": 25, "emoji": "🔵"},
    "Эпические": {"chance": 9, "new_rep": 600, "old_rep": 120, "emoji": "🟣"},
    "Легендарные": {"chance": 1, "new_rep": 3000, "old_rep": 600, "emoji": "💎"},
}

# папки на английском (как у тебя на сервере)
RARITY_DIR = {
    "Обычные": "common",
    "Редкие": "rare",
    "Эпические": "epic",
    "Легендарные": "legendary",
}

CARS_DATABASE = {
    "Toyota Camry": "Обычные",
    "Honda Civic": "Обычные",
    "Ford Focus": "Обычные",

    "Toyota Supra A80": "Редкие",
    "Nissan Skyline GTR": "Редкие",
    "BMW M3 E46": "Редкие",

    "BMW M5 F90": "Эпические",
    "Audi R8": "Эпические",
    "Lamborghini Huracan": "Эпические",

    "Bugatti Chiron": "Легендарные",
    "Koenigsegg Agera RS": "Легендарные",
}

RANKS = [
    (0, "Новичок"),
    (1500, "Коллекционер"),
    (5000, "Охотник"),
    (15000, "Эксперт"),
    (40000, "Эстет"),
    (100000, "Миллионер"),
]

# ================= БАЗА =================

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

users = load_db()

# ================= ВСПОМОГАТЕЛЬНОЕ =================

def get_rank(rep: int) -> str:
    for value, name in reversed(RANKS):
        if rep >= value:
            return name
    return RANKS[0][1]

def next_rank_info(rep: int):
    for value, name in RANKS:
        if rep < value:
            return value, name
    return None, "MAX"

def progress_bar(percent: int) -> str:
    filled = percent // 10
    return "█" * filled + "░" * (10 - filled)

def main_menu(uid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Открыть кейс", callback_data=f"open:{uid}")],
        [
            InlineKeyboardButton(text="🪪 Профиль", callback_data=f"profile:{uid}"),
            InlineKeyboardButton(text="🏎 Гараж", callback_data=f"garage:{uid}"),
        ],
    ])

# ================= ЛОГИКА КЕЙСА =================

async def open_case(user_id: int, name: str):
    now = time.time()
    user = users.setdefault(user_id, {"rep": 0, "garage": [], "last_case": 0})

    if now - user["last_case"] < CASE_COOLDOWN:
        rem = int(CASE_COOLDOWN - (now - user["last_case"]))
        return False, f"⏳ {name}, подожди {rem//3600}ч {(rem%3600)//60}м"

    rarity = random.choices(
        list(RARITY_CONFIG.keys()),
        [v["chance"] for v in RARITY_CONFIG.values()],
        k=1
    )[0]

    car = random.choice([c for c, r in CARS_DATABASE.items() if r == rarity])
    is_new = car not in user["garage"]

    rep_gain = RARITY_CONFIG[rarity]["new_rep" if is_new else "old_rep"]
    user["rep"] += rep_gain
    user["last_case"] = now
    if is_new:
        user["garage"].append(car)

    save_db(users)

    next_val, next_name = next_rank_info(user["rep"])
    percent = 100 if not next_val else min(100, int(user["rep"] / next_val * 100))

    text = (
        f"📦 *КЕЙС ОТКРЫТ!*\n"
        f"━━━━━━━━━━━━━━\n"
        f"{RARITY_CONFIG[rarity]['emoji']} *{car}*\n"
        f"💎 Редкость: `{rarity}`\n"
        f"🏆 REP: `+{rep_gain}` {'🔥 NEW' if is_new else ''}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎖 Ранг: `{get_rank(user['rep'])}`\n"
        f"`[{progress_bar(percent)}] {percent}%`"
    )

    # поиск картинки
    photo = None
    folder = RARITY_DIR[rarity]
    for ext in ("jpg", "png", "jpeg", "webp"):
        path = os.path.join(CARDS_DIR, folder, f"{car}.{ext}")
        if os.path.exists(path):
            photo = FSInputFile(path)
            break

    return True, text, photo

# ================= BOT =================

bot = Bot(TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        f"👋 *Привет, {message.from_user.first_name}!*\n\n"
        "🏎 Добро пожаловать в *CarCase*.\n"
        "📦 Открывай кейсы и собирай коллекцию.",
        parse_mode="Markdown",
        reply_markup=main_menu(message.from_user.id),
    )

@dp.callback_query(F.data.startswith("open:"))
async def cb_open(call: CallbackQuery):
    uid = int(call.data.split(":")[1])
    if call.from_user.id != uid:
        return await call.answer("❌ Не твое меню", show_alert=True)

    ok, *data = await open_case(uid, call.from_user.first_name)
    if not ok:
        return await call.answer(data[0], show_alert=True)

    text, photo = data
    if photo:
        await call.message.answer_photo(photo=photo, caption=text, parse_mode="Markdown")
    else:
        await call.message.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("profile:"))
async def cb_profile(call: CallbackQuery):
    uid = int(call.data.split(":")[1])
    u = users.get(uid)
    if not u:
        return await call.answer("Сначала открой кейс", show_alert=True)

    next_val, next_name = next_rank_info(u["rep"])
    percent = 100 if not next_val else min(100, int(u["rep"] / next_val * 100))

    await call.message.answer(
        f"🪪 *ПРОФИЛЬ*\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎖 Ранг: `{get_rank(u['rep'])}`\n"
        f"🏆 REP: `{u['rep']}`\n"
        f"🚗 Машин: `{len(u['garage'])}`\n"
        f"`[{progress_bar(percent)}] {percent}%`",
        parse_mode="Markdown",
    )

@dp.callback_query(F.data.startswith("garage:"))
async def cb_garage(call: CallbackQuery):
    uid = int(call.data.split(":")[1])
    if call.from_user.id != uid:
        return await call.answer("❌ Не твое меню", show_alert=True)

    user = users.get(uid)
    if not user or not user["garage"]:
        return await call.answer("🚗 Гараж пуст", show_alert=True)

    text = "🏎 *ТВОЙ ГАРАЖ*\n━━━━━━━━━━━━━━\n"
    for car in sorted(user["garage"], key=lambda x: CARS_DATABASE[x]):
        rarity = CARS_DATABASE[car]
        emoji = RARITY_CONFIG[rarity]["emoji"]
        text += f"{emoji} `{car}`\n"

    await call.message.answer(text, parse_mode="Markdown")

# ================= ЗАПУСК =================

async def main():
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
    ])
    print("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
