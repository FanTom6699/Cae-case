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
            except: return {}
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

def get_user_name(user: types.User):
    if user.username: return f"@{user.username}"
    return user.first_name

# Клавиатура теперь включает ID владельца в callback_data, чтобы кнопки были персональными
def get_main_menu_keyboard(owner_id):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📦 Открыть кейс", callback_data=f"open_{owner_id}"))
    builder.row(
        types.InlineKeyboardButton(text="🪪 Профиль", callback_data=f"prof_{owner_id}"),
        types.InlineKeyboardButton(text="🏎 Гараж", callback_data=f"gar_{owner_id}")
    )
    return builder.as_markup()

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def start(message: types.Message):
    name = get_user_name(message.from_user)
    welcome_text = (
        f"👋 *Привет, {name}!*\n\n"
        "🏎 Ты попал в *CarCase* — элитный клуб коллекционеров!\n\n"
        "Испытай удачу и собери коллекцию редчайших гиперкаров мира.\n\n"
        "🕒 *Кейс доступен каждые 5 часов.*"
    )
    await message.answer_photo(
        photo=PHOTO_URL,
        caption=welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(message.from_user.id)
    )

# --- ОБРАБОТЧИКИ КНОПОК ---
@dp.callback_query(F.data.startswith(("open_", "prof_", "gar_", "back_")))
async def handle_callbacks(callback: types.CallbackQuery):
    # Разделяем действие и ID владельца
    action, owner_id = callback.data.split("_")
    owner_id = int(owner_id)
    
    # Проверка: тот ли человек нажал на кнопку?
    if callback.from_user.id != owner_id:
        await callback.answer("❌ Это не ваше меню! Вызовите свое через /start", show_alert=True)
        return

    name = get_user_name(callback.from_user)

    if action == "back":
        welcome_text = (
            f"👋 *Привет, {name}!*\n\n"
            "🏎 Ты попал в *CarCase* — элитный клуб коллекционеров!\n\n"
            "🕒 *Кейс доступен каждые 5 часов.*"
        )
        await callback.message.edit_caption(caption=welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(owner_id))

    elif action == "open":
        now = time.time()
        if owner_id not in users: users[owner_id] = {"rep": 0, "garage": [], "last_case": 0}

        wait_time = 18000
        if now - users[owner_id].get("last_case", 0) < wait_time:
            rem = int(wait_time - (now - users[owner_id].get("last_case", 0)))
            await callback.answer(f"⏳ {name}, жди {rem//3600}ч {(rem%3600)//60}м", show_alert=True)
            return

        rarity = random.choices(list(RARITY_CONFIG.keys()), [r["chance"] for r in RARITY_CONFIG.values()], k=1)[0]
        car_name = random.choice([n for n, r in CARS_DATABASE.items() if r == rarity])
        
        is_new = car_name not in users[owner_id]["garage"]
        rep_gain = RARITY_CONFIG[rarity]["new_rep" if is_new else "old_rep"]
        
        users[owner_id]["rep"] += rep_gain
        if is_new: users[owner_id]["garage"].append(car_name)
        users[owner_id]["last_case"] = now
        save_db()

        next_rank, progress = get_next_rank_info(users[owner_id]["rep"])
        progress_bar = "█" * (progress // 10) + "░" * (10 - (progress // 10))

        result_text = (
            f"📦 *{name}, КЕЙС ОТКРЫТ!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏎 *Авто:* `{car_name}`\n"
            f"💎 *Редкость:* `{rarity}`\n"
            f"📈 *REP:* `+{rep_gain}` {'(NEW! 🔥)' if is_new else ''}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎖 *Ранг:* `{get_rank(users[owner_id]['rep'])}`\n"
            f"📊 *До {next_rank}:* `{progress}%`\n"
            f"`[{progress_bar}]`"
        )
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_{owner_id}"))
        await callback.message.edit_caption(caption=result_text, parse_mode="Markdown", reply_markup=builder.as_markup())

    elif action == "prof":
        if owner_id not in users:
            await callback.answer("Сначала открой кейс!")
            return
        u = users[owner_id]
        next_rank, progress = get_next_rank_info(u['rep'])
        counts = {"Legendary": 0, "Epic": 0, "Rare": 0, "Common": 0}
        for car in u['garage']: counts[CARS_DATABASE.get(car, "Common")] += 1
        
        progress_bar = "█" * (progress // 10) + "░" * (10 - (progress // 10))
        msg = (
            f"👤 *ПРОФИЛЬ: {name}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎖 *Ранг:* `{get_rank(u['rep'])}`\n"
            f"🏆 *Репутация:* `{u['rep']:,}`\n\n"
            f"📊 *До {next_rank}:* `{progress}%`\n"
            f"`[{progress_bar}]`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏎 *ГАРАЖ:*\n"
            f"💎 Leg: `{counts['Legendary']}` | 🟣 Epic: `{counts['Epic']}`\n"
            f"🔵 Rare: `{counts['Rare']}` | ⚪ Com: `{counts['Common']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✨ *Всего машин:* `{len(u['garage'])}`"
        )
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_{owner_id}"))
        await callback.message.edit_caption(caption=msg, parse_mode="Markdown", reply_markup=builder.as_markup())

    elif action == "gar":
        if owner_id not in users or not users[owner_id]["garage"]:
            await callback.answer("Гараж пуст!"); return
        u = users[owner_id]
        sorted_garage = sorted(u['garage'], key=lambda x: (["Legendary", "Epic", "Rare", "Common"].index(CARS_DATABASE.get(x, "Common"))))
        garage_text = f"🏎 *ГАРАЖ: {name}*\n━━━━━━━━━━━━━━━━━━━━\n"
        for car in sorted_garage[:15]:
            r = CARS_DATABASE.get(car, "Common")
            garage_text += f"{RARITY_CONFIG[r]['emoji']} `{car}`\n"
        
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_{owner_id}"))
        await callback.message.edit_caption(caption=garage_text, parse_mode="Markdown", reply_markup=builder.as_markup())

    await callback.answer()

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
