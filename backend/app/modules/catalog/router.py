"""Роутер М1. Архитектура §6:
GET,POST,PATCH /units | /products | /warehouses | /expense-types | /expense-categories
чтение: any · запись: admin.

DELETE не реализован НИ ДЛЯ ОДНОГО справочника — SV-8. Это не упущение:
удаления в системе нет, архивация делается PATCH-ом status/is_active.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import require_admin, require_any_role
from app.modules.catalog import service as svc
from app.modules.catalog.models import ExpenseCategory, ExpenseType, Product, Unit, Warehouse
from app.modules.catalog.schemas import (
    ExpenseCategoryCreate,
    ExpenseCategoryList,
    ExpenseCategoryRead,
    ExpenseCategoryUpdate,
    ExpenseTypeCreate,
    ExpenseTypeList,
    ExpenseTypeRead,
    ExpenseTypeUpdate,
    ProductCreate,
    ProductList,
    ProductRead,
    ProductUpdate,
    UnitCreate,
    UnitList,
    UnitRead,
    UnitUpdate,
    WarehouseCreate,
    WarehouseList,
    WarehouseRead,
    WarehouseUpdate,
)
from app.shared.enums import CatalogStatus
from app.shared.pagination import Page, PageParamsDep

router = APIRouter(tags=["catalog"])

EntityId = Annotated[int, Path(ge=1, description="Идентификатор записи")]

# Зависимости-охранники уровня операции (архитектура §6).
ReadAccess = Depends(require_any_role)
WriteAccess = Depends(require_admin)


# ══════════════════════ units ═══════════════════════════════════════


@router.get(
    "/units",
    response_model=Page[UnitList],
    dependencies=[ReadAccess],
    summary="Список единиц измерения",
)
async def list_units(
    params: PageParamsDep,
    is_active: Annotated[bool | None, Query(description="Фильтр по активности")] = None,
    session: AsyncSession = Depends(get_session),
) -> Page[UnitList]:
    filters = [Unit.is_active == is_active] if is_active is not None else None
    items, total = await svc.units_service(session).list(params, filters=filters)
    return Page.build([UnitList.model_validate(i) for i in items], total, params)


@router.get(
    "/units/{id}",
    response_model=UnitRead,
    dependencies=[ReadAccess],
    summary="Единица измерения",
)
async def get_unit(id: EntityId, session: AsyncSession = Depends(get_session)) -> Unit:
    return await svc.units_service(session).get(id)


@router.post(
    "/units",
    response_model=UnitRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WriteAccess],
    summary="Создать единицу измерения (admin)",
)
async def create_unit(
    payload: UnitCreate, session: AsyncSession = Depends(get_session)
) -> Unit:
    return await svc.units_service(session).create(payload)


@router.patch(
    "/units/{id}",
    response_model=UnitRead,
    dependencies=[WriteAccess],
    summary="Изменить/заархивировать единицу измерения (admin)",
)
async def update_unit(
    id: EntityId, payload: UnitUpdate, session: AsyncSession = Depends(get_session)
) -> Unit:
    # SV-8: архивация — is_active=false в этом же PATCH. DELETE отсутствует.
    return await svc.units_service(session).update(id, payload)


# ══════════════════════ products ════════════════════════════════════


@router.get(
    "/products",
    response_model=Page[ProductList],
    dependencies=[ReadAccess],
    summary="Список товаров",
)
async def list_products(
    params: PageParamsDep,
    status_filter: Annotated[CatalogStatus | None, Query(alias="status")] = None,
    unit_id: Annotated[int | None, Query(ge=1)] = None,
    session: AsyncSession = Depends(get_session),
) -> Page[ProductList]:
    filters = []
    if status_filter is not None:
        filters.append(Product.status == status_filter)
    if unit_id is not None:
        filters.append(Product.unit_id == unit_id)
    items, total = await svc.products_service(session).list(params, filters=filters or None)
    return Page.build([ProductList.model_validate(i) for i in items], total, params)


@router.get(
    "/products/{id}", response_model=ProductRead, dependencies=[ReadAccess], summary="Товар"
)
async def get_product(id: EntityId, session: AsyncSession = Depends(get_session)) -> Product:
    return await svc.products_service(session).get(id)


@router.post(
    "/products",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WriteAccess],
    summary="Создать товар (admin)",
)
async def create_product(
    payload: ProductCreate, session: AsyncSession = Depends(get_session)
) -> Product:
    return await svc.products_service(session).create(payload)


@router.patch(
    "/products/{id}",
    response_model=ProductRead,
    dependencies=[WriteAccess],
    summary="Изменить/заархивировать товар (admin)",
)
async def update_product(
    id: EntityId, payload: ProductUpdate, session: AsyncSession = Depends(get_session)
) -> Product:
    return await svc.products_service(session).update(id, payload)


# ══════════════════════ warehouses ══════════════════════════════════


@router.get(
    "/warehouses",
    response_model=Page[WarehouseList],
    dependencies=[ReadAccess],
    summary="Список складов",
)
async def list_warehouses(
    params: PageParamsDep,
    status_filter: Annotated[CatalogStatus | None, Query(alias="status")] = None,
    allows_issuance: Annotated[
        bool | None,
        Query(description="AP-12: склады списания для формы заявки (SV-9)"),
    ] = None,
    session: AsyncSession = Depends(get_session),
) -> Page[WarehouseList]:
    # AP-12: форма заявки запрашивает allows_issuance=true&status=active.
    # Индекса по allows_issuance нет намеренно — справочник крошечный,
    # seq scan корректен (02-database.md §7.3).
    filters = []
    if status_filter is not None:
        filters.append(Warehouse.status == status_filter)
    if allows_issuance is not None:
        filters.append(Warehouse.allows_issuance == allows_issuance)
    items, total = await svc.warehouses_service(session).list(params, filters=filters or None)
    return Page.build([WarehouseList.model_validate(i) for i in items], total, params)


@router.get(
    "/warehouses/{id}",
    response_model=WarehouseRead,
    dependencies=[ReadAccess],
    summary="Склад (с адресом)",
)
async def get_warehouse(id: EntityId, session: AsyncSession = Depends(get_session)) -> Warehouse:
    return await svc.warehouses_service(session).get(id)


@router.post(
    "/warehouses",
    response_model=WarehouseRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WriteAccess],
    summary="Создать склад (admin)",
)
async def create_warehouse(
    payload: WarehouseCreate, session: AsyncSession = Depends(get_session)
) -> Warehouse:
    return await svc.warehouses_service(session).create(payload)


@router.patch(
    "/warehouses/{id}",
    response_model=WarehouseRead,
    dependencies=[WriteAccess],
    summary="Изменить/заархивировать склад (admin)",
)
async def update_warehouse(
    id: EntityId, payload: WarehouseUpdate, session: AsyncSession = Depends(get_session)
) -> Warehouse:
    return await svc.warehouses_service(session).update(id, payload)


# ══════════════════ expense_types (расход ТОВАРА) ═══════════════════


@router.get(
    "/expense-types",
    response_model=Page[ExpenseTypeList],
    dependencies=[ReadAccess],
    summary="Список типов расхода товара",
)
async def list_expense_types(
    params: PageParamsDep,
    status_filter: Annotated[CatalogStatus | None, Query(alias="status")] = None,
    session: AsyncSession = Depends(get_session),
) -> Page[ExpenseTypeList]:
    filters = [ExpenseType.status == status_filter] if status_filter is not None else None
    items, total = await svc.expense_types_service(session).list(params, filters=filters)
    return Page.build([ExpenseTypeList.model_validate(i) for i in items], total, params)


@router.get(
    "/expense-types/{id}",
    response_model=ExpenseTypeRead,
    dependencies=[ReadAccess],
    summary="Тип расхода товара",
)
async def get_expense_type(
    id: EntityId, session: AsyncSession = Depends(get_session)
) -> ExpenseType:
    return await svc.expense_types_service(session).get(id)


@router.post(
    "/expense-types",
    response_model=ExpenseTypeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WriteAccess],
    summary="Создать тип расхода товара (admin)",
)
async def create_expense_type(
    payload: ExpenseTypeCreate, session: AsyncSession = Depends(get_session)
) -> ExpenseType:
    return await svc.expense_types_service(session).create(payload)


@router.patch(
    "/expense-types/{id}",
    response_model=ExpenseTypeRead,
    dependencies=[WriteAccess],
    summary="Изменить/заархивировать тип расхода товара (admin)",
)
async def update_expense_type(
    id: EntityId, payload: ExpenseTypeUpdate, session: AsyncSession = Depends(get_session)
) -> ExpenseType:
    # INV-4/ОВ-9: смена requires_employee у типа с историей будет отклонена
    # базой — сервис переведёт отказ в русский текст, а не в 500.
    return await svc.expense_types_service(session).update(id, payload)


# ═════════════ expense_categories (расход ДЕНЕГ) ════════════════════


@router.get(
    "/expense-categories",
    response_model=Page[ExpenseCategoryList],
    dependencies=[ReadAccess],
    summary="Список видов расхода денег",
)
async def list_expense_categories(
    params: PageParamsDep,
    status_filter: Annotated[CatalogStatus | None, Query(alias="status")] = None,
    session: AsyncSession = Depends(get_session),
) -> Page[ExpenseCategoryList]:
    filters = (
        [ExpenseCategory.status == status_filter] if status_filter is not None else None
    )
    items, total = await svc.expense_categories_service(session).list(params, filters=filters)
    return Page.build([ExpenseCategoryList.model_validate(i) for i in items], total, params)


@router.get(
    "/expense-categories/{id}",
    response_model=ExpenseCategoryRead,
    dependencies=[ReadAccess],
    summary="Вид расхода денег",
)
async def get_expense_category(
    id: EntityId, session: AsyncSession = Depends(get_session)
) -> ExpenseCategory:
    return await svc.expense_categories_service(session).get(id)


@router.post(
    "/expense-categories",
    response_model=ExpenseCategoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WriteAccess],
    summary="Создать вид расхода денег (admin)",
)
async def create_expense_category(
    payload: ExpenseCategoryCreate, session: AsyncSession = Depends(get_session)
) -> ExpenseCategory:
    return await svc.expense_categories_service(session).create(payload)


@router.patch(
    "/expense-categories/{id}",
    response_model=ExpenseCategoryRead,
    dependencies=[WriteAccess],
    summary="Изменить/заархивировать вид расхода денег (admin)",
)
async def update_expense_category(
    id: EntityId, payload: ExpenseCategoryUpdate, session: AsyncSession = Depends(get_session)
) -> ExpenseCategory:
    return await svc.expense_categories_service(session).update(id, payload)
