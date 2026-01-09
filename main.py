import asyncio
import random
import logging
import sqlite3
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# --- КОНФИГУРАЦИЯ ---
# Бот будет брать токен из переменной окружения BOT_TOKEN, которую ты задал в PowerShell
API_TOKEN = os.getenv("BOT_TOKEN") 

# Базовая ссылка на Raw-контент твоего репозитория
GITHUB_BASE_URL = "https://raw.githubusercontent.com/fantom6699/cae-case/main/cards/"

if not API_TOKEN:
    exit("Ошибка: Переменная окружения BOT_TOKEN не найдена! Проверь настройки в PowerShell.")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ МАШИН ---
# Имена файлов строго соответствуют твоему репозиторию
CARS_DATABASE = {
    "Обычные": [
        "toyota_camry", "honda_civic", "ford_focus", 
        "vw_golf", "hyundai_solaris", "kia_rio", "lada_vesta"
    ],
    "Редкие": [
        "nissan_skyline_gtr", "subaru_impreza_wrx", "bmw_m3_e46", 
        "toyota_supra", "mitsubishi_lancer_evo", "audi_tt"
    ],
    "Эпические": [
        "bmw_m5_f90", "mercedes_benz_amg_gt", "audi_r8", 
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

# --- РАБОТА С БД ---
def init_db():
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, exp INTEGER, level INTEGER)''')
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

def add_exp(user_id, amount):
    exp, level = get_user_data(user_id)
    new_exp = exp + amount
    new_level = level
    if new_exp >= level * 100:
        new_exp -= level * 100
        new_level += 1
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET exp = ?, level = ? WHERE user_id = ?", (new_exp, new_level, user_id))
    conn.commit()
    conn.close()
    return new_level > level

# --- ИНТЕРФЕЙС ---
def main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📦 Открыть кейс")
    builder.button(text="👤 Профиль")
    return builder.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    init_db()
    await message.answer(f"🏎 Привет, {message.from_user.first_name}! Готов испытать удачу?", reply_markup=main_keyboard())

@dp.message(F.text == "👤 Профиль")
async def profile_cmd(message: types.Message):
    exp, level = get_user_data(message.from_user.id)
    await message.answer(f"👤 *ПРОФИЛЬ*\n\n🎖 Уровень: `{level}`\n📊 Опыт: `{exp}/{level*100}`", parse_mode="Markdown")

@dp.message(F.text == "📦 Открыть кейс")
async def open_case(message: types.Message):
    chance = random.random() * 100
    if chance < 1: rarity = "Легендарные"
    elif chance < 10: rarity = "Эпические"
    elif chance < 40: rarity = "Редкие"
    else: rarity = "Обычные"

    car_file = random.choice(CARS_DATABASE[rarity])
    folder = CATEGORY_TO_FOLDER[rarity]
    
    # Porsche у тебя в репозитории .jpg, остальные .png
    extension = ".jpg" if "porshe" in car_file else ".png"
    photo_url = f"{GITHUB_BASE_URL}{folder}/{car_file}{extension}"
    
    add_exp(message.from_user.id, 20)
    display_name = car_file.replace('_', ' ').title()
    
    caption = f"📦 *КЕЙС ОТКРЫТ!*\n\n🏎 Авто: `{display_name}`\n💎 Редкость: *{rarity}*"

    try:
        await message.answer_photo(photo=photo_url, caption=caption, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка загрузки фото: {e}")
        await message.answer(f"{caption}\n\n⚠️ _Картинка не загрузилась (проверь пути на GitHub)_", parse_mode="Markdown")

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
