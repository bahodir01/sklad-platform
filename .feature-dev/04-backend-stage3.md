# 04 · Backend, ЭТАП 3 «Заявки и печать»

**Вход:** `02-contract.json` (источник правды) · `01-requirements.md` (§3 М4, §5 INV-2/INV-3/SV-4/SV-5/SV-9) · `03-architecture.md` (§5.3, ADR-2/ADR-2a/ADR-3) · `04-backend-stage2.md` (ledger, numbering, pdf).
**Стек:** PostgreSQL 16 · SQLAlchemy 2.0 (`Mapped[]`) · Alembic · Pydantic v2 · FastAPI · Python 3.12+. **Django/DRF не использованы нигде** — подтверждение в §7(в).
**Модуль:** `backend/app/modules/issuance/`. На входе был только `models.py` (этап 1); написаны сервис, роутер, схемы, репозиторий, бланк.

---

## 1. Что построено

| Слой | Файл | Ответственность |
|---|---|---|
| Схемы | `backend/app/modules/issuance/schemas.py` | Pydantic v2 по API-флагам контракта (Create/Read/List; Update нет — см. §5) |
| Доступ к данным | `backend/app/modules/issuance/repository.py` | Очередь AP-2/AP-3, «Мои» AP-4, реестр AP-11, тип «Выдача», справки для бланка |
| **Бизнес-логика** | `backend/app/modules/issuance/service.py` | **Статусная машина + `issue()`** — сердце этапа |
| API | `backend/app/modules/issuance/router.py` | 9 эндпоинтов заявок; RBAC + row-level; Idempotency-Key |
| Бланк | `backend/app/templates/pdf/writeoff.html` | Черновая заглушка расхода (ОВ-1б), все поля §6.4 |
| Хранилище | `backend/app/shared/storage.py` | **Новый** — MinIO/S3 с локальным фолбэком (ленивый boto3, как WeasyPrint) |
| Сборка | `backend/app/main.py` | Подключён `issuance_router` |
| Доступ | `backend/app/modules/stock/router.py` | `GET /stock/*` открыт любой роли (было admin-only) |

**9 эндпоинтов М4 (`/api/v1`):**
`POST /requests` · `POST /requests/{id}/confirm` · `GET /requests/my` (teacher/worker);
`GET /requests?status=to_print` · `GET /requests/count?status=to_print` · `POST /requests/{id}/print` · `POST /requests/{id}/issue` · `GET /requests/{id}/pdf` · `POST /requests/batch-print` · `GET /requests/registry` (admin).
Проверено по OpenAPI (FastAPI 0.139 включает роутеры лениво через `_IncludedRouter`; пути видны в `app.openapi()`).

---

## 2. Ключевые решения реализации

### 2.1. `issue()` — порядок операций (§5.3, ADR-2/ADR-3, INV-2/SV-5) — `issuance/service.py`

Реализовано ДОСЛОВНО по заданию и §5.3, порядок не переставлен:

```
issue(request_id):
    1. writeoff = INSERT writeoffs(expense_type='Выдача', employee_id, warehouse_id,
                                   requires_employee=true, date=today, author_id, number) + items
       flush → writeoff.id
    2. для каждой строки: ledger.post(−qty, 'writeoff', writeoff.id)   # InsufficientStock возможен
    3. UPDATE requests SET status='issued', issued_at=now(), writeoff_id=:id   # ОДНИМ оператором
         WHERE id=:id AND status='printed'                                     # условие ВНУТРИ UPDATE (SV-5)
    4. IF rowcount=0: session.rollback(); RAISE Conflict                        # проводка+списание откатятся
    5. COMMIT
```

