# 15c. Сервис семантического поиска товара для Telegram-бота (спека15 §3a)

Основание: `.feature-dev/15-telegram-bot-spec.md` §3a (+ §3, шаги 1-3).
Внутренний сервисный слой — вызывается ботом (следующий этап спеки, §6), не
отдельный публичный HTTP-эндпоинт. Схема (миграция 0004, `integration_settings`
из `.feature-dev/15a-schema-telegram.md`, сервис интеграций из
`.feature-dev/15b-integrations-backend.md`) — не тронута.

## Что реализовано

### 1. `backend/app/modules/ai/` (новый модуль, не `shared/`)

Решил разместить в `modules/ai/`, а не в `shared/ai_search.py` (задача
допускала оба варианта): сервис прямо зависит от `catalog.models.Product`,
`catalog.repository.CatalogRepository`, `catalog.schemas.ProductList` и
`admin.service.IntegrationService` — это бизнес-логика уровня модуля, а не
общая утилита без зависимостей от других модулей (проверил прецедент:
`shared/numbering.py`, `shared/files.py` в этом кодовом стиле берут только
generic-параметры/`shared.storage`, ни один `shared/*.py` не импортирует
`modules/*`). Модуль без роутера (нет `router.py`) — это не CRUD-справочник,
эндпоинта не появляется в `main.py`, гейт схемы это не затрагивает.

- `backend/app/modules/ai/schemas.py` — `ProductMatch` (`id`, `name`) и
  `ResolveResult` (`matches: list[ProductMatch]`,
  `source: Literal["substring","ai","none"]`). Не участвуют в табличном
  контракте (своей таблицы нет) — задокументировано в докстринге, по тому же
  приёму, что `IntegrationRead/Update` в 15b.
- `backend/app/modules/ai/service.py`:
  - `find_by_substring(session, query, warehouse_id=None, limit=5) -> list[Product]`
    — `ILIKE %text%` по `products.status='active'`, `ORDER BY name`. Пустой
    запрос → `[]` без похода в БД.
  - `suggest_products_ai(session, query, candidates: list[Product]) -> list[ProductMatch]`
    — шаг 2. Читает секрет через новый `IntegrationService.get_active_secret("ai_search")`
    (см. п.2 ниже); `None` (выключено/нет ключа) → сразу `[]`. Иначе — вызов
    Anthropic (`claude-haiku-4-5`, `max_tokens=256`,
    `client.with_options(timeout=5.0, max_retries=0)` — жёсткий таймаут 5с
    без ретраев, чтобы не растягивать wall-clock). Весь блок (конструктор
    клиента + сетевой вызов + разбор ответа) обёрнут в `except Exception:
    return []` — сеть/таймаут/невалидный ключ/что угодно не роняет диалог
    бота (спека15 §3a).
  - `find_all_paginated(session, warehouse_id, page, size=10) -> Page[ProductList]`
    — шаг 3, переиспользует `shared/pagination.py` (`PageParams`/`Page.build`)
    и `catalog/repository.py` (`CatalogRepository`) — тот же путь, что и
    `GET /products` в М1, без дублирования.
  - `resolve_product_query(session, query, warehouse_id) -> ResolveResult`
    — оркестратор шагов 1→2: подстрока → (если пусто) ИИ по ВСЕМ активным
    товарам (не только уже отфильтрованным подстрокой — прямое требование
    §3a). Шаг 3 сознательно вне цепочки: это ручная альтернатива, бот
    предлагает её сам при `matches == []` или по запросу учителя в любой
    момент (спека15 §3).

- `backend/app/modules/admin/service.py` (дополнен) — новый публичный метод
  `IntegrationService.get_active_secret(kind) -> str | None`: возвращает
  расшифрованный секрет ТОЛЬКО если `kind in ALLOWED_KINDS` и
  `is_enabled=true` и `secret_encrypted` не пуст, иначе `None` (включая
  случай неудачной расшифровки — не бросает `ValueError` наружу). Это
  единственная точка, где `ai_search.service` касается `integration_settings`
  — секрет не читается напрямую через модель в обход `IntegrationService`, по
  прямому указанию задачи «через IntegrationService/decrypt_secret».

