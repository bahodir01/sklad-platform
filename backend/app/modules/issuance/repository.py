"""Доступ к данным М4 (архитектура §2 — без бизнес-правил).

Запросы фильтр-карточек экрана «Выдачи товара» (спека13 §5: К выдаче/К подписи/
Подписано/Передано), «Моих заявок» (AP-4, row-level в сервисе), реестра ПЕРЕДАЧИ
в бухгалтерию (спека13 §4) и справочные данные для issue()/бланка/пачки.
"""

from collections import namedtuple
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.auth.models import User
from app.modules.catalog.models import ExpenseType, Product, Unit
from app.modules.issuance.models import Request, SignatureBatch, Writeoff
from app.shared.enums import CatalogStatus, RequestStatus
from app.shared.pagination import PageParams

ProductInfo = namedtuple("ProductInfo", ["name", "unit_code"])


def _attach_employee(req: Request, full_name: str, category: Any) -> Request:
    """Навешивает вычисляемые ФИО+категорию сотрудника на ORM-объект заявки.

    §6.3/§6.4: Read-ответы заявок показывают «ФИО и категорию сотрудника», а не
    только employee_id. Значения приходят JOIN-ом на `users` (тот же приём, что в
    отчёте ДДС) и НЕ являются колонками — это ненавязчивые атрибуты экземпляра,
    которые читает Pydantic (from_attributes) как employee_full_name/…_category.
    В БД не пишутся, схема не меняется.
    """
    req.employee_full_name = full_name
    req.employee_category = category
    return req


class IssuanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── чтение заявок ───────────────────────────────────────────────

    async def get_request(self, request_id: int) -> Request | None:
        """Заявка без строк — для проверок статуса/владельца."""
        return await self._session.get(Request, request_id)

    async def get_request_with_items(
        self, request_id: int, *, populate_existing: bool = False
    ) -> Request | None:
        """Заявка со строками + ФИО/категория сотрудника (JOIN на users, §6.3/§6.4).

        populate_existing=True синхронизирует in-session объект с БД после
        условного UPDATE (был status/writeoff_id меняли синхронизацию сессии).
        """
        stmt = (
            select(Request, User.full_name, User.category)
            .join(User, Request.employee_id == User.id)
            .where(Request.id == request_id)
            .options(selectinload(Request.items))
        )
        if populate_existing:
            stmt = stmt.execution_options(populate_existing=True)
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        req, full_name, category = row
        return _attach_employee(req, full_name, category)

    async def list_requests(
        self, params: PageParams, *, filters: list[Any] | None = None
    ) -> tuple[list[Request], int]:
        """Список заявок (фильтр-карточки, «Мои») — offset-пагинация.

        Сортировка (created_at DESC, id DESC) ложится на композитный индекс
        (employee_id, created_at DESC) для «Моих заявок» (AP-4). Фильтр по
        status обслуживает ix_requests_status (спека13 §5).
        """
        # JOIN на users: список показывает ФИО+категорию (§6.3), а не employee_id.
        stmt: Select = (
            select(Request, User.full_name, User.category)
            .join(User, Request.employee_id == User.id)
        )
        if filters:
            stmt = stmt.where(*filters)
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        rows = await self._session.execute(
            stmt.order_by(Request.created_at.desc(), Request.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        result = [
            _attach_employee(req, full_name, category)
            for req, full_name, category in rows.all()
        ]
        return result, int(total or 0)

    async def count_requests(self, *, filters: list[Any] | None = None) -> int:
        """Счётчик фильтр-карточки (спека13 §5). WHERE status=? покрыт
        ix_requests_status — запрос крошечный."""
        stmt = select(func.count()).select_from(Request)
        if filters:
            stmt = stmt.where(*filters)
        return int(await self._session.scalar(stmt) or 0)

    # ── реестр ПЕРЕДАЧИ в бухгалтерию (спека13 §4) ──────────────────

    async def registry(
        self, params: PageParams, *, filters: list[Any] | None = None
    ) -> tuple[list[tuple[Request, Writeoff]], int]:
        """Переданные заявки + их проводки. ОБА номера (ADR-2a) + ФИО/категория
        сотрудника + реквизиты передачи (спека13 §4) — JOIN на users/writeoffs.

        Реестр — доказательство передачи (бухгалтерия расписывается): показываем
        заявки status='submitted'. Опциональные фильтры (register_no, дата) —
        через filters от сервиса.
        """
        base: Select = (
            select(Request, Writeoff, User.full_name, User.category)
            .join(Writeoff, Request.writeoff_id == Writeoff.id)
            .join(User, Request.employee_id == User.id)
            .where(Request.status == RequestStatus.submitted)
        )
        if filters:
            base = base.where(*filters)
        total = await self._session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        rows = await self._session.execute(
            base.order_by(Request.submitted_at.desc(), Request.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        return (
            [(_attach_employee(r, fn, cat), w) for r, w, fn, cat in rows.all()],
            int(total or 0),
        )

    # ── пачка печати/подписи (спека13 §3) ───────────────────────────

    async def lock_issued_requests(self, ids: list[int]) -> list[Request]:
        """Заявки из списка в статусе 'issued', заблокированные FOR UPDATE.

        Пакетная печать/подпись трогают статус — блокировка сериализует их с
        конкурентным issue()/mark-signed по тем же строкам (спека13 §6). Не-issued
        id просто не попадают в выборку (в сервисе уходят в skipped)."""
        if not ids:
            return []
        rows = await self._session.scalars(
            select(Request)
            .where(Request.id.in_(ids), Request.status == RequestStatus.issued)
            .order_by(Request.id)
            .with_for_update()
        )
        return list(rows)

    async def get_batch(self, batch_id: int) -> SignatureBatch | None:
        return await self._session.get(SignatureBatch, batch_id)

    async def batch_requests_detail(
        self, batch_id: int
    ) -> list[tuple[Request, str, Any]]:
        """Заявки пачки со строками + ФИО/категория, СГРУППИРОВАННЫЕ по сотруднику.

        Для одного PDF по сотрудникам (спека13 §3): сортировка по employee_id
        собирает разделы одного человека рядом."""
        rows = await self._session.execute(
            select(Request, User.full_name, User.category)
            .join(User, Request.employee_id == User.id)
            .where(Request.batch_id == batch_id)
            .options(selectinload(Request.items))
            .order_by(User.full_name, Request.id)
        )
        return [(r, fn, cat) for r, fn, cat in rows.all()]

    # ── справочные данные для issue()/бланка ────────────────────────

    async def issuance_expense_type(self) -> ExpenseType | None:
        """Тип расхода «Выдача»: активный тип с requires_employee=true.

        issue() создаёт проводку именно этого типа (спека13 §2). Порча/брак имеют
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
