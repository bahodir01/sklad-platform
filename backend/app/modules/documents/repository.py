"""Доступ к данным М2 (архитектура §2 — без бизнес-правил).

Здесь живут запросы, которые сервису нужны для контроля перезакупки (SV-1):
блокировка строк уведомления (FOR UPDATE) и агрегат «уже приобретено» по
(notification, product) из acquisition_items (AP-6/AP-7).
"""

from collections import namedtuple
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.catalog.models import Product, Unit
from app.modules.documents.models import (
    Acquisition,
    AcquisitionItem,
    Notification,
    NotificationItem,
)
from app.shared.pagination import PageParams

ProductInfo = namedtuple("ProductInfo", ["name", "unit_code"])


class DocumentsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── notifications ───────────────────────────────────────────────

    async def list_notifications(
        self, params: PageParams, *, filters: list[Any] | None = None
    ) -> tuple[list[Notification], int]:
        stmt: Select[tuple[Notification]] = select(Notification)
        if filters:
            stmt = stmt.where(*filters)
        total = await self._session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        rows = await self._session.scalars(
            stmt.order_by(Notification.id.desc()).offset(params.offset).limit(params.limit)
        )
        return list(rows), int(total or 0)

    async def get_notification_with_items(self, notification_id: int) -> Notification | None:
        return await self._session.scalar(
            select(Notification)
            .where(Notification.id == notification_id)
            .options(selectinload(Notification.items))
        )

    async def lock_notification_items(self, notification_id: int) -> list[NotificationItem]:
        """SV-1/AP-7: блокируем ВСЕ строки уведомления до конца транзакции.

        Без FOR UPDATE два параллельных приобретения оба прочитали бы
        remaining=10 и оба прошли бы проверку — TOCTOU → перезакупка. Блокировка
        сериализует их: второй ждёт коммита первого и видит обновлённый остаток.
        """
        rows = await self._session.scalars(
            select(NotificationItem)
            .where(NotificationItem.notification_id == notification_id)
            .with_for_update()
        )
        return list(rows)

    async def has_acquisitions(self, notification_id: int) -> bool:
        """Есть ли хоть одно приобретение у уведомления (SV-11).

        Удаление уведомления разрешено ⟺ приобретений нет: они породили бы
        append-only движения склада (ADR-1). FK acquisitions.notification_id
        RESTRICT страхует на уровне БД — здесь даём внятный русский отказ ДО
        отказа constraint-а.
        """
        exists = await self._session.scalar(
            select(func.count())
            .select_from(Acquisition)
            .where(Acquisition.notification_id == notification_id)
        )
        return bool(exists)

    async def purchased_by_product(self, notification_id: int) -> dict[int, Decimal]:
        """Сколько уже приобретено по каждому товару этого уведомления.

        SUM(acquisition_items.qty) по всем приобретениям уведомления,
        сгруппированный по товару (AP-6). qty_purchased не хранится (ТЗ §3) —
        это его единственный источник истины.
        """
        rows = await self._session.execute(
            select(
                AcquisitionItem.product_id,
                func.coalesce(func.sum(AcquisitionItem.qty), 0),
            )
            .join(Acquisition, AcquisitionItem.acquisition_id == Acquisition.id)
            .where(Acquisition.notification_id == notification_id)
            .group_by(AcquisitionItem.product_id)
        )
        return {pid: Decimal(total) for pid, total in rows.all()}

    async def product_info(self, product_ids: list[int]) -> dict[int, ProductInfo]:
        """Имя товара + код ЕИ (из products.unit_id) — для текстов ошибок и бланка.

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

    async def get_acquisition_with_items(self, acquisition_id: int) -> Acquisition | None:
        return await self._session.scalar(
            select(Acquisition)
            .where(Acquisition.id == acquisition_id)
            .options(selectinload(Acquisition.items))
        )
