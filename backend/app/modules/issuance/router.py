"""Роутер М4 (архитектура §6). Статусная машина заявки + очередь печати.

Доступ:
  teacher/worker: POST /requests, POST /requests/{id}/confirm, GET /requests/my
  admin:          GET /requests?status=to_print, GET /requests/count,
                  POST /{id}/print, POST /{id}/issue, GET /{id}/pdf,
                  POST /requests/batch-print, GET /requests/registry

ВАЖНО о порядке маршрутов: статические пути (/requests/my, /requests/count,
/requests/registry, /requests/batch-print) объявлены ДО динамического
/requests/{id}/..., иначе FastAPI попытался бы разобрать "my"/"count" как {id}.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import ConflictError
from app.core.security import require_admin, require_role
from app.modules.auth.models import User
from app.modules.auth.tokens import get_redis
from app.modules.issuance.schemas import (
    BatchPrintRequest,
    BatchPrintResult,
    IssueResult,
    RegistryRow,
    RequestCount,
    RequestCreate,
    RequestList,
    RequestRead,
    WriteoffCreate,
    WriteoffRead,
)
from app.modules.issuance.models import Request
from app.modules.issuance.service import IssuanceService
from app.shared.enums import RequestStatus, UserRole
from app.shared.pagination import Page, PageParamsDep

router = APIRouter(tags=["issuance"])

EntityId = Annotated[int, Path(ge=1, description="Идентификатор заявки")]

# Заявку подаёт/подтверждает сотрудник (teacher|worker); admin делами склада не
# подменяет сотрудника — заявка это его документ (§1.3).
require_employee = require_role(UserRole.teacher, UserRole.worker)

# TTL идемпотентности issue() — короткий: он гасит лишь ретрай сети/двойной клик.
_IDEMPOTENCY_TTL_SECONDS = 60 * 10


# ══════════════════════ Сотрудник ═══════════════════════════════════


@router.post(
    "/requests",
    response_model=RequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать заявку (черновик; teacher/worker)",
)
async def create_request(
    payload: RequestCreate,
    user: User = Depends(require_employee),
    session: AsyncSession = Depends(get_session),
) -> RequestRead:
    # employee_id — сервер из current_user (api.create=false; SV-9 по складу).
    req = await IssuanceService(session).create_request(
        employee_id=user.id, payload=payload
    )
    return RequestRead.model_validate(req)


@router.post(
    "/requests/{id}/confirm",
    response_model=RequestRead,
    summary="Подтвердить заявку (draft→to_print; только владелец)",
)
async def confirm_request(
    id: EntityId,
    user: User = Depends(require_employee),
    session: AsyncSession = Depends(get_session),
) -> RequestRead:
    req = await IssuanceService(session).confirm_request(
        request_id=id, employee_id=user.id
    )
    return RequestRead.model_validate(req)


@router.get(
    "/requests/my",
    response_model=Page[RequestList],
    summary="Мои заявки (row-level: только свои, §1.3)",
)
async def my_requests(
    params: PageParamsDep,
    user: User = Depends(require_employee),
    session: AsyncSession = Depends(get_session),
) -> Page[RequestList]:
    items, total = await IssuanceService(session).list_my(params, employee_id=user.id)
    return Page.build([RequestList.model_validate(i) for i in items], total, params)


# ══════════════════════ Завсклад (admin) ════════════════════════════


@router.get(
    "/requests/count",
    response_model=RequestCount,
    summary="Счётчик очереди «К печати» (бейдж, AP-3)",
)
async def requests_count(
    status_filter: Annotated[RequestStatus, Query(alias="status")] = RequestStatus.to_print,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> RequestCount:
    # Бейдж считает только очередь печати; иные статусы бейджем не отслеживаются.
    if status_filter != RequestStatus.to_print:
        return RequestCount(count=0)
    return RequestCount(count=await IssuanceService(session).count_to_print())


@router.get(
    "/requests/registry",
    response_model=Page[RegistryRow],
    summary="Реестр выданных: ОБА номера — заявки и проводки (§6.4, ADR-2a)",
)
async def requests_registry(
    params: PageParamsDep,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Page[RegistryRow]:
    rows, total = await IssuanceService(session).registry(params)
    items = [
        RegistryRow(
            request_id=r.id,
            request_number=r.number,
            writeoff_id=w.id,
            writeoff_number=w.number,
            employee_id=r.employee_id,
            warehouse_id=r.warehouse_id,
            issued_at=r.issued_at,
            writeoff_date=w.date,
        )
        for r, w in rows
    ]
    return Page.build(items, total, params)


@router.post(
    "/requests/batch-print",
    response_model=BatchPrintResult,
    summary="Пакетная печать очереди (§6.3)",
)
async def batch_print(
    payload: BatchPrintRequest,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> BatchPrintResult:
    printed, skipped = await IssuanceService(session).batch_print(ids=payload.ids)
    return BatchPrintResult(printed=printed, skipped=skipped)


@router.get(
    "/requests",
    response_model=Page[RequestList],
    summary="Очередь «К печати» (admin, AP-2)",
)
async def list_requests(
    params: PageParamsDep,
    status_filter: Annotated[RequestStatus, Query(alias="status")] = RequestStatus.to_print,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Page[RequestList]:
    # Очередь — status='to_print' (AP-2). Иные статусы админ смотрит через реестр.
    svc = IssuanceService(session)
    if status_filter == RequestStatus.to_print:
        items, total = await svc.list_to_print(params)
    else:
        items, total = await svc._repo.list_requests(  # noqa: SLF001
            params, filters=[Request.status == status_filter]
        )
    return Page.build([RequestList.model_validate(i) for i in items], total, params)


@router.post(
    "/requests/{id}/print",
    response_model=RequestRead,
    summary="Отметить напечатанной (to_print→printed, admin, ОВ-3)",
)
async def print_request(
    id: EntityId,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> RequestRead:
    req, _pdf = await IssuanceService(session).print_request(request_id=id)
    return RequestRead.model_validate(req)


@router.post(
    "/requests/{id}/issue",
    response_model=IssueResult,
    summary="Выдать товар: проводка + списание (printed→issued, admin)",
)
async def issue_request(
    id: EntityId,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> IssueResult:
    """POST /requests/{id}/issue — необратимая выдача (§5.3).

    Идемпотентность (архитектура §6): при наличии Idempotency-Key ретрай сети /
    двойной клик по «Выдано» отсекается через Redis ДО входа в транзакцию. Если
    Redis недоступен — гарантию единственного списания даёт условие
    `WHERE status='printed'` внутри UPDATE (SV-5): второй issue() получит
    rowcount=0 и Conflict. Redis лишь экономит поход в БД на явном ретрае.
    """
    redis_guard_key = f"idem:issue:{id}:{idempotency_key}" if idempotency_key else None
    if redis_guard_key is not None:
        try:
            # SET NX: первый запрос занимает ключ, повторный — отбивается.
            acquired = await get_redis().set(redis_guard_key, "1", nx=True, ex=_IDEMPOTENCY_TTL_SECONDS)
            if not acquired:
                raise ConflictError(
                    "Повторная выдача по тому же Idempotency-Key отклонена",
                    code="idempotency_replay",
                )
        except ConflictError:
            raise
        except Exception:  # noqa: BLE001 — Redis недоступен: полагаемся на SV-5
            redis_guard_key = None

    try:
        req, writeoff = await IssuanceService(session).issue_request(
            request_id=id, author_id=user.id
        )
    except Exception:
        # Операция не прошла — освобождаем ключ, чтобы законный повтор был возможен.
        if redis_guard_key is not None:
            try:
                await get_redis().delete(redis_guard_key)
            except Exception:  # noqa: BLE001
                pass
        raise

    return IssueResult(
        request=RequestRead.model_validate(req),
        writeoff=WriteoffRead.model_validate(writeoff),
    )


# ══════════════════ Порча / брак — прямое списание (ЭТАП 4) ═════════


@router.post(
    "/writeoffs",
    response_model=WriteoffRead,
    status_code=status.HTTP_201_CREATED,
    summary="Прямое списание порча/брак БЕЗ заявки (admin, §4.4)",
)
async def create_writeoff(
    payload: WriteoffCreate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> WriteoffRead:
    """POST /writeoffs — только порча/брак (requires_employee=false). Выдача
    (requires_employee=true) отклоняется: она создаётся через issue() (этап 3).

    author_id — сервер из current_user; number/requires_employee — сервер.
    Списывает немедленно через ledger.post(−qty), без статусов и печати.
    """
    writeoff = await IssuanceService(session).create_writeoff(
        author_id=user.id, payload=payload
    )
    return WriteoffRead.model_validate(writeoff)


@router.get(
    "/requests/{id}/pdf",
    summary="PDF бланка расхода (номер ЗАЯВКИ, ADR-2a; перепечатка безопасна)",
)
async def request_pdf(
    id: EntityId,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Response:
    req, pdf, html = await IssuanceService(session).build_pdf(request_id=id)
    if pdf is not None:
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{req.number}.pdf"'},
        )
    # WeasyPrint недоступен: отдаём готовый к печати HTML, честно помечая заголовком.
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"X-PDF-Renderer": "unavailable-html-fallback"},
    )