- **Обе колонки (`status`, `writeoff_id`) меняются одним `UPDATE`.** INV-2 — немедленный `CHECK` (в PostgreSQL не может быть DEFERRABLE), поэтому «сначала статус, потом проводка вторым оператором» упало бы на первом же операторе. **Проверено боем** (сценарий 2e ниже): попытка `SET status='issued'` с `writeoff_id=NULL` отвергается БД на том же операторе.
- **Защита от двойного списания — в `WHERE ... AND status='printed'`** (SV-5), а не в предварительном `if`. Пред-проверка статуса в коде есть, но она только для внятного текста — помечена в комментарии; настоящая защита — атомарный условный UPDATE и `rowcount`.
- **Проводка спекулятивно создаётся первой**, до условия. При `rowcount=0` вся транзакция откатывается — осиротевших `writeoffs` и лишних движений не остаётся (проверено: сценарий 2 — ровно одна проводка).
- **Списание — только через `ledger.post(−qty, 'writeoff')`** (SV-2), готовый и проверенный на этапе 2. `InsufficientStock` из ledger перевыбрасывается с `product_name` (ledger имён не резолвит).
- **Тип «Выдача»** ищется как активный `expense_type` с `requires_employee=true` (порча/брак имеют `false` и через заявку не проходят). `requires_employee` копируется в проводку → составной FK + `ck_writeoffs_employee_iff_required` (INV-4) выполнены, `employee_id` обязателен и берётся из заявки.

### 2.2. Статусная машина (§5.3) — только вперёд, нужной ролью

`draft ──confirm()──► to_print ──print()──► printed ──issue()──► issued`

- **confirm()** — владелец-сотрудник. Row-level: чужую заявку подтвердить нельзя (маскируется под 404, чтобы не раскрывать чужие id). Переход условным `UPDATE ... WHERE status='draft' AND employee_id=:me` — повторный клик/гонка не двигают дважды.
- **print()** — admin, ОВ-3: статус «Напечатан» ставится **явно** (открытие PDF ≠ факт печати). Рендер бланка → снимок в MinIO (`documents/requests/<number>.pdf`) с локальным фолбэком → `pdf_url`. Перепечатка безопасна: `printed→printed`, `printed_at` не затирается (`coalesce(printed_at, now())`).
- **issue()** — admin (см. 2.1).
- Откат статусов вне scope (ТЗ §11).

### 2.3. Форма заявки и SV-9

`POST /requests`: `employee_id` ставит **сервер** из `current_user` (api.create=false). Склад — только `allows_issuance=true AND status='active'` (SV-9/AP-12): проверка в сервисе (внятный текст) + триггер `requests_check_issuance_warehouse` в БД (последний рубеж, `_translate_integrity_error` переводит его отказ в тот же русский текст). Правку черновика (ОВ-11) **не** добавлял.

### 2.4. Idempotency-Key на `POST /requests/{id}/issue` (§6)

Заголовок `Idempotency-Key` → Redis `SET NX ex=600` по ключу `idem:issue:{id}:{key}` **до** входа в транзакцию: явный ретрай/двойной клик отбивается, не доходя до БД. При неуспехе операции ключ освобождается (законный повтор возможен). **Если Redis недоступен — ключ игнорируется, и гарантию единственного списания даёт `WHERE status='printed'` (SV-5)**: Redis лишь экономит поход в БД. Так и задокументировано в docstring эндпоинта.

### 2.5. Реестр и оба номера (§6.4, ADR-2a)

`GET /requests/registry` join `requests`↔`writeoffs` по `writeoff_id`, отдаёт **оба** номера (`request_number` — на бумаге; `writeoff_number` — в учёте). На бланке печатается **номер заявки** (ADR-2a): в момент печати проводки ещё нет.

### 2.6. Бланк расхода — заглушка (ОВ-1б)

`templates/pdf/writeoff.html`, поля §6.4: номер ЗАЯВКИ, ФИО+категория сотрудника, склад, таблица товаров (ЕИ из `products.unit_id`), причина (`reason`), место рукописной подписи (две линии: выдал/получил). Помечен «ЧЕРНОВАЯ ФОРМА». WeasyPrint ленивый: без нативных pango/cairo `GET /{id}/pdf` отдаёт печатный HTML с `X-PDF-Renderer: unavailable-html-fallback`. При получении настоящего бланка подменяется только HTML — код не трогается.

### 2.7. Хранилище файлов — `shared/storage.py` (новый)

