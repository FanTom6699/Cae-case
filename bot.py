import asyncio
import os
import json
import random
import logging
import math
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
    get_top_users_by_xp,
    get_top_users_by_race_wins,
    get_user_rank_by_xp,
    get_xp_analytics,
    get_economy_analytics,
    get_race_economy_analytics,
    get_users_page,
    search_users_by_nick,
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
    set_user_duplicate_streak,
    add_user_xp,
    set_user_level_round_rewarded,
    increment_weekly_cases_opened,
    get_top_users_by_weekly_cases,
    increment_weekly_group_cases_opened,
    get_top_users_by_group_weekly_cases,
    clear_group_weekly_cases_stats,
    clear_weekly_cases_stats,
    has_group_week_rewarded,
    mark_group_week_rewarded,
    has_global_week_rewarded,
    mark_global_week_rewarded,
    has_user_seen_global_week,
    mark_user_seen_global_week,
    get_all_user_ids,
    get_all_group_chat_ids,
    get_admin_summary_stats,
    add_race_result,
    get_user_race_stats,
)
from races import (
    apply_map_modifiers_to_stats,
    apply_tuning_upgrade,
    build_car_stats,
    ensure_race_profiles,
    get_car_profile,
    get_tuning_cost,
    is_tuning_maxed,
    load_race_maps,
    MAX_TUNE_LEVEL,
    make_bot_opponent,
    pick_random_race_map,
    render_race_frame,
    save_race_profiles,
    simulate_race,
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

with open("cards.json", "r", encoding="utf-8-sig") as f:
    CARDS = json.load(f)

def _is_active_card(card: dict) -> bool:
    return bool(str((card or {}).get("sticker_id", "")).strip())


ACTIVE_CARDS = {card_id: card for card_id, card in CARDS.items() if _is_active_card(card)}
COMMON_CARDS = [k for k, v in ACTIVE_CARDS.items() if v["rarity"] == "Common"]
RARE_CARDS = [k for k, v in ACTIVE_CARDS.items() if v["rarity"] == "Rare"]
EPIC_CARDS = [k for k, v in ACTIVE_CARDS.items() if v["rarity"] == "Epic"]
LEGENDARY_CARDS = [k for k, v in ACTIVE_CARDS.items() if v["rarity"] == "Legendary"]
ALL_CARDS = list(ACTIVE_CARDS.keys())
RACE_PROFILES = ensure_race_profiles(CARDS)
RACE_MAPS = load_race_maps()

FREE_CASE_COOLDOWN = timedelta(hours=4)
PAID_CASE_COOLDOWN = timedelta(seconds=int(os.getenv("PAID_CASE_COOLDOWN_SECONDS", "120")))
PAID_CASE_PRICE = int(os.getenv("PAID_CASE_PRICE", "45000"))
FREE_CASE_BONUS_COINS = int(os.getenv("FREE_CASE_BONUS_COINS", "0"))
DAILY_SELL_LIMIT = int(os.getenv("DAILY_SELL_LIMIT", "5"))
GARAGE_PAGE_SIZE = 5
GROUP_CASE_RATE_LIMIT_SECONDS = int(os.getenv("GROUP_CASE_RATE_LIMIT_SECONDS", "30"))
GROUP_CASE_RATE_LIMIT = {}
FEEDBACK_PENDING = {}
ADMIN_BROADCAST_PENDING = {}
ADMIN_PROFILE_LOOKUP_PENDING = set()
ADMIN_EDIT_LOOKUP_PENDING = set()
ADMIN_USER_FIND_PENDING = set()
ADMIN_USER_EDIT_PENDING = {}
ADMIN_DUPLICATE_PITY_PENDING = set()
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
    "Common": 0.40,
    "Rare": 0.44,
    "Epic": 0.05,
    "Legendary": 0.035,
}

SELL_PRICE_BOUNDS = {
    "Common": (2200, 10000),
    "Rare": (11000, 24000),
    "Epic": (26000, 78000),
    "Legendary": (85000, 220000),
}

DAILY_TASKS = {
    "free_case": {"title": "Открыть бесплатный кейс", "target": 1, "reward": 2000},
    "buy_standard": {"title": "Купить платный кейс", "target": 1, "reward": 3200},
    "sell_car": {"title": "Продать машину", "target": 1, "reward": 2600},
    "get_rare_plus": {"title": "Получить машину редкости Редкая и выше", "target": 1, "reward": 4200},
}

DAILY_TASK_XP = {
    "free_case": int(os.getenv("XP_TASK_FREE_CASE", "25")),
    "buy_standard": int(os.getenv("XP_TASK_BUY_STANDARD", "40")),
    "sell_car": int(os.getenv("XP_TASK_SELL_CAR", "30")),
    "get_rare_plus": int(os.getenv("XP_TASK_GET_RARE_PLUS", "55")),
}

STREAK_REWARDS = {
    1: 1200,
    2: 1800,
    3: 2500,
    4: 3200,
    5: 4200,
    6: 5400,
    7: 7000,
}

GROUP_WEEKLY_REWARDS = [30000, 20000, 12000]
GLOBAL_WEEKLY_REWARDS = [60000, 40000, 25000]

XP_GAIN_BY_RARITY = {
    "Common": int(os.getenv("XP_COMMON", "15")),
    "Rare": int(os.getenv("XP_RARE", "35")),
    "Epic": int(os.getenv("XP_EPIC", "63")),  # -30% XP за Epic
    "Legendary": int(os.getenv("XP_LEGENDARY", "220")),
}
DUPLICATE_REWARD_MULTIPLIER = {
    "Common": float(os.getenv("DUPLICATE_MULT_COMMON", "0.15")),
    "Rare": float(os.getenv("DUPLICATE_MULT_RARE", "0.17")),
    "Epic": float(os.getenv("DUPLICATE_MULT_EPIC", "0.19")),
    "Legendary": float(os.getenv("DUPLICATE_MULT_LEGENDARY", "0.22")),
}
LEVEL_BASE_XP = int(os.getenv("LEVEL_BASE_XP", "100"))
LEVEL_ROUND_STEP = int(os.getenv("LEVEL_ROUND_STEP", "5"))
MAX_LEVEL = int(os.getenv("MAX_LEVEL", "100"))
LEVEL_ROUND_BASE_REWARD = int(os.getenv("LEVEL_ROUND_BASE_REWARD", "10000"))
LEVEL_ROUND_STEP_BONUS = int(os.getenv("LEVEL_ROUND_STEP_BONUS", "2500"))
XP_NOTIFY_COOLDOWN_SECONDS = int(os.getenv("XP_NOTIFY_COOLDOWN_SECONDS", "10"))
XP_NOTIFY_LAST_TS = {}
DUPLICATE_PITY_THRESHOLD = int(os.getenv("DUPLICATE_PITY_THRESHOLD", "5"))

FAST_TAP_DAILY_LIMIT = int(os.getenv("FAST_TAP_DAILY_LIMIT", "3"))
FAST_TAP_WINDOW_SECONDS = int(os.getenv("FAST_TAP_WINDOW_SECONDS", "60"))
FAST_TAP_REWARD_COINS = int(os.getenv("FAST_TAP_REWARD_COINS", "2500"))
FAST_TAP_REWARD_XP = int(os.getenv("FAST_TAP_REWARD_XP", "15"))
FAST_TAP_START_HOUR = int(os.getenv("FAST_TAP_START_HOUR", "8"))
FAST_TAP_END_HOUR = int(os.getenv("FAST_TAP_END_HOUR", "24"))
FAST_TAP_SCHEDULER_TICK_SECONDS = int(os.getenv("FAST_TAP_SCHEDULER_TICK_SECONDS", "20"))
FAST_TAP_ACTIVE_ROUNDS = {}  # chat_id -> {round_id, message_id, expires_at, winner_id}
FAST_TAP_DAILY_COUNTER = {}  # (chat_id, day_key) -> count
FAST_TAP_DAILY_SCHEDULE = {}  # (chat_id, local_day_key) -> {"slots": [sec], "launched": set()}
RACE_TICK_DELAY_SECONDS = float(os.getenv("RACE_TICK_DELAY_SECONDS", "1.0"))
RACE_SELECTED_CAR_ID = {}  # user_id -> car_id
RACE_DUEL_INVITE_TIMEOUT_SECONDS = int(os.getenv("RACE_DUEL_INVITE_TIMEOUT_SECONDS", "60"))
RACE_DUEL_INIT_COOLDOWN_SECONDS = int(os.getenv("RACE_DUEL_INIT_COOLDOWN_SECONDS", "3600"))
RACE_DUEL_PENDING = {}  # (chat_id, message_id) -> {challenger_id, opponent_id, challenger_name, opponent_name, status}
RACE_DUEL_LAST_INIT_AT = {}  # user_id -> monotonic timestamp
PRIVATE_RACE_SEARCH_TIMEOUT_SECONDS = int(os.getenv("PRIVATE_RACE_SEARCH_TIMEOUT_SECONDS", "60"))
PRIVATE_RACE_REMATCH_BLOCK_SECONDS = int(os.getenv("PRIVATE_RACE_REMATCH_BLOCK_SECONDS", "3600"))
PRIVATE_RACE_QUEUE_BY_CLASS = {}  # class_code -> [entry]
PRIVATE_RACE_SEARCH_BY_USER = {}  # user_id -> entry
PRIVATE_RACE_LAST_PAIR_TS = {}  # (min_user_id, max_user_id) -> monotonic timestamp
RACE_RANKS = [
    {"key": "rookie", "emoji": "🥉", "name": "Новичок", "min_wins": 0, "reward": 1500},
    {"key": "street", "emoji": "🥉", "name": "Уличный гонщик", "min_wins": 50, "reward": 2200},
    {"key": "semi_pro", "emoji": "🥈", "name": "Полупрофи", "min_wins": 150, "reward": 3600},
    {"key": "pro", "emoji": "🥈", "name": "Профи", "min_wins": 300, "reward": 5200},
    {"key": "elite", "emoji": "🥇", "name": "Элита", "min_wins": 500, "reward": 7800},
    {"key": "legend", "emoji": "🏆", "name": "Легенда трассы", "min_wins": 750, "reward": 11500},
    {"key": "king", "emoji": "👑", "name": "Король трассы", "min_wins": 1000, "reward": 16000},
]

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
    """Выбирает машину из primary; если primary пусто, берет из fallback."""
    if primary_cards:
        return draw_weighted_card_by_price(primary_cards)

    if fallback_cards:
        return draw_weighted_card_by_price(fallback_cards)

    return None


def draw_card_with_pity(user_id, primary_cards, fallback_cards, duplicate_streak):
    """После N дублей подряд гарантирует новый автомобиль, если есть доступные."""
    threshold = max(1, int(DUPLICATE_PITY_THRESHOLD))

    if int(duplicate_streak or 0) >= threshold:
        missing_primary = [card_id for card_id in primary_cards if not has_car_in_garage(user_id, card_id)]
        if missing_primary:
            return draw_weighted_card_by_price(missing_primary), True

        missing_fallback = [card_id for card_id in fallback_cards if not has_car_in_garage(user_id, card_id)]
        if missing_fallback:
            return draw_weighted_card_by_price(missing_fallback), True

    return draw_card_from_lists(user_id, primary_cards, fallback_cards), False


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


def can_access_races(user_id: int) -> bool:
    return True


def clear_admin_pending_states(user_id: int):
    ADMIN_BROADCAST_PENDING.pop(user_id, None)
    ADMIN_PROFILE_LOOKUP_PENDING.discard(user_id)
    ADMIN_EDIT_LOOKUP_PENDING.discard(user_id)
    ADMIN_USER_FIND_PENDING.discard(user_id)
    ADMIN_USER_EDIT_PENDING.pop(user_id, None)
    ADMIN_DUPLICATE_PITY_PENDING.discard(user_id)


def build_admin_player_profile_view(target_user_id: int, back_callback: str = "menu:admin"):
    target_user = get_user(target_user_id)
    if not target_user:
        return None, None

    rarity_counts = get_user_rarity_counts(target_user_id)
    total_cars = sum(rarity_counts.values())
    username = target_user.get("username")
    nick = f"@{username}" if username else "Без ника"

    text = (
        f"{header()}\n\n"
        "👤 <b>Профиль игрока</b>\n\n"
        f"🪪 <b>Ник:</b> {nick}\n"
        f"🆔 <b>ID:</b> <code>{target_user_id}</code>\n"
        f"💰 <b>Баланс:</b> {target_user['coins']} Coins\n"
        f"🎁 <b>Открыто кейсов:</b> {target_user.get('total_cases_opened', 0)}\n"
        f"🚗 <b>Машин:</b> {total_cars}\n\n"
        "<b>По редкостям:</b>\n"
        f"⚪ Обычная: {rarity_counts.get('Common', 0)}\n"
        f"🔵 Редкая: {rarity_counts.get('Rare', 0)}\n"
        f"🟣 Эпическая: {rarity_counts.get('Epic', 0)}\n"
        f"🟡 Легендарная: {rarity_counts.get('Legendary', 0)}\n\n"
        f"{footer()}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редактировать этого игрока", callback_data=f"admin:edit_user_id:{target_user_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data=back_callback)],
        ]
    )
    return text, kb


def get_fast_tap_today_count(chat_id: int) -> int:
    return int(FAST_TAP_DAILY_COUNTER.get((int(chat_id), current_day_key()), 0))


def can_launch_fast_tap(chat_id: int):
    today_count = get_fast_tap_today_count(chat_id)
    if today_count >= max(1, FAST_TAP_DAILY_LIMIT):
        return False, today_count
    return True, today_count


async def close_fast_tap_round_later(chat_id: int, round_id: str):
    await asyncio.sleep(max(1, FAST_TAP_WINDOW_SECONDS))

    active = FAST_TAP_ACTIVE_ROUNDS.get(chat_id)
    if not active or active.get("round_id") != round_id:
        return

    if active.get("winner_id") is not None:
        FAST_TAP_ACTIVE_ROUNDS.pop(chat_id, None)
        return

    message_id = active.get("message_id")
    FAST_TAP_ACTIVE_ROUNDS.pop(chat_id, None)
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(
                f"{header()}\n\n"
                "⌛ <b>Раунд завершён</b>\n\n"
                f"Никто не нажал кнопку за {max(1, FAST_TAP_WINDOW_SECONDS // 60)} мин.\n\n"
                f"{footer()}"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


async def launch_fast_tap_round(chat_id: int):
    chat_id = int(chat_id)

    active = FAST_TAP_ACTIVE_ROUNDS.get(chat_id)
    if active and active.get("expires_at", 0) > time.time() and active.get("winner_id") is None:
        return False, "already_active"

    can_launch, today_count = can_launch_fast_tap(chat_id)
    if not can_launch:
        return False, "daily_limit"

    round_id = f"{int(time.time() * 1000)}{random.randint(100, 999)}"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ ЖМИ", callback_data=f"fasttap:click:{chat_id}:{round_id}")]
        ]
    )

    msg = await bot.send_message(
        chat_id,
        f"{header()}\n\n"
        "🚨 <b>Быстрый раунд</b>\n\n"
        "Кто первый нажмёт кнопку — заберёт награду!\n\n"
        f"🎁 Приз: +{fmt_coins(FAST_TAP_REWARD_COINS)} и +{fmt_xp(FAST_TAP_REWARD_XP)}\n"
        "⏳ Время: 1 минута\n\n"
        f"{footer()}",
        parse_mode="HTML",
        reply_markup=kb,
    )

    FAST_TAP_DAILY_COUNTER[(chat_id, current_day_key())] = today_count + 1
    FAST_TAP_ACTIVE_ROUNDS[chat_id] = {
        "round_id": round_id,
        "message_id": msg.message_id,
        "expires_at": time.time() + max(1, FAST_TAP_WINDOW_SECONDS),
        "winner_id": None,
    }
    asyncio.create_task(close_fast_tap_round_later(chat_id, round_id))
    return True, "ok"


def _fast_tap_local_now():
    return datetime.now()


def _fast_tap_local_day_key():
    return _fast_tap_local_now().date().isoformat()


def _fast_tap_window_bounds_seconds():
    start = max(0, min(23, int(FAST_TAP_START_HOUR))) * 3600
    end_hour = int(FAST_TAP_END_HOUR)
    end = max(start + 1, min(24, max(1, end_hour))) * 3600
    return start, end


def get_fast_tap_schedule(chat_id: int, day_key: str):
    key = (int(chat_id), str(day_key))
    schedule = FAST_TAP_DAILY_SCHEDULE.get(key)
    if schedule:
        return schedule

    start_sec, end_sec = _fast_tap_window_bounds_seconds()
    window = max(1, end_sec - start_sec)
    slots_count = max(1, int(FAST_TAP_DAILY_LIMIT))

    if slots_count >= window:
        offsets = list(range(window))
    else:
        offsets = random.sample(range(window), k=slots_count)

    slots = sorted(start_sec + offset for offset in offsets)
    schedule = {"slots": slots, "launched": set()}
    FAST_TAP_DAILY_SCHEDULE[key] = schedule
    return schedule


def _fast_tap_cleanup_old_day_data(current_local_day_key: str):
    keys_to_delete = [key for key in FAST_TAP_DAILY_SCHEDULE.keys() if key[1] != current_local_day_key]
    for key in keys_to_delete:
        FAST_TAP_DAILY_SCHEDULE.pop(key, None)


async def fast_tap_scheduler_loop():
    while True:
        try:
            now = _fast_tap_local_now()
            day_key = now.date().isoformat()
            _fast_tap_cleanup_old_day_data(day_key)

            start_sec, end_sec = _fast_tap_window_bounds_seconds()
            sec_of_day = (now.hour * 3600) + (now.minute * 60) + now.second
            if sec_of_day < start_sec or sec_of_day >= end_sec:
                await asyncio.sleep(max(5, FAST_TAP_SCHEDULER_TICK_SECONDS))
                continue

            for chat_id in get_all_group_chat_ids():
                active = FAST_TAP_ACTIVE_ROUNDS.get(chat_id)
                if active and active.get("expires_at", 0) > time.time() and active.get("winner_id") is None:
                    continue

                schedule = get_fast_tap_schedule(chat_id, day_key)
                for index, slot_sec in enumerate(schedule["slots"]):
                    if index in schedule["launched"]:
                        continue
                    if sec_of_day >= slot_sec:
                        ok, reason = await launch_fast_tap_round(chat_id)
                        if ok:
                            schedule["launched"].add(index)
                        elif reason == "daily_limit":
                            schedule["launched"].add(index)
                        break
        except Exception as e:
            logger.error("fast_tap_scheduler_loop error: %s", e)

        await asyncio.sleep(max(5, FAST_TAP_SCHEDULER_TICK_SECONDS))


