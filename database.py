import aiosqlite
import time

class Database:
    def __init__(self, db_path: str = "carcase.db"):
        self.db_path = db_path

    async def create_tables(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    coins INTEGER DEFAULT 1000,
                    last_case_time INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS garage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    car_name TEXT,
                    rarity TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
            """)
            await db.commit()

    async def user_exists(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)) as cursor:
                return await cursor.fetchone() is not None

    async def add_user(self, user_id: int, username: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
                (user_id, username)
            )
            await db.commit()

    async def get_user(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                return await cursor.fetchone()

    async def update_last_case_time(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            current_time = int(time.time())
            await db.execute("UPDATE users SET last_case_time = ? WHERE user_id = ?", (current_time, user_id))
            await db.commit()

    async def add_car_to_garage(self, user_id: int, car_name: str, rarity: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO garage (user_id, car_name, rarity) VALUES (?, ?, ?)",
                (user_id, car_name, rarity)
            )
            await db.commit()

db = Database()
