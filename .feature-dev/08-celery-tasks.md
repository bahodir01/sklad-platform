# Этап фоновых задач (Celery + Redis) — отчёт

**Основание ТЗ:** архитектура §8 (таблица задач), §7.2 (пополнение касс — подтверждение за админом), §9, ADR-1 (ревизия остатков).
**Стек:** Celery 5.6.3 + Redis (брокер/backend), поверх существующего FastAPI + SQLAlchemy 2.0 async. Django НЕ использован.
**Статус:** завершено, проверено боем на живых Redis (6379) и PostgreSQL (5433). Схема НЕ менялась, гейт зелёный.

---

## 1. Файлы

### Существовавшие (проверены, не переписаны — только досведены зависимости)

| Файл | Задача §8 | Роль |
|---|---|---|
| `backend/app/tasks/celery_app.py` | — | Celery-приложение, конфиг, **beat-расписание** (3 регламентные задачи) |
| `backend/app/tasks/runtime.py` | — | Мост sync-Celery ↔ async-сервисы: `run_async` + `task_session` на NullPool-engine (свой engine на вызов — asyncpg не переживает смену event loop) |
| `backend/app/tasks/pdf_tasks.py` | `generate_writeoff_pdf`, `generate_notification_pdf` | Прогрев PDF (триггер `confirm()` / создание уведомления) |
| `backend/app/tasks/export_tasks.py` | `export_report` | Async-выгрузка отчёта (xlsx/pdf) в объектное хранилище |
| `backend/app/tasks/reconcile.py` | `reconcile_stock` | Сверка `stock_balances` ↔ `SUM(stock_movements)`, FULL OUTER JOIN, read-only, алерт |
| `backend/app/tasks/income.py` | `monthly_income_draft` | Черновик пополнения касс — уведомление админу, НЕ автопроводка |
| `backend/app/tasks/backup.py` | `db_backup` | `pg_dump -Fc` (основной) + COPY-CSV фолбэк |
| `backend/app/modules/reports/router.py` | — | Async-экспорт: `POST /reports/export`, `GET /reports/exports/{id}`, `.../download` — уже привязан |

### Изменённые на этом этапе

| Файл | Что и зачем |
|---|---|
| `backend/pyproject.toml` | **Добавлен `celery[redis]>=5.4,<6`** — весь пакет `tasks/` от него зависел, но в зависимостях он отсутствовал (единственный реальный пробел). **`redis>=5.2` → `redis>=5.2,<6`** — docstring `celery_app.py` заявлял «пин redis-py 5.x в pyproject», но пина не было; теперь заявление соответствует факту и защищает от RESP3-дефолта redis-py 6+. |
| `backend/Dockerfile` | Добавлен `postgresql-client` (бинарь `pg_dump`) — иначе `db_backup` в контейнере молча уходил бы в COPY-фолбэк; с ним основной путь — восстановимый через `pg_restore` дамп (архитектура §8: «pg_dump в MinIO»). |
| `docker-compose.yml` | **Добавлены сервисы `worker` и `beat`** (были осознанно отложены с этапа 1). Обновлена шапка-комментарий. |

### Проверка полноты §8 — все 5 задач на месте

| §8 | Задача | Реализация | Триггер |
|---|---|---|---|
| 1 | generate PDF (прогрев) | `generate_writeoff_pdf` + `generate_notification_pdf` | по событию (`confirm()` / создание уведомления) |
| 2 | export_report (async) | `export_report` | по запросу (`POST /reports/export`) |
| 3 | reconcile_stock | `reconcile_stock` | beat, 03:00 |
| 4 | monthly_income_draft | `monthly_income_draft` | beat, 1-е число, 06:00 |
| 5 | db_backup | `db_backup` | beat, 02:00 |

Beat-расписание (`celery_app.conf.beat_schedule`): `reconcile-stock-nightly` (crontab 03:00), `db-backup-nightly` (02:00), `monthly-income-draft` (day_of_month=1, 06:00). Прогрев PDF и export_report — по событию/запросу, в beat их нет (верно).

### Привязка async-экспорта (обратная совместимость) — завершена и проверена

