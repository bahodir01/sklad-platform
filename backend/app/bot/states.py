"""FSM-состояния диалогов бота (спека15 §3, §4). aiogram-хранилище —
``MemoryStorage`` (см. main.py): состояние живёт в памяти процесса и
теряется при перезапуске — приемлемо на масштабе школы (учитель просто
начинает диалог заново через меню), тот же компромисс, что и «перезапуск
процесса при смене токена» (спека15 §6, зафиксировано в отчёте 15d).
"""

from aiogram.fsm.state import State, StatesGroup


class IssuanceStates(StatesGroup):
    """Диалог «Заявка на товар» (спека15 §3)."""

    choosing_warehouse = State()
    entering_product_query = State()
    choosing_product = State()
    entering_qty = State()
    entering_reason = State()
    confirming = State()


class ExpenseStates(StatesGroup):
    """Диалог «Расход денег» (спека15 §4)."""

    choosing_category = State()
    entering_amount = State()
    entering_description = State()
    waiting_photo = State()
    confirming = State()
