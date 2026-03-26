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
        cases_common INTEGER DEFAULT 0,
        created_at TEXT,
        total_cases_opened INTEGER DEFAULT 0,
        xp_total INTEGER DEFAULT 0,
        level_round_rewarded INTEGER DEFAULT 0,
        last_daily_notify_day TEXT,
        streak_current INTEGER DEFAULT 0,
        streak_best INTEGER DEFAULT 0,
        streak_last_claim_day TEXT,
        duplicate_streak INTEGER DEFAULT 0,
        race_total INTEGER DEFAULT 0,
        race_wins INTEGER DEFAULT 0,
        race_losses INTEGER DEFAULT 0,
        race_draws INTEGER DEFAULT 0,
        dm_status TEXT DEFAULT 'unknown',
        dm_status_updated_at TEXT
    )
    """)

    # =========================
    # DAILY TASKS
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_tasks_progress (
        user_id INTEGER,
        day_key TEXT,
        task_key TEXT,
        progress INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0,
        rewarded INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, day_key, task_key)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_sell_limits (
        user_id INTEGER,
        day_key TEXT,
        sold_count INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, day_key)
    )
    """)

    # =========================
    # WEEKLY STATS
    # =========================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS weekly_case_stats (
        user_id INTEGER,
        week_key TEXT,
        cases_opened INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, week_key)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS weekly_group_case_stats (
        chat_id INTEGER,
        user_id INTEGER,
        week_key TEXT,
        cases_opened INTEGER DEFAULT 0,
        PRIMARY KEY (chat_id, user_id, week_key)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS weekly_group_rewards_log (
        chat_id INTEGER,
        week_key TEXT,
        awarded_at TEXT,
        PRIMARY KEY (chat_id, week_key)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS weekly_global_rewards_log (
        week_key TEXT PRIMARY KEY,
        awarded_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS weekly_global_seen (
        user_id INTEGER,
        week_key TEXT,
        PRIMARY KEY (user_id, week_key)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS xp_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        source TEXT,
        amount INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS economy_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        source TEXT,
        amount INTEGER DEFAULT 0,
        created_at TEXT
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

    if "created_at" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN created_at TEXT"
        )

    if "total_cases_opened" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN total_cases_opened INTEGER DEFAULT 0"
        )

    if "xp_total" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN xp_total INTEGER DEFAULT 0"
        )

    if "level_round_rewarded" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN level_round_rewarded INTEGER DEFAULT 0"
        )

    if "last_daily_notify_day" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN last_daily_notify_day TEXT"
        )

    if "streak_current" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN streak_current INTEGER DEFAULT 0"
        )

    if "streak_best" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN streak_best INTEGER DEFAULT 0"
        )

    if "streak_last_claim_day" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN streak_last_claim_day TEXT"
        )

    if "duplicate_streak" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN duplicate_streak INTEGER DEFAULT 0"
        )

    if "race_total" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN race_total INTEGER DEFAULT 0"
        )

    if "race_wins" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN race_wins INTEGER DEFAULT 0"
        )

    if "race_losses" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN race_losses INTEGER DEFAULT 0"
        )

    if "race_draws" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN race_draws INTEGER DEFAULT 0"
        )

    if "dm_status" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN dm_status TEXT DEFAULT 'unknown'"
        )

    if "dm_status_updated_at" not in columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN dm_status_updated_at TEXT"
        )

    cur.execute(
        "UPDATE users SET created_at = COALESCE(created_at, ?) WHERE created_at IS NULL OR created_at = ''",
        (datetime.utcnow().isoformat(),)
    )
    cur.execute(
        "UPDATE users SET dm_status = COALESCE(NULLIF(dm_status, ''), 'unknown')"
    )

    # Мягкий бэкфилл: для старых пользователей, у кого счётчик ещё 0,
    # проставляем минимум по текущему размеру гаража.
    cur.execute(
        """
        UPDATE users
        SET total_cases_opened = (
            SELECT COUNT(*)
            FROM garage g
            WHERE g.user_id = users.user_id
        )
        WHERE COALESCE(total_cases_opened, 0) = 0
        """
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
        (user_id, username, first_name, coins, cases_common, last_free_case_time, created_at, total_cases_opened, xp_total, level_round_rewarded, last_daily_notify_day, streak_current, streak_best, streak_last_claim_day, duplicate_streak)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, username, first_name, 0, 1, None, datetime.utcnow().isoformat(), 0, 0, 0, None, 0, 0, None, 0)  # 1 стартовый кейс
    )
    cur.execute(
        "UPDATE users SET dm_status = 'active', dm_status_updated_at = ? WHERE user_id = ?",
        (datetime.utcnow().isoformat(), user_id)
    )
    conn.commit()
    conn.close()


