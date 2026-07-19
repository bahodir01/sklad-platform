"""Pydantic v2-схемы М4. Состав задают API-флаги 02-contract.json, ДОСЛОВНО.

Правило без исключений: поле в XxxCreate ⟺ api.create=true,
в XxxRead ⟺ api.get_single=true, в XxxList ⟺ api.get_index=true.
Update-схем нет: у requests/writeoffs НЕТ ни одного update=true — статусы
двигает только сервер через статусную машину (ADR-2, editable=False).

Вложенные строки (`items`) и не-колоночные величины разрешены валидатору
контракта явным `__contract_extra_fields__`.

Карта флагов (перенос из контракта):

  requests        List (get_index): id number employee_id warehouse_id status
                                    issued_at writeoff_id created_at batch_id
                                    submitted_at submitted_register_no
                  Read (get_single): + reason printed_at pdf_url
                  Create: warehouse_id, reason (+ items)
                  Update: — (нет ни одного update=true)

  Фича 13 (спека §2-§4): статусы draft→to_issue→issued→signed→submitted;
  batch_id/submitted_at/submitted_register_no — server-managed read-поля,
  выведены в List+Read (get_index/get_single=true в контракте 0002).
  request_items   Create: product_id, qty
                  Read:   id request_id product_id qty
                  (get_index только у id → отдельной List-схемы не заводим)
  writeoffs       List (get_index): id number date warehouse_id expense_type_id
                                    employee_id author_id
                  Read (get_single): + requires_employee
                  Create: date warehouse_id expense_type_id employee_id
                          — порча/брак (POST /writeoffs), вне scope этапа 3
  writeoff_items  Read (get_single): id writeoff_id product_id qty reason
                  Create: product_id qty reason
"""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import RequestStatus, UserCategory

# ── request_items ───────────────────────────────────────────────────


class RequestItemCreate(BaseModel):
    product_id: int
    qty: Decimal = Field(gt=0, description="Запрошено, > 0 (INV-6)")


class RequestItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int
    product_id: int
    qty: Decimal


# ── requests ────────────────────────────────────────────────────────


class RequestCreate(BaseModel):
    """POST /requests — черновик заявки сотрудника.

    employee_id НЕ принимается (api.create=false): сервер ставит его из
    current_user (SV-6-аналог для заявок). warehouse_id — только склад с
    allows_issuance=true AND status='active' (SV-9), проверяет сервис + триггер.
    """

    __contract_extra_fields__ = {"items"}

    warehouse_id: int
    reason: str = Field(min_length=1, description="Обоснование получения (печатается)")
    items: list[RequestItemCreate] = Field(min_length=1)


class RequestList(BaseModel):
    """get_index-состав. Ни reason, ни printed_at, ни pdf_url здесь нет.

    employee_full_name / employee_category — ВЫЧИСЛЯЕМЫЕ поля (§6.3: очередь «К
    печати» показывает «ФИО и категорию сотрудника», а не только employee_id).
    Резолвятся JOIN-ом на `users` по employee_id в репозитории — тот же приём,
    что в отчёте ДДС (reports). Колонками словаря НЕ являются, поэтому вынесены в
    __contract_extra_fields__ (как computed-величины отчётов), а не в контракт.
    """

    model_config = ConfigDict(from_attributes=True)
    __contract_extra_fields__ = {"employee_full_name", "employee_category"}

    id: int
    number: str
    employee_id: int
    employee_full_name: str | None = None
    employee_category: UserCategory | None = None
    warehouse_id: int
    status: RequestStatus
    issued_at: dt.datetime | None
    writeoff_id: int | None
    created_at: dt.datetime
    # ── Фича 13 (спека §3/§4): пачка печати/подписи + передача ──
    batch_id: int | None
    submitted_at: dt.date | None
    submitted_register_no: str | None


class RequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    # items — вложенные строки; employee_full_name/employee_category —
    # вычисляемые (JOIN на users, §6.3/§6.4). Ни то, ни другое не колонка словаря.
    __contract_extra_fields__ = {"items", "employee_full_name", "employee_category"}

    id: int
    number: str
    employee_id: int
    employee_full_name: str | None = None
    employee_category: UserCategory | None = None
    warehouse_id: int
    reason: str
    status: RequestStatus
    printed_at: dt.datetime | None
    issued_at: dt.datetime | None
    writeoff_id: int | None
    pdf_url: str | None
    created_at: dt.datetime
    # ── Фича 13 (спека §3/§4): пачка печати/подписи + передача ──
    batch_id: int | None
    submitted_at: dt.date | None
    submitted_register_no: str | None
    items: list[RequestItemRead] = []


# ── writeoff_items ──────────────────────────────────────────────────


