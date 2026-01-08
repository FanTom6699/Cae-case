import asyncio
import time
import json
import random
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

# --- КОНФИГУРАЦИЯ ---
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")

if not API_TOKEN:
    print("ОШИБКА: Токен не найден!")
    exit()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

DB_FILE = "database.json"
PHOTO_URL = "https://1s4oyld5dc.ucarecd.net/93fe7ec6-08ee-4c26-88c0-a720bf6997f5/"

# --- БАЗА ДАННЫХ ---
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
            except:
                return {}
    return {}

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

users = load_db()

# --- КОНТЕНТ ---
RARITY_CONFIG = {
    "Common": {"chance": 60, "new_rep": 20, "old_rep": 4, "emoji": "⚪"},
    "Rare": {"chance": 30, "new_rep": 100, "old_rep": 20, "emoji": "🔵"},
    "Epic": {"chance": 9, "new_rep": 500, "old_rep": 100, "emoji": "🟣"},
    "Legendary": {"chance": 1, "new_rep": 2500, "old_rep": 500, "emoji": "💎"}
}

CARS_DATABASE = {
    "Toyota Camry": "Common", "Honda Civic": "Common", "Ford Focus": "Common",
    "Volkswagen Golf": "Common", "Hyundai Solaris": "Common", "Kia Rio": "Common", "Lada Vesta": "Common",
    "Nissan Skyline GTR": "Rare", "Subaru Impreza WRX": "Rare", "BMW M3 E46": "Rare",
    "Toyota Supra A80": "Rare", "Mitsubishi Lancer Evo": "Rare", "Audi TT": "Rare",
    "BMW M5 F90": "Epic", "Mercedes-Benz AMG GT": "Epic", "Audi R8": "Epic",
    "Porsche 911 Turbo S": "Epic", "Ferrari 458 Italia": "Epic", "Lamborghini Huracan": "Epic",
    "Bugatti Chiron": "Legendary", "Koenigsegg Agera RS": "Legendary", "Pagani Huayra": "Legendary",
    "McLaren P1": "Legendary", "Ferrari LaFerrari": "Legendary"
}

RANKS = [
    (0, "Любитель"), (1500, "Поисковик"), (5000, "Охотник за редкостями"),
    (15000, "Эксперт марки"), (40000, "Эстет"), (100000, "Миллиардер"), (250000, "Икона стиля")
]

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_rank(rep):
    for threshold, name in reversed(RANKS):
        if rep >= threshold: return name
    return "Новичок"

def get_next_rank_info(rep):
    for i in range(len(RANKS)-1):
        if rep < RANKS[i+1][0]:
            next_rank_name = RANKS[i+1][1]
            next_rank_rep = RANKS[i+1][0]
            current_rank_rep = RANKS[i][0]
            progress = int((rep - current_rank_rep) / (next_rank_rep - current_rank_rep) * 100)
            return next_rank_name, progress
    return "MAX", 100

def get_main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📦 Открыть кейс", callback_data="open_case_btn"))
    builder.row(
        types.InlineKeyboardButton(text="🪪 Профиль", callback_data="profile_btn"),
        types.InlineKeyboardButton(text="🏎 Гараж", callback_data="garage_btn")
    )
    return builder.as_markup()

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    welcome_text = (
        f"👋 *Привет, {message.from_user.first_name}!*\n\n"
        "🏎 Ты попал в *CarCase* — элитный клуб коллекционеров!\n\n"
        "Испытай удачу и собери коллекцию редчайших гиперкаров мира.\n\n"
        "🕒 *Кейс доступен каждые 5 часов.*"
    )
    await message.answer_photo(
        photo=PHOTO_URL,
        caption=welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )

# --- ОБРАБОТЧИКИ КНОПОК ---
@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    welcome_text = (
        f"👋 *Привет, {callback.from_user.first_name}!*\n\n"
        "🏎 Ты попал в *CarCase* — элитный клуб коллекционеров!\n\n"
        "🕒 *Кейс доступен каждые 5 часов.*"
    )
    try:
        await callback.message.edit_caption(
            caption=welcome_text, 
            parse_mode="Markdown", 
            reply_markup=get_main_menu_keyboard()
        )
    except TelegramBadRequest:
        pass
    await callback.answer()

