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

RARITY_DIR = {
    "Обычные": "common",
    "Редкие": "rare",
    "Эпические": "epic",
    "Легендарные": "legendary",
}

# === ГЛАВНОЕ: ТОЧНОЕ СООТВЕТСТВИЕ ИМЯ -> ФАЙЛ ===

CAR_IMAGE_MAP = {
    # COMMON
    "Toyota Camry": "toyota_camry.png",
    "Honda Civic": "honda_civic.png",
    "Ford Focus": "ford_focus.png",
    "Volkswagen Golf": "vw_golf.png",
    "Hyundai Solaris": "hyundai_solaris.png",
    "Kia Rio": "kia_rio.png",
    "Lada Vesta": "lada_vesta.png",

    # RARE
    "Toyota Supra": "toyota_supra.png",
    "Nissan Skyline GTR": "nissan_skyline_gtr.png",
    "BMW M3 E46": "bmw_m3_e46.png",
    "Audi TT": "audi_tt.png",
    "Mitsubishi Lancer Evo": "mitsubishi_lancer_evo.png",
    "Subaru Impreza WRX": "subaru_Impreza_wrx.png",

    # EPIC
    "BMW M5 F90": "bmw_m5_f90.png",
    "Audi R8": "auidi_r8.png",
    "Ferrari 458 Italia": "ferrari_458_italia.png",
    "Mercedes-Benz AMG GT": "mercedes_benz_amg_gt.png",
    "Lamborghini Huracan": "lamborghini_huracan.png",
    "Porsche 911 Turbo S": "porshe_911_turbo_s.jpg",

    # LEGENDARY
    "Bugatti Chiron": "bugatti_chiron.png",
    "Koenigsegg Agera RS": "koenigsegg_agera_rs.png",
    "Pagani Huayra": "pagani_huayra.png",
    "Ferrari LaFerrari": "ferrari_laferrari.png",
    "McLaren P1": "mclaren_p1.png",
}

CARS_DATABASE = {
    # COMMON
    "Toyota Camry": "Обычные",
    "Honda Civic": "Обычные",
    "Ford Focus": "Обычные",
    "Volkswagen Golf": "Обычные",
    "Hyundai Solaris": "Обычные",
    "Kia Rio": "Обычные",
    "Lada Vesta": "Обычные",

    # RARE
    "Toyota Supra": "Редкие",
    "Nissan Skyline GTR": "Редкие",
    "BMW M3 E46": "Редкие",
    "Audi TT": "Редкие",
    "Mitsubishi Lancer Evo": "Редкие",
    "Subaru Impreza WRX": "Редкие",

    # EPIC
    "BMW M5 F90": "Эпические",
    "Audi R8": "Эпические",
    "Ferrari 458 Italia": "Эпические",
    "Mercedes-Benz AMG GT": "Эпические",
    "Lamborghini Huracan": "Эпические",
    "Porsche 911 Turbo S": "Эпические",

    # LEGENDARY
    "Bugatti Chiron": "Легендарные",
    "Koenigsegg Agera RS": "Легендарные",
    "Pagani Huayra": "Легендарные",
    "Ferrari LaFerrari": "Легендарные",
    "McLaren P1": "Легендарные",
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

def progress_bar(percent: int) -> str:
    return "█" * (percent // 10) + "░" * (10 - percent // 10)

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

    percent = min(100, int(user["rep"] / 1500 * 100))

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

    photo = None
    img_name = CAR_IMAGE_MAP.get(car)
    if img_name:
        img_path = os.path.join(CARDS_DIR, RARITY_DIR[rarity], img_name)
        if os.path.exists(img_path):
            photo = FSInputFile(img_path)

    return True, text, photo

# ================= BOT =================

bot = Bot(TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        f"👋 *Привет, {message.from_user.first_name}!*\n\n"
        "🏎 Добро пожаловать в *CarCase*.",
        parse_mode="Markdown",
        reply_markup=main_menu(message.from_user.id),
    )

@dp.callback_query(F.data.startswith("open:"))
async def cb_open(call: CallbackQuery):
    uid = int(call.data.split(":")[1])
    ok, *data = await open_case(uid, call.from_user.first_name)
    if not ok:
        return await call.answer(data[0], show_alert=True)

    text, photo = data
    if photo:
        await call.message.answer_photo(photo=photo, caption=text, parse_mode="Markdown")
    else:
        await call.message.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("garage:"))
async def cb_garage(call: CallbackQuery):
    uid = int(call.data.split(":")[1])
    user = users.get(uid)
    if not user or not user["garage"]:
        return await call.answer("🚗 Гараж пуст", show_alert=True)

    text = "🏎 *ТВОЙ ГАРАЖ*\n━━━━━━━━━━━━━━\n"
    for car in user["garage"]:
        text += f"• `{car}`\n"

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
