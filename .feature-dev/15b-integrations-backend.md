# 15b. Бэкенд экрана «Интеграции» (§5а спеки15)

Основание: `.feature-dev/15-telegram-bot-spec.md` §5а. Схема (миграция 0004,
`.feature-dev/15a-schema-telegram.md`) уже накатана и не тронута — только
шифрование, сервис и три эндпоинта поверх готовой таблицы `integration_settings`.

## Что сделано

### 1. Шифрование — `backend/app/shared/crypto.py` (новый)
`encrypt_secret(plain) -> str` / `decrypt_secret(cipher) -> str` на Fernet
(`cryptography`). Ключ — `settings.integration_secret_key` (новая настройка
в `core/config.py`, `.env`-переменная `INTEGRATION_SECRET_KEY`, по тому же
принципу, что `jwt_secret`). Fernet требует ровно 32 «сырых» байта в
urlsafe-base64, а `INTEGRATION_SECRET_KEY` — произвольная строка (как
`JWT_SECRET`), поэтому реальный ключ Fernet — `SHA-256(INTEGRATION_SECRET_KEY)`,
детерминированно. `cryptography>=43` и `httpx>=0.28` (был только в `[dev]`)
добавлены в основные зависимости `pyproject.toml`. `.env.example` дополнен
`INTEGRATION_SECRET_KEY` с командой генерации.

### 2. Схемы — `backend/app/modules/admin/schemas.py` (новый)
- `IntegrationRead`: `kind, display_name, is_enabled, updated_at, masked_secret`.
  `masked_secret` — вычисляется сервисом (расшифровка + маска), не читается
  из БД напрямую нигде в схеме.
- `IntegrationUpdate`: `secret: str` (новый секрет в открытом виде — входной
  параметр запроса, сервис проверяет и шифрует).
- Обе — `__contract_table__ = None`: в `02-contract.json` у
  `integration_settings` ВСЕ атрибуты помечены `api.create=false`/
  `api.update=false` (обновление тут — сервисное действие «проверить и
  зашифровать», не прямая запись столбца), а `masked_secret`/`secret` вообще
  не столбцы. Тот же приём, что уже применён к `MoneyExpenseSubmission` в
  `cash/schemas.py`, задокументирован в докстрингах классов.

### 3. Сервис — `backend/app/modules/admin/service.py` (новый) — `IntegrationService`
- `list_all()` — обе строки, секрет только маской.
- `update_secret(kind, secret, admin_id)`:
  - `telegram` → `_verify_telegram_token`: `GET https://api.telegram.org/bot{token}/getMe`
    (httpx, таймаут 10 с) ДО записи в БД. `ok=false`/сетевая ошибка/невалидный
    JSON → `ValidationError` (422) с текстом Telegram как есть, секрет НЕ
    сохраняется. Успех → `display_name = result.username`.
  - `ai_search` → `_verify_ai_search_key`: облегчённая проверка формата
    (`sk-ant-...`, минимум 10 символов) без реального вызова Anthropic — по
    прямому указанию задачи; `display_name` фиксированно `"Anthropic API"`
    (реального имени модели без вызова API узнать неоткуда — см. «отклонения»).
  - В обоих случаях: `secret_encrypted = encrypt_secret(secret)`,
    `is_enabled = true`, `updated_by = admin_id`, commit.
  - `kind` не из `{telegram, ai_search}` → `NotFoundError` (404).
- `disable(kind, admin_id)` — только `is_enabled=false` + `updated_by`; секрет
  и `display_name` не трогает (повторный `PUT` без изменений в теле не нужен —
  достаточно снова прислать секрет, он перепроверяется и переустанавливает
  `is_enabled=true`).
- `mask_secret(kind, plain)` — `123456:AAE••••1234` для `telegram` (формат
  `<bot_id>:<token>`, видны id целиком + первые 3 и последние 4 символа
  токена), `sk-ant-••••ab12` для остальных (первые ≤7 + последние 4 символа).
  Секрет никогда не отдаётся целиком.