def main_menu_kb(user_id: int = None):
    has_races_access = user_id is not None and can_access_races(user_id)

    kb = [
        [
            InlineKeyboardButton(text="🎁 Бесплатный кейс", callback_data="menu:free"),
            InlineKeyboardButton(text="💳 Купить кейс", callback_data="menu:buy_cases"),
        ],
        [
            InlineKeyboardButton(text="📅 Ежедневные задания", callback_data="menu:daily"),
            InlineKeyboardButton(text="🚗 Гараж", callback_data="menu:garage:0"),
        ],
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats"),
        ],
        [InlineKeyboardButton(text="📚 Дополнительно", callback_data="menu:more")]
        if not has_races_access
        else [
            InlineKeyboardButton(text="🏁 Гонки", callback_data="menu:races"),
            InlineKeyboardButton(text="📚 Дополнительно", callback_data="menu:more"),
        ],
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


def format_number(value):
    n = int(value or 0)
    sign = "-" if n < 0 else ""
    return f"{sign}{abs(n):,}".replace(",", " ")


def fmt_coins(value):
    return f"{format_number(value)} Coins"


def fmt_xp(value):
    return f"{format_number(value)} XP"


def get_race_rank_info(wins_count: int):
    wins = max(0, int(wins_count or 0))
    current = RACE_RANKS[0]
    next_rank = None

    for rank in RACE_RANKS:
        if wins >= rank["min_wins"]:
            current = rank
        elif next_rank is None:
            next_rank = rank
            break

    wins_to_next = 0
    if next_rank:
        wins_to_next = max(0, int(next_rank["min_wins"]) - wins)

    return {
        "current": current,
        "next": next_rank,
        "wins_to_next": wins_to_next,
    }


def get_user_race_car_for_duel(user_id: int):
    selected_car_id = RACE_SELECTED_CAR_ID.get(user_id)
    if selected_car_id:
        selected_car = get_car_by_id(selected_car_id)
        if selected_car and selected_car.get("user_id") == user_id:
            return selected_car
        RACE_SELECTED_CAR_ID.pop(user_id, None)

    cars = get_user_garage(user_id)
    if not cars:
        return None

    return cars[0]


def race_duel_initiator_rate_limit_ok(user_id: int):
    now = time.monotonic()
    last = RACE_DUEL_LAST_INIT_AT.get(int(user_id))
    if last is not None:
        remaining = int(max(0, RACE_DUEL_INIT_COOLDOWN_SECONDS - (now - last)))
        if remaining > 0:
            return False, remaining

    return True, 0


def mark_race_duel_initiator_used(user_id: int):
    RACE_DUEL_LAST_INIT_AT[int(user_id)] = time.monotonic()


def build_group_duel_result_text(
    challenger_id: int,
    opponent_id: int,
    challenger_name: str,
    opponent_name: str,
    with_meta: bool = False,
):
    def _pack(text: str, duel_played: bool = False):
        if with_meta:
            return text, duel_played
        return text

    challenger_user = get_user(challenger_id)
    opponent_user = get_user(opponent_id)
    if not challenger_user or not opponent_user:
        return _pack(
            f"{header()}\n\n"
            "⛔ Дуэль отменена: один из игроков не зарегистрирован в боте.\n\n"
            f"{footer()}"
        )

    challenger_car = get_user_race_car_for_duel(challenger_id)
    opponent_car = get_user_race_car_for_duel(opponent_id)
    if not challenger_car or not opponent_car:
        return _pack(
            f"{header()}\n\n"
            "🚘 Дуэль отменена: у одного из игроков нет машины в гараже.\n\n"
            f"{footer()}"
        )

    challenger_card_id = challenger_car.get("name", "")
    challenger_rarity = challenger_car.get("rarity", "Common")
    challenger_card = CARDS.get(challenger_card_id, {})
    challenger_car_name = challenger_card.get("name_ru") or challenger_card_id or "Машина"

    opponent_card_id = opponent_car.get("name", "")
    opponent_rarity = opponent_car.get("rarity", "Common")
    opponent_card = CARDS.get(opponent_card_id, {})
    opponent_car_name = opponent_card.get("name_ru") or opponent_card_id or "Машина"

    challenger_profile = get_car_profile(challenger_card_id, challenger_rarity, RACE_PROFILES)
    opponent_profile = get_car_profile(opponent_card_id, opponent_rarity, RACE_PROFILES)
    challenger_class = str(challenger_profile.get("class", "D")).upper()
    opponent_class = str(opponent_profile.get("class", "D")).upper()

    if challenger_class != opponent_class:
        return _pack(
            f"{header()}\n\n"
            "⛔ У вас разные классы автомобиля — дуэль невозможна.\n\n"
            f"👤 {challenger_name}: <b>{challenger_car_name}</b> — класс <b>{challenger_class}</b>\n"
            f"👤 {opponent_name}: <b>{opponent_car_name}</b> — класс <b>{opponent_class}</b>\n\n"
            "Выберите машины одинакового класса и повторите дуэль.\n\n"
            f"{footer()}"
        )

    challenger_stats = build_car_stats(challenger_card_id, challenger_rarity, race_profiles=RACE_PROFILES)
    opponent_stats = build_car_stats(opponent_card_id, opponent_rarity, race_profiles=RACE_PROFILES)

    selected_map = pick_random_race_map(RACE_MAPS)
    map_name = selected_map.get("name_ru", "Трек")
    map_description = selected_map.get("description_ru", "")
    challenger_stats_on_map = apply_map_modifiers_to_stats(challenger_stats, selected_map)
    opponent_stats_on_map = apply_map_modifiers_to_stats(opponent_stats, selected_map)

    race_result = simulate_race(challenger_stats_on_map, opponent_stats_on_map, ticks_total=12)
    winner = race_result.get("winner")
    winner_reason = str(race_result.get("winner_reason") or "")
    frames = race_result.get("frames") or []

    challenger_power = (
        0.55 * challenger_stats_on_map["speed"]
        + 0.25 * challenger_stats_on_map["accel"]
        + 0.12 * challenger_stats_on_map["grip"]
        + 0.08 * challenger_stats_on_map["reliability"]
    )
    opponent_power = (
        0.55 * opponent_stats_on_map["speed"]
        + 0.25 * opponent_stats_on_map["accel"]
        + 0.12 * opponent_stats_on_map["grip"]
        + 0.08 * opponent_stats_on_map["reliability"]
    )

    speed_diff = challenger_stats_on_map["speed"] - opponent_stats_on_map["speed"]
    accel_diff = challenger_stats_on_map["accel"] - opponent_stats_on_map["accel"]
    stability_diff = (
        challenger_stats_on_map["grip"] + challenger_stats_on_map["reliability"]
    ) - (
        opponent_stats_on_map["grip"] + opponent_stats_on_map["reliability"]
    )

    winner_advantages = []
    if winner == "player":
        winner_advantages = [
            ("скорость", speed_diff),
            ("разгон", accel_diff),
            ("стабильность", stability_diff),
        ]
        winner_advantages = [(name, value) for name, value in winner_advantages if value > 0]
        winner_advantages.sort(key=lambda x: abs(x[1]), reverse=True)
        if winner_advantages:
            top_metric, top_value = winner_advantages[0]
            explain_line = (
                f"Ключевой фактор победителя: <b>{top_metric}</b> "
                f"(+{abs(top_value):.0f}) у {challenger_name}"
            )
        else:
            explain_line = f"Ключевой фактор победителя: у {challenger_name} не было явного перевеса по статам"
    elif winner == "opponent":
        winner_advantages = [
            ("скорость", -speed_diff),
            ("разгон", -accel_diff),
            ("стабильность", -stability_diff),
        ]
        winner_advantages = [(name, value) for name, value in winner_advantages if value > 0]
        winner_advantages.sort(key=lambda x: abs(x[1]), reverse=True)
        if winner_advantages:
            top_metric, top_value = winner_advantages[0]
            explain_line = (
                f"Ключевой фактор победителя: <b>{top_metric}</b> "
                f"(+{abs(top_value):.0f}) у {opponent_name}"
            )
        else:
            explain_line = f"Ключевой фактор победителя: у {opponent_name} не было явного перевеса по статам"
    else:
        reasons = [
            (abs(speed_diff), "скорость", speed_diff),
            (abs(accel_diff), "разгон", accel_diff),
            (abs(stability_diff), "стабильность", stability_diff),
        ]
        reasons.sort(key=lambda x: x[0], reverse=True)
        top_metric, top_value = reasons[0][1], reasons[0][2]
        if top_value > 0:
            explain_line = f"Ключевой фактор: <b>{top_metric}</b> в пользу {challenger_name}"
        elif top_value < 0:
            explain_line = f"Ключевой фактор: <b>{top_metric}</b> в пользу {opponent_name}"
        else:
            explain_line = "Ключевой фактор: <b>почти равные характеристики</b>"

    tempo_gap = challenger_power - opponent_power
    if tempo_gap > 0:
        tempo_line = f"• По статам: {challenger_name} сильнее на <b>{abs(tempo_gap):.1f}</b> балла"
    elif tempo_gap < 0:
        tempo_line = f"• По статам: {opponent_name} сильнее на <b>{abs(tempo_gap):.1f}</b> балла"
    else:
        tempo_line = "• По статам: силы машин равны"

    if frames:
        start_diff = float(frames[0].get("player_progress", 0.0)) - float(frames[0].get("opponent_progress", 0.0))
        if abs(start_diff) < 0.25:
            start_line = "• Старт: без явного лидера"
        elif start_diff > 0:
            start_line = f"• Старт: {challenger_name} начал лучше и вёл на <b>{abs(start_diff):.1f}%</b>"
        else:
            start_line = f"• Старт: {opponent_name} начал лучше и вёл на <b>{abs(start_diff):.1f}%</b>"

        peak_frame = max(
            frames,
            key=lambda frame: abs(
                float(frame.get("player_progress", 0.0)) - float(frame.get("opponent_progress", 0.0))
            ),
        )
        peak_gap = float(peak_frame.get("player_progress", 0.0)) - float(peak_frame.get("opponent_progress", 0.0))
        if abs(peak_gap) < 0.25:
            peak_line = "• Самый большой отрыв: минимальный (почти паритет)"
        elif peak_gap > 0:
            peak_line = f"• Самый большой отрыв: {challenger_name} вёл на <b>{abs(peak_gap):.1f}%</b>"
        else:
            peak_line = f"• Самый большой отрыв: {opponent_name} вёл на <b>{abs(peak_gap):.1f}%</b>"
    else:
        start_line = "• Старт: данных нет"
        peak_line = "• Самый большой отрыв: данных нет"

    player_time_s = float(race_result.get("player_time_s", 0.0))
    opponent_time_s = float(race_result.get("opponent_time_s", 0.0))
    time_gap = abs(player_time_s - opponent_time_s)
    finish_gap_ms = int(round(time_gap * 1000.0))
    if winner == "player":
        finish_line = f"• Финиш: {challenger_name} быстрее на <b>{time_gap:.2f} c</b>"
    elif winner == "opponent":
        finish_line = f"• Финиш: {opponent_name} быстрее на <b>{time_gap:.2f} c</b>"
    else:
        finish_line = "• Финиш: фотофиниш, разница минимальна"

    if winner == "player":
        if winner_reason == "photo_finish_time":
            decision_line = (
                f"• Решающий момент: {challenger_name} выиграл фотофиниш по времени "
                f"(<b>{max(1, finish_gap_ms)} мс</b>)"
            )
        else:
            decision_line = f"• Решающий момент: {challenger_name} удержал лидерство по дистанции"
    elif winner == "opponent":
        if winner_reason == "photo_finish_time":
            decision_line = (
                f"• Решающий момент: {opponent_name} выиграл фотофиниш по времени "
                f"(<b>{max(1, finish_gap_ms)} мс</b>)"
            )
        else:
            decision_line = f"• Решающий момент: {opponent_name} удержал лидерство по дистанции"
    else:
        if finish_gap_ms > 0:
            decision_line = f"• Решающий момент: фотофиниш (<b>{finish_gap_ms} мс</b>) — зафиксирована ничья"
        else:
            decision_line = "• Решающий момент: разница меньше <b>1 мс</b> — зафиксирована ничья"

    if winner == "player":
        advantage_parts = []
        if speed_diff > 0:
            advantage_parts.append(f"скорость +{abs(speed_diff):.0f}")
        if accel_diff > 0:
            advantage_parts.append(f"разгон +{abs(accel_diff):.0f}")
        if stability_diff > 0:
            advantage_parts.append(f"стабильность +{abs(stability_diff):.0f}")
        if advantage_parts:
            advantages_line = f"• Преимущества победителя: {', '.join(advantage_parts)}"
        else:
            advantages_line = f"• Преимущества победителя: по статам паритет, {challenger_name} дожал на дистанции"
    elif winner == "opponent":
        advantage_parts = []
        if speed_diff < 0:
            advantage_parts.append(f"скорость +{abs(speed_diff):.0f}")
        if accel_diff < 0:
            advantage_parts.append(f"разгон +{abs(accel_diff):.0f}")
        if stability_diff < 0:
            advantage_parts.append(f"стабильность +{abs(stability_diff):.0f}")
        if advantage_parts:
            advantages_line = f"• Преимущества победителя: {', '.join(advantage_parts)}"
        else:
            advantages_line = f"• Преимущества победителя: по статам паритет, {opponent_name} дожал на дистанции"
    else:
        advantages_line = "• Преимущества по статам: явного перевеса не было"

    track_mods = selected_map.get("modifiers", {}) if isinstance(selected_map.get("modifiers", {}), dict) else {}
    mod_labels = {
        "speed": "скорость",
        "accel": "разгон",
        "grip": "сцепление",
        "reliability": "надёжность",
    }
    active_modifiers = []
    for field, label in mod_labels.items():
        modifier = float(track_mods.get(field, 1.0))
        diff_pct = (modifier - 1.0) * 100.0
        if abs(diff_pct) >= 0.5:
            active_modifiers.append(f"{label} {'+' if diff_pct > 0 else ''}{diff_pct:.0f}%")

    if active_modifiers:
        track_line = f"• Влияние трека: {', '.join(active_modifiers)}"
    else:
        track_line = "• Влияние трека: нейтральный профиль"

    equal_stats = speed_diff == 0 and accel_diff == 0 and stability_diff == 0
    upset = (winner == "player" and tempo_gap < 0) or (winner == "opponent" and tempo_gap > 0)
    if equal_stats:
        randomness_line = "• Статы равны — в таком случае исход часто решает удача в конкретном заезде"
    elif upset:
        randomness_line = "• Победа при более слабых статах — в этом заезде удача была на стороне победителя"
    else:
        randomness_line = ""

    near_equal_stats = (
        abs(speed_diff) <= 1
        and abs(accel_diff) <= 1
        and abs(stability_diff) <= 2
        and abs(tempo_gap) <= 0.8
    )
    if equal_stats:
        chance_line = "• Оценка перед стартом: шансы были практически <b>50/50</b>"
        parity_explain_line = "⚖️ <b>Пояснение:</b> машины равны по характеристикам, поэтому победитель может определиться только на последних метрах."
    elif near_equal_stats:
        chance_line = "• Оценка перед стартом: шансы были близки к <b>50/50</b>"
        parity_explain_line = "⚖️ <b>Пояснение:</b> машины почти равны, поэтому в одном заезде может победить один, а в следующем — другой."
    else:
        chance_line = ""
        parity_explain_line = ""

    reward_line = ""
    rank_line = ""

    if winner == "player":
        add_race_result(challenger_id, "win")
        add_race_result(opponent_id, "loss")
        winner_id = challenger_id
        winner_name = challenger_name
        winner_before_wins = int(challenger_user.get("race_wins", 0))
        winner_stats = get_user_race_stats(winner_id)
        winner_rank_before = get_race_rank_info(winner_before_wins)["current"]
        winner_rank_after = get_race_rank_info(int(winner_stats.get("wins", 0)))["current"]
        reward_coins = int(winner_rank_after["reward"])
        add_coins(winner_id, reward_coins, source=f"race_duel_win_{winner_rank_after['key']}")
        reward_line = f"💸 Награда победителю: +<b>{fmt_coins(reward_coins)}</b>\n"
        if winner_rank_before["key"] != winner_rank_after["key"]:
            rank_line = f"🎉 Новый ранг: {winner_rank_after['emoji']} <b>{winner_rank_after['name']}</b>\n"
        result_line = f"🏆 Победитель: <b>{winner_name}</b>"
    elif winner == "opponent":
        add_race_result(challenger_id, "loss")
        add_race_result(opponent_id, "win")
        winner_id = opponent_id
        winner_name = opponent_name
        winner_before_wins = int(opponent_user.get("race_wins", 0))
        winner_stats = get_user_race_stats(winner_id)
        winner_rank_before = get_race_rank_info(winner_before_wins)["current"]
        winner_rank_after = get_race_rank_info(int(winner_stats.get("wins", 0)))["current"]
        reward_coins = int(winner_rank_after["reward"])
        add_coins(winner_id, reward_coins, source=f"race_duel_win_{winner_rank_after['key']}")
        reward_line = f"💸 Награда победителю: +<b>{fmt_coins(reward_coins)}</b>\n"
        if winner_rank_before["key"] != winner_rank_after["key"]:
            rank_line = f"🎉 Новый ранг: {winner_rank_after['emoji']} <b>{winner_rank_after['name']}</b>\n"
        result_line = f"🏆 Победитель: <b>{winner_name}</b>"
    else:
        add_race_result(challenger_id, "draw")
        add_race_result(opponent_id, "draw")
        result_line = "🤝 Ничья"

    challenger_total_stats = get_user_race_stats(challenger_id)
    opponent_total_stats = get_user_race_stats(opponent_id)

    return _pack(
        f"{header()}\n\n"
        "🏁 <b>Групповая дуэль</b>\n\n"
        f"📊 Класс заезда: <b>{challenger_class}</b>\n"
        f"🗺 Трек: <b>{map_name}</b>\n"
        f"{map_description}\n"
        f"👤 {challenger_name}: <b>{challenger_car_name}</b>\n"
        f"👤 {opponent_name}: <b>{opponent_car_name}</b>\n\n"
        "<b>Итог по дистанции:</b>\n"
        f"• {challenger_name}: <b>{int(round(race_result['player_progress']))}%</b>\n"
        f"• {opponent_name}: <b>{int(round(race_result['opponent_progress']))}%</b>\n\n"
        "<b>Время прохождения:</b>\n"
        f"• {challenger_name}: <b>{race_result['player_time_s']:.2f} c</b>\n"
        f"• {opponent_name}: <b>{race_result['opponent_time_s']:.2f} c</b>\n\n"
        "<b>Сравнение характеристик:</b>\n"
        f"• {challenger_name}: общая сила <b>{challenger_power:.1f}</b> | ⚡{challenger_stats_on_map['speed']} 🚀{challenger_stats_on_map['accel']} 🛞{challenger_stats_on_map['grip']} 🛡{challenger_stats_on_map['reliability']}\n"
        f"• {opponent_name}: общая сила <b>{opponent_power:.1f}</b> | ⚡{opponent_stats_on_map['speed']} 🚀{opponent_stats_on_map['accel']} 🛞{opponent_stats_on_map['grip']} 🛡{opponent_stats_on_map['reliability']}\n"
        f"• {explain_line}\n\n"
        "<b>Почему такой результат:</b>\n"
        f"{tempo_line}\n"
        f"{start_line}\n"
        f"{peak_line}\n"
        f"{finish_line}\n"
        f"{decision_line}\n"
        f"{advantages_line}\n"
        f"{track_line}\n"
        f"{(chance_line + chr(10)) if chance_line else ''}"
        f"{(randomness_line + chr(10)) if randomness_line else ''}\n"
        f"{(parity_explain_line + chr(10) + chr(10)) if parity_explain_line else ''}"
        f"{result_line}\n"
        f"{reward_line}"
        f"{rank_line}"
        "\n"
        "<b>Статистика после дуэли:</b>\n"
        f"• {challenger_name}: <b>{challenger_total_stats['wins']}/{challenger_total_stats['losses']}/{challenger_total_stats['draws']}</b> (В/П/Н)\n"
        f"• {opponent_name}: <b>{opponent_total_stats['wins']}/{opponent_total_stats['losses']}/{opponent_total_stats['draws']}</b> (В/П/Н)\n\n"
        f"{footer()}"
    , duel_played=True)


