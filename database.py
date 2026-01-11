import aiosqlite
import time

class Database:
    def __init__(self, db_path: str = "carcase.db"):
        self.db_path = db_path

    async def create_tables(self):
        """Инициализация таблиц и обновление структуры при необходимости."""
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица пользователей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    coins INTEGER DEFAULT 1000,
                    last_case_time INTEGER DEFAULT 0
                )
            """)
            
            # Обновление существующей таблицы (на случай, если колонка last_case_time отсутствует)
            try:
                await db.execute("ALTER TABLE users ADD COLUMN last_case_time INTEGER DEFAULT 0")
            except aiosqlite.OperationalError:
                pass # Колонка уже существует

            # Таблица гаража
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
        """Проверка, зарегистрирован ли игрок."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)) as cursor:
                result = await cursor.fetchone()
                return result is not None

    async def add_user(self, user_id: int, username: str):
        """Регистрация нового игрока."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, username, last_case_time) VALUES (?, ?, 0)",
                (user_id, username)
            )
            await db.commit()

    async def get_user(self, user_id: int):
        """Получение данных профиля пользователя."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                return await cursor.fetchone()

    async def update_last_case_time(self, user_id: int):
        """Запись времени последнего открытия кейса."""
        async with aiosqlite.connect(self.db_path) as db:
            current_time = int(time.time())
            await db.execute("UPDATE users SET last_case_time = ? WHERE user_id = ?", (current_time, user_id))
            await db.commit()

    async def add_car_to_garage(self, user_id: int, car_name: str, rarity: str):
        """Добавление автомобиля в коллекцию игрока."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO garage (user_id, car_name, rarity) VALUES (?, ?, ?)",
                (user_id, car_name, rarity)
            )
            await db.commit()

    async def get_user_garage(self, user_id: int):
        """Получение списка всех машин в гараже пользователя."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT car_name, rarity FROM garage WHERE user_id = ?", (user_id,)) as cursor:
                return await cursor.fetchall()

# Глобальный объект для использования в bot.py
db = Database()
