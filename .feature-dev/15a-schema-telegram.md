# 15a. Схема: Telegram-бот + экран «Интеграции» (миграция 0004)

Основание: `.feature-dev/15-telegram-bot-spec.md` §2 (привязка по телефону) и §5а
(экран «Интеграции»). Только схема — сервис привязки, шифрование секретов, бот
и эндпоинты `/admin/integrations` делают следующие агенты.

## Что добавлено

### 1. `users.phone` (спека15 §2)
- `varchar(20)`, `nullable=True`.
- `CHECK ck_users_phone_format`: `phone IS NULL OR phone ~ '^\+\d{9,15}$'` —
  базовый заслон от мусора (PostgreSQL ARE поддерживает `\d`). Полную
  нормализацию (пробелы/скобки/локальные форматы ввода админом → E.164)
  делает сервис при сохранении, не БД — по требованию задачи.
- Частичный уникальный индекс `uq_users_phone_not_null WHERE phone IS NOT NULL`
  (несколько NULL не конфликтуют, как у `email`).
- API: `get_index=get_single=create=update=true` — админ вносит/правит телефон
  через модуль «Пользователи».

### 2. `users.telegram_chat_id` (спека15 §2)
- `bigint`, `nullable=True`, частичный уникальный индекс
  `uq_users_telegram_chat_id_not_null WHERE telegram_chat_id IS NOT NULL`.
- API: `get_single=true`, всё остальное `false` — сервисное поле, пишет
  только бот в момент привязки, не обычный CRUD пользователя.
- Вместе с `phone` даёт уникальность в обе стороны (один Telegram-аккаунт —
  один пользователь и наоборот), как требует §2.

### 3. `integration_settings` (спека15 §5а)
Одна строка на тип интеграции:
`id, kind (varchar(32) UNIQUE), secret_encrypted (text NULL), display_name
(varchar(255) NULL), is_enabled (boolean NOT NULL default false), updated_by
(FK → users, ON DELETE RESTRICT, nullable), updated_at (timestamptz, NOT NULL,
server_default=now(), onupdate=now())`.

`kind` — обычный `varchar`, не enum (по прямому требованию спеки: набор типов
интеграций может расшириться INSERT-ом новой строки, без `ALTER TYPE`).
Уникальность `kind` — единственный механизм, гарантирующий «ровно одна строка
на тип». Миграция 0004 сеет ровно две строки — `telegram` и `ai_search`,
`is_enabled=false`, `secret_encrypted=NULL`, `updated_by=NULL` — по аналогии с
seed двух `cash_desks` в 0001. Схема шифрованием не занимается: колонка хранит
уже готовый шифротекст, ключ — у сервиса из `.env`.

Модель `IntegrationSetting` размещена в `backend/app/modules/admin/models.py` —
том же модуле, где уже живёт роутер алертов (`admin/router.py`, фича 13): экран
«Интеграции» — часть той же зоны «Администрирование». Pydantic-схемы для
`integration_settings` (Read с маской секрета, Create/Update с новым секретом)
не созданы — их добавляет следующий агент вместе с эндпоинтами
`GET/PUT/POST /admin/integrations`.

## Изменённые/созданные файлы

- `backend/app/modules/auth/models.py` — добавлены колонки `phone`,
  `telegram_chat_id`, CHECK и два частичных уникальных индекса на `User`.
- `backend/app/modules/auth/schemas.py` — `phone` добавлен в
  `UserList/UserRead/UserCreate/UserUpdate`, `telegram_chat_id` — только в
  `UserRead` (read-only, сервисное поле). Валидация телефона в схеме зеркалит
  CHECK в БД (`PHONE_PATTERN`).
- `backend/app/modules/admin/models.py` (новый) — модель `IntegrationSetting`.
- `backend/app/models.py` — реестр: импорт `IntegrationSetting`, счётчик таблиц
  23 → 24.
