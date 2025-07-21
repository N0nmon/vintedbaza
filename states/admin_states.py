from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    # Состояния для управления пользователями
    add_user_id = State()
    add_user_name = State()
    delete_user_id = State()
    
    # Состояние для управления доступом
    manage_access_user_id = State()

class AddProductStates(StatesGroup):
    name = State()
    photo = State()
    sizes = State()
    purchase_price = State()

class EditProductStates(StatesGroup):
    select_product = State()
    select_action = State()
    new_name = State()
    new_purchase_price = State()

class JournalFilterStates(StatesGroup):
    enter_period = State()
    select_seller = State()
    select_product = State()
    select_account = State()
    select_status = State()

class ReportStates(StatesGroup):
    select_seller_for_report = State()
    select_period_for_seller_report = State()
    enter_csv_period = State()

class AccountManagementStates(StatesGroup):
    enter_account_display_name = State()
    enter_account_search_name = State()
    select_account_to_assign = State()
    select_user_to_assign = State()
    select_account_to_delete = State()
    select_assignment_to_delete = State()

class AddStockStates(StatesGroup):
    select_product = State()
    enter_sizes = State()
