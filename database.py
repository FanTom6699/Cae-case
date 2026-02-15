import sqlite3
from datetime import datetime

DB_NAME = "database.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # =========================
    # USERS
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        coins INTEGER DEFAULT 0,
        last_case_time TEXT,
        last_free_case_time TEXT,
        cases_common INTEGER DEFAULT 0
    )
    """)

    # =========================
    # GARAGE
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS garage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        car_name TEXT,
        rarity TEXT,
        obtained_at TEXT
    )
    """)

    # =========================
    # GROUP SETTINGS
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS group_settings (
        chat_id INTEGER PRIMARY KEY,
        welcome_enabled INTEGER DEFAULT 1
    )
    """)

    # =========================
    # МИГРАЦИИ (БЕЗ ПОТЕРИ ДАННЫХ)
    # =========================
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]

    if "cases_common" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN cases_common INTEGER DEFAULT 0"
        )

    if "last_free_case_time" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN last_free_case_time TEXT"
        )

    if "username" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN username TEXT"
        )

    if "first_name" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN first_name TEXT"
        )

    conn.commit()
    conn.close()


def get_group_welcome_enabled(chat_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT welcome_enabled FROM group_settings WHERE chat_id = ?",
        (chat_id,)
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return True
    return bool(row[0])


def set_group_welcome_enabled(chat_id, enabled):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO group_settings (chat_id, welcome_enabled) VALUES (?, ?)",
        (chat_id, 1 if enabled else 0)
    )
    conn.commit()
    conn.close()


# =========================
# USERS
# =========================

def add_user(user_id, username=None, first_name=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO users 
        (user_id, username, first_name, coins, cases_common, last_free_case_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, username, first_name, 0, 1, None)  # 1 стартовый кейс
    )
    conn.commit()
    conn.close()


def update_user_profile(user_id, username=None, first_name=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
        (username, first_name, user_id)
    )
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, username, first_name, coins, last_case_time, cases_common, last_free_case_time
        FROM users WHERE user_id = ?
        """,
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "user_id": row[0],
        "username": row[1],
        "first_name": row[2],
        "coins": row[3],
        "last_case_time": row[4],
        "cases_common": row[5],
        "last_free_case_time": row[6]
    }


def get_top_users_by_coins(limit=10):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, username, first_name, coins
        FROM users
        ORDER BY coins DESC
        LIMIT ?
        """,
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {"user_id": r[0], "username": r[1], "first_name": r[2], "coins": r[3]}
        for r in rows
    ]


def get_top_users_by_collection(limit=10):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.user_id, u.username, u.first_name, COUNT(DISTINCT g.car_name) AS cnt
        FROM users u
        LEFT JOIN garage g ON u.user_id = g.user_id
        GROUP BY u.user_id
        ORDER BY cnt DESC
        LIMIT ?
        """,
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {"user_id": r[0], "username": r[1], "first_name": r[2], "count": r[3]}
        for r in rows
    ]


def set_user_coins(user_id, amount):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET coins = ? WHERE user_id = ?",
        (amount, user_id)
    )
    conn.commit()
    conn.close()


def add_coins(user_id, amount):
    """Добавляет Coins к текущему балансу"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET coins = coins + ? WHERE user_id = ?",
        (amount, user_id)
    )
    conn.commit()
    conn.close()


def subtract_coins(user_id, amount):
    """Вычитает Coins из баланса"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET coins = coins - ? WHERE user_id = ?",
        (amount, user_id)
    )
    conn.commit()
    conn.close()


# =========================
# FREE CASE
# =========================

def update_last_free_case_time(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET last_free_case_time = ? WHERE user_id = ?",
        (datetime.utcnow().isoformat(), user_id)
    )
    conn.commit()
    conn.close()


# =========================
# CASES
# =========================

def add_common_case(user_id, amount=1):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET cases_common = cases_common + ? WHERE user_id = ?",
        (amount, user_id)
    )
    conn.commit()
    conn.close()


def remove_common_case(user_id, amount=1):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET cases_common = cases_common - ? WHERE user_id = ?",
        (amount, user_id)
    )
    conn.commit()
    conn.close()


# =========================
# GARAGE
# =========================

def add_car_to_garage(user_id, car_name, rarity):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO garage (user_id, car_name, rarity, obtained_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, car_name, rarity, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_user_garage(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, car_name, rarity
        FROM garage
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()

    return [{"id": r[0], "name": r[1], "rarity": r[2]} for r in rows]


def get_car_by_id(car_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT car_name, rarity, user_id
        FROM garage
        WHERE id = ?
        """,
        (car_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return {"name": row[0], "rarity": row[1], "user_id": row[2]}


def delete_car_from_garage(car_id):
    """Удаляет машину из гаража (при продаже)"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM garage WHERE id = ?",
        (car_id,)
    )
    conn.commit()
    conn.close()


def has_car_in_garage(user_id, car_name):
    """Проверяет, есть ли машина в гараже у пользователя"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM garage WHERE user_id = ? AND car_name = ?",
        (user_id, car_name)
    )
    count = cur.fetchone()[0]
    conn.close()
    return count > 0
