"""Бизнес-правила М4: статусная машина заявки и выдача. Транзакция открывается
здесь (архитектура §2).

Статусная машина (§5.3, ADR-2):

    draft ──confirm()──► to_print ──print()──► printed ──issue()──► issued
      │                     │                     │                    │
   сотрудник           очередь завсклада      PDF + подпись        writeoff +
   заполняет           (бейдж AP-3)           на бумаге            ledger.post(−)

Переходы только вперёд и только нужной ролью; откат вне scope (ТЗ §11).

issue() — САМОЕ ОПАСНОЕ место системы (§5.3). Порядок операций строго по
02-database.md §7.1 / архитектуре §5.3, и переставлять его НЕЛЬЗЯ:
INV-2 (`status='issued'` ⟺ `writeoff_id IS NOT NULL`) — немедленный CHECK (в
PostgreSQL не может быть DEFERRABLE), поэтому статус и writeoff_id обязаны
меняться ОДНИМ оператором UPDATE. Защита от двойного списания — в условии
`WHERE status='printed'` этого же UPDATE (SV-5), не в проверке перед ним.
"""

import datetime as dt

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    ConflictError,
    DomainError,
    DuplicateError,
    InsufficientStock,
    NotFoundError,
    ValidationError,
)
from app.modules.auth.models import User
from app.modules.catalog.models import ExpenseType, Warehouse
from app.modules.issuance.models import Request, RequestItem, Writeoff, WriteoffItem
from app.modules.issuance.repository import IssuanceRepository
from app.modules.issuance.schemas import RequestCreate, WriteoffCreate
from app.modules.stock import ledger
from app.shared.enums import CatalogStatus, MovementDocType, RequestStatus
from app.shared.numbering import next_document_number
from app.shared.pagination import PageParams

_REQUEST_PREFIX = "REQ-"
_WRITEOFF_PREFIX = "WOFF-"


class IssuanceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = IssuanceRepository(session)

    # ══════════════════ Форма заявки (сотрудник) ════════════════════

    async def create_request(
        self, *, employee_id: int, payload: RequestCreate
    ) -> Request:
        """POST /requests — черновик. employee_id из current_user (сервер).

        SV-9: заявку можно подать только со склада allows_issuance=true AND
        status='active'. Проверяем здесь (внятный текст) и в триггере БД
        requests_check_issuance_warehouse (последний рубеж).
        """
        warehouse = await self._session.get(Warehouse, payload.warehouse_id)
        if warehouse is None:
            raise NotFoundError("Склад", payload.warehouse_id)
        if warehouse.status != CatalogStatus.active:
            raise ValidationError(
                "Склад архивирован — подать заявку с него нельзя",
                code="warehouse_archived",
            )
        if not warehouse.allows_issuance:
            # SV-9 / AP-12: только «склад списания».
            raise ValidationError(
                "С этого склада нельзя подавать заявки: он не отмечен как склад "
                "списания (SV-9)",
                code="warehouse_not_issuance",
            )

        number = await next_document_number(
            self._session, Request.number, prefix=_REQUEST_PREFIX
        )
        req = Request(
            number=number,
            employee_id=employee_id,
            warehouse_id=payload.warehouse_id,
            reason=payload.reason,
            items=[
                RequestItem(product_id=i.product_id, qty=i.qty) for i in payload.items
            ],
        )
        self._session.add(req)
        await self._commit()
        # status/created_at приходят из server_default — дочитываем.
        await self._session.refresh(req, ["status", "created_at"])
        return await self._repo.get_request_with_items(req.id)

    async def confirm_request(self, *, request_id: int, employee_id: int) -> Request:
        """POST /requests/{id}/confirm (draft→to_print), только владелец-сотрудник.

        Row-level (§1.3): подтвердить может лишь автор заявки. Переход — условным
        UPDATE, чтобы повторный клик/гонка не двигали статус дважды.
        """
        req = await self._repo.get_request(request_id)
        if req is None:
            raise NotFoundError("Заявка", request_id)
        if req.employee_id != employee_id:
            # Row-level отказ формулируем как 404, чтобы не раскрывать чужие id.
            raise NotFoundError("Заявка", request_id)

        result = await self._session.execute(
            update(Request)
            .where(
                Request.id == request_id,
                Request.status == RequestStatus.draft,
                Request.employee_id == employee_id,
            )
            .values(status=RequestStatus.to_print)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            raise ConflictError(
                "Заявку можно подтвердить только из черновика",
                code="invalid_transition",
            )
        await self._commit()
        return await self._reload(request_id)

    # ══════════════════ Очередь «К печати» (admin) ══════════════════

    async def list_to_print(self, params: PageParams) -> tuple[list[Request], int]:
        return await self._repo.list_requests(
            params, filters=[Request.status == RequestStatus.to_print]
        )

    async def count_to_print(self) -> int:
        return await self._repo.count_requests(
            filters=[Request.status == RequestStatus.to_print]
        )

    async def list_my(
        self, params: PageParams, *, employee_id: int
    ) -> tuple[list[Request], int]:
        """GET /requests/my — row-level: ТОЛЬКО заявки текущего сотрудника (§1.3).

        Фильтр по employee_id живёт в сервисе, а не только в UI: сотрудник не
        должен видеть чужие заявки, даже обращаясь к эндпоинту напрямую.
        """
        return await self._repo.list_requests(
            params, filters=[Request.employee_id == employee_id]
        )

    async def print_request(self, *, request_id: int) -> tuple[Request, bytes | None]:
        """POST /requests/{id}/print (to_print→printed), admin.

        ОВ-3: статус «Напечатан» ставит завскладом ЯВНО — открытие PDF ≠ факт
        печати. Перепечатка безопасна: из printed снова в printed, printed_at не
        затирается. Возвращает (заявка, pdf_bytes|None) — байты для ответа с
        файлом, роутер решает про MinIO/фолбэк.
        """
        req = await self._repo.get_request_with_items(request_id)
        if req is None:
            raise NotFoundError("Заявка", request_id)
        if req.status not in (RequestStatus.to_print, RequestStatus.printed):
            raise ConflictError(
                "Печать доступна только для заявок в очереди «К печати»",
                code="invalid_transition",
            )

        pdf_bytes, pdf_url = await self._render_and_store(req)

        result = await self._session.execute(
            update(Request)
            .where(
                Request.id == request_id,
                Request.status.in_([RequestStatus.to_print, RequestStatus.printed]),
            )
            .values(
                status=RequestStatus.printed,
                # printed_at — только при первой печати; перепечатка не затирает.
                printed_at=func.coalesce(Request.printed_at, func.now()),
                pdf_url=pdf_url,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:  # pragma: no cover — статус проверен выше
            raise ConflictError("Заявка недоступна для печати", code="invalid_transition")
        await self._commit()
        return await self._reload(request_id), pdf_bytes

    async def batch_print(self, *, ids: list[int]) -> tuple[list[int], list[int]]:
        """POST /requests/batch-print — печать очереди пачкой (§6.3).

        Не в наличии/не в статусе — попадают в skipped, а не рушат всю пачку.
        Каждая заявка печатается своей транзакцией (одна плохая не откатит
        остальные).
        """
        printed: list[int] = []
        skipped: list[int] = []
        for rid in ids:
            try:
                await self.print_request(request_id=rid)
                printed.append(rid)
            except DomainError:
                skipped.append(rid)
        return printed, skipped

    # ══════════════════ Выдача — issue() (§5.3, ADR-3) ══════════════

    async def issue_request(
        self, *, request_id: int, author_id: int
    ) -> tuple[Request, Writeoff]:
        """POST /requests/{id}/issue (printed→issued), admin. НЕОБРАТИМО.

        Порядок операций КРИТИЧЕН — см. модульный docstring и §5.3:
          1. INSERT writeoffs (проводка рождается ПЕРВОЙ) + writeoff_items;
          2. ledger.post(−qty) по каждой строке (может упасть InsufficientStock);
          3. UPDATE requests SET status='issued', issued_at, writeoff_id ОДНИМ
             оператором WHERE id=? AND status='printed' (INV-2 + SV-5);
          4. rowcount=0 → Conflict → ROLLBACK (проводка и списание откатятся).
        """
        req = await self._repo.get_request_with_items(request_id)
        if req is None:
            raise NotFoundError("Заявка", request_id)
        # Предварительная проверка статуса — только ради внятной ошибки на явно
        # невыданной заявке; НАСТОЯЩАЯ защита от гонки — в WHERE ниже (SV-5).
        if req.status != RequestStatus.printed:
            raise ConflictError(
                "Выдать можно только напечатанную заявку", code="invalid_transition"
            )

        expense_type = await self._repo.issuance_expense_type()
        if expense_type is None:
            raise ValidationError(
                "Не настроен активный тип расхода «Выдача» (requires_employee=true)",
                code="issuance_type_missing",
            )

        # ── 1. Проводка рождается ПЕРВОЙ ────────────────────────────
        number = await next_document_number(
            self._session, Writeoff.number, prefix=_WRITEOFF_PREFIX
        )
        writeoff = Writeoff(
            number=number,
            date=dt.date.today(),
            warehouse_id=req.warehouse_id,
            expense_type_id=expense_type.id,
            # Копия флага (Д-2): при «Выдаче» requires_employee=true, значит
            # employee_id обязателен — INV-4 CHECK выполнен.
            requires_employee=expense_type.requires_employee,
            employee_id=req.employee_id,
            author_id=author_id,
            items=[
                WriteoffItem(product_id=it.product_id, qty=it.qty, reason=None)
                for it in req.items
            ],
        )
        self._session.add(writeoff)
        await self._session.flush()  # writeoff.id для doc_id движения

        # ── 2. Списание — ТОЛЬКО через ledger (§5.2, SV-2). Расход, знак − ──
        info = await self._repo.product_info([it.product_id for it in req.items])
        for it in req.items:
            try:
                await ledger.post(
                    self._session,
                    product_id=it.product_id,
                    warehouse_id=req.warehouse_id,
                    qty=-it.qty,
                    doc_type=MovementDocType.writeoff,
                    doc_id=writeoff.id,
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

        # ── 3. Статус + связка ОДНИМ оператором (INV-2 немедленный CHECK) ──
        # Условие status='printed' ВНУТРИ UPDATE (SV-5): два параллельных
        # issue() → второй получит rowcount=0. issued_at, status, writeoff_id
        # меняются вместе — «выдано без проводки» не существует ни на миг.
        result = await self._session.execute(
            update(Request)
            .where(Request.id == request_id, Request.status == RequestStatus.printed)
            .values(
                status=RequestStatus.issued,
                issued_at=func.now(),
                writeoff_id=writeoff.id,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            # Гонка/повтор: другой issue() уже перевёл заявку. Откатываем ВСЮ
            # транзакцию — осиротевшая проводка и её списание уходят вместе с ней.
            await self._session.rollback()
            raise ConflictError(
                "Заявка уже выдана или не находится в статусе «Напечатана»",
                code="already_issued",
            )

        await self._commit()

        await self._session.refresh(
            req, ["status", "issued_at", "writeoff_id", "pdf_url", "printed_at"]
        )
        return req, writeoff

    # ══════════════════ Порча / брак — прямое списание (ЭТАП 4) ═════

    async def create_writeoff(
        self, *, author_id: int, payload: WriteoffCreate
    ) -> Writeoff:
        """POST /writeoffs (admin) — прямое списание порча/брак БЕЗ заявки (§4.4).

        В отличие от выдачи (issue(), этап 3) здесь нет статусов, печати и подписи:
        проводка создаётся СРАЗУ и списывает немедленно через ledger.post(−qty).
        Порча и брак могут случиться на ЛЮБОМ складе — ограничение allows_issuance
        (SV-9) на них НЕ распространяется (ТЗ §3 М1), склад не проверяем на этот флаг.

        Инварианты, закрытые здесь и продублированные в БД:
          * тип расхода — только requires_employee=false (Порча/Брак). Тип
            «Выдача» (requires_employee=true) отклоняется: выдача идёт лишь через
            заявку (этап 3);
          * INV-4: при requires_employee=false сотрудник запрещён (employee_id=NULL).
            Составной FK + CHECK ck_writeoffs_employee_iff_required — последний рубеж.
        """
        expense_type = await self._session.get(ExpenseType, payload.expense_type_id)
        if expense_type is None:
            raise NotFoundError("Тип расхода товара", payload.expense_type_id)
        if expense_type.status != CatalogStatus.active:
            raise ValidationError(
                "Тип расхода архивирован — списание по нему невозможно",
                code="expense_type_archived",
            )

        # Тип «Выдача» через этот эндпоинт запрещён — только через заявку (этап 3).
        if expense_type.requires_employee:
            raise ValidationError(
                "Тип расхода «Выдача» проводится только через заявку сотрудника "
                "(этап 3), а не прямым списанием",
                code="issuance_via_request",
            )

        # INV-4 в сервисе (внятный текст): при порче/браке сотрудника не указывают.
        if payload.employee_id is not None:
            raise ValidationError(
                "При «Порче»/«Браке» сотрудник-получатель не указывается (INV-4)",
                code="employee_forbidden",
            )

        number = await next_document_number(
            self._session, Writeoff.number, prefix=_WRITEOFF_PREFIX
        )
        writeoff = Writeoff(
            number=number,
            date=payload.date,
            warehouse_id=payload.warehouse_id,
            expense_type_id=expense_type.id,
            # Копия флага (Д-2): requires_employee=false ⇒ employee_id обязан быть
            # NULL, что и требует INV-4. Клиент это поле не присылает (api.create=false).
            requires_employee=expense_type.requires_employee,
            employee_id=None,
            author_id=author_id,
            items=[
                WriteoffItem(product_id=i.product_id, qty=i.qty, reason=i.reason)
                for i in payload.items
            ],
        )
        self._session.add(writeoff)
        await self._session.flush()  # writeoff.id для doc_id движения

        # Списание — ТОЛЬКО через ledger (§5.2, SV-2). Немедленно, знак −.
        info = await self._repo.product_info([i.product_id for i in payload.items])
        for it in payload.items:
            try:
                await ledger.post(
                    self._session,
                    product_id=it.product_id,
                    warehouse_id=payload.warehouse_id,
                    qty=-it.qty,
                    doc_type=MovementDocType.writeoff,
                    doc_id=writeoff.id,
                )
            except InsufficientStock as exc:
                pi = info.get(it.product_id)
                raise InsufficientStock(
                    product_id=exc.product_id,
                    warehouse_id=exc.warehouse_id,
                    available=exc.available,
                    requested=exc.requested,
                    product_name=pi.name if pi else None,
                ) from exc

        await self._commit()
        return await self._session.scalar(
            select(Writeoff)
            .where(Writeoff.id == writeoff.id)
            .options(selectinload(Writeoff.items))
            .execution_options(populate_existing=True)
        )

    # ══════════════════ Реестр выданных (§6.4) ══════════════════════

    async def registry(
        self, params: PageParams
    ) -> tuple[list[tuple[Request, Writeoff]], int]:
        return await self._repo.registry(params)

    # ══════════════════ Чтение / PDF ════════════════════════════════

    async def get_own_request(self, *, request_id: int, employee_id: int) -> Request:
        req = await self._repo.get_request_with_items(request_id)
        if req is None or req.employee_id != employee_id:
            raise NotFoundError("Заявка", request_id)
        return req

    async def build_pdf(self, *, request_id: int) -> tuple[Request, bytes | None, str]:
        """Данные и HTML/PDF бланка расхода для GET /{id}/pdf.

        Возвращает (заявка, pdf_bytes|None, html). Перепечатка статус не меняет.
        """
        req = await self._repo.get_request_with_items(request_id)
        if req is None:
            raise NotFoundError("Заявка", request_id)
        html = await self._render_html(req)
        from app.shared.pdf import html_to_pdf  # локальный импорт: ленивый WeasyPrint

        return req, html_to_pdf(html), html

    # ── бланк расхода (заглушка ОВ-1б, поля §6.4) ───────────────────

    async def _render_html(self, req: Request) -> str:
        from app.shared.pdf import build_org_context, render_template

        employee = await self._session.get(User, req.employee_id)
        warehouse = await self._session.get(Warehouse, req.warehouse_id)
        info = await self._repo.product_info([it.product_id for it in req.items])
        items_ctx = [
            {
                "product_name": info[it.product_id].name if it.product_id in info else "?",
                "qty": _fmt(it.qty),
                "unit_code": info[it.product_id].unit_code if it.product_id in info else "",
            }
            for it in req.items
        ]
        return render_template(
            "writeoff.html",
            {
                "r": req,
                "employee": employee,
                "warehouse": warehouse,
                "items": items_ctx,
                "org": build_org_context(),
            },
        )

    async def _render_and_store(self, req: Request) -> tuple[bytes | None, str]:
        """Рендер бланка + снимок в MinIO (документы) с локальным фолбэком.

        Ключ объекта ``documents/requests/<number>.pdf`` → pdf_url (ADR-2a: на
        бумаге номер ЗАЯВКИ). Если WeasyPrint недоступен — снимок не кладём, но
        ключ фиксируем: GET /{id}/pdf отрендерит на лету.
        """
        from app.core.config import settings
        from app.shared.pdf import html_to_pdf
        from app.shared.storage import put_object

        html = await self._render_html(req)
        pdf_bytes = html_to_pdf(html)
        key = f"requests/{req.number}.pdf"
        if pdf_bytes is not None:
            pdf_url = put_object(
                settings.s3_bucket_documents,
                key,
                pdf_bytes,
                content_type="application/pdf",
            )
        else:
            # Снимок не сформирован (нет нативных pango/cairo) — фиксируем ключ.
            pdf_url = f"{settings.s3_bucket_documents}/{key}"
        return pdf_bytes, pdf_url

    # ══════════════════ Общее ═══════════════════════════════════════

    async def _reload(self, request_id: int) -> Request:
        """Свежая заявка со строками после условного UPDATE (populate_existing:
        синхронизируем in-session объект с БД, а не отдаём устаревший из карты)."""
        return await self._session.scalar(
            select(Request)
            .where(Request.id == request_id)
            .options(selectinload(Request.items))
            .execution_options(populate_existing=True)
        )

    async def _commit(self) -> None:
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise _translate_integrity_error(exc) from exc


def _fmt(value) -> str:
    """Decimal → человекочитаемое число без хвостовых нулей: 3.000 → «3»."""
    from decimal import Decimal

    return format(Decimal(value).normalize(), "f")


def _translate_integrity_error(exc: IntegrityError) -> DomainError:
    """Отказ constraint-а/триггера → русский текст (архитектура §6), а не 500."""
    text = str(getattr(exc, "orig", exc)).lower()
    if "requests_check_issuance_warehouse" in text or "allows_issuance" in text:
        return ValidationError(
            "С этого склада нельзя подавать заявки: он не отмечен как склад "
            "списания (SV-9)",
            code="warehouse_not_issuance",
        )
    if "ck_requests_issued_iff_posted" in text:
        # Сюда доходить не должны: issue() меняет status и writeoff_id одним
        # оператором. Если всплыло — это баг порядка операций, не данные.
        return ValidationError(
            "Нарушен инвариант INV-2 (выдана ⟺ есть проводка)", code="inv2_violated"
        )
    if "uq_requests_writeoff_id" in text:
        return ConflictError(
            "Эта проводка уже привязана к другой заявке (INV-3)", code="writeoff_taken"
        )
    if "ck_requests_reason_not_blank" in text:
        return ValidationError("Обоснование не может быть пустым", code="reason_blank")
    if "ck_writeoffs_employee_iff_required" in text:
        return ValidationError(
            "Для типа расхода «Выдача» обязателен сотрудник-получатель (INV-4)",
            code="employee_required",
        )
    if "qty_positive" in text:
        return ValidationError("Количество должно быть больше нуля (INV-6)")
    if "ck_stock_balances_qty_non_negative" in text:
        return ValidationError(
            "Операция увела бы остаток склада в минус", code="negative_balance"
        )
    if "unique" in text or "duplicate key" in text:
        return DuplicateError("Номер документа", "")
    if "foreign key" in text:
        return ValidationError("Указана несуществующая связанная запись", code="fk_violation")
    return ValidationError("Операция отклонена базой данных")
