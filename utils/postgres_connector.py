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

    async def fetch_product_tasks_from_postgres(platform_id: str):
    """
    Запрашивает из PostgreSQL все задачи для конкретного platform_id.
    """
    if not platform_id:
        return []
    pool = await get_pg_pool()
    query = "SELECT id, user_id, size FROM public.products WHERE is_active = $1 ORDER BY size"
    async with pool.acquire() as connection:
        rows = await connection.fetch(query, platform_id)
    return rows