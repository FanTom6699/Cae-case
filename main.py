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

# --- КОНТЕНТ (Переведено на русский) ---
RARITY_CONFIG = {
    "Обычные": {"chance": 60, "new_rep": 20, "old_rep": 4, "emoji": "⚪"},
    "Редкие": {"chance": 30, "new_rep": 100, "old_rep": 20, "emoji": "🔵"},
    "Эпические": {"chance": 9, "new_rep": 500, "old_rep": 100, "emoji": "🟣"},
    "Легендарные": {"chance": 1, "new_rep": 2500, "old_rep": 500, "emoji": "💎"}
}

CARS_DATABASE = {
    "Toyota Camry": "Обычные", "Honda Civic": "Обычные", "Ford Focus": "Обычные",
    "Volkswagen Golf": "Обычные", "Hyundai Solaris": "Обычные", "Kia Rio": "Обычные", "Lada Vesta": "Обычные",
    "Nissan Skyline GTR": "Редкие", "Subaru Impreza WRX": "Редкие", "BMW M3 E46": "Редкие",
    "Toyota Supra A80": "Редкие", "Mitsubishi Lancer Evo": "Редкие", "Audi TT": "Редкие",
    "BMW M5 F90": "Эпические", "Mercedes-Benz AMG GT": "Эпические", "Audi R8": "Эпические",
    "Porsche 911 Turbo S": "Эпические", "Ferrari 458 Italia": "Эпические", "Lamborghini Huracan": "Эпические",
    "Bugatti Chiron": "Легендарные", "Koenigsegg Agera RS": "Легендарные", "Pagani Huayra": "Легендарные",
    "McLaren P1": "Легендарные", "Ferrari LaFerrari": "Легендарные"
}

RANKS = [(0, "Любитель"), (1500, "Поисковик"), (5000, "Охотник за редкостями"),
         (15000, "Эксперт марки"), (40000, "Эстет"), (100000, "Миллиардер"), (250000, "Икона стиля")]

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

def get_main_menu_keyboard(owner_id):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📦 Открыть кейс", callback_data=f"open_{owner_id}"))
    builder.row(
        types.InlineKeyboardButton(text="🪪 Профиль", callback_data=f"prof_{owner_id}"),
        types.InlineKeyboardButton(text="🏎 Гараж", callback_data=f"garcat_{owner_id}")
    )
    return builder.as_markup()

# --- ЛОГИКА ОТКРЫТИЯ КЕЙСА (Вынесена для повторного использования) ---
async def open_case_logic(user_id, name):
    now = time.time()
    if user_id not in users: users[user_id] = {"rep": 0, "garage": [], "last_case": 0}
    wait_time = 18000
    if now - users[user_id].get("last_case", 0) < wait_time:
        rem = int(wait_time - (now - users[user_id].get("last_case", 0)))
        return False, f"⏳ {name}, еще рано! Приходи через {rem//3600}ч {(rem%3600)//60}м."

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
    
    text = (
        f"📦 *{name}, КЕЙС ОТКРЫТ!*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🏎 *Авто:* `{car_name}`\n💎 *Редкость:* `{rarity}`\n📈 *REP:* `+{rep_gain}` {'(NEW! 🔥)' if is_new else ''}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n🎖 *Ранг:* `{get_rank(users[user_id]['rep'])}`\n"
        f"📊 *До {next_rank}:* `{progress}%`\n`[{progress_bar}]`"
    )
    return True, text

# --- КОМАНДЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    name = message.from_user.first_name
    await message.answer_photo(photo=PHOTO_URL, caption=f"👋 *Привет, {name}!*\n\n🏎 Это *CarCase*! Используй кнопки ниже.", parse_mode="Markdown", reply_markup=get_main_menu_keyboard(message.from_user.id))

@dp.message(Command("case"))
@dp.message(F.text.lower().in_(["кейс", "машина", "машинка"]))
async def cmd_case(message: types.Message):
    success, result = await open_case_logic(message.from_user.id, message.from_user.first_name)
    if success:
        await message.answer_photo(photo=PHOTO_URL, caption=result, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(message.from_user.id))
    else:
        await message.reply(result, parse_mode="Markdown")

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    # Код профиля вызовем через имитацию нажатия кнопки
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала открой кейс!")
        return
    # Вместо простого старта сразу генерируем текст профиля
    await btn_profile_manual(message)

