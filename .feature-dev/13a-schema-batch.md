# 13a · Схема: пакетная подпись и учёт передачи (этап 1 — только схема)

**Вход:** `13-batch-signature-spec.md` (§2 статусы, §3 `signature_batches`, §4 поля передачи, §6 ограничения).
**Стек:** PostgreSQL 16 · SQLAlchemy 2.0 · Alembic · Pydantic v2. **Django нет.**
**Ревизия:** `0002_batch_signature` (`down_revision = 0001_initial`). `0001` не тронута.
**Гейт:** зелёный (exit 0).

---

## 1. Что добавлено / изменено

### 1.1 Статусная модель `requests.status` (§2)
- Enum `request_status`: `draft, to_print, printed, issued` → **`draft, to_issue, issued, signed, submitted`**.
- Data migration в 0002: `to_print → to_issue`, `printed → to_issue`, `draft/issued → без изменений`.
- Списание (writeoff) теперь рождается на переходе `to_issue → issued` (было `printed → issued`) — это логика этапа 2, схема лишь готовит статусы.

### 1.2 Инвариант INV-2 (§6, проводка)
- Было: `CHECK ((status = 'issued') = (writeoff_id IS NOT NULL))`.
- Стало: `CHECK ((status IN ('issued','signed','submitted')) = (writeoff_id IS NOT NULL))`.
- Совместимость: прежние `issued` уже имеют `writeoff_id` → проходят; `to_print/printed → to_issue` имеют `writeoff_id IS NULL` → проходят.

### 1.3 Новая таблица `signature_batches` (§3) — 23-я таблица
`id, number (uniq, серверная серия), period_from date, period_to date, created_by → users (RESTRICT), printed_at timestamptz NULL, signed_at timestamptz NULL, pdf_url varchar(500) NULL, created_at`.
- `CHECK (period_from <= period_to)` — последний рубеж против бессмысленного периода (в спеке не задан явно, добавлен как разумный guard).
- Индекс `ix_signature_batches_created_by` (FK, по конвенции проекта).
- `requests.batch_id → signature_batches(id)` (nullable, `ondelete RESTRICT`), индекс `ix_requests_batch_id`. Признак «напечатано» = `batch_id IS NOT NULL`.

### 1.4 Колонки передачи в бухгалтерию (§4)
- `requests.submitted_at` (date NULL), `requests.submitted_register_no` (varchar(32) NULL).
- `money_expense.submitted_at` (date NULL), `money_expense.submitted_register_no` (varchar(32) NULL).
- Частичный индекс `ix_money_expense_not_submitted (id) WHERE submitted_at IS NULL` — у денег нет статуса, «Передано/Не передано» различается только по `submitted_at`; actionable-набор (экран передачи, bulk) держится горячим. Тот же приём, что прежний `ix_requests_to_print`.
- Для `requests` отдельного частичного индекса под «переданные/непереданные» нет: там это статусы (`signed`/`submitted`), их обслуживает `ix_requests_status`. `submitted_register_no` без индекса — печать реестра по требованию, не горячий путь (правило проекта: индекс под заявленный access pattern).

### 1.5 Индекс очереди
Частичный `ix_requests_to_print (WHERE status='to_print')` снят вместе со значением `to_print`. Четыре фильтр-карточки экрана «Выдачи товара» (§5 спеки) обслуживает существующий `ix_requests_status`.

### 1.6 Затронутые файлы
- `backend/app/shared/enums.py` — `RequestStatus`.
- `backend/app/modules/issuance/models.py` — модель `SignatureBatch`; `Request`: `batch_id/submitted_at/submitted_register_no`, INV-2, снят `ix_requests_to_print`.
- `backend/app/modules/cash/models.py` — `MoneyExpense`: `submitted_at/submitted_register_no` + частичный индекс.
- `backend/app/models.py` — реестр: `SignatureBatch` (22 → 23 таблицы).
- `backend/alembic/versions/0002_batch_signature.py` — новая ревизия.
- `.feature-dev/build_dictionary.py` — источник правды словаря (правки атрибутов только здесь) + перегенерированные `02-contract.json` / `02-data-dictionary.xlsx`.
- `.feature-dev/02-database.md` — раздел §12 про 0002.

---

## 2. Как решён `ALTER TYPE` enum на живых данных

PostgreSQL не удаляет значения из enum; `ALTER TYPE … ADD VALUE` нельзя использовать в той же транзакции, где значение затем читается. Нужно и добавить, и убрать значения — поэтому тип **пересоздаётся** (транзакционно-безопасно, с ремапом в одном `ALTER COLUMN … USING`):

1. Снять зависящее от старых значений: `DROP INDEX ix_requests_to_print`, `DROP CONSTRAINT ck_requests_issued_iff_posted`, `ALTER COLUMN status DROP DEFAULT`.
2. `RENAME` старого типа → `CREATE` нового → `ALTER COLUMN status TYPE … USING (CASE … )` (ремап `to_print/printed → to_issue`) → `SET DEFAULT 'draft'` → `DROP TYPE …_old`.
3. Добавить новый INV-2.

`ix_requests_status` (обычный b-tree) Postgres при смене типа перестраивает сам.

---

## 3. Результаты прогонов (живая БД `:5433/sklad`)

### 3.1 `alembic upgrade head`
```
Running upgrade 0001_initial -> 0002_batch_signature, batch signature & submission tracking (фича 13)
alembic current →  0002_batch_signature (head)
```

