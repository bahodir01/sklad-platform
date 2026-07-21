"""Роутер М7 «Администрирование»: уведомления админ-панели (только admin).

  GET /admin/alerts — текущие алерты, собранные НА ЛЕТУ из состояния системы.

Решение заказчика (Q3, 19.07.2026): канал алертов регламентных задач —
«уведомление внутри админ-панели». Схема заморожена, таблицы уведомлений НЕТ и
не добавляем. Поэтому строки-уведомления не хранятся, а выводятся read-only:

  1. stock_discrepancy — та же сверка, что ночная задача reconcile_stock
     (stock_balances ↔ SUM(stock_movements)); переиспользуется
     tasks.reconcile.compute_discrepancies. Пустой список = всё сходится (ADR-1).
  2. income_draft — неподтверждённые черновики пополнения касс, которые кладёт
     задача monthly_income_draft (артефакты drafts/income/*.json, posted=false);
     переиспользуется tasks.income.list_income_draft_alerts (§7.2).

Эндпоинт идемпотентен и без побочных эффектов: только читает. Логику
reconcile/income НЕ дублирует — вызывает те же функции.

Производительность. Фронт дёргает эндпоинт периодически (как бейдж «К печати»).
Сверка остатков — тот же FULL OUTER JOIN + GROUP BY, что ночью; на текущем
масштабе укладывается в бюджет, покрыта индексом на (product_id, warehouse_id).
Если станет горячо — кэш в Redis с TTL 30–60 c поверх этого же вызова снимет
нагрузку без изменения контракта (см. отчёт .feature-dev/08-celery-tasks.md).
Чтение черновиков — считанные мелкие JSON в месяц.
"""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import require_admin
from app.modules.admin.schemas import IntegrationRead, IntegrationUpdate
from app.modules.admin.service import IntegrationService
from app.modules.auth.models import User

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])

AlertType = Literal["stock_discrepancy", "income_draft"]
AlertSeverity = Literal["critical", "warning", "info"]


class AdminAlert(BaseModel):
    """Один алерт для панели уведомлений админа."""

    type: AlertType
    severity: AlertSeverity
    title: str
    detail: str
    # ── Полезная нагрузка stock_discrepancy ─────────────────────────
    product_id: int | None = None
    warehouse_id: int | None = None
    balance: str | None = Field(default=None, description="Остаток в проекции stock_balances")
    computed: str | None = Field(default=None, description="SUM(stock_movements) по журналу")
    delta: str | None = None
    # ── Полезная нагрузка income_draft ──────────────────────────────
    period: str | None = None
    object_ref: str | None = None


class AdminAlertsResponse(BaseModel):
    alerts: list[AdminAlert]
    count: int = Field(description="Число алертов — фронт показывает бейджем")


@router.get(
    "/admin/alerts",
    response_model=AdminAlertsResponse,
    summary="Текущие алерты админ-панели (расхождения остатков + черновики пополнения)",
)
async def admin_alerts(
    session: AsyncSession = Depends(get_session),
) -> AdminAlertsResponse:
    # Ленивый импорт (как в reports router): не тянуть Celery в API-процесс на
    # старте — только при первом обращении к эндпоинту.
    from app.tasks.income import list_income_draft_alerts
    from app.tasks.reconcile import compute_discrepancies

    alerts: list[AdminAlert] = []

    # 1. Расхождения остатков (ADR-1) — та же логика, что reconcile_stock.
    _checked, discrepancies = await compute_discrepancies(session)
    for d in discrepancies:
        alerts.append(
            AdminAlert(
                type="stock_discrepancy",
                severity="critical",
                title="Расхождение остатка склада",
                detail=(
                    f"Товар #{d['product_id']}, склад #{d['warehouse_id']}: "
                    f"остаток {d['balance_qty']}, по журналу движений "
                    f"{d['movements_sum']} (дельта {d['delta']}). Требуется разбор."
                ),
                product_id=d["product_id"],
                warehouse_id=d["warehouse_id"],
                balance=d["balance_qty"],
                computed=d["movements_sum"],
                delta=d["delta"],
            )
        )

    # 2. Черновики пополнения касс (§7.2) — неподтверждённые артефакты.
    for draft in list_income_draft_alerts():
        period = draft.get("period", "?")
        alerts.append(
            AdminAlert(
                type="income_draft",
                severity="warning",
                title=f"Пора пополнить кассы за {period}",
                detail=(
                    "Сформирован черновик ежемесячного пополнения. Приход НЕ "
                    "проведён автоматически (§7.2) — подтвердите вручную: "
                    "POST /api/v1/cash/income."
                ),
                period=period,
                object_ref=draft.get("object_ref"),
            )
        )

    return AdminAlertsResponse(alerts=alerts, count=len(alerts))


# ══════════════════════ М7 «Интеграции» (спека15 §5а) ═══════════════
#
# Единое место внешних ключей: Telegram-бот и ИИ-поиск товара, по одной
# строке в integration_settings на kind (модель — modules/admin/models.py,
# миграция 0004, обе строки засеяны выключенными). Секрет — только зашифрован
# (shared/crypto.py, ключ INTEGRATION_SECRET_KEY из .env) и никогда не
# возвращается в открытом виде — GET отдаёт masked_secret.


@router.get(
    "/admin/integrations",
    response_model=list[IntegrationRead],
    summary="Список интеграций (telegram, ai_search) — секрет только маской",
)
async def list_integrations(
    session: AsyncSession = Depends(get_session),
) -> list[IntegrationRead]:
    return await IntegrationService(session).list_all()


@router.put(
    "/admin/integrations/{kind}",
    response_model=IntegrationRead,
    summary=(
        "Сохранить и проверить секрет интеграции — telegram: getMe перед "
        "сохранением (невалидный токен → 422, не сохраняется); ai_search: "
        "проверка формата ключа"
    ),
)
async def update_integration(
    kind: str,
    payload: IntegrationUpdate,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> IntegrationRead:
    return await IntegrationService(session).update_secret(
        kind, payload.secret, admin_id=user.id
    )


@router.post(
    "/admin/integrations/{kind}/disable",
    response_model=IntegrationRead,
    summary="Отключить интеграцию (секрет НЕ стирается — повторный PUT включит заново)",
)
async def disable_integration(
    kind: str,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> IntegrationRead:
    return await IntegrationService(session).disable(kind, admin_id=user.id)
