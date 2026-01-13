import sqlite3
from datetime import datetime

DB_NAME = "database.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # Users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        coins INTEGER DEFAULT 0,
        last_case_time TEXT
    )
    """)

    # Garage
    cur.execute("""
    CREATE TABLE IF NOT EXISTS garage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        car_name TEXT,
        rarity TEXT,
        obtained_at TEXT
    )
    """)

    # Migrations
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]

    if "cases_common" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN cases_common INTEGER DEFAULT 0")

    if "daily_streak" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN daily_streak INTEGER DEFAULT 0")

    if "last_daily" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN last_daily TEXT")

    conn.commit()
    conn.close()


# =========================
# USERS
# =========================

def add_user(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, coins, cases_common, daily_streak) VALUES (?, ?, ?, ?)",
        (user_id, 0, 1, 0)
    )
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, coins, last_case_time, cases_common, daily_streak, last_daily FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "user_id": row[0],
        "coins": row[1],
        "last_case_time": row[2],
        "cases_common": row[3],
        "daily_streak": row[4],
        "last_daily": row[5],
    }

def update_user_coins(user_id, amount):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def set_user_coins(user_id, amount):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET coins = ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def set_daily(user_id, streak, date):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?",
        (streak, date, user_id)
    )
    conn.commit()
    conn.close()


# =========================
# CASES
# =========================

def add_common_case(user_id, amount=1):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET cases_common = cases_common + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def remove_common_case(user_id, amount=1):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET cases_common = cases_common - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()


# =========================
# GARAGE
# =========================

def add_car_to_garage(user_id, car_name, rarity):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO garage (user_id, car_name, rarity, obtained_at) VALUES (?, ?, ?, ?)",
        (user_id, car_name, rarity, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def get_user_garage(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT car_name, rarity FROM garage WHERE user_id = ? ORDER BY id DESC",
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()

    return [{"name": r[0], "rarity": r[1]} for r in rows]
