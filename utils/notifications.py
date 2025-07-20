from aiogram import Bot
from sqlalchemy import select, func

from db.database import async_session
from db.models import User, Product, Stock, UserProductAccess

async def send_sale_notification(bot: Bot, sold_product: Product, sold_size: str):
    """
    Отправляет уведомление о продаже только тем пользователям,
    у которых есть доступ к этому товару (или администраторам).
    """
    async with async_session() as session:
        # Получаем ID админов
        admin_ids = set((await session.execute(select(User.user_id).where(User.is_admin == True))).scalars().all())
        
        # Получаем ID пользователей с доступом к товару
        access_ids = set((await session.execute(
            select(UserProductAccess.user_id).where(UserProductAccess.product_id == sold_product.id)
        )).scalars().all())

        # Объединяем всех, кому нужно отправить уведомление
        recipient_ids = admin_ids.union(access_ids)

        # Получаем обновленную информацию по остаткам
        stmt = (
            select(Stock.size, func.count(Stock.id).label('count'))
            .where(Stock.product_id == sold_product.id, Stock.is_available == True)
            .group_by(Stock.size)
            .order_by(Stock.size)
        )
        result = await session.execute(stmt)
        sizes_stock = result.all()

    # ИЗМЕНЕНИЕ: Добавляем информацию о проданном размере
    if not sizes_stock:
        response_text = (
            f"**Продажа!**\n\n"
            f"**{sold_product.name}**\n"
            f"Продан размер: **{sold_size}**\n\n"
            f"Это была последняя пара. Товара больше нет в наличии."
        )
    else:
        sizes_info = "\n".join([f"Размер: {size} - {count} шт." for size, count in sizes_stock])
        response_text = (
            f"**Продажа!**\n\n"
            f"**{sold_product.name}**\n"
            f"Продан размер: **{sold_size}**\n\n"
            f"**Новые остатки:**\n{sizes_info}"
        )

    for user_id in recipient_ids:
        try:
            await bot.send_photo(
                chat_id=user_id,
                photo=sold_product.photo_id,
                caption=response_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
