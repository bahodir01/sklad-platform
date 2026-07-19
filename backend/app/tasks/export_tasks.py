"""export_report — асинхронная выгрузка отчёта в файл (архитектура §8, §6 ТЗ).

Тяжёлый экспорт (десятки тысяч строк истории/ДДС) синхронно блокировал бы
uvicorn-воркер. Этап 6 (04-backend-stage6.md §2) уже подготовил шов: сбор
данных (`ReportsService.build_*_table`) отделён от генерации файла
(`exporters.export_table`, чистая функция ReportTable→bytes). Эта задача просто
соединяет их в фоне и кладёт байты в объектное хранилище:

    table   = await service.build_<report>_table(**filters)   # сбор данных
    result  = export_table(table, fmt)                          # генерация файла
    put_object(bucket, key, result.content)                     # → MinIO/фолбэк

Функции ниже НЕ переписаны — вынос в Celery оказался тривиальным ровно потому,
что этап 6 их так и спроектировал. Скачивание — по ключу объекта: роутер отдаёт
presigned URL (или стрим из хранилища в локальном режиме).

Потолок EXPORT_ROW_CAP (settings.export_row_cap) снимает риск «миллион строк в
память воркера»: сверх потолка выгрузка усекается с явной пометкой в итогах.
"""

import datetime as dt
import logging

from app.core.config import settings
from app.tasks.celery_app import celery_app
from app.tasks.runtime import run_async, task_session

logger = logging.getLogger(__name__)

_VALID_REPORTS = ("balances", "unpurchased", "movements", "cashflow")
_VALID_FORMATS = ("xlsx", "pdf")


def _parse_date(value):
    return dt.date.fromisoformat(value) if value else None


@celery_app.task(
    name="tasks.export_report",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
)
def export_report(self, report: str, fmt: str, filters: dict | None = None) -> dict:
    """Собрать отчёт, сгенерировать файл, положить в хранилище.

    :param report: один из balances|unpurchased|movements|cashflow.
    :param fmt: xlsx|pdf.
    :param filters: dict фильтров (даты — ISO-строки, enum — их value).
    :returns: {object_ref, filename, media_type, bytes, truncated}.
    """
    if report not in _VALID_REPORTS:
        raise ValueError(f"Неизвестный отчёт: {report!r}")
    if fmt not in _VALID_FORMATS:
        raise ValueError(f"Неизвестный формат экспорта: {fmt!r}")
    try:
        return run_async(_export_report(report, fmt, filters or {}))
    except Exception as exc:  # noqa: BLE001
        logger.warning("export_report(%s, %s) не удалась: %s", report, fmt, exc)
        raise self.retry(exc=exc) from exc


async def _build_table(report: str, filters: dict):
    from app.modules.reports.service import ReportsService
    from app.shared.enums import MovementDocType, UserCategory

    async with task_session() as session:
        svc = ReportsService(session)
        if report == "balances":
            return await svc.build_balances_table(
                warehouse_id=filters.get("warehouse_id"),
                product_id=filters.get("product_id"),
                unit_id=filters.get("unit_id"),
            )
        if report == "unpurchased":
            return await svc.build_unpurchased_table(
                notification_id=filters.get("notification_id"),
                product_id=filters.get("product_id"),
                date_from=_parse_date(filters.get("date_from")),
                date_to=_parse_date(filters.get("date_to")),
            )
        if report == "movements":
            dt_ = filters.get("doc_type")
            return await svc.build_movements_table(
                product_id=filters.get("product_id"),
                warehouse_id=filters.get("warehouse_id"),
                doc_type=MovementDocType(dt_) if dt_ else None,
                date_from=_parse_date(filters.get("date_from")),
                date_to=_parse_date(filters.get("date_to")),
            )
        # cashflow — категория обязательна (§8.2/AP-8).
        category = filters.get("category")
        if not category:
            raise ValueError("Для ДДС обязателен фильтр category (teacher|worker)")
        return await svc.build_cashflow_table(
            category=UserCategory(category),
            expense_category_id=filters.get("expense_category_id"),
            employee_id=filters.get("employee_id"),
            date_from=_parse_date(filters.get("date_from")),
            date_to=_parse_date(filters.get("date_to")),
        )


async def _export_report(report: str, fmt: str, filters: dict) -> dict:
    from app.modules.reports.exporters import export_table
    from app.shared.storage import put_object

    table = await _build_table(report, filters)

    # Потолок строк: сверх лимита усекаем и честно помечаем — не тянем миллионы
    # строк в память воркера.
    truncated = False
    cap = settings.export_row_cap
    if len(table.rows) > cap:
        table.rows = table.rows[:cap]
        table.summary = list(table.summary) + [
            ("⚠ Выгрузка усечена", f"показаны первые {cap} строк(и)")
        ]
        truncated = True

    result = export_table(table, fmt)  # чистая функция ReportTable → bytes

    key = f"{settings.s3_bucket_exports_prefix}/{result.filename}"
    object_ref = put_object(
        settings.s3_bucket_documents,
        key,
        result.content,
        content_type=result.media_type,
    )
    logger.info(
        "export_report: %s.%s готов (%d байт%s) → %s",
        report,
        fmt,
        len(result.content),
        ", усечён" if truncated else "",
        object_ref,
    )
    return {
        "status": "ok",
        "report": report,
        "format": fmt,
        "object_ref": object_ref,
        "filename": result.filename,
        "media_type": result.media_type,
        "bytes": len(result.content),
        "truncated": truncated,
    }