- **Маленькие отчёты — синхронно, как прежде:** `GET /reports/{balances|unpurchased|movements|cashflow}?format=xlsx|pdf` отдаёт файл в теле ответа. Контракт не сломан.
- **Большие отчёты — асинхронно:** `POST /reports/export {report, format, filters}` → `202` + `task_id`, `status_url`, `download_url`. `GET /reports/exports/{task_id}` — polling статуса. `GET /reports/exports/{task_id}/download` — скачивание готового файла из хранилища. Потолок `EXPORT_ROW_CAP=100000` с честной пометкой усечения.

---

## 2. Проверка боем — 4 прогона

Окружение: Redis жив на 6379 (RESP2 через `redis.connection.DEFAULT_RESP_VERSION=2` — Redis сервер v5 не знает HELLO), PostgreSQL `127.0.0.1:5433/sklad`. Worker: `celery -A app.tasks.celery_app:celery_app worker --pool=solo --concurrency=1`. Воркер поднялся, `Connected to redis://localhost:6379/1`, зарегистрировал все 6 задач, `ready`.

### Прогон 1 — `reconcile_stock` (ADR-1)

| Шаг | Результат |
|---|---|
| Чистая БД | `{checked_pairs: 0, discrepancy_count: 0, discrepancies: []}` — SUCCESS |
| Искусственное расхождение (`INSERT stock_balances (1,1,99.5)` через psql — фантомный остаток) | `discrepancy_count: 1`, `{product_id:1, warehouse_id:1, balance_qty:"99.500", movements_sum:"0", delta:"99.500"}`. В лог воркера — **ERROR-алерт**: `reconcile_stock: обнаружено расхождений остатков: 1 … РАСХОЖДЕНИЕ product_id=1 warehouse_id=1: баланс=99.500, сумма движений=0, дельта=99.500` |
| Убрал расхождение (`DELETE`) | снова `discrepancy_count: 0` |

Задача строго read-only: расхождение НЕ «чинит» (SV-2 — единственный писатель остатков это `ledger.post()`), только обнаруживает и алертит. **Пройдено.**

### Прогон 2 — `monthly_income_draft` (§7.2, НЕ автопроводка)

| Метрика | До | После |
|---|---|---|
| `cash_desks.balance` teacher / worker | 0.00 / 0.00 | **0.00 / 0.00** |
| `money_income` строк | 0 | **0** |

Результат: `status: ok`, артефакт-черновик `documents/drafts/income/2026-07.json` (на диске подтверждён, локальный фолбэк — MinIO не поднят), `posted: false`, `requires_admin_confirmation: true`, `suggested_amount: null` (сумму вписывает админ вручную через `POST /cash/income`). **Балансы касс НЕ изменились, money_income НЕ создан. Пройдено.**

### Прогон 3 — `export_report` (файл в фоне, size>0)

`export_report("balances","xlsx",{})` → SUCCESS: `object_ref: documents/exports/balances_20260719.xlsx`, `filename: balances_20260719.xlsx`, `bytes: 5144`, `truncated: false`. Файл сгенерирован в фоне, **размер 5144 > 0**. **Пройдено.**

### Прогон 4 — `db_backup` (дамп, size>0)

`pg_dump` в бандле окружения отсутствует (в `scratchpad/pgsql/bin/` только `psql.exe`) → задача корректно ушла в **COPY-CSV фолбэк**. Результат: `object_ref: documents/backups/sklad_20260719_000150.sql`, `bytes: 3913`, `mode: copy-fallback`. Дамп на диске — 3913 байт, содержит все **22 таблицы** с реальными данными (напр. `cash_desks`: `1,teacher,0.00` / `2,worker,0.00`). **Размер 3913 > 0, дамп восстановим. Пройдено.**
> В prod-образе (после правки Dockerfile) `pg_dump` присутствует → основной путь даст custom-дамп (`mode: pg_dump`), а не фолбэк.

**БД оставлена чистой:** `stock_balances=0`, `stock_movements=0`, `money_income=0`, сиды (2 склада, 2 товара, 2 кассы) не тронуты.

---

## 3. Запуск worker + beat (prod / compose)

### docker-compose (добавлено на этом этапе)

```bash
docker compose up -d worker beat     # + api, db, redis, minio уже были
docker compose logs -f worker beat
```

