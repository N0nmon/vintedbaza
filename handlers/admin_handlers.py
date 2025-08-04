import math
import csv
import io
import os
from datetime import datetime, timedelta
from html import escape

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select, delete, func, update
from sqlalchemy.orm import joinedload

from db.database import async_session
from db.models import User, Product, Stock, Sale, UserProductAccess, PlatformAccount, AccountAssignment
from config import settings
from keyboards.admin_keyboards import (
    get_admin_panel_keyboard, create_access_management_keyboard, 
    get_user_management_keyboard, create_user_selection_keyboard, 
    get_product_management_keyboard, create_product_selection_keyboard, 
    get_product_edit_keyboard, create_sales_journal_keyboard,
    get_sale_details_keyboard, get_journal_filter_keyboard,
    create_filter_selection_keyboard, get_status_filter_keyboard,
    create_text_filter_selection_keyboard, get_reports_panel_keyboard,
    get_finance_summary_keyboard, get_account_management_keyboard,
    create_account_selection_keyboard, create_assignment_selection_keyboard,
    get_category_management_keyboard, create_category_selection_keyboard
)
from keyboards.common_keyboards import get_cancel_kb, remove_kb
from states.admin_states import AdminStates, AddProductStates, EditProductStates, JournalFilterStates, ReportStates, AddStockStates, AccountManagementStates, CategoryStates

router = Router()
router.message.filter(F.from_user.id == settings.admin_id)
router.callback_query.filter(F.from_user.id == settings.admin_id)

ITEMS_PER_PAGE = 10

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def safe_edit_text(callback_or_message, text: str, reply_markup: InlineKeyboardMarkup):
    """Безопасно редактирует сообщение, избегая ошибки 'message is not modified'."""
    message = callback_or_message.message if isinstance(callback_or_message, CallbackQuery) else callback_or_message
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in e.message:
            # Это не ошибка, просто игнорируем и отвечаем на колбэк
            if isinstance(callback_or_message, CallbackQuery):
                await callback_or_message.answer()
        else:
            # Другая ошибка, пытаемся восстановиться
            try:
                await message.delete()
                await message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
            except Exception as final_e:
                print(f"Failed to recover from TelegramBadRequest: {final_e}")

# --- КОНЕЦ БЛОКА ---

async def show_admin_panel(message: Message):
    await message.answer("Админ-панель:", reply_markup=get_admin_panel_keyboard())

async def show_sales_journal(callback_or_message, state: FSMContext, page=0):
    message = callback_or_message.message if isinstance(callback_or_message, CallbackQuery) else callback_or_message
    filters = await state.get_data()
    
    async with async_session() as session:
        base_query = select(Sale)
        count_query = select(func.count(Sale.id))
        
        if filters.get('start_date'):
            base_query = base_query.where(Sale.sale_date >= filters['start_date'])
            count_query = count_query.where(Sale.sale_date >= filters['start_date'])
        if filters.get('end_date'):
            base_query = base_query.where(Sale.sale_date <= filters['end_date'])
            count_query = count_query.where(Sale.sale_date <= filters['end_date'])
        if filters.get('seller_id'):
            base_query = base_query.where(Sale.seller_id == filters['seller_id'])
            count_query = count_query.where(Sale.seller_id == filters['seller_id'])
        if filters.get('product_id'):
            base_query = base_query.join(Sale.stock_item).where(Stock.product_id == filters['product_id'])
            count_query = count_query.join(Sale.stock_item).where(Stock.product_id == filters['product_id'])
        if filters.get('account'):
            base_query = base_query.where(Sale.account == filters['account'])
            count_query = count_query.where(Sale.account == filters['account'])
        if 'is_confirmed' in filters:
            base_query = base_query.where(Sale.is_confirmed == filters['is_confirmed'])
            count_query = count_query.where(Sale.is_confirmed == filters['is_confirmed'])
        
        total_sales_count = (await session.execute(count_query)).scalar_one()
        total_pages = math.ceil(total_sales_count / ITEMS_PER_PAGE) if total_sales_count > 0 else 1
        
        stmt = (
            base_query
            .options(joinedload(Sale.stock_item).joinedload(Stock.product))
            .order_by(Sale.sale_date.desc())
            .offset(page * ITEMS_PER_PAGE)
            .limit(ITEMS_PER_PAGE)
        )
        sales = (await session.execute(stmt)).scalars().all()

    if not sales and page == 0:
        text = "Продаж по заданным фильтрам не найдено."
    else:
        text = "📔 Журнал Продаж:"

    keyboard = create_sales_journal_keyboard(sales, page, total_pages)
    
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        try:
            await message.delete()
        except TelegramBadRequest: pass
        await message.answer(text, reply_markup=keyboard)

async def show_product_edit_card(callback_or_message, product_id: int):
    message = callback_or_message.message if isinstance(callback_or_message, CallbackQuery) else callback_or_message
    async with async_session() as session:
        product = await session.get(Product, product_id)
    if not product:
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.answer("Товар не найден.", show_alert=True)
        return
    
    text = (
        f"<b>Название:</b> {escape(product.name)}\n"
        f"<b>Закупочная цена:</b> {product.purchase_price:.2f} zł\n\n"
        "Что вы хотите изменить?"
    )
    
    await message.edit_text(text, parse_mode="HTML", reply_markup=get_product_edit_keyboard(product_id))

def get_period_dates(period: str):
    today = datetime.now().date()
    start_date, end_date = None, None
    if period == "today":
        start_date = datetime.combine(today, datetime.min.time())
        end_date = datetime.combine(today, datetime.max.time())
    elif period == "week":
        start_date = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
        end_date = datetime.combine(start_date.date() + timedelta(days=6), datetime.max.time())
    elif period == "month":
        start_date = datetime.combine(today.replace(day=1), datetime.min.time())
        next_month = start_date.replace(day=28) + timedelta(days=4)
        end_date = datetime.combine(next_month - timedelta(days=next_month.day), datetime.max.time())
    return start_date, end_date

# --- ОБРАБОТЧИКИ ---

@router.message(F.text == "⬅️ Отмена", StateFilter("*"))
@router.message(Command("cancel"), StateFilter("*"))
async def cancel_fsm_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активного действия для отмены.")
        return
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=remove_kb())
    await show_admin_panel(message)

@router.callback_query(F.data == "back_to_admin_panel")
async def handle_back_to_admin_panel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Админ-панель:", reply_markup=get_admin_panel_keyboard())