def update_user_profile(user_id, username=None, first_name=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET username = ?, first_name = ?, dm_status = 'active', dm_status_updated_at = ? WHERE user_id = ?",
        (username, first_name, datetime.utcnow().isoformat(), user_id)
    )
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, username, first_name, coins, last_case_time, cases_common, last_free_case_time, created_at, total_cases_opened, xp_total, level_round_rewarded, last_daily_notify_day, streak_current, streak_best, streak_last_claim_day, duplicate_streak, race_total, race_wins, race_losses, race_draws, COALESCE(dm_status, 'unknown'), dm_status_updated_at
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
        "last_free_case_time": row[6],
        "created_at": row[7],
        "total_cases_opened": row[8],
        "xp_total": row[9],
        "level_round_rewarded": row[10],
        "last_daily_notify_day": row[11],
        "streak_current": row[12],
        "streak_best": row[13],
        "streak_last_claim_day": row[14],
        "duplicate_streak": row[15],
        "race_total": row[16],
        "race_wins": row[17],
        "race_losses": row[18],
        "race_draws": row[19],
        "dm_status": row[20] or "unknown",
        "dm_status_updated_at": row[21],
    }


def set_user_dm_status(user_id, status):
    normalized = str(status or "").strip().lower()
    if normalized not in {"unknown", "active", "blocked", "deleted"}:
        normalized = "unknown"

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET dm_status = ?, dm_status_updated_at = ? WHERE user_id = ?",
        (normalized, datetime.utcnow().isoformat(), user_id)
    )
    conn.commit()
    conn.close()


def add_race_result(user_id, result):
    normalized = str(result or "").strip().lower()
    if normalized not in {"win", "loss", "draw"}:
        return

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE users
        SET race_total = COALESCE(race_total, 0) + 1,
            race_wins = COALESCE(race_wins, 0) + ?,
            race_losses = COALESCE(race_losses, 0) + ?,
            race_draws = COALESCE(race_draws, 0) + ?
        WHERE user_id = ?
        """,
        (
            1 if normalized == "win" else 0,
            1 if normalized == "loss" else 0,
            1 if normalized == "draw" else 0,
            user_id,
        )
    )
    conn.commit()
    conn.close()


def get_user_race_stats(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(race_total, 0), COALESCE(race_wins, 0), COALESCE(race_losses, 0), COALESCE(race_draws, 0)
        FROM users
        WHERE user_id = ?
        """,
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"total": 0, "wins": 0, "losses": 0, "draws": 0}

    return {
        "total": int(row[0] or 0),
        "wins": int(row[1] or 0),
        "losses": int(row[2] or 0),
        "draws": int(row[3] or 0),
    }


def set_user_streak(user_id, current, best, last_claim_day):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE users
        SET streak_current = ?, streak_best = ?, streak_last_claim_day = ?
        WHERE user_id = ?
        """,
        (current, best, last_claim_day, user_id)
    )
    conn.commit()
    conn.close()


def set_user_duplicate_streak(user_id, value):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET duplicate_streak = ? WHERE user_id = ?",
        (max(0, int(value)), user_id)
    )
    conn.commit()
    conn.close()


def set_last_daily_notify_day(user_id, day_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET last_daily_notify_day = ? WHERE user_id = ?",
        (day_key, user_id)
    )
    conn.commit()
    conn.close()


def increment_total_cases_opened(user_id, amount=1):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET total_cases_opened = COALESCE(total_cases_opened, 0) + ? WHERE user_id = ?",
        (amount, user_id)
    )
    conn.commit()
    conn.close()


def add_user_xp(user_id, amount, source=None):
    delta = max(0, int(amount))
    if delta <= 0:
        return

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET xp_total = COALESCE(xp_total, 0) + ? WHERE user_id = ?",
        (delta, user_id)
    )

    if source:
        cur.execute(
            """
            INSERT INTO xp_events (user_id, source, amount, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, str(source), delta, datetime.utcnow().isoformat())
        )

    conn.commit()
    conn.close()


