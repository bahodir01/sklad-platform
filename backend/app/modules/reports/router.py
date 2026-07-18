"""Роутер М6 «Отчётность» (архитектура §6, все эндпоинты — admin):

  GET /reports/balances    — §8.1.1 остатки в реальном времени (AP-10)
  GET /reports/unpurchased — §8.1.2 недокупленное по уведомлениям (AP-6)
  GET /reports/movements   — §8.1.3 история движений, keyset (AP-5)
  GET /reports/cashflow    — §8.2   ДДС, фильтр по категории обязателен (AP-8)

Каждый отчёт: ?format=json|xlsx|pdf (ТЗ §8.1.1/§8.2). json — типизированный
ответ; xlsx/pdf — файл, сгенерированный из тех же данных (exporters.export_table).
Генерация вынесена в отдельную функцию (не в роутере) ради тривиального выноса в
Celery — см. docstring exporters.py.
"""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.exceptions import ValidationError
from app.core.security import require_admin
from app.modules.reports.exporters import ExportResult, export_table
from app.modules.reports.schemas import (
    BalanceReportRow,
    CashflowReport,
    MovementReportPage,
    UnpurchasedReportRow,
)
from app.modules.reports.service import ReportsService
from app.shared.enums import MovementDocType, UserCategory
from app.shared.pagination import Page, PageParamsDep

router = APIRouter(tags=["reports"], dependencies=[Depends(require_admin)])

ReportFormat = Literal["json", "xlsx", "pdf"]


def _file_response(result: ExportResult) -> Response:
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"'
        },
    )


# ══════════════════════ §8.1.1 Остатки (AP-10) ══════════════════════


@router.get("/reports/balances", response_model=None, summary="Остатки в реальном времени (AP-10)")
async def report_balances(
    params: PageParamsDep,
    warehouse_id: Annotated[int | None, Query(ge=1)] = None,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    unit_id: Annotated[int | None, Query(ge=1, description="Ед. измерения товара")] = None,
    format: ReportFormat = "json",
    session: AsyncSession = Depends(get_session),
) -> Page[BalanceReportRow] | Response:
    svc = ReportsService(session)
    if format == "json":
        rows, total = await svc.list_balances(
            params, warehouse_id=warehouse_id, product_id=product_id, unit_id=unit_id
        )
        return Page.build(
            [BalanceReportRow.model_validate(r) for r in rows], total, params
        )
    table = await svc.build_balances_table(
        warehouse_id=warehouse_id, product_id=product_id, unit_id=unit_id
    )
    return _file_response(export_table(table, format))


# ══════════════════════ §8.1.2 Недокупленное (AP-6) ═════════════════


@router.get("/reports/unpurchased", response_model=None, summary="Недокупленное по уведомлениям (AP-6)")
async def report_unpurchased(
    params: PageParamsDep,
    notification_id: Annotated[int | None, Query(ge=1)] = None,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    date_from: Annotated[dt.date | None, Query(description="Дата уведомления, с")] = None,
    date_to: Annotated[dt.date | None, Query(description="Дата уведомления, по")] = None,
    format: ReportFormat = "json",
    session: AsyncSession = Depends(get_session),
) -> Page[UnpurchasedReportRow] | Response:
    svc = ReportsService(session)
    if format == "json":
        rows, total = await svc.list_unpurchased(
            params,
            notification_id=notification_id,
            product_id=product_id,
            date_from=date_from,
            date_to=date_to,
        )
        return Page.build(
            [UnpurchasedReportRow.model_validate(r) for r in rows], total, params
        )
    table = await svc.build_unpurchased_table(
        notification_id=notification_id,
        product_id=product_id,
        date_from=date_from,
        date_to=date_to,
    )
    return _file_response(export_table(table, format))


# ══════════════════════ §8.1.3 История движений (AP-5) ══════════════


@router.get("/reports/movements", response_model=None, summary="История движений, keyset-пагинация (AP-5)")
async def report_movements(
    cursor: Annotated[str | None, Query(description="Курсор следующей страницы")] = None,
    limit: Annotated[int, Query(ge=1, le=settings.page_size_max)] = settings.page_size_default,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    warehouse_id: Annotated[int | None, Query(ge=1)] = None,
    doc_type: Annotated[MovementDocType | None, Query()] = None,
    date_from: Annotated[dt.date | None, Query()] = None,
    date_to: Annotated[dt.date | None, Query()] = None,
    format: ReportFormat = "json",
    session: AsyncSession = Depends(get_session),
) -> MovementReportPage | Response:
    svc = ReportsService(session)
    if format == "json":
        try:
            items, next_cursor = await svc.list_movements(
                limit=limit,
                cursor=cursor,
                product_id=product_id,
                warehouse_id=warehouse_id,
                doc_type=doc_type,
                date_from=date_from,
                date_to=date_to,
            )
        except ValueError as exc:  # битый курсор
            raise ValidationError(str(exc), code="bad_cursor") from exc
        return MovementReportPage(items=items, next_cursor=next_cursor, limit=limit)
    # Экспорт истории отдаёт весь отфильтрованный набор (под потолком EXPORT_ROW_CAP),
    # курсор для файла не нужен.
    table = await svc.build_movements_table(
        product_id=product_id,
        warehouse_id=warehouse_id,
        doc_type=doc_type,
        date_from=date_from,
        date_to=date_to,
    )
    return _file_response(export_table(table, format))


# ══════════════════════ §8.2 ДДС (AP-8) ═════════════════════════════


@router.get("/reports/cashflow", response_model=None, summary="ДДС — фильтр по категории обязателен (AP-8)")
async def report_cashflow(
    params: PageParamsDep,
    # §8.2/AP-8: фильтр по категории ОБЯЗАТЕЛЕН (teacher|worker) → касса категории.
    category: Annotated[UserCategory, Query(description="Категория/касса, ОБЯЗАТЕЛЬНО")],
    expense_category_id: Annotated[int | None, Query(ge=1, description="Вид расхода денег")] = None,
    employee_id: Annotated[int | None, Query(ge=1, description="Сотрудник")] = None,
    date_from: Annotated[dt.date | None, Query()] = None,
    date_to: Annotated[dt.date | None, Query()] = None,
    format: ReportFormat = "json",
    session: AsyncSession = Depends(get_session),
) -> CashflowReport | Response:
    svc = ReportsService(session)
    if format == "json":
        return await svc.cashflow(
            params,
            category=category,
            expense_category_id=expense_category_id,
            employee_id=employee_id,
            date_from=date_from,
            date_to=date_to,
        )
    table = await svc.build_cashflow_table(
        category=category,
        expense_category_id=expense_category_id,
        employee_id=employee_id,
        date_from=date_from,
        date_to=date_to,
    )
    return _file_response(export_table(table, format))