- `backend/pyproject.toml` — добавлен `anthropic>=0.68` в основные
  зависимости (уже был установлен в venv локально, версия 0.101.0; в
  проекте раньше нигде не упоминался).

### Промпт для ИИ (полный текст, `_build_ai_prompt` в `service.py`)

```
Ты помогаешь сопоставить запрос сотрудника школы одному или нескольким товарам на складе. Номенклатура хранится по-русски, а сотрудник мог написать запрос на другом языке (узбекском, английском), латиницей или с опечаткой — ищи совпадение по смыслу, а не только по буквам.

Запрос сотрудника: "<query>"

Список товаров, из которых можно выбирать (JSON-массив объектов {id, name}):
<candidates_json>

Верни СТРОГО JSON-массив id (от 0 до 5 элементов) товаров, которые могут соответствовать запросу, от наиболее вероятного к наименее вероятному. Никакого текста вне массива — ни пояснений, ни markdown-разметки. Если ни один товар не подходит по смыслу — верни пустой массив.

Пример корректного ответа целиком: [12, 47, 3]
Пример корректного ответа, если ничего не подходит: []
```

Разбор ответа (`_parse_id_list`): сначала пробует `json.loads` на всём
тексте ответа как есть; если это не валидный JSON — регэкспом
`\[[^\[\]]*\]` вырезает первый плоский массив в тексте (на случай, если
модель добавила пояснение вокруг) и пробует ещё раз. Любая неудача на обоих
шагах (не JSON, не список, элементы не число/строка-число) → `[]`, без
исключения наружу.

## Прогоны на живой БД (postgres:5433/sklad)

Env — как в задаче (`DATABASE_URL/REDIS_URL/JWT_SECRET/SECRET_KEY/
INTEGRATION_SECRET_KEY/PYTHONIOENCODING=utf-8`). Сервер на :8000 не трогал —
все прогоны через прямой Python-скрипт с `SessionLocal()` (сервис не HTTP-
эндпоинт, тестировать удобнее так, чем через тестовый роутер).

**Тестовые товары** (id 48-50, добавлены и в конце прогона удалены):
`Бумага A4`, `Ручка шариковая`, `Маркер для доски` — юнит `sht` (id=1,
уже был в сидах), склад `W-ISS` (id=1, `allows_issuance=true`, уже был в
сидах). Существующие сиды `Бумага` (id=1), `Вода` (id=2) не трогал.

**1. `find_by_substring`:**
```
find_by_substring("бумага")        -> id=1 'Бумага', id=48 'Бумага A4'
find_by_substring("несуществующее") -> []
```

**2. `suggest_products_ai` при выключенной интеграции** (реальное состояние
БД на момент прогона: `ai_search.is_enabled=false`) — прямой вызов с 5
кандидатами:
```
suggest_products_ai(session, "paper", candidates) -> []   (без исключения)
```

**3. `resolve_product_query`:**
```
resolve_product_query("бумага", warehouse_id=1)
  -> source='substring', matches=[{id:1,name:'Бумага'}, {id:48,name:'Бумага A4'}]

resolve_product_query("paper", warehouse_id=1)   # англ., прямого совпадения нет, ai выключен
  -> source='none', matches=[]
```

**4. Реальный вызов Anthropic API — ЧАСТИЧНО проверено.**
API-ключа Anthropic (реального или пробного) в этом окружении нет
(`ANTHROPIC_API_KEY` не задан, `ant auth status` — команда `ant` не найдена).
Полноценно пункт 4 задачи («модель находит "Бумага A4" по смыслу запроса
"paper"») **не проверен живым успешным вызовом** — это честно не сделано.

