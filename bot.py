import asyncio
import os
import json
import random
import logging
from logging.handlers import TimedRotatingFileHandler
import time
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
    ChatMemberUpdated,
    BotCommand,
    BotCommandScopeAllGroupChats,
)
from dotenv import load_dotenv

from database import (
    init_db,
    add_user,
    get_user,
    get_user_rarity_counts,
    update_user_profile,
    set_user_coins,
    add_coins,
    subtract_coins,
    increment_total_cases_opened,
    add_common_case,
    remove_common_case,
    add_car_to_garage,
    get_user_garage,
    update_last_case_time,
    update_last_free_case_time,
    get_car_by_id,
    delete_car_from_garage,
    has_car_in_garage,
    get_top_users_by_coins,
    get_top_users_by_collection,
    get_group_welcome_enabled,
    set_group_welcome_enabled,
    ensure_daily_task_row,
    get_daily_tasks_progress,
    get_daily_sold_count,
    increment_daily_sold_count,
    add_daily_task_progress,
    mark_daily_task_rewarded,
    set_last_daily_notify_day,
    set_user_streak,
    increment_weekly_cases_opened,
    get_top_users_by_weekly_cases,
    increment_weekly_group_cases_opened,
    get_top_users_by_group_weekly_cases,
    has_group_week_rewarded,
    mark_group_week_rewarded,
    has_global_week_rewarded,
    mark_global_week_rewarded,
    has_user_seen_global_week,
    mark_user_seen_global_week,
    get_all_user_ids,
    get_all_group_chat_ids,
    get_admin_summary_stats,
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
FEEDBACK_CHAT_ID = int(os.getenv("FEEDBACK_CHAT_ID", "-1003802493555"))
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "5658493362"))

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

FREE_CASE_COOLDOWN = timedelta(hours=4)
PAID_CASE_COOLDOWN = timedelta(seconds=int(os.getenv("PAID_CASE_COOLDOWN_SECONDS", "120")))
FREE_CASE_BONUS_COINS = int(os.getenv("FREE_CASE_BONUS_COINS", "0"))
DAILY_SELL_LIMIT = int(os.getenv("DAILY_SELL_LIMIT", "5"))
GARAGE_PAGE_SIZE = 5
GROUP_CASE_RATE_LIMIT_SECONDS = int(os.getenv("GROUP_CASE_RATE_LIMIT_SECONDS", "30"))
GROUP_CASE_RATE_LIMIT = {}
FEEDBACK_PENDING = {}
ADMIN_BROADCAST_PENDING = {}
LAST_CAR_VIEW_MESSAGE_IDS = {}  # user_id -> (sticker_id, main_message_id)
GARAGE_MESSAGE_ID = {}  # user_id -> message_id сообщения гаража для редактирования
LAST_STICKER_MESSAGE_ID = {}  # user_id -> message_id последнего стикера

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

RARITY_RU = {
    "Common": "Обычная",
    "Rare": "Редкая",
    "Epic": "Эпическая",
    "Legendary": "Легендарная",
}

SELL_PRICE_MULTIPLIER = {
    "Common": 0.45,
    "Rare": 0.50,
    "Epic": 0.06,
    "Legendary": 0.04,
}

SELL_PRICE_BOUNDS = {
    "Common": (2500, 12000),
    "Rare": (13000, 28000),
    "Epic": (30000, 90000),
    "Legendary": (100000, 260000),
}

DAILY_TASKS = {
    "free_case": {"title": "Открыть бесплатный кейс", "target": 1, "reward": 3000},
    "buy_standard": {"title": "Купить платный кейс", "target": 1, "reward": 5000},
    "sell_car": {"title": "Продать машину", "target": 1, "reward": 4000},
    "get_rare_plus": {"title": "Получить машину редкости Редкая и выше", "target": 1, "reward": 7000},
}

STREAK_REWARDS = {
    1: 2000,
    2: 3000,
    3: 4000,
    4: 5000,
    5: 7000,
    6: 9000,
    7: 12000,
}

GROUP_WEEKLY_REWARDS = [50000, 30000, 20000]
GLOBAL_WEEKLY_REWARDS = [100000, 70000, 50000]

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


def draw_free_case_card(user_id):
    """Бесплатный кейс: только Common/Rare/Epic (без Legendary)."""
    rand = random.random()

    if rand < 0.70:  # 70% Common
        cards = COMMON_CARDS
    elif rand < 0.90:  # 20% Rare
        cards = RARE_CARDS
    else:  # 10% Epic
        cards = EPIC_CARDS

    fallback_cards = COMMON_CARDS + RARE_CARDS + EPIC_CARDS
    return draw_card_from_lists(user_id, cards, fallback_cards)


def draw_card_from_lists(user_id, primary_cards, fallback_cards):
    """Выбирает машину без дублей; если в primary пусто, берет из fallback."""
    available_primary = [c for c in primary_cards if not has_car_in_garage(user_id, c)]
    if available_primary:
        return draw_weighted_card_by_price(available_primary)

    available_fallback = [c for c in fallback_cards if not has_car_in_garage(user_id, c)]
    if available_fallback:
        return draw_weighted_card_by_price(available_fallback)

    return None


def draw_weighted_card_by_price(card_ids):
    """Чем дороже машина, тем ниже шанс выпадения; чем дешевле, тем выше."""
    if not card_ids:
        return None

    # Для небольшого пула делаем равномерный шанс,
    # чтобы не затягивать добор последних машин.
    if len(card_ids) <= 8:
        return random.choice(card_ids)

    prices = []
    weights = []
    for card_id in card_ids:
        card = CARDS.get(card_id, {})
        rarity = card.get("rarity", "Common")
        effective_price = max(1, get_effective_sell_price(card, rarity_override=rarity))

        prices.append(effective_price)

    min_price = min(prices)
    max_price = max(prices)

    for effective_price in prices:
        if max_price == min_price:
            weights.append(1.0)
            continue

        # Мягкий перекос: дорогие машины реже, но не слишком.
        # Самая дорогая в пуле получает ~70% веса самой дешёвой.
        normalized = (effective_price - min_price) / (max_price - min_price)
        weight = 1.0 - (0.30 * normalized)
        weights.append(weight)

    return random.choices(card_ids, weights=weights, k=1)[0]

# =========================
# UI HELPERS
# =========================

def header():
    return "🚗 <b>CarCase</b>\n━━━━━━━━━━━━"

def footer():
    return "━━━━━━━━━━━━"


async def delete_message_safe(message: Message):
    try:
        await message.delete()
    except Exception:
        pass