@router.message(Command("admin"))
async def show_admin_panel_command(message: Message):
    await show_admin_panel(message)

# --- Отчеты и Аналитика ---
@router.callback_query(F.data == "reports_panel")
async def reports_panel_handler(callback: CallbackQuery):
    await callback.message.edit_text("Отчеты и Аналитика:", reply_markup=get_reports_panel_keyboard())

@router.callback_query(F.data == "finance_summary_panel")
async def finance_summary_panel_handler(callback: CallbackQuery):
    await callback.message.edit_text("Выберите период для финансовой сводки:", reply_markup=get_finance_summary_keyboard())

@router.callback_query(F.data.startswith("finance_period_"))
async def show_finance_summary(callback: CallbackQuery):
    period = callback.data.split("_")[-1]
    
    period_text_map = {
        "today": "за сегодня", "week": "за эту неделю",
        "month": "за этот месяц", "all": "за все время"
    }
    period_text = period_text_map.get(period)
    start_date, end_date = get_period_dates(period)

    async with async_session() as session:
        query = select(Sale).options(joinedload(Sale.stock_item).joinedload(Stock.product))
        if start_date and end_date:
            query = query.where(Sale.sale_date.between(start_date, end_date))
        
        all_sales = (await session.execute(query)).scalars().all()

    confirmed_sales = [s for s in all_sales if s.is_confirmed]
    unconfirmed_sales = [s for s in all_sales if not s.is_confirmed]

    conf_revenue = sum(s.price for s in confirmed_sales)
    conf_profit = sum(s.price - s.stock_item.product.purchase_price for s in confirmed_sales if s.stock_item.product.purchase_price > 0)
    conf_sales_count = len(confirmed_sales)
    
    unconf_revenue = sum(s.price for s in unconfirmed_sales)
    unconf_profit = sum(s.price - s.stock_item.product.purchase_price for s in unconfirmed_sales if s.stock_item.product.purchase_price > 0)
    unconf_sales_count = len(unconfirmed_sales)
    
    response_text = (
        f"📊 <b>Финансовая сводка {period_text}</b>\n\n"
        f"<b>--- Подтвержденные ---</b>\n"
        f"<b>Выручка:</b> {conf_revenue:.2f} zł\n"
        f"<b>Чистая прибыль:</b> {conf_profit:.2f} zł\n"
        f"<b>Количество:</b> {conf_sales_count} шт.\n\n"
        f"<b>--- Ожидают подтверждения ---</b>\n"
        f"<b>Потенциальная выручка:</b> {unconf_revenue:.2f} zł\n"
        f"<b>Потенциальная прибыль:</b> {unconf_profit:.2f} zł\n"
        f"<b>Количество:</b> {unconf_sales_count} шт."
    )
    
    await callback.message.edit_text(response_text, parse_mode="HTML", reply_markup=get_finance_summary_keyboard())

