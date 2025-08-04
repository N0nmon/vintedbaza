from html import escape
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db.models import Product, User, Sale, PlatformAccount, Category

def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Журнал Продаж 📔", callback_data="sales_journal_reset")],
        [InlineKeyboardButton(text="Отчеты и Аналитика 📈", callback_data="reports_panel")],
        [InlineKeyboardButton(text="Управление товарами 📦", callback_data="manage_products")],
        [InlineKeyboardButton(text="Управление пользователями 👥", callback_data="manage_users")],
        [InlineKeyboardButton(text="Управление доступом 🔑", callback_data="manage_access")],
        [InlineKeyboardButton(text="Управление Аккаунтами 📧", callback_data="manage_accounts")],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def get_reports_panel_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Финансовая сводка", callback_data="finance_summary_panel")],
        [InlineKeyboardButton(text="Отчет по продавцам", callback_data="seller_report_start")],
        [InlineKeyboardButton(text="Экспорт продаж в CSV", callback_data="export_csv_start")],
        [InlineKeyboardButton(text="⬅️ Назад в админ-панель", callback_data="back_to_admin_panel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_finance_summary_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="За сегодня", callback_data="finance_period_today"),
            InlineKeyboardButton(text="За неделю", callback_data="finance_period_week"),
        ],
        [
            InlineKeyboardButton(text="За месяц", callback_data="finance_period_month"),
            InlineKeyboardButton(text="За все время", callback_data="finance_period_all"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад к отчетам", callback_data="reports_panel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_sales_journal_keyboard(sales: list[Sale], page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    for sale in sales:
        status_icon = "✅" if sale.is_confirmed else "❌"
        product_name = escape(sale.stock_item.product.name)
        product_size = escape(sale.stock_item.size)
        account = escape(sale.account or "??")
        text = f"№{sale.id} | {sale.sale_date.strftime('%d.%m')} | {product_name} ({product_size}) | {account} | {status_icon}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"view_sale_{sale.id}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"journal_page_{page-1}"))
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"journal_page_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
        
    buttons.append([InlineKeyboardButton(text="Фильтр 🔍", callback_data="journal_filter")])
    buttons.append([InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="back_to_admin_panel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def get_journal_filter_keyboard(current_filters: dict) -> InlineKeyboardMarkup:
    period_icon = "✅" if current_filters.get('start_date') else ""
    seller_icon = "✅" if current_filters.get('seller_id') else ""
    product_icon = "✅" if current_filters.get('product_id') else ""
    account_icon = "✅" if current_filters.get('account') else ""
    status_icon = "✅" if 'is_confirmed' in current_filters else ""

    buttons = [
        [InlineKeyboardButton(text=f"{period_icon} По периоду", callback_data="filter_period")],
        [InlineKeyboardButton(text=f"{seller_icon} По продавцу", callback_data="filter_seller")],
        [InlineKeyboardButton(text=f"{product_icon} По товару", callback_data="filter_product")],
        [InlineKeyboardButton(text=f"{account_icon} По аккаунту", callback_data="filter_account")],
        [InlineKeyboardButton(text=f"{status_icon} По статусу", callback_data="filter_status")],
        [InlineKeyboardButton(text="Сбросить все фильтры", callback_data="filter_reset")],
        [InlineKeyboardButton(text="⬅️ Показать результат", callback_data="sales_journal")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_sale_details_keyboard(sale: Sale) -> InlineKeyboardMarkup:
    buttons = []
    if not sale.is_confirmed:
        buttons.append([InlineKeyboardButton(text="✅ Подтвердить продажу", callback_data=f"admin_confirm_sale_{sale.id}")])
    
    buttons.append([InlineKeyboardButton(text="↩️ Отменить (вернуть на склад)", callback_data=f"admin_return_sale_{sale.id}")])
    buttons.append([InlineKeyboardButton(text="🗑️ Удалить запись (без возврата)", callback_data=f"admin_delete_sale_{sale.id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к журналу", callback_data="sales_journal")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def create_filter_selection_keyboard(items: list, callback_prefix: str, name_attr: str, id_attr: str) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        buttons.append([InlineKeyboardButton(text=getattr(item, name_attr), callback_data=f"{callback_prefix}_{getattr(item, id_attr)}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к фильтрам", callback_data="journal_filter")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_text_filter_selection_keyboard(items: list[str], callback_prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        buttons.append([InlineKeyboardButton(text=item, callback_data=f"{callback_prefix}_{item}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к фильтрам", callback_data="journal_filter")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_status_filter_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✅ Подтвержденные", callback_data="set_filter_status_true")],
        [InlineKeyboardButton(text="❌ Неподтвержденные", callback_data="set_filter_status_false")],
        [InlineKeyboardButton(text="⬅️ Назад к фильтрам", callback_data="journal_filter")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_product_management_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Добавить товар", callback_data="add_product")],
        [InlineKeyboardButton(text="Поступление товара", callback_data="add_stock")],
        [InlineKeyboardButton(text="Редактировать товар", callback_data="edit_product")],
        [InlineKeyboardButton(text="Показать ID товаров", callback_data="show_product_ids")],
        [InlineKeyboardButton(text="Управление категориями 🗂️", callback_data="manage_categories")],
        # [InlineKeyboardButton(text="Синхронизировать папки этикеток", callback_data="sync_label_folders")],
        [InlineKeyboardButton(text="Редактировать ID платформ", callback_data="edit_platform_ids")],
        [InlineKeyboardButton(text="⬅️ Назад в админ-панель", callback_data="back_to_admin_panel")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def get_category_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для главного меню управления категориями."""
    buttons = [
        [InlineKeyboardButton(text="Добавить категорию", callback_data="add_category")],
        [InlineKeyboardButton(text="Переименовать категорию", callback_data="rename_category")],
        [InlineKeyboardButton(text="Удалить категорию", callback_data="delete_category")],
        [InlineKeyboardButton(text="Распределить товары по категориям", callback_data="assign_products_to_category")],
        [InlineKeyboardButton(text="⬅️ Назад к управлению товарами", callback_data="manage_products")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_assign_category_keyboard(categories: list[Category], product_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора категории для конкретного товара."""
    buttons = []
    # Делаем кнопки по 2 в ряд, если их много
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(text=cat.name, callback_data=f"assign_cat_{product_id}_{cat.id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="➡️ Пропустить товар", callback_data=f"assign_cat_skip_{product_id}")])
    buttons.append([InlineKeyboardButton(text="⏹️ Завершить распределение", callback_data="manage_categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_category_selection_keyboard(categories: list[Category], callback_prefix: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора одной из существующих категорий."""
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(text=cat.name, callback_data=f"{callback_prefix}_{cat.id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="manage_categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_product_selection_keyboard(products: list[Product], prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    for product in products:
        buttons.append([InlineKeyboardButton(text=product.name, callback_data=f"{prefix}_{product.id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="manage_products")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def get_product_edit_keyboard(product_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Изменить название", callback_data=f"edit_name_{product_id}")],
        [InlineKeyboardButton(text="Изменить закуп. цену", callback_data=f"edit_price_{product_id}")],
        [InlineKeyboardButton(text="⬅️ Назад к выбору товара", callback_data="edit_product")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def get_user_management_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Добавить пользователя", callback_data="add_user")],
        [InlineKeyboardButton(text="Показать всех пользователей", callback_data="show_users")],
        [InlineKeyboardButton(text="Удалить пользователя", callback_data="delete_user")],
        [InlineKeyboardButton(text="⬅️ Назад в админ-панель", callback_data="back_to_admin_panel")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def create_user_selection_keyboard(users: list[User], callback_prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    for user in users:
        text = user.username or f"ID: {user.user_id}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"{callback_prefix}_{user.user_id}")])
    
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_admin_panel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def create_access_management_keyboard(user_id: int, all_products: list, user_product_ids: set) -> InlineKeyboardMarkup:
    buttons = []
    for product in all_products:
        has_access = product.id in user_product_ids
        icon = "✅" if has_access else "❌"
        text = f"{icon} {product.name}"
        callback_data = f"toggle_access_{user_id}_{product.id}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=callback_data)])
    
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к выбору пользователя", callback_data="manage_access")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def get_account_management_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Добавить аккаунт", callback_data="add_platform_account")],
        [InlineKeyboardButton(text="Назначить ответственного", callback_data="assign_account_user")],
        [InlineKeyboardButton(text="Удалить аккаунт", callback_data="delete_platform_account")],
        [InlineKeyboardButton(text="Снять ответственного", callback_data="remove_assignment")],
        [InlineKeyboardButton(text="Список аккаунтов и ответственных", callback_data="list_accounts")],
        [InlineKeyboardButton(text="⬅️ Назад в админ-панель", callback_data="back_to_admin_panel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_account_selection_keyboard(accounts: list[PlatformAccount], callback_prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    for acc in accounts:
        buttons.append([InlineKeyboardButton(text=f"{acc.display_name}", callback_data=f"{callback_prefix}_{acc.id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="manage_accounts")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_assignment_selection_keyboard(assignments: list) -> InlineKeyboardMarkup:
    buttons = []
    for assignment_id, acc_name, user_name in assignments:
        text = f"{escape(user_name)} -> {escape(acc_name)}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"delete_assignment_{assignment_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="manage_accounts")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