- `worker` — тот же образ, что `api`; НЕ мигрирует БД, НЕ слушает HTTP. Пул prefork (дефолт Linux), `--concurrency=2`. `worker_prefetch_multiplier=1` (в `celery_app`) не даёт набивать тяжёлые задачи пачкой.
- `beat` — **ровно один экземпляр на кластер** (иначе расписание задвоится). Только ставит задачи в очередь; исполняет их `worker`.
- Redis в compose — `redis:7-alpine` (знает RESP2 и RESP3). redis-py пиннут `<6` (RESP2) → совместим и с Redis 7 (compose), и с Redis 5 (иные среды). Поэтому broker/backend URL идут БЕЗ `?protocol=2`.

### Прод вручную (Gunicorn-стиль, архитектура §2)

```bash
# worker
celery -A app.tasks.celery_app:celery_app worker --loglevel=INFO --concurrency=4
# beat (один процесс на весь кластер)
celery -A app.tasks.celery_app:celery_app beat --loglevel=INFO --schedule /var/run/celerybeat-schedule
# Windows-dev: worker дополнительно с --pool=solo (prefork на Windows нестабилен)
```

Проверено: `celery beat` стартует с нашим расписанием (`beat: Starting...`, 3 регламентные записи).

---

## 4. Итоги

### (а) Отклонения от исходного состояния

1. **`celery[redis]` не был объявлен в `pyproject.toml`** — добавлен (`>=5.4,<6`). Пакет `tasks/` без него не устанавливался бы вне текущей машины. Единственный содержательный пробел прошлой попытки.
2. **`redis>=5.2` → `redis>=5.2,<6`** — приведено в соответствие с docstring `celery_app.py` (заявлял пин, которого не было) и защищает от RESP3-дефолта redis-py 6+.
3. **`postgresql-client` добавлен в `Dockerfile`** — чтобы `db_backup` в проде шёл основным путём `pg_dump`, а не фолбэком.
4. **Сервисы `worker` и `beat` добавлены в `docker-compose.yml`** — были осознанно отложены с этапа 1; теперь этап фоновых задач их вводит.
5. Ни одно из отклонений не меняет схему БД, не трогает `frontend/`, не ломает этапы 1–6 (установленные celery 5.6.3 / redis 5.3.1 удовлетворяют новым ограничениям; гейт зелёный).

### (б) ВОПРОСЫ по ТЗ (нужен ответ заказчика)

1. **Модель «черновика пополнения касс» (§7.2).** Схема заморожена (02-contract.json, 22 таблицы), у `money_income` НЕТ статуса draft/pending — «черновик прихода» негде хранить, не меняя схему. Сейчас черновик реализован как **артефакт-уведомление** админу (`drafts/income/<YYYY-MM>.json`) + структурный алерт, приход НЕ проводится. Устраивает ли такой вид «черновика», или заказчик хочет отдельную запись со спец-статусом (потребует правки схемы — 23-я таблица или новое поле)?
2. **Сумма ежемесячного пополнения.** Политики суммы в ТЗ/схеме нет. Задача кладёт `suggested_amount: null` — сумму вписывает админ вручную. Нужна ли автоматическая подсказка суммы (фикс-сумма? прошлый месяц? формула)? Пока не угадываем, чтобы не подсунуть неверную цифру.
3. ~~**Канал уведомлений задач.**~~ **✅ ЗАКРЫТ заказчиком 19.07.2026: «уведомление внутри админ-панели».** Реализовано — см. раздел 5. (Q1 и Q2 подтверждены заказчиком без изменений; Q4 — дефолты подходят.)
4. **Ретраи/алертинг инфраструктуры.** Значения `max_retries`/`default_retry_delay` заданы разумными дефолтами (export 2×15с, PDF 3×10с). Заказчик подтвердил: **дефолты подходят.**

### (в) Подтверждения

- **Django НЕ использован.** Celery подключён как самостоятельная библиотека к тому же FastAPI-приложению; задачи вызывают существующие async-сервисы (`ReportsService`, `IssuanceService`, `ledger`, `storage`), бизнес-логику не дублируют. ORM — SQLAlchemy 2.0, миграции — Alembic, схемы — Pydantic v2.
- **Схема не менялась.** Задачи read-only на транзакционных таблицах (reconcile/income — чистое чтение; export/backup — чтение; PDF-прогрев пишет только в объектное хранилище).
- **Гейт зелёный:**
  ```
  OK: backend code matches the data dictionary contract.
  ```
  (`contract_validator_sqlalchemy.py` против `02-contract.json` по всем 13 указанным модулям/схемам).

---