### 4. Эндпоинты — `backend/app/modules/admin/router.py` (дополнен, рядом с `GET /admin/alerts`)
Все под общим `dependencies=[Depends(require_admin)]` роутера (как и `/admin/alerts`):
- `GET /admin/integrations` → `list[IntegrationRead]`.
- `PUT /admin/integrations/{kind}` (тело `IntegrationUpdate`) → `IntegrationRead`.
- `POST /admin/integrations/{kind}/disable` → `IntegrationRead`.

Роутер уже подключён в `main.py` с этапа 13 (`admin_router`, `/api/v1`
префикс) — новый код ничего не меняет в `main.py`.

## Прогоны на живой БД (postgres:5433/sklad, миграция 0004 на входе, сервер :8016)

Сервер запущен `uvicorn app.main:app --port 8016` (не трогал существующий
процесс на :8000), env: `DATABASE_URL/REDIS_URL/JWT_SECRET/SECRET_KEY/
INTEGRATION_SECRET_KEY/PYTHONIOENCODING=utf-8` как в задаче. Логин
`admin/admin12345` (admin), `teach1/teach12345` (teacher) — dev-пароли из
`00-STATUS.md`.

**Baseline** `GET /admin/integrations` (до тестов):
```json
[{"kind":"ai_search","display_name":null,"is_enabled":false,"masked_secret":null},
 {"kind":"telegram","display_name":null,"is_enabled":false,"masked_secret":null}]
```

**(а) Заведомо невалидный telegram-токен:**
```
PUT /admin/integrations/telegram  {"secret":"not-a-real-token"}
→ 422 {"code":"validation_error","message":"Telegram отклонил токен: Not Found"}
```
БД после: `telegram.secret_encrypted` по-прежнему NULL (проверено psql) — не сохранён.

**(б) Валидный ПО ФОРМАТУ (`<цифры>:<строка>`), но фиктивный токен:**
```
PUT /admin/integrations/telegram  {"secret":"123456789:AAEfakefake...fk"}
→ 422 {"code":"validation_error","message":"Telegram отклонил токен: Unauthorized"}
```
Telegram реально ответил 401 на несуществующий bot id — транслировано в
понятный 422, не 500. Секрет не сохранён.

**(в) ai_search, фиктивный `sk-ant-test123`:**
```
PUT /admin/integrations/ai_search  {"secret":"sk-ant-test123"}
→ 200 {"kind":"ai_search","display_name":"Anthropic API","is_enabled":true,
       "masked_secret":"sk-ant-••••t123"}
```
`GET /admin/integrations` после — та же маска, секрет в открытом виде нигде
не отдан.

**(г) disable → повторный PUT включает заново:**
```
POST /admin/integrations/ai_search/disable
→ 200 {"is_enabled":false,"masked_secret":"sk-ant-••••t123"}   # секрет НЕ стёрт
PUT /admin/integrations/ai_search  {"secret":"sk-ant-test123"}
→ 200 {"is_enabled":true,"masked_secret":"sk-ant-••••t123"}
```

**(д) не-admin (teacher) → 403; плюс kind вне набора → 404:**
```
GET  /admin/integrations                          (teacher) → 403 forbidden
PUT  /admin/integrations/telegram                  (teacher) → 403 forbidden
POST /admin/integrations/nope/disable              (admin)   → 404 not_found
PUT  /admin/integrations/nope                       (admin)   → 404 not_found
```

**Секрет не логируется.** `grep` по логу uvicorn за весь прогон на строки
`sk-ant-test123`, `not-a-real-token`, `123456789:AAEfake...` — 0 совпадений;
в логе только метод/путь/статус (стандартный access-лог uvicorn).

**БД возвращена в чистое состояние** — `UPDATE integration_settings SET
secret_encrypted=NULL, display_name=NULL, is_enabled=false, updated_by=NULL`
для обеих строк, проверено повторным `GET /admin/integrations` (обе снова
`is_enabled:false, masked_secret:null`). Тестовый сервер на :8016 остановлен,
:8000 не трогал.

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
Итог: `OK: backend code matches the data dictionary contract.`

