# 07 — Регрессионный pytest-набор backend

**Источник:** `.feature-dev/01-requirements.md` §5 (INV-1..INV-9, SV-1..SV-9), `.feature-dev/03-architecture.md` §9 «Тестирование», разовые скрипты `stage2_scenarios.py` / `stage3_scenarios.py` / `verify_stage45.py` / `verify_reports.py` (скретчпад проверки этапов 2–6).

Разовые скрипты были эталоном поведения, но одноразовым — их сценарии перенесены в постоянный набор `backend/tests/`, запускаемый `pytest` и пригодный для CI.

---

## 1. Результат прогона

```
cd backend
python -m pytest -v
# ...
50 passed in ~9s
```

Прогнано трижды подряд (проверка на нестабильность гоночных тестов) — **50/50 зелёных каждый раз**, без флейков.

Команда для полного запуска (как выполнялась при сдаче):

```bash
cd backend
DATABASE_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/sklad" \
REDIS_URL="redis://localhost:6379/0" \
SECRET_KEY="test-secret-key-for-local-verification-only-32b" \
JWT_SECRET_KEY="test-jwt-secret-key-for-local-verification-32b" \
JWT_SECRET="test-jwt-secret-key-for-local-verification-32b" \
PYTHONIOENCODING=utf-8 \
python -m pytest -v
```

(`conftest.py` также ставит эти значения через `os.environ.setdefault(...)`, так что при отсутствии внешнего `.env` тесты всё равно поднимутся с тем же локальным Postgres — переменные окружения нужны только если реальная БД/секреты отличаются от локального стенда проверки.)

---

## 2. Структура

```
backend/tests/
  conftest.py                    инфраструктура: подключение к БД, автоочистка, фикстуры
  constants.py                   фиксированные id сидов (unit=1, product=1, ...)
  test_documents_acquisition.py  SV-1 (перезакупка, в т.ч. конкурентная), SV-7 (автозакрытие)
  test_documents_transfer.py     SV-3 (перемещение сверх остатка), INV-5, §4.3
  test_issuance_flow.py          SV-4/ADR-3, SV-5+INV-2 (двойной issue(), ГЛАВНЫЙ ТЕСТ), SV-9, §1.3
  test_writeoffs.py              §4.4 порча/брак, INV-4
  test_cash.py                   INV-7, INV-8/ОВ-2 (касса в минус, в т.ч. конкурентно), SV-6, §1.3
  test_reports.py                М6: остатки, недокуп, история (keyset), ДДС
  test_invariants_db.py          БД-инварианты напрямую (в обход сервисного слоя): INV-1, INV-4, INV-5, INV-6, INV-9, SV-9-триггер
  test_smoke.py                  健康check самой инфраструктуры тестов
```

50 тестов, сгруппированы по модулю предметной области (не по файлу кода), как и просило задание — тест на инвариант, а не на функцию.

---

## 3. Что покрыто

### 3.1 Критичное (обязательный список из архитектуры §9)

| Требование архитектуры §9 | Тест(ы) |
|---|---|
| Перезакупка (SV-1), текст ошибки по §4.2 | `test_documents_acquisition.py::test_overbuy_rejected_with_sv1_error_format` |
| Перезакупка — конкурентная (`FOR UPDATE`, TOCTOU) | `test_documents_acquisition.py::test_concurrent_overbuy_protected_by_for_update` |
| Двойной `issue()` — ГЛАВНЫЙ ТЕСТ | `test_issuance_flow.py::test_double_issue_race_yields_exactly_one_writeoff` |
| Конкурентное списание последнего товара при `issue()` | `test_issuance_flow.py::test_double_issue_race_last_unit_of_stock` |
| Касса в минус (одиночно) | `test_cash.py::test_expense_insufficient_funds_leaves_balance_intact` |
| Касса в минус — конкурентно (`FOR UPDATE`) | `test_cash.py::test_concurrent_expenses_do_not_overdraw_desk` |

Все шесть — зелёные, воспроизведены с реальным конкурентным `asyncio.gather()` двух независимых сессий/транзакций против живого PostgreSQL (не мок).

### 3.2 SV-правила (сервисные инварианты)

