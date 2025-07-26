import os
from html import escape

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select, func, update
from sqlalchemy.orm import joinedload

from config import settings
from db.database import async_session
from db.models import Product, Stock, Sale, User, UserProductAccess
from keyboards.common_keyboards import (
    get_main_menu_keyboard, create_products_keyboard, 
    create_sizes_keyboard, get_cancel_kb, remove_kb,
    get_my_sales_keyboard, create_confirmation_keyboard,
    get_summary_menu_keyboard,
    create_label_sizes_keyboard
)
from states.user_states import SaleStates
from utils.notifications import send_sale_notification
from utils.postgres_connector import fetch_all_products_from_postgres, fetch_product_tasks_from_postgres
from html import escape
from collections import defaultdict


router = Router()

# --- Универсальный обработчик отмены для этого роутера ---
@router.message(F.text == "⬅️ Отмена", StateFilter(SaleStates))
@router.message(Command("cancel"), StateFilter(SaleStates))
async def cancel_fsm_handler_user(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=get_main_menu_keyboard())

@router.callback_query(F.data == "cancel_action", StateFilter("*"))
async def cancel_inline_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.answer("Действие отменено.")

# --- Основные команды ---
async def get_allowed_products(session, user: User) -> list:
    if user.is_admin:
        stmt = select(Product)
    else:
        stmt = select(Product).join(UserProductAccess).where(UserProductAccess.user_id == user.user_id)
    result = await session.execute(stmt)
    return result.scalars().all()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("Привет! Я бот для учета обуви.", reply_markup=get_main_menu_keyboard())

@router.message(F.text == "Сводка 📈")
async def show_summary_menu(message: Message):
    """
    Показывает меню выбора типа сводки.
    """
    await message.answer("Выберите тип сводки:", reply_markup=get_summary_menu_keyboard())

