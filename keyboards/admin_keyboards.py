from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db.models import Product, User

def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Добавить товар", callback_data="add_product")],
        [InlineKeyboardButton(text="Отменить продажу (с возвратом)", callback_data="process_return")],
        [InlineKeyboardButton(text="Управление пользователями", callback_data="manage_users")],
        [InlineKeyboardButton(text="Управление доступом к товарам", callback_data="manage_access")],
        [InlineKeyboardButton(text="Отчеты и Продажи", callback_data="sales_management")],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def get_sales_management_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Последние 10 продаж", callback_data="report_last_10")],
        [InlineKeyboardButton(text="Общая статистика", callback_data="report_summary")],
        [InlineKeyboardButton(text="Удалить ошибочную продажу", callback_data="delete_sale_start")],
        [InlineKeyboardButton(text="⬅️ Назад в админ-панель", callback_data="back_to_admin_panel")]
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

def create_user_selection_keyboard(users: list[User]) -> InlineKeyboardMarkup:
    buttons = []
    for user in users:
        text = user.username or f"ID: {user.user_id}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"select_user_access_{user.user_id}")])
    
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