- `backend/alembic/versions/0004_telegram_bot.py` (новый) — миграция поверх
  0003, полностью обратимая.
- `.feature-dev/build_dictionary.py` — новые строки `users.phone`,
  `users.telegram_chat_id`, таблица `integration_settings` (6 атрибутов).
- `.feature-dev/02-contract.json`, `.feature-dev/02-data-dictionary.xlsx` —
  перегенерированы (155 строк, 24 таблицы).

## Прогоны на живой БД (postgres:5433/sklad, 0003 на входе)

1. **`alembic upgrade head`** — 0003 → 0004, без ошибок.
   `alembic current` → `0004_telegram_bot (head)`.
2. **psql-инспекция**:
   - `users`: колонки `phone varchar(20)`, `telegram_chat_id bigint` на
     месте; индексы `uq_users_phone_not_null`, `uq_users_telegram_chat_id_not_null`
     (оба `UNIQUE ... WHERE ... IS NOT NULL`); CHECK
     `ck_users_phone_format` присутствует.
   - `integration_settings`: таблица создана, PK, `UNIQUE(kind)`,
     `FK updated_by → users.id ON DELETE RESTRICT`; ровно 2 строки —
     `telegram`/`ai_search`, `is_enabled=false`.
   - **CHECK боем**: `INSERT ... phone = 'not-a-phone'` →
     `ОШИБКА: ... нарушает ограничение-проверку "ck_users_phone_format"` (отбит).
     `phone = '+998901234567'` → принят.
   - **UNIQUE боем**: повторный `phone`/`telegram_chat_id` → оба отбиты
     `ограничение уникальности uq_users_..._not_null`; вторая строка с обоими
     полями `NULL` — принята (частичный индекс NULL не считает).
   - Тестовые строки удалены, финальная проверка `count(*) WHERE username LIKE
     'test_%' = 0` — БД чистая.
3. **`downgrade -1` → `upgrade head`**: после downgrade `users` вернулась к
   9 колонкам ровно как в 0003 (phone/telegram_chat_id и их индексы/CHECK
   исчезли), `integration_settings` исчезла целиком (`\dt` → «не найдена»).
   `alembic current` → `0003_users_email`. Повторный `upgrade head` прошёл
   без ошибок, seed `integration_settings` пересоздан (2 строки), БД снова
   на `0004_telegram_bot (head)`.
4. **`python .feature-dev/build_dictionary.py`** → `rows: 155 | tables: 24`,
   оба артефакта перезаписаны.
5. **Импорт реестра**: `app.models.Base.metadata.tables` → 24 таблицы, включая
   `integration_settings` — alembic `env.py` (импортирует `app.models`) увидит
   новую таблицу для будущих `autogenerate`-сверок.

## Гейт

```
python .claude/skills/database-schema-design/assets/contract_validator_sqlalchemy.py \
  .feature-dev/02-contract.json \
  backend/app/modules/auth/models.py backend/app/modules/catalog/models.py \
  backend/app/modules/documents/models.py backend/app/modules/stock/models.py \
  backend/app/modules/issuance/models.py backend/app/modules/cash/models.py \
  backend/app/modules/admin/models.py backend/app/core/audit.py \
  backend/app/modules/catalog/schemas.py backend/app/modules/auth/schemas.py \
  backend/app/modules/documents/schemas.py backend/app/modules/stock/schemas.py \
  backend/app/modules/issuance/schemas.py backend/app/modules/cash/schemas.py \
  backend/app/modules/users/schemas.py
```

Итог: `OK: backend code matches the data dictionary contract.`

Путь `backend/app/modules/users/models.py` из шаблона задачи не существует —
модель `User` живёт в `backend/app/modules/auth/models.py` (проверено Glob'ом,
это тот же файл, что уже нёс `email` с этапа М7); использован реальный путь.
Добавлен `backend/app/modules/admin/models.py` в список — иначе валидатор не
увидел бы класс `IntegrationSetting` и упал бы на `[table] 'integration_settings'
... has no mapped class`.

