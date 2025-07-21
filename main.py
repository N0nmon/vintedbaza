import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from db.database import create_tables, async_session
from db.models import User

from middlewares.access_control import AccessControlMiddleware
from handlers import common_handlers, admin_handlers

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils.scheduler import check_unconfirmed_sales
from utils.gmail_checker import check_gmail

async def on_startup():
    # Создаем папку для медиа, если ее нет
    if not os.path.exists('media'):
        os.makedirs('media')

    # await create_tables()
    async with async_session() as session:
        admin = await session.get(User, settings.admin_id)
        if not admin:
            session.add(User(user_id=settings.admin_id, username='Admin', is_admin=True))
            await session.commit()

async def main():
    logging.basicConfig(level=logging.INFO)
    
    storage = MemoryStorage()
    
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=storage)
    
    dp.message.middleware(AccessControlMiddleware())
    
    dp.include_router(admin_handlers.router)
    dp.include_router(common_handlers.router)
    
    # --- НАЧАЛО БЛОКА: Код планировщика ---
    scheduler = AsyncIOScheduler(timezone="Europe/Warsaw")
    # Запускаем проверку каждый день в 11:00 по Варшаве
    scheduler.add_job(check_unconfirmed_sales, 'cron', hour=15, minute=0, kwargs={'bot': bot}) # Проверка неподтвержденных продаж каждый день в 15:00 по Варшаве
    scheduler.add_job(check_gmail, 'interval', minutes=1, kwargs={'bot': bot}) # Проверка почты каждую минуту
    scheduler.start()
    # --- КОНЕЦ БЛОКА ---

    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен.")