def set_user_level_round_rewarded(user_id, level_value):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET level_round_rewarded = ? WHERE user_id = ?",
        (max(0, int(level_value)), user_id)
    )
    conn.commit()
    conn.close()


def get_user_rarity_counts(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT rarity, COUNT(*)
        FROM garage
        WHERE user_id = ?
        GROUP BY rarity
        """,
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()

    result = {"Common": 0, "Rare": 0, "Epic": 0, "Legendary": 0}
    for rarity, count in rows:
        result[rarity] = count
    return result


def ensure_daily_task_row(user_id, day_key, task_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO daily_tasks_progress (user_id, day_key, task_key, progress, completed, rewarded)
        VALUES (?, ?, ?, 0, 0, 0)
        """,
        (user_id, day_key, task_key)
    )
    conn.commit()
    conn.close()


def get_daily_tasks_progress(user_id, day_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT task_key, progress, completed, rewarded
        FROM daily_tasks_progress
        WHERE user_id = ? AND day_key = ?
        """,
        (user_id, day_key)
    )
    rows = cur.fetchall()
    conn.close()

    return {
        r[0]: {
            "progress": r[1],
            "completed": bool(r[2]),
            "rewarded": bool(r[3]),
        }
        for r in rows
    }


def add_daily_task_progress(user_id, day_key, task_key, amount, target):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO daily_tasks_progress (user_id, day_key, task_key, progress, completed, rewarded)
        VALUES (?, ?, ?, 0, 0, 0)
        """,
        (user_id, day_key, task_key)
    )

    cur.execute(
        """
        SELECT progress, completed, rewarded
        FROM daily_tasks_progress
        WHERE user_id = ? AND day_key = ? AND task_key = ?
        """,
        (user_id, day_key, task_key)
    )
    row = cur.fetchone()
    prev_progress = row[0] if row else 0
    prev_completed = bool(row[1]) if row else False
    prev_rewarded = bool(row[2]) if row else False

    new_progress = min(prev_progress + amount, target)
    now_completed = new_progress >= target

    cur.execute(
        """
        UPDATE daily_tasks_progress
        SET progress = ?, completed = ?
        WHERE user_id = ? AND day_key = ? AND task_key = ?
        """,
        (new_progress, 1 if now_completed else 0, user_id, day_key, task_key)
    )

    conn.commit()
    conn.close()

    return {
        "progress": new_progress,
        "completed": now_completed,
        "just_completed": (not prev_completed and now_completed),
        "rewarded": prev_rewarded,
    }


def mark_daily_task_rewarded(user_id, day_key, task_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE daily_tasks_progress
        SET rewarded = 1
        WHERE user_id = ? AND day_key = ? AND task_key = ?
        """,
        (user_id, day_key, task_key)
    )
    conn.commit()
    conn.close()


def get_daily_sold_count(user_id, day_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT sold_count
        FROM daily_sell_limits
        WHERE user_id = ? AND day_key = ?
        """,
        (user_id, day_key)
    )
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def increment_daily_sold_count(user_id, day_key, amount=1):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO daily_sell_limits (user_id, day_key, sold_count)
        VALUES (?, ?, 0)
        """,
        (user_id, day_key)
    )
    cur.execute(
        """
        UPDATE daily_sell_limits
        SET sold_count = sold_count + ?
        WHERE user_id = ? AND day_key = ?
        """,
        (amount, user_id, day_key)
    )
    conn.commit()
    conn.close()


def increment_weekly_cases_opened(user_id, week_key, amount=1):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO weekly_case_stats (user_id, week_key, cases_opened)
        VALUES (?, ?, 0)
        """,
        (user_id, week_key)
    )
    cur.execute(
        """
        UPDATE weekly_case_stats
        SET cases_opened = cases_opened + ?
        WHERE user_id = ? AND week_key = ?
        """,
        (amount, user_id, week_key)
    )
    conn.commit()
    conn.close()