boto3 импортируется **лениво** (как WeasyPrint). Объект кладётся в MinIO; при недоступности — в локальный temp-каталог, а **ключ `bucket/key` одинаков в обоих режимах** → `pdf_url` в БД не зависит от режима. `presigned_url` (TTL 5 мин, ТЗ §7) — в S3-режиме; в локальном `GET /{id}/pdf` рендерит на лету.

### 2.8. Открытие `GET /stock/*` любой роли

Архитектура §6: M3 — «any (сотрудник — только чтение)». Заменена зависимость `require_admin` → `require_any_role` (форма заявки подбирает товар/склад по `/stock/balances`, ОВ-5/AP-12). Запись остатков снаружи по-прежнему невозможна — пишет только ledger (SV-2). Это ровно то расширение, которое этап 2 пометил как Б-1.

---

## 3. Проверка боем на живой БД (PostgreSQL 16, `127.0.0.1:5433/sklad`)

Прогон сервисного слоя (`IssuanceService` + `ledger`) напрямую против реальной БД: настоящие `FOR UPDATE`, немедленный `CHECK` INV-2, `UNIQUE(writeoff_id)`, триггер SV-9, advisory-lock нумерации. Скрипт: `scratchpad/stage3_scenarios.py`. Сиды на месте (admin=3, teacher=4, W-ISS=1/W-NO=2, expense_types Выдача=1/Порча=2, product=1, unit=1).

```
[PASS] 1a. Остаток не трогается до issue(): draft=100 confirm=100 print=100 (SV-4/ADR-3)
[PASS] 1b. Остаток упал РОВНО на issue(): 100 − 10 = 90; движений writeoff=1
[PASS] 1c. Проводка создана и связана: writeoff=WOFF-000001 id=1, requests.writeoff_id=1
[PASS] 1d. Статус issued + INV-2 держится
[PASS] 2a. Двойной issue() (ГОНКА): исходы=['conflict','ok'] — ровно один успешен
[PASS] 2b. Создана РОВНО одна проводка: writeoffs в БД=1
[PASS] 2c. Товар списан ОДИН раз: движений writeoff=1, остаток=40 (50 − 10)
[PASS] 2d. INV-2 держится после гонки, статус заявки=issued
[PASS] 2e. INV-2 немедленный: status='issued' без writeoff_id отвергается БД на том же операторе
[PASS] 3a. issue() при недостатке → InsufficientStock ('...доступно 5.000, списывается 10.000')
[PASS] 3b. Статус остался printed, проводки/движения нет, остаток цел (5.000)
[PASS] 4.  Заявка со склада без allows_issuance отклонена (SV-9), заявок в БД=0
[PASS] 5.  /requests/my: свои(teacher)=1, чужой запрос(admin)=0 (row-level §1.3)
Пройдено 13/13
```

**Сценарий 2 (главный тест) — двойной issue().** Две **параллельные** (`asyncio.gather`) корутины issue() одной заявки, каждая в своей сессии/транзакции. Остатка хватало на две выдачи (50 ≥ 2×10) — специально, чтобы второй issue() отбился по **статусной** гонке (Conflict), а не по нехватке товара. Итог: **ровно одна проводка WOFF-000001, одно движение −10, остаток 40 (списано один раз), второй issue() → Conflict, INV-2 держится.** Сериализацию обеспечивают три рубежа сразу: advisory-lock серии нумерации (`WOFF-`), атомарный `UPDATE ... WHERE status='printed'` (SV-5) и блокировка строки баланса в ledger (SV-3); какой из них сработает первым — зависит от планировщика, гарантия одна.

**Сценарий 2e** отдельно доказывает, **зачем** нужен один UPDATE: прямой `UPDATE requests SET status='issued'` с `writeoff_id=NULL` немедленно отвергается CHECK-ом `ck_requests_issued_iff_posted` — то есть двухшаговый порядок из §5.3 физически невозможен, обе колонки обязаны меняться вместе.

**После прогонов БД очищена** (`TRUNCATE requests, request_items, writeoffs, writeoff_items, stock_movements, stock_balances RESTART IDENTITY CASCADE`) — оставлена чистой; сиды/справочники не тронуты (проверено: users=2, warehouses=2, expense_types=2, products=1; заявок/проводок/движений/остатков = 0).