async def edit_message_text(
    message: Message,
    text: str,
    reply_markup=None,
    parse_mode="HTML",
    replace_photo: bool = False,
):
    """Edit message text intelligently based on message type."""
    
    # Проверяем есть ли фото
    has_photo = getattr(message, "photo", None) is not None
    
    # Если есть фото и replace_photo=True, удаляем старое и отправляем новое
    if has_photo and replace_photo:
        try:
            await delete_message_safe(message)
        except Exception as e:
            logger.debug("Failed to delete message: %s", e)
        
        try:
            await message.answer(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        except Exception as e:
            logger.error("Failed to answer with new message: %s", e)
        return
    
    # Если есть фото и replace_photo=False, пробуем отредактировать caption
    if has_photo and not replace_photo:
        try:
            await message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
            return
        except Exception as e:
            logger.debug("edit_caption failed: %s", e)
            # Fallback: удаляем и отправляем новое
            try:
                await delete_message_safe(message)
                await message.answer(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                )
            except Exception as fallback_error:
                logger.error("Fallback answer failed: %s", fallback_error)
            return
    
    # Для текстовых сообщений - редактируем
    try:
        await message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        logger.debug("Message edited successfully")
    except Exception as e:
        logger.error("edit_text failed, message might be too old or deleted: %s", e)

def is_owner(user_id: int) -> bool:
    return user_id == ADMIN_USER_ID


def main_menu_kb(user_id: int = None):
    kb = [
        [InlineKeyboardButton(text="🎁 Бесплатный кейс", callback_data="menu:free")],
        [InlineKeyboardButton(text="💳 Купить кейс", callback_data="menu:buy_cases")],
        [InlineKeyboardButton(text="📅 Ежедневные задания", callback_data="menu:daily")],
        [InlineKeyboardButton(text="🚗 Гараж", callback_data="menu:garage:0")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile")],
        [InlineKeyboardButton(text="✍️ Отзыв", callback_data="menu:feedback")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats")],
        [InlineKeyboardButton(text="💰 Баланс", callback_data="menu:balance")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
    ]

    if user_id is not None and is_owner(user_id):
        kb.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="menu:admin")])

    return InlineKeyboardMarkup(inline_keyboard=kb)

# =========================
# UTILS
# =========================

def format_timedelta(td: timedelta):
    total = int(td.total_seconds())
    h = total // 3600
    m = (total % 3600) // 60
    return f"{h} ч {m} мин"


def current_day_key():
    return datetime.utcnow().date().isoformat()


def current_week_key():
    iso = datetime.utcnow().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def previous_week_key():
    prev = datetime.utcnow() - timedelta(days=7)
    iso = prev.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def get_streak_reward(streak_day: int):
    return STREAK_REWARDS.get(min(streak_day, 7), STREAK_REWARDS[7])


def ensure_daily_tasks_initialized(user_id, day_key):
    for task_key in DAILY_TASKS:
        ensure_daily_task_row(user_id, day_key, task_key)


async def maybe_notify_daily_available(target: Message, user):
    day_key = current_day_key()
    if user.get("last_daily_notify_day") == day_key:
        return

    ensure_daily_tasks_initialized(user["user_id"], day_key)
    set_last_daily_notify_day(user["user_id"], day_key)

    await target.answer(
        f"{header()}\n\n"
        "📅 <b>Ежедневные задания доступны!</b>\n\n"
        "Зайди в меню <b>Ежедневные задания</b> и получи награды 💰\n\n"
        f"{footer()}",
        parse_mode="HTML",
    )


async def maybe_apply_streak_bonus(target: Message, user):
    today = current_day_key()
    last_claim_day = user.get("streak_last_claim_day")

    if last_claim_day == today:
        return

    yesterday = (datetime.utcnow().date() - timedelta(days=1)).isoformat()
    current_streak = int(user.get("streak_current") or 0)
    best_streak = int(user.get("streak_best") or 0)

    if last_claim_day == yesterday:
        current_streak += 1
    else:
        current_streak = 1

    best_streak = max(best_streak, current_streak)
    reward = get_streak_reward(current_streak)

    set_user_streak(user["user_id"], current_streak, best_streak, today)
    add_coins(user["user_id"], reward)

    await target.answer(
        f"{header()}\n\n"
        "🔥 <b>Ежедневный вход!</b>\n\n"
        f"Серия: <b>{current_streak}</b> дн.\n"
        f"🎁 Награда: +{reward} Coins\n"
        f"🏆 Лучший стрик: {best_streak} дн.\n\n"
        f"{footer()}",
        parse_mode="HTML",
    )


async def process_group_weekly_rewards(chat_id: int):
    prev_week = previous_week_key()
    if has_group_week_rewarded(chat_id, prev_week):
        return

    top = get_top_users_by_group_weekly_cases(chat_id, prev_week, 3)
    if not top:
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, row in enumerate(top):
        reward = GROUP_WEEKLY_REWARDS[i]
        add_coins(row["user_id"], reward)
        lines.append(
            f"{medals[i]} <b>{row['first_name'] or 'Игрок'}</b> — {row['cases_opened']} кейсов (+{reward} Coins)"
        )

    mark_group_week_rewarded(chat_id, prev_week)
    award_time = datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")

    msg = await bot.send_message(
        chat_id,
        f"{header()}\n\n"
        f"🏁 <b>ИТОГИ НЕДЕЛИ В ГРУППЕ</b>\n<code>{prev_week}</code>\n\n"
        f"{chr(10).join(lines)}\n\n"
        f"✅ Награды начислены: <b>{award_time}</b>\n\n"
        f"{footer()}",
        parse_mode="HTML",
    )
    try:
        await bot.pin_chat_message(chat_id, msg.message_id, disable_notification=True)
    except Exception:
        pass


async def process_global_weekly_rewards_once():
    prev_week = previous_week_key()
    if has_global_week_rewarded(prev_week):
        return

    top = get_top_users_by_weekly_cases(prev_week, 3)
    if not top:
        return

    for i, row in enumerate(top):
        add_coins(row["user_id"], GLOBAL_WEEKLY_REWARDS[i])

    mark_global_week_rewarded(prev_week)

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, row in enumerate(top):
        reward = GLOBAL_WEEKLY_REWARDS[i]
        lines.append(
            f"{medals[i]} <b>{row['first_name'] or 'Игрок'}</b> — {row['cases_opened']} кейсов (+{reward} Coins)"
        )

    text = (
        f"{header()}\n\n"
        f"🌍 <b>ИТОГИ ОБЩЕГО ТОПА НЕДЕЛИ</b>\n<code>{prev_week}</code>\n\n"
        f"{chr(10).join(lines)}\n\n"
        f"✅ Награды начислены: <b>{datetime.utcnow().strftime('%d.%m.%Y %H:%M UTC')}</b>\n\n"
        f"{footer()}"
    )

    for uid in get_all_user_ids():
        if has_user_seen_global_week(uid, prev_week):
            continue
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            mark_user_seen_global_week(uid, prev_week)
        except Exception:
            continue


async def maybe_notify_global_weekly_results(target: Message, user_id: int):
    prev_week = previous_week_key()
    if not has_global_week_rewarded(prev_week):
        return
    if has_user_seen_global_week(user_id, prev_week):
        return

    top = get_top_users_by_weekly_cases(prev_week, 3)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, row in enumerate(top):
        reward = GLOBAL_WEEKLY_REWARDS[i]
        lines.append(
            f"{medals[i]} <b>{row['first_name'] or 'Игрок'}</b> — {row['cases_opened']} кейсов (+{reward} Coins)"
        )

    text = (
        f"{header()}\n\n"
        f"🌍 <b>ИТОГИ ОБЩЕГО ТОПА НЕДЕЛИ</b>\n<code>{prev_week}</code>\n\n"
        f"{chr(10).join(lines) if lines else 'На прошлой неделе победителей не было.'}\n"
        f"✅ Дата начисления: <b>{datetime.utcnow().strftime('%d.%m.%Y %H:%M UTC')}</b>\n\n"
        f"{footer()}"
    )

    await target.answer(text, parse_mode="HTML")
    mark_user_seen_global_week(user_id, prev_week)


async def apply_daily_task_progress(user_id: int, task_key: str, amount: int = 1, notify_message: Message = None):
    if task_key not in DAILY_TASKS:
        return

    day_key = current_day_key()
    ensure_daily_tasks_initialized(user_id, day_key)

    task = DAILY_TASKS[task_key]
    state = add_daily_task_progress(user_id, day_key, task_key, amount, task["target"])

    if state["just_completed"] and not state["rewarded"]:
        add_coins(user_id, task["reward"])
        mark_daily_task_rewarded(user_id, day_key, task_key)

        try:
            await bot.send_message(
                user_id,
                f"{header()}\n\n"
                "✅ <b>Задание выполнено!</b>\n\n"
                f"📌 {task['title']}\n"
                f"🎁 Награда: +{task['reward']} Coins\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def is_group_admin(chat_id, user_id):
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status in ("administrator", "creator")


def format_user_label(user_id, username, first_name):
    if username and first_name:
        return f"{first_name} (@{username})"
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


def paid_case_available(user):
    if not user["last_case_time"]:
        return True, None
    last = datetime.fromisoformat(user["last_case_time"])
    now = datetime.utcnow()
    diff = now - last
    if diff >= PAID_CASE_COOLDOWN:
        return True, None
    return False, PAID_CASE_COOLDOWN - diff


def get_effective_sell_price(card, rarity_override=None):
    base_price = int(card.get("sell_price", 0) or 0)
    if base_price <= 0:
        return 0

    rarity = rarity_override or card.get("rarity", "Common")
    multiplier = SELL_PRICE_MULTIPLIER.get(rarity, 0.40)
    min_price, max_price = SELL_PRICE_BOUNDS.get(rarity, (1000, 50000))

    adjusted = int(round(base_price * multiplier))
    return max(min_price, min(max_price, adjusted))


async def send_stats(target, from_callback=False):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Топ по Coins", callback_data="stats:coins")],
            [InlineKeyboardButton(text="🚗 Топ по коллекции", callback_data="stats:collection")],
            [InlineKeyboardButton(text="📅 Топ недели", callback_data="stats:week_cases")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="start")],
        ]
    )

    text = (
        f"{header()}\n\n"
        "📊 <b>Статистика</b>\n\n"
        "Выбирай, что хочешь посмотреть:\n\n"
        f"{footer()}"
    )

    if from_callback:
        await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