@router.callback_query(F.data == "seller_report_start")
async def seller_report_start(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        sellers = (await session.execute(select(User))).scalars().all()
    keyboard = create_user_selection_keyboard(sellers, "select_seller_report")
    await callback.message.edit_text("Выберите продавца для отчета:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("select_seller_report_"))
async def seller_report_process(callback: CallbackQuery):
    seller_id = int(callback.data.split("_")[-1])
    
    async with async_session() as session:
        seller = await session.get(User, seller_id)
        
        stmt = (
            select(Sale)
            .options(joinedload(Sale.stock_item).joinedload(Stock.product))
            .where(Sale.seller_id == seller_id)
        )
        all_sales = (await session.execute(stmt)).scalars().all()

    confirmed_sales = [s for s in all_sales if s.is_confirmed]
    unconfirmed_sales = [s for s in all_sales if not s.is_confirmed]

    conf_revenue = sum(s.price for s in confirmed_sales)
    conf_profit = sum(s.price - s.stock_item.product.purchase_price for s in confirmed_sales if s.stock_item.product.purchase_price > 0)
    
    unconf_revenue = sum(s.price for s in unconfirmed_sales)
    unconf_profit = sum(s.price - s.stock_item.product.purchase_price for s in unconfirmed_sales if s.stock_item.product.purchase_price > 0)

    response_text = (
        f"<b>Отчет по продавцу: {escape(seller.username)}</b> (за все время)\n\n"
        f"<b>--- Подтвержденные ---</b>\n"
        f"<b>Выручка:</b> {conf_revenue:.2f} zł\n"
        f"<b>Прибыль:</b> {conf_profit:.2f} zł\n"
        f"<b>Количество:</b> {len(confirmed_sales)} шт.\n\n"
        f"<b>--- Ожидают подтверждения ---</b>\n"
        f"<b>Потенциальная выручка:</b> {unconf_revenue:.2f} zł\n"
        f"<b>Потенциальная прибыль:</b> {unconf_profit:.2f} zł\n"
        f"<b>Количество:</b> {len(unconfirmed_sales)} шт."
    )
    await callback.message.edit_text(response_text, parse_mode="HTML", reply_markup=get_reports_panel_keyboard())

@router.callback_query(F.data == "export_csv_start")
async def export_csv_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ReportStates.enter_csv_period)
    await callback.message.answer(
        "Введите период для экспорта в формате: <b>ДД.ММ.ГГГГ - ДД.ММ.ГГГГ</b>\n"
        "Или отправьте 'все', чтобы выгрузить все продажи.",
        parse_mode="HTML",
        reply_markup=get_cancel_kb()
    )
    await callback.answer()

@router.message(ReportStates.enter_csv_period)
async def export_csv_process(message: Message, state: FSMContext):
    start_date, end_date = None, None
    if message.text.lower() != 'все':
        try:
            start_str, end_str = [d.strip() for d in message.text.split('-')]
            start_date = datetime.strptime(start_str, "%d.%m.%Y")
            end_date = datetime.strptime(end_str, "%d.%m.%Y").replace(hour=23, minute=59, second=59)
        except ValueError:
            await message.answer("Неверный формат. Попробуйте еще раз.")
            return

    await state.clear()
    await message.answer("Готовлю отчет...", reply_markup=remove_kb())

    async with async_session() as session:
        query = (
            select(Sale)
            .options(
                joinedload(Sale.stock_item).joinedload(Stock.product),
                joinedload(Sale.seller)
            )
            .order_by(Sale.sale_date.asc())
        )
        if start_date and end_date:
            query = query.where(Sale.sale_date.between(start_date, end_date))
        
        sales = (await session.execute(query)).scalars().all()

    if not sales:
        await message.answer("За указанный период нет продаж для экспорта.")
        return

    output = io.StringIO()
    writer = csv.writer(output)
    
    headers = [
        "ID Продажи", "Дата", "Время", "Товар", "Размер", "Продавец", "Аккаунт",
        "Цена продажи (zl)", "Закуп. цена (zl)", "Прибыль (zl)", "Статус", "Ссылка на этикетку"
    ]
    writer.writerow(headers)
    
    for sale in sales:
        profit = sale.price - sale.stock_item.product.purchase_price
        row = [
            sale.id,
            sale.sale_date.strftime('%Y-%m-%d'),
            sale.sale_date.strftime('%H:%M:%S'),
            sale.stock_item.product.name,
            sale.stock_item.size,
            sale.seller.username,
            sale.account,
            sale.price,
            sale.stock_item.product.purchase_price,
            profit,
            "Подтверждена" if sale.is_confirmed else "Не подтверждена",
            sale.label_link
        ]
        writer.writerow(row)
    
    output.seek(0)
    file_data = BufferedInputFile(output.getvalue().encode('utf-8-sig'), filename="sales_report.csv")
    await message.answer_document(file_data)
    await show_admin_panel(message)

# --- Журнал Продаж и его фильтры ---
@router.callback_query(F.data == "sales_journal_reset")
async def sales_journal_reset_and_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_sales_journal(callback, state)

@router.callback_query(F.data == "sales_journal")
async def sales_journal_show_filtered(callback: CallbackQuery, state: FSMContext):
    await show_sales_journal(callback, state)

@router.callback_query(F.data.startswith("journal_page_"))
async def sales_journal_page_handler(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[-1])
    await show_sales_journal(callback, state, page)

@router.callback_query(F.data == "journal_filter")
async def journal_filter_menu(callback: CallbackQuery, state: FSMContext):
    filters = await state.get_data()
    await callback.message.edit_text("Настройте фильтры:", reply_markup=get_journal_filter_keyboard(filters))

@router.callback_query(F.data == "filter_reset")
async def reset_filters(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Фильтры сброшены.", show_alert=True)
    filters = await state.get_data()
    await callback.message.edit_text("Настройте фильтры:", reply_markup=get_journal_filter_keyboard(filters))

@router.callback_query(F.data == "filter_period")
async def filter_by_period_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(JournalFilterStates.enter_period)
    await callback.message.edit_text("Введите период в формате: <b>ДД.ММ.ГГГГ - ДД.ММ.ГГГГ</b>\nИли одну дату: <b>ДД.ММ.ГГГГ</b>", parse_mode="HTML")
    await callback.answer()

@router.message(JournalFilterStates.enter_period)
async def process_period_filter(message: Message, state: FSMContext):
    try:
        if '-' in message.text:
            start_str, end_str = [d.strip() for d in message.text.split('-')]
            start_date = datetime.strptime(start_str, "%d.%m.%Y")
            end_date = datetime.strptime(end_str, "%d.%m.%Y").replace(hour=23, minute=59, second=59)
        else:
            date_str = message.text.strip()
            start_date = datetime.strptime(date_str, "%d.%m.%Y")
            end_date = start_date.replace(hour=23, minute=59, second=59)
        
        await state.update_data(start_date=start_date, end_date=end_date)
    except ValueError:
        await message.answer("Неверный формат даты. Попробуйте еще раз.")
        return
    
    await state.set_state(None)
    filters = await state.get_data()
    await message.delete()
    await message.answer("Фильтр по дате установлен.", reply_markup=get_journal_filter_keyboard(filters))

@router.callback_query(F.data == "filter_seller")
async def filter_by_seller_start(callback: CallbackQuery):
    async with async_session() as session:
        sellers = (await session.execute(select(User))).scalars().all()
    keyboard = create_filter_selection_keyboard(sellers, "set_filter_seller", "username", "user_id")
    await callback.message.edit_text("Выберите продавца:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("set_filter_seller_"))
async def set_seller_filter(callback: CallbackQuery, state: FSMContext):
    seller_id = int(callback.data.split("_")[-1])
    await state.update_data(seller_id=seller_id)
    filters = await state.get_data()
    await callback.message.edit_text("Фильтр по продавцу установлен.", reply_markup=get_journal_filter_keyboard(filters))

@router.callback_query(F.data == "filter_product")
async def filter_by_product_start(callback: CallbackQuery):
    async with async_session() as session:
        products = (await session.execute(select(Product))).scalars().all()
    keyboard = create_filter_selection_keyboard(products, "set_filter_product", "name", "id")
    await callback.message.edit_text("Выберите товар:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("set_filter_product_"))
async def set_product_filter(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[-1])
    await state.update_data(product_id=product_id)
    filters = await state.get_data()
    await callback.message.edit_text("Фильтр по товару установлен.", reply_markup=get_journal_filter_keyboard(filters))

@router.callback_query(F.data == "filter_account")
async def filter_by_account_start(callback: CallbackQuery):
    async with async_session() as session:
        accounts = (await session.execute(select(Sale.account).where(Sale.account.isnot(None)).distinct())).scalars().all()
    if not accounts:
        await callback.answer("Еще не было продаж с указанием аккаунта.", show_alert=True)
        return
    keyboard = create_text_filter_selection_keyboard(accounts, "set_filter_account")
    await callback.message.edit_text("Выберите аккаунт:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("set_filter_account_"))
async def set_account_filter(callback: CallbackQuery, state: FSMContext):
    account = callback.data.replace("set_filter_account_", "", 1)
    await state.update_data(account=account)
    filters = await state.get_data()
    await callback.message.edit_text("Фильтр по аккаунту установлен.", reply_markup=get_journal_filter_keyboard(filters))

@router.callback_query(F.data == "filter_status")
async def filter_by_status_start(callback: CallbackQuery):
    await callback.message.edit_text("Выберите статус:", reply_markup=get_status_filter_keyboard())

@router.callback_query(F.data.startswith("set_filter_status_"))
async def set_status_filter(callback: CallbackQuery, state: FSMContext):
    status = callback.data.split("_")[-1] == "true"
    await state.update_data(is_confirmed=status)
    filters = await state.get_data()
    await callback.message.edit_text("Фильтр по статусу установлен.", reply_markup=get_journal_filter_keyboard(filters))

# --- Просмотр и управление деталями продажи ---
@router.callback_query(F.data.startswith("view_sale_"))
async def view_sale_details(callback: CallbackQuery):
    sale_id = int(callback.data.split("_")[-1])
    
    async with async_session() as session:
        sale = (await session.execute(
            select(Sale).options(
                joinedload(Sale.stock_item).joinedload(Stock.product),
                joinedload(Sale.seller)
            ).where(Sale.id == sale_id)
        )).scalar_one_or_none()

    if not sale:
        await callback.answer("Продажа не найдена.", show_alert=True)
        return

    status = "✅ Подтверждена" if sale.is_confirmed else "❌ Не подтверждена"
    profit = sale.price - sale.stock_item.product.purchase_price
    
    text = (
        f"<b>Продажа №{sale.id}</b>\n\n"
        f"<b>Дата:</b> {sale.sale_date.strftime('%d.%m.%Y %H:%M')}\n"
        f"<b>Товар:</b> {escape(sale.stock_item.product.name)} ({escape(sale.stock_item.size)})\n"
        f"<b>Продавец:</b> {escape(sale.seller.username or str(sale.seller.user_id))}\n"
        f"<b>Аккаунт:</b> {escape(sale.account or 'Не указан')}\n"
        "----------------------------------\n"
        f"<b>Цена продажи:</b> {sale.price:.2f} zł\n"
        f"<b>Закуп. цена:</b> {sale.stock_item.product.purchase_price:.2f} zł\n"
        f"<b>Прибыль:</b> {profit:.2f} zł\n"
        "----------------------------------\n"
        f"<b>Статус:</b> {status}\n"
        f"<b>Ссылка на этикетку:</b> {escape(sale.label_link or 'Нет')}"
    )
    
    keyboard = get_sale_details_keyboard(sale)
    
    await callback.message.delete()
    try:
        await callback.message.answer(text, parse_mode="HTML")
        screenshot = FSInputFile(sale.screenshot_path)
        await callback.message.answer_photo(photo=screenshot, reply_markup=keyboard)
    except Exception as e:
        await callback.message.answer(f"Не удалось загрузить скриншот: {e}", reply_markup=keyboard)
    
    await callback.answer()

@router.callback_query(F.data.startswith("admin_confirm_sale_"))
async def admin_confirm_sale_handler(callback: CallbackQuery, state: FSMContext):
    sale_id = int(callback.data.split("_")[-1])
    async with async_session() as session:
        await session.execute(update(Sale).where(Sale.id == sale_id).values(is_confirmed=True))
        await session.commit()
    await callback.answer("Продажа подтверждена!", show_alert=True)
    await callback.message.delete()
    await show_sales_journal(callback, state)

@router.callback_query(F.data.startswith("admin_return_sale_"))
async def admin_return_sale_handler(callback: CallbackQuery, state: FSMContext):
    sale_id = int(callback.data.split("_")[-1])
    async with async_session() as session:
        sale_to_return = await session.get(Sale, sale_id)
        if sale_to_return:
            stock_id = sale_to_return.stock_id
            await session.execute(update(Stock).where(Stock.id == stock_id).values(is_available=True))
            await session.delete(sale_to_return)
            await session.commit()
            await callback.answer("Продажа отменена, товар возвращен на склад.", show_alert=True)
            await callback.message.delete()
            await show_sales_journal(callback, state)
        else:
            await callback.answer("Продажа не найдена.", show_alert=True)

@router.callback_query(F.data.startswith("admin_delete_sale_"))
async def admin_delete_sale_handler(callback: CallbackQuery, state: FSMContext):
    sale_id = int(callback.data.split("_")[-1])
    async with async_session() as session:
        sale_to_delete = await session.get(Sale, sale_id)
        if sale_to_delete:
            await session.delete(sale_to_delete)
            await session.commit()
            await callback.answer("Запись о продаже удалена.", show_alert=True)
            await callback.message.delete()
            await show_sales_journal(callback, state)
        else:
            await callback.answer("Продажа не найдена.", show_alert=True)

# --- Управление товарами ---
@router.callback_query(F.data == "manage_products")
async def manage_products_menu(callback: CallbackQuery):
    await callback.message.edit_text("Управление товарами:", reply_markup=get_product_management_keyboard())

@router.callback_query(F.data == "add_product")
async def handle_add_product_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddProductStates.name)
    await callback.message.answer("Введите название модели обуви:", reply_markup=get_cancel_kb())
    await callback.answer()

@router.message(AddProductStates.name)
async def handle_product_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Отлично. Теперь отправьте главное фото товара:")
    await state.set_state(AddProductStates.photo)

@router.message(AddProductStates.photo, F.photo)
async def handle_product_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id)
    await message.answer("Фото принято. Теперь введите доступные размеры через запятую:")
    await state.set_state(AddProductStates.sizes)

@router.message(AddProductStates.photo)
async def handle_product_photo_invalid(message: Message):
    await message.answer("Это не фото. Пожалуйста, отправьте фото товара.")

@router.message(AddProductStates.sizes)
async def handle_product_sizes(message: Message, state: FSMContext):
    sizes_text = message.text
    sizes_list = [size.strip() for size in sizes_text.split(',')]
    if not all(size.replace('.', '', 1).isdigit() for size in sizes_list):
        await message.answer("Неправильный формат. Введите размеры числами через запятую.")
        return
    await state.update_data(sizes=sizes_list)
    await message.answer("Размеры приняты. Теперь введите закупочную цену (себестоимость) в zł:")
    await state.set_state(AddProductStates.purchase_price)

@router.message(AddProductStates.purchase_price)
async def handle_purchase_price(message: Message, state: FSMContext):
    """
    Это ПОСЛЕДНИЙ шаг в процессе добавления товара.
    Он принимает цену и сразу сохраняет товар в базу.
    """
    # Проверяем, что введена цена
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("Цена должна быть числом. Попробуйте еще раз.")
        return
    
    # Получаем все данные из состояний
    await state.update_data(purchase_price=float(message.text))
    data = await state.get_data()
    
    # Сразу сохраняем товар в базу данных
    try:
        async with async_session() as session:
            # Создаем товар БЕЗ platform_id. Он автоматически будет NULL (пустым).
            new_product = Product(
                name=data.get('name'), 
                photo_id=data.get('photo_id'),
                purchase_price=data.get('purchase_price')
            )
            session.add(new_product)
            await session.flush()
            
            # Добавляем остатки
            for size in data.get('sizes', []):
                session.add(Stock(product_id=new_product.id, size=size))
            await session.commit()

            # Создаем папку для этикеток
            labels_dir = f"labels/{new_product.id}"
            os.makedirs(labels_dir, exist_ok=True)
            
            await message.answer(f"Товар '{escape(data.get('name'))}' успешно добавлен.", reply_markup=remove_kb())
    except Exception as e:
        await message.answer(f"Произошла ошибка: {e}", reply_markup=remove_kb())
    finally:
        # Очищаем состояние, завершая процесс
        await state.clear()
        await show_admin_panel(message)

@router.callback_query(F.data == "show_product_ids")
async def show_product_ids_handler(callback: CallbackQuery):
    async with async_session() as session:
        products = (await session.execute(select(Product))).scalars().all()

    if not products:
        await callback.answer("В базе данных еще нет товаров.", show_alert=True)
        return

    response_text = "ID всех товаров:\n\n"
    for product in products:
        response_text += f"<b>ID: {product.id}</b> — {escape(product.name)}\n"

    await callback.message.answer(response_text, parse_mode="HTML")
    await callback.answer()

# --- КОНЕЦ БЛОКА ---
# --- Редактирование товара ---
@router.callback_query(F.data == "edit_product")
async def edit_product_start(callback: CallbackQuery):
    async with async_session() as session:
        products = (await session.execute(select(Product))).scalars().all()
    if not products:
        await callback.answer("Товаров для редактирования нет.", show_alert=True)
        return
    await callback.message.edit_text("Выберите товар для редактирования:", reply_markup=create_product_selection_keyboard(products))

async def show_product_edit_card(callback_or_message, product_id: int):
    message = callback_or_message.message if isinstance(callback_or_message, CallbackQuery) else callback_or_message
    async with async_session() as session:
        product = await session.get(Product, product_id)
    if not product:
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.answer("Товар не найден.", show_alert=True)
        return
    
    text = (
        f"<b>Название:</b> {escape(product.name)}\n"
        f"<b>Закупочная цена:</b> {product.purchase_price:.2f} zł\n\n"
        "Что вы хотите изменить?"
    )
    
    await message.edit_text(text, parse_mode="HTML", reply_markup=get_product_edit_keyboard(product_id))

@router.callback_query(F.data.startswith("select_edit_product_"))
async def select_product_to_edit(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[-1])
    await state.update_data(edit_product_id=product_id)
    await show_product_edit_card(callback, product_id)

@router.callback_query(F.data.startswith("edit_name_"))
async def edit_product_name_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditProductStates.new_name)
    await callback.message.answer("Введите новое название товара:", reply_markup=get_cancel_kb())
    await callback.answer()

@router.message(EditProductStates.new_name)
async def edit_product_name_process(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("edit_product_id")
    new_name = message.text
    
    async with async_session() as session:
        await session.execute(update(Product).where(Product.id == product_id).values(name=new_name))
        await session.commit()
    
    await message.answer("Название успешно изменено.", reply_markup=remove_kb())
    await state.clear()
    await show_product_edit_card(message, product_id)

@router.callback_query(F.data.startswith("edit_price_"))
async def edit_product_price_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditProductStates.new_purchase_price)
    await callback.message.answer("Введите новую закупочную цену (в zł):", reply_markup=get_cancel_kb())
    await callback.answer()

@router.message(EditProductStates.new_purchase_price)
async def edit_product_price_process(message: Message, state: FSMContext):
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("Цена должна быть числом. Попробуйте еще раз.")
        return
    data = await state.get_data()
    product_id = data.get("edit_product_id")
    new_price = float(message.text)
    
    async with async_session() as session:
        await session.execute(update(Product).where(Product.id == product_id).values(purchase_price=new_price))
        await session.commit()
        
    await message.answer("Закупочная цена успешно изменена.", reply_markup=remove_kb())
    await state.clear()
    await show_product_edit_card(message, product_id)

# --- НАЧАЛО БЛОКА: Поступление товара ---

@router.callback_query(F.data == "add_stock")
async def add_stock_start(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        products = (await session.execute(select(Product))).scalars().all()
    if not products:
        await callback.answer("Сначала добавьте хотя бы один товар.", show_alert=True)
        return
    
    # Исправлено: Передаем правильный префикс в функцию создания клавиатуры
    keyboard = create_product_selection_keyboard(products, prefix="select_stock_product")
    
    await callback.message.edit_text("Выберите товар для пополнения остатков:", reply_markup=keyboard)
    await state.set_state(AddStockStates.select_product)

@router.callback_query(F.data.startswith("select_stock_product_"), AddStockStates.select_product)
async def add_stock_select_product(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[-1])
    await state.update_data(product_id=product_id)
    
    # Сначала удаляем старое сообщение с кнопками
    await callback.message.delete()
    
    # Затем отправляем новое сообщение с клавиатурой отмены
    await callback.message.answer(
        "Введите размеры для добавления через запятую (например: 41, 42, 42, 43):",
        reply_markup=get_cancel_kb()
    )
    await state.set_state(AddStockStates.enter_sizes)

@router.message(AddStockStates.enter_sizes)
async def add_stock_process_sizes(message: Message, state: FSMContext):
    sizes_text = message.text
    sizes_list = [size.strip() for size in sizes_text.split(',')]
    if not all(size.replace('.', '', 1).isdigit() for size in sizes_list):
        await message.answer("Неправильный формат. Введите размеры числами через запятую или нажмите 'Отмена'.")
        return

    data = await state.get_data()
    product_id = data.get("product_id")

    try:
        async with async_session() as session:
            product = await session.get(Product, product_id)
            for size in sizes_list:
                new_stock_item = Stock(product_id=product_id, size=size)
                session.add(new_stock_item)
            await session.commit()
        
        await message.answer(
            f"Остатки для товара '{escape(product.name)}' успешно пополнены.\n"
            f"Добавлены размеры: {', '.join(sizes_list)}",
            reply_markup=remove_kb()
        )
    except Exception as e:
        await message.answer(f"Произошла ошибка при добавлении размеров: {e}", reply_markup=remove_kb())
    finally:
        await state.clear()
        await show_admin_panel(message)

# --- КОНЕЦ БЛОКА ---        
# --- Управление пользователями ---
@router.callback_query(F.data == "manage_users")
async def handle_manage_users(callback: CallbackQuery):
    await callback.message.edit_text("Управление пользователями:", reply_markup=get_user_management_keyboard())

@router.callback_query(F.data == "add_user")
async def add_user_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.add_user_id)
    await callback.message.answer("Введите ID пользователя для добавления:", reply_markup=get_cancel_kb())
    await callback.answer()

@router.message(AdminStates.add_user_id)
async def add_user_get_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("ID должен быть числом. Попробуйте еще раз.")
        return
    user_id = int(message.text)
    async with async_session() as session:
        existing_user = await session.get(User, user_id)
        if existing_user:
            await message.answer(f"Пользователь с ID {user_id} уже существует.", reply_markup=remove_kb())
            await state.clear()
            await show_admin_panel(message)
            return
    await state.update_data(user_id=user_id)
    await state.set_state(AdminStates.add_user_name)
    await message.answer("Теперь введите имя (ник) пользователя:")

@router.message(AdminStates.add_user_name)
async def add_user_get_name(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get('user_id')
    username = message.text
    try:
        async with async_session() as session:
            new_user = User(user_id=user_id, username=username)
            session.add(new_user)
            await session.commit()
            await message.answer(f"Пользователь {escape(username)} (ID: {user_id}) успешно добавлен.", reply_markup=remove_kb())
    except Exception as e:
        await message.answer(f"Произошла ошибка: {e}", reply_markup=remove_kb())
    finally:
        await state.clear()
        await show_admin_panel(message)

@router.callback_query(F.data == "show_users")
async def handle_show_users(callback: CallbackQuery):
    async with async_session() as session:
        users = await session.execute(select(User))
        user_list = users.scalars().all()
    if not user_list:
        await callback.message.answer("В базе данных нет пользователей.")
        return
    response_text = "Список пользователей:\n\n"
    for user in user_list:
        role = "Админ" if user.is_admin else "Пользователь"
        username = escape(user.username or 'Не указано')
        response_text += f"ID: <code>{user.user_id}</code> | Имя: {username} | Роль: {role}\n"
    await callback.message.answer(response_text, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "delete_user")
async def handle_delete_user_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.delete_user_id)
    await callback.message.answer("Введите ID пользователя, которого хотите удалить:", reply_markup=get_cancel_kb())
    await callback.answer()

@router.message(AdminStates.delete_user_id)
async def handle_delete_user_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("ID должен быть числом. Попробуйте еще раз.")
        return
    user_id_to_delete = int(message.text)
    if user_id_to_delete == settings.admin_id:
        await message.answer("Нельзя удалить самого себя.", reply_markup=remove_kb())
    else:
        async with async_session() as session:
            result = await session.execute(delete(User).where(User.user_id == user_id_to_delete))
            await session.commit()
        if result.rowcount > 0:
            await message.answer(f"Пользователь с ID {user_id_to_delete} успешно удален.", reply_markup=remove_kb())
        else:
            await message.answer(f"Пользователь с ID {user_id_to_delete} не найден.", reply_markup=remove_kb())
    await state.clear()
    await show_admin_panel(message)

# --- Управление доступом к товарам ---
@router.callback_query(F.data == "manage_access")
async def handle_manage_access_start(callback: CallbackQuery):
    async with async_session() as session:
        users = (await session.execute(select(User).where(User.is_admin == False))).scalars().all()
    if not users:
        await callback.answer("Нет пользователей для управления доступом.", show_alert=True)
        return
    keyboard = create_user_selection_keyboard(users, "select_user_access")
    await callback.message.edit_text("Выберите пользователя для настройки доступа:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("select_user_access_"))
async def select_user_for_access(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[-1])
    async with async_session() as session:
        user_to_manage = await session.get(User, user_id)
        all_products = (await session.execute(select(Product))).scalars().all()
        user_access_result = await session.execute(select(UserProductAccess.product_id).where(UserProductAccess.user_id == user_id))
        user_product_ids = set(user_access_result.scalars().all())
    keyboard = create_access_management_keyboard(user_id, all_products, user_product_ids)
    await callback.message.edit_text(f"Настройка доступа для {escape(user_to_manage.username or str(user_id))}:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("toggle_access_"))
async def toggle_product_access(callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id_str, product_id_str = parts[2], parts[3]
    user_id, product_id = int(user_id_str), int(product_id_str)
    async with async_session() as session:
        result = await session.execute(
            select(UserProductAccess).where(
                UserProductAccess.user_id == user_id,
                UserProductAccess.product_id == product_id
            )
        )
        access_entry = result.scalar_one_or_none()
        if access_entry:
            await session.delete(access_entry)
        else:
            session.add(UserProductAccess(user_id=user_id, product_id=product_id))
        await session.commit()
        
        all_products = (await session.execute(select(Product))).scalars().all()
        user_access_result = await session.execute(
            select(UserProductAccess.product_id).where(UserProductAccess.user_id == user_id)
        )
        user_product_ids = set(user_access_result.scalars().all())
        keyboard = create_access_management_keyboard(user_id, all_products, user_product_ids)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()
# --- НАЧАЛО БЛОКА: Исправленное управление аккаунтами ---

@router.callback_query(F.data == "manage_accounts")
async def manage_accounts_menu(callback: CallbackQuery):
    await safe_edit_text(callback, "Управление аккаунтами площадок:", get_account_management_keyboard())

@router.callback_query(F.data == "add_platform_account")
async def add_platform_account_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AccountManagementStates.enter_account_display_name)
    await safe_edit_text(callback, "Введите короткое имя для аккаунта (например, 7b):", InlineKeyboardMarkup(inline_keyboard=[]))
    await callback.answer()

@router.message(AccountManagementStates.enter_account_display_name)
async def add_platform_account_display_name(message: Message, state: FSMContext):
    await state.update_data(display_name=message.text)
    await state.set_state(AccountManagementStates.enter_account_search_name)
    await message.answer("Теперь введите точное имя аккаунта для поиска в письмах (например, Vinted_МойАкк):")

@router.message(AccountManagementStates.enter_account_search_name)
async def add_platform_account_search_name(message: Message, state: FSMContext):
    data = await state.get_data()
    display_name = data.get("display_name")
    search_name = message.text

    try:
        async with async_session() as session:
            new_account = PlatformAccount(display_name=display_name, search_name=search_name)
            session.add(new_account)
            await session.commit()
        await message.answer(f"Аккаунт '{escape(display_name)}' успешно добавлен.")
    except Exception as e:
        await message.answer(f"Произошла ошибка. Возможно, такое имя уже существует.\n\n{e}")
    finally:
        await state.clear()
        await message.answer("Управление аккаунтами площадок:", reply_markup=get_account_management_keyboard())
            
@router.callback_query(F.data == "list_accounts")
async def list_accounts_handler(callback: CallbackQuery):
    async with async_session() as session:
        stmt = (
            select(PlatformAccount, User.username)
            .outerjoin(AccountAssignment, PlatformAccount.id == AccountAssignment.account_id)
            .outerjoin(User, AccountAssignment.user_id == User.user_id)
        )
        results = (await session.execute(stmt)).all()

    if not results:
        await callback.answer("Еще не добавлено ни одного аккаунта.", show_alert=True)
        return

    accounts_map = {}
    for account, username in results:
        if account.id not in accounts_map:
            accounts_map[account.id] = {'account': account, 'users': []}
        if username:
            accounts_map[account.id]['users'].append(username)

    response_text = "<b>Список аккаунтов и ответственных:</b>\n\n"
    for item in accounts_map.values():
        acc = item['account']
        users_str = ", ".join(map(escape, item['users'])) or "<i>Не назначен</i>"
        response_text += f"🔹 <b>{escape(acc.display_name)}</b> (поиск по: <code>{escape(acc.search_name)}</code>)\n    Ответственные: {users_str}\n"

    await safe_edit_text(callback, response_text, get_account_management_keyboard())

@router.callback_query(F.data == "assign_account_user")
async def assign_account_user_start(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        accounts = (await session.execute(select(PlatformAccount))).scalars().all()
    if not accounts:
        await callback.answer("Сначала добавьте хотя бы один аккаунт.", show_alert=True)
        return
    
    keyboard = create_account_selection_keyboard(accounts, "assign_acc")
    await safe_edit_text(callback, "Выберите аккаунт, на который нужно назначить ответственного:", keyboard)
    await state.set_state(AccountManagementStates.select_account_to_assign)

@router.callback_query(AccountManagementStates.select_account_to_assign, F.data.startswith("assign_acc_"))
async def assign_account_select_user(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split("_")[-1])
    await state.update_data(account_id=account_id)
    
    async with async_session() as session:
        users = (await session.execute(select(User))).scalars().all()
    
    keyboard = create_user_selection_keyboard(users, "assign_user")
    await safe_edit_text(callback, "Теперь выберите пользователя, который будет отвечать за этот аккаунт:", keyboard)
    await state.set_state(AccountManagementStates.select_user_to_assign)

@router.callback_query(AccountManagementStates.select_user_to_assign, F.data.startswith("assign_user_"))
async def assign_account_process(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    account_id = data.get("account_id")

    try:
        async with async_session() as session:
            new_assignment = AccountAssignment(user_id=user_id, account_id=account_id)
            session.add(new_assignment)
            await session.commit()
        await callback.answer("Пользователь успешно назначен ответственным!", show_alert=True)
    except Exception:
        await callback.answer("Этот пользователь уже назначен на данный аккаунт.", show_alert=True)
    finally:
        await state.clear()
        await safe_edit_text(callback, "Управление аккаунтами площадок:", get_account_management_keyboard())

@router.callback_query(F.data == "delete_platform_account")
async def delete_platform_account_start(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        accounts = (await session.execute(select(PlatformAccount))).scalars().all()
    if not accounts:
        await callback.answer("Нет аккаунтов для удаления.", show_alert=True)
        return
    
    keyboard = create_account_selection_keyboard(accounts, "delete_acc")
    await safe_edit_text(callback, "Выберите аккаунт для удаления:", keyboard)
    await state.set_state(AccountManagementStates.select_account_to_delete)

@router.callback_query(AccountManagementStates.select_account_to_delete, F.data.startswith("delete_acc_"))
async def delete_platform_account_process(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split("_")[-1])
    
    async with async_session() as session:
        account_to_delete = await session.get(PlatformAccount, account_id)
        if account_to_delete:
            await session.delete(account_to_delete)
            await session.commit()
            await callback.answer(f"Аккаунт '{escape(account_to_delete.display_name)}' успешно удален.", show_alert=True)
        else:
            await callback.answer("Аккаунт не найден.", show_alert=True)
            
    await state.clear()
    await safe_edit_text(callback, "Управление аккаунтами площадок:", get_account_management_keyboard())

@router.callback_query(F.data == "remove_assignment")
async def remove_assignment_start(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        stmt = (
            select(AccountAssignment.id, PlatformAccount.display_name, User.username)
            .join(PlatformAccount, AccountAssignment.account_id == PlatformAccount.id)
            .join(User, AccountAssignment.user_id == User.user_id)
        )
        assignments = (await session.execute(stmt)).all()

    if not assignments:
        await callback.answer("Нет назначенных ответственных.", show_alert=True)
        return
        
    keyboard = create_assignment_selection_keyboard(assignments)
    await safe_edit_text(callback, "Выберите назначение для отмены:", keyboard)
    await state.set_state(AccountManagementStates.select_assignment_to_delete)

@router.callback_query(AccountManagementStates.select_assignment_to_delete, F.data.startswith("delete_assignment_"))
async def remove_assignment_process(callback: CallbackQuery, state: FSMContext):
    assignment_id = int(callback.data.split("_")[-1])
    
    async with async_session() as session:
        assignment_to_delete = await session.get(AccountAssignment, assignment_id)
        if assignment_to_delete:
            await session.delete(assignment_to_delete)
            await session.commit()
            await callback.answer("Назначение успешно отменено.", show_alert=True)
        else:
            await callback.answer("Назначение не найдено.", show_alert=True)

    await state.clear()
    await safe_edit_text(callback, "Управление аккаунтами площадок:", get_account_management_keyboard())

# --- КОНЕЦ БЛОКА --

# === НАЧАЛО БЛОКА: Логика редактирования ID платформы ===
@router.callback_query(F.data == "edit_platform_ids")
async def edit_platform_ids_start(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        products = (await session.execute(select(Product).order_by(Product.name))).scalars().all()
    if not products:
        await callback.answer("Сначала добавьте хотя бы один товар.", show_alert=True)
        return
    keyboard = create_product_selection_keyboard(products, prefix="edit_plat_id")
    await callback.message.edit_text("Выберите товар, для которого хотите изменить ID платформы:", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("edit_plat_id_"))
async def edit_platform_id_select_product(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split('_')[-1])
    async with async_session() as session:
        product = await session.get(Product, product_id)
    if not product:
        await callback.answer("Товар не найден.", show_alert=True)
        return
    await state.update_data(product_id_to_edit=product_id)
    await state.set_state(AdminStates.edit_platform_id)
    current_id_text = f"<code>{escape(product.platform_id)}</code>" if product.platform_id else "<i>не установлен</i>"
    await callback.message.edit_text(
        f"Редактирование ID для товара: <b>{escape(product.name)}</b>\n"
        f"Текущий ID: {current_id_text}\n\n"
        f"Введите новый ID платформы (или отправьте 'удалить', чтобы очистить его):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_edit_platform_id")]
        ])
    )

@router.message(AdminStates.edit_platform_id)
async def edit_platform_id_process(message: Message, state: FSMContext):
    new_id = message.text.strip()
    data = await state.get_data()
    product_id = data.get("product_id_to_edit")
    if new_id.lower() == 'удалить':
        new_id = None
        success_text = "ID успешно удален."
    else:
        success_text = f"ID <code>{escape(new_id)}</code> успешно присвоен."
    try:
        async with async_session() as session:
            await session.execute(
                update(Product).where(Product.id == product_id).values(platform_id=new_id)
            )
            await session.commit()
        await message.answer(success_text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"⚠️ **Ошибка!**\nПопробуйте ввести другой ID.\n\n`{e}`", parse_mode="HTML")
        return
    await state.clear()
    await edit_platform_ids_start(CallbackQuery(id='auto', from_user=message.from_user, chat_instance='auto', message=message), state)

@router.callback_query(F.data == "cancel_edit_platform_id")
async def cancel_edit_platform_id_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Редактирование отменено.")
    await edit_platform_ids_start(callback, state)
# === КОНЕЦ БЛОКА ===

@router.callback_query(F.data == "manage_categories")
async def manage_categories_menu(callback: CallbackQuery, state: FSMContext):
    """Показывает меню управления категориями."""
    await state.clear() # На всякий случай чистим состояние
    async with async_session() as session:
        categories = (await session.execute(select(Category).order_by(Category.name))).scalars().all()

    text = "🗂️ <b>Управление категориями</b>\n\nСуществующие категории:\n"
    if not categories:
        text += "<i>Пока не создано ни одной категории.</i>"
    else:
        text += "\n".join([f"• {escape(cat.name)}" for cat in categories])

    await callback.message.edit_text(text, reply_markup=get_category_management_keyboard(), parse_mode="HTML")
    await callback.answer()

# --- Добавление категории ---
@router.callback_query(F.data == "add_category")
async def add_category_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CategoryStates.add_category_name)
    # Используем edit_text, чтобы изменить текущее сообщение
    await callback.message.edit_text("Введите название новой категории:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="manage_categories")]]))
    await callback.answer()

@router.message(CategoryStates.add_category_name)
async def add_category_process(message: Message, state: FSMContext):
    category_name = message.text
    async with async_session() as session:
        exists = (await session.execute(select(Category).where(Category.name == category_name))).scalar_one_or_none()
        if exists:
            await message.answer("Категория с таким названием уже существует. Попробуйте другое.")
            # Сразу удалим предыдущее сообщение бота ("Введите название...")
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id - 1)
            return

        new_category = Category(name=category_name)
        session.add(new_category)
        await session.commit()

    await state.clear()
    # Имитируем нажатие на кнопку, чтобы вернуться в меню
    # Сначала удалим сообщение пользователя и предыдущее сообщение бота
    await message.delete()
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id - 1)
    except: pass # Если сообщение уже удалено, ничего страшного
    
    # Создаем фейковый колбэк, чтобы вызвать manage_categories_menu
    fake_callback = CallbackQuery(
        id=str(message.message_id),
        from_user=message.from_user,
        chat_instance=message.chat.id, # chat_instance - обязательный параметр
        message=message,
        data="manage_categories"
    )
    await manage_categories_menu(fake_callback, state)


# --- Переименование категории ---
@router.callback_query(F.data == "rename_category")
async def rename_category_start(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        categories = (await session.execute(select(Category).order_by(Category.name))).scalars().all()
    if not categories:
        await callback.answer("Нет категорий для переименования.", show_alert=True)
        return

    await state.set_state(CategoryStates.select_category_to_rename)
    await callback.message.edit_text(
        "Выберите категорию, которую хотите переименовать:",
        reply_markup=create_category_selection_keyboard(categories, "rename_cat")
    )

@router.callback_query(F.data.startswith("rename_cat_"), CategoryStates.select_category_to_rename)
async def rename_category_selected(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split("_")[-1])
    await state.update_data(category_id=category_id)
    await state.set_state(CategoryStates.enter_new_category_name)
    await callback.message.edit_text("Введите новое название для категории:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="manage_categories")]]))
    await callback.answer()

@router.message(CategoryStates.enter_new_category_name)
async def rename_category_process(message: Message, state: FSMContext):
    data = await state.get_data()
    category_id = data.get("category_id")
    new_name = message.text

    async with async_session() as session:
        await session.execute(update(Category).where(Category.id == category_id).values(name=new_name))
        await session.commit()

    await state.clear()
    await message.delete()
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id - 1)
    except: pass
    
    fake_callback = CallbackQuery(id=str(message.message_id), from_user=message.from_user, chat_instance=str(message.chat.id), message=message, data="manage_categories")
    await manage_categories_menu(fake_callback, state)


# --- Удаление категории ---
@router.callback_query(F.data == "delete_category")
async def delete_category_start(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        categories = (await session.execute(select(Category).order_by(Category.name))).scalars().all()
    if not categories:
        await callback.answer("Нет категорий для удаления.", show_alert=True)
        return

    await state.set_state(CategoryStates.select_category_to_delete)
    await callback.message.edit_text(
        "Выберите категорию для УДАЛЕНИЯ.\n\n"
        "<b>Внимание:</b> Товары, находящиеся в этой категории, не будут удалены. "
        "Они просто останутся без категории.",
        parse_mode="HTML",
        reply_markup=create_category_selection_keyboard(categories, "delete_cat")
    )

@router.callback_query(F.data.startswith("delete_cat_"), CategoryStates.select_category_to_delete)
async def delete_category_process(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split("_")[-1])
    async with async_session() as session:
        category_to_delete = await session.get(Category, category_id)
        if category_to_delete:
            # Сначала отвязываем товары, чтобы избежать проблем с 'lazy="joined"'
            await session.execute(
                update(Product).where(Product.category_id == category_id).values(category_id=None)
            )
            # Теперь удаляем саму категорию
            await session.delete(category_to_delete)
            await session.commit()
            await callback.answer(f"Категория «{escape(category_to_delete.name)}» удалена.", show_alert=True)
        else:
            await callback.answer("Категория не найдена.", show_alert=True)

    await state.clear()
    await manage_categories_menu(callback)