class WriteoffItemCreate(BaseModel):
    """Строка прямого списания (порча/брак). Состав = api.create writeoff_items."""

    product_id: int
    qty: Decimal = Field(gt=0, description="Списываемое количество, > 0 (INV-6)")
    reason: str | None = Field(default=None, max_length=500, description="Причина списания")


class WriteoffItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    writeoff_id: int
    product_id: int
    qty: Decimal
    reason: str | None


# ── writeoffs ───────────────────────────────────────────────────────


class WriteoffCreate(BaseModel):
    """POST /writeoffs — ЭТАП 4: прямое списание порча/брак БЕЗ заявки (admin).

    Только типы с requires_employee=false (Порча/Брак). Выдача (requires_employee=
    true) через этот эндпоинт запрещена — она проводится статусной машиной заявки
    (issue(), этап 3). employee_id при порче/браке обязан быть NULL (INV-4).

    Состав полей = api.create писеоффа ДОСЛОВНО: date, warehouse_id,
    expense_type_id, employee_id. number/requires_employee/author_id ставит сервер.
    """

    __contract_extra_fields__ = {"items"}

    date: dt.date
    warehouse_id: int
    expense_type_id: int
    # employee_id принимается (api.create=true), но при порче/браке ДОЛЖЕН быть
    # None — сервис отклонит непустое значение внятной ошибкой до CHECK INV-4.
    employee_id: int | None = None
    items: list[WriteoffItemCreate] = Field(min_length=1)


class WriteoffRead(BaseModel):
    """Проводка списания (get_single). При выдаче рождается внутри issue()."""

    model_config = ConfigDict(from_attributes=True)
    __contract_extra_fields__ = {"items"}

    id: int
    number: str
    date: dt.date
    warehouse_id: int
    expense_type_id: int
    requires_employee: bool
    employee_id: int | None
    author_id: int
    items: list[WriteoffItemRead] = []


# ── Транспортные конверты (НЕ суффикс Create/Update/Read/List → вне
#    проверки контракта: это не проекции таблиц, а ответы операций) ───


class RequestCount(BaseModel):
    """Бейдж-счётчик фильтр-карточки экрана «Выдачи товара» (спека13 §5)."""

    count: int


class IdListRequest(BaseModel):
    """Тело bulk-действий (спека13 §3/§4): список id, работа с исключениями.

    Клиент присылает id, которые ДЕЙСТВИТЕЛЬНО обрабатываются (напр. подписанные);
    исключённые (снятая галочка) просто не попадают в список — сервер их не трогает.
    """

    ids: list[int] = Field(min_length=1, description="Идентификаторы заявок")


class IssueResult(BaseModel):
    """Ответ POST /requests/{id}/issue: заявка + рождённая проводка (спека13 §2)."""

    request: RequestRead
    writeoff: WriteoffRead


class BatchPrintResult(BaseModel):
    """Ответ POST /requests/batch-print (спека13 §3): создана пачка, один PDF по
    сотрудникам. Статус заявок НЕ меняется — печать лишь группирует и печатает."""

    batch_id: int
    batch_number: str
    printed: list[int] = []  # заявки, попавшие в пачку (были issued)
    skipped: list[int] = []  # не issued — в пачку не взяты
    rendered_pdf: bool = False  # False → WeasyPrint без нативных зависимостей


class MarkSignedResult(BaseModel):
    """Ответ POST /requests/mark-signed (спека13 §3): issued → signed, исключения
    остаются issued."""

    signed: list[int] = []
    skipped: list[int] = []


class SubmitResult(BaseModel):
    """Ответ POST /requests/submit-to-accounting (спека13 §4): signed → submitted,
    общий submitted_register_no на весь вызов."""

    register_no: str | None = None
    submitted: list[int] = []
    skipped: list[int] = []


class RegistryRow(BaseModel):
    """Строка реестра ПЕРЕДАЧИ в бухгалтерию (спека13 §4, ADR-2a): ОБА номера +
    номер реестра передачи. Доказательство передачи — бухгалтерия расписывается.

    Поиск работает по любому из номеров — бухгалтерия держит на руках бумагу с
    номером ЗАЯВКИ (проводки на момент печати ещё не существовало), а в учёте
    списание лежит под номером ПРОВОДКИ.
    """

    request_id: int
    request_number: str
    writeoff_id: int
    writeoff_number: str
    employee_id: int
    # §6.4: ФИО+категория сотрудника рядом с ОБОИМИ номерами. JOIN на users.
    employee_full_name: str | None = None
    employee_category: UserCategory | None = None
    warehouse_id: int
    issued_at: dt.datetime | None
    writeoff_date: dt.date
    # Фича 13 (спека §4): реквизиты передачи в бухгалтерию.
    submitted_at: dt.date | None = None
    submitted_register_no: str | None = None
