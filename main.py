import asyncio
import json
import os
import random
import time
import math

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

# ================= CONFIG =================

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN not found")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "users.json")
CARDS_DIR = os.path.join(BASE_DIR, "cards")

CASE_COOLDOWN = 6 * 60 * 60
PAGE_SIZE = 5

# ================= GAME DATA =================

RARITY_CONFIG = {
    "Обычные": {"chance": 55, "new_rep": 15, "old_rep": 3, "emoji": "⚪"},
    "Редкие": {"chance": 30, "new_rep": 90, "old_rep": 18, "emoji": "🔵"},
    "Эпические": {"chance": 12, "new_rep": 500, "old_rep": 100, "emoji": "🟣"},
    "Легендарные": {"chance": 3, "new_rep": 3000, "old_rep": 600, "emoji": "💎"},
}

RARITY_DIR = {
    "Обычные": "common",
    "Редкие": "rare",
    "Эпические": "epic",
    "Легендарные": "legendary",
}

CAR_IMAGE_MAP = {
    "Toyota Camry": "toyota_camry.png",
    "Honda Civic": "honda_civic.png",
    "Ford Focus": "ford_focus.png",
    "Volkswagen Golf": "vw_golf.png",
    "Hyundai Solaris": "hyundai_solaris.png",
    "Kia Rio": "kia_rio.png",
    "Lada Vesta": "lada_vesta.png",
    "Toyota Supra": "toyota_supra.png",
    "Nissan Skyline GTR": "nissan_skyline_gtr.png",
    "BMW M3 E46": "bmw_m3_e46.png",
    "Audi TT": "audi_tt.png",
    "Mitsubishi Lancer Evo": "mitsubishi_lancer_evo.png",
    "Subaru Impreza WRX": "subaru_Impreza_wrx.png",
    "BMW M5 F90": "bmw_m5_f90.png",
    "Audi R8": "auidi_r8.png",
    "Ferrari 458 Italia": "ferrari_458_italia.png",
    "Mercedes-Benz AMG GT": "mercedes_benz_amg_gt.png",
    "Lamborghini Huracan": "lamborghini_huracan.png",
    "Porsche 911 Turbo S": "porshe_911_turbo_s.jpg",
    "Bugatti Chiron": "bugatti_chiron.png",
    "Koenigsegg Agera RS": "koenigsegg_agera_rs.png",
    "Pagani Huayra": "pagani_huayra.png",
    "Ferrari LaFerrari": "ferrari_laferrari.png",
    "McLaren P1": "mclaren_p1.png",
}

CARS_DATABASE = {name: (
    "Обычные" if name in [
        "Toyota Camry","Honda Civic","Ford Focus","Volkswagen Golf",
        "Hyundai Solaris","Kia Rio","Lada Vesta"
    ] else
    "Редкие" if name in [
        "Toyota Supra","Nissan Skyline GTR","BMW M3 E46","Audi TT",
        "Mitsubishi Lancer Evo","Subaru Impreza WRX"
    ] else
    "Эпические" if name in [
        "BMW M5 F90","Audi R8","Ferrari 458 Italia",
        "Mercedes-Benz AMG GT","Lamborghini Huracan","Porsche 911 Turbo S"
    ] else
    "Легендарные"
) for name in CAR_IMAGE_MAP}

RANKS = [
    (0, "Новичок"),
    (2000, "Коллекционер"),
    (8000, "Охотник"),
    (25000, "Эксперт"),
    (70000, "Эстет"),
    (200000, "Легенда"),
]

CASE_TRIGGERS = [
    "кейс","case","машина","машинку","тачка","тачку","тачки",
    "открыть кейс","car","cars","авто"
]

# ================= DB =================

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

users = load_db()

# ================= UTILS =================

def get_rank(rep):
    for v, name in reversed(RANKS):
        if rep >= v:
            return name
    return RANKS[0][1]

def progress_bar(p):
    return "█" * (p // 10) + "░" * (10 - p // 10)

def main_menu(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Открыть кейс", callback_data=f"open:{uid}")],
        [
            InlineKeyboardButton(text="🪪 Профиль", callback_data=f"profile:{uid}"),
            InlineKeyboardButton(text="🏎 Гараж", callback_data=f"garage:{uid}:menu"),
        ],
    ])

# ================= CASE =================

async def open_case(uid, name):
    now = time.time()
    user = users.setdefault(str(uid), {"rep": 0, "garage": [], "last": 0})

    if now - user["last"] < CASE_COOLDOWN:
        r = int(CASE_COOLDOWN - (now - user["last"]))
        return False, f"⏳ {name}, подожди {r//3600}ч {(r%3600)//60}м"

    rarity = random.choices(list(RARITY_CONFIG), [v["chance"] for v in RARITY_CONFIG.values()])[0]
    pool = [c for c, r in CARS_DATABASE.items() if r == rarity]
    car = random.choice(pool)

    is_new = car not in user["garage"]
    rep = RARITY_CONFIG[rarity]["new_rep" if is_new else "old_rep"]

    user["rep"] += rep
    user["last"] = now
    if is_new:
        user["garage"].append(car)

    save_db()

    percent = min(100, int(user["rep"] / 2000 * 100))

    text = (
        f"{RARITY_CONFIG[rarity]['emoji']} *{car}*\n"
        f"Редкость: `{rarity}`\n"
        f"REP: `+{rep}` {'🔥' if is_new else ''}\n\n"
        f"Ранг: `{get_rank(user['rep'])}`\n"
        f"`[{progress_bar(percent)}] {percent}%`"
    )

    img = CAR_IMAGE_MAP.get(car)
    photo = None
    if img:
        path = os.path.join(CARDS_DIR, RARITY_DIR[rarity], img)
        if os.path.exists(path):
            photo = FSInputFile(path)

    return True, text, photo