### 3.2 Проверки через psql (после upgrade)
| Проверка | Результат |
|---|---|
| enum `request_status` | `draft,to_issue,issued,signed,submitted` ✓ |
| таблица `signature_batches` | `id,number,period_from,period_to,created_by,printed_at,signed_at,pdf_url,created_at` ✓ |
| `requests` новые колонки | `batch_id,submitted_at,submitted_register_no` ✓ |
| `money_expense` новые колонки | `submitted_at,submitted_register_no` ✓ |
| INV-2 | `CHECK ((status = ANY (ARRAY['issued','signed','submitted'])) = (writeoff_id IS NOT NULL))` ✓ |
| `ix_requests_to_print` | отсутствует ✓ |
| новые индексы | `ix_requests_batch_id, ix_signature_batches_created_by, ix_money_expense_not_submitted, ix_requests_status` ✓ |
| FK `requests.batch_id` | `FOREIGN KEY (batch_id) REFERENCES signature_batches(id) ON DELETE RESTRICT` ✓ |
| заявки в старых статусах `to_print/printed` | `0` ✓ (миграция значений прошла) |
| seed касс | `teacher,worker` — не тронут ✓ |

### 3.3 Обратимость: `alembic downgrade -1` → `alembic upgrade head`
| Шаг | Результат |
|---|---|
| `downgrade -1` | `0002 → 0001_initial`; enum вернулся к `draft,to_print,printed,issued`; `signature_batches` удалена; `requests.batch_id` снят; старый INV-2 и `ix_requests_to_print` восстановлены ✓ |
| `upgrade head` (повторно) | `0001 → 0002`, enum снова `draft,to_issue,issued,signed,submitted` ✓ |

БД оставлена на **`0002_batch_signature` (head)**. Тестовых записей не создавал; сиды не тронуты.

### 3.4 Гейт
```
python .claude/skills/database-schema-design/assets/contract_validator_sqlalchemy.py \
  .feature-dev/02-contract.json backend/app/modules/*/models.py \
  backend/app/core/audit.py backend/app/modules/*/schemas.py
→ OK: backend code matches the data dictionary contract.   (exit 0)
```
Одна промежуточная ошибка гейта была исправлена: сперва я пометил `money_expense.submitted_at` как `db_index=True`, но частичный индекс индексирует `id` по предикату `WHERE submitted_at IS NULL`, а не саму колонку (валидатор считает индексируемыми только колонки в аргументах `Index(...)`, не в предикате). Исправлено: у колонки `db_index` пуст, частичный индекс описан в `other validations` — как и в прежнем `ix_requests_to_print`.

---

## 4. Итог

### (а) Отклонения от задания
1. **`create/update` для новых полей — всегда `—`, `get_index/get_single` — пока `—`.** Новые атрибуты (`signature_batches.*`, поля передачи, `batch_id`) server-managed (ставятся bulk-действиями), клиент их не присылает — `create/update=—` постоянно. Read-экспозицию (`get_index/get_single`) и Pydantic-схемы я **намеренно не включил**: схемы — этап 2, а гейт валидатора падает, если пометить read-поле, которого нет в схеме. Чтобы гейт этапа 1 был зелёным, флаги оставлены `—`; этап 2 их поднимет вместе со схемами. Проверка логики валидатора это подтвердила (schema-check требует поле в `XxxRead/XxxList` при `get_single/get_index=true`).
2. **Снят частичный индекс очереди `ix_requests_to_print`** (его значение `to_print` исчезло) вместо замены на новый частичный индекс — четыре фильтр-карточки обслуживает уже существующий `ix_requests_status`. Соответствует правилу проекта «индекс под заявленный access pattern».
3. **Добавлен `CHECK (period_from <= period_to)`** на `signature_batches` — в спеке §3 явно не задан, добавлен как разумный guard.
4. **Длина `submitted_register_no` = varchar(32)** — в задании длина не указана; выбрано по конвенции документов-номеров (как `number`).

### (б) Вопросы / требует внимания следующего агента (этап 2)
1. **Существующий код статусной машины сломан намеренно и требует правки этапом 2.** `issuance/service.py`, `issuance/router.py`, `issuance/repository.py` (и `tests/test_issuance_flow.py`) написаны под старую модель и ссылаются на `RequestStatus.to_print` / `.printed`, которых больше нет в enum → **ImportError/AttributeError при импорте этих модулей**. Это вне моих границ (только схема); миграцию/гейт/env.py не задевает (alembic и валидатор их не импортируют). Этап 2 обязан переписать переходы под `draft→to_issue→issued→signed→submitted`, перенести списание на `to_issue→issued`, добавить bulk-действия печати/подписи/передачи и обновить pytest (спека §6).
2. **API-флаги и Pydantic-схемы** новых полей и таблицы `signature_batches` — за этапом 2 (поднять `get_index/get_single`, где нужно на экранах §5, и добавить `SignatureBatch*`, поля передачи в `RequestRead/List`, `MoneyExpense*`).
3. **Формат номера пачки/реестра** — серверная серия, как у прочих документов (спека §7); реализация нумерации — этап 2.

### (в) Django нет; миграция обратима
- Django-ветка не применялась: SQLAlchemy 2.0 модели, Alembic-ревизия, Pydantic v2. Проверено.
- Миграция **обратима структурно** и проверена боем (`downgrade -1` → `upgrade head`). **Ограничение downgrade — семантическое:** обратный ремап `to_issue → to_print`, `signed/submitted → issued` (старая модель этих состояний не знала) — часть исторической информации о подписи/передаче теряется. Структура восстанавливается полностью. На момент миграции `requests` пуста → фактической потери данных нет.