Вместо этого проверил ветку обработки ошибок РЕАЛЬНЫМ сетевым вызовом:
временно (в рамках одного скрипта, с восстановлением состояния в `finally`)
включил `ai_search` с форматно валидным, но не существующим ключом
(`sk-ant-api03-FAKEKEY...`) через `encrypt_secret`/прямую запись в
`integration_settings`, и вызвал `suggest_products_ai` — ушёл настоящий HTTP-
запрос на `api.anthropic.com`, получил отказ (невалидный ключ), пойман
`except Exception`, вернул `[]`:
```
suggest_products_ai(session, "paper", candidates)          -> []
resolve_product_query("paper", warehouse_id=1) (тот же fake-ключ) -> source='none', matches=[]
```
Это подтверждает, что код (а) реально доходит до сетевого вызова с ключом из
БД (расшифровка/`IntegrationService.get_active_secret` работают), (б) любая
ошибка API (в т.ч. настоящий отказ Anthropic, не мок) гасится в `[]`, не
роняя вызывающий код. Состояние `integration_settings.ai_search` после теста
восстановлено (`is_enabled=false`, исходный `secret_encrypted`/`display_name`
— строка `ai_search` в БД и до, и после прогона: `is_enabled=false,
has_secret=true` — этот `has_secret=true` был в БД ДО начала работы над этой
задачей, не мой артефакт, восстановлен как был).

**5. `find_all_paginated`:**
```
find_all_paginated(warehouse_id=1, page=1, size=2) -> total=5, pages=3
  page 1: id=1 'Бумага', id=2 'Вода'
find_all_paginated(warehouse_id=1, page=2, size=2)
  page 2: id=48 'Бумага A4', id=49 'Ручка шариковая'
```
(total=5 = 2 сидовых + 3 тестовых товара на момент прогона.)

**БД возвращена в чистое состояние** — тестовые товары id 48-50 удалены,
проверено повторным `SELECT`: остались только исходные `Бумага`(1)/`Вода`(2).
`integration_settings` не изменена относительно состояния до работы.

## Гейт

```
python .claude/skills/database-schema-design/assets/contract_validator_sqlalchemy.py \
  .feature-dev/02-contract.json \
  backend/app/modules/auth/models.py backend/app/modules/catalog/models.py \
  backend/app/modules/documents/models.py backend/app/modules/stock/models.py \
  backend/app/modules/issuance/models.py backend/app/modules/cash/models.py \
  backend/app/core/audit.py backend/app/modules/admin/models.py \
  backend/app/modules/catalog/schemas.py backend/app/modules/auth/schemas.py \
  backend/app/modules/documents/schemas.py backend/app/modules/stock/schemas.py \
  backend/app/modules/issuance/schemas.py backend/app/modules/cash/schemas.py \
  backend/app/modules/users/schemas.py backend/app/modules/admin/schemas.py
```
Итог: `OK: backend code matches the data dictionary contract.` (прогнан
дважды — до и после прогонов на живой БД, оба раза `OK`).

Дополнительно: `python -c "import app.main"` — приложение импортируется без
ошибок (15 роутов, как и до этой задачи — `modules/ai` не добавляет
эндпоинтов), существующие модули не задеты.

## (а) Отклонения от буквального текста задачи

1. **`warehouse_id` принимается всеми функциями по форме вызова из задачи,
   но НЕ используется для фильтрации.** В реальной схеме (`02-contract.json`)
   `products` — глобальный справочник, привязки «товар ⟷ склад» нет
   (остатки — `stock_balances`, это другое). Проверил по
   `modules/issuance/service.py:create_request` — единственная проверка
   склада там: `allows_issuance`/`status`; `product_id` не сверяется со
   складом вообще. Спека15 §3a буквально говорит «список товаров... тех же,
   что видны на выбранном складе», но такой видимости в схеме нет и она
   заморожена — задокументировал это прямо в докстринге модуля, параметр
   оставил в сигнатуре (не ломает форму вызова, которую использует будущий
   бот) на случай, если такая привязка появится позже.
