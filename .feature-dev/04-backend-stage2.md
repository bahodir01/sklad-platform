# 04 · Backend, ЭТАП 2 «Товародвижение»

**Вход:** `02-contract.json` (источник правды) · `01-requirements.md` (ТЗ) · `03-architecture.md` (§5.1/§5.2/§5.3, ADR-1/ADR-3) · `04-backend-stage1.md` (каркас, модели всех 22 таблиц, auth, catalog).
**Стек:** PostgreSQL 16 · SQLAlchemy 2.0 (`Mapped[]`) · Alembic · Pydantic v2 · FastAPI · Python 3.12+. **Django/DRF не использованы нигде** — подтверждение в §7(в).
**Критический путь пройден:** `stock/ledger.py` реализован ПЕРВЫМ и проверен боем на живой БД — он зависимость этапов 3, 4, 6.

---

## 1. Что построено (scope этапа 2)

| Модуль | Файл | Ответственность |
|---|---|---|
| М3 ядро | `backend/app/modules/stock/ledger.py` | **Единая точка записи движений** (SV-2). Единственный писатель `stock_movements`/`stock_balances` |
| М3 | `backend/app/modules/stock/{schemas,repository,service,router}.py` | Чтение остатков (AP-10, offset) и истории (AP-5, keyset) |
| М2 | `backend/app/modules/documents/{schemas,repository,service,router}.py` | Уведомления (CRUD+PDF), приобретения (SV-1), перемещения |
| shared | `backend/app/shared/numbering.py` | Генератор номеров документов (независимые серии) |
| shared | `backend/app/shared/pdf.py` | Jinja2-рендер + WeasyPrint (ленивый), бланк BILDIRISHNOMA |
| core | `backend/app/core/exceptions.py` (+`InsufficientStock`) · `core/config.py` (+реквизиты org) | |
| сборка | `backend/app/main.py` | Подключены роутеры `documents` и `stock` |

**7 эндпоинтов (`/api/v1`, все — admin):** `GET,POST /notifications`, `GET /notifications/{id}`, `GET /notifications/{id}/pdf`, `POST /acquisitions`, `POST /transfers`, `GET /stock/balances`, `GET /stock/movements`. Проверено по OpenAPI; `DELETE` отсутствует.

---

## 2. Ключевые решения реализации

### 2.1. `ledger.post()` — сердце (§5.2, ADR-1, SV-2, SV-3)

Порядок ровно по архитектуре §5.2, с явной защитой от двух гонок:

1. **Гонка на создании строки баланса** решена `INSERT ... ON CONFLICT DO NOTHING` по индексу `(product_id, warehouse_id)`, затем `SELECT ... FOR UPDATE`. Наивное «SELECT, если None — INSERT» ловит второй параллельный запрос `IntegrityError`-ом на уникальном индексе; `ON CONFLICT` этого окна не оставляет. Стратегия описана в комментарии модуля.
2. **Гонка на списании** (SV-3) решена `SELECT ... FOR UPDATE` по строке баланса — сериализует конкурентные списания последнего товара.
3. **`balance + qty < 0` → `InsufficientStock` ДО вставки движения**, а не отлов `CHECK (qty >= 0)` постфактум: доменное правило даёт русский текст, CHECK остаётся последним рубежом БД.
4. Количества — только `Decimal` (жёсткая проверка `isinstance`; `float` → `TypeError`).
5. Ledger делает `flush`, но **не** `commit` — транзакцией владеет вызывающий сервис (§2 архитектуры). `stock_movements` append-only, не редактируется/не удаляется.

### 2.2. Контроль перезакупки (§5.1, SV-1) — `documents/service.create_acquisition`

`SELECT ... FROM notification_items WHERE notification_id=? FOR UPDATE` **до** чтения `SUM(acquisition_items.qty)`. Без блокировки два параллельных приобретения оба прочли бы `remaining=10` и оба прошли (TOCTOU). Строки приобретения агрегируются по товару (один товар может встретиться в документе дважды). Текст ошибки **строго по §4.2**:
`Товар "Бумага": остаток к приобретению 5 sht, невозможно приобрести 15 sht` (имя и ЕИ подтягиваются из `products`/`units`, число — без хвостовых нулей).

