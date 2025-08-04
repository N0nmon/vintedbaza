# Файл: db/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from .models import Base, User
from config import settings

DATABASE_URL = f"postgresql+asyncpg://{settings.db_user}:{settings.db_pass}@{settings.db_host}:{settings.db_port}/{settings.db_name}"
# Создаем асинхронный "движок" для подключения. Файл БД будет называться "bot.db"
engine = create_async_engine(DATABASE_URL, echo=True, connect_args={"server_settings": {"search_path": "public"}})
# Создаем фабрику сессий для асинхронной работы
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)