| Правило | Тест(ы) |
|---|---|
| SV-1 перезакупка | см. 3.1 + `test_overbuy_rejected_when_notification_fully_closed`, `test_notification_moves_to_in_progress_on_partial_purchase` |
| SV-2 единая точка записи (ledger) | косвенно во всех тестах на баланс/движения — альтернативного пути записи в `stock_balances` в коде нет |
| SV-3 списание сверх остатка | `test_documents_transfer.py::test_transfer_over_stock_rejected_sv3`, `test_writeoffs.py::test_spoilage_over_stock_rejected`, `test_issuance_flow.py::test_issue_with_insufficient_stock_rolls_back_fully` |
| SV-4 списание только на `issue()` (ADR-3) | `test_issuance_flow.py::test_stock_untouched_until_issue_sv4` (баланс идентичен на draft/confirm/print) |
| SV-5 двойное списание | см. 3.1 |
| SV-6 касса — сервер, не клиент | `test_cash.py::test_expense_desk_is_server_determined_sv6`, `test_admin_cannot_create_own_expense` |
| SV-7 автозакрытие уведомления | `test_documents_acquisition.py::test_autoclose_on_full_purchase_sv7` |
| SV-8 справочники не удаляются физически | не тестировалось отдельно — в коде М1 нет DELETE-эндпоинтов ни для одного справочника (структурная гарантия, не требует теста гонки/инварианта) |
| SV-9 заявка только со склада списания | `test_issuance_flow.py::test_request_from_non_issuance_warehouse_rejected_by_service` (сервис) + `test_request_from_non_issuance_warehouse_rejected_at_db_level` (триггер БД) + `test_invariants_db.py::test_sv9_trigger_*` (прямой обход сервиса, момент подачи не ретроактивен) |

### 3.3 БД-инварианты (CHECK/UNIQUE — продублированы в БД)

| Инвариант | Тест | Как проверяется |
|---|---|---|
| INV-1 `stock_balances.qty >= 0` | `test_invariants_db.py::test_inv1_negative_balance_rejected_at_db_level` | прямой `UPDATE` в обход ledger |
| INV-2 `issued ⟺ writeoff_id NOT NULL` | `test_issuance_flow.py::test_inv2_check_is_immediate_not_deferrable` + держится после гонки в `test_double_issue_race_*` | CHECK немедленный, не DEFERRABLE — доказано прямым `UPDATE ... SET status='issued'` без `writeoff_id` |
| INV-3 `requests.writeoff_id` UNIQUE | косвенно `test_double_issue_race_yields_exactly_one_writeoff` (ровно одна проводка на заявку) | — |
| INV-4 сотрудник ⟺ `requires_employee` | `test_writeoffs.py::test_spoilage_with_employee_rejected_inv4` (сервис) + `test_invariants_db.py::test_inv4_employee_required_mismatch_rejected_at_db_level` (прямой INSERT, композитный FK+CHECK) |
| INV-5 `from_warehouse_id <> to_warehouse_id` | `test_documents_transfer.py::test_transfer_same_warehouse_rejected_inv5` (сервис) + `test_invariants_db.py::test_inv5_same_warehouse_transfer_rejected_at_db_level` (БД) |
| INV-6 `qty > 0` во всех `*_items` | `test_invariants_db.py::test_inv6_zero_qty_rejected_in_request_items` (репрезентативно; CHECK идентичен по структуре во всех `*_items`) |
| INV-7 `money_expense.receipt_url` NOT NULL / чек обязателен | `test_cash.py::test_expense_without_receipt_rejected_inv7`, `test_expense_bad_receipt_type_rejected` (magic bytes, не расширение) |
| INV-8 `cash_desks.balance >= 0` | см. 3.1 + `test_cash.py::test_cash_desks_balance_check_enforced_at_db_level` (прямой `UPDATE`) |
| INV-9 `users.category IS NULL ⟺ role='admin'` | `test_invariants_db.py::test_inv9_admin_with_category_rejected`, `test_inv9_non_admin_without_category_rejected`, `test_inv9_valid_rows_accepted` (контроль ложноположительных) |

### 3.4 Отчётность (М6, не входит в обязательный список §9, но перенесена из `verify_reports.py` по просьбе задания)

`test_reports.py`: остатки по складам после прихода+перемещения, «недокуп» (остаток к приобретению, закрытые уведомления исключены), история движений — знаки по видам документа + keyset-пагинация (AP-5, страницы не пересекаются), ДДС — фильтр по обязательной категории (AP-8) + корректность итогов/балансов касс.

Экспорт в xlsx/pdf (`export_table`) в постоянный набор **не перенесён** — он не входит ни в обязательный список архитектуры §9, ни в перечисленные в задании инварианты; проверка сериализации в файл более уместна как быстрый smoke-тест в CI на уровне «файл открывается», а не как регрессия бизнес-инварианта. Если нужно — легко добавляется по образцу `verify_reports.py` сценария 5.

---

## 4. Инфраструктура и её ограничения

### 4.1 Реальный PostgreSQL, не testcontainers

