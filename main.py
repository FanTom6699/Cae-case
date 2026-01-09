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
# Бот берет токен из переменной окружения BOT_TOKEN
API_TOKEN = os.getenv("BOT_TOKEN") 

# Базовая ссылка на Raw-контент твоего репозитория
GITHUB_BASE_URL = "https://raw.githubusercontent.com/fantom6699/cae-case/main/cards/"

if not API_TOKEN:
    exit("Ошибка: Переменная BOT_TOKEN не найдена!")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ МАШИН ---
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

# --- SQLITE БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, exp INTEGER, level INTEGER)')
    cursor.execute('CREATE TABLE IF NOT EXISTS garage (user_id INTEGER, car_id TEXT)')
    conn.commit()
    conn.close()

def add_to_garage(user_id, car_id):
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO garage (user_id, car_id) VALUES (?, ?)", (user_id, car_id))
    conn.commit()
    conn.close()

def get_user_cars_in_category(user_id, category):
    conn = sqlite3.connect('user_data.db')
    cursor = conn.cursor()
    # Получаем список всех машин пользователя
    cursor.execute("SELECT car_id FROM garage WHERE user_id = ?", (user_id,))
    user_cars = [row[0] for row in cursor.fetchall()]
    conn.close()
    # Фильтруем только те, что относятся к выбранной категории
    return [car for car in set(user_cars) if car in CARS_DATABASE[category]]

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
    chance = random.random() * 100
    if chance < 1: rarity = "Легендарные"
    elif chance < 10: rarity = "Эпические"
    elif chance < 40: rarity = "Редкие"
    else: rarity = "Обычные"

    car_file = random.choice(CARS_DATABASE[rarity])
    add_to_garage(message.from_user.id, car_file)
    
    folder = CATEGORY_TO_FOLDER[rarity]
    extension = ".jpg" if "porshe" in car_file else ".png"
    photo_url = f"{GITHUB_BASE_URL}{folder}/{car_file}{extension}"
    
    display_name = car_file.replace('_', ' ').title()
    caption = f"🎁 *ТЕБЕ ВЫПАЛО:*\n\n🏎 Авто: `{display_name}`\n💎 Редкость: *{rarity}*"

    try:
        await message.answer_photo(photo=photo_url, caption=caption, parse_mode="Markdown")
    except Exception:
        await message.answer(f"{caption}\n\n⚠️ Ошибка загрузки фото.")

@dp.message(F.text == "🏎 Гараж")
async def garage_categories(message: types.Message):
    builder = InlineKeyboardBuilder()
    for cat in CARS_DATABASE.keys():
        builder.button(text=cat, callback_data=f"gar_cat_{cat}")
    builder.adjust(2)
    await message.answer("🏎 Выберите категорию гаража:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("gar_cat_"))
async def show_cars_in_category(callback: types.CallbackQuery):
    category = callback.data.replace("gar_cat_", "")
    user_id = callback.from_user.id
    
    cars = get_user_cars_in_category(user_id, category)
    
    if not cars:
        await callback.answer(f"В категории '{category}' у вас еще нет машин!", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for car_id in cars:
        display_name = car_id.replace('_', ' ').title()
        builder.button(text=display_name, callback_data=f"view_car_{car_id}")
    
    builder.button(text="⬅️ Назад", callback_data="back_to_cats")
    builder.adjust(2)
    
    await callback.message.edit_text(f"🏎 Категория: *{category}*\nВаши машины:", 
                                     parse_mode="Markdown", 
                                     reply_markup=builder.as_markup())

@dp.callback_query(F.data == "back_to_cats")
async def back_to_categories(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    for cat in CARS_DATABASE.keys():
        builder.button(text=cat, callback_data=f"gar_cat_{cat}")
    builder.adjust(2)
    await callback.message.edit_text("🏎 Выберите категорию гаража:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("view_car_"))
async def view_car_in_garage(callback: types.CallbackQuery):
    car_file = callback.data.replace("view_car_", "")
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

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
