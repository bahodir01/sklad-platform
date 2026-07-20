# 14. М7 «Пользователи» — CRUD + email (ОВ-12, часть CRUD+email)

Продолжение оборвавшейся сессии. Код (миграция, модель, схемы, репозиторий,
сервис, роутер) был уже написан ранее — не хватало ровно одного шага:
роутер `users` был импортирован в `app/main.py`, но не подключён через
`app.include_router(...)`, и миграция `0003_users_email` не была накачена на
живую БД. Оба пробела закрыты; остальной код переиспользован без переписывания.

## Что сделано в этом заходе

1. **`backend/app/main.py`** — добавлена строка
   `app.include_router(users_router, prefix=settings.api_prefix)` (роутер уже
   импортировался, но не подключался — из-за этого приложение видело только
   50 эндпоинтов вместо актуальных). После правки `app.openapi()["paths"]`
   даёт 53 пути / 70 эндпоинтов, из них `/users`, `/users/{id}`,
   `/users/{id}/reset-password` — 5 операций.
2. **Миграция `0003_users_email`** — применена на локальную БД
   (`alembic upgrade head`): 0002_batch_signature → 0003_users_email.
   `users.email` появился, частичный уникальный индекс
   `uq_users_email_not_null … WHERE email IS NOT NULL` создан.