---

## 4. Гейт контракта — зелёный

```
python .claude/skills/database-schema-design/assets/contract_validator_sqlalchemy.py .feature-dev/02-contract.json \
  backend/app/modules/auth/models.py backend/app/modules/catalog/models.py \
  backend/app/modules/documents/models.py backend/app/modules/stock/models.py \
  backend/app/modules/issuance/models.py backend/app/modules/cash/models.py \
  backend/app/core/audit.py \
  backend/app/modules/catalog/schemas.py backend/app/modules/auth/schemas.py \
  backend/app/modules/documents/schemas.py backend/app/modules/stock/schemas.py \
  backend/app/modules/issuance/schemas.py
→ OK: backend code matches the data dictionary contract.
```

Добавлена `issuance/schemas.py`. Схему **не менял** — только код.

**Пути для гейта (новое этапа 3):** модель — `backend/app/modules/issuance/models.py` (этап 1, не тронута); схемы — `backend/app/modules/issuance/schemas.py` (новая).

---

## 5. Соответствие API-флагам (буквально, из контракта)

Следствия, которые легко принять за ошибку и «поправить», но они верны:

- **Ни у `requests`, ни у `writeoffs` нет ни одного `update=true`** → схем `RequestUpdate`/`WriteoffUpdate` нет. Статус двигает только сервер (статусная машина), поля `editable=False`. Правка черновика (ОВ-11) не реализована — см. §6(б).
- `requests`: `reason`/`printed_at`/`pdf_url` — `get_index=false` → в `RequestList` их нет, только в `RequestRead`.
- `request_items`: `get_index=true` только у `id` → отдельной `RequestItemList` не завожу; строки видны как вложенные в `RequestRead` (whitelist `__contract_extra_fields__ = {"items"}`).
- `WriteoffCreate` **не реализована**: прямое создание проводки (порча/брак, `POST /writeoffs`) — это этап 4. Выдача создаётся только через `issue()`. Схема `WriteoffRead` есть — она отдаётся в ответе `issue()`.
- Транспортные конверты (`RequestCount`, `IssueResult`, `RegistryRow`, `BatchPrint*`) не оканчиваются на Create/Update/Read/List → валидатор их не привязывает к таблицам (это ответы операций, не проекции сущностей).

---

## 6. (а) Что сделано иначе / потребовало решения

| # | Предписание | Что сделано | Почему |
|---|---|---|---|
| В-1 | `requests.created_at` «фиксируется при подтверждении» (описание в контракте) | Ставится `server_default=func.now()` при INSERT черновика | Модель (заморожена) объявляет `created_at NOT NULL server_default=now()`. Отдельной записи на confirm нет, а NOT NULL не допускает отложенного заполнения. Расхождение описания и модели — не мой слой (схема заморожена) |
| В-2 | Idempotency-Key (Redis) | `SET NX ex=600`; при отсутствии Redis — падение на SV-5 | Ровно как в задании; ключ освобождается при неуспехе, чтобы законный повтор был возможен |
| В-3 | Тип расхода «Выдача» для проводки | Ищется как активный `expense_type` с `requires_employee=true` | Имя «Выдача» — данные, флаг `requires_employee` — инвариант. Поиск по флагу устойчивее к переименованию справочника |
| В-4 | Нумерация проводок | Своя серия `WOFF-` через существующий `next_document_number` (advisory-xact-lock) | Независимая серия (ADR-2a): порча/брак заявок не имеют. Серия заявок — `REQ-` |
| В-5 | `GET /stock/*` — «any» | `require_admin` → `require_any_role` | Закрывает Б-1 этапа 2; форма заявки читает `/stock/balances` (AP-12/ОВ-5). Запись остатков снаружи по-прежнему невозможна |
| В-6 | Хранение PDF (MinIO, ТЗ §7) | Новый `shared/storage.py` с ленивым boto3 + локальным фолбэком | На dev/CI без MinIO приложение не должно падать (как WeasyPrint этапа 2). Ключ `bucket/key` одинаков в обоих режимах |
| В-7 | Бланк расхода | Черновая заглушка `writeoff.html` со всеми полями §6.4 | ОВ-1б: настоящий бланк придёт позже; подменяется только HTML |
| В-8 | Row-level отказ confirm() чужой заявки | Отдаётся 404, а не 403 | Не раскрываем существование чужих заявок сотруднику |