(Первый прогон дал `[unmatched]` для `IntegrationRead`/`IntegrationUpdate` —
валидатор не смог сопоставить имя схемы `Integration*` с классом модели
`IntegrationSetting` по умолчанию; исправлено явным `__contract_table__ =
None` с обоснованием в докстринге, см. «Что сделано» п.2.)

## (а) Отклонения от буквального текста задачи

1. **`ai_search.display_name` после PUT — фиксированная строка `"Anthropic
   API"`**, не «имя модели». Задача прямо разрешает не делать реальный вызов
   Anthropic на этом этапе («полноценную проверку... не обязателен реальный
   API-вызов»), а без вызова узнать реальное имя модели неоткуда. Когда
   следующий агент добавит реальный тестовый вызов при первом использовании
   поиска (спека15 §3a), он же может уточнить `display_name` по факту ответа
   Anthropic.
2. **Минимальная длина ai_search-ключа — 10 символов, не более строгая.**
   Задача сама даёт тестовый пример `sk-ant-test123` (14 символов) как
   валидный сценарий (в) — порог подобран так, чтобы это прошло, при этом
   отсекая пустой/обрезанный ввод (просто `"sk-ant-"` без хвоста).
3. **`IntegrationRead`/`IntegrationUpdate` помечены `__contract_table__ =
   None`**, хотя формально они проецируют часть колонок `integration_settings`.
   Причина в «Что сделано» п.2: контракт помечает ВСЕ атрибуты этой таблицы
   `api.create=false`/`api.update=false` (мутация здесь — сервисное действие,
   не прямая запись столбца), а `masked_secret`/`secret` не являются
   столбцами вовсе. Строгая построчная сверка `get_single`-флагов потребовала
   бы добавить в `IntegrationRead` `id`/`updated_by`, которых явно нет в
   составе схемы из задачи (§5а перечисляет ровно `kind, display_name,
   is_enabled, updated_at, masked_secret`) — решил довериться тексту задачи
   и явно опустить схему из строгой проверки, а не молча разойтись с ней.
4. **`httpx` продублирован из `[project.optional-dependencies].dev` в
   основные `dependencies`** — он нужен рантайму (`getMe`), а не только
   тестам; в `dev`-секции оставлен как был.

## (б) Вопросы к следующим агентам / заказчику

1. Когда `shared/ai_search.py` (спека15 §3a) появится и станет делать
   реальные вызовы Anthropic — стоит ли тогда обновлять `display_name`
   ai_search на что-то содержательное (имя модели) при следующем успешном
   вызове, а не только при `PUT`? Сейчас `display_name` фиксируется один раз,
   на момент сохранения ключа.
2. `disable` не трогает `secret_encrypted`/`display_name` намеренно (секрет
   переиспользуется при повторном включении). Если заказчик захочет отдельную
   операцию «удалить секрет полностью» (не просто выключить) — это новый
   эндпоинт, сейчас его нет ни в схеме, ни в задаче.

## (в) Django нет, гейт зелёный

Стек — FastAPI + SQLAlchemy 2.0 + Pydantic v2, как и во всём проекте. Django/
DRF нигде не использованы. Гейт (см. выше) — `OK`. Секрет проверен на
отсутствие в логах uvicorn за весь прогон (см. «Прогоны» выше) и не
возвращается в открытом виде ни в одном ответе API — только `masked_secret`.

## Файлы

- `backend/app/shared/crypto.py` (новый)
- `backend/app/modules/admin/schemas.py` (новый)
- `backend/app/modules/admin/service.py` (новый)
- `backend/app/modules/admin/router.py` (дополнен: 3 эндпоинта `/admin/integrations*`)
- `backend/app/core/config.py` (добавлена `integration_secret_key`)
- `backend/pyproject.toml` (добавлены `cryptography>=43`, `httpx>=0.28` в основные deps)
- `.env.example` (добавлена `INTEGRATION_SECRET_KEY`)
