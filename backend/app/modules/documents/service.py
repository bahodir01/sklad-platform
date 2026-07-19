"""Бизнес-правила М2. Транзакция открывается здесь (архитектура §2).

Три операции, три инварианта:
  * create_acquisition — SV-1, контроль перезакупки (§5.1), + SV-7 автозакрытие;
  * create_transfer    — две записи ledger (§4.3), SV-3 через InsufficientStock;
  * create_notification — CRUD-шапка, строки-потолки для SV-1.

Единственный писатель остатков — ledger.post (SV-2). Сервис вызывает только его,
в stock_movements/stock_balances напрямую не пишет.
"""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DomainError,
    DuplicateError,
    InsufficientStock,
    NotFoundError,
    ValidationError,
)
from app.modules.documents.models import (
    Acquisition,
    AcquisitionItem,
    Notification,
    NotificationItem,
    Transfer,
    TransferItem,
)
from app.modules.documents.repository import DocumentsRepository
from app.modules.documents.schemas import (
    AcquisitionCreate,
    NotificationCreate,
    NotificationUpdate,
    TransferCreate,
)
from app.modules.stock import ledger
from app.shared.enums import MovementDocType, NotificationStatus
from app.shared.numbering import next_document_number
from app.shared.pagination import PageParams

_ZERO = Decimal("0")


def _fmt(value: Decimal) -> str:
    """Decimal → человекочитаемое число без хвостовых нулей: 10.000 → «10»."""
    d = Decimal(value)
    normalized = d.normalize()
    # normalize() у целых даёт экспоненту (1E+1); format 'f' её разворачивает.
    return format(normalized, "f")


class DocumentsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DocumentsRepository(session)

    # ══════════════════ Уведомления ════════════════════════════════

    async def list_notifications(
        self, params: PageParams, *, filters=None
    ) -> tuple[list[Notification], int]:
        return await self._repo.list_notifications(params, filters=filters)

    async def get_notification_detail(self, notification_id: int) -> Notification:
        """GET /{id}: шапка + строки с вычисленным остатком к приобретению."""
        notif = await self._repo.get_notification_with_items(notification_id)
        if notif is None:
            raise NotFoundError("Уведомление", notification_id)
        purchased = await self._repo.purchased_by_product(notification_id)
        for item in notif.items:
            bought = purchased.get(item.product_id, _ZERO)
            # Проставляем НЕ-колоночные атрибуты на инстанс — их прочитает
            # NotificationItemRead (whitelisted). В БД они не хранятся (ТЗ §3).
            item.qty_purchased = bought
            item.qty_remaining = item.qty_requested - bought
        return notif

    async def create_notification(
        self, *, author_id: int, payload: NotificationCreate
    ) -> Notification:
        product_ids = [i.product_id for i in payload.items]
        if len(set(product_ids)) != len(product_ids):
            # UNIQUE(notification_id, product_id) отбил бы это IntegrityError-ом,
            # но внятный текст лучше 422 из перевода отказа БД.
            raise ValidationError(
                "Товар не должен повторяться в строках одного уведомления",
                code="duplicate_product",
            )

        number = await next_document_number(
            self._session, Notification.number, prefix="NOTIF-"
        )
        notif = Notification(
            number=number,
            date=payload.date,
            author_id=author_id,
            warehouse_id=payload.warehouse_id,
            body_text=payload.body_text,
            division_name=payload.division_name,
            comment=payload.comment,
            items=[
                NotificationItem(product_id=i.product_id, qty_requested=i.qty_requested)
                for i in payload.items
            ],
        )
        self._session.add(notif)
        await self._commit()
        # status/created_at приходят из server_default — дочитываем их.
        await self._session.refresh(notif, ["status", "created_at"])
        return await self.get_notification_detail(notif.id)

    async def submit_notification(self, notification_id: int) -> Notification:
        """draft → in_progress: «завсклад отправил в работу» (ОВ-11).

        Единственный путь из черновика в работу. Раньше это ошибочно делало
        первое приобретение — из-за чего состояние «в работе без приобретений»
        (нужное правилу удаления SV-11) было недостижимо. Теперь переход —
        отдельное явное действие, независимое от закупок.
        """
        notif = await self._session.get(Notification, notification_id)
        if notif is None:
            raise NotFoundError("Уведомление", notification_id)
        if notif.status != NotificationStatus.draft:
            raise ValidationError(
                "Отправить в работу можно только уведомление в статусе «черновик»",
                code="notification_not_draft",
            )
        notif.status = NotificationStatus.in_progress
        await self._commit()
        return await self.get_notification_detail(notif.id)

    async def update_notification(
        self, notification_id: int, payload: NotificationUpdate
    ) -> Notification:
        """PATCH уведомления. Правила зависят от статуса (SV-10).

          * черновик — можно всё (тексты, date, warehouse_id, любые правки строк);
          * в работе — только аддитивно: править тексты, добавлять строки,
            увеличивать qty; ЗАПРЕТ на смену date/warehouse_id, уменьшение qty
            ниже приобретённого, удаление строк с приобретениями;
          * закрыт — любые правки запрещены.
        """
        notif = await self._repo.get_notification_with_items(notification_id)
        if notif is None:
            raise NotFoundError("Уведомление", notification_id)

        if notif.status == NotificationStatus.closed:
            raise ValidationError(
                "Уведомление закрыто — редактирование невозможно",
                code="notification_closed",
            )

        provided = payload.model_fields_set
        is_draft = notif.status == NotificationStatus.draft

        # ── Скалярные поля ──────────────────────────────────────────
        # Тексты правятся в любом открытом статусе (черновик и в работе).
        if "comment" in provided:
            notif.comment = payload.comment
        if "body_text" in provided:
            notif.body_text = payload.body_text
        if "division_name" in provided:
            notif.division_name = payload.division_name

        # date/warehouse_id — только в черновике: в работе приобретения уже
        # могли пойти на старый склад, менять назначение задним числом нельзя.
        if "date" in provided and payload.date != notif.date:
            if not is_draft:
                raise ValidationError(
                    "Дату уведомления можно менять только в черновике",
                    code="notification_field_locked",
                )
            notif.date = payload.date
        if "warehouse_id" in provided and payload.warehouse_id != notif.warehouse_id:
            if not is_draft:
                raise ValidationError(
                    "Склад назначения можно менять только в черновике "
                    "(по уведомлению в работе приобретения уже идут на прежний склад)",
                    code="notification_field_locked",
                )
            notif.warehouse_id = payload.warehouse_id

        # ── Строки ──────────────────────────────────────────────────
        if "items" in provided and payload.items is not None:
            await self._apply_item_changes(notif, payload.items, is_draft=is_draft)

        await self._commit()
        return await self.get_notification_detail(notif.id)

    async def _apply_item_changes(
        self, notif: Notification, desired_items, *, is_draft: bool
    ) -> None:
        """Привести строки уведомления к желаемому состоянию (дифф по product_id).

        В черновике — полная замена. В работе — только аддитивно, с проверками
        против уже приобретённого (SUM acquisition_items под FOR UPDATE).
        """
        desired = {it.product_id: it.qty_requested for it in desired_items}
        if len(desired) != len(desired_items):
            raise ValidationError(
                "Товар не должен повторяться в строках одного уведомления",
                code="duplicate_product",
            )
        if not desired:
            raise ValidationError(
                "Уведомление должно содержать хотя бы одну строку",
                code="empty_items",
            )

        existing = {it.product_id: it for it in notif.items}

        if is_draft:
            # Черновик: приобретений нет по определению — свободная замена.
            for pid, item in list(existing.items()):
                if pid not in desired:
                    notif.items.remove(item)  # delete-orphan удалит строку
            for pid, qty in desired.items():
                if pid in existing:
                    existing[pid].qty_requested = qty
                else:
                    notif.items.append(
                        NotificationItem(product_id=pid, qty_requested=qty)
                    )
            return

        # ── В работе: аддитивные правки под блокировкой строк (SV-1/AP-7) ──
        await self._repo.lock_notification_items(notif.id)
        purchased = await self._repo.purchased_by_product(notif.id)
        affected = set(existing) | set(desired)
        info = await self._repo.product_info(list(affected))

        def _name(pid: int) -> str:
            pi = info.get(pid)
            return pi.name if pi else f"id={pid}"

        # Удаление строки, по которой есть приобретения, — запрещено.
        for pid, item in list(existing.items()):
            if pid not in desired:
                if purchased.get(pid, _ZERO) > _ZERO:
                    raise ValidationError(
                        f'Товар "{_name(pid)}": по строке есть приобретения — '
                        f"удалить её нельзя, пока уведомление в работе",
                        code="item_has_acquisitions",
                    )
                notif.items.remove(item)

        for pid, qty in desired.items():
            bought = purchased.get(pid, _ZERO)
            if pid in existing:
                # Нельзя опустить заявку ниже уже приобретённого по этой строке.
                if qty < bought:
                    unit = info[pid].unit_code if pid in info else ""
                    raise ValidationError(
                        f'Товар "{_name(pid)}": уже приобретено {_fmt(bought)} {unit}, '
                        f"нельзя установить заявку {_fmt(qty)} {unit} ниже приобретённого",
                        code="qty_below_purchased",
                    )
                existing[pid].qty_requested = qty
            else:
                # Новая строка — аддитивно, всегда допустимо (bought=0).
                notif.items.append(
                    NotificationItem(product_id=pid, qty_requested=qty)
                )

    async def delete_notification(self, notification_id: int) -> None:
        """Физическое удаление уведомления — SV-11.

        Разрешено ⟺ у уведомления НЕТ ни одного приобретения. Тогда оно не
        создало ни одного stock_movement и инертно для учёта; удаляется вместе
        со своими notification_items (CASCADE). Это ПЕРВОЕ разрешённое
        физудаление документа: SV-8 (запрет удаления) касается только НСИ.
        """
        notif = await self._session.get(Notification, notification_id)
        if notif is None:
            raise NotFoundError("Уведомление", notification_id)
        if await self._repo.has_acquisitions(notification_id):
            raise ValidationError(
                "Нельзя удалить уведомление: есть связанные приобретения",
                code="notification_has_acquisitions",
            )
        await self._session.delete(notif)
        await self._commit()

    # ══════════════════ Приобретения (SV-1, §5.1) ══════════════════

    async def create_acquisition(
        self, *, author_id: int, payload: AcquisitionCreate
    ) -> Acquisition:
        # 1. Уведомление-основание существует и находится «в работе».
        #    Приобретать можно ТОЛЬКО против in_progress (ОВ-11): против
        #    черновика нельзя (сначала submit), против закрытого — тем более.
        notif = await self._session.get(Notification, payload.notification_id)
        if notif is None:
            raise NotFoundError("Уведомление", payload.notification_id)
        if notif.status == NotificationStatus.closed:
            raise ValidationError(
                "Уведомление закрыто — приобретение по нему невозможно",
                code="notification_closed",
            )
        if notif.status == NotificationStatus.draft:
            raise ValidationError(
                "Уведомление в черновике — отправьте его в работу "
                "(submit) перед приобретением",
                code="notification_not_in_progress",
            )

        # 2. FOR UPDATE на строках уведомления — против TOCTOU (SV-1/AP-7).
        locked = await self._repo.lock_notification_items(notif.id)
        requested = {it.product_id: it.qty_requested for it in locked}

        # 3. Агрегируем строки приобретения по товару (в одном документе товар
        #    может встретиться дважды — считаем суммарно против остатка).
        add_by_product: dict[int, Decimal] = defaultdict(lambda: _ZERO)
        for it in payload.items:
            add_by_product[it.product_id] += it.qty

        unknown = [pid for pid in add_by_product if pid not in requested]
        if unknown:
            raise ValidationError(
                "Товар отсутствует в строках уведомления и не может быть приобретён по нему",
                code="product_not_in_notification",
                details={"product_ids": unknown},
            )

        # 4. Уже приобретено (под блокировкой — значение консистентно).
        purchased = await self._repo.purchased_by_product(notif.id)
        info = await self._repo.product_info(list(requested.keys()))

        # 5. Контроль перезакупки. Текст ошибки СТРОГО по §4.2 ТЗ.
        for pid, add_qty in add_by_product.items():
            already = purchased.get(pid, _ZERO)
            remaining = requested[pid] - already
            if add_qty > remaining:
                name = info[pid].name
                unit = info[pid].unit_code
                raise ValidationError(
                    f'Товар "{name}": остаток к приобретению {_fmt(remaining)} {unit}, '
                    f"невозможно приобрести {_fmt(add_qty)} {unit}",
                    code="overbuy",
                )

        # 6. Вставка документа приобретения.
        number = await next_document_number(
            self._session, Acquisition.number, prefix="ACQ-"
        )
        acq = Acquisition(
            number=number,
            date=payload.date,
            notification_id=notif.id,
            warehouse_id=payload.warehouse_id,
            supplier=payload.supplier,
            author_id=author_id,
            items=[
                AcquisitionItem(product_id=i.product_id, qty=i.qty, price=i.price)
                for i in payload.items
            ],
        )
        self._session.add(acq)
        await self._session.flush()  # нужен acq.id для doc_id движения

        # 7. Приход на склад — только через ledger (§4.2, SV-2).
        for it in payload.items:
            await ledger.post(
                self._session,
                product_id=it.product_id,
                warehouse_id=acq.warehouse_id,
                qty=it.qty,  # приход, знак +
                doc_type=MovementDocType.acquisition,
                doc_id=acq.id,
            )

        # 8. SV-7: автозакрытие, если по ВСЕМ строкам остаток к приобретению = 0.
        all_closed = all(
            purchased.get(pid, _ZERO) + add_by_product.get(pid, _ZERO) >= req
            for pid, req in requested.items()
        )
        # SV-7 только закрывает; перехода draft→in_progress здесь БОЛЬШЕ НЕТ —
        # в работу переводит явный submit (ОВ-11). Сюда доходят лишь in_progress.
        if all_closed:
            notif.status = NotificationStatus.closed

        await self._commit()
        return await self._repo.get_acquisition_with_items(acq.id)

    # ══════════════════ Перемещения (§4.3) ═════════════════════════

    async def create_transfer(
        self, *, author_id: int, payload: TransferCreate
    ) -> Transfer:
        if payload.from_warehouse_id == payload.to_warehouse_id:
            # INV-5 CHECK продублирован здесь ради внятного текста вместо 422/500.
            raise ValidationError(
                "Склад-источник и склад-получатель должны различаться (INV-5)",
                code="same_warehouse",
            )

        number = await next_document_number(
            self._session, Transfer.number, prefix="TRF-"
        )
        transfer = Transfer(
            number=number,
            date=payload.date,
            from_warehouse_id=payload.from_warehouse_id,
            to_warehouse_id=payload.to_warehouse_id,
            author_id=author_id,
            items=[
                TransferItem(product_id=i.product_id, qty=i.qty) for i in payload.items
            ],
        )
        self._session.add(transfer)
        await self._session.flush()  # transfer.id для doc_id

        info = await self._repo.product_info([i.product_id for i in payload.items])

        # §4.3: перемещение = ДВЕ записи ledger с doc_type='transfer'.
        # Порядок «сначала списание, потом приход»: если на источнике не хватает,
        # InsufficientStock срывает транзакцию ДО прихода — приход-без-списания
        # физически невозможен.
        for it in payload.items:
            try:
                await ledger.post(
                    self._session,
                    product_id=it.product_id,
                    warehouse_id=payload.from_warehouse_id,
                    qty=-it.qty,  # списание со склада-источника
                    doc_type=MovementDocType.transfer,
                    doc_id=transfer.id,
                )
            except InsufficientStock as exc:
                # Обогащаем ошибку ledger именем товара (ledger имён не резолвит).
                pi = info.get(it.product_id)
                raise InsufficientStock(
                    product_id=exc.product_id,
                    warehouse_id=exc.warehouse_id,
                    available=exc.available,
                    requested=exc.requested,
                    product_name=pi.name if pi else None,
                ) from exc
            await ledger.post(
                self._session,
                product_id=it.product_id,
                warehouse_id=payload.to_warehouse_id,
                qty=it.qty,  # приход на склад-получатель
                doc_type=MovementDocType.transfer,
                doc_id=transfer.id,
            )

        await self._commit()
        # transfer.items уже в памяти (заданы в Python, id получили при flush);
        # expire_on_commit=False их не сбрасывает — перечитывать нечего.
        return transfer

    # ══════════════════ Общее ══════════════════════════════════════

    async def _commit(self) -> None:
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise _translate_integrity_error(exc) from exc


def _translate_integrity_error(exc: IntegrityError) -> DomainError:
    """Отказ constraint-а → русский текст (архитектура §6), а не 500."""
    text = str(getattr(exc, "orig", exc)).lower()
    if "ck_transfers_different_warehouses" in text:
        return ValidationError(
            "Склад-источник и склад-получатель должны различаться (INV-5)",
            code="same_warehouse",
        )
    if "ck_stock_balances_qty_non_negative" in text:
        # Последний рубеж INV-1: сюда доходить не должны (ledger ловит раньше).
        return ValidationError(
            "Операция увела бы остаток склада в минус", code="negative_balance"
        )
    if "qty_positive" in text or "qty_requested > 0" in text:
        return ValidationError("Количество должно быть больше нуля (INV-6)")
    if "uq_notification_items" in text:
        return ValidationError(
            "Товар не должен повторяться в строках одного уведомления",
            code="duplicate_product",
        )
    if "unique" in text or "duplicate key" in text:
        return DuplicateError("Номер документа", "")
    if "foreign key" in text:
        return ValidationError("Указана несуществующая связанная запись", code="fk_violation")
    if "check constraint" in text:
        return ValidationError("Значения полей нарушают правила учёта")
    return ValidationError("Операция отклонена базой данных")
