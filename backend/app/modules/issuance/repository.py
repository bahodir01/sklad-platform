"""Доступ к данным М4 (архитектура §2 — без бизнес-правил).

Запросы очереди «К печати» (AP-2/AP-3), «Моих заявок» (AP-4, row-level в
сервисе), реестра выданных документов (AP-11: проводка → заявка → бумага) и
справочные данные для issue()/бланка.
"""

from collections import namedtuple
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.catalog.models import ExpenseType, Product, Unit
from app.modules.issuance.models import Request, Writeoff
from app.shared.enums import CatalogStatus, RequestStatus
from app.shared.pagination import PageParams

ProductInfo = namedtuple("ProductInfo", ["name", "unit_code"])


class IssuanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── чтение заявок ───────────────────────────────────────────────

    async def get_request(self, request_id: int) -> Request | None:
        """Заявка без строк — для проверок статуса/владельца."""
        return await self._session.get(Request, request_id)

    async def get_request_with_items(self, request_id: int) -> Request | None:
        return await self._session.scalar(
            select(Request)
            .where(Request.id == request_id)
            .options(selectinload(Request.items))
        )

    async def list_requests(
        self, params: PageParams, *, filters: list[Any] | None = None
    ) -> tuple[list[Request], int]:
        """Список заявок (очередь «К печати», «Мои») — offset-пагинация.

        Сортировка (created_at DESC, id DESC) ложится на композитный индекс
        (employee_id, created_at DESC) для «Моих заявок» (AP-4).
        """
        stmt: Select[tuple[Request]] = select(Request)
        if filters:
            stmt = stmt.where(*filters)
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        rows = await self._session.scalars(
            stmt.order_by(Request.created_at.desc(), Request.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        return list(rows), int(total or 0)

    async def count_requests(self, *, filters: list[Any] | None = None) -> int:
        """AP-3: бейдж-счётчик. WHERE status='to_print' покрыт частичным
        индексом ix_requests_to_print — запрос крошечный."""
        stmt = select(func.count()).select_from(Request)
        if filters:
            stmt = stmt.where(*filters)
        return int(await self._session.scalar(stmt) or 0)

    # ── реестр выданных (§6.4, AP-11) ───────────────────────────────

    async def registry(
        self, params: PageParams, *, filters: list[Any] | None = None
    ) -> tuple[list[tuple[Request, Writeoff]], int]:
        """Выданные заявки + их проводки. ОБА номера (ADR-2a)."""
        base: Select = (
            select(Request, Writeoff)
            .join(Writeoff, Request.writeoff_id == Writeoff.id)
            .where(Request.status == RequestStatus.issued)
        )
        if filters:
            base = base.where(*filters)
        total = await self._session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        rows = await self._session.execute(
            base.order_by(Request.issued_at.desc(), Request.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        return [(r, w) for r, w in rows.all()], int(total or 0)

    # ── справочные данные для issue()/бланка ────────────────────────

    async def issuance_expense_type(self) -> ExpenseType | None:
        """Тип расхода «Выдача»: активный тип с requires_employee=true.

        issue() создаёт проводку именно этого типа (§5.3). Порча/брак имеют
        requires_employee=false и через заявку никогда не проходят.
        """
        return await self._session.scalar(
            select(ExpenseType)
            .where(
                ExpenseType.requires_employee.is_(True),
                ExpenseType.status == CatalogStatus.active,
            )
            .order_by(ExpenseType.id)
        )

    async def product_info(self, product_ids: list[int]) -> dict[int, ProductInfo]:
        """Имя товара + код ЕИ (из products.unit_id) — для текста ошибок и бланка.

        Единица в строках документов не хранится (ТЗ §3) — тянется отсюда.
        """
        if not product_ids:
            return {}
        rows = await self._session.execute(
            select(Product.id, Product.name, Unit.code)
            .join(Unit, Product.unit_id == Unit.id)
            .where(Product.id.in_(product_ids))
        )
        return {pid: ProductInfo(name, code) for pid, name, code in rows.all()}
