from datetime import datetime, timedelta
from html import escape

from aiogram import Bot
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from db.database import async_session
from db.models import Sale, User
from config import settings

async def check_unconfirmed_sales(bot: Bot):
    """
    Проверяет продажи старше 5 дней и отправляет напоминания.
    """
    five_days_ago = datetime.now() - timedelta(days=5)
    admin_reminders = []

    async with async_session() as session:
        # Находим всех продавцов, у которых есть просроченные неподтвержденные продажи
        stmt = (
            select(Sale.seller_id, User.username, func.count(Sale.id).label("overdue_count"))
            .join(User, Sale.seller_id == User.user_id)
            .where(Sale.is_confirmed == False, Sale.sale_date < five_days_ago)
            .group_by(Sale.seller_id, User.username)
        )
        overdue_sellers = (await session.execute(stmt)).all()

    if not overdue_sellers:
        print(f"[{datetime.now()}] No overdue sales found.")
        return

    # Отправляем напоминания каждому продавцу и собираем инфу для админа
    for seller_id, username, count in overdue_sellers:
        try:
            user_message = (
                f"❗️ <b>Напоминание</b> ❗️\n\n"
                f"У вас есть <b>{count}</b> неподтвержденных продаж старше 5 дней. "
                f"Пожалуйста, проверьте их в разделе 'Мои продажи'."
            )
            await bot.send_message(chat_id=seller_id, text=user_message, parse_mode="HTML")
            admin_reminders.append(f"✅ Уведомление отправлено <b>{escape(username)}</b> ({count} шт.)")
        except Exception as e:
            admin_reminders.append(f"❌ Не удалось уведомить <b>{escape(username)}</b> ({count} шт.): {e}")

    # Отправляем итоговый отчет админу
    if admin_reminders:
        admin_report_header = "Отчет по просроченным продажам:\n\n"
        admin_report = admin_report_header + "\n".join(admin_reminders)
        await bot.send_message(chat_id=settings.admin_id, text=admin_report, parse_mode="HTML")