@dp.callback_query(F.data == "open_case_btn")
async def btn_open(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    now = time.time()
    if user_id not in users:
        users[user_id] = {"rep": 0, "garage": [], "last_case": 0}

    wait_time = 18000
    if now - users[user_id].get("last_case", 0) < wait_time:
        rem = int(wait_time - (now - users[user_id].get("last_case", 0)))
        await callback.answer(f"⏳ Жди {rem//3600}ч {(rem%3600)//60}м", show_alert=True)
        return

    rarity = random.choices(list(RARITY_CONFIG.keys()), [r["chance"] for r in RARITY_CONFIG.values()], k=1)[0]
    car_name = random.choice([n for n, r in CARS_DATABASE.items() if r == rarity])
    
    is_new = car_name not in users[user_id]["garage"]
    rep_gain = RARITY_CONFIG[rarity]["new_rep" if is_new else "old_rep"]
    
    users[user_id]["rep"] += rep_gain
    if is_new: users[user_id]["garage"].append(car_name)
    users[user_id]["last_case"] = now
    save_db()

    next_rank, progress = get_next_rank_info(users[user_id]["rep"])
    progress_bar = "█" * (progress // 10) + "░" * (10 - (progress // 10))

    result_text = (
        f"📦 *КЕЙС ОТКРЫТ!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏎 *Авто:* `{car_name}`\n"
        f"💎 *Редкость:* `{rarity}`\n"
        f"📈 *REP:* `+{rep_gain}` {'(NEW! 🔥)' if is_new else ''}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎖 *Ранг:* `{get_rank(users[user_id]['rep'])}`\n"
        f"📊 *До {next_rank}:* `{progress}%`\n"
        f"`[{progress_bar}]`"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"))
    
    await callback.message.edit_caption(caption=result_text, parse_mode="Markdown", reply_markup=builder.as_markup())
    await callback.answer(f"Выпала {car_name}!")

@dp.callback_query(F.data == "profile_btn")
async def btn_profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in users:
        await callback.answer("Сначала открой свой первый кейс!", show_alert=True)
        return

    u = users[user_id]
    rep = u['rep']
    rank = get_rank(rep)
    next_rank, progress = get_next_rank_info(rep)
    
    # Считаем редкости
    counts = {"Legendary": 0, "Epic": 0, "Rare": 0, "Common": 0}
    for car in u['garage']:
        r = CARS_DATABASE.get(car, "Common")
        counts[r] += 1

    # Полоска прогресса (стиль [██░░░░░░░░])
    progress_bar = "█" * (progress // 10) + "░" * (10 - (progress // 10))

    msg = (
        f"👤 *КАРТОЧКА КОЛЛЕКЦИОНЕРА*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎖 *Ваш ранг:* `{rank}`\n"
        f"🏆 *Репутация (REP):* `{rep:,}`\n\n"
        f"📊 *До ранга {next_rank}:*\n"
        f"`[{progress_bar}]` *{progress}%*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏎 *ВАШ ГАРАЖ:*\n"
        f"💎 Legendary: `{counts['Legendary']}`\n"
        f"🟣 Epic: `{counts['Epic']}`\n"
        f"🔵 Rare: `{counts['Rare']}`\n"
        f"⚪ Common: `{counts['Common']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ *Всего машин:* `{len(u['garage'])}`"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"))
    
    try:
        await callback.message.edit_caption(caption=msg, parse_mode="Markdown", reply_markup=builder.as_markup())
    except TelegramBadRequest:
        pass
    await callback.answer()

@dp.callback_query(F.data == "garage_btn")
async def btn_garage(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in users or not users[user_id]["garage"]:
        await callback.answer("Твой гараж пока пуст!", show_alert=True)
        return

    u = users[user_id]
    sorted_garage = sorted(u['garage'], key=lambda x: (["Legendary", "Epic", "Rare", "Common"].index(CARS_DATABASE.get(x, "Common"))))
    
    garage_text = "🏎 *ТВОЙ ГАРАЖ (ТОП-15):*\n"
    garage_text += "━━━━━━━━━━━━━━━━━━━━\n"
    for car in sorted_garage[:15]:
        r = CARS_DATABASE.get(car, "Common")
        emoji = RARITY_CONFIG[r]["emoji"]
        garage_text += f"{emoji} `{car}`\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"))
    
    try:
        await callback.message.edit_caption(caption=garage_text, parse_mode="Markdown", reply_markup=builder.as_markup())
    except TelegramBadRequest:
        pass
    await callback.answer()

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
