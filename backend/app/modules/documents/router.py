"""Роутер М2 (архитектура §6, все — admin):
  GET,POST /notifications · GET /notifications/{id} · GET /notifications/{id}/pdf
  POST /acquisitions · POST /transfers
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import require_admin
from app.modules.auth.models import User
from app.modules.documents.models import Notification
from app.modules.documents.schemas import (
    AcquisitionCreate,
    AcquisitionRead,
    NotificationCreate,
    NotificationList,
    NotificationRead,
    TransferCreate,
    TransferRead,
)
from app.modules.documents.service import DocumentsService, _fmt
from app.shared.enums import NotificationStatus
from app.shared.pagination import Page, PageParamsDep
from app.shared.pdf import build_org_context, html_to_pdf, render_template

router = APIRouter(tags=["documents"])

EntityId = Annotated[int, Path(ge=1, description="Идентификатор записи")]


# ══════════════════════ notifications ═══════════════════════════════


@router.get(
    "/notifications",
    response_model=Page[NotificationList],
    summary="Список уведомлений",
)
async def list_notifications(
    params: PageParamsDep,
    status_filter: Annotated[NotificationStatus | None, Query(alias="status")] = None,
    warehouse_id: Annotated[int | None, Query(ge=1)] = None,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Page[NotificationList]:
    filters = []
    if status_filter is not None:
        filters.append(Notification.status == status_filter)
    if warehouse_id is not None:
        filters.append(Notification.warehouse_id == warehouse_id)
    items, total = await DocumentsService(session).list_notifications(
        params, filters=filters or None
    )
    return Page.build([NotificationList.model_validate(i) for i in items], total, params)


@router.post(
    "/notifications",
    response_model=NotificationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать уведомление (admin)",
)
async def create_notification(
    payload: NotificationCreate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Notification:
    # author_id проставляется сервером из текущего пользователя (api.create=false).
    return await DocumentsService(session).create_notification(
        author_id=user.id, payload=payload
    )


@router.get(
    "/notifications/{id}",
    response_model=NotificationRead,
    summary="Уведомление + строки с остатком к приобретению",
)
async def get_notification(
    id: EntityId,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Notification:
    return await DocumentsService(session).get_notification_detail(id)


@router.get(
    "/notifications/{id}/pdf",
    summary="PDF-бланк BILDIRISHNOMA (перепечатка безопасна, статус не меняется)",
)
async def notification_pdf(
    id: EntityId,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Response:
    svc = DocumentsService(session)
    notif = await svc.get_notification_detail(id)

    repo = svc._repo  # noqa: SLF001 — читаем справочные имена для бланка
    info = await repo.product_info([it.product_id for it in notif.items])
    items_ctx = [
        {
            "product_name": info[it.product_id].name,
            "qty": _fmt(it.qty_requested),
            "unit_code": info[it.product_id].unit_code,
        }
        for it in notif.items
    ]
    html = render_template(
        "notification.html", {"n": notif, "items": items_ctx, "org": build_org_context()}
    )

    pdf = html_to_pdf(html)
    if pdf is not None:
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{notif.number}.pdf"'
            },
        )
    # WeasyPrint недоступен в этом окружении: отдаём готовый к печати HTML
    # (его всё равно можно распечатать из браузера) и честно помечаем заголовком,
    # что PDF не сформирован. Прод-конфиг при этом не ломается.
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"X-PDF-Renderer": "unavailable-html-fallback"},
    )


# ══════════════════════ acquisitions ════════════════════════════════


@router.post(
    "/acquisitions",
    response_model=AcquisitionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Провести приобретение (admin, SV-1 контроль перезакупки)",
)
async def create_acquisition(
    payload: AcquisitionCreate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AcquisitionRead:
    acq = await DocumentsService(session).create_acquisition(
        author_id=user.id, payload=payload
    )
    return AcquisitionRead.model_validate(acq)


# ══════════════════════ transfers ═══════════════════════════════════


@router.post(
    "/transfers",
    response_model=TransferRead,
    status_code=status.HTTP_201_CREATED,
    summary="Провести перемещение (admin, две записи ledger, SV-3)",
)
async def create_transfer(
    payload: TransferCreate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> TransferRead:
    transfer = await DocumentsService(session).create_transfer(
        author_id=user.id, payload=payload
    )
    return TransferRead.model_validate(transfer)