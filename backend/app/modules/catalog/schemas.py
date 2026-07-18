"""Pydantic v2-схемы М1. Состав каждой схемы задают API-флаги 02-contract.json.

Правило без исключений: поле попадает в XxxCreate ⟺ api.create = true,
в XxxUpdate ⟺ api.update = true, в XxxList ⟺ api.get_index = true,
в XxxRead ⟺ api.get_single = true. «Отдать всё подряд» — запрещено.

Карта флагов, перенесённая из контракта дословно:

  units.code             i ✓ s ✓ c ✓ u ✓
  units.name             i ✓ s ✓ c ✓ u ✓
  units.is_active        i ✓ s ✓ c ✗ u ✓   ← архивация только через update
  products.name          i ✓ s ✓ c ✓ u ✓
  products.unit_id       i ✓ s ✓ c ✓ u ✗   ← ЕИ товара после создания не меняется
  products.sku           i ✓ s ✓ c ✓ u ✓
  products.status        i ✓ s ✓ c ✗ u ✓
  warehouses.code        i ✓ s ✓ c ✓ u ✓
  warehouses.name        i ✓ s ✓ c ✓ u ✓
  warehouses.address     i ✗ s ✓ c ✓ u ✓   ← в списке адреса НЕТ
  warehouses.allows_issuance  i ✓ s ✓ c ✓ u ✓
  warehouses.status      i ✓ s ✓ c ✗ u ✓
  expense_types.name              i ✓ s ✓ c ✓ u ✓
  expense_types.requires_employee i ✓ s ✓ c ✓ u ✓
  expense_types.status            i ✓ s ✓ c ✗ u ✓
  expense_categories.name   i ✓ s ✓ c ✓ u ✓
  expense_categories.status i ✓ s ✓ c ✗ u ✓

DELETE-схем нет: SV-8 — справочники физически не удаляются.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import CatalogStatus

# ── units ───────────────────────────────────────────────────────────


class UnitList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    is_active: bool


class UnitRead(UnitList):
    """get_single-состав совпадает с get_index — наследуем, а не копируем."""


class UnitCreate(BaseModel):
    code: str = Field(min_length=1, max_length=16, examples=["шт"])
    name: str = Field(min_length=1, max_length=100, examples=["Штука"])
    # is_active не принимается: api.create = false. Новая единица активна
    # по server_default=true.


class UnitUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=16)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None  # SV-8: архивация единицы измерения


# ── products ────────────────────────────────────────────────────────


class ProductList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    unit_id: int
    sku: str | None
    status: CatalogStatus


class ProductRead(ProductList):
    pass


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255, examples=["Бумага A4"])
    unit_id: int
    sku: str | None = Field(default=None, max_length=64)
    # status не принимается: api.create = false → server_default='active'.


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    sku: str | None = Field(default=None, max_length=64)
    status: CatalogStatus | None = None  # SV-8: перевод в архив
    # unit_id отсутствует: api.update = false. Смена единицы измерения у товара
    # с историей движений переопределила бы смысл уже проведённых количеств.


# ── warehouses ──────────────────────────────────────────────────────


class WarehouseList(BaseModel):
    """address здесь НЕТ: api.get_index = false (есть только в детали)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    allows_issuance: bool
    status: CatalogStatus


class WarehouseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    address: str | None
    allows_issuance: bool
    status: CatalogStatus


class WarehouseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    # SV-9: «Склад списания». Отмеченных складов может быть несколько.
    allows_issuance: bool = False


class WarehouseUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=32)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    # Снятие галочки разрешено и НЕ инвалидирует ранее поданные заявки:
    # SV-9 — правило момента подачи (02-database.md §7.3).
    allows_issuance: bool | None = None
    status: CatalogStatus | None = None


# ── expense_types (расход ТОВАРА) ───────────────────────────────────


class ExpenseTypeList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    requires_employee: bool
    status: CatalogStatus


class ExpenseTypeRead(ExpenseTypeList):
    pass


class ExpenseTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, examples=["Выдача сотруднику"])
    requires_employee: bool


class ExpenseTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    # ВНИМАНИЕ (INV-4, ОВ-9): смена флага у типа, по которому уже есть проводки,
    # блокируется базой — составной FK с ON UPDATE CASCADE протянет новое
    # значение в writeoffs, и ck_writeoffs_employee_iff_required его отвергнет.
    # Это ожидаемое поведение, а не баг: штатный путь — архивировать тип и
    # завести новый (SV-8). Сервис переводит отказ БД в русский текст.
    requires_employee: bool | None = None
    status: CatalogStatus | None = None


# ── expense_categories (расход ДЕНЕГ) ───────────────────────────────


class ExpenseCategoryList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: CatalogStatus


class ExpenseCategoryRead(ExpenseCategoryList):
    pass


class ExpenseCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, examples=["Канцелярия"])


class ExpenseCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    status: CatalogStatus | None = None