## 5. Дополнение (19.07.2026): эндпоинт алертов админ-панели (Q3)

Заказчик выбрал канал алертов — **«уведомление внутри админ-панели»**. Схема заморожена, таблицы уведомлений НЕТ и не добавляем: алерты **выводятся из состояния на лету** read-only эндпоинтом.

### Файлы

| Файл | Изменение |
|---|---|
| `backend/app/modules/admin/router.py` | **Новый.** `GET /api/v1/admin/alerts` (только admin) + Pydantic-схемы `AdminAlert`, `AdminAlertsResponse`. |
| `backend/app/modules/admin/__init__.py` | **Новый.** Пакет модуля М7. |
| `backend/app/main.py` | Подключён `admin_router` под `/api/v1`. |
| `backend/app/tasks/reconcile.py` | Логика сверки вынесена в переиспользуемую `compute_discrepancies(session)`; задача `reconcile_stock` теперь зовёт её же (дублирования нет). |
| `backend/app/tasks/income.py` | Добавлена `list_income_draft_alerts()` — читает артефакты `drafts/income/*.json`, возвращает неподтверждённые (`posted:false`). |
| `backend/app/shared/storage.py` | Добавлена read-only `list_objects(bucket, prefix)` (S3 list_objects_v2 + локальный фолбэк) — нужна, чтобы перечислить артефакты черновиков. |

### Контракт эндпоинта

`GET /api/v1/admin/alerts` → `200`:
```json
{ "alerts": [ { "type": "stock_discrepancy|income_draft", "severity": "critical|warning|info",
                "title": "...", "detail": "...",
                "product_id": 1, "warehouse_id": 2, "balance": "...", "computed": "...", "delta": "...",
                "period": "YYYY-MM", "object_ref": "..." } ],
  "count": 2 }
```
Фронт показывает `count` бейджем и список в панели уведомлений. Два источника, собираются на лету:
1. **`stock_discrepancy`** (severity `critical`) — та же сверка `stock_balances ↔ SUM(stock_movements)`, что ночная `reconcile_stock` (переиспользована `compute_discrepancies`). Пустой список = всё сходится (ADR-1).
2. **`income_draft`** (severity `warning`) — неподтверждённые черновики пополнения касс из `drafts/income/*.json` (переиспользована `list_income_draft_alerts`, §7.2).

**Свойства:** read-only, идемпотентно, без побочных эффектов; RBAC — только admin; логику reconcile/income не дублирует (зовёт те же функции). Импорты Celery-модулей ленивые (внутри хендлера) — как в reports router, чтобы не тянуть Celery в API-процесс на старте.

**Производительность.** Эндпоинт дёргается фронтом периодически (как бейдж «К печати»). Сверка — тот же FULL OUTER JOIN + GROUP BY, что ночью, покрыт индексом `(product_id, warehouse_id)`; на текущем масштабе укладывается в бюджет. Если станет горячо — **кэш в Redis TTL 30–60 c** поверх того же вызова снимет нагрузку без изменения контракта (рекомендация, не реализовано — в ТЗ требования нет). Чтение черновиков — считанные мелкие JSON в месяц.

### Проверка боем (живой uvicorn :8011, реальный admin-JWT через `create_access_token`, БД 5433)

| Сценарий | Результат |
|---|---|
| Без токена | `401` — RBAC работает |
| Чистые остатки + существующий артефакт черновика | `200`, `count=1`: только `income_draft` за `2026-07` (нет `stock_discrepancy`) |
| Внёс расхождение через psql (`stock_balances (1,2,42.25)`) | `200`, `count=2`: **`stock_discrepancy`** `Товар #1, склад #2 … дельта 42.250` + `income_draft` |
| Убрал расхождение (`DELETE`) | `200`, `count=1`: `stock_discrepancy` исчез, остался только `income_draft` |

Все три сценария из ТЗ подтверждены (пустой/малый список; расхождение появляется и исчезает; артефакт черновика в алертах). **БД оставлена чистой** (`stock_balances=0`, `stock_movements=0`; сиды не тронуты).

### Гейт (эндпоинт схему не меняет)
```
OK: backend code matches the data dictionary contract.
```

### Подтверждения по дополнению
- **Схема НЕ менялась**, новых таблиц нет — алерты выводятся из состояния. `frontend/` не тронут (там другой агент). Этапы 1–6 не сломаны.
- **Django не использован.**