def get_top_users_by_weekly_cases(week_key, limit=10):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.user_id, u.username, u.first_name, w.cases_opened
        FROM weekly_case_stats w
        JOIN users u ON u.user_id = w.user_id
        WHERE w.week_key = ?
        ORDER BY w.cases_opened DESC, u.user_id ASC
        LIMIT ?
        """,
        (week_key, limit)
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {"user_id": r[0], "username": r[1], "first_name": r[2], "cases_opened": r[3]}
        for r in rows
    ]


def increment_weekly_group_cases_opened(chat_id, user_id, week_key, amount=1):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO weekly_group_case_stats (chat_id, user_id, week_key, cases_opened)
        VALUES (?, ?, ?, 0)
        """,
        (chat_id, user_id, week_key)
    )
    cur.execute(
        """
        UPDATE weekly_group_case_stats
        SET cases_opened = cases_opened + ?
        WHERE chat_id = ? AND user_id = ? AND week_key = ?
        """,
        (amount, chat_id, user_id, week_key)
    )
    conn.commit()
    conn.close()


def get_top_users_by_group_weekly_cases(chat_id, week_key, limit=10):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.user_id, u.username, u.first_name, w.cases_opened
        FROM weekly_group_case_stats w
        JOIN users u ON u.user_id = w.user_id
        WHERE w.chat_id = ? AND w.week_key = ?
        ORDER BY w.cases_opened DESC, u.user_id ASC
        LIMIT ?
        """,
        (chat_id, week_key, limit)
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {"user_id": r[0], "username": r[1], "first_name": r[2], "cases_opened": r[3]}
        for r in rows
    ]


def clear_weekly_cases_stats(week_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM weekly_case_stats WHERE week_key = ?",
        (week_key,)
    )
    conn.commit()
    conn.close()


def clear_group_weekly_cases_stats(chat_id, week_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM weekly_group_case_stats WHERE chat_id = ? AND week_key = ?",
        (chat_id, week_key)
    )
    conn.commit()
    conn.close()


def get_all_user_ids():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_all_group_chat_ids():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT chat_id FROM group_settings")
    from_settings = [r[0] for r in cur.fetchall()]

    cur.execute("SELECT DISTINCT chat_id FROM weekly_group_case_stats")
    from_weekly = [r[0] for r in cur.fetchall()]

    conn.close()
    return list(set(from_settings + from_weekly))


def get_admin_summary_stats():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM garage")
    garage_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM daily_tasks_progress")
    daily_rows = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM weekly_case_stats")
    weekly_rows = cur.fetchone()[0]

    conn.close()

    return {
        "users_count": users_count,
        "garage_count": garage_count,
        "daily_rows": daily_rows,
        "weekly_rows": weekly_rows,
    }


def has_group_week_rewarded(chat_id, week_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM weekly_group_rewards_log WHERE chat_id = ? AND week_key = ?",
        (chat_id, week_key)
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def mark_group_week_rewarded(chat_id, week_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO weekly_group_rewards_log (chat_id, week_key, awarded_at)
        VALUES (?, ?, ?)
        """,
        (chat_id, week_key, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def has_global_week_rewarded(week_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM weekly_global_rewards_log WHERE week_key = ?",
        (week_key,)
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def mark_global_week_rewarded(week_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO weekly_global_rewards_log (week_key, awarded_at)
        VALUES (?, ?)
        """,
        (week_key, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def has_user_seen_global_week(user_id, week_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM weekly_global_seen WHERE user_id = ? AND week_key = ?",
        (user_id, week_key)
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def mark_user_seen_global_week(user_id, week_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO weekly_global_seen (user_id, week_key) VALUES (?, ?)",
        (user_id, week_key)
    )
    conn.commit()
    conn.close()


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


def get_top_users_by_xp(limit=20):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, username, first_name, COALESCE(xp_total, 0) AS xp_total
        FROM users
        ORDER BY xp_total DESC, user_id ASC
        LIMIT ?
        """,
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {"user_id": r[0], "username": r[1], "first_name": r[2], "xp_total": r[3]}
        for r in rows
    ]


def get_top_users_by_race_wins(limit=10):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, username, first_name,
               COALESCE(race_wins, 0) AS race_wins,
               COALESCE(race_total, 0) AS race_total
        FROM users
        ORDER BY race_wins DESC, race_total DESC, user_id ASC
        LIMIT ?
        """,
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "user_id": r[0],
            "username": r[1],
            "first_name": r[2],
            "race_wins": r[3],
            "race_total": r[4],
        }
        for r in rows
    ]


def get_user_rank_by_xp(user_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT COALESCE(xp_total, 0) FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return None

    user_xp = int(row[0] or 0)
    cur.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE COALESCE(xp_total, 0) > ?
           OR (COALESCE(xp_total, 0) = ? AND user_id < ?)
        """,
        (user_xp, user_xp, user_id)
    )
    higher = int(cur.fetchone()[0] or 0)
    conn.close()
    return higher + 1


def get_xp_analytics(days=7):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users_count = int(cur.fetchone()[0] or 0)

    cur.execute("SELECT COALESCE(SUM(xp_total), 0), COALESCE(AVG(xp_total), 0), COALESCE(MAX(xp_total), 0) FROM users")
    total_xp, avg_xp, max_xp = cur.fetchone()

    cutoff = datetime.utcnow().timestamp() - max(1, int(days)) * 86400
    cutoff_iso = datetime.utcfromtimestamp(cutoff).isoformat()

    cur.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM xp_events
        WHERE created_at >= ?
        """,
        (cutoff_iso,)
    )
    xp_last_days = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT source, COALESCE(SUM(amount), 0) AS total_amount
        FROM xp_events
        WHERE created_at >= ?
        GROUP BY source
        ORDER BY total_amount DESC, source ASC
        LIMIT 5
        """,
        (cutoff_iso,)
    )
    sources = [{"source": r[0] or "unknown", "amount": int(r[1] or 0)} for r in cur.fetchall()]

    conn.close()

    return {
        "users_count": users_count,
        "total_xp": int(total_xp or 0),
        "avg_xp": float(avg_xp or 0),
        "max_xp": int(max_xp or 0),
        "xp_last_days": xp_last_days,
        "top_sources": sources,
    }


