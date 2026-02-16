import asyncio
import os
import json
import random
import logging
from logging.handlers import TimedRotatingFileHandler
import time
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)
from dotenv import load_dotenv

from database import (
    init_db,
    add_user,
    get_user,
    update_user_profile,
    set_user_coins,
    add_coins,
    subtract_coins,
    add_common_case,
    remove_common_case,
    add_car_to_garage,
    get_user_garage,
    update_last_free_case_time,
    get_car_by_id,
    delete_car_from_garage,
    has_car_in_garage,
    get_top_users_by_coins,
    get_top_users_by_collection,
    get_group_welcome_enabled,
    set_group_welcome_enabled,
)

# =========================
# INIT
# =========================

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
BOT_ID = None
LOG_PATH = os.getenv("LOG_PATH", "bot.log")
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "1"))
FEEDBACK_CHAT_ID = int(os.getenv("FEEDBACK_CHAT_ID", "-5129896461"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        TimedRotatingFileHandler(
            LOG_PATH,
            when="midnight",
            interval=1,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
            utc=True,
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("carcase")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# =========================
# DATA
# =========================

with open("cards.json", "r", encoding="utf-8") as f:
    CARDS = json.load(f)

COMMON_CARDS = [k for k, v in CARDS.items() if v["rarity"] == "Common"]
RARE_CARDS = [k for k, v in CARDS.items() if v["rarity"] == "Rare"]
EPIC_CARDS = [k for k, v in CARDS.items() if v["rarity"] == "Epic"]
LEGENDARY_CARDS = [k for k, v in CARDS.items() if v["rarity"] == "Legendary"]
ALL_CARDS = list(CARDS.keys())

FREE_CASE_COOLDOWN = timedelta(hours=5)
GARAGE_PAGE_SIZE = 5
GROUP_CASE_RATE_LIMIT_SECONDS = int(os.getenv("GROUP_CASE_RATE_LIMIT_SECONDS", "30"))
GROUP_CASE_RATE_LIMIT = {}
FEEDBACK_PENDING = {}

FEEDBACK_CATEGORIES = [
    ("review", "Отзыв об игре"),
    ("bug", "Баг"),
    ("idea", "Идея"),
    ("improve", "Улучшение"),
    ("other", "Другое"),
]

RARITY_EMOJI = {
    "Common": "⚪",
    "Rare": "🔵",
    "Epic": "🟣",
    "Legendary": "🟡",
}

# =========================
# RARITY DRAW
# =========================

def draw_random_card(user_id):
    """Выбирает случайную машину по вероятностям редкостей (без дублей)"""
    rand = random.random()
    
    if rand < 0.70:  # 70% Common
        cards = COMMON_CARDS
    elif rand < 0.90:  # 20% Rare
        cards = RARE_CARDS
    elif rand < 0.98:  # 8% Epic
        cards = EPIC_CARDS
    else:  # 2% Legendary
        cards = LEGENDARY_CARDS
    
    return draw_card_from_lists(user_id, cards, ALL_CARDS)


def draw_card_from_lists(user_id, primary_cards, fallback_cards):
    """Выбирает машину без дублей; если в primary пусто, берет из fallback."""
    available_primary = [c for c in primary_cards if not has_car_in_garage(user_id, c)]
    if available_primary:
        return random.choice(available_primary)

    available_fallback = [c for c in fallback_cards if not has_car_in_garage(user_id, c)]
    if available_fallback:
        return random.choice(available_fallback)

    return None

# =========================
# UI HELPERS
# =========================

def header():
    return "🚗 <b>CarCase</b>\n━━━━━━━━━━━━"

def footer():
    return "━━━━━━━━━━━━"


async def edit_message_text(message: Message, text: str, reply_markup=None, parse_mode="HTML"):
    if getattr(message, "photo", None):
        try:
            await message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
            return
        except Exception:
            pass

    try:
        await message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except Exception:
        await message.answer(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )

def main_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Бесплатный кейс", callback_data="menu:free")],
            [InlineKeyboardButton(text="💳 Купить кейс", callback_data="menu:buy_cases")],
            [InlineKeyboardButton(text="🚗 Гараж", callback_data="menu:garage:0")],
            [InlineKeyboardButton(text="✍️ Отзыв", callback_data="menu:feedback")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats")],
            [InlineKeyboardButton(text="💰 Баланс", callback_data="menu:balance")],
        ]
    )

# =========================
# UTILS
# =========================

def format_timedelta(td: timedelta):
    total = int(td.total_seconds())
    h = total // 3600
    m = (total % 3600) // 60
    return f"{h} ч {m} мин"


async def is_group_admin(chat_id, user_id):
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status in ("administrator", "creator")


def format_user_label(user_id, username, first_name):
    if username:
        return f"@{username}"
    if first_name:
        return first_name
    return f"ID {user_id}"

def free_case_available(user):
    if not user["last_free_case_time"]:
        return True, None
    last = datetime.fromisoformat(user["last_free_case_time"])
    now = datetime.utcnow()
    diff = now - last
    if diff >= FREE_CASE_COOLDOWN:
        return True, None
    return False, FREE_CASE_COOLDOWN - diff


async def send_stats(target, from_callback=False):
    top_coins = get_top_users_by_coins(10)
    top_collection = get_top_users_by_collection(10)

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    coins_lines = []
    for i, row in enumerate(top_coins, start=1):
        label = format_user_label(row["user_id"], row["username"], row["first_name"])
        prefix = medals.get(i, f"{i}.")
        coins_lines.append(f"{prefix} {label} — {row['coins']} Coins")

    coll_lines = []
    total_cards = len(CARDS)
    for i, row in enumerate(top_collection, start=1):
        label = format_user_label(row["user_id"], row["username"], row["first_name"])
        prefix = medals.get(i, f"{i}.")
        coll_lines.append(f"{prefix} {label} — {row['count']} / {total_cards}")

    text = (
        f"{header()}\n\n"
        "🏆 <b>ТОП ПО COINS</b>\n"
        f"{('\\n'.join(coins_lines)) if coins_lines else 'Пусто'}\n\n"
        "🚗 <b>ТОП ПО КОЛЛЕКЦИИ</b>\n"
        f"{('\\n'.join(coll_lines)) if coll_lines else 'Пусто'}\n\n"
        f"{footer()}"
    )

    if hasattr(target, "edit_text") and from_callback:
        await edit_message_text(target, text, reply_markup=main_menu_kb())
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=main_menu_kb())


def group_case_rate_limit_ok(chat_id, user_id):
    now = time.monotonic()
    key = (chat_id, user_id)
    last = GROUP_CASE_RATE_LIMIT.get(key)
    if last is not None:
        remaining = GROUP_CASE_RATE_LIMIT_SECONDS - (now - last)
        if remaining > 0:
            return False, int(remaining)
    GROUP_CASE_RATE_LIMIT[key] = now
    return True, 0

# =========================
# START
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        add_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
    else:
        update_user_profile(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )

    await message.answer(
        f"{header()}\n\n"
        "Добро пожаловать.\n"
        "Используй меню ниже.\n\n"
        f"{footer()}",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


@dp.message(Command("stats"))
async def stats_command(message: Message):
    await send_stats(message)


@dp.callback_query(F.data == "menu:stats")
async def stats_menu(call: CallbackQuery):
    await send_stats(call.message, from_callback=True)
    await call.answer()


@dp.callback_query(F.data == "menu:feedback")
async def feedback_menu(call: CallbackQuery):
    if call.message.chat.type != "private":
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await call.answer()
        await call.message.answer(
            f"{header()}\n\n"
            "✍️ Отзывы принимаются в ЛС\n\n"
            f"<a href='{bot_link}'>Нажми сюда</a> чтобы открыть бота\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return

    kb = [
        [InlineKeyboardButton(text=label, callback_data=f"feedback:cat:{slug}")]
        for slug, label in FEEDBACK_CATEGORIES
    ]
    kb.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data="feedback:cancel"),
        InlineKeyboardButton(text="🔙 Меню", callback_data="menu:balance"),
    ])

    await call.message.edit_text(
        f"{header()}\n\n"
        "✍️ <b>Отзыв</b>\n\n"
        "Выбери категорию:\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data.startswith("feedback:cat:"))
async def feedback_category(call: CallbackQuery):
    if call.message.chat.type != "private":
        await call.answer()
        return

    slug = call.data.split(":", 2)[2]
    category = dict(FEEDBACK_CATEGORIES).get(slug, "Другое")
    FEEDBACK_PENDING[call.from_user.id] = slug

    await call.message.edit_text(
        f"{header()}\n\n"
        f"✍️ <b>Категория:</b> {category}\n\n"
        "Напиши сообщение одним текстом:\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="❌ Отмена", callback_data="feedback:cancel"),
                InlineKeyboardButton(text="🔙 Меню", callback_data="menu:balance"),
            ]]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data == "feedback:cancel")