async def show_leaderboard(call: CallbackQuery, stat_type: str):
    if stat_type == "coins":
        top = get_top_users_by_coins(10)
        title = "🏆 <b>ТОП ПО МОНЕТАМ</b>"
        line_format = lambda i, row, medals: f"{medals.get(i, f'{i}.')} <b>{row['first_name'] or 'Игрок'}</b> — {row['coins']} 💰"
    elif stat_type == "week_cases":
        week_key = current_week_key()
        top = get_top_users_by_weekly_cases(week_key, 10)
        title = f"📅 <b>ТОП НЕДЕЛИ ПО ОТКРЫТИЯМ</b>\n<code>{week_key}</code>"
        line_format = lambda i, row, medals: f"{medals.get(i, f'{i}.')} <b>{row['first_name'] or 'Игрок'}</b> — {row['cases_opened']} кейсов"
    else:
        top = get_top_users_by_collection(10)
        total_cards = len(CARDS)
        title = "🚗 <b>ТОП ПО КОЛЛЕКЦИИ</b>"
        line_format = lambda i, row, medals: f"{medals.get(i, f'{i}.')} <b>{row['first_name'] or 'Игрок'}</b> — {row['count']}/{total_cards} 🚗"

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = []
    for i, row in enumerate(top, start=1):
        lines.append(line_format(i, row, medals))

    text = (
        f"{header()}\n\n"
        f"{title}\n\n"
        f"{chr(10).join(lines) if lines else 'Пока нет данных'}\n\n"
        f"{footer()}"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:stats")],
        ]
    )

    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


async def get_group_top_by_coins(chat_id: int, limit: int = 10):
    candidates = get_top_users_by_coins(300)
    top = []
    allowed_statuses = {"creator", "administrator", "member", "restricted"}

    for row in candidates:
        try:
            member = await bot.get_chat_member(chat_id, row["user_id"])
            if member.status in allowed_statuses:
                top.append(row)
                if len(top) >= limit:
                    break
        except TelegramBadRequest:
            continue
        except Exception:
            continue

    return top


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
# SEND CAR IMAGE HELPER
# =========================