Архитектура §9 предписывает `pytest + testcontainers`: половина логики (`FOR UPDATE`, немедленные `CHECK`, триггеры) непроверяема на SQLite. **Docker в этой среде недоступен**, поэтому `backend/tests/conftest.py` использует документированный fallback: подключается к уже поднятому, смигрированному и засеянному PostgreSQL 16 через `DATABASE_URL` — тем же способом, каким работали разовые скрипты (`stage2_scenarios.py` и др.).

**Для CI** нужно заменить фикстуру подключения на `testcontainers.postgres.PostgresContainer("postgres:16")` (уже объявлен dev-зависимостью в `pyproject.toml`):

```python
from testcontainers.postgres import PostgresContainer

with PostgresContainer("postgres:16") as pg:
    os.environ["DATABASE_URL"] = pg.get_connection_url().replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
    # alembic upgrade head
    # затем — минимальный сид: cash_desks (создаются миграцией), unit, product,
    # два warehouse (allows_issuance=true/false), два expense_type
    # (requires_employee=true/false), admin (role=admin, category=NULL),
    # teacher (role=teacher, category=teacher) — см. backend/tests/constants.py
    # за точным списком id, который тесты жёстко ожидают.
```

`tests/conftest.py::verify_seed_data` — session-scoped автофикстура — падает с понятным сообщением на этапе сбора тестов, если сиды не соответствуют `constants.py`, вместо того чтобы 50 тестов упали по отдельности с невнятным `NotFoundError`. Это же защищает от случайного запуска набора против «не той» БД.

### 4.2 Изоляция тестов: без вложенных транзакций/SAVEPOINT

Обычный паттерн pytest+SQLAlchemy (обернуть тест в SAVEPOINT и откатить) здесь не подходит: каждый вызов сервиса (`DocumentsService`, `IssuanceService`, `CashService`) открывает **свою** `AsyncSession` через `app.core.database.SessionLocal()` — так работает и продакшен (один HTTP-запрос = одна транзакция, архитектура §2), и это принципиально необходимо для гоночных тестов (`asyncio.gather` двух независимых сессий должен создавать настоящую конкуренцию за блокировку строки, а не жить в одной транзакции).

Вместо этого — по явному указанию задания — использована другая стратегия: autouse-фикстура `clean_db` в `conftest.py` **truncate**-ит все транзакционные таблицы (`stock_movements`, `stock_balances`, `notifications`/`acquisitions`/`transfers` + их `*_items`, `requests`, `writeoffs` + их `*_items`, `money_income`, `money_expense`, `audit_log`) и сбрасывает балансы касс в 0 — **до и после каждого теста**. Справочники-сиды не трогаются никогда.

Тесты, которым нужны сущности сверх сида (категория расхода денег, пользователь-`worker` — сид не содержит ни одного), создают их с префиксом `TEST_`/`test_` (см. `TEST_CATALOG_PREFIX`/`TEST_PREFIX` в `conftest.py`) — та же autouse-фикстура подметает и их. Прогон трижды подряд оставляет БД идентичной изначальному состоянию (проверено `psql`-запросом после серии прогонов — см. раздел 1).

### 4.3 Версии/окружение

- `pytest-asyncio` и `httpx` пришлось доустановить (`pytest` 8.3.2 без `pytest-asyncio` был установлен, но не покрывал async-тесты) — итоговые версии `pytest 9.1.1` / `pytest-asyncio 1.4.0`.
- `pyproject.toml` уже содержал `[project.optional-dependencies].dev` с `pytest`, `pytest-asyncio`, `httpx`, `testcontainers[postgres]` — новых зависимостей добавлять не пришлось.
- В `[tool.pytest.ini_options]` добавлены `asyncio_default_fixture_loop_scope = "session"` и `asyncio_default_test_loop_scope = "session"` + `testpaths = ["tests"]`. Без session-scope loop'а тесты падали с `RuntimeError: ... attached to a different loop` — `app.core.database.engine` создаётся один раз при импорте модуля и держит пул соединений `asyncpg`, а дефолтный для pytest-asyncio loop-per-test рвёт этот пул между тестами.

---

## 5. Непокрытое / оставлено за скобками

