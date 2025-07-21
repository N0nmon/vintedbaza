from aiogram.fsm.state import State, StatesGroup

class SaleStates(StatesGroup):
    select_product = State()
    select_size = State()
    price = State()
    account = State() # Новое состояние
    label_link = State()
    screenshot = State()
