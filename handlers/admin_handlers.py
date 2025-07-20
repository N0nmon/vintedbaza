from datetime import datetime, timedelta
from html import escape

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile
from sqlalchemy import select, delete, func, update
from sqlalchemy.orm import joinedload

from db.database import async_session
from db.models import User, Product, Stock, Sale, UserProductAccess
from config import settings
from keyboards.admin_keyboards import (
    get_admin_panel_keyboard, get_sales_management_keyboard,
    create_access_management_keyboard, get_user_management_keyboard,
    create_user_selection_keyboard
)
from keyboards.common_keyboards import get_cancel_kb, remove_kb
from states.admin_states import AdminStates, AddProductStates

router = Router()
router.message.filter(F.from_user.id == settings.admin_id)
router.callback_query.filter(F.from_user.id == settings.admin_id)

# --- Универсальные обработчики отмены и возврата ---
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

# --- Главное меню админки ---
@router.message(Command("admin"))
async def show_admin_panel(message: Message):
    await message.answer("Админ-панель:", reply_markup=get_admin_panel_keyboard())

# --- Отмена продажи (возврат) ---
@router.callback_query(F.data == "process_return")
async def process_return_start(callback: CallbackQuery, state: FSMContext):
    async with async_session() as session:
        stmt = (
            select(Sale)
            .options(joinedload(Sale.stock_item).joinedload(Stock.product))
            .order_by(Sale.sale_date.desc())
        )
        result = await session.execute(stmt)
        all_sales = result.scalars().all()

    if not all_sales:
        await callback.answer("Еще не было ни одной продажи.", show_alert=True)
        return

    sales_list_text = "Все зарегистрированные продажи:\n\n"
    for sale in all_sales:
        product_name = escape(sale.stock_item.product.name)
        product_size = escape(sale.stock_item.size)
        sales_list_text += (
            f"🔹 <b>№{sale.id}</b> | {sale.sale_date.strftime('%d.%m.%Y')} | "
            f"{product_name} ({product_size})\n"
        )
    
    await callback.message.answer(sales_list_text, parse_mode="HTML")
    await callback.message.answer("Введите номер продажи для отмены (товар вернется на склад):", reply_markup=get_cancel_kb())
    await state.set_state(AdminStates.return_sale_id)
    await callback.answer()

@router.message(AdminStates.return_sale_id)
async def process_return_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Номер продажи должен быть числом. Попробуйте еще раз.")
        return
    
    sale_id = int(message.text)
    
    async with async_session() as session:
        sale_to_return = await session.get(Sale, sale_id)
        if not sale_to_return:
            await message.answer(f"Продажа с номером {sale_id} не найдена.", reply_markup=remove_kb())
            await state.clear()
            await show_admin_panel(message)
            return
            
        stock_id = sale_to_return.stock_id
        await session.execute(update(Stock).where(Stock.id == stock_id).values(is_available=True))
        await session.delete(sale_to_return)
        await session.commit()

    await message.answer(f"Продажа №{sale_id} успешно отменена. Товар возвращен на склад.", reply_markup=remove_kb())
    await state.clear()
    await show_admin_panel(message)

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
    keyboard = create_user_selection_keyboard(users)
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
        access_entry = await session.execute(select(UserProductAccess).where(UserProductAccess.user_id == user_id, UserProductAccess.product_id == product_id)).scalar_one_or_none()
        if access_entry:
            await session.delete(access_entry)
        else:
            session.add(UserProductAccess(user_id=user_id, product_id=product_id))
        await session.commit()
        all_products = (await session.execute(select(Product))).scalars().all()
        user_access_result = await session.execute(select(UserProductAccess.product_id).where(UserProductAccess.user_id == user_id))
        user_product_ids = set(user_access_result.scalars().all())
        keyboard = create_access_management_keyboard(user_id, all_products, user_product_ids)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()

