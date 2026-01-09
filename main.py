import asyncio
import random
import logging
import json
import os
from dotenv import load_dotenv  # Добавили загрузку .env
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# Загружаем переменные из файла .env
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# --- КОНФИГУРАЦИЯ ---
# Теперь бот сам найдет BOT_TOKEN внутри твоего файла .env
API_TOKEN = os.getenv("BOT_TOKEN") 
DB_FILE = "database.json" 
GITHUB_BASE_URL = "https://raw.githubusercontent.com/fantom6699/cae-case/main/cards/"

if not API_TOKEN:
    exit("Ошибка: Переменная BOT_TOKEN не найдена в файле .env!")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ МАШИН ---
CARS_DATABASE = {
    "Обычные": ["toyota_camry", "honda_civic", "ford_focus", "vw_golf", "hyundai_solaris", "kia_rio", "lada_vesta"],
    "Редкие": ["nissan_skyline_gtr", "subaru_impreza", "bmw_m3_e46", "toyota_supra", "mitsubishi_lancer_evo", "audi_tt"],
    "Эпические": ["bmw_m5_f90", "mercedes_benz_amg_gt", "audi_r8", "porshe_911_turbo_s", "ferrari_458_italia", "lamborghini_huracan"],
    "Легендарные": ["bugatti_chiron", "koenigsegg_agera_rs", "pagani_huayra", "mclaren_p1", "ferrari_laferrari"]
}

CATEGORY_TO_FOLDER = {"Обычные": "common", "Редкие": "rare", "Эпические": "epic", "Легендарные": "legendary"}

# --- РАБОТА С JSON ---
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
            except: return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# Инициализация данных
users = load_db()

def init_user(user_id):
    if user_id not in users:
        users[user_id] = {"exp": 0, "level": 1, "garage": []}
        save_db(users)

# --- КЛАВИАТУРЫ ---
def main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📦 Открыть кейс")
    builder.button(text="👤 Профиль")
    builder.button(text="🏎 Гараж")
    return builder.as_markup(resize_keyboard=True)

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    init_user(message.from_user.id)
    await message.answer("🏎 Бот запущен! Данные берутся из .env и сохраняются в database.json", reply_markup=main_keyboard())

@dp.message(F.text == "📦 Открыть кейс")
async def open_case(message: types.Message):
    user_id = message.from_user.id
    init_user(user_id)
    
    chance = random.random() * 100
    if chance < 1: rarity = "Легендарные"
    elif chance < 10: rarity = "Эпические"
    elif chance < 40: rarity = "Редкие"
    else: rarity = "Обычные"

    car_file = random.choice(CARS_DATABASE[rarity])
    users[user_id]["garage"].append(car_file)
    
    # Опыт
    users[user_id]["exp"] += 20
    if users[user_id]["exp"] >= users[user_id]["level"] * 100:
        users[user_id]["exp"] = 0
        users[user_id]["level"] += 1
    
    save_db(users)

    folder = CATEGORY_TO_FOLDER[rarity]
    extension = ".jpg" if "porshe" in car_file else ".png"
    photo_url = f"{GITHUB_BASE_URL}{folder}/{car_file}{extension}"
    
    display_name = car_file.replace('_', ' ').title()
    await message.answer_photo(photo=photo_url, caption=f"🎁 Выпало: *{display_name}*\n💎 Редкость: {rarity}", parse_mode="Markdown")

@dp.message(F.text == "🏎 Гараж")
async def garage_categories(message: types.Message):
    builder = InlineKeyboardBuilder()
    for cat in CARS_DATABASE.keys():
        builder.button(text=cat, callback_data=f"gar_cat_{cat}")
    builder.adjust(2)
    await message.answer("🏎 Категории твоего гаража:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("gar_cat_"))
async def show_category(callback: types.CallbackQuery):
    cat = callback.data.replace("gar_cat_", "")
    user_id = callback.from_user.id
    init_user(user_id)
    
    # Показываем только уникальные машины игрока в этой категории
    user_cars = [c for c in set(users[user_id]["garage"]) if c in CARS_DATABASE[cat]]
    
    if not user_cars:
        await callback.answer(f"В категории {cat} пока пусто!", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for car_id in user_cars:
        builder.button(text=car_id.replace('_', ' ').title(), callback_data=f"view_car_{car_id}")
    builder.button(text="⬅️ Назад", callback_data="back_to_cats")
    builder.adjust(2)
    
    await callback.message.edit_text(f"🏎 Твои машины в категории {cat}:", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "back_to_cats")
async def back(callback: types.CallbackQuery):
    await garage_categories(callback.message)
    await callback.answer()

@dp.callback_query(F.data.startswith("view_car_"))
async def view_car(callback: types.CallbackQuery):
    car_file = callback.data.replace("view_car_", "")
    rarity = next((r for r, cars in CARS_DATABASE.items() if car_file in cars), "Обычные")
    extension = ".jpg" if "porshe" in car_file else ".png"
    photo_url = f"{GITHUB_BASE_URL}{CATEGORY_TO_FOLDER[rarity]}/{car_file}{extension}"
    
    await callback.message.answer_photo(photo=photo_url, caption=f"🏎 *{car_file.replace('_', ' ').title()}*", parse_mode="Markdown")
    await callback.answer()

@dp.message(F.text == "👤 Профиль")
async def profile_cmd(message: types.Message):
    init_user(message.from_user.id)
    u = users[message.from_user.id]
    await message.answer(f"👤 *ПРОФИЛЬ*\n\n🎖 Уровень: `{u['level']}`\n📊 Опыт: `{u['exp']}/{u['level']*100}`", parse_mode="Markdown")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