Первый прогон гейта (до правки `auth/schemas.py`) дал 5 ожидаемых
`[api]`-несовпадений: `UserCreate/UserList/UserRead/UserUpdate` не знали про
`phone`/`telegram_chat_id`. Это НЕ тот же случай, что `integration_settings`
(совсем новая таблица без единой схемы, для неё отсутствие Read/Create — норма
по прямому указанию задачи): здесь схемы `User*` уже существуют и раньше
проходили гейт, а я добавил колонки в уже контрактный класс — поэтому дополнил
`auth/schemas.py` (только объявления полей + `PHONE_PATTERN`, зеркалящий CHECK;
без сервисной логики), чтобы не оставлять существующий модуль в красном
состоянии.

## (а) Отклонения от буквального текста задачи

1. **`updated_by` сделан `nullable=True`**, хотя в тексте задачи он просто
   «→ users (ondelete RESTRICT)» без явного указания nullable. Причина:
   миграция сеет строки `telegram`/`ai_search` ДО того, как какой-либо админ
   их настраивал — `updated_by` физически некого проставить. Альтернатива
   (не сеять строки миграцией, создавать их лениво при первом
   GET/PUT сервисом) усложнила бы следующий этап без выигрыша — решил сеять,
   как `cash_desks` в 0001, и сделать `updated_by`/`secret_encrypted`/
   `display_name` nullable для «ещё не настроенного» состояния.
2. **`secret_encrypted` — `nullable=True`**, по той же причине (сид-строки без
   секрета). Спека это не проговаривает явно, но подразумевает («секрет
   маскируется» предполагает, что секрета может не быть).
3. **`auth/schemas.py` тронут**, хотя задача просила «только схема БД» и
   явно разрешила пропустить Pydantic-схемы только для `integration_settings`.
   Разрешил себе минимальную правку (объявления полей, без бизнес-логики),
   потому что иначе гейт для уже существующего модуля `users` остался бы
   красным — что явно противоречит требованию «Гейт: ... (ожидается exit 0)».

## (б) Вопросы к следующим агентам / заказчику

1. **Формат нормализации `phone`** — задача (§8 «Открытые мелочи») оставляет
   это на службу; CHECK в БД принимает `+` и 9-15 цифр, но не проверяет код
   страны/оператора. Если понадобится более строгая проверка (например, только
   `+998`), это отдельная миграция на CHECK — сейчас сознательно широкий диапазон.
2. **`integration_settings.secret_encrypted` тип `text`** — задача допускала
   `bytea/text`; выбран `text`, т.к. симметричное шифрование (Fernet и
   аналоги) обычно даёт base64-строку, которую удобнее хранить текстом, чем
   бинарником. Если сервис шифрования следующего этапа выберет сырые байты
   (AES-GCM без base64-обёртки) — потребуется миграция типа на `bytea`.
3. **Сид `integration_settings` двумя строками при миграции vs ленивое
   создание сервисом** — выбран сид (см. «отклонения» выше). Если
   `backend-architect`/сервисный агент предпочтёт паттерн «строка создаётся
   при первом сохранении» (`INSERT ... ON CONFLICT DO UPDATE`), сид не мешает:
   `UNIQUE(kind)` всё равно не даст завести вторую строку одного типа, апсерт
   просто обновит существующую.

## (в) Django нет, миграция обратима

Стек — SQLAlchemy 2.0 / Alembic / Pydantic v2 / PostgreSQL 16, как и во всех
предыдущих ревизиях; Django ORM/DRF нигде не использован. `downgrade()`
миграции 0004 прогнан и подтверждён боем (шаг 3 выше): полностью убирает
`integration_settings`, обе колонки `users`, их CHECK и оба частичных
индекса, возвращая `users` в точности к состоянию 0003.