# --- CALLBACKS ---
@dp.callback_query(F.data.startswith(("open_", "prof_", "garcat_", "garlist_", "back_")))
async def handle_callbacks(callback: types.CallbackQuery):
    data = callback.data.split("_")
    action = data[0]
    owner_id = int(data[1])
    
    if callback.from_user.id != owner_id:
        await callback.answer("❌ Это не ваше меню!", show_alert=True)
        return

    name = callback.from_user.first_name

    if action == "back":
        await callback.message.edit_caption(caption=f"🏎 *CarCase* — Главное меню\n\nИгрок: *{name}*", parse_mode="Markdown", reply_markup=get_main_menu_keyboard(owner_id))

    elif action == "open":
        success, result = await open_case_logic(owner_id, name)
        if success:
            await callback.message.edit_caption(caption=result, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(owner_id))
        else:
            await callback.answer(result.replace(f"⏳ {name}, ", ""), show_alert=True)

    elif action == "prof":
        u = users[owner_id]
        next_rank, progress = get_next_rank_info(u['rep'])
        counts = {r: 0 for r in RARITY_CONFIG}
        for car in u['garage']: counts[CARS_DATABASE.get(car, "Обычные")] += 1
        progress_bar = "█" * (progress // 10) + "░" * (10 - (progress // 10))
        msg = (
            f"👤 *ПРОФИЛЬ: {name}*\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🎖 *Ранг:* `{get_rank(u['rep'])}` | 🏆 *REP:* `{u['rep']:,}`\n"
            f"📊 *До {next_rank}:* `[{progress_bar}] {progress}%` \n━━━━━━━━━━━━━━━━━━━━\n"
            f"🏎 *ГАРАЖ:*\n💎 Лег: `{counts['Легендарные']}` | 🟣 Эпик: `{counts['Эпические']}`\n"
            f"🔵 Редк: `{counts['Редкие']}` | ⚪ Обыч: `{counts['Обычные']}`\n━━━━━━━━━━━━━━━━━━━━\n"
            f"✨ *Всего машин:* `{len(u['garage'])}`"
        )
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_{owner_id}"))
        await callback.message.edit_caption(caption=msg, parse_mode="Markdown", reply_markup=builder.as_markup())

    elif action == "garcat": # Меню категорий гаража
        builder = InlineKeyboardBuilder()
        for r in RARITY_CONFIG:
            builder.row(types.InlineKeyboardButton(text=f"{RARITY_CONFIG[r]['emoji']} {r}", callback_data=f"garlist_{owner_id}_{r}"))
        builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_{owner_id}"))
        await callback.message.edit_caption(caption=f"🏎 *Гараж {name}*\nВыберите категорию:", parse_mode="Markdown", reply_markup=builder.as_markup())

    elif action == "garlist": # Список машин конкретной категории
        cat = data[2]
        u = users[owner_id]
        my_cars = [car for car in u['garage'] if CARS_DATABASE.get(car) == cat]
        
        txt = f"🏎 *{cat.upper()} МАШИНЫ ({name})*\n━━━━━━━━━━━━━━━━━━━━\n"
        if not my_cars:
            txt += "_Здесь пока машин нету..._"
        else:
            txt += "\n".join([f"• `{c}`" for c in my_cars])
            
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="⬅️ К категориям", callback_data=f"garcat_{owner_id}"))
        await callback.message.edit_caption(caption=txt, parse_mode="Markdown", reply_markup=builder.as_markup())

    await callback.answer()

async def btn_profile_manual(message):
    u = users[message.from_user.id]
    name = message.from_user.first_name
    next_rank, progress = get_next_rank_info(u['rep'])
    msg = f"👤 *ПРОФИЛЬ: {name}*\n🎖 *Ранг:* `{get_rank(u['rep'])}` | 🏆 *REP:* `{u['rep']:,}`\n📊 *До {next_rank}:* `{progress}%`"
    await message.answer_photo(photo=PHOTO_URL, caption=msg, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(message.from_user.id))

# --- ЗАПУСК ---
async def main():
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Главное меню"),
        types.BotCommand(command="case", description="Открыть кейс"),
        types.BotCommand(command="profile", description="Мой профиль")
    ])
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