async def send_car_image(target, card, car_rarity, caption, reply_markup=None, user_id=None):
    """
    Универсальная функция для отправки изображения машины
    Приоритет: sticker_id > image файл > текст
    
    target: Message или CallbackQuery.message
    card: словарь с данными машины из CARDS
    car_rarity: редкость машины
    caption: текст подписи
    reply_markup: клавиатура (опционально)
    user_id: ID пользователя (для сохранения ID стикера)
    """
    # Проверяем наличие sticker_id (приоритет) - НЕ пустая строка!
    sticker_id = card.get("sticker_id", "").strip()
    
    if sticker_id:  # Теперь проверяет что строка не пустая
        # Отправляем стикер
        try:
            sticker_message = await target.answer_sticker(sticker_id)
            # Сохраняем ID стикера для последующего удаления
            if user_id:
                LAST_STICKER_MESSAGE_ID[user_id] = sticker_message.message_id
            # После стикера отправляем текст с информацией
            if reply_markup:
                await target.answer(caption, parse_mode="HTML", reply_markup=reply_markup)
            else:
                await target.answer(caption, parse_mode="HTML")
            return True
        except Exception as e:
            logger.warning(f"Failed to send sticker {sticker_id}: {e}, falling back to image")
    
    # Если нет sticker_id или не удалось - пробуем изображение
    image_path = card.get("image", "")
    if image_path and not image_path.startswith("/") and not image_path.startswith("."):
        image_path = f"./{image_path}"
    
    try:
        if image_path and os.path.exists(image_path):
            image = FSInputFile(image_path)
            await target.answer_document(
                image,
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            return True
    except (FileNotFoundError, OSError) as e:
        logger.warning(f"Image not found or error: {image_path}, error: {e}")
    
    # Если нет ни стикера, ни изображения - ничего не отправляем
    logger.warning(f"No image available for card, skipping send")
    return False

# =========================
# TEST IMAGE COMMAND
# =========================

@dp.message(Command("testimage"))
async def test_image(message: Message):
    """Тестовая команда для проверки отправки изображений с прозрачным фоном"""
    
    await message.answer("🧪 Команда работает! Пробую отправить как стикер...")
    
    # Путь к тестовому изображению (используем Honda Civic)
    test_image_path = "./common/honda_civic.png"
    
    try:
        if os.path.exists(test_image_path):
            image = FSInputFile(test_image_path)
            
            # Отправляем как стикер
            try:
                await message.answer_sticker(image)
                await message.answer(
                    f"{header()}\n\n"
                    "🎨 <b>СТИКЕР</b>\n\n"
                    "🚘 Хонда Сивик\n"
                    "✅ Отправлено как стикер\n"
                    "⚠️ Стикеры всегда маленькие в Telegram\n\n"
                    f"{footer()}",
                    parse_mode="HTML",
                )
                logger.info("test_image_sent user_id=%s path=%s as_sticker=True", message.from_user.id, test_image_path)
            except Exception as sticker_error:
                await message.answer(
                    f"{header()}\n\n"
                    f"❌ <b>Не удалось отправить как стикер</b>\n\n"
                    f"<code>{str(sticker_error)}</code>\n\n"
                    f"📝 Требования для стикера:\n"
                    f"• PNG или WEBP формат\n"
                    f"• Размер до 512x512 пикселей\n"
                    f"• Файл до 512 КБ\n"
                    f"• Прозрачный фон\n\n"
                    f"{footer()}",
                    parse_mode="HTML",
                )
                logger.error("test_image_sticker_failed user_id=%s error=%s", message.from_user.id, str(sticker_error))
        else:
            await message.answer(
                f"{header()}\n\n"
                f"❌ Тестовое изображение не найдено:\n"
                f"<code>{test_image_path}</code>\n\n"
                f"Создай PNG файл с прозрачным фоном и помести его по этому пути.\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
            logger.warning("test_image_not_found user_id=%s path=%s", message.from_user.id, test_image_path)
    except Exception as e:
        await message.answer(
            f"{header()}\n\n"
            f"❌ Ошибка при отправке изображения:\n"
            f"<code>{str(e)}</code>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        logger.error("test_image_error user_id=%s error=%s", message.from_user.id, str(e))

# =========================
# GET STICKER FILE_ID
# =========================

@dp.message(F.sticker)
async def get_sticker_id(message: Message):
    """Получить file_id любого стикера - просто перешли стикер боту"""
    # Проверка доступа: только админ (ID 5658493362) и только в ЛС
    if message.chat.type != "private" or message.from_user.id != 5658493362:
        return
    
    sticker = message.sticker
    
    info_text = (
        f"{header()}\n\n"
        f"🎨 <b>ИНФОРМАЦИЯ О СТИКЕРЕ</b>\n\n"
        f"📋 <b>file_id:</b>\n"
        f"<code>{sticker.file_id}</code>\n\n"
        f"📐 <b>Размер:</b> {sticker.width}x{sticker.height}\n"
        f"📦 <b>Файл:</b> {sticker.file_size} байт\n"
    )
    
    if sticker.set_name:
        info_text += f"📚 <b>Стикерпак:</b> {sticker.set_name}\n"
    
    info_text += (
        f"\n💡 <b>Как использовать:</b>\n"
        f"Скопируй file_id и добавь в cards.json:\n"
        f'<code>"sticker_id": "{sticker.file_id}"</code>\n\n'
        f"{footer()}"
    )
    
    await message.answer(info_text, parse_mode="HTML")
    logger.info(
        "sticker_id_requested user_id=%s file_id=%s set_name=%s",
        message.from_user.id,
        sticker.file_id,
        sticker.set_name
    )

# =========================
# CREATE STICKER FROM PHOTO
# =========================

@dp.message(Command("addsticker"))
async def add_sticker_command(message: Message):
    """Команда для создания стикера из фото"""
    # Проверка доступа: только админ (ID 5658493362) и только в ЛС
    if message.chat.type != "private" or message.from_user.id != 5658493362:
        return
    
    await message.answer(
        f"{header()}\n\n"
        "🎨 <b>СОЗДАНИЕ СТИКЕРА</b>\n\n"
        "📸 Отправь мне фото машины (PNG с прозрачным фоном)\n"
        "🤖 Я создам стикер и дам тебе file_id\n\n"
        "⚠️ <b>Требования:</b>\n"
        "• Формат: PNG с прозрачностью\n"
        "• Размер: оптимально 512x512px\n"
        "• До 512 КБ\n\n"
        f"{footer()}",
        parse_mode="HTML"
    )

@dp.message(F.photo | F.document)
async def create_sticker_from_photo(message: Message):
    """Создать стикер из отправленного фото"""
    
    # Проверка доступа: только админ (ID 5658493362) и только в ЛС
    if message.chat.type != "private" or message.from_user.id != 5658493362:
        return
    
    # Проверяем что это прямой ответ на команду или в контексте создания стикера
    if not message.photo and not (message.document and message.document.mime_type and 'image' in message.document.mime_type):
        return
    
    await message.answer("⏳ Создаю стикер...")
    
    try:
        # Получаем файл
        if message.photo:
            file = message.photo[-1]  # Берем самое большое фото
            file_id = file.file_id
        else:
            file = message.document
            file_id = file.file_id
        
        # Скачиваем файл
        file_info = await message.bot.get_file(file_id)
        file_path = file_info.file_path
        
        # Загружаем как стикер
        bot_file = await message.bot.download_file(file_path)
        
        # Создаем временный файл
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
            tmp_file.write(bot_file.read())
            tmp_path = tmp_file.name
        
        # Отправляем как стикер чтобы получить file_id
        sticker_file = FSInputFile(tmp_path)
        sent_sticker = await message.answer_sticker(sticker_file)
        
        # Получаем file_id отправленного стикера
        sticker_id = sent_sticker.sticker.file_id
        
        # Удаляем временный файл
        os.remove(tmp_path)
        
        # Отправляем результат
        await message.answer(
            f"{header()}\n\n"
            f"✅ <b>СТИКЕР СОЗДАН!</b>\n\n"
            f"📋 <b>file_id:</b>\n"
            f"<code>{sticker_id}</code>\n\n"
            f"💾 <b>Добавь в cards.json:</b>\n"
            f'<code>"sticker_id": "{sticker_id}"</code>\n\n'
            f"📝 Нажми на file_id, чтобы скопировать\n\n"
            f"{footer()}",
            parse_mode="HTML"
        )
        
        logger.info(
            "sticker_created user_id=%s file_id=%s",
            message.from_user.id,
            sticker_id
        )
        
    except Exception as e:
        await message.answer(
            f"{header()}\n\n"
            f"❌ <b>Ошибка создания стикера</b>\n\n"
            f"<code>{str(e)}</code>\n\n"
            f"⚠️ Убедись что:\n"
            f"• Файл PNG с прозрачным фоном\n"
            f"• Размер до 512KB\n"
            f"• Разрешение оптимально 512x512\n\n"
            f"{footer()}",
            parse_mode="HTML"
        )
        logger.error("sticker_creation_failed user_id=%s error=%s", message.from_user.id, str(e))

# =========================
# START
# =========================

@dp.message(F.chat.type == "private", Command("start"))
async def start(message: Message):
    user = get_user(message.from_user.id)
    is_new = user is None
    
    if is_new:
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

    if is_new:
        # Подробное приветствие для новых
        await message.answer(
            f"{header()}\n\n"
            f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
            f"🎮 Я игровой бот для сбора редких машин! Открывай кейсы, собирай коллекцию, продавай машины и зарабатывай монеты!\n\n"
            f"🎁 <b>Как начать:</b>\n"
            f"• Открывай <b>бесплатные кейсы</b> каждые 4 часа\n"
            f"• Копи монеты и <b>покупай платные кейсы</b>\n"
            f"• Собирай все машины в <b>гараже</b>\n"
            f"• Продавай дубликаты и зарабатывай\n\n"
            f"Выбирай действие ниже и начинай играть!\n\n"
            f"{footer()}",
            reply_markup=main_menu_kb(message.from_user.id),
            parse_mode="HTML",
        )
    else:
        # Обычное меню для вернувшихся
        await message.answer(
            f"{header()}\n\n"
            f"Привет, <b>{message.from_user.first_name}</b>!\n"
            f"Выбирай действие:\n\n"
            f"{footer()}",
            reply_markup=main_menu_kb(message.from_user.id),
            parse_mode="HTML",
        )

    user_for_daily = get_user(message.from_user.id)
    if user_for_daily:
        await process_global_weekly_rewards_once()
        await maybe_notify_global_weekly_results(message, message.from_user.id)
        await maybe_apply_streak_bonus(message, user_for_daily)
        user_for_daily = get_user(message.from_user.id)
        await maybe_notify_daily_available(message, user_for_daily)


@dp.callback_query(F.data == "start")
async def start_menu(call: CallbackQuery):
    if call.message.chat.type != "private":
        await call.answer("❌ Меню доступно только в ЛС", show_alert=True)
        return
    
    # Удаляем предыдущий стикер, если был
    if call.from_user.id in LAST_CAR_VIEW_MESSAGE_IDS:
        try:
            sticker_msg_id, _ = LAST_CAR_VIEW_MESSAGE_IDS[call.from_user.id]
            if sticker_msg_id:
                await bot.delete_message(call.message.chat.id, sticker_msg_id)
        except Exception:
            pass
        del LAST_CAR_VIEW_MESSAGE_IDS[call.from_user.id]
    
    # Просто редактируем текущее сообщение на меню
    await call.message.edit_text(
        f"{header()}\n\n"
        "Меню\n\n"
        f"{footer()}",
        reply_markup=main_menu_kb(call.from_user.id),
        parse_mode="HTML",
    )

    user = get_user(call.from_user.id)
    if user:
        await process_global_weekly_rewards_once()
        await maybe_notify_global_weekly_results(call.message, call.from_user.id)
        await maybe_apply_streak_bonus(call.message, user)
        user = get_user(call.from_user.id)
        await maybe_notify_daily_available(call.message, user)

    await call.answer()


@dp.callback_query(F.data == "menu:help")
async def help_menu(call: CallbackQuery):
    if call.message.chat.type != "private":
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await call.answer()
        await call.message.answer(
            f"{header()}\n\n"
            "❓ Помощь доступна только в ЛС\n\n"
            f"<a href='{bot_link}'>Открыть бота</a>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return
    
    help_text = (
        f"{header()}\n\n"
        "<b>❓ Помощь</b>\n\n"
        "<b>📱 Команды:</b>\n"
        "/start - Главное меню\n"
        "/stats - Топ игроков\n"
        "/help - Справка\n\n"
        "<b>🔊 Триггеры в группе:</b>\n"
        "<b>Открыть кейс:</b>\n"
        "  кейс, case, открыть, open\n"
        "<b>Баланс:</b>\n"
        "  баланс, balance, coins\n\n"
        "<b>💡 Совет:</b>\n"
        "Все основные функции доступны через меню ниже 👇\n\n"
        f"{footer()}"
    )
    
    await call.message.edit_text(
        help_text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="start")]]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.message(Command("stats"))
async def stats_command(message: Message):
    await send_stats(message)


@dp.message(Command("help"))
async def help_command(message: Message):
    help_text = (
        f"{header()}\n\n"
        "<b>❓ Помощь</b>\n\n"
        "<b>📱 Команды:</b>\n"
        "/start - Главное меню\n"
        "/stats - Топ игроков\n"
        "/help - Справка\n\n"
        "<b>🔊 Триггеры в группе:</b>\n"
        "<b>Открыть кейс:</b>\n"
        "  кейс, case, открыть, open\n"
        "<b>Баланс:</b>\n"
        "  баланс, balance, coins\n\n"
        "<b>💡 Совет:</b>\n"
        "Все основные функции доступны через меню 👇\n\n"
        f"{footer()}"
    )
    await message.answer(help_text, parse_mode="HTML")


@dp.callback_query(F.data == "menu:stats")
async def stats_menu(call: CallbackQuery):
    await send_stats(call.message, from_callback=True)
    await call.answer()


@dp.callback_query(F.data.startswith("stats:"))
async def show_stats(call: CallbackQuery):
    stat_type = call.data.split(":")[1]
    await show_leaderboard(call, stat_type)
    await call.answer()


@dp.callback_query(F.data == "menu:feedback")
async def feedback_menu(call: CallbackQuery):
    if call.message.chat.type != "private":
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await call.answer()
        await delete_message_safe(call.message)
        await call.message.answer(
            f"{header()}\n\n"
            "✍️ Отзывы принимаются в ЛС\n\n"
            f"<a href='{bot_link}'>Открыть бота</a>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return

    kb = [
        [InlineKeyboardButton(text=label, callback_data=f"feedback:cat:{slug}")]
        for slug, label in FEEDBACK_CATEGORIES
    ]
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="start")])

    await call.message.edit_text(
        f"{header()}\n\n"
        "✍️ <b>Отзыв</b>\n\n"
        "Выбирай категорию:\n\n"
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
                InlineKeyboardButton(text="🔙 Назад", callback_data="start"),
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
        "🔙 Назад в меню\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Меню", callback_data="start")]]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.message(F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def feedback_message(message: Message):
    if is_owner(message.from_user.id) and message.from_user.id in ADMIN_BROADCAST_PENDING:
        text = (message.text or "").strip()
        if not text:
            await message.answer(
                f"{header()}\n\n"
                "Отправь рассылку текстом одним сообщением.\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
            return

        target = ADMIN_BROADCAST_PENDING.pop(message.from_user.id)
        payload = f"📣 Объявление от разработчика\n\n{text}"

        users_ok = users_fail = 0
        groups_ok = groups_fail = 0
        pinned_ok = pinned_fail = 0

        if target in {"private", "all"}:
            for uid in get_all_user_ids():
                try:
                    await bot.send_message(uid, payload)
                    users_ok += 1
                except Exception:
                    users_fail += 1

        if target in {"groups", "all"}:
            for chat_id in get_all_group_chat_ids():
                try:
                    sent = await bot.send_message(chat_id, payload)
                    groups_ok += 1
                    try:
                        await bot.pin_chat_message(chat_id, sent.message_id, disable_notification=True)
                        pinned_ok += 1
                    except Exception:
                        pinned_fail += 1
                except Exception:
                    groups_fail += 1

        await message.answer(
            f"{header()}\n\n"
            "✅ <b>Рассылка завершена</b>\n\n"
            f"👤 ЛС: {users_ok} успешно, {users_fail} ошибок\n"
            f"👥 Группы: {groups_ok} успешно, {groups_fail} ошибок\n"
            f"📌 Закреплено: {pinned_ok} успешно, {pinned_fail} не удалось\n\n"
            f"{footer()}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
                    [InlineKeyboardButton(text="🔙 Меню", callback_data="start")],
                ]
            ),
            parse_mode="HTML",
        )
        return

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
        global BOT_ID, FEEDBACK_CHAT_ID
        if BOT_ID is None:
            me = await bot.get_me()
            BOT_ID = me.id

        try:
            await bot.get_chat_member(FEEDBACK_CHAT_ID, BOT_ID)
        except TelegramBadRequest as exc:
            params = getattr(exc, "parameters", None)
            migrate_to = getattr(params, "migrate_to_chat_id", None) if params else None
            if migrate_to:
                FEEDBACK_CHAT_ID = migrate_to
                await bot.get_chat_member(FEEDBACK_CHAT_ID, BOT_ID)
            else:
                raise
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

    feedback_text = (
        f"📬 <b>Новый отзыв</b>\n\n"
        f"👤 <b>Пользователь:</b> {sender.full_name}\n"
        f"🔗 <b>Username:</b> {username}\n"
        f"🆔 <b>ID:</b> {sender.id}\n"
        f"🏷️ <b>Категория:</b> {category}\n\n"
        f"💬 <b>Сообщение:</b>\n{text}"
    )

    try:
        await bot.send_message(
            FEEDBACK_CHAT_ID,
            feedback_text,
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
    except TelegramBadRequest as exc:
        params = getattr(exc, "parameters", None)
        migrate_to = getattr(params, "migrate_to_chat_id", None) if params else None
        if migrate_to:
            try:
                await bot.send_message(
                    migrate_to,
                    feedback_text,
                    parse_mode="HTML",
                )
                FEEDBACK_CHAT_ID = migrate_to
                await message.answer(
                    f"{header()}\n\n"
                    "✅ Спасибо! Отзыв отправлен.\n\n"
                    f"{footer()}",
                    reply_markup=main_menu_kb(),
                    parse_mode="HTML",
                )
                logger.info(
                    "feedback_chat_migrated user_id=%s old_chat_id=%s new_chat_id=%s",
                    sender.id,
                    FEEDBACK_CHAT_ID,
                    migrate_to,
                )
                return
            except Exception as exc2:
                logger.error(
                    "feedback_send_failed user_id=%s error=%s",
                    sender.id,
                    exc2,
                )
        else:
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
# PROFILE
# =========================

@dp.callback_query(F.data == "menu:profile")
async def profile_menu(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Тебя не нашли в базе, нажми /start", show_alert=True)
        return

    rarity_counts = get_user_rarity_counts(call.from_user.id)
    total_cars = sum(rarity_counts.values())
    total_catalog = len(CARDS)
    collection_percent = (total_cars / total_catalog * 100) if total_catalog else 0
    reg_raw = user.get("created_at")
    reg_text = "Неизвестно"
    if reg_raw:
        try:
            reg_text = datetime.fromisoformat(reg_raw).strftime("%d.%m.%Y %H:%M")
        except Exception:
            reg_text = reg_raw

    username = user.get("username")
    nick = f"@{username}" if username else "Без ника"

    text = (
        f"{header()}\n\n"
        "👤 <b>Профиль</b>\n\n"
        f"🪪 <b>Ник:</b> {nick}\n"
        f"🆔 <b>ID:</b> <code>{user['user_id']}</code>\n"
        f"💰 <b>Баланс:</b> {user['coins']} Coins\n"
        f"🗓 <b>Первая регистрация:</b> {reg_text}\n"
        f"🔥 <b>Серия входов:</b> {user.get('streak_current', 0)} дн.\n"
        f"🏆 <b>Лучший стрик:</b> {user.get('streak_best', 0)} дн.\n"
        f"🎁 <b>Открыто кейсов:</b> {user.get('total_cases_opened', 0)}\n"
        f"🚗 <b>Машин в наличии:</b> {total_cars}\n\n"
        f"📈 <b>Заполнение коллекции:</b> {total_cars}/{total_catalog} ({collection_percent:.1f}%)\n\n"
        "<b>По редкостям:</b>\n"
        f"⚪ Обычная: {rarity_counts.get('Common', 0)}\n"
        f"🔵 Редкая: {rarity_counts.get('Rare', 0)}\n"
        f"🟣 Эпическая: {rarity_counts.get('Epic', 0)}\n"
        f"🟡 Легендарная: {rarity_counts.get('Legendary', 0)}\n\n"
        f"{footer()}"
    )

    await call.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Меню", callback_data="start")]]
        ),
        parse_mode="HTML",
    )
    await call.answer()