## 6. (б) Что в контракте/ТЗ показалось неверным — **сообщаю, не «чинил»**

| # | Где | Что не так | Предложение |
|---|---|---|---|
| К-1 | Контракт: `requests.created_at` описание | «Фиксируется при подтверждении заявки», но backend-модель — `server_default=func.now()` (ставится при INSERT черновика), а NOT NULL не даёт заполнить позже. Описание и модель расходятся. Реализовано по модели (заморожена) | Согласовать: либо поправить описание на «при создании черновика», либо (если нужен именно момент confirm) сделать колонку nullable и заполнять на confirm — но это правка схемы |
| К-2 | Контракт: `requests` / ОВ-11 | Ни одного `update=true`, `editable=False`, отдельного эндпоинта правки нет → **черновик заявки после создания нельзя ни исправить, ни удалить** (удаления нет по SV-8). Сотрудник с опечаткой в reason/qty в тупике. Повтор замечания этапа 2 (К-3) уже для заявок | До ответа заказчика не блокирую. Рекомендую: добавить `update`-флаги на `reason`/строки черновика + `PATCH` **или** статус `cancelled` для отмены черновика |
| К-3 | §6.3 vs §10 (терминология) | §6.3 называет очередь «номер расхода», хотя расхода (проводки) на момент печати ещё нет (ADR-2a). В коде колонка очереди — номер ЗАЯВКИ | Терминологический хвост, отмечен и в архитектуре §10. Поправить при ревизии ТЗ, чтобы не искали несуществующую сущность |
| К-4 | Контракт: `writeoffs`/`writeoff_items` | Много `get_index=true`/`get_single=true`, но GET-эндпоинтов списка/детали проводок в API нет (проводка видна через реестр заявок и — на этапе 4 — при порче/браке). Флаги опережают эндпоинты | Не блокирует; повтор наблюдения К-4 этапа 2 для соседних таблиц |
| К-5 | §5.3 архитектуры (пример псевдокода) | В §5.3 псевдокод issue() показывает `INSERT writeoffs(...)` без явного `date`/`number`/`requires_employee`; эти поля NOT NULL и заполняются сервером (date=сегодня, number=серия `WOFF-`, requires_employee=копия флага). Не дефект — уточнение, что псевдокод неполный | К сведению; реализация заполняет все NOT NULL-поля проводки |

## 6. (в) Подтверждение стека и гейта

- **Django/DRF не использованы.** Новый код: SQLAlchemy 2.0 Core/ORM (`select`, `update`, `func`, `selectinload`, `with_for_update` через ledger, `execution_options(synchronize_session=False / populate_existing=True)`), Pydantic v2 (`BaseModel`, `ConfigDict(from_attributes=True)`), FastAPI (`APIRouter`, `Depends`, `require_admin`/`require_role`, `Header`, `Response`), asyncpg. Ни `models.Model`, ни DRF-сериализаторов, ни Django-migrations.
- **Гейт контракта зелёный:** `OK: backend code matches the data dictionary contract.`
- **Схему не менял** — заморожена; правок DDL/моделей нет. Проверено, что INV-2/INV-3/SV-9/INV-4 живут в БД и срабатывают (сценарии 2c/2e/4).
- **13/13 сценариев на живой БД пройдены**, включая главный — двойной параллельный `issue()` (одна проводка, товар списан один раз, второй Conflict).

---

**Следующий шаг — этап 4 «Перемещения/расходы»:** порча/брак — прямое создание `writeoff` без заявки (`POST /writeoffs`, `WriteoffCreate` + `ledger.post(−qty,'writeoff')` сразу). Таблица `writeoffs`, ledger и статусная логика уже готовы и проверены этим этапом.