- **Экспорт отчётов в xlsx/pdf** (`app/modules/reports/exporters.py`) — см. §3.4.
- **HTTP-слой** (роутеры, `Depends(require_role(...))`, аутентификация/JWT, `Idempotency-Key`) — набор тестирует сервисный слой напрямую (как и разовые скрипты), не поднимает FastAPI `TestClient`/`httpx.AsyncClient`. Ролевой доступ на уровне эндпоинта, refresh-ротация, детекция переиспользования токена — вне периметра этой задачи (регрессия учётных инвариантов, не HTTP-контракта).
- **PDF-рендеринг бланков** (`shared/pdf.py`, WeasyPrint) — в среде проверки WeasyPrint предупреждает об отсутствии нативных библиотек (pango/cairo) и не мешает тестам (issue()/print_request используют HTML-фолбэк), но сам рендеринг PDF не проверялся.
- **MinIO/S3** (`shared/storage.py`) — `put_object`/`presigned_url` в тестовой среде работают в локальном фолбэк-режиме; интеграция с реальным MinIO не проверялась.
- **Фоновые задачи Celery** (`generate_writeoff_pdf`, `export_report`, `reconcile_stock`, `monthly_income_draft`, `db_backup`) — вне периметра, требуют брокера/воркера.
- **SV-8** (архивация вместо удаления) — не протестирован отдельным тестом: структурная гарантия (в коде М1 попросту нет DELETE-эндпоинтов), а не поведение, которое можно сломать гонкой или граничным значением.
- **INV-6 qty>0** проверен репрезентативно на одной таблице (`request_items`) — CHECK идентичен по формуле во всех пяти `*_items`-таблицах, дублировать тест на каждую не даёт новой информации.

---

## 6. Отклонения от задания

- Задание указывало `JWT_SECRET_KEY` в переменных окружения; фактическое имя поля в `app/core/config.py` — `JWT_SECRET` (env `JWT_SECRET`, без суффикса `_KEY`). `SECRET_KEY`/`JWT_SECRET_KEY` в конфиге приложения не используются вовсе (нет такого поля в `Settings`). `conftest.py` подстраховывается через `os.environ.setdefault` под оба варианта имён — тесты проходят независимо от того, какой из них выставлен в окружении CI.
- Сид не содержит пользователя категории `worker` (только `admin`, id=3, и `teach1`, id=4) — тестам, которым нужен `worker` (несколько тестов в `test_cash.py`, один в `test_reports.py`), он создаётся фикстурой `worker_user` в `conftest.py` с префиксом `test_` и подчищается автоматически.
- `test_documents_acquisition.py::test_concurrent_overbuy_protected_by_for_update` использует 8+8 при потолке 10 (как в `stage2_scenarios.py`), а не 15+15 — сохраняет операцию частичного, а не полного отклонения обеих попыток, что нагляднее демонстрирует именно TOCTOU-защиту (одна проходит, суммарно ≤10), а не тривиальный «обе слишком большие — обе отказ».
- Добавлен тест `test_double_issue_race_last_unit_of_stock`, которого не было в разовых скриптах: гонка `issue()` при остатке, РОВНО равном потребности заявки (без запаса). Он вскрыл нетривиальный, но корректный порядок ошибок (см. §7) — оставлен в наборе, так как явно упомянут архитектурой §9 («конкурентное списание последнего товара»).

---

## 7. Находки — уточнение поведения, НЕ баг

При написании `test_double_issue_race_last_unit_of_stock` первая версия теста ожидала, что проигравшая гонку транзакция получит `ConflictError` (как в сценарии с запасом остатка). Фактически, когда остаток **точно** равен запрошенному количеству (без запаса), проигравшая транзакция получает `InsufficientStock`, а не `Conflict`.

Это **не баг**, а прямое следствие документированного и обязательного порядка операций в `issue_request()` (`app/modules/issuance/service.py`, см. её же docstring и `03-architecture.md` §5.3): `ledger.post()` (шаг 2, берёт `FOR UPDATE` на строку `stock_balances`) выполняется **до** условного `UPDATE requests ... WHERE status='printed'` (шаг 3, источник `Conflict`). Когда стока хватает лишь одной заявке, проигравшая транзакция блокируется на `FOR UPDATE`, разблокируется уже на нулевом остатке победителя и падает на проверке остатка внутри `ledger.post()`, так и не дойдя до шага 3. При остатке с запасом (как в первом сценарии `stage3_scenarios.py`, 50 ≥ 2×10) обе транзакции проходят `ledger.post()` успешно, и различие между «первым» и «вторым» решается уже на `UPDATE ... WHERE status='printed'` — отсюда `Conflict`.

Итог: SV-5 (двойное списание) и SV-3 (нехватка остатка) — оба реализованы корректно и оба недостижимы одновременно (система никогда не спишет дважды и никогда не уйдёт в минус), но конкретный код ошибки у проигравшего зависит от того, есть ли у остатка запас сверх суммы конкурирующих заявок. Тест обновлён с исправленным ожиданием и подробным комментарием — поведение задокументировано, а не замаскировано.

**Других реальных багов в коде backend тестами не найдено** — все 50 тестов, включая шесть обязательных гоночных/граничных сценариев из архитектуры §9, проходят против неизменённого кода `backend/app/`.
