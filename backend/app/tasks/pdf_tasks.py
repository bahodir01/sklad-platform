"""Прогрев печатных форм в объектное хранилище (архитектура §8).

    generate_writeoff_pdf    — бланк расхода по заявке (триггер: confirm());
    generate_notification_pdf — бланк BILDIRISHNOMA (триггер: создание уведомления).

Смысл (§8): отрендерить PDF ЗАРАНЕЕ и положить в MinIO по детерминированному
ключу, чтобы «Печать» отдавала готовый файл мгновенно, а не рендерила его в
момент запроса пользователя.

Задачи НЕ дублируют бизнес-логику: рендер+сохранение заявки берётся у
IssuanceService (тот же код, что и в print_request), уведомление рендерится тем
же shared/pdf + templates/pdf/notification.html, что и печать бланка. В БД
задачи НЕ пишут (pdf_url в строке проставляет сам сервис при печати) —
прогрев касается только объектного хранилища, поэтому он безопасен и
идемпотентен: ключ детерминированный (documents/<kind>/<number>.pdf),
повторный прогон перезаписывает тот же объект.

Идемпотентность важна: confirm() может ретраиться, а прогрев одного и того же
документа обязан давать один и тот же объект, а не плодить копии.
"""

import logging
from decimal import Decimal

from app.core.config import settings
from app.tasks.celery_app import celery_app
from app.tasks.runtime import run_async, task_session

logger = logging.getLogger(__name__)


def _fmt_qty(value: Decimal) -> str:
    """Decimal → человекочитаемо без хвостовых нулей (3.000 → «3»)."""
    return format(Decimal(value).normalize(), "f")


# ══════════════════ generate_writeoff_pdf (заявка → бланк расхода) ══════════


@celery_app.task(
    name="tasks.generate_writeoff_pdf",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def generate_writeoff_pdf(self, request_id: int) -> dict:
    """Прогреть PDF бланка расхода по заявке. Триггер — confirm() (§8).

    Переиспользует IssuanceService._render_and_store — тот же рендер и то же
    сохранение в MinIO под ключом documents/requests/<number>.pdf, что и печать.
    """
    try:
        return run_async(_generate_writeoff_pdf(request_id))
    except Exception as exc:  # noqa: BLE001 — прогрев не критичен: ретрай, потом сдаёмся
        logger.warning("generate_writeoff_pdf(%s) не удалась: %s", request_id, exc)
        raise self.retry(exc=exc) from exc


async def _generate_writeoff_pdf(request_id: int) -> dict:
    from app.modules.issuance.service import IssuanceService

    async with task_session() as session:
        svc = IssuanceService(session)
        req = await svc._repo.get_request_with_items(request_id)  # noqa: SLF001
        if req is None:
            logger.info("generate_writeoff_pdf: заявка %s не найдена — пропуск", request_id)
            return {"status": "not_found", "request_id": request_id}
        # Тот же рендер+сохранение, что использует print_request (не дублируем логику).
        pdf_bytes, pdf_url = await svc._render_and_store(req)  # noqa: SLF001
        return {
            "status": "ok",
            "request_id": request_id,
            "number": req.number,
            "object_ref": pdf_url,
            "rendered_pdf": pdf_bytes is not None,  # False → WeasyPrint без нативных зависимостей
        }


# ══════════════════ generate_notification_pdf (BILDIRISHNOMA) ══════════════


@celery_app.task(
    name="tasks.generate_notification_pdf",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def generate_notification_pdf(self, notification_id: int) -> dict:
    """Прогреть PDF бланка уведомления (BILDIRISHNOMA). Триггер — создание (§8)."""
    try:
        return run_async(_generate_notification_pdf(notification_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "generate_notification_pdf(%s) не удалась: %s", notification_id, exc
        )
        raise self.retry(exc=exc) from exc


async def _generate_notification_pdf(notification_id: int) -> dict:
    from app.modules.documents.repository import DocumentsRepository
    from app.shared.pdf import build_org_context, html_to_pdf, render_template
    from app.shared.storage import put_object

    async with task_session() as session:
        repo = DocumentsRepository(session)
        notif = await repo.get_notification_with_items(notification_id)
        if notif is None:
            logger.info(
                "generate_notification_pdf: уведомление %s не найдено — пропуск",
                notification_id,
            )
            return {"status": "not_found", "notification_id": notification_id}

        info = await repo.product_info([it.product_id for it in notif.items])
        items_ctx = [
            {
                "product_name": info[it.product_id].name if it.product_id in info else "?",
                "qty": _fmt_qty(it.qty_requested),
                "unit_code": info[it.product_id].unit_code if it.product_id in info else "",
            }
            for it in notif.items
        ]
        # Тот же шаблон и тот же рендер, что печать бланка (shared/pdf).
        html = render_template(
            "notification.html",
            {"n": notif, "items": items_ctx, "org": build_org_context()},
        )
        pdf_bytes = html_to_pdf(html)

        # Детерминированный ключ (ADR-2a: на бланке номер уведомления) → идемпотентно.
        key = f"notifications/{notif.number}.pdf"
        if pdf_bytes is not None:
            object_ref = put_object(
                settings.s3_bucket_documents,
                key,
                pdf_bytes,
                content_type="application/pdf",
            )
        else:
            # WeasyPrint без нативных pango/cairo — снимок не кладём, ключ фиксируем
            # (как в issuance._render_and_store): печать отрендерит на лету.
            object_ref = f"{settings.s3_bucket_documents}/{key}"
        return {
            "status": "ok",
            "notification_id": notification_id,
            "number": notif.number,
            "object_ref": object_ref,
            "rendered_pdf": pdf_bytes is not None,
        }
