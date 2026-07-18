"""Бизнес-правила М1. Транзакция открывается здесь (архитектура §2).

Главное правило модуля — SV-8: справочники НЕ удаляются физически.
Метода delete() в этом сервисе нет и быть не должно; архивация — это
update со status='archived' / is_active=false.
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.core.exceptions import DomainError, DuplicateError, NotFoundError, ValidationError
from app.modules.catalog.models import (
    ExpenseCategory,
    ExpenseType,
    Product,
    Unit,
    Warehouse,
)
from app.modules.catalog.repository import CatalogRepository
from app.shared.pagination import PageParams

M = TypeVar("M", bound=Base)


class CatalogService(Generic[M]):
    """Один сервис на пять справочников: правила у них общие.

    :param unique_field: колонка с UNIQUE — для внятной ошибки вместо 500.
    :param title: русское название сущности для текстов ошибок.
    """

    def __init__(
        self,
        session: AsyncSession,
        model: type[M],
        *,
        title: str,
        unique_field: str | None = None,
        unique_title: str | None = None,
    ) -> None:
        self._session = session
        self._model = model
        self._repo: CatalogRepository[M] = CatalogRepository(session, model)
        self._title = title
        self._unique_field = unique_field
        self._unique_title = unique_title or "Значение"

    async def list(self, params: PageParams, *, filters: list[Any] | None = None):
        return await self._repo.list(params, filters=filters)

    async def get(self, entity_id: int) -> M:
        entity = await self._repo.get(entity_id)
        if entity is None:
            raise NotFoundError(self._title, entity_id)
        return entity

    async def create(self, payload: BaseModel) -> M:
        data = payload.model_dump(exclude_unset=True)
        await self._ensure_unique(data.get(self._unique_field) if self._unique_field else None)
        entity = self._model(**data)
        self._repo.add(entity)
        await self._commit()
        await self._session.refresh(entity)
        return entity

    async def update(self, entity_id: int, payload: BaseModel) -> M:
        entity = await self.get(entity_id)
        # exclude_unset: PATCH — «не прислали» и «прислали null» это разные
        # вещи. Без него sku=None затирал бы артикул при любом обновлении имени.
        data = payload.model_dump(exclude_unset=True)

        if self._unique_field and self._unique_field in data:
            new_value = data[self._unique_field]
            if new_value != getattr(entity, self._unique_field):
                await self._ensure_unique(new_value)

        for field, value in data.items():
            setattr(entity, field, value)

        await self._commit()
        await self._session.refresh(entity)
        return entity

    # SV-8: delete() отсутствует намеренно. Физическое удаление справочника
    # запрещено ТЗ; FK стоят ondelete=RESTRICT и его бы и не пропустили.

    async def _ensure_unique(self, value: Any) -> None:
        if self._unique_field is None or value is None:
            return
        column = getattr(self._model, self._unique_field)
        exists = await self._session.scalar(select(column).where(column == value).limit(1))
        if exists is not None:
            raise DuplicateError(self._unique_title, value)

    async def _commit(self) -> None:
        """Коммит с переводом отказов БД в доменные ошибки.

        Проверка уникальности выше — это UX (внятный текст), а не гарантия:
        между SELECT и INSERT есть окно, и в него попадёт конкурентный запрос.
        Гарантию даёт UNIQUE-constraint, поэтому его нарушение обязано
        обрабатываться и здесь.
        """
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise _translate_integrity_error(exc, self._title, self._unique_title) from exc


def _translate_integrity_error(
    exc: IntegrityError, title: str, unique_title: str
) -> DomainError:
    """Отказ constraint-а → русский текст для тостера (архитектура §6)."""
    text = str(getattr(exc, "orig", exc))

    if "uq_expense_types_id_requires_employee" in text or "fk_writeoffs_expense_type" in text:
        # INV-4 / ОВ-9: у типа расхода уже есть проводки.
        return ValidationError(
            "Признак «требуется сотрудник» нельзя изменить у типа расхода, "
            "по которому уже есть списания. Заархивируйте тип и создайте новый",
            code="expense_type_flag_locked",
        )
    if "ck_writeoffs_employee_iff_required" in text:
        return ValidationError(
            "Признак «требуется сотрудник» противоречит уже проведённым списаниям "
            "этого типа расхода. Заархивируйте тип и создайте новый",
            code="expense_type_flag_locked",
        )
    if "unique" in text.lower() or "duplicate key" in text.lower():
        return DuplicateError(unique_title, "")
    if "foreign key" in text.lower() or "violates foreign key" in text.lower():
        return ValidationError(
            "Указана несуществующая связанная запись", code="fk_violation"
        )
    if "check constraint" in text.lower():
        return ValidationError(f"{title}: значения полей нарушают правила учёта")
    return ValidationError(f"{title}: операция отклонена базой данных")


# ── Фабрики сервисов: русские названия и UNIQUE-поля в одном месте ───


def units_service(session: AsyncSession) -> CatalogService[Unit]:
    return CatalogService(
        session, Unit, title="Единица измерения", unique_field="code", unique_title="Код единицы"
    )


def products_service(session: AsyncSession) -> CatalogService[Product]:
    # У products UNIQUE-полей нет: sku по контракту не unique.
    return CatalogService(session, Product, title="Товар")


def warehouses_service(session: AsyncSession) -> CatalogService[Warehouse]:
    return CatalogService(
        session, Warehouse, title="Склад", unique_field="code", unique_title="Код склада"
    )


def expense_types_service(session: AsyncSession) -> CatalogService[ExpenseType]:
    return CatalogService(session, ExpenseType, title="Тип расхода товара")


def expense_categories_service(session: AsyncSession) -> CatalogService[ExpenseCategory]:
    return CatalogService(session, ExpenseCategory, title="Вид расхода денег")
