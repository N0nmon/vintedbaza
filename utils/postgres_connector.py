# Файл: utils/postgres_connector.py
import asyncpg
from config import settings

pool = None

async def get_pg_pool():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(
            user=settings.pg_user,
            password=settings.pg_password,
            database=settings.pg_database,
            host=settings.pg_host,
            port=settings.pg_port
        )
    return pool

async def fetch_all_products_from_postgres():
    """
    Запрашивает из PostgreSQL ВСЕ строки из таблицы public.products,
    независимо от статуса.
    """
    pool = await get_pg_pool()
    # --- ИЗМЕНЕННЫЙ ЗАПРОС: УБРАНО 'WHERE status = ...' ---
    query = "SELECT id, user_id, is_active, size FROM public.products ORDER BY user_id, is_active, id"
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
    async with pool.acquire() as connection:
        rows = await connection.fetch(query)
    return rows