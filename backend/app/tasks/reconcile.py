"""reconcile_stock — ночной ревизор остатков (архитектура §8, ADR-1).

Beat, ежедневно 03:00. Сверяет денормализованную проекцию ``stock_balances`` с
её источником правды ``SUM(stock_movements)`` по каждому (product, warehouse).
При расхождении — лог/алерт (ADR-1: «регламентная задача-ревизор сверяет и
алертит при расхождении»).

Задача СТРОГО read-only: ничего не пишет и НЕ «чинит» баланс. Правило SV-2 —
единственный писатель остатков это ledger.post(); автоправка расхождения здесь
затёрла бы симптом реальной проблемы (баг в транзакции, ручное вмешательство в
БД). Задача обязана только обнаружить и громко сообщить — решение принимает
человек. Идемпотентна по построению (чистое чтение).

Расхождением считается ЛЮБОЙ из случаев:
  * баланс есть, сумма движений отличается (проекция разошлась с журналом);
  * есть движения, но строки баланса нет (проекция потеряла позицию);
  * есть строка баланса с qty≠0, но движений по ней нет (фантомный остаток).
FULL OUTER JOIN покрывает все три разом.
"""

import logging

from sqlalchemy import text

from app.tasks.celery_app import celery_app
from app.tasks.runtime import run_async, task_session

logger = logging.getLogger(__name__)

# COALESCE(...,0) с обеих сторон: NULL из внешнего JOIN приравниваем к нулю,
# иначе «нет строки» ложно прошло бы фильтр как совпадение или как расхождение.
_RECONCILE_SQL = text(
    """
    SELECT COALESCE(b.product_id,   m.product_id)   AS product_id,
           COALESCE(b.warehouse_id, m.warehouse_id) AS warehouse_id,
           COALESCE(b.qty, 0)     AS balance_qty,
           COALESCE(m.total, 0)   AS movements_sum
    FROM stock_balances b
    FULL OUTER JOIN (
        SELECT product_id, warehouse_id, SUM(qty) AS total
        FROM stock_movements
        GROUP BY product_id, warehouse_id
    ) m ON b.product_id = m.product_id AND b.warehouse_id = m.warehouse_id
    WHERE COALESCE(b.qty, 0) <> COALESCE(m.total, 0)
    ORDER BY product_id, warehouse_id
    """
)


async def compute_discrepancies(session) -> tuple[int, list[dict]]:
    """Сверить stock_balances с SUM(stock_movements) НА ПЕРЕДАННОЙ сессии.

    Единственное место с логикой сверки — переиспользуется и ночной задачей
    reconcile_stock (на своём task_session), и read-only эндпоинтом админ-панели
    GET /admin/alerts (на request-сессии). Дублирования нет: кто вызвал — тот и
    владеет сессией/транзакцией; функция только читает.

    :returns: (checked_pairs, discrepancies), где discrepancies — список dict
        с ключами product_id, warehouse_id, balance_qty, movements_sum, delta
        (Decimal → str, JSON-сериализуемо).
    """
    checked_pairs = await session.scalar(text("SELECT count(*) FROM stock_balances"))
    rows = (await session.execute(_RECONCILE_SQL)).all()
    discrepancies = [
        {
            "product_id": r.product_id,
            "warehouse_id": r.warehouse_id,
            # Decimal → str: точность сохраняется, JSON-сериализуемо.
            "balance_qty": str(r.balance_qty),
            "movements_sum": str(r.movements_sum),
            "delta": str(r.balance_qty - r.movements_sum),
        }
        for r in rows
    ]
    return int(checked_pairs or 0), discrepancies


@celery_app.task(name="tasks.reconcile_stock", bind=True)
def reconcile_stock(self) -> dict:
    """Сверить stock_balances с SUM(stock_movements). Вернуть сводку.

    Возвращает dict (JSON-сериализуемый для result backend):
      { checked_pairs, discrepancy_count, discrepancies: [...] }.
    Помимо возврата — пишет алерт в лог на каждое расхождение (ADR-1).
    """
    return run_async(_reconcile_stock())


async def _reconcile_stock() -> dict:
    async with task_session() as session:
        checked_pairs, discrepancies = await compute_discrepancies(session)

    if discrepancies:
        # Алерт (ADR-1). ERROR-уровень → уходит в сборщик логов/алертинг.
        logger.error(
            "reconcile_stock: обнаружено расхождений остатков: %d. "
            "stock_balances разошлась с SUM(stock_movements) — требуется разбор.",
            len(discrepancies),
        )
        for d in discrepancies:
            logger.error(
                "  РАСХОЖДЕНИЕ product_id=%s warehouse_id=%s: "
                "баланс=%s, сумма движений=%s, дельта=%s",
                d["product_id"],
                d["warehouse_id"],
                d["balance_qty"],
                d["movements_sum"],
                d["delta"],
            )
    else:
        logger.info(
            "reconcile_stock: расхождений нет (проверено пар product/warehouse: %d).",
            checked_pairs or 0,
        )

    return {
        "checked_pairs": int(checked_pairs or 0),
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies,
    }