### 2.3. Перемещение (§4.3) — две записи ledger

`ledger.post(−qty, transfer, from_wh)` затем `ledger.post(+qty, transfer, to_wh)`, обе `doc_type='transfer'`. Порядок «сначала списание»: если на источнике не хватает — `InsufficientStock` рвёт транзакцию **до** прихода, приход-без-списания физически невозможен. `InsufficientStock` из ledger перевыбрасывается с именем товара (ledger имён не резолвит — не его слой). INV-5 (`from<>to`) проверяется и в сервисе (внятный текст), и CHECK-ом БД.

### 2.4. Автозакрытие уведомления (SV-7)

После приобретения: если по **всем** строкам `purchased ≥ requested` → `status='closed'`; иначе, если было `draft` → `in_progress`. Enum `notification_status` в контракте включает `in_progress`, но правило перехода `draft→in_progress` в ТЗ явно не прописано — выбрано «первое приобретение переводит в работу». См. §6(б).

### 2.5. Нумерация без таблицы-счётчика

Схема заморожена (22 таблицы, счётчика среди них нет). Следующий номер серии = максимум числового хвоста `number` этой серии + 1, под `pg_advisory_xact_lock(hashtext(prefix))` — транзакционная блокировка сериализует выдачу номеров одной серии, снимается на COMMIT/ROLLBACK, разные серии и прочие операции не трогает. UNIQUE на `number` — последний рубеж. Серии: `NOTIF-`, `ACQ-`, `TRF-`.

### 2.6. PDF-бланк BILDIRISHNOMA

Jinja2-рендер `templates/pdf/notification.html`; контекст ровно как в шаблоне: `n` (ORM Notification: `n.body_text`/`n.division_name`/`n.comment`), `items[]` с `product_name`/`qty`/`unit_code` (ЕИ из `products.unit_id`), `org` из настроек. WeasyPrint импортируется **лениво**: на машинах без нативных pango/cairo (как здесь) эндпоинт отдаёт готовый к печати HTML с заголовком `X-PDF-Renderer: unavailable-html-fallback`, приложение не падает. Печать не меняет статус, перепечатка безопасна.

---

## 3. Проверка боем на живой БД (PostgreSQL 16, `127.0.0.1:5433/sklad`)

Прогон сервисного слоя напрямую против реальной БД (настоящие `FOR UPDATE`, `CHECK`, `UNIQUE`; HTTP/JWT/Redis не задействованы — проверяется ядро товародвижения). Скрипт: `scratchpad/stage2_scenarios.py`.

```
[PASS] 1. Приобретение 10 → приход: acq=ACQ-000001, balance(W-ISS)=10.000,
        movements=[(10.000, 'acquisition', 1, wh=1)]
[PASS] 2. Перезакупка 15 при остатке 5 → отказ:
        message='Товар "Бумага": остаток к приобретению 5 sht, невозможно приобрести 15 sht'
[PASS] 3. Перемещение 3 W-ISS→W-NO → две записи: tr=TRF-000001, W-ISS=12.000, W-NO=3.000,
        transfer_movements=[(-3.000,'transfer',1,wh=1),(3.000,'transfer',1,wh=2)]
[PASS] 4. Перемещение 999 при остатке 3 → InsufficientStock:
        message='Недостаточно товара «Бумага» на складе (id=2): доступно 3.000, списывается 999';
        баланс W-NO до=3.000 после=3.000 (полный откат транзакции)
[PASS] 5. Автозакрытие при полном приобретении (SV-7): status: draft → closed
[PASS] 6. Конкурентная перезакупка (FOR UPDATE, SV-1): results=['ok','rejected: overbuy'],
        суммарно приобретено=8.000 (потолок 10 не превышен)
Пройдено 6/6
```

Сценарии 1–5 — обязательные из задания. Сценарий 6 добавлен: две параллельные закупки по 8 при потолке 10 — без `FOR UPDATE` прошли бы обе (перезакупка 16), с блокировкой ровно одна проходит, вторая отбивается. Это прямая проверка защиты SV-1 от гонки.