# =========================
# ADMIN PANEL
# =========================

@dp.callback_query(F.data == "menu:admin")
async def admin_panel(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещен", show_alert=True)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📈 Статистика бота", callback_data="admin:stats")],
            [InlineKeyboardButton(text="📅 Статус недели", callback_data="admin:week")],
            [InlineKeyboardButton(text="📣 Массовая рассылка", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="🔙 Меню", callback_data="start")],
        ]
    )

    await call.message.edit_text(
        f"{header()}\n\n"
        "🛠 <b>Админ-панель</b>\n\n"
        "Доступ только для разработчика.\n"
        "Выбирай нужный раздел ниже.\n\n"
        f"{footer()}",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await call.answer()


@dp.message(F.chat.type == "private", Command("admin"))
async def admin_command(message: Message):
    if not is_owner(message.from_user.id):
        await message.answer(
            f"{header()}\n\n"
            "⛔ Доступ запрещен\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📈 Статистика бота", callback_data="admin:stats")],
            [InlineKeyboardButton(text="📅 Статус недели", callback_data="admin:week")],
            [InlineKeyboardButton(text="📣 Массовая рассылка", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="🔙 Меню", callback_data="start")],
        ]
    )

    await message.answer(
        f"{header()}\n\n"
        "🛠 <b>Админ-панель</b>\n\n"
        "Доступ только для разработчика.\n"
        "Выбирай нужный раздел ниже.\n\n"
        f"{footer()}",
        reply_markup=kb,
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "admin:stats")
async def admin_stats(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещен", show_alert=True)
        return

    stats = get_admin_summary_stats()
    await call.message.edit_text(
        f"{header()}\n\n"
        "📈 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{stats['users_count']}</b>\n"
        f"🚗 Машин в гаражах: <b>{stats['garage_count']}</b>\n"
        f"📅 Записей дневок: <b>{stats['daily_rows']}</b>\n"
        f"🏁 Записей недельки: <b>{stats['weekly_rows']}</b>\n"
        f"🆔 Admin ID: <code>{ADMIN_USER_ID}</code>\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
                [InlineKeyboardButton(text="🔙 Меню", callback_data="start")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data == "admin:week")
async def admin_week_status(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещен", show_alert=True)
        return

    current = current_week_key()
    previous = previous_week_key()
    global_top = get_top_users_by_weekly_cases(current, 5)

    lines = []
    for i, row in enumerate(global_top, start=1):
        lines.append(f"{i}. <b>{row['first_name'] or 'Игрок'}</b> — {row['cases_opened']} кейсов")

    await call.message.edit_text(
        f"{header()}\n\n"
        "📅 <b>Статус недели</b>\n\n"
        f"Текущая: <code>{current}</code>\n"
        f"Прошлая: <code>{previous}</code>\n\n"
        f"<b>Топ текущей недели (глобально):</b>\n"
        f"{chr(10).join(lines) if lines else 'Пока нет открытий.'}\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
                [InlineKeyboardButton(text="🔙 Меню", callback_data="start")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_menu(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещен", show_alert=True)
        return

    await call.message.edit_text(
        f"{header()}\n\n"
        "📣 <b>Массовая рассылка</b>\n\n"
        "Выбирай, куда отправить сообщение:\n"
        "• 👤 Только в ЛС\n"
        "• 👥 Только в группы\n"
        "• 🌐 В ЛС и группы\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="👤 ЛС", callback_data="admin:broadcast_target:private"),
                    InlineKeyboardButton(text="👥 Группы", callback_data="admin:broadcast_target:groups"),
                ],
                [InlineKeyboardButton(text="🌐 ЛС + Группы", callback_data="admin:broadcast_target:all")],
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data.startswith("admin:broadcast_target:"))
async def admin_broadcast_target(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещен", show_alert=True)
        return

    target = call.data.split(":", 2)[2]
    if target not in {"private", "groups", "all"}:
        await call.answer("❌ Неизвестный тип рассылки", show_alert=True)
        return

    ADMIN_BROADCAST_PENDING[call.from_user.id] = target
    target_label = {"private": "ЛС", "groups": "Группы", "all": "ЛС + Группы"}[target]

    await call.message.edit_text(
        f"{header()}\n\n"
        "📝 <b>Введи текст рассылки</b>\n\n"
        f"Канал: <b>{target_label}</b>\n"
        "Отправь одним текстовым сообщением в этот чат.\n"
        "Если передумал — нажми «Отмена».\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:broadcast_cancel")],
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data == "admin:broadcast_cancel")
async def admin_broadcast_cancel(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещен", show_alert=True)
        return

    ADMIN_BROADCAST_PENDING.pop(call.from_user.id, None)
    await call.message.edit_text(
        f"{header()}\n\n"
        "❌ Рассылка отменена\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
                [InlineKeyboardButton(text="🔙 Меню", callback_data="start")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


# =========================
# BALANCE
# =========================

@dp.callback_query(F.data == "menu:balance")
async def balance(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Тебя не нашли в базе, нажми /start", show_alert=True)
        return
    
    await call.message.edit_text(
        f"{header()}\n\n"
        f"💰 <b>Coins:</b> {user['coins']}\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Меню", callback_data="start")]]
        ),
        parse_mode="HTML",
    )
    await call.answer()


# =========================
# DAILY TASKS
# =========================

@dp.callback_query(F.data == "menu:daily")
async def daily_tasks_menu(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Тебя не нашли в базе, нажми /start", show_alert=True)
        return

    day_key = current_day_key()
    ensure_daily_tasks_initialized(user["user_id"], day_key)
    progress = get_daily_tasks_progress(user["user_id"], day_key)

    lines = []
    done_count = 0
    for task_key, task in DAILY_TASKS.items():
        state = progress.get(task_key, {"progress": 0, "completed": False})
        cur = state.get("progress", 0)
        target = task["target"]
        completed = state.get("completed", False)
        status = "✅ Выполнено" if completed else f"⏳ {cur}/{target}"
        if completed:
            done_count += 1
        lines.append(f"• <b>{task['title']}</b> — {status} (+{task['reward']} 💰)")

    text = (
        f"{header()}\n\n"
        "📅 <b>Ежедневные задания</b>\n\n"
        f"Прогресс: <b>{done_count}/{len(DAILY_TASKS)}</b>\n"
        f"День: <code>{day_key}</code> (UTC)\n\n"
        f"{chr(10).join(lines)}\n\n"
        f"{footer()}"
    )

    await call.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Меню", callback_data="start")]]
        ),
        parse_mode="HTML",
    )
    await call.answer()

# =========================
# BUY CASES
# =========================

@dp.callback_query(F.data == "menu:buy_cases")
async def buy_cases_menu(call: CallbackQuery):
    if call.message.chat.type != "private":
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await call.answer()
        await call.message.answer(
            f"{header()}\n\n"
            "💳 Магазин доступен только в ЛС\n\n"
            f"<a href='{bot_link}'>Открыть бота</a>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return
    
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Тебя не нашли в базе, нажми /start", show_alert=True)
        return
    
    paid_case = {
        "name": "Платный",
        "price": 38000,
        "desc": "70% Обычная, 20% Редкая, 8% Эпическая, 2% Легендарная",
    }

    affordability = "✅" if user["coins"] >= paid_case["price"] else "❌"
    kb = [
        [
            InlineKeyboardButton(
                text=f"{affordability} {paid_case['name']} - {paid_case['price']} 💰",
                callback_data="buy_case:paid",
            )
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="start")],
    ]

    await call.message.edit_text(
        f"{header()}\n\n"
        "<b>💳 Магазин кейсов</b>\n\n"
        f"💰 <b>У тебя:</b> {user['coins']} Coins\n\n"
        f"🎲 <b>{paid_case['name']} кейс:</b> {paid_case['desc']}\n\n"
        "✅ = можно купить\n"
        "❌ = недостаточно Coins\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data.startswith("buy_case:"))
async def buy_case(call: CallbackQuery):
    case_type = call.data.split(":")[1]
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Тебя не нашли в базе, нажми /start", show_alert=True)
        return

    case_info = {
        "name": "Платный",
        "price": 38000,
        "rarity_dist": [(0.70, "Common"), (0.90, "Rare"), (0.98, "Epic"), (1.0, "Legendary")],
    }

    if case_type != "paid":
        await call.answer("❌ Неизвестный кейс", show_alert=True)
        return

    can_open_paid, paid_remaining = paid_case_available(user)
    if not can_open_paid:
        seconds_left = max(1, int(paid_remaining.total_seconds()))
        await call.answer(
            f"⏳ Подожди {seconds_left} сек перед следующим платным кейсом",
            show_alert=True,
        )
        return

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
    update_last_case_time(call.from_user.id)

    card = CARDS[card_id]
    rarity = card["rarity"]
    
    # Добавляем машину в гараж
    add_car_to_garage(call.from_user.id, card_id, rarity)
    increment_total_cases_opened(call.from_user.id)
    increment_weekly_cases_opened(call.from_user.id, current_week_key(), 1)
    await apply_daily_task_progress(call.from_user.id, "buy_standard", notify_message=call.message)
    if rarity in ("Rare", "Epic", "Legendary"):
        await apply_daily_task_progress(call.from_user.id, "get_rare_plus", notify_message=call.message)
    logger.info(
        "buy_case_opened user_id=%s case=%s card_id=%s rarity=%s price=%s",
        call.from_user.id,
        case_type,
        card_id,
        rarity,
        case_info["price"],
    )

    emoji = RARITY_EMOJI.get(rarity, "❓")
    sell_price = get_effective_sell_price(card)
    
    await delete_message_safe(call.message)
    
    caption = (
        f"{header()}\n\n"
        f"🎉 <b>ОТКРЫТ {case_info['name'].upper()} КЕЙС</b>\n\n"
        f"🚘 <b>{card['name_ru']}</b>\n"
        f"Редкость: {emoji} {RARITY_RU.get(rarity, rarity)}\n\n"
        f"💵 <b>Цена продажи:</b> {sell_price} Coins\n\n"
        f"{footer()}"
    )
    
    success = await send_car_image(call.message, card, rarity, caption, user_id=call.from_user.id)
    if not success:
        # Если нет фото - отправим текст с кнопкой
        await call.message.answer(
            caption,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="start")]]
            )
        )
    await call.answer()

