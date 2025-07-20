from aiogram.fsm.state import State, StatesGroup

class SaleStates(StatesGroup):
    select_product = State()
    select_size = State()
    price = State()
    label_link = State()
    screenshot = State()