async def expire_race_duel_invite_later(chat_id: int, message_id: int, timeout_seconds: int):
    await asyncio.sleep(max(5, int(timeout_seconds or 60)))

    state_key = (chat_id, message_id)
    duel_state = RACE_DUEL_PENDING.get(state_key)
    if not duel_state or duel_state.get("status") != "pending":
        return

    challenger_name = duel_state.get("challenger_name") or "Игрок"
    opponent_name = duel_state.get("opponent_name") or "Игрок"
    RACE_DUEL_PENDING.pop(state_key, None)

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(
                f"{header()}\n\n"
                "🏁 <b>Вызов на дуэль</b>\n\n"
                f"👤 <b>{opponent_name}</b> не ответил на вызов от <b>{challenger_name}</b>.\n"
                "⌛ Время ожидания истекло (1 минута).\n\n"
                f"{footer()}"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


def _private_pair_key(user_a: int, user_b: int):
    first = int(min(user_a, user_b))
    second = int(max(user_a, user_b))
    return (first, second)


def _private_rematch_block_remaining(user_a: int, user_b: int, now_ts: float | None = None) -> int:
    now_value = float(time.monotonic() if now_ts is None else now_ts)
    last_ts = PRIVATE_RACE_LAST_PAIR_TS.get(_private_pair_key(user_a, user_b))
    if last_ts is None:
        return 0
    return int(max(0, PRIVATE_RACE_REMATCH_BLOCK_SECONDS - (now_value - last_ts)))


def _remove_private_search_entry(user_id: int):
    existing = PRIVATE_RACE_SEARCH_BY_USER.pop(int(user_id), None)
    if not existing:
        return

    class_code = str(existing.get("class_code", "")).upper()
    queue = PRIVATE_RACE_QUEUE_BY_CLASS.get(class_code, [])
    PRIVATE_RACE_QUEUE_BY_CLASS[class_code] = [
        item for item in queue
        if int(item.get("user_id", 0)) != int(user_id)
    ]


async def _expire_private_race_search_later(user_id: int, token: str):
    await asyncio.sleep(max(5, int(PRIVATE_RACE_SEARCH_TIMEOUT_SECONDS)))

    active = PRIVATE_RACE_SEARCH_BY_USER.get(int(user_id))
    if not active or str(active.get("token")) != str(token):
        return

    chat_id = int(active.get("chat_id"))
    message_id = int(active.get("message_id"))
    class_code = str(active.get("class_code", "?")).upper()
    _remove_private_search_entry(user_id)

    timeout_text = (
        f"{header()}\n\n"
        "🔎 <b>Подбор соперника</b>\n\n"
        f"Класс: <b>{class_code}</b>\n"
        "⌛ За 1 минуту соперник не найден.\n\n"
        "Нажми <b>Подбор снова</b>, чтобы повторить поиск.\n\n"
        f"{footer()}"
    )
    timeout_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Подбор снова", callback_data="races:vs_bot")],
            [InlineKeyboardButton(text="❌ Отменить поиск", callback_data="races:search:cancel")],
            [InlineKeyboardButton(text="🔙 К гонкам", callback_data="menu:races")],
        ]
    )

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=timeout_text,
            parse_mode="HTML",
            reply_markup=timeout_kb,
        )
    except Exception:
        try:
            await bot.send_message(chat_id, timeout_text, parse_mode="HTML", reply_markup=timeout_kb)
        except Exception:
            pass


async def _publish_private_race_result(entry_a: dict, entry_b: dict):
    user_a = int(entry_a.get("user_id"))
    user_b = int(entry_b.get("user_id"))
    name_a = entry_a.get("user_name") or "Игрок"
    name_b = entry_b.get("user_name") or "Игрок"

    result_text = build_group_duel_result_text(user_a, user_b, name_a, name_b).replace(
        "🏁 <b>Групповая дуэль</b>",
        "🏁 <b>Дуэль в ЛС</b>",
    )
    result_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Подбор снова", callback_data="races:vs_bot:new")],
            [InlineKeyboardButton(text="📊 Статистика гонок", callback_data="races:stats:new")],
            [InlineKeyboardButton(text="🔙 К гонкам", callback_data="menu:races:new")],
        ]
    )

    for item in (entry_a, entry_b):
        chat_id = int(item.get("chat_id"))
        message_id = int(item.get("message_id"))
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=result_text,
                parse_mode="HTML",
                reply_markup=result_kb,
            )
        except Exception:
            try:
                await bot.send_message(chat_id, result_text, parse_mode="HTML", reply_markup=result_kb)
            except Exception:
                pass


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


