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
FEEDBACK_CHAT_ID = int(os.getenv("FEEDBACK_CHAT_ID", "-1003802493555"))

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
GARAGE_PAGE_SIZE = 5
GROUP_CASE_RATE_LIMIT_SECONDS = int(os.getenv("GROUP_CASE_RATE_LIMIT_SECONDS", "30"))
GROUP_CASE_RATE_LIMIT = {}
FEEDBACK_PENDING = {}
LAST_STICKER_MESSAGE_ID = {}  # user_id -> message_id последнего стикера
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

def main_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Бесплатный кейс", callback_data="menu:free")],
            [InlineKeyboardButton(text="💳 Купить кейс", callback_data="menu:buy_cases")],
            [InlineKeyboardButton(text="🚗 Гараж", callback_data="menu:garage:0")],
            [InlineKeyboardButton(text="✍️ Отзыв", callback_data="menu:feedback")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats")],
            [InlineKeyboardButton(text="💰 Баланс", callback_data="menu:balance")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
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


async def send_stats(target, from_callback=False):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Топ по Coins", callback_data="stats:coins")],
            [InlineKeyboardButton(text="🚗 Топ по коллекции", callback_data="stats:collection")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="start")],
        ]
    )

    text = (
        f"{header()}\n\n"
        "📊 <b>Статистика</b>\n\n"
        "Выбери что хочешь посмотреть:\n\n"
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
        line_format = lambda i, row, medals: f"{medals.get(i, f'({i})')} <b>{row['first_name'] or 'Unknown'}</b> — {row['coins']} 💰"
    else:
        top = get_top_users_by_collection(10)
        total_cards = len(CARDS)
        title = "🚗 <b>ТОП ПО КОЛЛЕКЦИИ</b>"
        line_format = lambda i, row, medals: f"{medals.get(i, f'({i})')} <b>{row['first_name'] or 'Unknown'}</b> — {row['count']}/{total_cards} 🚗"

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = []
    for i, row in enumerate(top, start=1):
        lines.append(line_format(i, row, medals))

    text = (
        f"{header()}\n\n"
        f"{title}\n\n"
        f"{chr(10).join(lines) if lines else 'Пусто'}\n\n"
        f"{footer()}"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:stats")],
        ]
    )

    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


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
            f"📝 Нажми на file_id чтобы скопировать\n\n"
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
            f"Выбери действие ниже и начни играть!\n\n"
            f"{footer()}",
            reply_markup=main_menu_kb(),
            parse_mode="HTML",
        )
    else:
        # Обычное меню для вернувшихся
        await message.answer(
            f"{header()}\n\n"
            f"Привет, <b>{message.from_user.first_name}</b>!\n"
            f"Выбери действие:\n\n"
            f"{footer()}",
            reply_markup=main_menu_kb(),
            parse_mode="HTML",
        )