async def feedback_cancel(call: CallbackQuery):
    FEEDBACK_PENDING.pop(call.from_user.id, None)
    await call.message.edit_text(
        f"{header()}\n\n"
        "❌ Отзыв отменен\n\n"
        f"{footer()}",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await call.answer()


@dp.message(F.chat.type == "private")
async def feedback_message(message: Message):
    if message.from_user.id not in FEEDBACK_PENDING:
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer(
            f"{header()}\n\n"
            "Напиши сообщение текстом\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return

    slug = FEEDBACK_PENDING.pop(message.from_user.id, "other")
    category = dict(FEEDBACK_CATEGORIES).get(slug, "Другое")

    sender = message.from_user
    username = f"@{sender.username}" if sender.username else "(нет username)"

    try:
        global BOT_ID
        if BOT_ID is None:
            me = await bot.get_me()
            BOT_ID = me.id

        await bot.get_chat_member(FEEDBACK_CHAT_ID, BOT_ID)
    except Exception as exc:
        logger.error(
            "feedback_chat_unavailable user_id=%s error=%s",
            sender.id,
            exc,
        )
        await message.answer(
            f"{header()}\n\n"
            "❌ Бот не добавлен в группу отзывов.\n"
            "Добавь бота в группу, чтобы отзывы доходили.\n\n"
            f"{footer()}",
            reply_markup=main_menu_kb(),
            parse_mode="HTML",
        )
        return

    try:
        await bot.send_message(
            FEEDBACK_CHAT_ID,
            f"📬 <b>Новый отзыв</b>\n\n"
            f"👤 <b>Пользователь:</b> {sender.full_name}\n"
            f"🔗 <b>Username:</b> {username}\n"
            f"🆔 <b>ID:</b> {sender.id}\n"
            f"🏷️ <b>Категория:</b> {category}\n\n"
            f"💬 <b>Сообщение:</b>\n{text}",
            parse_mode="HTML",
        )
        await message.answer(
            f"{header()}\n\n"
            "✅ Спасибо! Отзыв отправлен.\n\n"
            f"{footer()}",
            reply_markup=main_menu_kb(),
            parse_mode="HTML",
        )
        logger.info(
            "feedback_sent user_id=%s category=%s chat_id=%s",
            sender.id,
            slug,
            FEEDBACK_CHAT_ID,
        )
    except Exception as exc:
        logger.error(
            "feedback_send_failed user_id=%s error=%s",
            sender.id,
            exc,
        )
        await message.answer(
            f"{header()}\n\n"
            "❌ Не удалось отправить отзыв. Попробуй позже.\n\n"
            f"{footer()}",
            reply_markup=main_menu_kb(),
            parse_mode="HTML",
        )

# =========================
# BALANCE
# =========================

@dp.callback_query(F.data == "menu:balance")
async def balance(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Пользователь не найден, используй /start", show_alert=True)
        return
    await edit_message_text(
        call.message,
        f"{header()}\n\n"
        f"💰 <b>Coins:</b> {user['coins']}\n\n"
        f"{footer()}",
        reply_markup=main_menu_kb(),
    )
    await call.answer()

# =========================
# BUY CASES
# =========================

@dp.callback_query(F.data == "menu:buy_cases")
async def buy_cases_menu(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Пользователь не найден, используй /start", show_alert=True)
        return
    
    # Цены случаев (на основе средних цен машин)
    cases = {
        "standard": {
            "name": "Стандартный",
            "price": 500,
            "desc": "70% Common, 20% Rare, 8% Epic, 2% Leg"
        },
        "premium": {
            "name": "Премиум",
            "price": 1500,
            "desc": "70% Rare, 25% Epic, 5% Legendary"
        },
        "luxury": {
            "name": "Люкс",
            "price": 4000,
            "desc": "70% Epic, 30% Legendary"
        }
    }

    kb = []
    for case_type, info in cases.items():
        affordability = "✅" if user["coins"] >= info["price"] else "❌"
        kb.append([
            InlineKeyboardButton(
                text=f"{affordability} {info['name']} - {info['price']} 💰",
                callback_data=f"buy_case:{case_type}"
            )
        ])

    kb.append([InlineKeyboardButton(text="🔙 Меню", callback_data="menu:balance")])

    await edit_message_text(
        call.message,
        f"{header()}\n\n"
        "<b>💳 Магазин кейсов</b>\n\n"
        f"💰 <b>У вас:</b> {user['coins']} Coins\n\n"
        "✅ = можно купить\n"
        "❌ = недостаточно Coins\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("buy_case:"))
async def buy_case(call: CallbackQuery):
    case_type = call.data.split(":")[1]
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Пользователь не найден, используй /start", show_alert=True)
        return

    cases = {
        "standard": {
            "name": "Стандартный",
            "price": 500,
            "rarity_dist": [(0.70, "Common"), (0.90, "Rare"), (0.98, "Epic"), (1.0, "Legendary")]
        },
        "premium": {
            "name": "Премиум",
            "price": 1500,
            "rarity_dist": [(0.70, "Rare"), (0.95, "Epic"), (1.0, "Legendary")]
        },
        "luxury": {
            "name": "Люкс",
            "price": 4000,
            "rarity_dist": [(0.70, "Epic"), (1.0, "Legendary")]
        }
    }

    if case_type not in cases:
        await call.answer("❌ Неизвестный кейс", show_alert=True)
        return

    case_info = cases[case_type]

    if user["coins"] < case_info["price"]:
        await call.answer("❌ Недостаточно Coins!", show_alert=True)
        return

    # Выбираем машину по распределению рарити специфичному для этого кейса
    rand = random.random()
    rarity = "Common"
    for threshold, r in case_info["rarity_dist"]:
        if rand < threshold:
            rarity = r
            break

    # Выбираем машину из этой рарити (без дублей)
    case_cards = COMMON_CARDS + RARE_CARDS + EPIC_CARDS + LEGENDARY_CARDS
    if rarity == "Common":
        card_id = draw_card_from_lists(call.from_user.id, COMMON_CARDS, case_cards)
    elif rarity == "Rare":
        card_id = draw_card_from_lists(call.from_user.id, RARE_CARDS, case_cards)
    elif rarity == "Epic":
        card_id = draw_card_from_lists(call.from_user.id, EPIC_CARDS, case_cards)
    else:  # Legendary
        card_id = draw_card_from_lists(call.from_user.id, LEGENDARY_CARDS, case_cards)
    
    if card_id is None:
        await call.answer("❌ Все машины этого кейса уже в твоём гараже!", show_alert=True)
        logger.info(
            "buy_case_no_cards user_id=%s case=%s",
            call.from_user.id,
            case_type,
        )
        return
    
    # Вычитаем Coins только если машина доступна
    subtract_coins(call.from_user.id, case_info["price"])

    card = CARDS[card_id]
    rarity = card["rarity"]
    
    # Добавляем машину в гараж
    add_car_to_garage(call.from_user.id, card_id, rarity)
    logger.info(
        "buy_case_opened user_id=%s case=%s card_id=%s rarity=%s price=%s",
        call.from_user.id,
        case_type,
        card_id,
        rarity,
        case_info["price"],
    )

    emoji = RARITY_EMOJI.get(rarity, "❓")
    image_path = card["image"]
    if image_path and not image_path.startswith("/") and not image_path.startswith("."):
        image_path = f"./common/{image_path.split('/')[-1]}"
    
    try:
        if image_path:
            image = FSInputFile(image_path)
            await call.message.answer_photo(
                image,
                caption=(
                    f"{header()}\n\n"
                    f"🎉 <b>ОТКРЫТ {case_info['name'].upper()} КЕЙС</b>\n\n"
                    f"🚘 <b>{card['name_ru']}</b>\n"
                    f"Редкость: {emoji} {rarity}\n\n"
                    f"{footer()}"
                ),
                parse_mode="HTML",
            )
    except (FileNotFoundError, OSError):
        logger.warning(
            "image_missing context=buy_case user_id=%s card_id=%s image_path=%s",
            call.from_user.id,
            card_id,
            image_path,
        )
        await call.message.answer(
            f"{header()}\n\n"
            f"🎉 <b>ОТКРЫТ {case_info['name'].upper()} КЕЙС</b>\n\n"
            f"🚘 <b>{card['name_ru']}</b>\n"
            f"Редкость: {emoji} {rarity}\n"
            f"📸 <i>Фото на стадии разработки</i>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
    else:
        if not image_path:
            await call.message.answer(
                f"{header()}\n\n"
                f"🎉 <b>ОТКРЫТ {case_info['name'].upper()} КЕЙС</b>\n\n"
                f"🚘 <b>{card['name_ru']}</b>\n"
                f"Редкость: {emoji} {rarity}\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )

    await call.answer()

# =========================
# FREE CASE
# =========================

@dp.callback_query(F.data == "menu:free")
async def free_case(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Пользователь не найден, используй /start", show_alert=True)
        return
    available, remaining = free_case_available(user)

    if not available:
        await edit_message_text(
            call.message,
            f"{header()}\n\n"
            "⏳ Бесплатный кейс недоступен\n\n"
            f"Осталось: {format_timedelta(remaining)}\n\n"
            f"{footer()}",
        )
        await call.answer()
        return

    card_id = draw_random_card(call.from_user.id)
    
    if card_id is None:
        update_last_free_case_time(user["user_id"])
        logger.info(
            "free_case_no_cards user_id=%s",
            call.from_user.id,
        )
        await edit_message_text(
            call.message,
            f"{header()}\n\n"
            "🎯 <b>Коллекция полна!</b>\n\n"
            "Ты собрал все машины!\n\n"
            f"{footer()}",
        )
        await call.answer()
        return
    
    card = CARDS.get(card_id)
    if not card:
        await call.answer("❌ Машина не найдена в каталоге!", show_alert=True)
        return
    rarity = card["rarity"]

    add_car_to_garage(user["user_id"], card_id, rarity)
    add_coins(user["user_id"], 100)  # Бонус за бесплатный кейс
    update_last_free_case_time(user["user_id"])
    logger.info(
        "free_case_opened user_id=%s card_id=%s rarity=%s bonus=100",
        call.from_user.id,
        card_id,
        rarity,
    )

    image_path = card["image"]
    if image_path and not image_path.startswith("/") and not image_path.startswith("."):
        image_path = f"./common/{image_path.split('/')[-1]}"
    
    try:
        if image_path:
            image = FSInputFile(image_path)
            await call.message.answer_photo(
                image,
                caption=(
                    f"{header()}\n\n"
                    "🎁 <b>БЕСПЛАТНЫЙ КЕЙС</b>\n\n"
                    f"🚘 <b>{card['name_ru']}</b>\n"
                    f"Редкость: {RARITY_EMOJI[rarity]} {rarity}\n"
                    f"💰 <b>Бонус:</b> +100 Coins\n\n"
                    f"{footer()}"
                ),
                parse_mode="HTML",
            )
    except (FileNotFoundError, OSError):
        logger.warning(
            "image_missing context=free_case user_id=%s card_id=%s image_path=%s",
            call.from_user.id,
            card_id,
            image_path,
        )
        await call.message.answer(
            f"{header()}\n\n"
            "🎁 <b>БЕСПЛАТНЫЙ КЕЙС</b>\n\n"
            f"🚘 <b>{card['name_ru']}</b>\n"
            f"Редкость: {RARITY_EMOJI[rarity]} {rarity}\n"
            f"📸 <i>Фото на стадии разработки</i>\n"
            f"💰 <b>Бонус:</b> +100 Coins\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
    else:
        if not image_path:
            await call.message.answer(
                f"{header()}\n\n"
                "🎁 <b>БЕСПЛАТНЫЙ КЕЙС</b>\n\n"
                f"🚘 <b>{card['name_ru']}</b>\n"
                f"Редкость: {RARITY_EMOJI[rarity]} {rarity}\n"
                f"💰 <b>Бонус:</b> +100 Coins\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
    await call.answer()

# =========================
# GARAGE (PAGINATION)
# =========================

@dp.callback_query(F.data.startswith("menu:garage"))
async def garage(call: CallbackQuery):
    page = int(call.data.split(":")[2])
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Пользователь не найден, используй /start", show_alert=True)
        return
    cars = get_user_garage(user["user_id"])

    if not cars:
        await edit_message_text(
            call.message,
            f"{header()}\n\n🚗 Гараж пуст\n\n{footer()}",
            reply_markup=main_menu_kb(),
        )
        await call.answer()
        return

    start = page * GARAGE_PAGE_SIZE
    end = start + GARAGE_PAGE_SIZE
    chunk = cars[start:end]

    kb = []
    for car in chunk:
        card = CARDS.get(car["name"])
        emoji = RARITY_EMOJI.get(car["rarity"], "❓")
        display_name = card["name_ru"] if card else f"{car['name']} (нет в каталоге)"
        kb.append([
            InlineKeyboardButton(
                text=f"{emoji} {display_name}",
                callback_data=f"car:view:{car['id']}"
            )
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"menu:garage:{page-1}"))
    if end < len(cars):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"menu:garage:{page+1}"))

    if nav:
        kb.append(nav)

    kb.append([InlineKeyboardButton(text="🔙 Меню", callback_data="menu:balance")])

    await edit_message_text(
        call.message,
        f"{header()}\n\n🚗 <b>Твой гараж</b>\n\n{footer()}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
    )
    await call.answer()


# =========================
# CAR VIEW
# =========================

@dp.callback_query(F.data.startswith("car:view"))
async def car_view(call: CallbackQuery):
    car_id = int(call.data.split(":")[2])
    car = get_car_by_id(car_id)

    if not car:
        await call.answer("🚗 Машина не найдена", show_alert=True)
        logger.info(
            "car_view_not_found user_id=%s car_id=%s",
            call.from_user.id,
            car_id,
        )
        return
    if car["user_id"] != call.from_user.id:
        await call.answer("⛔ Это не твоя кнопка", show_alert=True)
        logger.info(
            "car_view_forbidden user_id=%s owner_id=%s car_id=%s",
            call.from_user.id,
            car["user_id"],
            car_id,
        )
        return

    card = CARDS.get(car["name"])
    if not card:
        card = {
            "name_ru": car["name"],
            "image": "",
            "sell_price": 0,
        }
    emoji = RARITY_EMOJI.get(car["rarity"], "❓")
    sell_price = card.get("sell_price", 0)

    image_path = card["image"]
    if image_path and not image_path.startswith("/") and not image_path.startswith("."):
        image_path = f"./common/{image_path.split('/')[-1]}"
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"💵 Продать за {sell_price} 💰 Coins", callback_data=f"sell:{car_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:garage:0")]
        ]
    )
    
    try:
        if image_path:
            image = FSInputFile(image_path)
            await call.message.answer_photo(
                image,
                caption=(
                    f"{header()}\n\n"
                    f"🚘 <b>{card['name_ru']}</b>\n"
                    f"Редкость: {emoji} {car['rarity']}\n"
                    f"💰 <b>Продать за:</b> {sell_price} Coins\n\n"
                    f"{footer()}"
                ),
                parse_mode="HTML",
                reply_markup=kb
            )
    except (FileNotFoundError, OSError):
        logger.warning(
            "image_missing context=car_view user_id=%s card_name=%s image_path=%s",
            call.from_user.id,
            car.get("name"),
            image_path,
        )
        await call.message.answer(
            f"{header()}\n\n"
            f"🚘 <b>{card['name_ru']}</b>\n"
            f"Редкость: {emoji} {car['rarity']}\n"
            f"💰 <b>Продать за:</b> {sell_price} Coins\n"
            f"📸 <i>Фото на стадии разработки</i>\n\n"
            f"{footer()}",
            parse_mode="HTML",
            reply_markup=kb
        )
    else:
        if not image_path:
            await call.message.answer(
                f"{header()}\n\n"
                f"🚘 <b>{card['name_ru']}</b>\n"
                f"Редкость: {emoji} {car['rarity']}\n"
                f"💰 <b>Продать за:</b> {sell_price} Coins\n\n"
                f"{footer()}",
                parse_mode="HTML",
                reply_markup=kb
            )
    await call.answer()


# =========================
# SELL CAR
# =========================

@dp.callback_query(F.data.startswith("sell:"))
async def sell_car(call: CallbackQuery):
    car_id = int(call.data.split(":")[1])
    car = get_car_by_id(car_id)

    if not car:
        await call.answer("🚗 Машина не найдена", show_alert=True)
        logger.info(
            "sell_not_found user_id=%s car_id=%s",
            call.from_user.id,
            car_id,
        )
        return
    if car["user_id"] != call.from_user.id:
        await call.answer("⛔ Это не твоя кнопка", show_alert=True)
        logger.info(
            "sell_forbidden user_id=%s owner_id=%s car_id=%s",
            call.from_user.id,
            car["user_id"],
            car_id,
        )
        return

    card = CARDS.get(car["name"])
    if not card:
        card = {
            "name_ru": car["name"],
            "sell_price": 0,
        }
    sell_price = card.get("sell_price", 0)

    # Продаём машину
    delete_car_from_garage(car_id)
    add_coins(call.from_user.id, sell_price)
    logger.info(
        "sell_completed user_id=%s car_id=%s card_name=%s price=%s",
        call.from_user.id,
        car_id,
        car.get("name"),
        sell_price,
    )

    await edit_message_text(
        call.message,
        f"{header()}\n\n"
        f"✅ <b>Машина продана!</b>\n\n"
        f"🚘 {card['name_ru']}\n"
        f"💰 <b>Получено:</b> +{sell_price} Coins\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 К гаражу", callback_data="menu:garage:0")]]
        ),
    )
    await call.answer("✅ Машина продана!", show_alert=True)