def get_level_by_xp(xp_total: int) -> int:
    xp = max(0, int(xp_total or 0))
    base = max(1, LEVEL_BASE_XP)
    level = int(math.isqrt(xp // base) + 1)
    return min(max(1, level), max(1, MAX_LEVEL))


def get_next_level_xp(level: int) -> int:
    lvl = max(1, int(level or 1))
    max_level = max(1, MAX_LEVEL)
    if lvl >= max_level:
        return 0
    base = max(1, LEVEL_BASE_XP)
    return base * (lvl ** 2)


def get_level_floor_xp(level: int) -> int:
    lvl = max(1, int(level or 1))
    base = max(1, LEVEL_BASE_XP)
    if lvl <= 1:
        return 0
    return base * ((lvl - 1) ** 2)


def render_progress_bar(current_value: int, max_value: int, width: int = 6) -> str:
    max_v = max(1, int(max_value or 1))
    cur_v = max(0, min(int(current_value or 0), max_v))
    w = max(4, int(width or 6))
    ratio = cur_v / max_v
    filled = int(round(ratio * w))
    filled = max(0, min(filled, w))
    empty = w - filled
    percent = int(round(ratio * 100))
    return f"{'🟩' * filled}{'⬜' * empty} {percent}%"


def get_round_level_reward(level: int) -> int:
    step = max(1, LEVEL_ROUND_STEP)
    milestone = max(step, int(level // step) * step)
    milestone_index = max(1, milestone // step)
    return LEVEL_ROUND_BASE_REWARD + (milestone_index - 1) * LEVEL_ROUND_STEP_BONUS


async def apply_xp_amount_progress(user_id: int, xp_gain: int, notify_message: Message = None, source: str = None):
    if xp_gain <= 0:
        return

    before = get_user(user_id)
    if not before:
        return

    before_xp = int(before.get("xp_total") or 0)
    before_level = get_level_by_xp(before_xp)
    before_round_rewarded = int(before.get("level_round_rewarded") or 0)

    add_user_xp(user_id, xp_gain, source=source)

    after = get_user(user_id)
    if not after:
        return

    after_xp = int(after.get("xp_total") or 0)
    after_level = get_level_by_xp(after_xp)
    next_level_xp = get_next_level_xp(after_level)
    xp_to_next_level = 0 if next_level_xp <= 0 else max(0, next_level_xp - after_xp)

    now_ts = time.monotonic()
    last_notify_ts = XP_NOTIFY_LAST_TS.get(user_id, 0)
    can_notify = notify_message is not None and (now_ts - last_notify_ts >= max(0, XP_NOTIFY_COOLDOWN_SECONDS))

    if can_notify and after_level > before_level:
        next_level_line = (
            "🎯 До следующего уровня: <b>MAX</b>\n"
            if after_level >= max(1, MAX_LEVEL)
            else f"🎯 До следующего уровня: {fmt_xp(xp_to_next_level)}\n"
        )
        await notify_message.answer(
            f"{header()}\n\n"
            "🏅 <b>Новый уровень!</b>\n\n"
            f"⭐ Опыт: {fmt_xp(after_xp)}\n"
            f"📈 Уровень: <b>{before_level} → {after_level}</b>\n"
            f"{next_level_line}\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        XP_NOTIFY_LAST_TS[user_id] = now_ts

    step = max(1, LEVEL_ROUND_STEP)
    max_level = max(1, MAX_LEVEL)
    capped_after_level = min(after_level, max_level)
    next_round_level = max(step, ((before_round_rewarded // step) + 1) * step)
    reached_round_levels = []
    level_cursor = next_round_level
    while level_cursor <= capped_after_level:
        reached_round_levels.append(level_cursor)
        level_cursor += step

    if reached_round_levels:
        total_bonus = sum(get_round_level_reward(level) for level in reached_round_levels)
        add_coins(user_id, total_bonus, source="level_round_reward")
        set_user_level_round_rewarded(user_id, reached_round_levels[-1])

        if can_notify:
            rounds_text = ", ".join(str(level) for level in reached_round_levels)
            await notify_message.answer(
                f"{header()}\n\n"
                "🎁 <b>Награда за круглый уровень!</b>\n\n"
                f"🏁 Уровни: {rounds_text}\n"
                f"💰 Награда: +{fmt_coins(total_bonus)}\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
            XP_NOTIFY_LAST_TS[user_id] = time.monotonic()


async def apply_xp_progress(user_id: int, rarity: str, notify_message: Message = None):
    xp_gain = int(XP_GAIN_BY_RARITY.get(rarity, XP_GAIN_BY_RARITY["Common"]))
    source_key = f"case_{str(rarity or 'Common').lower()}"
    await apply_xp_amount_progress(user_id, xp_gain, notify_message=notify_message, source=source_key)


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
        "📅 <b>Ежедневные задания доступны</b>\n\n"
        "Зайди в раздел <b>Ежедневные задания</b> и забери награды.\n\n"
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
    add_coins(user["user_id"], reward, source="streak_reward")

    await target.answer(
        f"{header()}\n\n"
        "🔥 <b>Ежедневный вход!</b>\n\n"
        f"Серия: <b>{current_streak}</b> дн.\n"
        f"🎁 Награда: +{fmt_coins(reward)}\n"
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
        add_coins(row["user_id"], reward, source="weekly_group_reward")
        lines.append(
            f"{medals[i]} <b>{row['first_name'] or 'Игрок'}</b> — {row['cases_opened']} кейсов (+{reward} Coins)"
        )

    mark_group_week_rewarded(chat_id, prev_week)
    clear_group_weekly_cases_stats(chat_id, prev_week)
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
        add_coins(row["user_id"], GLOBAL_WEEKLY_REWARDS[i], source="weekly_global_reward")

    mark_global_week_rewarded(prev_week)
    clear_weekly_cases_stats(prev_week)

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
        "ℹ️ Недельная статистика обновлена: начинается новый соревновательный цикл.\n\n"
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
    if not top:
        return

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
        f"{chr(10).join(lines)}\n"
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
        task_xp = int(DAILY_TASK_XP.get(task_key, 0))
        add_coins(user_id, task["reward"], source=f"daily_task_{task_key}")
        await apply_xp_amount_progress(user_id, task_xp, notify_message=notify_message, source=f"task_{task_key}")
        mark_daily_task_rewarded(user_id, day_key, task_key)

        try:
            await bot.send_message(
                user_id,
                f"{header()}\n\n"
                "✅ <b>Задание выполнено!</b>\n\n"
                f"📌 {task['title']}\n"
                f"🎁 Награда: +{fmt_coins(task['reward'])}\n"
                f"⭐ Опыт: +{fmt_xp(task_xp)}\n\n"
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


def get_cars_by_rarity(rarity: str):
    rows = []
    for car_key, card in CARDS.items():
        if card.get("rarity") != rarity:
            continue
        rows.append((car_key, card.get("name_ru", car_key)))
    rows.sort(key=lambda item: item[1].lower())
    return rows


def rarity_slug_to_value(slug: str):
    mapping = {
        "common": "Common",
        "rare": "Rare",
        "epic": "Epic",
        "legendary": "Legendary",
    }
    return mapping.get(slug)


def rarity_value_to_label(rarity: str):
    mapping = {
        "Common": "⚪ Обычные",
        "Rare": "🔵 Редкие",
        "Epic": "🟣 Эпические",
        "Legendary": "🟡 Легендарные",
    }
    return mapping.get(rarity, rarity)

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


def get_duplicate_reward_coins(card, rarity_override=None):
    rarity = rarity_override or card.get("rarity", "Common")
    base_sell = get_effective_sell_price(card, rarity_override=rarity)
    if base_sell <= 0:
        return 0
    ratio = DUPLICATE_REWARD_MULTIPLIER.get(rarity, 0.35)
    return int(round(base_sell * ratio))


async def send_stats(target, from_callback=False):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Топ по Coins", callback_data="stats:coins")],
            [InlineKeyboardButton(text="🚗 Топ по коллекции", callback_data="stats:collection")],
            [InlineKeyboardButton(text="📅 Топ недели", callback_data="stats:week_cases")],
            [InlineKeyboardButton(text="🏁 Топ по победам", callback_data="stats:race_wins")],
            [InlineKeyboardButton(text="🏅 Топ по уровню", callback_data="stats:level")],
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
    elif stat_type == "level":
        if call.message.chat.type != "private":
            await call.answer("⛔ Доступно только в ЛС", show_alert=True)
            return
        top = get_top_users_by_xp(10)
        title = "🏅 <b>ТОП ПО УРОВНЮ</b>"
        line_format = lambda i, row, medals: f"{medals.get(i, f'{i}.')} <b>{row['first_name'] or 'Игрок'}</b> — {get_level_by_xp(row.get('xp_total', 0))} ур."
    elif stat_type == "week_cases":
        week_key = current_week_key()
        top = get_top_users_by_weekly_cases(week_key, 10)
        title = f"📅 <b>ТОП НЕДЕЛИ ПО ОТКРЫТИЯМ</b>\n<code>{week_key}</code>"
        line_format = lambda i, row, medals: f"{medals.get(i, f'{i}.')} <b>{row['first_name'] or 'Игрок'}</b> — {row['cases_opened']} кейсов"
    elif stat_type == "race_wins":
        top = get_top_users_by_race_wins(10)
        title = "🏁 <b>ТОП ПО ПОБЕДАМ В ГОНКАХ</b>"
        line_format = lambda i, row, medals: f"{medals.get(i, f'{i}.')} <b>{row['first_name'] or 'Игрок'}</b> — {row['race_wins']} побед ({row['race_total']} заездов)"
    else:
        top = get_top_users_by_collection(10)
        total_cards = len(CARDS)
        title = "🚗 <b>ТОП ПО КОЛЛЕКЦИИ</b>"
        line_format = lambda i, row, medals: f"{medals.get(i, f'{i}.')} <b>{row['first_name'] or 'Игрок'}</b> — {row['count']}/{total_cards} 🚗"

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = []
    has_real_race_wins = True
    if stat_type == "race_wins":
        has_real_race_wins = any(int(row.get("race_wins", 0)) > 0 for row in top)

    if stat_type == "race_wins" and not has_real_race_wins:
        lines = []
    else:
        for i, row in enumerate(top, start=1):
            lines.append(line_format(i, row, medals))

    viewer = get_user(call.from_user.id)
    viewer_level_line = ""
    if viewer:
        viewer_xp = int(viewer.get("xp_total") or 0)
        viewer_level = get_level_by_xp(viewer_xp)
        rank_line = ""
        if stat_type == "level":
            viewer_rank = get_user_rank_by_xp(call.from_user.id)
            if viewer_rank:
                rank_line = f"\n🏆 <b>Твой ранг:</b> #{viewer_rank}"
        viewer_level_line = f"\n👤 <b>Твой уровень:</b> {viewer_level} ({viewer_xp} XP){rank_line}\n"

    text = (
        f"{header()}\n\n"
        f"{title}\n\n"
        f"{chr(10).join(lines) if lines else 'Пока нет данных'}\n\n"
        f"{viewer_level_line}"
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


async def get_group_top_by_race_wins(chat_id: int, limit: int = 10):
    candidates = get_top_users_by_race_wins(500)
    top = []
    allowed_statuses = {"creator", "administrator", "member", "restricted"}

    for row in candidates:
        if int(row.get("race_wins", 0)) <= 0:
            continue

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
            media_message = await target.answer_document(
                image,
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            if user_id:
                LAST_STICKER_MESSAGE_ID[user_id] = media_message.message_id
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
    # Удаляем медиа последнего открытия кейса, если было
    media_msg_id = LAST_STICKER_MESSAGE_ID.pop(message.from_user.id, None)
    if media_msg_id:
        try:
            await bot.delete_message(message.chat.id, media_msg_id)
        except Exception:
            pass

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
            "🎮 Открывай кейсы, собирай коллекцию машин и прокачивай профиль.\n\n"
            f"🎁 <b>Как начать:</b>\n"
            "• Открывай <b>бесплатный кейс</b> каждые 4 часа\n"
            "• Копи Coins и открывай <b>платные кейсы</b>\n"
            "• Собирай машины в <b>гараже</b>\n"
            "• Продавай дубликаты и получай Coins\n\n"
            "Выбирай действие в меню ниже.\n\n"
            f"{footer()}",
            reply_markup=main_menu_kb(message.from_user.id),
            parse_mode="HTML",
        )
    else:
        # Обычное меню для вернувшихся
        await message.answer(
            f"{header()}\n\n"
            f"👋 Привет, <b>{message.from_user.first_name}</b>!\n"
            "Выбирай действие в меню ниже.\n\n"
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
        await call.answer("⛔ Доступно только в ЛС", show_alert=True)
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

    # Удаляем медиа последнего открытия кейса, если было
    media_msg_id = LAST_STICKER_MESSAGE_ID.pop(call.from_user.id, None)
    if media_msg_id:
        try:
            await bot.delete_message(call.message.chat.id, media_msg_id)
        except Exception:
            pass
    
    # Просто редактируем текущее сообщение на меню
    await call.message.edit_text(
        f"{header()}\n\n"
        "🏠 <b>Главное меню</b>\n\n"
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
        "❓ <b>Помощь</b>\n\n"
        "<b>📱 Команды:</b>\n"
        "• /start — главное меню\n"
        "• /stats — топ игроков\n"
        "• /help — справка\n\n"
        "<b>🔊 Триггеры в группе:</b>\n"
        "• Открыть кейс: кейс, case, открыть, open\n"
        "• Баланс: баланс, balance, coins\n\n"
        "Все основные функции доступны через меню ниже.\n\n"
        f"{footer()}"
    )
    
    await call.message.edit_text(
        help_text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 К меню", callback_data="start")]]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data == "menu:more")
async def more_menu(call: CallbackQuery):
    if call.message.chat.type != "private":
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await call.answer()
        await call.message.answer(
            f"{header()}\n\n"
            "📚 Дополнительно доступно только в ЛС\n\n"
            f"<a href='{bot_link}'>Открыть бота</a>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return

    await call.message.edit_text(
        f"{header()}\n\n"
        "📚 <b>Дополнительно</b>\n\n"
        "Выбирай нужный раздел:\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Отзыв", callback_data="menu:feedback")],
                [InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
                [InlineKeyboardButton(text="🔙 К меню", callback_data="start")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


def _build_races_menu_view(user_id: int):
    user = get_user(user_id)
    if not user:
        return None, None

    cars = get_user_garage(user_id)
    cars_count = len(cars)
    race_ready_text = "✅ Готов к заездам" if cars_count > 0 else "⚠️ Нужна хотя бы 1 машина"
    selected_car = None
    selected_card = None
    selected_car_id = RACE_SELECTED_CAR_ID.get(user_id)
    if selected_car_id:
        selected_car = get_car_by_id(selected_car_id)
        if not selected_car or selected_car.get("user_id") != user_id:
            RACE_SELECTED_CAR_ID.pop(user_id, None)
            selected_car = None
        else:
            selected_card = CARDS.get(selected_car.get("name", ""), {})

    if selected_car:
        selected_name = selected_card.get("name_ru") or selected_car.get("name") or "Машина"
        selected_profile = get_car_profile(selected_car.get("name", ""), selected_car.get("rarity", "Common"), RACE_PROFILES)
        selected_line = (
            f"🚘 Выбрана: <b>{selected_name}</b> "
            f"({RARITY_EMOJI.get(selected_car.get('rarity', ''), '❓')} {RARITY_RU.get(selected_car.get('rarity', ''), selected_car.get('rarity', '—'))})"
        )
        selected_stats_line = (
            "⚙️ Характеристики:\n"
            f"• ⚡ Скорость: <b>{selected_profile['speed']}</b>\n"
            f"• 🚀 Разгон: <b>{selected_profile['accel']}</b>\n"
            f"• 🛞 Сцепление: <b>{selected_profile['grip']}</b>\n"
            f"• 🛡 Надёжность: <b>{selected_profile['reliability']}</b>\n"
            f"• 📈 LVL тюнинга: <b>{selected_profile['tune_level']}</b>"
        )
    else:
        selected_line = "🚘 Выбрана: <b>не выбрана</b>"
        selected_stats_line = (
            "⚙️ Характеристики:\n"
            "• ⚡ Скорость: <b>—</b>\n"
            "• 🚀 Разгон: <b>—</b>\n"
            "• 🛞 Сцепление: <b>—</b>\n"
            "• 🛡 Надёжность: <b>—</b>\n"
            "• 📈 LVL тюнинга: <b>—</b>"
        )

    text = (
        f"{header()}\n\n"
        "🏁 <b>Гонки</b>\n\n"
        "Меню режима гонок.\n"
        "Выбирай машину, тюнинг и запускай заезды.\n\n"
        f"🚗 Машин в гараже: <b>{cars_count}</b>\n"
        f"{selected_line}\n"
        f"{selected_stats_line}\n"
        f"{race_ready_text}\n\n"
        f"{footer()}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚘 Выбрать машину", callback_data="races:pick:classes")],
            [InlineKeyboardButton(text="🔎 Подбор", callback_data="races:vs_bot")],
            [InlineKeyboardButton(text="⚙️ Тюнинг", callback_data="races:tune")],
            [InlineKeyboardButton(text="❓ Как играть", callback_data="races:howto")],
            [InlineKeyboardButton(text="🚗 Гараж", callback_data="menu:garage:0")],
            [InlineKeyboardButton(text="📊 Статистика гонок", callback_data="races:stats")],
            [InlineKeyboardButton(text="🔙 К меню", callback_data="start")],
        ]
    )
    return text, kb


@dp.callback_query(F.data == "menu:races")
async def races_menu(call: CallbackQuery):
    if not can_access_races(call.from_user.id):
        await call.answer("⛔ Раздел в тесте", show_alert=True)
        return

    if call.message.chat.type != "private":
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await call.answer()
        await call.message.answer(
            f"{header()}\n\n"
            "🏁 Гонки доступны только в ЛС\n\n"
            f"<a href='{bot_link}'>Открыть бота</a>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return

    text, kb = _build_races_menu_view(call.from_user.id)
    if not text:
        await call.answer("⛔ Профиль не найден. Нажми /start", show_alert=True)
        return

    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "menu:races:new")
async def races_menu_new_message(call: CallbackQuery):
    if not can_access_races(call.from_user.id):
        await call.answer("⛔ Раздел в тесте", show_alert=True)
        return

    if call.message.chat.type != "private":
        await call.answer("⛔ Доступно только в ЛС", show_alert=True)
        return

    text, kb = _build_races_menu_view(call.from_user.id)
    if not text:
        await call.answer("⛔ Профиль не найден. Нажми /start", show_alert=True)
        return

    await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await call.answer("✅ Открыто новым сообщением")


@dp.callback_query(F.data == "races:howto")
async def races_howto(call: CallbackQuery):
    if not can_access_races(call.from_user.id):
        await call.answer("⛔ Раздел в тесте", show_alert=True)
        return

    if call.message.chat.type != "private":
        await call.answer("⛔ Доступно только в ЛС", show_alert=True)
        return

    await call.message.edit_text(
        f"{header()}\n\n"
        "❓ <b>Как играть в гонки</b>\n\n"
        "<b>1) Подготовка</b>\n"
        "• Выбери машину в меню гонок (по классам)\n"
        "• При желании прокачай её в тюнинге\n"
        "• Без выбранной машины подбор не запустится\n\n"
        "<b>2) ЛС-подбор</b>\n"
        "• Нажми 🔎 Подбор — поиск идёт до 1 минуты\n"
        "• Если соперник не найден, можно запустить подбор снова\n"
        "• С одним и тем же соперником нельзя попасться повторно 1 час\n\n"
        "<b>3) Дуэль в группе</b>\n"
        "• Ответь на сообщение игрока командой /raceduel\n"
        "• Игрок принимает вызов через кнопки Да/Нет\n"
        "• Дуэль доступна только при одинаковом классе машин\n\n"
        "<b>4) Характеристики (кратко)</b>\n"
        "• ⚡ <b>Скорость</b> — помогает быстрее проходить дистанцию\n"
        "• 🚀 <b>Разгон</b> — помогает быстрее набирать ход и стартовать\n"
        "• 🛞 <b>Сцепление</b> — стабильнее проходишь сложные участки\n"
        "• 🛡 <b>Надёжность</b> — меньше просадок и случайных потерь скорости\n\n"
        "<b>5) Почему стоит качать тюнинг</b>\n"
        "• Улучшает шанс на победу против равного класса\n"
        "• Позволяет точечно усилить слабую сторону машины\n"
        "• Даёт более стабильные результаты на разных треках\n\n"
        "<b>6) Награды и статистика</b>\n"
        "• За победу начисляются Coins по твоему рангу\n"
        "• Ведётся статистика: победы/поражения/ничьи\n"
        "• Доступен общий топ по победам (ТОП-10)\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К гонкам", callback_data="menu:races")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data.startswith("races:pick:"))
async def race_pick_car_menu(call: CallbackQuery):
    if not can_access_races(call.from_user.id):
        await call.answer("⛔ Раздел в тесте", show_alert=True)
        return

    if call.message.chat.type != "private":
        await call.answer("⛔ Доступно только в ЛС", show_alert=True)
        return

    user = get_user(call.from_user.id)
    if not user:
        await call.answer("⛔ Профиль не найден. Нажми /start", show_alert=True)
        return

    parts = call.data.split(":")
    mode = parts[2] if len(parts) > 2 else "classes"
    cars = get_user_garage(call.from_user.id)
    if not cars:
        await call.answer("🚗 Гараж пуст. Открой кейс", show_alert=True)
        return

    class_groups = {}
    for car in cars:
        profile = get_car_profile(car.get("name", ""), car.get("rarity", "Common"), RACE_PROFILES)
        class_code = str(profile.get("class", "D")).upper()
        class_groups.setdefault(class_code, []).append(car)

    class_order = ["D", "C", "B", "A", "S"]
    sorted_classes = sorted(
        class_groups.keys(),
        key=lambda code: (class_order.index(code) if code in class_order else 999, code),
    )

    if mode == "classes" or mode.isdigit():
        kb = []
        for class_code in sorted_classes:
            class_cars_count = len(class_groups.get(class_code, []))
            kb.append([
                InlineKeyboardButton(
                    text=f"Класс {class_code} • {class_cars_count} шт.",
                    callback_data=f"races:pick:class:{class_code}:0",
                )
            ])

        kb.append([InlineKeyboardButton(text="🔙 К гонкам", callback_data="menu:races")])

        await call.message.edit_text(
            f"{header()}\n\n"
            "🚘 <b>Выбор машины для гонки</b>\n\n"
            f"Всего машин: <b>{len(cars)}</b>\n"
            f"Классов: <b>{len(sorted_classes)}</b>\n\n"
            "Сначала выбери класс автомобиля:\n\n"
            f"{footer()}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            parse_mode="HTML",
        )
        await call.answer()
        return

    if mode != "class" or len(parts) < 5:
        await call.answer("⚠️ Неверный формат выбора", show_alert=True)
        return

    class_code = str(parts[3]).upper()
    try:
        page = int(parts[4])
    except Exception:
        page = 0

    class_cars = class_groups.get(class_code, [])
    if not class_cars:
        await call.answer("🚘 В этом классе нет машин", show_alert=True)
        return

    total = len(class_cars)
    max_page = max(0, (total - 1) // GARAGE_PAGE_SIZE)
    page = max(0, min(page, max_page))
    start = page * GARAGE_PAGE_SIZE
    end = start + GARAGE_PAGE_SIZE
    chunk = class_cars[start:end]
    selected_car_id = RACE_SELECTED_CAR_ID.get(call.from_user.id)

    kb = []
    for car in chunk:
        card = CARDS.get(car.get("name", ""), {})
        display_name = card.get("name_ru") or car.get("name", "Машина")
        emoji = RARITY_EMOJI.get(car.get("rarity"), "❓")
        selected_prefix = "✅ " if selected_car_id == car.get("id") else ""
        kb.append([
            InlineKeyboardButton(
                text=f"{selected_prefix}{emoji} {display_name}",
                callback_data=f"races:picksel:{car['id']}",
            )
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"races:pick:class:{class_code}:{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"races:pick:class:{class_code}:{page + 1}"))
    if nav:
        kb.append(nav)

    kb.append([InlineKeyboardButton(text="🔙 К классам", callback_data="races:pick:classes")])
    kb.append([InlineKeyboardButton(text="🔙 К гонкам", callback_data="menu:races")])

    await call.message.edit_text(
        f"{header()}\n\n"
        "🚘 <b>Выбор машины для гонки</b>\n\n"
        f"Класс: <b>{class_code}</b>\n"
        f"Страница: <b>{page + 1}/{max_page + 1}</b>\n"
        f"Машин в классе: <b>{total}</b>\n\n"
        "✅ — текущая выбранная машина\n\n"
        "Выбери машину из списка:\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data.startswith("races:picksel:"))
async def race_pick_car_select(call: CallbackQuery):
    if not can_access_races(call.from_user.id):
        await call.answer("⛔ Раздел в тесте", show_alert=True)
        return

    if call.message.chat.type != "private":
        await call.answer("⛔ Доступно только в ЛС", show_alert=True)
        return

    car_id = int(call.data.split(":")[2])
    car = get_car_by_id(car_id)
    if not car or car.get("user_id") != call.from_user.id:
        await call.answer("⛔ Машина недоступна", show_alert=True)
        return

    RACE_SELECTED_CAR_ID[call.from_user.id] = car_id
    await call.answer("✅ Машина выбрана")

    cars = get_user_garage(call.from_user.id)
    cars_count = len(cars)
    race_ready_text = "✅ Готов к заездам" if cars_count > 0 else "⚠️ Нужна хотя бы 1 машина"
    card = CARDS.get(car.get("name", ""), {})
    profile = get_car_profile(car.get("name", ""), car.get("rarity", "Common"), RACE_PROFILES)
    selected_name = card.get("name_ru") or car.get("name") or "Машина"
    selected_line = (
        f"🚘 Выбрана: <b>{selected_name}</b> "
        f"({RARITY_EMOJI.get(car.get('rarity', ''), '❓')} {RARITY_RU.get(car.get('rarity', ''), car.get('rarity', '—'))})"
    )
    selected_stats_line = (
        "⚙️ Характеристики:\n"
        f"• ⚡ Скорость: <b>{profile['speed']}</b>\n"
        f"• 🚀 Разгон: <b>{profile['accel']}</b>\n"
        f"• 🛞 Сцепление: <b>{profile['grip']}</b>\n"
        f"• 🛡 Надёжность: <b>{profile['reliability']}</b>\n"
        f"• 📈 LVL тюнинга: <b>{profile['tune_level']}</b>"
    )

    await call.message.edit_text(
        f"{header()}\n\n"
        "🏁 <b>Гонки</b>\n\n"
        "Меню режима гонок.\n"
        "Выбирай машину, тюнинг и запускай заезды.\n\n"
        f"🚗 Машин в гараже: <b>{cars_count}</b>\n"
        f"{selected_line}\n"
        f"{selected_stats_line}\n"
        f"{race_ready_text}\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚘 Выбрать машину", callback_data="races:pick:classes")],
                [InlineKeyboardButton(text="🔎 Подбор", callback_data="races:vs_bot")],
                [InlineKeyboardButton(text="⚙️ Тюнинг", callback_data="races:tune")],
                [InlineKeyboardButton(text="❓ Как играть", callback_data="races:howto")],
                [InlineKeyboardButton(text="🚗 Гараж", callback_data="menu:garage:0")],
                [InlineKeyboardButton(text="📊 Статистика гонок", callback_data="races:stats")],
                [InlineKeyboardButton(text="🔙 К меню", callback_data="start")],
            ]
        ),
        parse_mode="HTML",
    )


def _build_race_stats_view(user_id: int, back_callback: str = "menu:races"):
    stats = get_user_race_stats(user_id)
    total = int(stats.get("total", 0))
    wins = int(stats.get("wins", 0))
    losses = int(stats.get("losses", 0))
    draws = int(stats.get("draws", 0))
    winrate = (wins / total * 100.0) if total > 0 else 0.0
    rank_info = get_race_rank_info(wins)
    current_rank = rank_info["current"]
    next_rank = rank_info["next"]

    if next_rank:
        next_rank_line = (
            f"🎯 До следующего ранга ({next_rank['emoji']} {next_rank['name']}): "
            f"<b>{rank_info['wins_to_next']}</b> побед\n"
        )
    else:
        next_rank_line = "🎯 Следующий ранг: <b>MAX</b>\n"

    text = (
        f"{header()}\n\n"
        "📊 <b>Статистика гонок</b>\n\n"
        f"🏷 Ранг: <b>{current_rank['emoji']} {current_rank['name']}</b>\n"
        f"💸 Награда за победу: <b>{fmt_coins(current_rank['reward'])}</b>\n"
        f"{next_rank_line}"
        "\n"
        f"🏁 Всего заездов: <b>{total}</b>\n"
        f"🏆 Побед: <b>{wins}</b>\n"
        f"😵 Поражений: <b>{losses}</b>\n"
        f"🤝 Ничьих: <b>{draws}</b>\n"
        f"📈 Винрейт: <b>{winrate:.1f}%</b>\n\n"
        f"{footer()}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К гонкам", callback_data=back_callback)],
        ]
    )
    return text, kb


@dp.callback_query(F.data == "races:stats")
async def race_stats_menu(call: CallbackQuery):
    if not can_access_races(call.from_user.id):
        await call.answer("⛔ Раздел в тесте", show_alert=True)
        return

    if call.message.chat.type != "private":
        await call.answer("⛔ Доступно только в ЛС", show_alert=True)
        return

    text, kb = _build_race_stats_view(call.from_user.id)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "races:stats:new")
async def race_stats_menu_new_message(call: CallbackQuery):
    if not can_access_races(call.from_user.id):
        await call.answer("⛔ Раздел в тесте", show_alert=True)
        return

    if call.message.chat.type != "private":
        await call.answer("⛔ Доступно только в ЛС", show_alert=True)
        return

    text, kb = _build_race_stats_view(call.from_user.id)
    await call.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await call.answer("✅ Открыто новым сообщением")


async def show_race_tuning_menu(call: CallbackQuery, notice: str = ""):
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("⛔ Профиль не найден. Нажми /start", show_alert=True)
        return

    selected_car_id = RACE_SELECTED_CAR_ID.get(call.from_user.id)
    if not selected_car_id:
        await call.answer("🚘 Сначала выбери машину в меню гонок", show_alert=True)
        return

    selected_car = get_car_by_id(selected_car_id)
    if not selected_car or selected_car.get("user_id") != call.from_user.id:
        RACE_SELECTED_CAR_ID.pop(call.from_user.id, None)
        await call.answer("🚘 Выбранная машина недоступна. Выбери снова", show_alert=True)
        return

    card_id = selected_car.get("name", "")
    rarity = selected_car.get("rarity", "Common")
    card = CARDS.get(card_id, {})
    profile = get_car_profile(card_id, rarity, RACE_PROFILES)
    is_maxed = is_tuning_maxed(profile)
    next_cost = None if is_maxed else get_tuning_cost(profile)

    car_name = card.get("name_ru") or card_id or "Машина"
    tune_text = (
        f"{header()}\n\n"
        "⚙️ <b>Тюнинг</b>\n\n"
        f"🚘 <b>{car_name}</b>\n"
        f"Редкость: {RARITY_EMOJI.get(rarity, '❓')} {RARITY_RU.get(rarity, rarity)}\n"
        f"🧩 Архетип: <b>{profile.get('archetype', 'sedan')}</b>\n"
        f"📈 Тюнинг-уровень: <b>{profile.get('tune_level', 1)}</b>/<b>{MAX_TUNE_LEVEL}</b>\n\n"
        f"⚡ Скорость: <b>{profile['speed']}</b>\n"
        f"🚀 Разгон: <b>{profile['accel']}</b>\n"
        f"🛞 Сцепление: <b>{profile['grip']}</b>\n"
        f"🛡 Надёжность: <b>{profile['reliability']}</b>\n\n"
        f"💰 Следующий апгрейд: <b>{fmt_coins(next_cost) if next_cost is not None else 'MAX LEVEL'}</b>\n"
        f"👛 Твой баланс: <b>{fmt_coins(user.get('coins', 0))}</b>\n"
    )

    if notice:
        tune_text += f"\n{notice}\n"

    tune_text += f"\n{footer()}"

    await call.message.edit_text(
        tune_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⚡ +Скорость", callback_data="races:tuneup:speed"),
                    InlineKeyboardButton(text="🚀 +Разгон", callback_data="races:tuneup:accel"),
                ],
                [
                    InlineKeyboardButton(text="🛞 +Сцепление", callback_data="races:tuneup:grip"),
                    InlineKeyboardButton(text="🛡 +Надёжность", callback_data="races:tuneup:reliability"),
                ],
                [InlineKeyboardButton(text="🔙 К гонкам", callback_data="menu:races")],
            ]
        ),
    )


@dp.callback_query(F.data == "races:tune")
async def race_tune_menu(call: CallbackQuery):
    if not can_access_races(call.from_user.id):
        await call.answer("⛔ Раздел в тесте", show_alert=True)
        return

    if call.message.chat.type != "private":
        await call.answer("⛔ Доступно только в ЛС", show_alert=True)
        return

    await show_race_tuning_menu(call)
    await call.answer()


@dp.callback_query(F.data.startswith("races:tuneup:"))
async def race_tune_upgrade(call: CallbackQuery):
    if not can_access_races(call.from_user.id):
        await call.answer("⛔ Раздел в тесте", show_alert=True)
        return

    if call.message.chat.type != "private":
        await call.answer("⛔ Доступно только в ЛС", show_alert=True)
        return

    user = get_user(call.from_user.id)
    if not user:
        await call.answer("⛔ Профиль не найден. Нажми /start", show_alert=True)
        return

    selected_car_id = RACE_SELECTED_CAR_ID.get(call.from_user.id)
    if not selected_car_id:
        await call.answer("🚘 Сначала выбери машину", show_alert=True)
        return

    selected_car = get_car_by_id(selected_car_id)
    if not selected_car or selected_car.get("user_id") != call.from_user.id:
        RACE_SELECTED_CAR_ID.pop(call.from_user.id, None)
        await call.answer("🚘 Машина недоступна. Выбери снова", show_alert=True)
        return

    stat = call.data.split(":")[2]
    card_id = selected_car.get("name", "")
    rarity = selected_car.get("rarity", "Common")

    profile_before = get_car_profile(card_id, rarity, RACE_PROFILES)
    cost = get_tuning_cost(profile_before)
    user_coins = int(user.get("coins", 0))
    if user_coins < cost:
        await call.answer(f"⛔ Не хватает Coins: нужно {fmt_coins(cost)}", show_alert=True)
        return

    ok, profile_after, reason = apply_tuning_upgrade(card_id, rarity, RACE_PROFILES, stat)
    if not ok:
        if reason == "cap_reached":
            await call.answer("⛔ Лимит прокачки этого параметра достигнут", show_alert=True)
        elif reason == "max_level_reached":
            await call.answer(f"⛔ Достигнут максимум тюнинга: LVL {MAX_TUNE_LEVEL}", show_alert=True)
        elif reason == "class_power_cap":
            await call.answer("⛔ Ограничение класса: слишком сильная сборка", show_alert=True)
        else:
            await call.answer("⚠️ Не удалось применить тюнинг", show_alert=True)
        return

    subtract_coins(call.from_user.id, cost, source=f"race_tune_{stat}")
    save_race_profiles(RACE_PROFILES)

    stat_labels = {
        "speed": "Скорость",
        "accel": "Разгон",
        "grip": "Сцепление",
        "reliability": "Надёжность",
    }
    stat_label = stat_labels.get(stat, stat)
    await show_race_tuning_menu(
        call,
        notice=(
            f"✅ Улучшено: <b>{stat_label}</b> → <b>{profile_after.get(stat)}</b>\n"
            f"💸 Списано: <b>{fmt_coins(cost)}</b>"
        ),
    )
    await call.answer("✅ Тюнинг применён")


@dp.callback_query(F.data == "races:vs_bot:new")
async def race_vs_bot_new_message(call: CallbackQuery):
    if not can_access_races(call.from_user.id):
        await call.answer("⛔ Раздел в тесте", show_alert=True)
        return

    if call.message.chat.type != "private":
        await call.answer("⛔ Доступно только в ЛС", show_alert=True)
        return

    await call.message.answer(
        f"{header()}\n\n"
        "🔁 <b>Новый заезд</b>\n\n"
        "Отчёт о прошлой гонке сохранён выше.\n"
        "Нажми кнопку ниже, чтобы запустить новый подбор.\n\n"
        f"{footer()}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔎 Запустить подбор", callback_data="races:vs_bot")],
                [InlineKeyboardButton(text="📊 Статистика гонок", callback_data="races:stats")],
                [InlineKeyboardButton(text="🔙 К гонкам", callback_data="menu:races")],
            ]
        ),
    )
    await call.answer("✅ Открыто новым сообщением")


@dp.callback_query(F.data == "races:vs_bot")
async def race_vs_bot(call: CallbackQuery):
    if not can_access_races(call.from_user.id):
        await call.answer("⛔ Раздел в тесте", show_alert=True)
        return

    if call.message.chat.type != "private":
        await call.answer("⛔ Доступно только в ЛС", show_alert=True)
        return

    user = get_user(call.from_user.id)
    if not user:
        await call.answer("⛔ Профиль не найден. Нажми /start", show_alert=True)
        return

    cars = get_user_garage(call.from_user.id)
    if not cars:
        await call.answer("🚗 Гараж пуст. Открой кейс, чтобы начать гонки", show_alert=True)
        return

    selected_car_id = RACE_SELECTED_CAR_ID.get(call.from_user.id)
    if not selected_car_id:
        await call.answer("🚘 Сначала выбери машину в меню гонок", show_alert=True)
        return

    selected_car = get_car_by_id(selected_car_id)
    if not selected_car or selected_car.get("user_id") != call.from_user.id:
        RACE_SELECTED_CAR_ID.pop(call.from_user.id, None)
        await call.answer("🚘 Выбранная машина недоступна. Выбери снова", show_alert=True)
        return

    profile = get_car_profile(selected_car.get("name", ""), selected_car.get("rarity", "Common"), RACE_PROFILES)
    class_code = str(profile.get("class", "D")).upper()

    active_search = PRIVATE_RACE_SEARCH_BY_USER.get(call.from_user.id)
    if active_search:
        elapsed = max(0.0, time.monotonic() - float(active_search.get("started_at", 0.0)))
        remaining = int(max(0, PRIVATE_RACE_SEARCH_TIMEOUT_SECONDS - elapsed))
        await call.answer(f"⏳ Ты уже в подборе. Осталось ~{max(1, int(math.ceil(remaining / 60)))} мин", show_alert=True)
        return

    queue = PRIVATE_RACE_QUEUE_BY_CLASS.setdefault(class_code, [])
    queue[:] = [
        item for item in queue
        if int(item.get("user_id", 0)) in PRIVATE_RACE_SEARCH_BY_USER
        and str(PRIVATE_RACE_SEARCH_BY_USER[int(item.get("user_id", 0))].get("token")) == str(item.get("token"))
    ]

    now_ts = time.monotonic()
    matched_entry = None
    for candidate in queue:
        candidate_user_id = int(candidate.get("user_id", 0))
        if candidate_user_id == call.from_user.id:
            continue
        if _private_rematch_block_remaining(call.from_user.id, candidate_user_id, now_ts=now_ts) > 0:
            continue
        matched_entry = candidate
        break

    self_entry = {
        "user_id": int(call.from_user.id),
        "chat_id": int(call.message.chat.id),
        "message_id": int(call.message.message_id),
        "user_name": call.from_user.first_name or "Игрок",
        "class_code": class_code,
        "started_at": now_ts,
    }

    if matched_entry:
        queue[:] = [item for item in queue if int(item.get("user_id", 0)) != int(matched_entry.get("user_id", 0))]
        PRIVATE_RACE_SEARCH_BY_USER.pop(int(matched_entry.get("user_id", 0)), None)

        pair_key = _private_pair_key(call.from_user.id, int(matched_entry.get("user_id", 0)))
        PRIVATE_RACE_LAST_PAIR_TS[pair_key] = now_ts

        await _publish_private_race_result(self_entry, matched_entry)
        await call.answer("✅ Соперник найден!", show_alert=False)
        return

    token = f"{call.from_user.id}:{now_ts}"
    self_entry["token"] = token
    PRIVATE_RACE_SEARCH_BY_USER[int(call.from_user.id)] = self_entry
    queue.append(self_entry)

    asyncio.create_task(_expire_private_race_search_later(call.from_user.id, token))

    await call.message.edit_text(
        f"{header()}\n\n"
        "🔎 <b>Подбор соперника</b>\n\n"
        f"Класс: <b>{class_code}</b>\n"
        "Ищем игрока до <b>1 минуты</b>...\n\n"
        "Если соперник не найдётся — нажми подбор снова.\n"
        "С ботом подбор сейчас отключён.\n\n"
        f"{footer()}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить поиск", callback_data="races:search:cancel")],
                [InlineKeyboardButton(text="🔙 К гонкам", callback_data="menu:races")],
            ]
        ),
    )
    await call.answer("🔎 Подбор запущен")