**Дополнительно проверено:** частичное приобретение (4 из 10) → `GET /notifications/{id}` возвращает `purchased=4.000, remaining=6.000, status=in_progress`; HTML-бланк рендерится (содержит `BILDIRISHNOMA` и строку товара); WeasyPrint без нативных библиотек корректно уходит в HTML-фолбэк, не роняя запрос.

**После прогонов таблицы товародвижения очищены** (`TRUNCATE ... RESTART IDENTITY`) — БД оставлена чистой для этапа 3; сиды/справочники не тронуты.

---

## 4. Гейт контракта — зелёный

```
python .claude/skills/database-schema-design/assets/contract_validator_sqlalchemy.py \
  .feature-dev/02-contract.json \
  backend/app/modules/auth/models.py backend/app/modules/catalog/models.py \
  backend/app/modules/documents/models.py backend/app/modules/stock/models.py \
  backend/app/modules/issuance/models.py backend/app/modules/cash/models.py \
  backend/app/core/audit.py \
  backend/app/modules/catalog/schemas.py backend/app/modules/auth/schemas.py \
  backend/app/modules/documents/schemas.py backend/app/modules/stock/schemas.py
→ OK: backend code matches the data dictionary contract.
```

Схемы новых модулей добавлены в команду (`documents/schemas.py`, `stock/schemas.py`). Вложенные `items` и вычисляемые `qty_purchased`/`qty_remaining` разрешены валидатору явным `__contract_extra_fields__` (колонками они не являются: ТЗ §3 «остаток к приобретению не хранится»). Схема **не менялась** — только код.

**Пути моделей/схем для гейта:** модели — `backend/app/modules/{documents,stock}/models.py` (этап 1, не тронуты); схемы — `backend/app/modules/{documents,stock}/schemas.py` (новые).

---

## 5. Соответствие API-флагам (буквально, из контракта)

Следствия, которые легко принять за ошибку и «поправить», но они верны:

- **`notifications` не имеет ни одного `update=true`** → схемы `NotificationUpdate` нет; статус меняет только сервер (autoclose/in_progress), `editable=False`.
- `notifications`: `comment`/`body_text`/`division_name`/`created_at`/`pdf_url` — `get_index=false` → в `NotificationList` их нет, только в `NotificationRead`.
- `stock_movements`/`stock_balances` — все поля `create=false`/`update=false` → только `List`/`Read`, никаких Create/Update (SV-2: пишет только ledger).
- `stock_movements.doc_id` — FK нет (полиморфная ссылка), целостность держит ledger.

---

## 6. (а) Что сделано иначе / потребовало решения

| # | Предписание | Что сделано | Почему |
|---|---|---|---|
| Б-1 | §3 API: М3 stock — «any (сотрудник — только чтение)» | На этапе 2 `GET /stock/*` под **admin** | Задание §3 прямо предписывает «всё — admin» для эндпоинтов этого этапа. Расширение до `any` — точечная замена зависимости на этапе 3, когда появятся заявки сотрудников. Схема/логика этого не касаются |
| Б-2 | Номера документов — «генерирует сервер» (ТЗ §9), способ не задан | `pg_advisory_xact_lock` + max-хвост, без таблицы-счётчика | Схема заморожена, 23-й таблицы заводить нельзя. Advisory-xact-lock сериализует выдачу без гонки и без нового объекта данных |
| Б-3 | Enum `notification_status` включает `in_progress`, но правило `draft→in_progress` в ТЗ не описано | Первое приобретение переводит `draft→in_progress`; полное — в `closed` (SV-7) | Иначе значение `in_progress` в enum-е мёртвое. Отдельного эндпоинта смены статуса нет (контракт: `status` create/update=false) |
| Б-4 | Приобретение по уведомлению | Разрешено против `draft` и `in_progress`, запрещено против `closed` | В scope этапа 2 нет «подтверждения» уведомления (это ближе к М4). Чтобы поток «создал → закупил» работал, `draft` допускается к закупке |
| Б-5 | Архитектура §8: WeasyPrint | Добавлен в зависимости + `jinja2`; импорт **ленивый**, HTML-фолбэк | На dev/CI без нативных pango/cairo падение импорта на старте из-за печатной формы недопустимо. Прод-конфиг (машина заказчика с либами) отдаёт настоящий PDF |
| Б-6 | Реквизиты бланка (ректор/подпись) — «константы приложения» (ТЗ §3) | Заведены в `core/config.py` (`org_*`), в БД не хранятся | Ровно как предписано; шапка целыми строками (узбекские окончания), склейки в шаблоне нет |
| Б-7 | `InsufficientStock` (§5.2) | Добавлен класс в `core/exceptions.py` (422), с `product_id/available/requested` | Ledger знает только id; сервис перевыбрасывает с `product_name` для читаемого текста |