def get_economy_analytics(days=7):
    conn = get_connection()
    cur = conn.cursor()

    cutoff_ts = datetime.utcnow().timestamp() - max(1, int(days)) * 86400
    cutoff_iso = datetime.utcfromtimestamp(cutoff_ts).isoformat()

    cur.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM economy_events
        WHERE created_at >= ? AND amount > 0
        """,
        (cutoff_iso,)
    )
    faucet = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT COALESCE(SUM(-amount), 0)
        FROM economy_events
        WHERE created_at >= ? AND amount < 0
        """,
        (cutoff_iso,)
    )
    sink = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT source, COALESCE(SUM(amount), 0) AS total_amount
        FROM economy_events
        WHERE created_at >= ? AND amount > 0
        GROUP BY source
        ORDER BY total_amount DESC, source ASC
        LIMIT 5
        """,
        (cutoff_iso,)
    )
    top_faucet_sources = [
        {"source": r[0] or "unknown", "amount": int(r[1] or 0)}
        for r in cur.fetchall()
    ]

    cur.execute(
        """
        SELECT source, COALESCE(SUM(-amount), 0) AS total_amount
        FROM economy_events
        WHERE created_at >= ? AND amount < 0
        GROUP BY source
        ORDER BY total_amount DESC, source ASC
        LIMIT 5
        """,
        (cutoff_iso,)
    )
    top_sink_sources = [
        {"source": r[0] or "unknown", "amount": int(r[1] or 0)}
        for r in cur.fetchall()
    ]

    conn.close()
    return {
        "faucet": faucet,
        "sink": sink,
        "net": faucet - sink,
        "top_faucet_sources": top_faucet_sources,
        "top_sink_sources": top_sink_sources,
    }


def get_race_economy_analytics(days=7):
        conn = get_connection()
        cur = conn.cursor()

        cutoff_ts = datetime.utcnow().timestamp() - max(1, int(days)) * 86400
        cutoff_iso = datetime.utcfromtimestamp(cutoff_ts).isoformat()

        cur.execute(
                """
                SELECT COALESCE(COUNT(*), 0), COALESCE(SUM(amount), 0)
                FROM economy_events
                WHERE created_at >= ?
                    AND amount > 0
                    AND source LIKE 'race_duel_win_%'
                """,
                (cutoff_iso,)
        )
        races_played, race_faucet = cur.fetchone()

        cur.execute(
                """
                SELECT COALESCE(SUM(-amount), 0)
                FROM economy_events
                WHERE created_at >= ?
                    AND amount < 0
                    AND source LIKE 'race_tune_%'
                """,
                (cutoff_iso,)
        )
        race_sink = int(cur.fetchone()[0] or 0)

        cur.execute(
                """
                SELECT COALESCE(COUNT(DISTINCT user_id), 0)
                FROM economy_events
                WHERE created_at >= ?
                    AND user_id IS NOT NULL
                    AND (
                        source LIKE 'race_duel_win_%'
                        OR source LIKE 'race_tune_%'
                    )
                """,
                (cutoff_iso,)
        )
        unique_racers = int(cur.fetchone()[0] or 0)

        conn.close()

        race_faucet = int(race_faucet or 0)
        races_played = int(races_played or 0)
        return {
                "races_played": races_played,
                "unique_racers": unique_racers,
                "faucet": race_faucet,
                "sink": race_sink,
                "net": race_faucet - race_sink,
        }


def search_users_by_nick(query, limit=20):
    conn = get_connection()
    cur = conn.cursor()
    pattern = f"%{query.lower()}%"
    cur.execute(
        """
        SELECT user_id, username, first_name, coins
        FROM users
        WHERE LOWER(COALESCE(username, '')) LIKE ?
           OR LOWER(COALESCE(first_name, '')) LIKE ?
        ORDER BY coins DESC, user_id ASC
        LIMIT ?
        """,
        (pattern, pattern, limit)
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {"user_id": r[0], "username": r[1], "first_name": r[2], "coins": r[3]}
        for r in rows
    ]


def get_users_page(page=0, page_size=10):
    safe_page = max(0, int(page or 0))
    safe_page_size = max(1, min(50, int(page_size or 10)))
    offset = safe_page * safe_page_size

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    total = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT user_id, username, first_name, coins, COALESCE(dm_status, 'unknown')
        FROM users
        ORDER BY LOWER(COALESCE(NULLIF(username, ''), NULLIF(first_name, ''), CAST(user_id AS TEXT))) ASC,
                 user_id ASC
        LIMIT ? OFFSET ?
        """,
        (safe_page_size, offset),
    )
    rows = cur.fetchall()
    conn.close()

    users = [
        {"user_id": r[0], "username": r[1], "first_name": r[2], "coins": r[3], "dm_status": (r[4] or "unknown")}
        for r in rows
    ]
    return {
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "users": users,
    }