# =========================
# FREE CASE
# =========================

@dp.callback_query(F.data == "menu:free")
async def free_case(call: CallbackQuery):
    if call.message.chat.type != "private":
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await call.answer()
        await call.message.answer(
            f"{header()}\n\n"
            "🎁 Бесплатные кейсы доступны только в ЛС\n\n"
            f"<a href='{bot_link}'>Открыть бота</a>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return
    
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Тебя не нашли в базе, нажми /start", show_alert=True)
        return
    available, remaining = free_case_available(user)

    if not available:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="start")],
            ]
        )
        await call.message.edit_text(
            f"{header()}\n\n"
            "⏳ Бесплатный кейс недоступен\n\n"
            f"Осталось: {format_timedelta(remaining)}\n\n"
            f"{footer()}",
            reply_markup=kb,
            parse_mode="HTML",
        )
        await call.answer()
        return

    card_id = draw_free_case_card(call.from_user.id)
    
    if card_id is None:
        update_last_free_case_time(user["user_id"])
        logger.info(
            "free_case_no_cards user_id=%s",
            call.from_user.id,
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="start")],
            ]
        )
        await call.message.edit_text(
            f"{header()}\n\n"
            "🎯 <b>Коллекция полна!</b>\n\n"
            "Ты собрал все машины!\n\n"
            f"{footer()}",
            reply_markup=kb,
            parse_mode="HTML",
        )
        await call.answer()
        return
    
    card = CARDS.get(card_id)
    if not card:
        await call.answer("❌ Машина не найдена в каталоге!", show_alert=True)
        return
    rarity = card["rarity"]

    add_car_to_garage(user["user_id"], card_id, rarity)
    increment_total_cases_opened(user["user_id"])
    increment_weekly_cases_opened(user["user_id"], current_week_key(), 1)
    await apply_daily_task_progress(user["user_id"], "free_case", notify_message=call.message)
    if rarity in ("Rare", "Epic", "Legendary"):
        await apply_daily_task_progress(user["user_id"], "get_rare_plus", notify_message=call.message)
    add_coins(user["user_id"], FREE_CASE_BONUS_COINS)
    update_last_free_case_time(user["user_id"])
    logger.info(
        "free_case_opened user_id=%s card_id=%s rarity=%s bonus=%s",
        call.from_user.id,
        card_id,
        rarity,
        FREE_CASE_BONUS_COINS,
    )

    await delete_message_safe(call.message)
    sell_price = get_effective_sell_price(card)
    
    caption = (
        f"{header()}\n\n"
        "🎁 <b>БЕСПЛАТНЫЙ КЕЙС</b>\n\n"
        f"🚘 <b>{card['name_ru']}</b>\n"
        f"Редкость: {RARITY_EMOJI[rarity]} {RARITY_RU.get(rarity, rarity)}\n"
        f"💵 <b>Цена продажи:</b> {sell_price} Coins\n"
        f"💰 <b>Бонус:</b> +{FREE_CASE_BONUS_COINS} Coins\n\n"
        f"{footer()}"
    )
    
    success = await send_car_image(call.message, card, rarity, caption, user_id=call.from_user.id)
    if not success:
        # Если нет фото - отправим текст с кнопкой
        await call.message.answer(
            caption,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="start")]]
            )
        )
    await call.answer()