@dp.callback_query(F.data == "races:search:cancel")
async def race_search_cancel(call: CallbackQuery):
    if call.message.chat.type != "private":
        await call.answer("⛔ Доступно только в ЛС", show_alert=True)
        return

    active_search = PRIVATE_RACE_SEARCH_BY_USER.get(call.from_user.id)
    if not active_search:
        await call.answer("ℹ️ Сейчас нет активного подбора", show_alert=True)
        return

    _remove_private_search_entry(call.from_user.id)

    await call.message.edit_text(
        f"{header()}\n\n"
        "❌ <b>Подбор отменён</b>\n\n"
        "Поиск соперника остановлен.\n\n"
        f"{footer()}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔁 Подбор снова", callback_data="races:vs_bot")],
                [InlineKeyboardButton(text="🔙 К гонкам", callback_data="menu:races")],
            ]
        ),
    )
    await call.answer("✅ Поиск остановлен")


@dp.message(Command("stats"))
async def stats_command(message: Message):
    await send_stats(message)


@dp.message(Command("help"))
async def help_command(message: Message):
    help_text = (
        f"{header()}\n\n"
        "❓ <b>Помощь</b>\n\n"
        "<b>📱 Команды:</b>\n"
        "• /start — главное меню\n"
        "• /stats — топ игроков\n"
        "• /help — справка\n\n"
        "<b>🔊 Триггеры в группе:</b>\n"
        "• Открыть кейс: кейс, case, открыть, open\n"
        "• Баланс: баланс, balance, coins\n\n"
        "Все основные функции доступны через меню.\n\n"
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
    global DUPLICATE_PITY_THRESHOLD

    if is_owner(message.from_user.id) and message.from_user.id in ADMIN_DUPLICATE_PITY_PENDING:
        text = (message.text or "").strip()
        try:
            value = int(text)
        except ValueError:
            await message.answer(
                f"{header()}\n\n"
                "❌ Введи целое число от 1 до 100.\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
            return

        if value < 1 or value > 100:
            await message.answer(
                f"{header()}\n\n"
                "❌ Допустимый диапазон: от 1 до 100.\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
            return

        DUPLICATE_PITY_THRESHOLD = value
        ADMIN_DUPLICATE_PITY_PENDING.discard(message.from_user.id)

        await message.answer(
            f"{header()}\n\n"
            "✅ <b>Порог гаранта обновлён</b>\n\n"
            f"Теперь гарант срабатывает после <b>{DUPLICATE_PITY_THRESHOLD}</b> дублей подряд.\n\n"
            f"{footer()}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
                ]
            ),
            parse_mode="HTML",
        )
        return

    if is_owner(message.from_user.id) and message.from_user.id in ADMIN_USER_FIND_PENDING:
        query = (message.text or "").strip()
        if len(query) < 2:
            await message.answer(
                f"{header()}\n\n"
                "Введи минимум 2 символа для поиска.\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
            return

        rows = search_users_by_nick(query, 20)
        if not rows:
            await message.answer(
                f"{header()}\n\n"
                "❌ По такому нику игроки не найдены\n\n"
                f"{footer()}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🔁 Новый поиск", callback_data="admin:user_find")],
                        [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
                    ]
                ),
                parse_mode="HTML",
            )
            return

        ADMIN_USER_FIND_PENDING.discard(message.from_user.id)

        lines = []
        kb = []
        for row in rows[:10]:
            username = row.get("username")
            first_name = row.get("first_name") or "Игрок"
            nick = f"@{username}" if username else "(без username)"
            uid = row["user_id"]
            lines.append(f"• <b>{first_name}</b> {nick} — <code>{uid}</code>")
            kb.append([
                InlineKeyboardButton(text=f"✏️ Редактировать {uid}", callback_data=f"admin:edit_user_id:{uid}")
            ])

        kb.append([InlineKeyboardButton(text="🔁 Новый поиск", callback_data="admin:user_find")])
        kb.append([InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")])

        await message.answer(
            f"{header()}\n\n"
            f"🔎 <b>Найдено игроков:</b> {len(rows)}\n\n"
            f"{chr(10).join(lines)}\n\n"
            f"{footer()}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            parse_mode="HTML",
        )
        return

    if is_owner(message.from_user.id) and message.from_user.id in ADMIN_PROFILE_LOOKUP_PENDING:
        text = (message.text or "").strip()
        if not text.isdigit():
            await message.answer(
                f"{header()}\n\n"
                "Введи корректный ID игрока (только число).\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
            return

        target_user_id = int(text)
        text, kb = build_admin_player_profile_view(target_user_id)
        if not text:
            await message.answer(
                f"{header()}\n\n"
                "❌ Игрок не найден\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
            return

        ADMIN_PROFILE_LOOKUP_PENDING.discard(message.from_user.id)

        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    if is_owner(message.from_user.id) and message.from_user.id in ADMIN_EDIT_LOOKUP_PENDING:
        text = (message.text or "").strip()
        if not text.isdigit():
            await message.answer(
                f"{header()}\n\n"
                "Введи корректный ID игрока (только число).\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
            return

        target_user_id = int(text)
        target_user = get_user(target_user_id)
        if not target_user:
            await message.answer(
                f"{header()}\n\n"
                "❌ Игрок не найден\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
            return

        ADMIN_EDIT_LOOKUP_PENDING.discard(message.from_user.id)

        await message.answer(
            f"{header()}\n\n"
            "🛠 <b>Редактирование игрока</b>\n\n"
            f"ID: <code>{target_user_id}</code>\n"
            f"Баланс: <b>{target_user['coins']}</b> Coins\n\n"
            "Выбери действие:\n\n"
            f"{footer()}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="➕ Монеты", callback_data=f"admin:edit_set:{target_user_id}:coins_add"),
                        InlineKeyboardButton(text="➖ Монеты", callback_data=f"admin:edit_set:{target_user_id}:coins_sub"),
                    ],
                    [InlineKeyboardButton(text="💰 Установить баланс", callback_data=f"admin:edit_set:{target_user_id}:coins_set")],
                    [InlineKeyboardButton(text="🚗 Выдать машину", callback_data=f"admin:edit_set:{target_user_id}:car_add")],
                    [InlineKeyboardButton(text="🗑 Забрать машину", callback_data=f"admin:edit_set:{target_user_id}:car_remove")],
                    [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
                ]
            ),
            parse_mode="HTML",
        )
        return

    if is_owner(message.from_user.id) and message.from_user.id in ADMIN_USER_EDIT_PENDING:
        payload = ADMIN_USER_EDIT_PENDING[message.from_user.id]
        target_user_id = payload["target_user_id"]
        action = payload["action"]
        text = (message.text or "").strip()

        target_user = get_user(target_user_id)
        if not target_user:
            ADMIN_USER_EDIT_PENDING.pop(message.from_user.id, None)
            await message.answer(
                f"{header()}\n\n"
                "❌ Игрок не найден\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
            return

        try:
            if action == "coins_add":
                amount = int(text)
                if amount <= 0:
                    raise ValueError()
                add_coins(target_user_id, amount, source="admin_add")
                new_user = get_user(target_user_id)
                await message.answer(
                    f"{header()}\n\n✅ Баланс увеличен на {amount} Coins\nНовый баланс: <b>{new_user['coins']}</b> Coins\n\n{footer()}",
                    parse_mode="HTML",
                )
                try:
                    await bot.send_message(
                        target_user_id,
                        f"{header()}\n\n💰 Администратор начислил тебе <b>+{amount}</b> Coins.\nТекущий баланс: <b>{new_user['coins']}</b> Coins\n\n{footer()}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

            elif action == "coins_sub":
                amount = int(text)
                if amount <= 0:
                    raise ValueError()
                current = max(0, int(target_user.get("coins", 0)))
                new_balance = max(0, current - amount)
                set_user_coins(target_user_id, new_balance)
                await message.answer(
                    f"{header()}\n\n✅ Баланс уменьшен на {amount} Coins\nНовый баланс: <b>{new_balance}</b> Coins\n\n{footer()}",
                    parse_mode="HTML",
                )
                try:
                    await bot.send_message(
                        target_user_id,
                        f"{header()}\n\n💸 Администратор списал у тебя <b>{amount}</b> Coins.\nТекущий баланс: <b>{new_balance}</b> Coins\n\n{footer()}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

            elif action == "coins_set":
                amount = int(text)
                if amount < 0:
                    raise ValueError()
                set_user_coins(target_user_id, amount)
                await message.answer(
                    f"{header()}\n\n✅ Баланс установлен: <b>{amount}</b> Coins\n\n{footer()}",
                    parse_mode="HTML",
                )
                try:
                    await bot.send_message(
                        target_user_id,
                        f"{header()}\n\n💰 Администратор установил твой баланс: <b>{amount}</b> Coins\n\n{footer()}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

            elif action == "car_add":
                car_key = text.lower()
                card = CARDS.get(car_key)
                if not card:
                    await message.answer(
                        f"{header()}\n\n❌ Машина не найдена в каталоге.\nВведи корректный ключ из cards.json\n\n{footer()}",
                        parse_mode="HTML",
                    )
                    return
                add_car_to_garage(target_user_id, car_key, card.get("rarity", "Common"))
                await message.answer(
                    f"{header()}\n\n✅ Машина выдана: <b>{card.get('name_ru', car_key)}</b>\n\n{footer()}",
                    parse_mode="HTML",
                )
                try:
                    await bot.send_message(
                        target_user_id,
                        f"{header()}\n\n🚘 Администратор выдал тебе машину: <b>{card.get('name_ru', car_key)}</b>\n\n{footer()}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

            elif action == "car_remove":
                car_key = text.lower()
                garage = get_user_garage(target_user_id)
                target_row = next((row for row in garage if row.get("name") == car_key), None)
                if not target_row:
                    await message.answer(
                        f"{header()}\n\n❌ У игрока нет этой машины в гараже\n\n{footer()}",
                        parse_mode="HTML",
                    )
                    return
                delete_car_from_garage(target_row["id"])
                card = CARDS.get(car_key, {})
                car_name = card.get("name_ru", car_key)
                await message.answer(
                    f"{header()}\n\n✅ Машина удалена: <b>{car_name}</b>\n\n{footer()}",
                    parse_mode="HTML",
                )
                try:
                    await bot.send_message(
                        target_user_id,
                        f"{header()}\n\n🗑 Администратор удалил у тебя машину: <b>{car_name}</b>\n\n{footer()}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

            ADMIN_USER_EDIT_PENDING.pop(message.from_user.id, None)

            updated_user = get_user(target_user_id)
            await message.answer(
                f"{header()}\n\n"
                "Выбери следующее действие:\n\n"
                f"ID: <code>{target_user_id}</code>\n"
                f"Баланс: <b>{updated_user['coins']}</b> Coins\n\n"
                f"{footer()}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(text="➕ Монеты", callback_data=f"admin:edit_set:{target_user_id}:coins_add"),
                            InlineKeyboardButton(text="➖ Монеты", callback_data=f"admin:edit_set:{target_user_id}:coins_sub"),
                        ],
                        [InlineKeyboardButton(text="💰 Установить баланс", callback_data=f"admin:edit_set:{target_user_id}:coins_set")],
                        [InlineKeyboardButton(text="🚗 Выдать машину", callback_data=f"admin:edit_set:{target_user_id}:car_add")],
                        [InlineKeyboardButton(text="🗑 Забрать машину", callback_data=f"admin:edit_set:{target_user_id}:car_remove")],
                        [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
                    ]
                ),
                parse_mode="HTML",
            )
            return

        except ValueError:
            await message.answer(
                f"{header()}\n\n"
                "❌ Неверный формат данных\n"
                "Проверь ввод и отправь снова\n\n"
                f"{footer()}",
                parse_mode="HTML",
            )
            return

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
            reply_markup=main_menu_kb(sender.id),
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
            reply_markup=main_menu_kb(sender.id),
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
                    reply_markup=main_menu_kb(sender.id),
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
            reply_markup=main_menu_kb(sender.id),
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
            reply_markup=main_menu_kb(sender.id),
            parse_mode="HTML",
        )

# =========================
# PROFILE
# =========================

@dp.callback_query(F.data == "menu:profile")
async def profile_menu(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("⛔ Профиль не найден. Нажми /start", show_alert=True)
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
    xp_total = int(user.get("xp_total") or 0)
    level = get_level_by_xp(xp_total)
    next_level_xp = get_next_level_xp(level)
    xp_to_next_level = 0 if next_level_xp <= 0 else max(0, next_level_xp - xp_total)
    next_level_text = "MAX" if level >= max(1, MAX_LEVEL) else f"{xp_to_next_level} XP"
    if next_level_xp <= 0:
        xp_bar_text = render_progress_bar(1, 1)
    else:
        level_floor_xp = get_level_floor_xp(level)
        level_span_xp = max(1, next_level_xp - level_floor_xp)
        level_progress_xp = max(0, xp_total - level_floor_xp)
        xp_bar_text = render_progress_bar(level_progress_xp, level_span_xp)

    text = (
        f"{header()}\n\n"
        "👤 <b>Профиль</b>\n\n"
        f"🪪 <b>Ник:</b> {nick}\n"
        f"🆔 <b>ID:</b> <code>{user['user_id']}</code>\n"
        f"💰 <b>Баланс:</b> {fmt_coins(user['coins'])}\n"
        f"⭐ <b>Опыт:</b> {fmt_xp(xp_total)}\n"
        f"🏅 <b>Уровень:</b> {level}\n"
        f"🎯 <b>До следующего:</b> {next_level_text}\n"
        f"📊 <b>Прогресс:</b> {xp_bar_text}\n"
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
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    clear_admin_pending_states(call.from_user.id)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Вся аналитика", callback_data="admin:all_analytics")],
            [InlineKeyboardButton(text="📅 Статус недели", callback_data="admin:week")],
            [InlineKeyboardButton(text="⚡ Быстрый раунд", callback_data="admin:fast_tap_menu")],
            [InlineKeyboardButton(text="🛡 Гарант дублей", callback_data="admin:duplicate_pity")],
            [InlineKeyboardButton(text="📋 Список игроков", callback_data="admin:users")],
            [InlineKeyboardButton(text="🚗 Список машин", callback_data="admin:cars_menu")],
            [InlineKeyboardButton(text="👤 Профиль игрока", callback_data="admin:user_profile")],
            [InlineKeyboardButton(text="🔎 Поиск по нику", callback_data="admin:user_find")],
            [InlineKeyboardButton(text="✏️ Редактировать игрока", callback_data="admin:edit_user")],
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
            "⛔ Доступ запрещён\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return

    clear_admin_pending_states(message.from_user.id)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Вся аналитика", callback_data="admin:all_analytics")],
            [InlineKeyboardButton(text="📅 Статус недели", callback_data="admin:week")],
            [InlineKeyboardButton(text="⚡ Быстрый раунд", callback_data="admin:fast_tap_menu")],
            [InlineKeyboardButton(text="🛡 Гарант дублей", callback_data="admin:duplicate_pity")],
            [InlineKeyboardButton(text="📋 Список игроков", callback_data="admin:users")],
            [InlineKeyboardButton(text="🚗 Список машин", callback_data="admin:cars_menu")],
            [InlineKeyboardButton(text="👤 Профиль игрока", callback_data="admin:user_profile")],
            [InlineKeyboardButton(text="🔎 Поиск по нику", callback_data="admin:user_find")],
            [InlineKeyboardButton(text="✏️ Редактировать игрока", callback_data="admin:edit_user")],
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


@dp.callback_query(F.data.startswith("admin:all_analytics"))
async def admin_all_analytics(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    full_mode = str(call.data or "") == "admin:all_analytics:full"

    stats = get_admin_summary_stats()
    xp_stats = get_xp_analytics(7)
    eco = get_economy_analytics(7)
    race_eco = get_race_economy_analytics(7)

    xp_source_lines = [
        f"• <b>{row['source']}</b>: {fmt_xp(row['amount'])}"
        for row in xp_stats.get("top_sources", [])
    ]
    faucet_lines = [
        f"• <b>{row['source']}</b>: +{fmt_coins(row['amount'])}"
        for row in eco.get("top_faucet_sources", [])
    ]
    sink_lines = [
        f"• <b>{row['source']}</b>: -{fmt_coins(row['amount'])}"
        for row in eco.get("top_sink_sources", [])
    ]

    users_count = max(1, int(stats.get("users_count", 0)))
    eco_net = int(eco.get("net", 0))
    race_faucet = int(race_eco.get("faucet", 0))
    race_sink = int(race_eco.get("sink", 0))
    race_net = int(race_eco.get("net", 0))
    race_count = int(race_eco.get("races_played", 0))
    race_unique = int(race_eco.get("unique_racers", 0))
    net_per_user = eco_net / users_count

    recommendations = []
    if eco_net > 0:
        recommendations.append(
            f"• <b>Инфляция Coins</b>: net +{format_number(eco_net)}. Снизь faucet или усили sink на ~<b>{format_number(max(1, int(eco_net * 0.6)))}</b> Coins/нед."
        )
    elif eco_net < 0:
        recommendations.append(
            f"• <b>Дефляция Coins</b>: net {format_number(eco_net)}. Ослабь sink или добавь faucet на ~<b>{format_number(max(1, int(abs(eco_net) * 0.4)))}</b> Coins/нед."
        )
    else:
        recommendations.append("• <b>Баланс Coins</b>: net около нуля, держи текущие коэффициенты.")

    if race_count < max(8, users_count // 2):
        recommendations.append(
            "• <b>Низкая активность гонок</b>: добавь daily-задачу на гонки и маленькую награду за участие, чтобы поднять вовлечённость."
        )

    if race_count > 0 and race_sink > race_faucet * 8:
        recommendations.append(
            "• <b>Гонки слишком дорогие</b>: тюнинг сильно дороже побед. Добавь утешительную выплату за заезд/поражение или снизь стоимость ранних апгрейдов."
        )

    if net_per_user > 15000:
        recommendations.append(
            "• <b>Высокий приток на игрока</b>: увеличь цену платного кейса ещё на 10–15% или снизь награды стрика/дневок на 10%."
        )

    recommendations_text = "\n".join(recommendations[:4]) if recommendations else "• Данных пока мало для уверенных рекомендаций."
    recommendations_compact = "\n".join(recommendations[:2]) if recommendations else "• Данных пока мало для уверенных рекомендаций."

    xp_top_line = xp_source_lines[0] if xp_source_lines else "• Пока нет данных"
    faucet_top_line = faucet_lines[0] if faucet_lines else "• Пока нет данных"
    sink_top_line = sink_lines[0] if sink_lines else "• Пока нет данных"

    if full_mode:
        analytics_text = (
            f"{header()}\n\n"
            "📊 <b>Сводная аналитика (7 дней) — полный режим</b>\n\n"
            "<b>1) База проекта</b>\n"
            "ℹ️ Отвечает за общий масштаб и заполненность БД.\n"
            f"👥 Пользователей: <b>{format_number(stats['users_count'])}</b>\n"
            f"🚗 Машин в гаражах: <b>{format_number(stats['garage_count'])}</b>\n"
            f"📅 Записей дневок: <b>{format_number(stats['daily_rows'])}</b>\n"
            f"🏁 Записей недельки: <b>{format_number(stats['weekly_rows'])}</b>\n\n"
            "<b>2) XP-прогресс</b>\n"
            "ℹ️ Отвечает за скорость прокачки игроков.\n"
            f"🧮 Общий XP: <b>{fmt_xp(xp_stats['total_xp'])}</b>\n"
            f"📊 Средний XP: <b>{format_number(round(xp_stats['avg_xp']))}</b>\n"
            f"🏆 Максимальный XP: <b>{fmt_xp(xp_stats['max_xp'])}</b>\n"
            f"📈 Начислено за 7 дней: <b>{fmt_xp(xp_stats['xp_last_days'])}</b>\n"
            f"<b>Топ источников XP:</b>\n{chr(10).join(xp_source_lines) if xp_source_lines else 'Пока нет данных'}\n\n"
            "<b>3) Экономика Coins</b>\n"
            "ℹ️ Отвечает за инфляцию/дефляцию валюты.\n"
            f"🟢 Выдано: <b>+{fmt_coins(eco['faucet'])}</b>\n"
            f"🔴 Сожжено: <b>-{fmt_coins(eco['sink'])}</b>\n"
            f"⚖️ Чистый баланс: <b>{'+' if eco_net > 0 else ''}{format_number(eco_net)} Coins</b>\n"
            f"👤 Net на пользователя: <b>{'+' if net_per_user > 0 else ''}{format_number(int(round(net_per_user)))} Coins</b>\n"
            f"<b>Топ источников выдачи:</b>\n{chr(10).join(faucet_lines) if faucet_lines else 'Пока нет данных'}\n"
            f"<b>Топ источников списания:</b>\n{chr(10).join(sink_lines) if sink_lines else 'Пока нет данных'}\n\n"
            "<b>4) Гонки</b>\n"
            "ℹ️ Отвечает за вовлечённость в режим гонок и вклад гонок в экономику.\n"
            f"🏎 Заездов с победителем: <b>{format_number(race_count)}</b>\n"
            f"👤 Уникальных гонщиков: <b>{format_number(race_unique)}</b>\n"
            f"🟢 Выдано за победы: <b>+{fmt_coins(race_faucet)}</b>\n"
            f"🔴 Сожжено на тюнинге: <b>-{fmt_coins(race_sink)}</b>\n"
            f"⚖️ Чистый баланс гонок: <b>{'+' if race_net > 0 else ''}{format_number(race_net)} Coins</b>\n\n"
            "<b>5) Что добавить для нормального баланса</b>\n"
            f"{recommendations_text}\n\n"
            f"{footer()}"
        )
        toggle_button = InlineKeyboardButton(text="🔽 Свернуть", callback_data="admin:all_analytics")
    else:
        analytics_text = (
            f"{header()}\n\n"
            "📊 <b>Сводная аналитика (7 дней) — коротко</b>\n\n"
            "ℹ️ Показывает ключевые метрики. Нажми <b>Развернуть</b> для детального отчёта.\n\n"
            "<b>1) База проекта</b>\n"
            f"👥 Пользователей: <b>{format_number(stats['users_count'])}</b> | 🚗 Машин: <b>{format_number(stats['garage_count'])}</b>\n"
            f"📅 Дневки: <b>{format_number(stats['daily_rows'])}</b> | 🏁 Недельки: <b>{format_number(stats['weekly_rows'])}</b>\n\n"
            "<b>2) XP-прогресс</b>\n"
            f"🧮 Общий XP: <b>{fmt_xp(xp_stats['total_xp'])}</b> | 📈 За 7 дней: <b>{fmt_xp(xp_stats['xp_last_days'])}</b>\n"
            f"🏆 Пик XP: <b>{fmt_xp(xp_stats['max_xp'])}</b>\n"
            f"<b>Топ источник XP:</b> {xp_top_line}\n\n"
            "<b>3) Экономика Coins</b>\n"
            f"🟢 Выдано: <b>+{fmt_coins(eco['faucet'])}</b> | 🔴 Сожжено: <b>-{fmt_coins(eco['sink'])}</b>\n"
            f"⚖️ Net: <b>{'+' if eco_net > 0 else ''}{format_number(eco_net)} Coins</b> | 👤 На пользователя: <b>{'+' if net_per_user > 0 else ''}{format_number(int(round(net_per_user)))}</b>\n"
            f"<b>Главный faucet:</b> {faucet_top_line}\n"
            f"<b>Главный sink:</b> {sink_top_line}\n\n"
            "<b>4) Гонки</b>\n"
            f"🏎 Заездов: <b>{format_number(race_count)}</b> | 👤 Гонщиков: <b>{format_number(race_unique)}</b>\n"
            f"🟢 Победы: <b>+{fmt_coins(race_faucet)}</b> | 🔴 Тюнинг: <b>-{fmt_coins(race_sink)}</b>\n"
            f"⚖️ Net гонок: <b>{'+' if race_net > 0 else ''}{format_number(race_net)} Coins</b>\n\n"
            "<b>5) Что делать сейчас</b>\n"
            f"{recommendations_compact}\n\n"
            f"{footer()}"
        )
        toggle_button = InlineKeyboardButton(text="🔎 Развернуть", callback_data="admin:all_analytics:full")

    await call.message.edit_text(
        analytics_text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [toggle_button],
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
                [InlineKeyboardButton(text="🔙 Меню", callback_data="start")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


async def render_admin_users_page(call: CallbackQuery, page: int):
    page_size = 8
    data = get_users_page(page=page, page_size=page_size)
    total = int(data.get("total", 0))
    users = data.get("users", [])
    safe_page = int(data.get("page", 0))
    total_pages = max(1, math.ceil(total / page_size))

    if safe_page >= total_pages:
        safe_page = max(0, total_pages - 1)
        data = get_users_page(page=safe_page, page_size=page_size)
        users = data.get("users", [])

    lines = []
    keyboard_rows = []
    for row in users:
        uid = int(row.get("user_id", 0))
        username = (row.get("username") or "").strip()
        first_name = (row.get("first_name") or "Игрок").strip()
        nick = f"@{username}" if username else first_name
        short_nick = nick if len(nick) <= 24 else f"{nick[:23]}…"
        lines.append(f"• {short_nick} — <code>{uid}</code>")
        keyboard_rows.append([
            InlineKeyboardButton(
                text=f"👤 {short_nick}",
                callback_data=f"admin:user_open:{uid}:{safe_page}",
            )
        ])

    nav_row = []
    if safe_page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin:users:page:{safe_page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"{safe_page + 1}/{total_pages}", callback_data="noop"))
    if safe_page + 1 < total_pages:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"admin:users:page:{safe_page + 1}"))
    if nav_row:
        keyboard_rows.append(nav_row)

    keyboard_rows.append([InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")])

    await call.message.edit_text(
        f"{header()}\n\n"
        "📋 <b>Список игроков</b>\n\n"
        "Нажми на ник, чтобы открыть профиль игрока.\n\n"
        f"👥 Всего игроков: <b>{format_number(total)}</b>\n"
        f"📄 Страница: <b>{safe_page + 1}/{total_pages}</b>\n\n"
        f"{chr(10).join(lines) if lines else 'Пока нет зарегистрированных игроков.'}\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "admin:users")
async def admin_users_list(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await render_admin_users_page(call, page=0)
    await call.answer()


@dp.callback_query(F.data.startswith("admin:users:page:"))
async def admin_users_list_page(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    parts = (call.data or "").split(":")
    page = 0
    if len(parts) >= 4 and parts[3].isdigit():
        page = int(parts[3])

    await render_admin_users_page(call, page=page)
    await call.answer()


@dp.callback_query(F.data.startswith("admin:user_open:"))
async def admin_user_open_from_list(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    parts = (call.data or "").split(":")
    if len(parts) < 4 or not parts[2].isdigit():
        await call.answer("❌ Некорректный ID", show_alert=True)
        return

    target_user_id = int(parts[2])
    page = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else 0
    text, kb = build_admin_player_profile_view(target_user_id, back_callback=f"admin:users:page:{page}")
    if not text:
        await call.answer("❌ Игрок не найден", show_alert=True)
        return

    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "admin:cars_menu")
async def admin_cars_menu(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await call.message.edit_text(
        f"{header()}\n\n"
        "🚗 <b>Список машин</b>\n\n"
        "Выбери редкость, чтобы посмотреть ключи для выдачи:\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⚪ Обычные", callback_data="admin:cars_rarity:common"),
                    InlineKeyboardButton(text="🔵 Редкие", callback_data="admin:cars_rarity:rare"),
                ],
                [
                    InlineKeyboardButton(text="🟣 Эпические", callback_data="admin:cars_rarity:epic"),
                    InlineKeyboardButton(text="🟡 Легендарные", callback_data="admin:cars_rarity:legendary"),
                ],
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data.startswith("admin:cars_rarity:"))
async def admin_cars_by_rarity(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    rarity_slug = call.data.split(":", 2)[2]
    rarity_value = rarity_slug_to_value(rarity_slug)
    if not rarity_value:
        await call.answer("❌ Неизвестная редкость", show_alert=True)
        return

    rows = get_cars_by_rarity(rarity_value)
    lines = [f"{RARITY_EMOJI.get(rarity_value, '❓')} <code>{car_key}</code> — {car_name}" for car_key, car_name in rows]

    text = (
        f"{header()}\n\n"
        f"🚗 <b>{rarity_value_to_label(rarity_value)}</b>\n"
        f"Всего: <b>{len(rows)}</b>\n\n"
        f"{chr(10).join(lines) if lines else 'Список пуст.'}\n\n"
        f"{footer()}"
    )

    # Страховка от лимита Telegram 4096 символов
    if len(text) > 3900:
        text = (
            f"{header()}\n\n"
            f"🚗 <b>{rarity_value_to_label(rarity_value)}</b>\n"
            f"Всего: <b>{len(rows)}</b>\n\n"
            "Список слишком длинный для одного сообщения.\n"
            "Показываю первые 80:\n\n"
            f"{chr(10).join(lines[:80]) if lines else 'Список пуст.'}\n\n"
            f"{footer()}"
        )

    await call.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К выбору редкости", callback_data="admin:cars_menu")],
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data == "admin:week")
async def admin_week_status(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
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


@dp.callback_query(F.data == "admin:duplicate_pity")
async def admin_duplicate_pity_prompt(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    clear_admin_pending_states(call.from_user.id)
    ADMIN_DUPLICATE_PITY_PENDING.add(call.from_user.id)

    await call.message.edit_text(
        f"{header()}\n\n"
        "🛡 <b>Гарант дублей</b>\n\n"
        f"Текущий порог: <b>{DUPLICATE_PITY_THRESHOLD}</b> дублей подряд\n\n"
        "Отправь новое число (от 1 до 100).\n"
        "Изменение применяется сразу, без перезапуска.\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data == "admin:fast_tap_menu")
async def admin_fast_tap_menu(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    groups = get_all_group_chat_ids()
    now = _fast_tap_local_now()
    start_hour = max(0, min(23, int(FAST_TAP_START_HOUR)))
    end_hour = min(24, max(start_hour + 1, int(FAST_TAP_END_HOUR)))
    in_window = start_hour <= now.hour < end_hour

    text = (
        f"{header()}\n\n"
        "⚡ <b>Быстрый раунд (авто)</b>\n\n"
        f"Режим: <b>{'активен' if in_window else 'вне окна запусков'}</b>\n"
        f"Окно запусков: <b>{start_hour:02d}:00–{end_hour:02d}:00</b>\n"
        f"Лимит на группу: <b>{FAST_TAP_DAILY_LIMIT}/день</b>\n"
        f"Длительность раунда: <b>{max(1, FAST_TAP_WINDOW_SECONDS // 60)} мин</b>\n"
        f"Награда: <b>+{fmt_coins(FAST_TAP_REWARD_COINS)}</b> и <b>+{fmt_xp(FAST_TAP_REWARD_XP)}</b>\n"
        f"Групп в базе: <b>{len(groups)}</b>\n\n"
        "Запуск происходит автоматически и случайно в течение дня.\n"
        "Ручной запуск отключён.\n\n"
        f"{footer()}"
    )

    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:fast_tap_menu")],
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
            ]
        ),
    )
    await call.answer()


@dp.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_menu(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    clear_admin_pending_states(call.from_user.id)

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


@dp.callback_query(F.data == "admin:user_profile")
async def admin_user_profile_prompt(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    clear_admin_pending_states(call.from_user.id)
    ADMIN_PROFILE_LOOKUP_PENDING.add(call.from_user.id)

    await call.message.edit_text(
        f"{header()}\n\n"
        "👤 <b>Профиль игрока</b>\n\n"
        "Отправь ID игрока одним сообщением.\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data == "admin:user_find")
async def admin_user_find_prompt(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    clear_admin_pending_states(call.from_user.id)
    ADMIN_USER_FIND_PENDING.add(call.from_user.id)

    await call.message.edit_text(
        f"{header()}\n\n"
        "🔎 <b>Поиск игрока по нику</b>\n\n"
        "Введи ник или часть ника (можно без @).\n"
        "Также ищет по имени профиля.\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data == "admin:edit_user")
async def admin_edit_user_prompt(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    clear_admin_pending_states(call.from_user.id)
    ADMIN_EDIT_LOOKUP_PENDING.add(call.from_user.id)

    await call.message.edit_text(
        f"{header()}\n\n"
        "✏️ <b>Редактирование игрока</b>\n\n"
        "Отправь ID игрока одним сообщением.\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data.startswith("admin:edit_user_id:"))
async def admin_edit_user_from_profile(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    parts = call.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        await call.answer("❌ Некорректный ID", show_alert=True)
        return

    target_user_id = int(parts[2])
    target_user = get_user(target_user_id)
    if not target_user:
        await call.answer("❌ Игрок не найден", show_alert=True)
        return

    await call.message.edit_text(
        f"{header()}\n\n"
        "🛠 <b>Редактирование игрока</b>\n\n"
        f"ID: <code>{target_user_id}</code>\n"
        f"Баланс: <b>{target_user['coins']}</b> Coins\n\n"
        "Выбери действие:\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="➕ Монеты", callback_data=f"admin:edit_set:{target_user_id}:coins_add"),
                    InlineKeyboardButton(text="➖ Монеты", callback_data=f"admin:edit_set:{target_user_id}:coins_sub"),
                ],
                [InlineKeyboardButton(text="💰 Установить баланс", callback_data=f"admin:edit_set:{target_user_id}:coins_set")],
                [InlineKeyboardButton(text="🚗 Выдать машину", callback_data=f"admin:edit_set:{target_user_id}:car_add")],
                [InlineKeyboardButton(text="🗑 Забрать машину", callback_data=f"admin:edit_set:{target_user_id}:car_remove")],
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data.startswith("admin:edit_set:"))
async def admin_edit_set_action(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    parts = call.data.split(":")
    if len(parts) != 4 or not parts[2].isdigit():
        await call.answer("❌ Некорректные данные", show_alert=True)
        return

    target_user_id = int(parts[2])
    action = parts[3]
    if action not in {"coins_add", "coins_sub", "coins_set", "car_add", "car_remove"}:
        await call.answer("❌ Неизвестное действие", show_alert=True)
        return

    target_user = get_user(target_user_id)
    if not target_user:
        await call.answer("❌ Игрок не найден", show_alert=True)
        return

    ADMIN_USER_EDIT_PENDING[call.from_user.id] = {
        "target_user_id": target_user_id,
        "action": action,
    }

    prompt_map = {
        "coins_add": "Введи сумму для начисления (целое число > 0)",
        "coins_sub": "Введи сумму для списания (целое число > 0)",
        "coins_set": "Введи новый баланс (целое число >= 0)",
        "car_add": "Введи ключ машины из cards.json (например: toyota_camry)",
        "car_remove": "Введи ключ машины для удаления (например: toyota_camry)",
    }

    await call.message.edit_text(
        f"{header()}\n\n"
        "✏️ <b>Редактирование игрока</b>\n\n"
        f"ID: <code>{target_user_id}</code>\n"
        f"{prompt_map[action]}\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="menu:admin")],
            ]
        ),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data.startswith("admin:broadcast_target:"))
async def admin_broadcast_target(call: CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    target = call.data.split(":", 2)[2]
    if target not in {"private", "groups", "all"}:
        await call.answer("❌ Неизвестный тип рассылки", show_alert=True)
        return

    clear_admin_pending_states(call.from_user.id)
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
        await call.answer("⛔ Доступ запрещён", show_alert=True)
        return

    clear_admin_pending_states(call.from_user.id)
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
        await call.answer("⛔ Профиль не найден. Нажми /start", show_alert=True)
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
        await call.answer("⛔ Профиль не найден. Нажми /start", show_alert=True)
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
        lines.append(f"• <b>{task['title']}</b> — {status} (+{fmt_coins(task['reward'])})")

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
        await call.answer("⛔ Профиль не найден. Нажми /start", show_alert=True)
        return

    # Удаляем медиа последнего открытия кейса, если было
    media_msg_id = LAST_STICKER_MESSAGE_ID.pop(call.from_user.id, None)
    if media_msg_id:
        try:
            await bot.delete_message(call.message.chat.id, media_msg_id)
        except Exception:
            pass
    
    paid_case = {
        "name": "Платный",
        "price": PAID_CASE_PRICE,
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
        await call.answer("⛔ Профиль не найден. Нажми /start", show_alert=True)
        return

    case_info = {
        "name": "Платный",
        "price": PAID_CASE_PRICE,
        "rarity_dist": [(0.70, "Common"), (0.90, "Rare"), (0.98, "Epic"), (1.0, "Legendary")],
    }

    if case_type != "paid":
        await call.answer("❌ Неизвестный тип кейса", show_alert=True)
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
        await call.answer("❌ Недостаточно Coins", show_alert=True)
        return

    # Выбираем машину по распределению рарити специфичному для этого кейса
    rand = random.random()
    rarity = "Common"
    for threshold, r in case_info["rarity_dist"]:
        if rand < threshold:
            rarity = r
            break

    # Выбираем машину из этой рарити
    case_cards = COMMON_CARDS + RARE_CARDS + EPIC_CARDS + LEGENDARY_CARDS
    duplicate_streak = int(user.get("duplicate_streak") or 0)
    pity_triggered = False
    if rarity == "Common":
        card_id, pity_triggered = draw_card_with_pity(call.from_user.id, COMMON_CARDS, case_cards, duplicate_streak)
    elif rarity == "Rare":
        card_id, pity_triggered = draw_card_with_pity(call.from_user.id, RARE_CARDS, case_cards, duplicate_streak)
    elif rarity == "Epic":
        card_id, pity_triggered = draw_card_with_pity(call.from_user.id, EPIC_CARDS, case_cards, duplicate_streak)
    else:  # Legendary
        card_id, pity_triggered = draw_card_with_pity(call.from_user.id, LEGENDARY_CARDS, case_cards, duplicate_streak)
    
    if card_id is None:
        await call.answer("❌ Все машины этого кейса уже в твоём гараже!", show_alert=True)
        logger.info(
            "buy_case_no_cards user_id=%s case=%s",
            call.from_user.id,
            case_type,
        )
        return
    
    # Вычитаем Coins только если машина доступна
    subtract_coins(call.from_user.id, case_info["price"], source="buy_paid_case")
    update_last_case_time(call.from_user.id)

    card = CARDS[card_id]
    rarity = card["rarity"]
    is_duplicate = has_car_in_garage(call.from_user.id, card_id)
    duplicate_coins = 0
    xp_gain = int(XP_GAIN_BY_RARITY.get(rarity, XP_GAIN_BY_RARITY["Common"]))
    
    if is_duplicate:
        duplicate_coins = get_duplicate_reward_coins(card, rarity_override=rarity)
        add_coins(call.from_user.id, duplicate_coins, source="duplicate_compensation")
        set_user_duplicate_streak(call.from_user.id, duplicate_streak + 1)
    else:
        add_car_to_garage(call.from_user.id, card_id, rarity)
        set_user_duplicate_streak(call.from_user.id, 0)

    increment_total_cases_opened(call.from_user.id)
    await apply_xp_progress(call.from_user.id, rarity, notify_message=call.message)
    increment_weekly_cases_opened(call.from_user.id, current_week_key(), 1)
    await apply_daily_task_progress(call.from_user.id, "buy_standard", notify_message=call.message)
    if rarity in ("Rare", "Epic", "Legendary"):
        await apply_daily_task_progress(call.from_user.id, "get_rare_plus", notify_message=call.message)
    logger.info(
        "buy_case_opened user_id=%s case=%s card_id=%s rarity=%s price=%s duplicate=%s duplicate_coins=%s pity=%s",
        call.from_user.id,
        case_type,
        card_id,
        rarity,
        case_info["price"],
        is_duplicate,
        duplicate_coins,
        pity_triggered,
    )

    emoji = RARITY_EMOJI.get(rarity, "❓")
    sell_price = get_effective_sell_price(card)
    
    await delete_message_safe(call.message)
    
    duplicate_text = ""
    if is_duplicate:
        duplicate_text = (
            "⚠️ <b>Эта машина уже есть в гараже</b>\n"
            f"♻️ Компенсация: +{fmt_coins(duplicate_coins)}\n"
            "\n"
        )
    pity_text = ""
    if pity_triggered and not is_duplicate:
        pity_text = "🛡 <b>Гарант сработал:</b> выдана новая машина\n\n"

    caption = (
        f"{header()}\n\n"
        f"🎉 <b>Открыт {case_info['name']} кейс</b>\n\n"
        f"🚘 <b>{card['name_ru']}</b>\n"
        f"Редкость: {emoji} {RARITY_RU.get(rarity, rarity)}\n\n"
        f"{pity_text}"
        f"⭐ Опыт: +{fmt_xp(xp_gain)}\n"
        f"{duplicate_text}"
        f"💵 <b>Цена продажи:</b> {fmt_coins(sell_price)}\n\n"
        f"{footer()}"
    )

    result_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="menu:buy_cases"),
                InlineKeyboardButton(text="🏠 Меню", callback_data="start"),
            ]
        ]
    )
    
    success = await send_car_image(
        call.message,
        card,
        rarity,
        caption,
        reply_markup=result_kb,
        user_id=call.from_user.id,
    )
    if not success:
        # Если нет фото - отправим текст с кнопкой
        await call.message.answer(
            caption,
            parse_mode="HTML",
            reply_markup=result_kb,
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
        await call.answer("⛔ Профиль не найден. Нажми /start", show_alert=True)
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

    duplicate_streak = int(user.get("duplicate_streak") or 0)
    free_case_cards = COMMON_CARDS + RARE_CARDS + EPIC_CARDS
    card_id, pity_triggered = draw_card_with_pity(call.from_user.id, free_case_cards, free_case_cards, duplicate_streak)
    
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
    is_duplicate = has_car_in_garage(user["user_id"], card_id)
    duplicate_coins = 0
    xp_gain = int(XP_GAIN_BY_RARITY.get(rarity, XP_GAIN_BY_RARITY["Common"]))

    if is_duplicate:
        duplicate_coins = get_duplicate_reward_coins(card, rarity_override=rarity)
        add_coins(user["user_id"], duplicate_coins, source="duplicate_compensation")
        set_user_duplicate_streak(user["user_id"], duplicate_streak + 1)
    else:
        add_car_to_garage(user["user_id"], card_id, rarity)
        set_user_duplicate_streak(user["user_id"], 0)

    increment_total_cases_opened(user["user_id"])
    await apply_xp_progress(user["user_id"], rarity, notify_message=call.message)
    increment_weekly_cases_opened(user["user_id"], current_week_key(), 1)
    await apply_daily_task_progress(user["user_id"], "free_case", notify_message=call.message)
    if rarity in ("Rare", "Epic", "Legendary"):
        await apply_daily_task_progress(user["user_id"], "get_rare_plus", notify_message=call.message)
    add_coins(user["user_id"], FREE_CASE_BONUS_COINS, source="free_case_bonus")
    update_last_free_case_time(user["user_id"])
    logger.info(
        "free_case_opened user_id=%s card_id=%s rarity=%s bonus=%s duplicate=%s duplicate_coins=%s pity=%s",
        call.from_user.id,
        card_id,
        rarity,
        FREE_CASE_BONUS_COINS,
        is_duplicate,
        duplicate_coins,
        pity_triggered,
    )

    await delete_message_safe(call.message)
    sell_price = get_effective_sell_price(card)
    
    duplicate_text = ""
    if is_duplicate:
        duplicate_text = (
            "⚠️ <b>Эта машина уже есть в гараже</b>\n"
            f"♻️ Компенсация: +{fmt_coins(duplicate_coins)}\n"
            ""
        )
    pity_text = ""
    if pity_triggered and not is_duplicate:
        pity_text = "🛡 <b>Гарант сработал:</b> выдана новая машина\n"

    caption = (
        f"{header()}\n\n"
        "🎁 <b>Бесплатный кейс</b>\n\n"
        f"🚘 <b>{card['name_ru']}</b>\n"
        f"Редкость: {RARITY_EMOJI[rarity]} {RARITY_RU.get(rarity, rarity)}\n"
        f"{pity_text}"
        f"⭐ Опыт: +{fmt_xp(xp_gain)}\n"
        f"{duplicate_text}"
        f"💵 <b>Цена продажи:</b> {fmt_coins(sell_price)}\n"
        f"💰 <b>Бонус:</b> +{fmt_coins(FREE_CASE_BONUS_COINS)}\n\n"
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
        await call.answer("⛔ Профиль не найден. Нажми /start", show_alert=True)
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
            inline_keyboard=[[InlineKeyboardButton(text="🔙 К меню", callback_data="start")]]
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

    kb.append([InlineKeyboardButton(text="🔙 К меню", callback_data="start")])

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
            [InlineKeyboardButton(text=f"💵 Продать за {fmt_coins(sell_price)}", callback_data=f"sell:{car_id}")],
            [
                InlineKeyboardButton(text="🔙 В гараж", callback_data="menu:garage:0"),
                InlineKeyboardButton(text="🏠 К меню", callback_data="start"),
            ],
        ]
    )
    
    caption = (
        f"{header()}\n\n"
        f"🚘 <b>{card['name_ru']}</b>\n"
        f"Редкость: {emoji} {RARITY_RU.get(car['rarity'], car['rarity'])}\n"
        f"💰 <b>Продать за:</b> {fmt_coins(sell_price)}\n\n"
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
    add_coins(call.from_user.id, sell_price, source="sell_car")
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
        f"💰 <b>Получено:</b> +{fmt_coins(sell_price)}\n"
        f"📉 <b>Продано сегодня:</b> {sold_today + 1}/{DAILY_SELL_LIMIT}\n\n"
        f"{footer()}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔙 В гараж", callback_data="menu:garage:0"),
                    InlineKeyboardButton(text="🏠 К меню", callback_data="start"),
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

    duplicate_streak = int(user.get("duplicate_streak") or 0)
    free_case_cards = COMMON_CARDS + RARE_CARDS + EPIC_CARDS
    card_id, pity_triggered = draw_card_with_pity(message.from_user.id, free_case_cards, free_case_cards, duplicate_streak)
    
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
    is_duplicate = has_car_in_garage(user["user_id"], card_id)
    duplicate_coins = 0
    xp_gain = int(XP_GAIN_BY_RARITY.get(rarity, XP_GAIN_BY_RARITY["Common"]))

    if is_duplicate:
        duplicate_coins = get_duplicate_reward_coins(card, rarity_override=rarity)
        add_coins(user["user_id"], duplicate_coins, source="duplicate_compensation")
        set_user_duplicate_streak(user["user_id"], duplicate_streak + 1)
    else:
        add_car_to_garage(user["user_id"], card_id, rarity)
        set_user_duplicate_streak(user["user_id"], 0)

    increment_total_cases_opened(user["user_id"])
    await apply_xp_progress(user["user_id"], rarity, notify_message=message)
    increment_weekly_cases_opened(user["user_id"], current_week_key(), 1)
    increment_weekly_group_cases_opened(message.chat.id, user["user_id"], current_week_key(), 1)
    await apply_daily_task_progress(user["user_id"], "free_case", notify_message=message)
    if rarity in ("Rare", "Epic", "Legendary"):
        await apply_daily_task_progress(user["user_id"], "get_rare_plus", notify_message=message)
    add_coins(user["user_id"], FREE_CASE_BONUS_COINS, source="free_case_bonus")
    update_last_free_case_time(user["user_id"])
    logger.info(
        "group_case_opened user_id=%s chat_id=%s card_id=%s rarity=%s bonus=%s duplicate=%s duplicate_coins=%s pity=%s",
        message.from_user.id,
        message.chat.id,
        card_id,
        rarity,
        FREE_CASE_BONUS_COINS,
        is_duplicate,
        duplicate_coins,
        pity_triggered,
    )
    sell_price = get_effective_sell_price(card)

    duplicate_text = ""
    if is_duplicate:
        duplicate_text = (
            "⚠️ <b>Эта машина уже есть в гараже</b>\n"
            f"♻️ Компенсация: +{fmt_coins(duplicate_coins)}\n"
            ""
        )
    pity_text = ""
    if pity_triggered and not is_duplicate:
        pity_text = "🛡 <b>Гарант сработал:</b> выдана новая машина\n"

    caption = (
        f"{header()}\n\n"
        f"🎁 <b>Кейс {message.from_user.first_name}</b>\n\n"
        f"🚘 <b>{card['name_ru']}</b>\n"
        f"Редкость: {RARITY_EMOJI[rarity]} {RARITY_RU.get(rarity, rarity)}\n"
        f"{pity_text}"
        f"⭐ Опыт: +{fmt_xp(xp_gain)}\n"
        f"{duplicate_text}"
        f"💵 <b>Цена продажи:</b> {fmt_coins(sell_price)}\n"
        f"💰 <b>Бонус:</b> +{fmt_coins(FREE_CASE_BONUS_COINS)}\n\n"
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

    text = f"{header()}\n\n🏆 <b>Топ этой группы</b>\n\n"
    for i, row in enumerate(top, start=1):
        text += f"{i}. <b>{row['first_name']}</b> — {fmt_coins(row['coins'])}\n"
    if not top:
        text += "Пока нет участников с профилем в боте.\n"
    text += f"\n{footer()}"
    
    await message.answer(text, parse_mode="HTML")


@dp.message(F.chat.type != "private", Command("toprace"))
async def top_race_command(message: Message):
    top = await get_group_top_by_race_wins(message.chat.id, 10)

    text = f"{header()}\n\n🏁 <b>Топ по победам в гонках (эта группа)</b>\n\n"
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for i, row in enumerate(top, start=1):
        place = medals.get(i, f"{i}.")
        text += (
            f"{place} <b>{row.get('first_name') or 'Игрок'}</b> — "
            f"{row.get('race_wins', 0)} побед ({row.get('race_total', 0)} заездов)\n"
        )

    if not top:
        text += "Пока нет информации.\n"

    text += f"\n{footer()}"
    await message.answer(text, parse_mode="HTML")


@dp.message(F.chat.type != "private", Command("raceduel"))
async def race_duel_group(message: Message):
    if not can_access_races(message.from_user.id):
        await message.answer(
            f"{header()}\n\n"
            "⛔ Гонки пока в тесте\n"
            "Доступ ограничен для тестового режима.\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return

    reply = message.reply_to_message
    if not reply or not reply.from_user:
        await message.answer(
            f"{header()}\n\n"
            "🏁 Чтобы начать дуэль, ответь командой\n"
            "<code>/raceduel</code> на сообщение соперника.\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return

    challenger_id = message.from_user.id
    opponent_id = reply.from_user.id

    if opponent_id == challenger_id:
        await message.answer("Нельзя вызвать самого себя.")
        return

    if reply.from_user.is_bot:
        await message.answer("С ботом дуэль недоступна.")
        return

    rate_ok, rate_remaining = race_duel_initiator_rate_limit_ok(challenger_id)
    if not rate_ok:
        wait_minutes = max(1, int(math.ceil(rate_remaining / 60)))
        await message.answer(
            f"{header()}\n\n"
            "⏳ Лимит дуэлей\n\n"
            f"Ты можешь предлагать дуэль только 1 раз в час.\n"
            f"Подожди ещё: <b>{wait_minutes} мин</b>.\n\n"
            "Входящие дуэли принимать можно без ограничений.\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return

    challenger_user = get_user(challenger_id)
    opponent_user = get_user(opponent_id)
    if not challenger_user or not opponent_user:
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await message.answer(
            f"{header()}\n\n"
            "👤 Оба участника должны быть зарегистрированы в боте.\n\n"
            f"<a href='{bot_link}'>Открыть бота в ЛС</a>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return

    challenger_car = get_user_race_car_for_duel(challenger_id)
    opponent_car = get_user_race_car_for_duel(opponent_id)
    if not challenger_car or not opponent_car:
        await message.answer(
            f"{header()}\n\n"
            "🚘 У одного из участников нет машины в гараже для дуэли.\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return
    challenger_name = message.from_user.first_name or "Игрок"
    opponent_name = reply.from_user.first_name or "Игрок"
    invite_text = (
        f"{header()}\n\n"
        "🏁 <b>Вызов на дуэль</b>\n\n"
        f"👤 <b>{challenger_name}</b> вызывает на гонку\n"
        f"👤 <b>{opponent_name}</b>\n\n"
        "Принять вызов?\n\n"
        f"{footer()}"
    )

    invite_message = await message.answer(
        invite_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Да",
                        callback_data=f"raceduel:yes:{challenger_id}:{opponent_id}",
                    ),
                    InlineKeyboardButton(
                        text="❌ Нет",
                        callback_data=f"raceduel:no:{challenger_id}:{opponent_id}",
                    ),
                ]
            ]
        ),
    )

    RACE_DUEL_PENDING[(message.chat.id, invite_message.message_id)] = {
        "challenger_id": challenger_id,
        "opponent_id": opponent_id,
        "challenger_name": challenger_name,
        "opponent_name": opponent_name,
        "status": "pending",
    }
    asyncio.create_task(
        expire_race_duel_invite_later(
            chat_id=message.chat.id,
            message_id=invite_message.message_id,
            timeout_seconds=RACE_DUEL_INVITE_TIMEOUT_SECONDS,
        )
    )


@dp.callback_query(F.data.startswith("raceduel:"))
async def race_duel_decision(call: CallbackQuery):
    if call.message.chat.type == "private":
        await call.answer("❌ Только для групп", show_alert=True)
        return

    parts = call.data.split(":")
    if len(parts) != 4:
        await call.answer("❌ Некорректный ответ", show_alert=True)
        return

    action = parts[1]
    try:
        challenger_id = int(parts[2])
        opponent_id = int(parts[3])
    except Exception:
        await call.answer("❌ Некорректный ответ", show_alert=True)
        return

    state_key = (call.message.chat.id, call.message.message_id)
    duel_state = RACE_DUEL_PENDING.get(state_key)
    if not duel_state:
        await call.answer("⌛ Это приглашение уже неактуально", show_alert=True)
        return

    if duel_state.get("status") != "pending":
        await call.answer("⌛ Ответ уже получен", show_alert=True)
        return

    if duel_state.get("challenger_id") != challenger_id or duel_state.get("opponent_id") != opponent_id:
        await call.answer("❌ Некорректный ответ", show_alert=True)
        return

    if call.from_user.id != opponent_id:
        await call.answer("⛔ Ответить может только вызванный игрок", show_alert=True)
        return

    challenger_name = duel_state.get("challenger_name") or "Игрок"
    opponent_name = duel_state.get("opponent_name") or "Игрок"

    if action == "no":
        duel_state["status"] = "rejected"
        RACE_DUEL_PENDING.pop(state_key, None)
        await call.message.edit_text(
            f"{header()}\n\n"
            "🏁 <b>Вызов на дуэль</b>\n\n"
            f"👤 <b>{opponent_name}</b> отклонил вызов от <b>{challenger_name}</b>.\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        await call.answer("❌ Дуэль отклонена")
        return

    if action != "yes":
        await call.answer("❌ Некорректный ответ", show_alert=True)
        return

    duel_state["status"] = "accepted"
    RACE_DUEL_PENDING.pop(state_key, None)
    result_text, duel_played = build_group_duel_result_text(
        challenger_id=challenger_id,
        opponent_id=opponent_id,
        challenger_name=challenger_name,
        opponent_name=opponent_name,
        with_meta=True,
    )

    if duel_played:
        mark_race_duel_initiator_used(challenger_id)

    await call.message.edit_text(result_text, parse_mode="HTML")
    await call.answer("✅ Дуэль принята")


@dp.callback_query(F.data.startswith("fasttap:click:"))
async def fast_tap_click(call: CallbackQuery):
    parts = call.data.split(":")
    if len(parts) != 4:
        await call.answer("❌ Раунд не найден или завершён", show_alert=True)
        return

    chat_id_raw = parts[2]
    round_id = parts[3]
    if not chat_id_raw.lstrip("-").isdigit():
        await call.answer("❌ Раунд не найден или завершён", show_alert=True)
        return

    chat_id = int(chat_id_raw)
    active = FAST_TAP_ACTIVE_ROUNDS.get(chat_id)
    if not active or active.get("round_id") != round_id:
        await call.answer("⌛ Этот раунд уже завершён", show_alert=True)
        return

    if active.get("expires_at", 0) <= time.time():
        await call.answer("⌛ Время вышло", show_alert=True)
        return

    if active.get("winner_id") is not None:
        await call.answer("🏁 Победитель уже определён", show_alert=True)
        return

    user = get_user(call.from_user.id)
    if not user:
        await call.answer("Сначала открой бота в ЛС и нажми /start", show_alert=True)
        return

    active["winner_id"] = call.from_user.id
    add_coins(call.from_user.id, FAST_TAP_REWARD_COINS, source="fast_tap_win")
    await apply_xp_amount_progress(
        call.from_user.id,
        FAST_TAP_REWARD_XP,
        notify_message=call.message,
        source="fast_tap_win",
    )

    winner_name = call.from_user.first_name or "Игрок"
    try:
        await call.message.edit_text(
            f"{header()}\n\n"
            "🏆 <b>Победа в быстром раунде</b>\n\n"
            f"{winner_name}, ты самый быстрый!\n\n"
            f"💰 Награда: +{fmt_coins(FAST_TAP_REWARD_COINS)}\n"
            f"⭐ Опыт: +{fmt_xp(FAST_TAP_REWARD_XP)}\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
    except Exception:
        pass

    FAST_TAP_ACTIVE_ROUNDS.pop(chat_id, None)
    await call.answer("✅ Ты первый!", show_alert=True)


@dp.message(F.chat.type != "private", Command("topweek"))
async def top_week_command(message: Message):
    await process_group_weekly_rewards(message.chat.id)

    week_key = current_week_key()
    top = get_top_users_by_group_weekly_cases(message.chat.id, week_key, 10)

    text = f"{header()}\n\n📅 <b>Топ недели в этой группе</b>\n<code>{week_key}</code>\n\n"
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
        f"💰 {message.from_user.first_name}, баланс: {fmt_coins(user['coins'])}\n\n"
        f"{footer()}",
        parse_mode="HTML",
    )

# =========================
# RUN
# =========================

async def main():
    fast_tap_scheduler_task = None
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
                BotCommand(command="toprace", description="Топ побед в гонках"),
                BotCommand(command="raceduel", description="Дуэль-гонка (по reply)"),
            ],
            scope=BotCommandScopeAllGroupChats()
        )
        
        logger.info("Bot commands set")
        logger.info("Starting polling...")

        fast_tap_scheduler_task = asyncio.create_task(fast_tap_scheduler_loop())
        logger.info(
            "Fast tap scheduler started: window=%02d:00-%02d:00, daily_limit=%s",
            max(0, min(23, int(FAST_TAP_START_HOUR))),
            min(24, max(max(0, min(23, int(FAST_TAP_START_HOUR))) + 1, int(FAST_TAP_END_HOUR))),
            max(1, FAST_TAP_DAILY_LIMIT),
        )
        
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
        if fast_tap_scheduler_task:
            fast_tap_scheduler_task.cancel()
            try:
                await fast_tap_scheduler_task
            except Exception:
                pass
        await bot.session.close()
        logger.info("Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)