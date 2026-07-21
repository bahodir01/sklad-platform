"""М-AI: семантический поиск товара для Telegram-бота (спека15 §3a, §3).

Сервис вызывается ботом (следующий этап спеки15, §6), не отдельный публичный
HTTP-эндпоинт — бот работает от имени привязанного пользователя и уже прошёл
RBAC/аутентификацию на уровне бизнес-эндпоинтов (`POST /requests` и т.п.),
которые он вызывает после того, как учитель выбрал товар кнопкой здесь.

Трёхступенчатый поиск (спека15 §3, шаги 1-3):
  1. ``find_by_substring``   — ILIKE по активным товарам. Бесплатно, мгновенно.
  2. ``suggest_products_ai`` — вызывается ТОЛЬКО когда шаг 1 дал ноль
     результатов (экономия запросов, спека15 §3a). Ключ и включённость — в
     ``integration_settings`` (kind='ai_search', модуль admin, спека15 §5а).
  3. ``find_all_paginated``  — «показать весь список», обычная пагинация,
     всегда доступна вручную на любом шаге (бот вызывает её напрямую, она вне
     цепочки ``resolve_product_query``).

``resolve_product_query`` — оркестрирующий метод, реализует цепочку шагов 1→2
(шаг 3 — сознательно вне цепочки: это ручная альтернатива, не автоматический
фолбэк с точки зрения этого сервиса, бот сам решает её предложить).

О ``warehouse_id`` в сигнатурах ниже: спека15 §3a буквально говорит «список
активных товаров... тех же, что видны на выбранном складе» — но в реальной
схеме (02-contract.json) товар (products) НЕ привязан к складу: заявка
принимает любой активный product_id независимо от warehouse_id (см.
modules/issuance/service.py:create_request — единственная проверка склада
там — allows_issuance/status, товар не сверяется со складом вообще).
Привязки «товар ⟷ склад» в схеме нет (номенклатура глобальна, остатки —
stock_balances, это другое). Поэтому warehouse_id здесь принимается (форма
вызова из спеки сохранена дословно — на случай, если в будущем появится
такая привязка) но НЕ используется для фильтрации — см. «Отклонения» в
.feature-dev/15c-ai-search.md.
"""

import json
import re
from typing import Final

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.service import IntegrationService
from app.modules.ai.schemas import ProductMatch, ResolveResult
from app.modules.catalog.models import Product
from app.modules.catalog.repository import CatalogRepository
from app.modules.catalog.schemas import ProductList
from app.shared.enums import CatalogStatus
from app.shared.pagination import Page, PageParams

_AI_MODEL: Final[str] = "claude-haiku-4-5"
_AI_TIMEOUT_SECONDS: Final[float] = 5.0
_AI_MAX_CANDIDATES_IN_PROMPT: Final[int] = 500
_MAX_MATCHES: Final[int] = 5
_DEFAULT_SUBSTRING_LIMIT: Final[int] = 5
_DEFAULT_PAGE_SIZE: Final[int] = 10


# ══════════════════════ Шаг 1: подстрока ═════════════════════════════


async def find_by_substring(
    session: AsyncSession,
    query: str,
    warehouse_id: int | None = None,
    limit: int = _DEFAULT_SUBSTRING_LIMIT,
) -> list[Product]:
    """Шаг 1 (спека15 §3, шаг 3.1): ``ILIKE %текст%`` по активным товарам.

    ``warehouse_id`` принят по форме вызова из спеки, но не фильтрует —
    products в схеме не привязаны к складу (см. докстринг модуля).
    """
    text = query.strip()
    if not text:
        return []
    stmt = (
        select(Product)
        .where(Product.status == CatalogStatus.active)
        .where(Product.name.ilike(f"%{text}%"))
        .order_by(Product.name)
        .limit(limit)
    )
    rows = await session.scalars(stmt)
    return list(rows)


# ══════════════════════ Шаг 2: ИИ-поиск смысла ═══════════════════════


async def _all_active_products(session: AsyncSession) -> list[Product]:
    """Все активные товары — кандидаты для ИИ (спека15 §3a: «передавай ВСЕ
    активные товары ... не только уже отфильтрованные подстрокой»)."""
    stmt = (
        select(Product)
        .where(Product.status == CatalogStatus.active)
        .order_by(Product.id)
        .limit(_AI_MAX_CANDIDATES_IN_PROMPT)
    )
    rows = await session.scalars(stmt)
    return list(rows)


def _build_ai_prompt(query: str, candidates: list[dict[str, object]]) -> str:
    """Промпт для Claude Haiku (спека15 §3a).

    Требует СТРОГО JSON-ответ (список id, 0-5, без пояснений) — парсится
    программно (``_parse_id_list``); модель ничего не выбирает и не создаёт,
    только предлагает кандидатов из присланного списка (спека15 §3a).
    """
    candidates_json = json.dumps(candidates, ensure_ascii=False)
    return (
        "Ты помогаешь сопоставить запрос сотрудника школы одному или "
        "нескольким товарам на складе. Номенклатура хранится по-русски, а "
        "сотрудник мог написать запрос на другом языке (узбекском, "
        "английском), латиницей или с опечаткой — ищи совпадение по смыслу, "
        "а не только по буквам.\n\n"
        f'Запрос сотрудника: "{query}"\n\n'
        "Список товаров, из которых можно выбирать (JSON-массив объектов "
        f"{{id, name}}):\n{candidates_json}\n\n"
        "Верни СТРОГО JSON-массив id (от 0 до 5 элементов) товаров, которые "
        "могут соответствовать запросу, от наиболее вероятного к наименее "
        "вероятному. Никакого текста вне массива — ни пояснений, ни "
        "markdown-разметки. Если ни один товар не подходит по смыслу — "
        "верни пустой массив.\n\n"
        "Пример корректного ответа целиком: [12, 47, 3]\n"
        "Пример корректного ответа, если ничего не подходит: []"
    )