2. **Секрет читается через новый метод `IntegrationService.get_active_secret`**,
   а не напрямую через `decrypt_secret` + `select(IntegrationSetting)` в
   `ai_search/service.py`. Небольшое дополнение к `admin/service.py` (не
   трогает схему/контракт), но собирает логику «получить активный секрет»
   в одном месте — соответствует прямому указанию задачи «через
   IntegrationService/decrypt_secret».
3. **Тестового HTTP-эндпоинта не добавил** (задача разрешала, но не
   требовала). Сервис — не CRUD, добавление роутера в `admin`/`catalog`
   ради теста добавило бы поверхность в `main.py` без пользы для бота
   (следующего этапа). Прогнал всё через прямые вызовы сервисного слоя с
   `SessionLocal()` — то же самое, что увидит бот, без лишнего кода.
4. **Пункт 4 «Проверки боем» не пройден живым УСПЕШНЫМ вызовом Anthropic**
   (нет ключа в окружении) — см. «Прогоны», п.4. Вместо этого — реальный
   сетевой вызов с заведомо невалидным ключом, подтверждающий обработку
   ошибок API до продакшен-ключа.
5. **`_AI_MAX_CANDIDATES_IN_PROMPT = 500`** — жёсткий потолок на число
   кандидатов, отправляемых в промпт ИИ (не из задачи буквально). На
   масштабе школы (десятки-сотни товаров) недостижим, но без потолка список
   «всех активных товаров» теоретически неограничен и раздул бы промпт/
   стоимость запроса без пользы — сочтено разумной защитой, а не
   расхождением с духом задачи.

## (б) Вопросы к следующему агенту (бот, спека15 §6)

1. `resolve_product_query` возвращает `ResolveResult.matches` максимум 5
   (константа `_MAX_MATCHES`) — совпадает с «до 5 совпадений inline-кнопками»
   из §3, п.3. Если `find_by_substring` вернёт больше 5 (сейчас `limit=5` по
   умолчанию, но вызывающий код может передать больше) — обрезки в
   `resolve_product_query` НЕТ, обрезает сам `find_by_substring` через
   `limit`. Бот должен звать `find_by_substring`/`resolve_product_query` с
   дефолтным `limit=5`, не переопределять его большим числом, если хочет
   строго «до 5».
2. `find_all_paginated` использует `ProductList` из `catalog/schemas.py`
   (id, name, unit_id, sku, status) — бот, вероятно, использует только
   `id`/`name` для кнопок; остальные поля лишние, но переиспользование
   существующей схемы показалось предпочтительнее дублирования DTO.
3. Реальный успешный вызов Anthropic (пункт 4 задачи) не проверен —
   при первом реальном включении интеграции админом стоит вручную
   прогнать `resolve_product_query` с англ./узб. запросом и сверить, что
   модель действительно находит смысловое совпадение, а не только что не
   роняется на ошибке (эта часть проверена).

## (в) Django нет, гейт зелёный

Стек — FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2, как и во всём
проекте. Django/DRF нигде не использованы. Гейт (см. выше) — `OK` дважды.
Схема не менялась (ни один файл `models.py`/миграций не тронут). Новый код
живёт в `backend/app/modules/ai/` (новый модуль) и одном добавленном методе
`backend/app/modules/admin/service.py`; `frontend/` не тронут.

## Файлы

- `backend/app/modules/ai/__init__.py` (новый)
- `backend/app/modules/ai/schemas.py` (новый) — `ProductMatch`, `ResolveResult`
- `backend/app/modules/ai/service.py` (новый) — `find_by_substring`,
  `suggest_products_ai`, `find_all_paginated`, `resolve_product_query`
- `backend/app/modules/admin/service.py` (дополнен) —
  `IntegrationService.get_active_secret`
- `backend/pyproject.toml` (добавлен `anthropic>=0.68` в основные зависимости)