3. **`backend/tests/test_users_crud.py`** — новый файл, 20 тестов на
   сервисном слое (по конвенции репозитория — все существующие тесты бьют
   в `UsersService`/`XxxService` напрямую через `SessionLocal()`, HTTP-слоя
   в pytest-наборе нет нигде, RBAC 403 проверен вручную curl'ом ниже).

Всё остальное (модель, миграция как файл, схемы `UserList/UserRead/UserCreate/
UserUpdate` в `modules/auth/schemas.py`, `modules/users/{repository,service,
router,schemas}.py`, запись в `build_dictionary.py`, регенерированные
`02-contract.json`/`02-data-dictionary.xlsx`) было готово от предыдущего
захода и проверено, а не переписано.

## Эндпоинты (`backend/app/modules/users/router.py`), все — `require_role(admin)`

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/v1/users` | список, фильтры `role`/`is_active`/`q` (ФИО/логин/email, ilike), пагинация |
| GET | `/api/v1/users/{id}` | деталь |
| POST | `/api/v1/users` | создание: email формат+домен `@npuu.uz` (`settings.email_domain`), INV-9 в схеме, Argon2id-пароль |
| PATCH | `/api/v1/users/{id}` | full_name/email/role/category/is_active; INV-9 на итоговом состоянии; самозащита админа |
| POST | `/api/v1/users/{id}/reset-password` | новый пароль ≥8 символов, гасит все refresh-сессии в Redis |

DELETE нет (стиль SV-8) — отключение только `PATCH is_active=false`.

## Проверка боем (curl, порт 8015, БД после прогона очищена от тестовых юзеров)

1. **`alembic upgrade head` → email-колонка есть.**
   ```
   Running upgrade 0002_batch_signature -> 0003_users_email
   ```
   `\d users` после апгрейда: колонка `email varchar(255)` NULL,
   индекс `uq_users_email_not_null UNIQUE btree (email) WHERE email IS NOT NULL`.

2. **`POST /users` (worker, `tw_test1@npuu.uz`) → 201; логин новым юзером работает.**
   ```
   POST /users → 201 {"id":106,...,"email":"tw_test1@npuu.uz","role":"worker",...}
   POST /auth/login {"username":"tw_test1","password":"pass1234"} → 200, access_token выдан
   ```

3. **Чужой домен → 422; дубль username → конфликт; admin с category → 422 (INV-9).**
   ```
   email @gmail.com          → 422 {"code":"email_wrong_domain",...}
   username "tw_test1" повтор → 422 {"code":"duplicate","message":"Логин \"tw_test1\" уже существует"}
   role=admin + category=worker → 422 {"code":"validation_error","msg":"...категория не указывается"}
   ```
   Примечание: `DuplicateError` в этом кодовой базе маппится в HTTP 422 (не 409) —
   это архитектурное решение `app/core/exceptions.py` (единый формат
   `{code, message, details}` для всех доменных ошибок, кроме `NotFoundError`=404
   и `ConflictError`=409 для гонок состояния типа SV-5); дубликат логина/email — тот
   же паттерн, что и во всех остальных модулях (catalog и т.д.), не отклонение.

4. **PATCH: смена ФИО/категории ок; admin деактивирует себя → 422.**
   ```
   PATCH /users/106 {"full_name":"...","category":"teacher","role":"teacher"} → 200
   PATCH /users/3 {"is_active": false} → 422 {"code":"self_deactivation_forbidden"}
   PATCH /users/3 {"role": "worker"}   → 422 {"code":"self_demotion_forbidden"}
   ```

5. **reset-password: старый пароль не работает, новый работает.**
   ```
   POST /users/106/reset-password {"password":"newpass99"} → 204
   POST /auth/login (старый пароль)  → 401 invalid_credentials
   POST /auth/login (новый пароль)   → 200, токен выдан
   ```

6. **teacher → GET /users → 403.**
   ```
   POST /auth/login (teach1/teach12345) → 200
   GET /users (Bearer teach-токен) → 403 {"code":"forbidden",...}
   ```

После прогона тестовый пользователь `tw_test1` (id=106) удалён вручную из БД —
в таблице `users` остались только сиды `admin` (id=3) и `teach1` (id=4).

## pytest

```
python -m pytest -q
........................................................................ [ 73%]
..........................                                               [100%]
98 passed in 18.83s
```

Из них 20 — новые (`tests/test_users_crud.py`): создание (валидный email,
неверный домен/формат, email=None валиден, дубль username/email, INV-9 в
схеме на create для admin+category и worker без category), правка (ФИО+
категория, самозащита деактивации/разжалования, деактивация чужого юзера,
переключение role→admin гасит category автоматически, обратное без category
отклоняется, чужой домен email на PATCH, 404 на несуществующего), сброс
пароля (смена хеша + погашение refresh-сессий через `RefreshTokenStore`),
список (фильтры role/is_active/поиск q), get/404.

БД после полного прогона `pytest` чиста (`clean_db` fixture подметает
`test_`-префиксные строки автоматически); сиды `admin`/`teach1` не тронуты
— проверено `SELECT id, username FROM users` после прогона: только 3/admin,
4/teach1.

## Гейт контракта

```
python .claude/skills/database-schema-design/assets/contract_validator_sqlalchemy.py \
  .feature-dev/02-contract.json \
  backend/app/modules/auth/models.py backend/app/modules/catalog/models.py \
  backend/app/modules/documents/models.py backend/app/modules/stock/models.py \
  backend/app/modules/issuance/models.py backend/app/modules/cash/models.py \
  backend/app/core/audit.py \
  backend/app/modules/catalog/schemas.py backend/app/modules/auth/schemas.py \
  backend/app/modules/documents/schemas.py backend/app/modules/stock/schemas.py \
  backend/app/modules/issuance/schemas.py backend/app/modules/cash/schemas.py

OK: backend code matches the data dictionary contract.
```

`build_dictionary.py` уже содержал строку `users.email` (доп. к
`04-backend-stage1.md`-набору) — регенерации не потребовалось, `02-contract.json`
и `02-data-dictionary.xlsx` от прошлого захода уже актуальны (одинаковый
таймстамп с `build_dictionary.py`).

## (а) Отклонения от инструкции

- HTTP-уровня (`AsyncClient`/`TestClient`) в pytest-наборе нет нигде во всём
  репозитории (все существующие suite-файлы, включая `test_cash.py`,
  `test_issuance_flow.py`, бьют напрямую в сервисный слой через
  `SessionLocal()` — так задокументировано в `tests/conftest.py`). Чтобы не
  ломать сложившуюся конвенцию суперпустячным исключением ради одного модуля,
  `test_users_crud.py` следует тому же стилю; сценарий «teacher → 403»
  проверен только curl'ом руками (см. §6 выше), а не автотестом — это
  осознанное соответствие стилю репозитория, а не забытая проверка.
- `DuplicateError` в этой кодовой базе отдаёт HTTP 422, а не 409 — до меня
  так было решено во всём `core/exceptions.py` (единственное исключение,
  `ConflictError`, зарезервировано под гонки состояния типа SV-5). Задача
  просила «дубль username → конфликт» — по смыслу условие выполнено
  (конфликт зафиксирован кодом `duplicate` и понятным текстом), но
  HTTP-статус не 409 — решил не отклоняться от установленного во всём
  проекте паттерна ради одного эндпоинта.

## (б) Вопросы

- Нет открытых вопросов по реализации — весь функционал по ТЗ и по
  инструкции этого захода закрыт и проверен.

## (в) Подтверждение

Django нигде не используется — весь стек SQLAlchemy 2.0 / Alembic /
Pydantic v2 / FastAPI. Гейт контракта зелёный, `pytest -q` — 98 passed,
0 failed, 0 skipped.
