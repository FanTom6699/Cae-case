import asyncio
import random
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Конфигурация
API_TOKEN = 'ТВОЙ_ТОКЕН_БОТА'
# Базовая ссылка на твои изображения на GitHub
GITHUB_BASE_URL = "https://raw.githubusercontent.com/fantom6699/cae-case/main/cards/"

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# База данных машин (приведено в соответствие с твоими файлами)
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
        "bmw_m5_f90", "mercedes_benz_amg_gt", "audi_r8", 
        "porshe_911_turbo_s", "ferrari_458_italia", "lamborghini_huracan"
    ],
    "Легендарные": [
        "bugatti_chiron", "koenigsegg_agera_rs", "pagani_huayra", 
        "mclaren_p1", "ferrari_laferrari"
    ]
}

# Маппинг категорий на папки GitHub
CATEGORY_TO_FOLDER = {
    "Обычные": "common",
    "Редкие": "rare",
    "Эпические": "epic",
    "Легендарные": "legendary"
}

# Работа с БД (уровни и опыт)
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

# Клавиатура
def main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📦 Открыть кейс")
    builder.button(text="👤 Профиль")
    return builder.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    init_db()
    await message.answer("Добро пожаловать в CarCase! Открывай кейсы и собирай коллекцию машин.", reply_markup=main_keyboard())

@dp.message(F.text == "👤 Профиль")
async def profile_cmd(message: types.Message):
    exp, level = get_user_data(message.from_user.id)
    await message.answer(f"👤 *Профиль*\n\nуровень: {level}\nОпыт: {exp}/{level*100}", parse_mode="Markdown")

@dp.message(F.text == "📦 Открыть кейс")
async def open_case(message: types.Message):
    # Логика шансов
    chance = random.random() * 100
    if chance < 1:
        rarity = "Легендарные"
    elif chance < 10:
        rarity = "Эпические"
    elif chance < 40:
        rarity = "Редкие"
    else:
        rarity = "Обычные"

    car_file = random.choice(CARS_DATABASE[rarity])
    folder = CATEGORY_TO_FOLDER[rarity]
    
    # Исправляем расширение для Porsche (у тебя в репозитории это .jpg)
    extension = ".jpg" if car_file == "porshe_911_turbo_s" else ".png"
    
    # Формируем прямую ссылку на фото
    photo_url = f"{GITHUB_BASE_URL}{folder}/{car_file}{extension}"
    
    # Добавляем опыт
    leveled_up = add_exp(message.from_user.id, 20)
    
    car_name_display = car_file.replace('_', ' ').title()
    result_text = f"🎉 Тебе выпала машина: *{car_name_display}*\nРедкость: *{rarity}*"
    
    if leveled_up:
        result_text += "\n\n🆙 *Новый уровень!*"

    try:
        await message.answer_photo(photo=photo_url, caption=result_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка отправки фото: {e}")
        await message.answer(f"{result_text}\n\n(Не удалось загрузить фото)")

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
