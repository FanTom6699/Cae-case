import asyncio
import time
import json
import random
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from datetime import datetime, timedelta

# --- КОНФИГУРАЦИЯ ---
load_dotenv() # Загружаем переменные из .env
API_TOKEN = os.getenv("BOT_TOKEN")

if not API_TOKEN:
    print("ОШИБКА: Токен не найден! Создай файл .env и добавь туда BOT_TOKEN=твои_токен")
    exit()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Файл базы данных
DB_FILE = "database.json"

# Загрузка базы данных
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                # JSON хранит ключи как строки, конвертируем обратно в int для user_id
                return {int(k): v for k, v in data.items()}
            except json.JSONDecodeError:
                return {}
    return {}

# Сохранение базы данных
def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

# Инициализация базы
users = load_db()

# --- КОНТЕНТ ---

# Редкости и шансы (Common - 60%, Rare - 30%, Epic - 9%, Legendary - 1%)
RARITY_CONFIG = {
    "Common": {"chance": 60, "new_rep": 20, "old_rep": 4},
    "Rare": {"chance": 30, "new_rep": 100, "old_rep": 20},
    "Epic": {"chance": 9, "new_rep": 500, "old_rep": 100},
    "Legendary": {"chance": 1, "new_rep": 2500, "old_rep": 500}
}

# Список машин
CARS_DATABASE = {
    # Common
    "Toyota Camry": "Common",
    "Honda Civic": "Common",
    "Ford Focus": "Common",
    "Volkswagen Golf": "Common",
    "Hyundai Solaris": "Common",
    "Kia Rio": "Common",
    "Lada Vesta": "Common",
    
    # Rare
    "Nissan Skyline GTR": "Rare",
    "Subaru Impreza WRX": "Rare",
    "BMW M3 E46": "Rare",
    "Toyota Supra A80": "Rare",
    "Mitsubishi Lancer Evo": "Rare",
    "Audi TT": "Rare",
    
    # Epic
    "BMW M5 F90": "Epic",
    "Mercedes-Benz AMG GT": "Epic",
    "Audi R8": "Epic",
    "Porsche 911 Turbo S": "Epic",
    "Ferrari 458 Italia": "Epic",
    "Lamborghini Huracan": "Epic",
    
    # Legendary
    "Bugatti Chiron": "Legendary",
    "Koenigsegg Agera RS": "Legendary",
    "Pagani Huayra": "Legendary",
    "McLaren P1": "Legendary",
    "Ferrari LaFerrari": "Legendary"
}

# Настройки Рангов
RANKS = [
    (0, "Любитель"),
    (1500, "Поисковик"),
    (5000, "Охотник за редкостями"),
    (15000, "Эксперт марки"),
    (40000, "Эстет"),
    (100000, "Миллиардер"),
    (250000, "Икона стиля")
]

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_rank(rep):
    for threshold, name in reversed(RANKS):
        if rep >= threshold:
            return name
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

def get_random_car():
    # Выбор редкости
    rarities = list(RARITY_CONFIG.keys())
    weights = [RARITY_CONFIG[r]["chance"] for r in rarities]
    chosen_rarity = random.choices(rarities, weights=weights, k=1)[0]
    
    # Выбор машины этой редкости
    available_cars = [name for name, r in CARS_DATABASE.items() if r == chosen_rarity]
    return random.choice(available_cars), chosen_rarity

# --- КОМАНДЫ ---

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🏎 Добро пожаловать в CarCase! Используй /case чтобы открыть кейс раз в 5 часов.")

@dp.message(Command("case"))
async def open_case(message: types.Message):
    user_id = message.from_user.id
    now = time.time()

    if user_id not in users:
        users[user_id] = {"rep": 0, "garage": [], "last_case": 0}

    wait_time = 18000 # 5 часов
    
    if now - users[user_id].get("last_case", 0) < wait_time:
        remaining = int(wait_time - (now - users[user_id].get("last_case", 0)))
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        await message.answer(f"⏳ Рано! Следующий кейс через {hours}ч {minutes}м.")
        return

    car_name, rarity = get_random_car()
    
    is_new = car_name not in users[user_id]["garage"]
    rep_gain = RARITY_CONFIG[rarity]["new_rep" if is_new else "old_rep"]
    
    users[user_id]["rep"] += rep_gain
    if is_new:
        users[user_id]["garage"].append(car_name)
    users[user_id]["last_case"] = now
    
    # Сохраняем прогресс
    save_db()

    current_rank = get_rank(users[user_id]["rep"])
    next_rank, progress = get_next_rank_info(users[user_id]["rep"])
    
    bars = progress // 10
    progress_bar = "█" * bars + "░" * (10 - bars)

    msg = (
        f"📦 *КЕЙС ОТКРЫТ!*\n\n"
        f"👤 *Игрок:* @{message.from_user.username}\n"
        f"🏎 *Машина:* {car_name}\n"
        f"💎 *Редкость:* {rarity}\n\n"
        f"🎖 *Ваш статус:* {current_rank}\n"
        f"📊 *До ранга {next_rank}:*\n"
        f"`[{progress_bar}] {progress}%`\n\n"
        f"📈 *Репутация:* +{rep_gain} REP {'(НОВИНКА! 🔥)' if is_new else '(Повтор)'}"
    )

    await message.answer(msg, parse_mode="Markdown")

@dp.message(Command("profile"))
async def profile(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Ты еще не открывал кейсы!")
        return
    
    u = users[user_id]
    
    # Сортировка гаража по редкости
    sorted_garage = sorted(
        u['garage'], 
        key=lambda x: (
            ["Legendary", "Epic", "Rare", "Common"].index(CARS_DATABASE.get(x, "Common")), 
            x
        )
    )
    
    garage_preview = ", ".join(sorted_garage[:10])
    if len(sorted_garage) > 10:
        garage_preview += f" и еще {len(sorted_garage) - 10}..."

    msg = (
        f"🪪 *ПРОФИЛЬ КОЛЛЕКЦИОНЕРА*\n\n"
        f"🎖 *Статус:* {get_rank(u['rep'])}\n"
        f"🏆 *Общий REP:* {u['rep']}\n"
        f"🏎 *В гараже:* {len(u['garage'])} шт.\n"
        f"📋 *Топ авто:* {garage_preview}"
    )
    await message.answer(msg, parse_mode="Markdown")

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