# =========================
# GROUP COMMANDS (SAFE)
# =========================

@dp.message(F.chat.type != "private", F.new_chat_members)
async def group_welcome(message: Message):
    if not get_group_welcome_enabled(message.chat.id):
        return

    bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
    title = message.chat.title or "группу"

    for member in message.new_chat_members:
        if member.is_bot:
            continue
        await message.answer(
            f"{header()}\n\n"
            f"👋 Добро пожаловать, <b>{member.first_name}</b> в <b>{title}</b>!\n\n"
            "Чтобы начать, зарегистрируйся в ЛС бота.\n\n"
            f"<a href='{bot_link}'>Нажми сюда</a> чтобы открыть бота\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )


@dp.message(F.chat.type != "private", Command("welcome"))
async def welcome_settings(message: Message):
    if not await is_group_admin(message.chat.id, message.from_user.id):
        await message.answer("⛔ Только админы могут менять приветствие")
        return

    enabled = get_group_welcome_enabled(message.chat.id)
    status = "✅ Включено" if enabled else "❌ Выключено"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Включить", callback_data="welcome:on"),
                InlineKeyboardButton(text="❌ Выключить", callback_data="welcome:off"),
            ]
        ]
    )
    await message.answer(
        f"{header()}\n\n"
        f"👋 <b>Приветствие:</b> {status}\n\n"
        f"{footer()}",
        reply_markup=kb,
        parse_mode="HTML",
    )