def _extract_text(response: "anthropic.types.Message") -> str:
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


def _parse_id_list(text: str) -> list[int]:
    """Строгий JSON → список int id. Если модель добавила текст вокруг
    массива — вырезает первый ``[...]`` регэкспом и пробует ещё раз
    (спека15: «попробуй extract разумно... прежде чем сдаться»). Любая
    неудача → пустой список, не исключение."""
    candidates_text = [text.strip()]
    match = re.search(r"\[[^\[\]]*\]", text, re.DOTALL)
    if match:
        candidates_text.append(match.group(0))

    for candidate in candidates_text:
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, list):
            continue
        ids: list[int] = []
        for item in data:
            if isinstance(item, bool):
                continue
            if isinstance(item, int):
                ids.append(item)
            elif isinstance(item, str) and re.fullmatch(r"-?\d+", item.strip()):
                ids.append(int(item.strip()))
        return ids
    return []


async def suggest_products_ai(
    session: AsyncSession,
    query: str,
    candidates: list[Product],
) -> list[ProductMatch]:
    """Шаг 2 (спека15 §3, шаг 3.2 / §3a): ИИ-поиск смысла среди ``candidates``.

    Вызывается только когда шаг 1 дал ноль результатов (экономия запросов).
    Если ``ai_search`` выключен/ключа нет — сразу ``[]``, не ошибка. Таймаут
    5с и ЛЮБАЯ ошибка (сеть, невалидный JSON от модели, что угодно) — тихий
    возврат ``[]``, не роняет вызывающий код (диалог бота).
    """
    if not candidates:
        return []

    api_key = await IntegrationService(session).get_active_secret("ai_search")
    if not api_key:
        return []

    by_id = {p.id: p for p in candidates}
    payload = [{"id": p.id, "name": p.name} for p in candidates]
    prompt = _build_ai_prompt(query, payload)

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.with_options(
            timeout=_AI_TIMEOUT_SECONDS, max_retries=0
        ).messages.create(
            model=_AI_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        # Спека15 §3a: сеть/таймаут/невалидный ключ/что угодно → тихо [].
        return []

    try:
        text = _extract_text(response)
        ids = _parse_id_list(text)
    except Exception:
        return []

    matches: list[ProductMatch] = []
    for product_id in ids:
        product = by_id.get(product_id)
        if product is not None:
            matches.append(ProductMatch(id=product.id, name=product.name))
        if len(matches) >= _MAX_MATCHES:
            break
    return matches


# ══════════════════════ Шаг 3: весь список (пагинация) ═══════════════


async def find_all_paginated(
    session: AsyncSession,
    warehouse_id: int | None,
    page: int,
    size: int = _DEFAULT_PAGE_SIZE,
) -> Page[ProductList]:
    """Шаг 3 (спека15 §3, шаг 3.3): «Показать весь список» — обычная
    постраничная выдача активных товаров (переиспользует shared/pagination.py
    и catalog/repository.py — тот же репозиторий, что и M1 «Товары»).

    ``warehouse_id`` принят по форме вызова из спеки, не фильтрует (см.
    докстринг модуля — products не привязаны к складу в схеме).
    """
    params = PageParams(page=page, size=size)
    repo: CatalogRepository[Product] = CatalogRepository(session, Product)
    items, total = await repo.list(
        params, filters=[Product.status == CatalogStatus.active]
    )
    return Page.build([ProductList.model_validate(i) for i in items], total, params)


# ══════════════════════ Оркестратор: шаги 1→2 ═════════════════════════


async def resolve_product_query(
    session: AsyncSession,
    query: str,
    warehouse_id: int,
) -> ResolveResult:
    """Цепочка шагов 1→2 (спека15 §3): подстрока → ИИ-поиск смысла.

    Это то, что вызывает бот на шаге «Напишите название товара». Шаг 3
    («Показать весь список») сознательно вне этой цепочки — вызывающий бот
    предлагает его сам, когда ``matches == []`` либо в любой момент по
    запросу учителя (спека15 §3, шаг 3: «всегда доступна как ручная
    альтернатива на любом шаге»).
    """
    substring_matches = await find_by_substring(session, query, warehouse_id=warehouse_id)
    if substring_matches:
        return ResolveResult(
            matches=[ProductMatch(id=p.id, name=p.name) for p in substring_matches],
            source="substring",
        )

    all_active = await _all_active_products(session)
    ai_matches = await suggest_products_ai(session, query, all_active)
    if ai_matches:
        return ResolveResult(matches=ai_matches, source="ai")

    return ResolveResult(matches=[], source="none")