# ================= BOT =================

bot = Bot(TOKEN)
dp = Dispatcher()

# -------- START & DEEPLINK --------

@dp.message(Command("start"))
async def start(m: Message):
    args = m.text.split(maxsplit=1)
    payload = args[1] if len(args) > 1 else None

    if payload == "case":
        return await start_case_private(m)
    if payload == "profile":
        return await show_profile(m)

    await m.answer("Добро пожаловать в *CarCase*", parse_mode="Markdown", reply_markup=main_menu(m.from_user.id))

# -------- GROUP COMMANDS --------

@dp.message(Command("case"))
async def cmd_case(m: Message):
    if m.chat.type != "private":
        botname = (await bot.get_me()).username
        return await m.reply(f"📦 Открой кейс:\nhttps://t.me/{botname}?start=case")
    await start_case_private(m)

@dp.message(Command("profile"))
async def cmd_profile(m: Message):
    if m.chat.type != "private":
        botname = (await bot.get_me()).username
        return await m.reply(f"🪪 Профиль:\nhttps://t.me/{botname}?start=profile")
    await show_profile(m)

# -------- GROUP TRIGGERS --------

@dp.message(F.chat.type.in_(["group", "supergroup"]))
async def group_triggers(m: Message):
    if not m.text:
        return
    txt = m.text.lower()
    if any(w in txt for w in CASE_TRIGGERS):
        botname = (await bot.get_me()).username
        await m.reply(f"📦 Открой кейс:\nhttps://t.me/{botname}?start=case")

# -------- PRIVATE --------

async def start_case_private(m: Message):
    ok, *d = await open_case(m.from_user.id, m.from_user.first_name)
    if not ok:
        return await m.answer(d[0])
    text, photo = d
    if photo:
        await m.answer_photo(photo=photo, caption=text, parse_mode="Markdown")
    else:
        await m.answer(text, parse_mode="Markdown")

async def show_profile(m: Message):
    u = users.get(str(m.from_user.id))
    if not u:
        return await m.answer("Сначала открой кейс")
    await m.answer(f"🪪 Профиль\nРанг: {get_rank(u['rep'])}\nREP: {u['rep']}\nМашин: {len(u['garage'])}")

# -------- CALLBACKS --------

@dp.callback_query(F.data.startswith("open:"))
async def open_cb(c: CallbackQuery):
    uid = int(c.data.split(":")[1])
    ok, *d = await open_case(uid, c.from_user.first_name)
    if not ok:
        return await c.answer(d[0], show_alert=True)
    text, photo = d
    if photo:
        await c.message.answer_photo(photo=photo, caption=text, parse_mode="Markdown")
    else:
        await c.message.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("profile:"))
async def profile_cb(c: CallbackQuery):
    uid = int(c.data.split(":")[1])
    u = users.get(str(uid))
    if not u:
        return await c.answer("Сначала открой кейс", show_alert=True)
    await c.message.answer(f"Ранг: {get_rank(u['rep'])}\nREP: {u['rep']}\nМашин: {len(u['garage'])}")

@dp.callback_query(F.data.startswith("garage:"))
async def garage_cb(c: CallbackQuery):
    _, uid, action, *rest = c.data.split(":")
    uid = int(uid)
    user = users.get(str(uid))
    if not user:
        return await c.answer("Гараж пуст", show_alert=True)

    if action == "menu":
        kb = [[InlineKeyboardButton(text=f"{RARITY_CONFIG[r]['emoji']} {r}", callback_data=f"garage:{uid}:list:{r}:1")] for r in RARITY_CONFIG]
        kb.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"back:{uid}")])
        await c.message.answer("Выбери категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    if action == "list":
        rarity = rest[0]
        page = int(rest[1])
        cars = [c for c in user["garage"] if CARS_DATABASE[c] == rarity]
        pages = max(1, math.ceil(len(cars) / PAGE_SIZE))
        page = max(1, min(page, pages))
        chunk = cars[(page-1)*PAGE_SIZE:page*PAGE_SIZE]

        kb = [[InlineKeyboardButton(text=c, callback_data=f"garage:{uid}:show:{c}")] for c in chunk]
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("◀", callback_data=f"garage:{uid}:list:{rarity}:{page-1}"))
        if page < pages:
            nav.append(InlineKeyboardButton("▶", callback_data=f"garage:{uid}:list:{rarity}:{page+1}"))
        if nav:
            kb.append(nav)
        kb.append([InlineKeyboardButton("⬅ Категории", callback_data=f"garage:{uid}:menu")])

        await c.message.answer(f"{rarity} — {page}/{pages}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    if action == "show":
        car = rest[0]
        rarity = CARS_DATABASE[car]
        img = CAR_IMAGE_MAP.get(car)
        if not img:
            return
        path = os.path.join(CARDS_DIR, RARITY_DIR[rarity], img)
        await c.message.answer_photo(FSInputFile(path), caption=f"{RARITY_CONFIG[rarity]['emoji']} *{car}*", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("back:"))
async def back(c: CallbackQuery):
    uid = int(c.data.split(":")[1])
    await c.message.answer("Главное меню", reply_markup=main_menu(uid))

# ================= RUN =================

async def main():
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="case", description="Открыть кейс"),
        BotCommand(command="profile", description="Профиль"),
    ])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
