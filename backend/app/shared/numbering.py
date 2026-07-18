"""Генератор номеров документов. Архитектура §3: shared/numbering.py.

ТЗ §9 «Допущение по нумерации»: notifications, acquisitions, transfers,
requests, writeoffs имеют НЕЗАВИСИМЫЕ серии, номера генерирует сервер.

ПОЧЕМУ БЕЗ ОТДЕЛЬНОЙ ТАБЛИЦЫ-СЧЁТЧИКА. Схема заморожена контрактом (22 таблицы),
таблицы-счётчика среди них нет. Поэтому следующий номер серии вычисляется из
максимума уже существующих в колонке `number`. Чтобы два параллельных документа
одной серии не прочитали один и тот же максимум и не столкнулись на UNIQUE, весь
подбор идёт под транзакционной advisory-блокировкой Postgres:

    pg_advisory_xact_lock(hashtext(series))

Блокировка берётся по имени серии, автоматически снимается при COMMIT/ROLLBACK
(xact-вариант) и сериализует ТОЛЬКО выдачу номеров этой серии — разные серии и
любые другие операции она не трогает. UNIQUE-constraint на `number` остаётся
последним рубежом на случай обхода этого хелпера.
"""

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute


async def next_document_number(
    session: AsyncSession,
    number_column: InstrumentedAttribute[str],
    *,
    prefix: str,
    width: int = 6,
) -> str:
    """Следующий номер серии вида ``PREFIX000042``.

    :param number_column: колонка ``.number`` модели документа (серия = таблица).
    :param prefix: префикс серии (``NOTIF-``, ``ACQ-``, ``TRF-``).

    Должен вызываться ВНУТРИ той же транзакции, что и INSERT документа: тогда
    advisory-xact-lock удерживается до COMMIT и никто другой не подберёт тот же
    номер, пока строка ещё не видна.
    """
    # hashtext(prefix) → int4; pg_advisory_xact_lock принимает bigint.
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(prefix))))

    # Максимальный числовой хвост среди существующих номеров этой серии.
    # regexp_replace срезает всё до цифр (префикс), остаток кастуется в int.
    max_seq = await session.scalar(
        select(
            func.max(
                cast(func.regexp_replace(number_column, r"^\D+", "", "g"), Integer)
            )
        ).where(number_column.like(f"{prefix}%"))
    )
    nxt = int(max_seq or 0) + 1
    return f"{prefix}{nxt:0{width}d}"