@dp.callback_query(F.data == "start")
async def start_menu(call: CallbackQuery):
    if call.message.chat.type != "private":
        await call.answer("❌ Меню доступно только в личных сообщениях", show_alert=True)
        return
    
    # Удаляем стикер машины если был открыт просмотр
    if call.from_user.id in LAST_STICKER_MESSAGE_ID:
        try:
            await bot.delete_message(call.message.chat.id, LAST_STICKER_MESSAGE_ID[call.from_user.id])
            del LAST_STICKER_MESSAGE_ID[call.from_user.id]
        except Exception:
            pass
    
    # Просто редактируем текущее сообщение на меню
    await call.message.edit_text(
        f"{header()}\n\n"
        "Меню\n\n"
        f"{footer()}",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await call.answer()


@dp.callback_query(F.data == "menu:help")
async def help_menu(call: CallbackQuery):
    if call.message.chat.type != "private":
        bot_link = f"https://t.me/{BOT_USERNAME}?start" if BOT_USERNAME else "https://t.me/CarCaseBot?start"
        await call.answer()
        await call.message.answer(
            f"{header()}\n\n"
            "❓ Помощь доступна только в ЛС\n\n"
            f"<a href='{bot_link}'>Нажми сюда</a>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return
    
    help_text = (
        f"{header()}\n\n"
        "<b>❓ Помощь</b>\n\n"
        "<b>📱 Команды:</b>\n"
        "/start - Главное меню\n"
        "/stats - Показать топ игроков\n"
        "/help - Эта справка\n\n"
        "<b>🔊 Триггеры в группе:</b>\n"
        "<b>Открыть кейс:</b>\n"
        "  кейс, case, открыть, open\n"
        "<b>Показать баланс:</b>\n"
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
        "/stats - Показать топ игроков\n"
        "/help - Эта справка\n\n"
        "<b>🔊 Триггеры в группе:</b>\n"
        "<b>Открыть кейс:</b>\n"
        "  кейс, case, открыть, open\n"
        "<b>Показать баланс:</b>\n"
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
            f"<a href='{bot_link}'>Нажми сюда</a> чтобы открыть бота\n\n"
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
# BALANCE
# =========================

@dp.callback_query(F.data == "menu:balance")
async def balance(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Пользователь не найден, используй /start", show_alert=True)
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
            f"<a href='{bot_link}'>Нажми сюда</a>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return
    
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Пользователь не найден, используй /start", show_alert=True)
        return
    
    # Цены случаев
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

    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="start")])

    await call.message.edit_text(
        f"{header()}\n\n"
        "<b>💳 Магазин кейсов</b>\n\n"
        f"💰 <b>У вас:</b> {user['coins']} Coins\n\n"
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
    
    await delete_message_safe(call.message)
    
    caption = (
        f"{header()}\n\n"
        f"🎉 <b>ОТКРЫТ {case_info['name'].upper()} КЕЙС</b>\n\n"
        f"🚘 <b>{card['name_ru']}</b>\n"
        f"Редкость: {emoji} {RARITY_RU.get(rarity, rarity)}\n\n"
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
            f"<a href='{bot_link}'>Нажми сюда</a>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return
    
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Пользователь не найден, используй /start", show_alert=True)
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

    card_id = draw_random_card(call.from_user.id)
    
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
    add_coins(user["user_id"], 100)  # Бонус за бесплатный кейс
    update_last_free_case_time(user["user_id"])
    logger.info(
        "free_case_opened user_id=%s card_id=%s rarity=%s bonus=100",
        call.from_user.id,
        card_id,
        rarity,
    )

    await delete_message_safe(call.message)
    
    caption = (
        f"{header()}\n\n"
        "🎁 <b>БЕСПЛАТНЫЙ КЕЙС</b>\n\n"
        f"🚘 <b>{card['name_ru']}</b>\n"
        f"Редкость: {RARITY_EMOJI[rarity]} {RARITY_RU.get(rarity, rarity)}\n"
        f"💰 <b>Бонус:</b> +100 Coins\n\n"
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
            f"<a href='{bot_link}'>Нажми сюда</a>\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )
        return
    
    page = int(call.data.split(":")[2])
    user = get_user(call.from_user.id)
    if not user:
        await call.answer("❌ Пользователь не найден, используй /start", show_alert=True)
        return
    cars = get_user_garage(user["user_id"])

    # Удаляем стикер машины если был открыт просмотр
    if call.from_user.id in LAST_STICKER_MESSAGE_ID:
        try:
            await bot.delete_message(call.message.chat.id, LAST_STICKER_MESSAGE_ID[call.from_user.id])
            del LAST_STICKER_MESSAGE_ID[call.from_user.id]
        except Exception:
            pass

    if not cars:
        await call.message.edit_text(
            f"{header()}\n\n🚗 Гараж пуст\n\n{footer()}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="start")]]
            ),
            parse_mode="HTML",
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

    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="start")])

    await call.message.edit_text(
        f"{header()}\n\n🚗 <b>Твой гараж</b>\n\n{footer()}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="HTML",
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

    await call.answer()  # Подтверждаем callback
    
    # Отправляем стикер если есть
    sticker_id = card.get("sticker_id", "").strip()
    if sticker_id:
        try:
            sticker_msg = await call.message.answer_sticker(sticker_id)
            LAST_STICKER_MESSAGE_ID[call.from_user.id] = sticker_msg.message_id
        except Exception as e:
            logger.warning(f"Failed to send sticker {sticker_id}: {e}")
    
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
    
    # Редактируем текст (без стикеров в messge, одно сообщение)
    await call.message.edit_text(caption, reply_markup=kb, parse_mode="HTML")


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

    # Удаляем стикер машины если был
    if call.from_user.id in LAST_STICKER_MESSAGE_ID:
        try:
            await bot.delete_message(call.message.chat.id, LAST_STICKER_MESSAGE_ID[call.from_user.id])
            del LAST_STICKER_MESSAGE_ID[call.from_user.id]
        except Exception:
            pass

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

    # Редактируем сообщение вместо отправки нового
    await call.message.edit_text(
        f"{header()}\n\n"
        f"✅ <b>Машина продана!</b>\n\n"
        f"🚘 {card['name_ru']}\n"
        f"💰 <b>Получено:</b> +{sell_price} Coins\n\n"
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
                f"• <code>баланс</code> - показать баланс\n\n"
                f"⚙️ <b>Для администрации:</b>\n"
                f"• <code>/welcome</code> - включить/отключить приветствие новых пользователей\n\n"
                f"<a href='{bot_link}'>Открыть бота в ЛС</a> чтобы начать игру!\n\n"
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
            f"<a href='{bot_link}'>Нажми сюда</a> чтобы открыть бота\n\n"
            f"{footer()}",
            parse_mode="HTML",
        )


@dp.message(F.chat.type != "private", Command("welcome"))
async def welcome_settings(message: Message):
    if not await is_group_admin(message.chat.id, message.from_user.id):
        await message.answer(
            f"{header()}\n\n"
            f"⚙️ Это команда для администрации\n\n"
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
        await call.answer("⚙️ Эта команда для администрации", show_alert=True)
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

    caption = (
        f"{header()}\n\n"
        f"🎁 <b>КЕЙС {message.from_user.first_name}</b>\n\n"
        f"🚘 <b>{card['name_ru']}</b>\n"
        f"Редкость: {RARITY_EMOJI[rarity]} {RARITY_RU.get(rarity, rarity)}\n"
        f"💰 <b>Бонус:</b> +100 Coins\n\n"
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
    top = get_top_users_by_coins(10)
    
    text = f"{header()}\n\n🏆 <b>ГЛОБАЛЬНЫЙ ТОП</b>\n\n"
    for i, row in enumerate(top, start=1):
        text += f"{i}. <b>{row['first_name']}</b> - {row['coins']} 💰\n"
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
            f"👤 {message.from_user.first_name}, зарегистрируйся сначала!\n\n"
            f"<a href='{bot_link}'>Нажми</a>\n\n"
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
                BotCommand(command="balance", description="Показать баланс"),
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