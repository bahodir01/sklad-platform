"""Бизнес-правила М4: статусная машина заявки, выдача и пакетная подпись.
Транзакция открывается здесь (архитектура §2).

Статусная машина (спека13 §2, ADR-2) — фича 13 расцепила выдачу и подпись:

    draft ─confirm()─► to_issue ─issue()─► issued ─mark_signed()─► signed ─submit()─► submitted
      │                   │                   │                        │                   │
   сотрудник        очередь «К выдаче»    товар выдан,           подписи собраны       передано
   заполняет                             СПИСАН со склада        пачкой                в бухгалтерию
                                         (ledger.post −qty)

Ключевое изменение фичи 13 (спека §1): списание товара — на переходе
to_issue → issued (в момент физической выдачи учителю), НЕ на печати. Печать и
подпись собираются ПОЗЖE пачкой (signature_batches) и статус выдачи не двигают.

issue() — САМОЕ ОПАСНОЕ место системы. Порядок операций строго по
02-database.md §7.1 и переставлять его НЕЛЬЗЯ: INV-2 (спека §2:
`status IN ('issued','signed','submitted')` ⟺ `writeoff_id IS NOT NULL`) —
немедленный CHECK (в PostgreSQL не может быть DEFERRABLE), поэтому статус и
writeoff_id обязаны меняться ОДНИМ оператором UPDATE. Защита от двойного
списания — в условии `WHERE status='to_issue'` этого же UPDATE (SV-5), не в
проверке перед ним.
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
from app.modules.issuance.models import (
    Request,
    RequestItem,
    SignatureBatch,
    Writeoff,
    WriteoffItem,
)
from app.modules.issuance.repository import IssuanceRepository
from app.modules.issuance.schemas import RequestCreate, WriteoffCreate
from app.modules.stock import ledger
from app.shared.enums import CatalogStatus, MovementDocType, RequestStatus
from app.shared.numbering import next_document_number
from app.shared.pagination import PageParams

_REQUEST_PREFIX = "REQ-"
_WRITEOFF_PREFIX = "WOFF-"
_BATCH_PREFIX = "BATCH-"
_REGISTER_PREFIX = "REG-"  # реестр передачи товара (спека13 §4)


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
        """POST /requests/{id}/confirm (draft→to_issue), только владелец-сотрудник.

        Спека13 §2: подтверждение ставит заявку в очередь «К выдаче» завсклада.
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
            .values(status=RequestStatus.to_issue)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            raise ConflictError(
                "Заявку можно подтвердить только из черновика",
                code="invalid_transition",
            )
        await self._commit()
        return await self._reload(request_id)

    # ══════════════════ Фильтр-карточки экрана (admin, спека13 §5) ═══

    async def list_by_status(
        self, params: PageParams, *, status: RequestStatus
    ) -> tuple[list[Request], int]:
        return await self._repo.list_requests(
            params, filters=[Request.status == status]
        )

    async def count_by_status(self, *, status: RequestStatus) -> int:
        return await self._repo.count_requests(filters=[Request.status == status])

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

    # ══════════════════ Выдача — issue() (спека13 §2) ═══════════════

    async def issue_request(
        self, *, request_id: int, author_id: int
    ) -> tuple[Request, Writeoff]:
        """POST /requests/{id}/issue (to_issue→issued), admin. НЕОБРАТИМО.

        Спека13 §1-§2: СПИСАНИЕ ТОВАРА ЗДЕСЬ — в момент физической выдачи учителю.
        Порядок операций КРИТИЧЕН — см. модульный docstring:
          1. INSERT writeoffs (проводка рождается ПЕРВОЙ) + writeoff_items;
          2. ledger.post(−qty) по каждой строке (может упасть InsufficientStock);
          3. UPDATE requests SET status='issued', issued_at, writeoff_id ОДНИМ
             оператором WHERE id=? AND status='to_issue' (INV-2 + SV-5);
          4. rowcount=0 → Conflict → ROLLBACK (проводка и списание откатятся).
        """
        req = await self._repo.get_request_with_items(request_id)
        if req is None:
            raise NotFoundError("Заявка", request_id)
        # Предварительная проверка статуса — только ради внятной ошибки; НАСТОЯЩАЯ
        # защита от гонки — в WHERE ниже (SV-5).
        if req.status != RequestStatus.to_issue:
            raise ConflictError(
                "Выдать можно только заявку из очереди «К выдаче»",
                code="invalid_transition",
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
        # Условие status='to_issue' ВНУТРИ UPDATE (SV-5): два параллельных
        # issue() → второй получит rowcount=0. issued_at, status, writeoff_id
        # меняются вместе — «выдано без проводки» не существует ни на миг.
        result = await self._session.execute(
            update(Request)
            .where(Request.id == request_id, Request.status == RequestStatus.to_issue)
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
                "Заявка уже выдана или не находится в статусе «К выдаче»",
                code="already_issued",
            )

        await self._commit()

        await self._session.refresh(
            req, ["status", "issued_at", "writeoff_id", "pdf_url", "printed_at"]
        )
        return req, writeoff

    # ══════════════════ Пачка печати (admin, спека13 §3) ════════════

    async def batch_print(
        self, *, ids: list[int], created_by: int
    ) -> tuple[SignatureBatch, list[int], list[int], bool]:
        """POST /requests/batch-print — печать пачкой (спека13 §3).

        Из списка берутся заявки в статусе 'issued' (не-issued → skipped, не рушат
        пачку). Создаётся signature_batches (серверный номер), выбранным ставится
        batch_id + printed_at (признак «напечатано» = batch_id IS NOT NULL). СТАТУС
        НЕ МЕНЯЕТСЯ. Генерируется ОДИН PDF, сгруппированный по сотрудникам.

        Возвращает (пачка, printed[], skipped[], rendered_pdf).
        """
        # FOR UPDATE по выбранным issued-заявкам — сериализация с issue()/подписью.
        locked = await self._repo.lock_issued_requests(ids)
        printed_ids = [r.id for r in locked]
        skipped_ids = [i for i in ids if i not in set(printed_ids)]
        if not printed_ids:
            raise ConflictError(
                "В пачку не попала ни одна заявка: нужны заявки в статусе «К подписи»",
                code="empty_batch",
            )

        # Период пачки = диапазон дат выдачи вошедших заявок (CHECK from <= to).
        issued_dates = [r.issued_at.date() for r in locked if r.issued_at is not None]
        period_from = min(issued_dates) if issued_dates else dt.date.today()
        period_to = max(issued_dates) if issued_dates else dt.date.today()

        number = await next_document_number(
            self._session, SignatureBatch.number, prefix=_BATCH_PREFIX
        )
        batch = SignatureBatch(
            number=number,
            period_from=period_from,
            period_to=period_to,
            created_by=created_by,
            printed_at=func.now(),
        )
        self._session.add(batch)
        await self._session.flush()  # batch.id

        # Признак «напечатано»: batch_id + printed_at на выбранных. Статус НЕ трогаем.
        await self._session.execute(
            update(Request)
            .where(Request.id.in_(printed_ids), Request.status == RequestStatus.issued)
            .values(batch_id=batch.id, printed_at=func.coalesce(Request.printed_at, func.now()))
            .execution_options(synchronize_session=False)
        )

        # Один PDF по сотрудникам → в MinIO, ключ в batch.pdf_url.
        pdf_bytes, pdf_url = await self._render_and_store_batch(batch.id, number)
        batch.pdf_url = pdf_url

        await self._commit()
        await self._session.refresh(batch)
        return batch, printed_ids, skipped_ids, pdf_bytes is not None

    async def mark_signed(self, *, ids: list[int]) -> tuple[list[int], list[int]]:
        """POST /requests/mark-signed — issued → signed пачкой (спека13 §3).

        Клиент присылает id, которые ДЕЙСТВИТЕЛЬНО подписаны; исключённые (снятая
        галочка) в список не попадают и остаются issued (вернутся в следующую
        пачку). Условие status='issued' в UPDATE защищает от гонок/повторов.
        Пачкам подписанных заявок ставится signed_at.
        """
        if not ids:
            return [], []
        # FOR UPDATE + условный UPDATE issued → signed.
        locked = await self._repo.lock_issued_requests(ids)
        signed_ids = [r.id for r in locked]
        skipped_ids = [i for i in ids if i not in set(signed_ids)]
        if not signed_ids:
            return [], skipped_ids

        batch_ids = {r.batch_id for r in locked if r.batch_id is not None}

        await self._session.execute(
            update(Request)
            .where(Request.id.in_(signed_ids), Request.status == RequestStatus.issued)
            .values(status=RequestStatus.signed)
            .execution_options(synchronize_session=False)
        )
        # Отметка «Пачка подписана»: signed_at на затронутых пачках.
        if batch_ids:
            await self._session.execute(
                update(SignatureBatch)
                .where(
                    SignatureBatch.id.in_(batch_ids),
                    SignatureBatch.signed_at.is_(None),
                )
                .values(signed_at=func.now())
                .execution_options(synchronize_session=False)
            )
        await self._commit()
        return signed_ids, skipped_ids

    async def submit_to_accounting(
        self, *, ids: list[int]
    ) -> tuple[str | None, list[int], list[int]]:
        """POST /requests/submit-to-accounting — signed → submitted (спека13 §4).

        Общий submitted_register_no на весь вызов (один номер реестра передачи),
        submitted_at = сегодня. Исключённые (не в списке / не signed) не трогаются.
        Условие status='signed' в UPDATE защищает от повторной передачи.
        """
        if not ids:
            return None, [], []
        # FOR UPDATE по signed-заявкам из списка.
        locked = await self._session.scalars(
            select(Request)
            .where(Request.id.in_(ids), Request.status == RequestStatus.signed)
            .order_by(Request.id)
            .with_for_update()
        )
        submit_ids = [r.id for r in locked]
        skipped_ids = [i for i in ids if i not in set(submit_ids)]
        if not submit_ids:
            return None, [], skipped_ids

        register_no = await next_document_number(
            self._session, Request.submitted_register_no, prefix=_REGISTER_PREFIX
        )
        await self._session.execute(
            update(Request)
            .where(Request.id.in_(submit_ids), Request.status == RequestStatus.signed)
            .values(
                status=RequestStatus.submitted,
                submitted_at=dt.date.today(),
                submitted_register_no=register_no,
            )
            .execution_options(synchronize_session=False)
        )
        await self._commit()
        return register_no, submit_ids, skipped_ids

    # ══════════════════ Порча / брак — прямое списание (ЭТАП 4) ═════

    async def create_writeoff(
        self, *, author_id: int, payload: WriteoffCreate
    ) -> Writeoff:
        """POST /writeoffs (admin) — прямое списание порча/брак БЕЗ заявки (§4.4).

        В отличие от выдачи (issue()) здесь нет статусов, печати и подписи:
        проводка создаётся СРАЗУ и списывает немедленно через ledger.post(−qty).
        Порча и брак могут случиться на ЛЮБОМ складе — ограничение allows_issuance
        (SV-9) на них НЕ распространяется (ТЗ §3 М1), склад не проверяем на этот флаг.

        Инварианты, закрытые здесь и продублированные в БД:
          * тип расхода — только requires_employee=false (Порча/Брак). Тип
            «Выдача» (requires_employee=true) отклоняется: выдача идёт лишь через
            заявку;
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

        # Тип «Выдача» через этот эндпоинт запрещён — только через заявку.
        if expense_type.requires_employee:
            raise ValidationError(
                "Тип расхода «Выдача» проводится только через заявку сотрудника, "
                "а не прямым списанием",
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

    # ══════════════════ Реестр передачи (спека13 §4) ════════════════

    async def registry(
        self,
        params: PageParams,
        *,
        register_no: str | None = None,
        date: dt.date | None = None,
    ) -> tuple[list[tuple[Request, Writeoff]], int]:
        """Реестр переданного в бухгалтерию по register_no / дате (спека13 §4)."""
        filters: list = []
        if register_no:
            filters.append(Request.submitted_register_no == register_no)
        if date:
            filters.append(Request.submitted_at == date)
        return await self._repo.registry(params, filters=filters or None)

    # ══════════════════ Чтение / PDF ════════════════════════════════

    async def get_own_request(self, *, request_id: int, employee_id: int) -> Request:
        req = await self._repo.get_request_with_items(request_id)
        if req is None or req.employee_id != employee_id:
            raise NotFoundError("Заявка", request_id)
        return req

    async def build_pdf(self, *, request_id: int) -> tuple[Request, bytes | None, str]:
        """Данные и HTML/PDF бланка расхода одной заявки (GET /{id}/pdf).

        Перепечать копии из истории (спека13 §5, экран «Передано»)."""
        req = await self._repo.get_request_with_items(request_id)
        if req is None:
            raise NotFoundError("Заявка", request_id)
        html = await self._render_html(req)
        from app.shared.pdf import html_to_pdf  # локальный импорт: ленивый WeasyPrint

        return req, html_to_pdf(html), html

    async def build_batch_pdf(
        self, *, batch_id: int
    ) -> tuple[SignatureBatch, bytes | None, str]:
        """GET /requests/batches/{id}/pdf — один PDF пачки по сотрудникам."""
        batch = await self._repo.get_batch(batch_id)
        if batch is None:
            raise NotFoundError("Пачка подписи", batch_id)
        html = await self._render_batch_html(batch)
        from app.shared.pdf import html_to_pdf

        return batch, html_to_pdf(html), html

    # ── бланк расхода одной заявки (заглушка ОВ-1б, поля §6.4) ───────

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

    # ── ОДИН бланк пачки, сгруппированный по сотрудникам (спека13 §3) ──

    async def _render_batch_html(self, batch: SignatureBatch) -> str:
        from app.shared.pdf import build_org_context, render_template

        detail = await self._repo.batch_requests_detail(batch.id)
        # Собираем строки-товары для резолва ЕИ одним запросом.
        all_pids = [
            it.product_id for req, _fn, _cat in detail for it in req.items
        ]
        info = await self._repo.product_info(all_pids)

        # Группировка по сотруднику: раздел листа на человека (спека13 §3).
        sections: list[dict] = []
        current: dict | None = None
        for req, full_name, category in detail:
            if current is None or current["employee_id"] != req.employee_id:
                current = {
                    "employee_id": req.employee_id,
                    "employee_full_name": full_name,
                    "employee_category": category.value if category else "—",
                    "requests": [],
                }
                sections.append(current)
            current["requests"].append(
                {
                    "number": req.number,
                    "reason": req.reason,
                    "lines": [
                        {
                            "product_name": info[it.product_id].name
                            if it.product_id in info
                            else "?",
                            "qty": _fmt(it.qty),
                            "unit_code": info[it.product_id].unit_code
                            if it.product_id in info
                            else "",
                        }
                        for it in req.items
                    ],
                }
            )
        return render_template(
            "signature_batch.html",
            {"batch": batch, "sections": sections, "org": build_org_context()},
        )

    async def _render_and_store(self, req: Request) -> tuple[bytes | None, str]:
        """Рендер бланка одной заявки + снимок в MinIO с локальным фолбэком.

        Ключ ``requests/<number>.pdf`` (ADR-2a: на бумаге номер ЗАЯВКИ) → pdf_url.
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
            pdf_url = f"{settings.s3_bucket_documents}/{key}"
        return pdf_bytes, pdf_url

    async def _render_and_store_batch(
        self, batch_id: int, number: str
    ) -> tuple[bytes | None, str]:
        """Рендер ОДНОГО бланка пачки по сотрудникам + снимок в MinIO.

        Ключ ``batches/<number>.pdf``. Если WeasyPrint недоступен — снимок не
        кладём, но ключ фиксируем: GET /batches/{id}/pdf отрендерит на лету.
        """
        from app.core.config import settings
        from app.shared.pdf import html_to_pdf
        from app.shared.storage import put_object

        batch = await self._repo.get_batch(batch_id)
        html = await self._render_batch_html(batch)
        pdf_bytes = html_to_pdf(html)
        key = f"batches/{number}.pdf"
        if pdf_bytes is not None:
            pdf_url = put_object(
                settings.s3_bucket_documents,
                key,
                pdf_bytes,
                content_type="application/pdf",
            )
        else:
            pdf_url = f"{settings.s3_bucket_documents}/{key}"
        return pdf_bytes, pdf_url

    # ══════════════════ Общее ═══════════════════════════════════════

    async def _reload(self, request_id: int) -> Request:
        """Свежая заявка со строками после условного UPDATE (populate_existing)."""
        return await self._repo.get_request_with_items(
            request_id, populate_existing=True
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
    if "ck_signature_batches_period_order" in text:
        return ValidationError(
            "Период пачки некорректен (начало позже конца)", code="batch_period_order"
        )
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