def set_user_coins(user_id, amount):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET coins = ? WHERE user_id = ?",
        (amount, user_id)
    )
    conn.commit()
    conn.close()


def add_coins(user_id, amount, source=None):
    """Добавляет Coins к текущему балансу"""
    delta = max(0, int(amount))
    if delta <= 0:
        return

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET coins = coins + ? WHERE user_id = ?",
        (delta, user_id)
    )
    if source:
        cur.execute(
            """
            INSERT INTO economy_events (user_id, source, amount, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, str(source), delta, datetime.utcnow().isoformat())
        )
    conn.commit()
    conn.close()


def subtract_coins(user_id, amount, source=None):
    """Вычитает Coins из баланса"""
    delta = max(0, int(amount))
    if delta <= 0:
        return

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET coins = coins - ? WHERE user_id = ?",
        (delta, user_id)
    )
    if source:
        cur.execute(
            """
            INSERT INTO economy_events (user_id, source, amount, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, str(source), -delta, datetime.utcnow().isoformat())
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


def update_last_case_time(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET last_case_time = ? WHERE user_id = ?",
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
        SELECT car_name, rarity, user_id, obtained_at
        FROM garage
        WHERE id = ?
        """,
        (car_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return {"name": row[0], "rarity": row[1], "user_id": row[2], "obtained_at": row[3]}


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