# =========================
# GARAGE (PAGINATION)
# =========================

@dp.callback_query(F.data.startswith("menu:garage"))
async def garage(call: CallbackQuery):
    if call.message.chat.type != "private":
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await call.answer()
        await call.message.answer(
            f"{header()}\n\n"
            "🚘 Гараж доступен только в ЛС\n\n"
            f"<a href='{bot_link}'>Открыть бота</a>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return
    
    page = int(call.data.split(":")[2])
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Тебя не нашли в базе, нажми /start", show_alert=True)
        return
    cars = get_user_garage(user["user_id"])

    # Удаляем предыдущий стикер, если был
    if call.from_user.id in LAST_CAR_VIEW_MESSAGE_IDS:
        try:
            sticker_msg_id, _ = LAST_CAR_VIEW_MESSAGE_IDS[call.from_user.id]
            if sticker_msg_id:
                await bot.delete_message(call.message.chat.id, sticker_msg_id)
        except Exception:
            pass
        del LAST_CAR_VIEW_MESSAGE_IDS[call.from_user.id]

    if not cars:
        text = f"{header()}\n\n🚗 Гараж пуст\n\n{footer()}"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="start")]]
        )
        
        if call.from_user.id in GARAGE_MESSAGE_ID:
            try:
                await bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=GARAGE_MESSAGE_ID[call.from_user.id],
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except Exception:
                # Fallback если сообщение не существует
                await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
                GARAGE_MESSAGE_ID[call.from_user.id] = call.message.message_id
        else:
            await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            GARAGE_MESSAGE_ID[call.from_user.id] = call.message.message_id
        
        await call.answer()
        return

    start = page * GARAGE_PAGE_SIZE
    end = start + GARAGE_PAGE_SIZE
    chunk = cars[start:end]

    rarity_counts = {"Common": 0, "Rare": 0, "Epic": 0, "Legendary": 0}
    for car in cars:
        if car["rarity"] in rarity_counts:
            rarity_counts[car["rarity"]] += 1

    garage_text = (
        f"{header()}\n\n"
        "🚗 <b>Твой гараж</b>\n\n"
        f"📦 <b>Всего машин:</b> {len(cars)}\n"
        f"⚪ Обычная: {rarity_counts['Common']}\n"
        f"🔵 Редкая: {rarity_counts['Rare']}\n"
        f"🟣 Эпическая: {rarity_counts['Epic']}\n"
        f"🟡 Легендарная: {rarity_counts['Legendary']}\n\n"
        f"{footer()}"
    )

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

    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="start")])

    if call.from_user.id in GARAGE_MESSAGE_ID:
        try:
            await bot.edit_message_text(
                garage_text,
                chat_id=call.message.chat.id,
                message_id=GARAGE_MESSAGE_ID[call.from_user.id],
                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
                parse_mode="HTML",
            )
        except Exception:
            # Fallback если сообщение не существует
            await call.message.edit_text(
                garage_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
                parse_mode="HTML",
            )
            GARAGE_MESSAGE_ID[call.from_user.id] = call.message.message_id
    else:
        await call.message.edit_text(
            garage_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            parse_mode="HTML",
        )
        GARAGE_MESSAGE_ID[call.from_user.id] = call.message.message_id
    
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
    sell_price = get_effective_sell_price(card, rarity_override=car["rarity"])

    await call.answer()  # Подтверждаем callback
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"💵 Продать за {sell_price} 💰 Coins", callback_data=f"sell:{car_id}")],
            [
                InlineKeyboardButton(text="🔙 Назад в гараж", callback_data="menu:garage:0"),
                InlineKeyboardButton(text="🏠 Меню", callback_data="start"),
            ],
        ]
    )
    
    caption = (
        f"{header()}\n\n"
        f"🚘 <b>{card['name_ru']}</b>\n"
        f"Редкость: {emoji} {RARITY_RU.get(car['rarity'], car['rarity'])}\n"
        f"💰 <b>Продать за:</b> {sell_price} Coins\n\n"
        f"{footer()}"
    )
    
    # Удаляем текущее сообщение гаража/меню перед показом машины
    if call.from_user.id in GARAGE_MESSAGE_ID:
        try:
            await bot.delete_message(
                call.message.chat.id,
                GARAGE_MESSAGE_ID[call.from_user.id],
            )
        except Exception:
            pass
        del GARAGE_MESSAGE_ID[call.from_user.id]

    # Удаляем старый стикер и прошлое текстовое сообщение
    if call.from_user.id in LAST_CAR_VIEW_MESSAGE_IDS:
        try:
            old_sticker_id, old_main_id = LAST_CAR_VIEW_MESSAGE_IDS[call.from_user.id]
            if old_sticker_id:
                await bot.delete_message(call.message.chat.id, old_sticker_id)
            if old_main_id:
                await bot.delete_message(call.message.chat.id, old_main_id)
        except Exception:
            pass
    
    # СНАЧАЛА отправляем НОВЫЙ стикер (будет первым)
    sticker_msg_id = None
    sticker_id = card.get("sticker_id", "").strip()
    if sticker_id:
        try:
            sticker_msg = await call.message.answer_sticker(sticker_id)
            sticker_msg_id = sticker_msg.message_id
        except Exception as e:
            logger.warning(f"Failed to send sticker {sticker_id}: {e}")

    # Отправляем текстовое сообщение после стикера (стикер будет первым)
    main_msg = await call.message.answer(caption, reply_markup=kb, parse_mode="HTML")
    GARAGE_MESSAGE_ID[call.from_user.id] = main_msg.message_id
    LAST_CAR_VIEW_MESSAGE_IDS[call.from_user.id] = (sticker_msg_id, main_msg.message_id)


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
    sell_price = get_effective_sell_price(card, rarity_override=car["rarity"])

    day_key = current_day_key()
    sold_today = get_daily_sold_count(call.from_user.id, day_key)
    if sold_today >= DAILY_SELL_LIMIT:
        await call.answer(
            f"⛔ Лимит продаж на сегодня исчерпан: {DAILY_SELL_LIMIT}",
            show_alert=True,
        )
        return

    # Удаляем предыдущий стикер, если был
    if call.from_user.id in LAST_CAR_VIEW_MESSAGE_IDS:
        try:
            sticker_msg_id, _ = LAST_CAR_VIEW_MESSAGE_IDS[call.from_user.id]
            if sticker_msg_id:
                await bot.delete_message(call.message.chat.id, sticker_msg_id)
        except Exception:
            pass
        del LAST_CAR_VIEW_MESSAGE_IDS[call.from_user.id]

    # Продаём машину
    delete_car_from_garage(car_id)
    add_coins(call.from_user.id, sell_price)
    increment_daily_sold_count(call.from_user.id, day_key)
    await apply_daily_task_progress(call.from_user.id, "sell_car", notify_message=call.message)
    logger.info(
        "sell_completed user_id=%s car_id=%s card_name=%s price=%s",
        call.from_user.id,
        car_id,
        car.get("name"),
        sell_price,
    )

    # Редактируем сообщение
    await call.message.edit_text(
        f"{header()}\n\n"
        f"✅ <b>Машина продана!</b>\n\n"
        f"🚘 {card['name_ru']}\n"
        f"💰 <b>Получено:</b> +{sell_price} Coins\n"
        f"📉 <b>Продано сегодня:</b> {sold_today + 1}/{DAILY_SELL_LIMIT}\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔙 К гаражу", callback_data="menu:garage:0"),
                    InlineKeyboardButton(text="🏠 Меню", callback_data="start"),
                ]
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer("✅ Машина продана!")

