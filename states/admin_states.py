from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    # Состояния для управления пользователями
    add_user_id = State()
    add_user_name = State()
    delete_user_id = State()
    
    # Состояние для управления доступом
    manage_access_user_id = State()

    # Состояние для возврата товара
    return_sale_id = State()

    # Состояние для удаления продажи
    delete_sale_id = State()

class AddProductStates(StatesGroup):
    name = State()
    photo = State()
    sizes = State()