@router.message(F.text == "Просмотреть остатки 📦")
@router.message(Command("stock"))
async def cmd_stock(message: Message, user: User):
    async with async_session() as session:
        products = await get_allowed_products(session, user)
    if not products:
        await message.answer("Для вас нет доступных товаров.")
        return
    keyboard = create_products_keyboard(products, action="stock")
    await message.answer("Выберите товар для просмотра остатков:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("stock_"))
async def show_product_stock(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    async with async_session() as session:
        product = await session.get(Product, product_id)
        if not product:
            await callback.answer("Товар не найден!", show_alert=True)
            return
        stmt = (
            select(Stock.size, func.count(Stock.id).label('count'))
            .where(Stock.product_id == product_id, Stock.is_available == True)
            .group_by(Stock.size).order_by(Stock.size)
        )
        result = await session.execute(stmt)
        sizes_stock = result.all()

    product_name = escape(product.name)
    if not sizes_stock:
        response_text = f"<b>{product_name}</b>\n\nВсе размеры проданы."
    else:
        sizes_info = "\n".join([f"Размер: {escape(size)} - {count} шт." for size, count in sizes_stock])
        response_text = f"<b>{product_name}</b>\n\n<b>Остатки по размерам:</b>\n{sizes_info}"
    
    try:
        await callback.message.answer_photo(photo=product.photo_id, caption=response_text, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "wrong file identifier" in e.message:
            await callback.message.answer(
                f"{response_text}\n\n<i>(Не удалось загрузить фото товара)</i>",
                parse_mode="HTML"
            )
        else:
            raise e
            
    await callback.answer()

# --- Просмотр и подтверждение своих продаж ---
@router.message(F.text == "Мои продажи 📋")
async def my_sales_handler(message: Message):
    async with async_session() as session:
        stmt = (
            select(Sale)
            .options(joinedload(Sale.stock_item).joinedload(Stock.product))
            .where(Sale.seller_id == message.from_user.id)
            .order_by(Sale.sale_date.desc())
        )
        result = await session.execute(stmt)
        user_sales = result.scalars().all()

    if not user_sales:
        await message.answer("У вас еще нет зарегистрированных продаж.")
        return

    response_text = "Ваши продажи:\n\n"
    for sale in user_sales:
        status = "✅ Подтверждена" if sale.is_confirmed else "❌ Требуется подтверждение"
        product_name = escape(sale.stock_item.product.name)
        product_size = escape(sale.stock_item.size)
        account = escape(sale.account or 'Не указан')
        response_text += (
            f"🔹 <b>№{sale.id}</b> | {sale.sale_date.strftime('%d.%m.%Y')} | "
            f"{product_name} ({product_size})\n"
            f"<b>Аккаунт:</b> {account} | <b>Статус:</b> {status}\n\n"
        )
    
    await message.answer(response_text, parse_mode="HTML", reply_markup=get_my_sales_keyboard())

@router.callback_query(F.data == "confirm_sale_menu")
async def confirm_sale_menu_handler(callback: CallbackQuery):
    async with async_session() as session:
        stmt = (
            select(Sale)
            .options(joinedload(Sale.stock_item).joinedload(Stock.product))
            .where(Sale.seller_id == callback.from_user.id, Sale.is_confirmed == False)
            .order_by(Sale.sale_date.asc())
        )
        result = await session.execute(stmt)
        unconfirmed_sales = result.scalars().all()
    
    if not unconfirmed_sales:
        await callback.answer("У вас нет продаж, требующих подтверждения.", show_alert=True)
        return

    keyboard = create_confirmation_keyboard(unconfirmed_sales)
    await callback.message.edit_text("Выберите продажу для подтверждения:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("confirm_sale_"))
async def confirm_sale_action_handler(callback: CallbackQuery):
    sale_id = int(callback.data.split("_")[-1])
    
    async with async_session() as session:
        stmt = update(Sale).where(Sale.id == sale_id, Sale.seller_id == callback.from_user.id).values(is_confirmed=True)
        await session.execute(stmt)
        await session.commit()
    
    await callback.answer("Продажа подтверждена!", show_alert=True)
    await callback.message.delete()


# --- FSM для регистрации продажи ---
@router.message(F.text == "Зарегистрировать продажу 💸")
async def start_sale(message: Message, state: FSMContext, user: User):
    async with async_session() as session:
        products = await get_allowed_products(session, user)
    if not products:
        await message.answer("Нечего продавать. Для вас нет доступных товаров.")
        return
    keyboard = create_products_keyboard(products, action="sale")
    await message.answer("Выберите товар, который был продан:", reply_markup=keyboard)
    await state.set_state(SaleStates.select_product)

@router.callback_query(F.data.regexp(r"^sale_\d+$"), StateFilter(SaleStates.select_product))
async def select_sale_product(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[1])
    await state.update_data(product_id=product_id)
    async with async_session() as session:
        stmt = (
            select(Stock.size, func.count(Stock.id).label('count'))
            .where(Stock.product_id == product_id, Stock.is_available == True)
            .group_by(Stock.size).order_by(Stock.size)
        )
        result = await session.execute(stmt)
        sizes_stock = result.all()
    if not sizes_stock:
        await callback.message.edit_text("У этого товара нет доступных размеров.")
        await state.clear()
        return
    keyboard = create_sizes_keyboard(sizes_stock, product_id)
    await callback.message.edit_text("Выберите проданный размер:", reply_markup=keyboard)
    await state.set_state(SaleStates.select_size)

@router.callback_query(F.data.startswith("sale_size_"), StateFilter(SaleStates.select_size))
async def select_sale_size(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    size = parts[3]
    await state.update_data(size=size)
    await callback.message.delete()
    await callback.message.answer(f"Выбран размер {size}. Введите цену продажи (в zł):", reply_markup=get_cancel_kb())
    await state.set_state(SaleStates.price)

@router.message(StateFilter(SaleStates.price))
async def enter_sale_price(message: Message, state: FSMContext):
    if not message.text.replace('.', '', 1).isdigit():
        await message.answer("Цена должна быть числом. Попробуйте еще раз.")
        return
    await state.update_data(price=float(message.text))
    await message.answer("Введите аккаунт, на котором произошла продажа:")
    await state.set_state(SaleStates.account)

@router.message(StateFilter(SaleStates.account))
async def enter_sale_account(message: Message, state: FSMContext):
    await state.update_data(account=message.text)
    await message.answer("Отправьте ссылку на этикетку:")
    await state.set_state(SaleStates.label_link)

@router.message(StateFilter(SaleStates.label_link))
async def enter_label_link(message: Message, state: FSMContext):
    await state.update_data(label_link=message.text)
    await message.answer("Отправьте скриншот подтверждения:")
    await state.set_state(SaleStates.screenshot)

@router.message(StateFilter(SaleStates.screenshot), F.photo)
async def enter_screenshot(message: Message, state: FSMContext, bot: Bot):
    await message.answer("Сохраняю продажу...", reply_markup=remove_kb())
    data = await state.get_data()
    product_id = data.get('product_id')
    size = data.get('size')
    label_link = data.get('label_link')
    account = data.get('account')
    try:
        async with async_session() as session:
            stmt_select = select(Stock.id).where(
                Stock.product_id == product_id,
                Stock.size == size,
                Stock.is_available == True
            ).limit(1)
            stock_id_result = await session.execute(stmt_select)
            stock_id = stock_id_result.scalar_one_or_none()
            if not stock_id:
                await message.answer("Ошибка: не найдена доступная пара этого размера.", reply_markup=get_main_menu_keyboard())
                await state.clear()
                return
            await session.execute(update(Stock).where(Stock.id == stock_id).values(is_available=False))
            new_sale = Sale(
                stock_id=stock_id,
                seller_id=message.from_user.id,
                price=data.get('price'),
                account=account,
                label_link=label_link
            )
            session.add(new_sale)
            await session.flush()
            order_number = new_sale.id
            screenshot_file = await bot.get_file(message.photo[-1].file_id)
            screenshot_path = os.path.join('media', f"sale_{order_number}.jpg")
            await bot.download_file(screenshot_file.file_path, screenshot_path)
            new_sale.screenshot_path = screenshot_path
            sold_product = await session.get(Product, product_id)
            await session.commit()
            await message.answer(f"Продажа №{order_number} успешно зарегистрирована!", reply_markup=get_main_menu_keyboard())
            
            if settings.forwarding_group_id:
                try:
                    await bot.send_message(chat_id=settings.forwarding_group_id, text=label_link)
                    screenshot = FSInputFile(screenshot_path)
                    await bot.send_photo(chat_id=settings.forwarding_group_id, photo=screenshot)
                except Exception as e:
                    await message.answer(f"Не удалось переслать данные в группу. Ошибка: {e}")
            
            await send_sale_notification(bot, sold_product, size)

    except Exception as e:
        await message.answer(f"Произошла критическая ошибка при сохранении продажи: {e}", reply_markup=get_main_menu_keyboard())
    finally:
        await state.clear()
        
# --- Логика получения этикеток ---

@router.message(F.text == "Получить этикетку 🏷️")
async def get_label_start(message: Message, user: User):
    print(f"[DEBUG] Пользователь {user.user_id} запросил получение этикетки.")
    async with async_session() as session:
        products = await get_allowed_products(session, user)
        print(f"[DEBUG] Доступные товары для пользователя {user.user_id}: {products}")
    
    if not products:
        print(f"[DEBUG] Для пользователя {user.user_id} нет доступных товаров.")
        await message.answer("Для вас нет доступных товаров.")
        return
    
    keyboard = create_products_keyboard(products, action="label_product")
    print(f"[DEBUG] Клавиатура для выбора товаров создана: {keyboard}")
    await message.answer("Выберите товар, для которого нужна этикетка:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("label_product_"))
async def get_label_select_product(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[-1])
    print(f"[DEBUG] Пользователь выбрал товар с ID: {product_id}")
    labels_dir = f"labels/{product_id}"
    print(f"[DEBUG] Директория для этикеток: {labels_dir}")
    
    available_sizes = []
    if os.path.exists(labels_dir):
        print(f"[DEBUG] Директория {labels_dir} существует. Сканируем файлы...")
        for filename in os.listdir(labels_dir):
            size = os.path.splitext(filename)[0]
            if size.replace('.', '', 1).isdigit():
                available_sizes.append(size)
                print(f"[DEBUG] Найден доступный размер: {size}")
    else:
        print(f"[DEBUG] Директория {labels_dir} не существует.")

    if not available_sizes:
        print(f"[DEBUG] Для товара {product_id} нет доступных этикеток.")
        await callback.answer("Для этого товара еще не загружены этикетки.", show_alert=True)
        return

    keyboard = create_label_sizes_keyboard(available_sizes, product_id)
    print(f"[DEBUG] Клавиатура для выбора размеров создана: {keyboard}")
    await callback.message.edit_text("Выберите размер:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("get_label_"))
async def get_label_send_file(callback: CallbackQuery):
    parts = callback.data.split("_")
    product_id = int(parts[2])
    size = parts[3]
    labels_dir = f"labels/{product_id}"
    # print(f"[DEBUG] Пользователь запросил этикетку для товара {product_id}, размер {size}.")
    # print(f"[DEBUG] Директория для поиска этикетки: {labels_dir}")

    label_path = None
    valid_extensions = ['.jpg', '.jpeg', '.png', '.pdf']  # Список допустимых расширений

    if os.path.exists(labels_dir):
        # print(f"[DEBUG] Директория {labels_dir} существует. Сканируем файлы...")
        for filename in os.listdir(labels_dir):
            file_ext = os.path.splitext(filename)[1].lower()  # Приводим расширение к нижнему регистру
            if filename.startswith(size) and file_ext in valid_extensions:
                label_path = os.path.join(labels_dir, filename)
                # print(f"[DEBUG] Файл найден: {label_path}")
                break
    else:
        # print(f"[DEBUG] Директория {labels_dir} не существует.")
        pass

    if label_path:
        # print(f"[DEBUG] Отправляем файл этикетки: {label_path}")
        await callback.message.answer_document(FSInputFile(label_path))
        await callback.answer()
    else:
        # print(f"[DEBUG] Файл этикетки для товара {product_id}, размер {size} не найден.")
        await callback.answer("Файл этикетки для этого размера не найден.", show_alert=True)
    
    await callback.message.delete()

# в конец файла handlers/common_handlers.py

@router.callback_query(F.data == "summary_tasks")
async def cmd_tasks_summary(callback: CallbackQuery, user: User):
    await callback.message.edit_text("🔍 Запрашиваю данные из PostgreSQL...")

    try:
        # 1. Получаем ВСЕ строки из PostgreSQL
        pg_products = await fetch_all_products_from_postgres()

        if not pg_products:
            # Используем edit_text, чтобы обновить сообщение "Запрашиваю данные..."
            await callback.message.edit_text("Таблица в PostgreSQL пуста.")
            return

        # 2. Получаем все наши товары для сопоставления ID
        async with async_session() as session:
            bot_products = (await session.execute(select(Product))).scalars().all()
            platform_id_to_name_map = {p.platform_id: p.name for p in bot_products if p.platform_id}

        # 3. Группируем строки по user_id из PostgreSQL
        products_by_user = {}
        for prod in pg_products:
            user_id = prod['user_id']
            if user_id not in products_by_user:
                products_by_user[user_id] = []
            products_by_user[user_id].append(prod)

        # 4. Формируем и отправляем отчет с "умным" разделением
        TELEGRAM_MESSAGE_LIMIT = 4096
        message_part = "<b>Полная сводка по таблице:</b>\n\n"
        
        # --- ИСПРАВЛЕНИЕ ЛОГИКИ ОТПРАВКИ ---
        
        # Сначала отправим первое сообщение как редактирование исходного
        is_first_part_sent = False

        for pg_user_id, user_products in products_by_user.items():
            user_block = f"👤 <b>Пользователь <code>{pg_user_id}</code>:</b>\n"
            for prod in user_products:
                platform_id = prod['is_active']
                product_name = platform_id_to_name_map.get(platform_id, f"Неизвестный товар ({platform_id})")
                size = prod['size']
                task_id = prod['id']
                user_block += f"  • {escape(product_name)} (размер: {size}) - <b>ID:</b> <code>{task_id}</code>\n"
            user_block += "\n"

            if len(message_part) + len(user_block) > TELEGRAM_MESSAGE_LIMIT:
                # Если это первая отправляемая часть, редактируем сообщение.
                if not is_first_part_sent:
                    await callback.message.edit_text(message_part, parse_mode="HTML")
                    is_first_part_sent = True
                # Все последующие части - отправляем как новые сообщения.
                else:
                    await callback.message.answer(message_part, parse_mode="HTML")
                
                message_part = user_block
            else:
                message_part += user_block

        # Отправляем последнюю оставшуюся часть
        if message_part and message_part != "<b>Полная сводка по таблице:</b>\n\n":
            if not is_first_part_sent:
                await callback.message.edit_text(message_part, parse_mode="HTML")
            else:
                await callback.message.answer(message_part, parse_mode="HTML")

    except Exception as e:
        await callback.message.answer(f"❌ Произошла ошибка при получении данных: {e}")

@router.callback_query(F.data == "summary_by_product")
async def summary_by_product_start(callback: CallbackQuery, user: User):
    """
    Этот обработчик запускает процесс, предлагая пользователю выбрать товар.
    """
    async with async_session() as session:
        products = await get_allowed_products(session, user)
    
    # --- НАЧАЛО ИСПРАВЛЕНИЯ ---
    if not products:
        # Заменяем message.answer на callback.answer
        await callback.answer("Для вас нет доступных товаров.", show_alert=True)
        return
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
    
    # Используем существующую функцию для создания клавиатуры, но с новым префиксом
    keyboard = create_products_keyboard(products, action="summary_product")
    
    # И здесь тоже используем callback.message.edit_text вместо .answer, чтобы изменить текущее сообщение
    await callback.message.edit_text("Выберите товар для анализа:", reply_markup=keyboard)
    await callback.answer() # Ответ на колбэк, чтобы "часики" на кнопке пропали

@router.callback_query(F.data.startswith("summary_product_"))
async def summary_by_product_process(callback: CallbackQuery):
    """
    Основной обработчик, который собирает, анализирует и выводит данные.
    """
    product_id = int(callback.data.split("_")[2])
    await callback.message.edit_text("⚙️ Собираю и анализирую данные...")

    # 1. Получаем информацию о товаре и его остатках из базы бота
    async with async_session() as session:
        product = await session.get(Product, product_id)
        if not product:
            await callback.message.edit_text("Ошибка: Товар не найден.")
            return

        # Проверяем, есть ли у товара ID для связи
        if not product.platform_id:
            await callback.message.edit_text(
                f"<b>Ошибка:</b> Для товара «{escape(product.name)}» не установлен ID платформы.\n\n"
                f"Администратор должен установить его в меню «Управление товарами» -> «Редактировать ID платформ».",
                parse_mode="HTML"
            )
            return
        
        # Запрос остатков
        stock_result = await session.execute(
            select(Stock.size, func.count(Stock.id))
            .where(Stock.product_id == product_id, Stock.is_available == True)
            .group_by(Stock.size)
        )
        # Словарь вида {'42': 3, '43': 1}
        stock_counts = dict(stock_result.all())

    # 2. Получаем задачи из PostgreSQL для этого товара
    pg_tasks = await fetch_product_tasks_from_postgres(product.platform_id)
    
    # Группируем задачи по размерам для удобства, вида {'42': [ {'user_id': 1, 'id': 10}... ]}
    tasks_by_size = {}
    for task in pg_tasks:
        size = task['size']
        if size not in tasks_by_size:
            tasks_by_size[size] = []
        tasks_by_size[size].append(task)
    
    # 3. Формируем отчет
    report_text = f"<b>Анализ по товару: {escape(product.name)}</b>\n\n"
    
    # --- Часть 1: Распределенные задачи ---
    report_text += "📊 <b>Распределенные задачи (из PostgreSQL):</b>\n"
    if not tasks_by_size:
        report_text += "  <em>Задачи для этого товара не найдены.</em>\n"
    else:
        sorted_task_sizes = sorted(tasks_by_size.keys(), key=float)
        for size in sorted_task_sizes:
            tasks = tasks_by_size[size]
            assignees = ", ".join([f"пользователю <code>{t['user_id']}</code> (ID: <code>{t['id']}</code>)" for t in tasks])
            report_text += f"  • <b>Размер {size}</b> ({len(tasks)} шт.): назначен(а) {assignees}\n"
    
    # --- Часть 2: Свободные остатки ---
    report_text += "\n📦 <b>Свободные остатки на складе (в боте):</b>\n"
    
    unassigned_stock = {size: count for size, count in stock_counts.items() if size not in tasks_by_size}
    
    if not unassigned_stock:
         report_text += "  <em>Все остатки распределены по задачам.</em>\n"
    else:
        sorted_stock_sizes = sorted(unassigned_stock.keys(), key=float)
        for size in sorted_stock_sizes:
            count = unassigned_stock[size]
            report_text += f"  ⚠️ <b>Размер {size}:</b> {count} шт. (не выставлено)\n"

    # --- Часть 3: Потенциальные проблемы ---
    problem_sizes = [size for size in tasks_by_size if size not in stock_counts]
    if problem_sizes:
        report_text += "\n❗️ <b>Возможные проблемы:</b>\n"
        for size in problem_sizes:
             report_text += f"  • <b>Размер {size}:</b> числится в задачах, но отсутствует на складе!\n"

    await callback.message.edit_text(report_text, parse_mode="HTML")

@router.callback_query(F.data == "summary_find_problems")
async def find_all_problems(callback: CallbackQuery):
    """
    Проводит полный аудит системы по трем направлениям:
    1. Невыставленные остатки (есть на складе, нет в задачах).
    2. "Призрачные" задачи (есть в задачах, нет на складе).
    3. Товары без ID платформы.
    """
    await callback.message.edit_text("🔍 Провожу полный аудит системы. Это может занять некоторое время...")

    # 1. Получаем все необходимые данные
    all_pg_tasks = await fetch_all_products_from_postgres()
    
    async with async_session() as session:
        all_bot_products = (await session.execute(select(Product))).scalars().all()
        stock_results = (await session.execute(
            select(Stock.product_id, Stock.size, func.count(Stock.id))
            .where(Stock.is_available == True)
            .group_by(Stock.product_id, Stock.size)
        )).all()

    # 2. Структурируем данные для удобного анализа
    product_map_by_platform_id = {p.platform_id: p for p in all_bot_products if p.platform_id}

    # Считаем остатки: {product_id: {size: count}}
    stock_counts = defaultdict(lambda: defaultdict(int))
    for product_id, size, count in stock_results:
        stock_counts[product_id][size] += count
        
    # Считаем задачи: {platform_id: {size: count}}
    tasks_counts = defaultdict(lambda: defaultdict(int))
    for task in all_pg_tasks:
        tasks_counts[task['is_active']][task['size']] += 1

    # 3. Начинаем анализ и формируем отчеты
    unlisted_stock_report = ""
    tasks_without_stock_report = ""
    products_without_id_report = ""

    # Проходим по всем товарам в нашей базе бота
    for product in all_bot_products:
        # Проблема 3: У товара нет ID
        if not product.platform_id:
            products_without_id_report += f"  - {escape(product.name)}\n"
            continue

        product_stock = stock_counts.get(product.id, {})
        product_tasks = tasks_counts.get(product.platform_id, {})
        
        # Объединяем все уникальные размеры для этого товара из обоих источников
        all_sizes_for_product = set(product_stock.keys()) | set(product_tasks.keys())

        temp_unlisted = ""
        temp_tasks_without_stock = ""

        for size in sorted(all_sizes_for_product, key=float):
            stock_count = product_stock.get(size, 0)
            task_count = product_tasks.get(size, 0)

            # Проблема 1: Есть на складе, но нет в задачах
            if stock_count > 0 and task_count == 0:
                temp_unlisted += f"  - <b>Размер {size}:</b> {stock_count} шт. лежит на складе без дела.\n"
            
            # Проблема 2: Есть в задачах, но нет на складе
            elif task_count > 0 and stock_count == 0:
                temp_tasks_without_stock += f"  - <b>Размер {size}:</b> числится в {task_count} задаче(ах), но отсутствует на складе!\n"

        if temp_unlisted:
            unlisted_stock_report += f"\n<b>Товар: «{escape(product.name)}»</b>\n{temp_unlisted}"
        
        if temp_tasks_without_stock:
            tasks_without_stock_report += f"\n<b>Товар: «{escape(product.name)}»</b>\n{temp_tasks_without_stock}"
            
    # 4. Формируем финальное сообщение
    final_text = "<b>Результаты полного аудита системы:</b>\n"
    has_problems = False

    if unlisted_stock_report:
        has_problems = True
        final_text += "\n📦 <b>Невыставленные остатки (есть на складе, но нет задач):</b>"
        final_text += unlisted_stock_report
        final_text += "\n---"

    if tasks_without_stock_report:
        has_problems = True
        final_text += "\n❗️ <b>Задачи, для которых НЕТ остатков на складе:</b>"
        final_text += tasks_without_stock_report
        final_text += "\n---"
        
    if products_without_id_report:
        has_problems = True
        final_text += "\n🔑 <b>Товары без ID платформы:</b>\n"
        final_text += products_without_id_report
        final_text += "<em>Эти товары не могут быть проверены.</em>"
        
    if not has_problems:
        final_text += "\n✅ Проблем и расхождений не найдено. Отличная работа!"

    await callback.message.edit_text(final_text, parse_mode="HTML")