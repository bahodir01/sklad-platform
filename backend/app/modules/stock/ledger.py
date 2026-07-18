"""СЕРДЦЕ СИСТЕМЫ. Единая точка записи движений товара (ADR-1, SV-2, §5.2).

Это ЕДИНСТВЕННЫЙ модуль во всей системе, которому разрешено писать в
``stock_movements`` и ``stock_balances``. Все документы (приобретение,
перемещение, выдача, порча/брак) вызывают только ``ledger.post()`` и никогда
не трогают эти две таблицы напрямую. Так остаток гарантированно остаётся
проекцией журнала, а не вторым независимым источником правды.

Контракт функции (архитектура §5.2):

    post(session, product_id, warehouse_id, qty: Decimal(±), doc_type, doc_id)
      1. гарантировать существование строки баланса (product, wh) без гонки;
      2. SELECT qty ... FOR UPDATE — сериализация конкурентных списаний (SV-3);
      3. если balance + qty < 0 → InsufficientStock (ДО вставки, не CHECK-ом);
      4. INSERT stock_movements (append-only, qty знаковое);
      5. UPDATE stock_balances SET qty = qty + :qty.

Транзакцией управляет ВЫЗЫВАЮЩИЙ сервис (архитектура §2: одна транзакция на
запрос). Ledger только flush-ит — commit/rollback делает документ, потому что
«движение + баланс + сам документ» атомарны именно на его уровне.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InsufficientStock
from app.modules.stock.models import StockBalance, StockMovement
from app.shared.enums import MovementDocType

_ZERO = Decimal("0")


async def post(
    session: AsyncSession,
    *,
    product_id: int,
    warehouse_id: int,
    qty: Decimal,
    doc_type: MovementDocType,
    doc_id: int,
) -> StockMovement:
    """Провести одно движение товара и обновить остаток. См. модульный docstring.

    :param qty: знаковое количество (Decimal). Приход > 0, расход < 0. Никогда
        не float — деньги и количества только Decimal (ТЗ §3).
    :raises InsufficientStock: если списание уводит остаток ниже нуля (SV-3).
    :returns: созданное движение (ещё не закоммиченное — коммитит вызывающий).
    """
    if not isinstance(qty, Decimal):
        # Жёстко: float здесь — это тихая потеря копеек/граммов в балансе.
        raise TypeError("ledger.post: qty обязан быть Decimal, не float")
    if qty == _ZERO:
        # CHECK (qty <> 0) в БД это тоже отвергнет, но бессмысленное движение
        # незачем доводить до базы — это ошибка вызывающего кода.
        raise ValueError("ledger.post: нулевое движение бессмысленно")

    # ── Шаг 1. Гарантировать строку баланса без гонки на UNIQUE(product,wh) ──
    # INSERT ... ON CONFLICT DO NOTHING: если строки нет — создаём с qty=0;
    # если параллельный post() уже её создал — конфликт молча гасится. Гонки
    # на уникальном индексе (product_id, warehouse_id) при этом не возникает,
    # в отличие от «SELECT, и если None — INSERT», где окно между проверкой и
    # вставкой ловит второй запрос IntegrityError-ом. Саму блокировку строки
    # эта вставка НЕ даёт — её берёт SELECT ... FOR UPDATE следующим шагом.
    await session.execute(
        pg_insert(StockBalance)
        .values(product_id=product_id, warehouse_id=warehouse_id, qty=_ZERO)
        .on_conflict_do_nothing(index_elements=["product_id", "warehouse_id"])
    )

    # ── Шаг 2. Заблокировать строку баланса (SV-3, защита от гонки списаний) ──
    # FOR UPDATE ОБЯЗАТЕЛЕН: без него два параллельных списания последнего
    # товара оба прочитают старый остаток, оба пройдут проверку и оба спишут —
    # уход в минус при гонке. Блокировка сериализует их: второй ждёт первого и
    # видит уже уменьшенный остаток.
    balance = await session.scalar(
        select(StockBalance)
        .where(
            StockBalance.product_id == product_id,
            StockBalance.warehouse_id == warehouse_id,
        )
        .with_for_update()
    )
    if balance is None:  # pragma: no cover — после ON CONFLICT строка всегда есть
        raise RuntimeError("ledger.post: строка баланса не создалась")

    new_qty = balance.qty + qty

    # ── Шаг 3. Проверка достаточности ДО вставки движения ──
    # Именно доменной ошибкой, а не отловом CHECK (qty >= 0) постфактум:
    # CHECK — последний рубеж БД, а бизнес-правило должно давать пользователю
    # внятный русский текст, а не 500 из IntegrityError.
    if new_qty < _ZERO:
        raise InsufficientStock(
            product_id=product_id,
            warehouse_id=warehouse_id,
            available=balance.qty,
            requested=-qty,  # qty здесь отрицательное → requested положительное
        )

    # ── Шаг 4. Журнал (append-only, никогда не редактируется и не удаляется) ──
    movement = StockMovement(
        product_id=product_id,
        warehouse_id=warehouse_id,
        qty=qty,
        doc_type=doc_type,
        doc_id=doc_id,
    )
    session.add(movement)

    # ── Шаг 5. Проекция: остаток = остаток + движение, в той же транзакции ──
    balance.qty = new_qty

    # flush, но НЕ commit: атомарность «документ + движение + баланс» на
    # совести вызывающего сервиса. flush нужен, чтобы у movement появился id
    # и чтобы конфликты всплыли здесь, а не в конце запроса.
    await session.flush()
    return movement