@dp.message(F.chat.type != "private", Command("garage"))
async def garage_group(message: Message):
    await message.answer(
        f"{header()}\n\n"
        "🚗 Гараж доступен в личных сообщениях с ботом\n\n"
        f"{footer()}",
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("welcome:"))
async def welcome_toggle(call: CallbackQuery):
    if call.message.chat.type == "private":
        await call.answer("❌ Эта кнопка работает только в группах", show_alert=True)
        return
    if not await is_group_admin(call.message.chat.id, call.from_user.id):
        await call.answer("⛔ Только админы могут менять приветствие", show_alert=True)
        return

    enabled = call.data.split(":", 1)[1] == "on"
    set_group_welcome_enabled(call.message.chat.id, enabled)
    status = "✅ Включено" if enabled else "❌ Выключено"

    await edit_message_text(
        call.message,
        f"{header()}\n\n"
        f"👋 <b>Приветствие:</b> {status}\n\n"
        f"{footer()}",
        reply_markup=call.message.reply_markup,
    )
    await call.answer("✅ Готово")


@dp.message(F.chat.type != "private", F.text.lower().regexp(r"(баланс|balance|coins)"))
async def balance_group(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await message.answer(
            f"{header()}\n\n"
            f"👤 {message.from_user.first_name}, сначала зарегистрируйся!\n\n"
            f"<a href='{bot_link}'>Нажми сюда</a> чтобы открыть бота в ЛС\n\n"
            f"{footer()}",
            parse_mode="HTML"
        )
        logger.info(
            "group_balance_unregistered user_id=%s chat_id=%s",
            message.from_user.id,
            message.chat.id,
        )
        return

    await message.answer(
        f"{header()}\n\n"
        f"💰 {message.from_user.first_name}, твой баланс: {user['coins']} Coins\n\n"
        f"{footer()}",
        parse_mode="HTML",
    )
    logger.info(
        "group_balance_shown user_id=%s chat_id=%s coins=%s",
        message.from_user.id,
        message.chat.id,
        user["coins"],
    )


# =========================
# GROUP TEXT TRIGGERS
# =========================

@dp.message(F.chat.type != "private", F.text.lower().regexp(r"(кейс|case|открыть|open)"))
async def group_text_trigger(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await message.answer(
            f"{header()}\n\n"
            f"👤 {message.from_user.first_name}, сначала зарегистрируйся!\n\n"
            f"<a href='{bot_link}'>Нажми сюда</a> чтобы открыть бота в ЛС\n\n"
            f"{footer()}",
            parse_mode="HTML"
        )
        logger.info(
            "group_case_unregistered user_id=%s chat_id=%s",
            message.from_user.id,
            message.chat.id,
        )
        return

    ok, remaining = group_case_rate_limit_ok(message.chat.id, message.from_user.id)
    if not ok:
        await message.answer(
            f"{header()}\n\n"
            f"⏳ {message.from_user.first_name}, не так часто!\n\n"
            f"Подожди: {remaining} сек\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        logger.info(
            "group_case_rate_limited user_id=%s chat_id=%s remaining=%s",
            message.from_user.id,
            message.chat.id,
            remaining,
        )
        return

    available, remaining = free_case_available(user)

    if not available:
        await message.answer(
            f"{header()}\n\n"
            f"⏳ {message.from_user.first_name}, бесплатный кейс недоступен\n\n"
            f"Осталось: {format_timedelta(remaining)}\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        logger.info(
            "group_case_cooldown user_id=%s chat_id=%s remaining=%s",
            message.from_user.id,
            message.chat.id,
            format_timedelta(remaining),
        )
        return

    card_id = draw_random_card(message.from_user.id)
    
    if card_id is None:
        await message.answer(
            f"{header()}\n\n"
            f"🎯 {message.from_user.first_name}, коллекция полна!\n\n"
            "Ты собрал все машины этой редкости!\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        logger.info(
            "group_case_no_cards user_id=%s chat_id=%s",
            message.from_user.id,
            message.chat.id,
        )
        return
    
    card = CARDS[card_id]
    rarity = card["rarity"]

    add_car_to_garage(user["user_id"], card_id, rarity)
    add_coins(user["user_id"], 100)  # Бонус за бесплатный кейс
    update_last_free_case_time(user["user_id"])
    logger.info(
        "group_case_opened user_id=%s chat_id=%s card_id=%s rarity=%s bonus=100",
        message.from_user.id,
        message.chat.id,
        card_id,
        rarity,
    )

    image_path = card["image"]
    if image_path and not image_path.startswith("/") and not image_path.startswith("."):
        image_path = f"./common/{image_path.split('/')[-1]}"
    
    try:
        if image_path:
            image = FSInputFile(image_path)
            await message.answer_photo(
                image,
                caption=(
                    f"{header()}\n\n"
                    f"🎁 <b>КЕЙС {message.from_user.first_name}</b>\n\n"
                    f"🚘 <b>{card['name_ru']}</b>\n"
                    f"Редкость: {RARITY_EMOJI[rarity]} {rarity}\n"
                    f"💰 <b>Бонус:</b> +100 Coins\n\n"
                    f"{footer()}"
                ),
                parse_mode="HTML",
            )
    except (FileNotFoundError, OSError):
        logger.warning(
            "image_missing context=group_case user_id=%s card_id=%s image_path=%s",
            message.from_user.id,
            card_id,
            image_path,
        )
        await message.answer(
            f"{header()}\n\n"
            f"🎁 <b>КЕЙС {message.from_user.first_name}</b>\n\n"
            f"🚘 <b>{card['name_ru']}</b>\n"
            f"Редкость: {RARITY_EMOJI[rarity]} {rarity}\n"
            f"📸 <i>Фото на стадии разработки</i>\n"
            f"💰 <b>Бонус:</b> +100 Coins\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
    else:
        if not image_path:
            await message.answer(
                f"{header()}\n\n"
                f"🎁 <b>КЕЙС {message.from_user.first_name}</b>\n\n"
                f"🚘 <b>{card['name_ru']}</b>\n"
                f"Редкость: {RARITY_EMOJI[rarity]} {rarity}\n"
                f"💰 <b>Бонус:</b> +100 Coins\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )

# =========================
# RUN
# =========================

async def main():
    init_db()
    global BOT_USERNAME
    global BOT_ID
    if not BOT_USERNAME:
        me = await bot.get_me()
        BOT_USERNAME = me.username
        BOT_ID = me.id
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())