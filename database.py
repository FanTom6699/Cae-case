import aiosqlite

class Database:
    def __init__(self, db_path: str = "carcase.db"):
        self.db_path = db_path

    async def create_tables(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица игроков
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    coins INTEGER DEFAULT 1000
                )
            """)
            # Таблица инвентаря (Гараж)
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

    async def register_user(self, user_id: int, username: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
                (user_id, username)
            )
            await db.commit()

    async def get_user_balance(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

db = Database()