## 6. (б) Что в контракте/ТЗ показалось неверным — **сообщаю, не «чинил»**

| # | Где | Что не так | Предложение |
|---|---|---|---|
| К-1 | ТЗ §5 enum `notification_status` vs §3/§4 | Значение `in_progress` есть, но **нигде не задан момент перехода** `draft→in_progress` (в отличие от чёткого SV-7 для `closed`). Реализовал «первое приобретение → in_progress». Стоит зафиксировать это в ТЗ явно |
| К-2 | ТЗ §4.2 пример текста | Пример `остаток к приобретению 10 шт` использует ЕИ `шт`, но код берёт ЕИ из `units.code` данных (в сиде — `sht`). Формат строки идентичен ТЗ; конкретная ЕИ зависит от справочника. Не дефект, фиксирую, чтобы «sht» в проверке не приняли за расхождение с примером |
| К-3 | Контракт: `notifications` | Ни одного `update=true` при `status` `editable=False` и без эндпоинта смены статуса. Значит **черновик уведомления после создания не редактируется никак** (даже опечатку в `body_text`). Возможно, это намеренно (документ печатается как есть), но стоит подтвердить: если админ должен править черновик — не хватает `update`-флагов на `body_text`/`comment`/`division_name` |
| К-4 | Контракт: `acquisitions`/`transfers`/`transfer_items` | Помечены `get_index=true`/`get_single=true` на многих полях, но GET-эндпоинтов списков/деталей у них в API (§3 арх. и задании) нет — эти проекции «повиснут» до этапа 6 (отчёты). Не блокирует, но флаги опережают наличие эндпоинтов |
| К-5 | Архитектура §5.4 (к сведению, чужой scope) | Повторяю замечание К-6 этапа 1: в §5.4 всё ещё «RAISE InsufficientFunds ← режим настраивается», хотя ОВ-2 закрыт (жёсткая блокировка). Всплывёт на этапе 5, здесь не трогаю |

## 7. (в) Подтверждение стека и гейта

- **Django/DRF не использованы.** Новый код: `DeclarativeBase`/`Mapped[]`/`mapped_column` (модели этапа 1, не тронуты), Pydantic v2 (`BaseModel`, `ConfigDict(from_attributes=True)`), FastAPI (`APIRouter`, `Depends`, `Depends(require_admin)`), SQLAlchemy Core/`asyncpg` (`select`, `with_for_update`, `pg_insert(...).on_conflict_do_nothing`, `func.pg_advisory_xact_lock`). Ни `models.Model`, ни DRF-сериализаторов, ни Django-migrations.
- **Гейт контракта зелёный** (§4): `OK: backend code matches the data dictionary contract.`
- **Схему не менял** — заморожена и провалидирована боем; правок DDL/моделей не вносил.
- **6/6 сценариев на живой БД пройдены**, включая конкурентную защиту SV-1 (FOR UPDATE).

---

**Следующий шаг — этап 3 «Заявки/печать»:** `modules/issuance`, статусная машина `draft→to_print→printed→issued`, `issue()` + проводка (`ledger.post(−qty,'writeoff')`) одним UPDATE с `writeoff_id` (см. предупреждение о порядке в `04-backend-stage1.md` §finale и `02-database.md §7.1`). Ledger готов и проверен — списание при выдаче вызывает уже существующий `ledger.post`.
