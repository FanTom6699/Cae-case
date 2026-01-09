import asyncio
import random
import logging
import json
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# --- КОНФИГУРАЦИЯ ---
# Бот берет токен из переменной окружения BOT_TOKEN (PowerShell)
API_TOKEN = os.getenv("BOT_TOKEN") 
DB_FILE = "database.json" # Файл базы данных
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
        "nissan_skyline_gtr", "subaru_impreza", "bmv_m3_e46", 
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

# --- ФУНКЦИИ JSON БАЗЫ ДАННЫХ ---
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                # Превращаем ID пользователей обратно в числа
                return {int(k): v for k, v in data.items()}
            except:
                return {}
    return {}

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

# Загружаем данные при старте
users = load_db()

def init_user(user_id):
    if user_id not in users:
        users[user_id] = {"exp": 0, "level": 1, "garage": []}
        save_db()

def add_exp(user_id, amount):
    init_user(user_id)
    u = users[user_id]
    u["exp"] += amount
    leveled_up = False
    # Логика уровня: каждые level * 100 опыта
    if u["exp"] >= u["level"] * 100:
        u["exp"] -= u["level"] * 100
        u["level"] += 1
        leveled_up = True
    save_db()
    return leveled_up

# --- ИНТЕРФЕЙС ---
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
    await message.answer(f"🏎 Привет, {message.from_user.first_name}! Бот на связи.", reply_markup=main_keyboard())

@dp.message(F.text == "📦 Открыть кейс")
async def open_case(message: types.Message):
    init_user(message.from_user.id)
    chance = random.random() * 100
    if chance < 1: rarity = "Легендарные"
    elif chance < 10: rarity = "Эпические"
    elif chance < 40: rarity = "Редкие"
    else: rarity = "Обычные"

    car_file = random.choice(CARS_DATABASE[rarity])
    
    # Добавляем в гараж и сохраняем опыт
    users[message.from_user.id]["garage"].append(car_file)
    leveled_up = add_exp(message.from_user.id, 20)
    
    folder = CATEGORY_TO_FOLDER[rarity]
    extension = ".jpg" if "porshe" in car_file else ".png"
    photo_url = f"{GITHUB_BASE_URL}{folder}/{car_file}{extension}"
    
    display_name = car_file.replace('_', ' ').title()
    caption = f"🎁 *ТЕБЕ ВЫПАЛО:*\n\n🏎 Авто: `{display_name}`\n💎 Редкость: *{rarity}*"
    if leveled_up:
        caption += "\n\n🆙 *НОВЫЙ УРОВЕНЬ!*"

    try:
        await message.answer_photo(photo=photo_url, caption=caption, parse_mode="Markdown")
    except Exception:
        await message.answer(f"{caption}\n\n⚠️ Ошибка фото.")

@dp.message(F.text == "🏎 Гараж")
async def garage_categories(message: types.Message):
    init_user(message.from_user.id)
    builder = InlineKeyboardBuilder()
    for cat in CARS_DATABASE.keys():
        builder.button(text=cat, callback_data=f"gar_cat_{cat}")
    builder.adjust(2)
    await message.answer("🏎 Выберите категорию гаража:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("gar_cat_"))
async def show_cars_in_category(callback: types.CallbackQuery):
    category = callback.data.replace("gar_cat_", "")
    user_id = callback.from_user.id
    init_user(user_id)
    
    # Фильтруем машины пользователя по категории
    user_garage = users[user_id]["garage"]
    cars_in_cat = [car for car in set(user_garage) if car in CARS_DATABASE[category]]
    
    if not cars_in_cat:
        await callback.answer(f"В категории '{category}' пусто!", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for car_id in cars_in_cat:
        display_name = car_id.replace('_', ' ').title()
        builder.button(text=display_name, callback_data=f"view_car_{car_id}")
    
    builder.button(text="⬅️ Назад", callback_data="back_to_cats")
    builder.adjust(2)
    
    await callback.message.edit_text(f"🏎 Категория: *{category}*\nТвои машины:", 
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

@dp.message(F.text == "👤 Профиль")
async def profile_cmd(message: types.Message):
    init_user(message.from_user.id)
    u = users[message.from_user.id]
    await message.answer(f"👤 *ПРОФИЛЬ*\n\n🎖 Уровень: `{u['level']}`\n📊 Опыт: `{u['exp']}/{u['level']*100}`", parse_mode="Markdown")

async def main():
    save_db() # Создаем файл если его нет
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
