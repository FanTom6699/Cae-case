import asyncio
import random
import logging
import sqlite3
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# --- КОНФИГУРАЦИЯ ---
# Берем токен из переменной окружения PowerShell
API_TOKEN = os.getenv("BOT_TOKEN") 

# Базовая ссылка на твой GitHub (Raw)
GITHUB_BASE_URL = "https://raw.githubusercontent.com/fantom6699/cae-case/main/cards/"

if not API_TOKEN:
    exit("Ошибка: Переменная BOT_TOKEN не найдена в системе!")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ МАШИН ---
CARS_DATABASE = {
    "Обычные": [
        "toyota_camry", "honda_civic", "ford_focus", 
        "vw_golf", "hyundai_solaris", "kia_rio", "lada_vesta"
    ],
    "Редкие": [
        "nissan_skyline_gtr", "subaru_impreza", "bmw_m3_e46", 
        "toyota_supra", "mitsubishi_lancer_evo", "audi_tt"
    ],
    "Эпические": [
        "bmw_m5_f90", "mercedes_amg_gy", "auidi_r8", 
        "porshe_911_turbo_s", "ferrari_458_italia", "lamborghini_huracan"
    ],
    "Легендарные": [
        "bugatti_chiron", "koenigsegg_agera_rs", "pagani_huayra", 
        "mclaren_p1", "ferrari_laferrari"
    ]
}

CATEGORY_TO_FOLDER = {
    "Обычные": "common",
    "Редкие": "rare",
    "Эпические": "epic",
    "Легендарные": "legendary"
}

# --- SQLITE БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, exp INTEGER, level INTEGER)')
    cursor.execute('CREATE TABLE IF NOT EXISTS garage (user_id INTEGER, car_id TEXT)')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT exp, level FROM users WHERE user_id = ?", (user_id,))
    data = cursor.fetchone()
    if not data:
        cursor.execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, 0, 1))
        conn.commit()
        data = (0, 1)
    conn.close()
    return data

def add_to_garage(user_id, car_id):
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO garage (user_id, car_id) VALUES (?, ?)", (user_id, car_id))
    conn.commit()
    conn.close()

def get_garage(user_id):
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT car_id FROM garage WHERE user_id = ?", (user_id,))
    return [row[0] for row in cursor.fetchall()]

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
    init_db()
    await message.answer("🏎 Добро пожаловать! Используй меню для игры.", reply_markup=main_keyboard())

@dp.message(F.text == "📦 Открыть кейс")
async def open_case(message: types.Message):
    # Шансы выпадения
    chance = random.random() * 100
    if chance < 1: rarity = "Легендарные"
    elif chance < 10: rarity = "Эпические"
    elif chance < 40: rarity = "Редкие"
    else: rarity = "Обычные"

    car_file = random.choice(CARS_DATABASE[rarity])
    add_to_garage(message.from_user.id, car_file)
    
    folder = CATEGORY_TO_FOLDER[rarity]
    # Проверка на Porsche (.jpg)
    extension = ".jpg" if "porshe" in car_file else ".png"
    photo_url = f"{GITHUB_BASE_URL}{folder}/{car_file}{extension}"
    
    display_name = car_file.replace('_', ' ').title()
    caption = f"🎁 *ТЕБЕ ВЫПАЛО:*\n\n🏎 Авто: `{display_name}`\n💎 Редкость: *{rarity}*"

    # Здесь НЕТ параметра reply_markup, поэтому инлайн-кнопок под фото НЕ БУДЕТ
    try:
        await message.answer_photo(photo=photo_url, caption=caption, parse_mode="Markdown")
    except Exception:
        await message.answer(f"{caption}\n\n⚠️ Ошибка загрузки фото.")

@dp.message(F.text == "🏎 Гараж")
async def show_garage(message: types.Message):
    cars = get_garage(message.from_user.id)
    if not cars:
        await message.answer("В гараже пока пусто.")
        return

    builder = InlineKeyboardBuilder()
    # Инлайн кнопки только здесь, чтобы смотреть детали машин
    for car_id in set(cars):
        display_name = car_id.replace('_', ' ').title()
        builder.button(text=display_name, callback_data=f"view_car_{car_id}")
    
    builder.adjust(2)
    await message.answer("🏎 Твой гараж:\n(Нажми на кнопку, чтобы увидеть фото)", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("view_car_"))
async def view_car_in_garage(callback: types.CallbackQuery):
    car_file = callback.data.replace("view_car_", "")
    
    # Поиск редкости для определения папки
    rarity = next((r for r, cars in CARS_DATABASE.items() if car_file in cars), "Обычные")
    folder = CATEGORY_TO_FOLDER[rarity]
    extension = ".jpg" if "porshe" in car_file else ".png"
    photo_url = f"{GITHUB_BASE_URL}{folder}/{car_file}{extension}"
    
    display_name = car_file.replace('_', ' ').title()
    
    await callback.message.answer_photo(
        photo=photo_url,
        caption=f"🏎 *{display_name}*\n💎 Редкость: {rarity}",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(F.text == "👤 Профиль")
async def profile_cmd(message: types.Message):
    exp, level = get_user_data(message.from_user.id)
    await message.answer(f"👤 *ПРОФИЛЬ*\n\nУровень: `{level}`\nОпыт: `{exp}/{level*100}`", parse_mode="Markdown")

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
