from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from db.models import Product, Sale

def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Создает клавиатуру главного меню.
    """
    buttons = [
        [KeyboardButton(text="Просмотреть остатки 📦")],
        [KeyboardButton(text="Зарегистрировать продажу 💸")],
        [KeyboardButton(text="Мои продажи 📋")],
        [KeyboardButton(text="Сводка по товарам 📈")],
        [KeyboardButton(text="Сводка по задачам 📊")],
        [KeyboardButton(text="Получить этикетку 🏷️")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    return keyboard

def get_my_sales_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Подтвердить продажу", callback_data="confirm_sale_menu")],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def create_confirmation_keyboard(unconfirmed_sales: list[Sale]) -> InlineKeyboardMarkup:
    buttons = []
    for sale in unconfirmed_sales:
        text = f"№{sale.id} | {sale.sale_date.strftime('%d.%m')} | {sale.stock_item.product.name} ({sale.stock_item.size})"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"confirm_sale_{sale.id}")])

    buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_action")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def get_cancel_kb() -> ReplyKeyboardMarkup:
    """
    Создает клавиатуру с одной кнопкой "Отмена".
    """
    buttons = [
        [KeyboardButton(text="⬅️ Отмена")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    return keyboard

def remove_kb() -> ReplyKeyboardRemove:
    """
    Возвращает объект для удаления reply-клавиатуры.
    """
    return ReplyKeyboardRemove()


def create_products_keyboard(products: list[Product], action: str) -> InlineKeyboardMarkup:
    """
    Создает inline-клавиатуру со списком товаров.
    action может быть 'stock' или 'sale' для формирования разных callback_data.
    """
    buttons = []
    for product in products:
        callback_data = f"{action}_{product.id}"
        button = InlineKeyboardButton(text=product.name, callback_data=callback_data)
        buttons.append([button])
    
    buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_action")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

def create_sizes_keyboard(sizes: list, product_id: int) -> InlineKeyboardMarkup:
    """
    Создает inline-клавиатуру с доступными размерами для продажи.
    """
    buttons = []
    for size, count in sizes:
        text = f"Размер: {size} ({count} шт.)"
        callback_data = f"sale_size_{product_id}_{size}"
        button = InlineKeyboardButton(text=text, callback_data=callback_data)
        buttons.append([button])
    
    buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_action")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

# --- НАЧАЛО БЛОКА: Новая клавиатура для выбора размера этикетки ---
def create_label_sizes_keyboard(sizes: list[str], product_id: int) -> InlineKeyboardMarkup:
    """
    Создает inline-клавиатуру с размерами, для которых есть этикетки.
    """
    buttons = []
    for size in sorted(sizes): # Сортируем размеры для порядка
        button = InlineKeyboardButton(text=f"Размер: {size}", callback_data=f"get_label_{product_id}_{size}")
        buttons.append([button])

    buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_action")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard
# --- КОНЕЦ БЛОКА ---