# --- Управление товарами ---
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
    data = await state.get_data()
    try:
        async with async_session() as session:
            new_product = Product(name=data.get('name'), photo_id=data.get('photo_id'))
            session.add(new_product)
            await session.flush()
            for size in sizes_list:
                session.add(Stock(product_id=new_product.id, size=size))
            await session.commit()
        await message.answer(f"Товар '{escape(data.get('name'))}' успешно добавлен.", reply_markup=remove_kb())
    except Exception as e:
        await message.answer(f"Произошла ошибка: {e}", reply_markup=remove_kb())
    finally:
        await state.clear()
        await show_admin_panel(message)

# --- Отчеты и управление продажами ---
@router.callback_query(F.data == "sales_management")
async def handle_sales_management(callback: CallbackQuery):
    await callback.message.edit_text("Отчеты и Продажи:", reply_markup=get_sales_management_keyboard())

@router.callback_query(F.data == "report_summary")
async def handle_report_summary(callback: CallbackQuery):
    async with async_session() as session:
        stmt = select(func.count(Sale.id), func.sum(Sale.price))
        result = await session.execute(stmt)
        total_sales, total_revenue = result.one()
    response_text = "Общая статистика:\n\n"
    response_text += f"Всего продаж: <b>{total_sales or 0}</b>\n"
    response_text += f"Общая сумма продаж: <b>{total_revenue or 0:.2f}</b>"
    await callback.message.answer(response_text, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "report_last_10")
async def handle_report_last_10(callback: CallbackQuery):
    async with async_session() as session:
        stmt = (
            select(Sale)
            .options(joinedload(Sale.stock_item).joinedload(Stock.product), joinedload(Sale.seller))
            .order_by(Sale.sale_date.desc()).limit(10)
        )
        result = await session.execute(stmt)
        last_sales = result.scalars().all()
    if not last_sales:
        await callback.message.answer("Еще не было ни одной продажи.")
        return
    await callback.message.answer("Последние 10 продаж:")
    for sale in last_sales:
        status = "✅ Подтверждена" if sale.is_confirmed else "❌ Не подтверждена"
        seller_name = escape(sale.seller.username or f"ID: {sale.seller.user_id}")
        product_name = escape(sale.stock_item.product.name)
        product_size = escape(sale.stock_item.size)
        label_link = escape(sale.label_link)
        
        response_text = (
            f"<b>Продажа №{sale.id}</b> от {sale.sale_date.strftime('%d.%m.%Y %H:%M')} | <b>{status}</b>\n"
            f"Товар: {product_name} (размер: {product_size})\n"
            f"Продавец: {seller_name}\n"
            f"Цена: {sale.price:.2f}\n"
            f"Ссылка на этикетку: {label_link}"
        )
        try:
            screenshot = FSInputFile(sale.screenshot_path)
            await callback.message.answer_photo(photo=screenshot, caption=response_text, parse_mode="HTML")
        except Exception as e:
            await callback.message.answer(f"{response_text}\n\n(Не удалось загрузить скриншот: {escape(str(e))})", parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "delete_sale_start")
async def delete_sale_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите номер продажи для удаления (это действие не вернет товар на склад):", reply_markup=get_cancel_kb())
    await state.set_state(AdminStates.delete_sale_id)
    await callback.answer()

@router.message(AdminStates.delete_sale_id)
async def delete_sale_process(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Номер продажи должен быть числом. Попробуйте еще раз.")
        return
    sale_id = int(message.text)
    async with async_session() as session:
        sale_to_delete = await session.get(Sale, sale_id)
        if sale_to_delete:
            await session.delete(sale_to_delete)
            await session.commit()
            await message.answer(f"Продажа №{sale_id} успешно удалена.", reply_markup=remove_kb())
        else:
            await message.answer(f"Продажа с номером {sale_id} не найдена.", reply_markup=remove_kb())
    await state.clear()
    await show_admin_panel(message)