# =========================
# GROUP COMMANDS (SAFE)
# =========================

@dp.message(Command("chat_id"))
async def chat_id_command(message: Message):
    if message.chat.type == "private":
        await message.answer(
            f"{header()}\n\n"
            f"🆔 Твой ID: {message.from_user.id}\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return

    await message.answer(
        f"{header()}\n\n"
        f"🆔 ID группы: {message.chat.id}\n\n"
        f"{footer()}",
        parse_mode="HTML",
    )

# =========================
# BOT ADDED TO GROUP
# =========================

@dp.my_chat_member()
async def bot_added_to_group(update: ChatMemberUpdated):
    if update.new_chat_member.status == "member":
        chat = update.chat
        if chat.type in ["group", "supergroup"]:
            bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
            title = chat.title or "группу"
            
            await update.from_user.bot.send_message(
                chat.id,
                f"{header()}\n\n"
                f"👋 Привет! Я добавлен в <b>{title}</b>!\n\n"
                f"🎮 Я игровой бот для сбора редких машин! Открывай кейсы, собирай коллекцию, продавай машины и зарабатывай монеты!\n\n"
                f"📝 Команды в группе:\n"
                f"• <code>кейс</code> - открыть бесплатный кейс\n"
                f"• <code>баланс</code> - узнать баланс\n\n"
                f"⚙️ <b>Для администрации:</b>\n"
                f"• <code>/welcome</code> - включить/отключить приветствие новых пользователей\n\n"
                f"<a href='{bot_link}'>Открыть бота в ЛС</a>, чтобы начать игру!\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
            logger.info("bot_added_to_group chat_id=%s chat_title=%s", chat.id, title)

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
            f"<a href='{bot_link}'>Открыть бота</a>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )


@dp.message(F.chat.type != "private", Command("welcome"))
async def welcome_settings(message: Message):
    if not await is_group_admin(message.chat.id, message.from_user.id):
        await message.answer(
            f"{header()}\n\n"
            f"⚙️ Команда только для администрации\n\n"
            f"{footer()}",
            parse_mode="HTML"
        )
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
        f"👋 <b>Приветствие новых пользователей:</b> {status}\n\n"
        f"{footer()}",
        reply_markup=kb,
        parse_mode="HTML",
    )

@dp.message(F.chat.type != "private", Command("garage"))
async def garage_group(message: Message):
    await message.answer(
        f"{header()}\n\n"
        "🚗 Гараж доступен в ЛС с ботом\n\n"
        f"{footer()}",
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("welcome:"))
async def welcome_toggle(call: CallbackQuery):
    if call.message.chat.type == "private":
        await call.answer("❌ Кнопка работает только в группах", show_alert=True)
        return
    if not await is_group_admin(call.message.chat.id, call.from_user.id):
        await call.answer("⚙️ Команда только для администрации", show_alert=True)
        return

    enabled = call.data.split(":", 1)[1] == "on"
    set_group_welcome_enabled(call.message.chat.id, enabled)
    status = "✅ Включено" if enabled else "❌ Выключено"

    try:
        await call.message.edit_text(
            f"{header()}\n\n"
            f"👋 <b>Приветствие новых пользователей:</b> {status}\n\n"
            f"{footer()}",
            reply_markup=call.message.reply_markup,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("welcome_toggle edit_text failed: %s", e)
    await call.answer("✅ Готово")


@dp.message(F.chat.type != "private", F.text.lower().regexp(r"(баланс|balance|coins)"))
async def balance_group(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await message.answer(
            f"{header()}\n\n"
            f"👤 {message.from_user.first_name}, сначала зарегистрируйся!\n\n"
            f"<a href='{bot_link}'>Открыть бота в ЛС</a>\n\n"
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
            f"<a href='{bot_link}'>Открыть бота в ЛС</a>\n\n"
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

    card_id = draw_free_case_card(message.from_user.id)
    
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
    increment_total_cases_opened(user["user_id"])
    increment_weekly_cases_opened(user["user_id"], current_week_key(), 1)
    increment_weekly_group_cases_opened(message.chat.id, user["user_id"], current_week_key(), 1)
    await apply_daily_task_progress(user["user_id"], "free_case", notify_message=message)
    if rarity in ("Rare", "Epic", "Legendary"):
        await apply_daily_task_progress(user["user_id"], "get_rare_plus", notify_message=message)
    add_coins(user["user_id"], FREE_CASE_BONUS_COINS)
    update_last_free_case_time(user["user_id"])
    logger.info(
        "group_case_opened user_id=%s chat_id=%s card_id=%s rarity=%s bonus=%s",
        message.from_user.id,
        message.chat.id,
        card_id,
        rarity,
        FREE_CASE_BONUS_COINS,
    )
    sell_price = get_effective_sell_price(card)

    caption = (
        f"{header()}\n\n"
        f"🎁 <b>КЕЙС {message.from_user.first_name}</b>\n\n"
        f"🚘 <b>{card['name_ru']}</b>\n"
        f"Редкость: {RARITY_EMOJI[rarity]} {RARITY_RU.get(rarity, rarity)}\n"
        f"💵 <b>Цена продажи:</b> {sell_price} Coins\n"
        f"💰 <b>Бонус:</b> +{FREE_CASE_BONUS_COINS} Coins\n\n"
        f"{footer()}"
    )
    
    success = await send_car_image(message, card, rarity, caption, user_id=message.from_user.id)
    if not success:
        # Если нет фото в группе - отправим просто текст
        await message.answer(caption, parse_mode="HTML")

# =========================
# TOP COMMAND
# =========================

@dp.message(F.chat.type != "private", Command("top"))
async def top_command(message: Message):
    top = await get_group_top_by_coins(message.chat.id, 10)

    text = f"{header()}\n\n🏆 <b>ТОП ЭТОЙ ГРУППЫ</b>\n\n"
    for i, row in enumerate(top, start=1):
        text += f"{i}. <b>{row['first_name']}</b> - {row['coins']} 💰\n"
    if not top:
        text += "Пока нет участников с профилем в боте.\n"
    text += f"\n{footer()}"
    
    await message.answer(text, parse_mode="HTML")


@dp.message(F.chat.type != "private", Command("topweek"))
async def top_week_command(message: Message):
    await process_group_weekly_rewards(message.chat.id)

    week_key = current_week_key()
    top = get_top_users_by_group_weekly_cases(message.chat.id, week_key, 10)

    text = f"{header()}\n\n📅 <b>ТОП НЕДЕЛИ В ЭТОЙ ГРУППЕ</b>\n<code>{week_key}</code>\n\n"
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, row in enumerate(top, start=1):
        text += f"{medals.get(i, f'{i}.')} <b>{row['first_name'] or 'Игрок'}</b> — {row['cases_opened']} кейсов\n"
    if not top:
        text += "Пока нет открытий кейсов на этой неделе.\n"
    text += f"\n{footer()}"

    await message.answer(text, parse_mode="HTML")

# =========================
# BALANCE COMMAND (GROUP EN)
# =========================

@dp.message(F.chat.type != "private", Command("balance"))
async def balance_command(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await message.answer(
            f"{header()}\n\n"
            f"👤 {message.from_user.first_name}, сначала зарегистрируйся!\n\n"
            f"<a href='{bot_link}'>Открыть бота</a>\n\n"
            f"{footer()}",
            parse_mode="HTML"
        )
        return
    
    await message.answer(
        f"{header()}\n\n"
        f"💰 {message.from_user.first_name}, баланс: {user['coins']} Coins\n\n"
        f"{footer()}",
        parse_mode="HTML",
    )

# =========================
# RUN
# =========================

async def main():
    try:
        init_db()
        global BOT_USERNAME
        global BOT_ID
        if not BOT_USERNAME:
            me = await bot.get_me()
            BOT_USERNAME = me.username
            BOT_ID = me.id
        
        logger.info("Bot started: %s", BOT_USERNAME)
        
        # Команды для личного чата
        await bot.set_my_commands([
            BotCommand(command="start", description="Начать игру"),
        ])
        
        # Команды для групп (только латиница)
        await bot.set_my_commands(
            [
                BotCommand(command="welcome", description="Приветствие новичков"),
                BotCommand(command="balance", description="Узнать баланс"),
                BotCommand(command="top", description="Топ игроков"),
            ],
            scope=BotCommandScopeAllGroupChats()
        )
        
        logger.info("Bot commands set")
        logger.info("Starting polling...")
        
        while True:
            try:
                await dp.start_polling(bot)
            except Exception as e:
                logger.error("Polling error: %s", e, exc_info=True)
                logger.info("Reconnecting in 5 seconds...")
                await asyncio.sleep(5)
        
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
    except Exception as e:
        logger.error("Fatal startup error: %s", e, exc_info=True)
    finally:
        await bot.session.close()
        logger.info("Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)