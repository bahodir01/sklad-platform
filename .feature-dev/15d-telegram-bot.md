# 15d. Telegram-бот (спека15 §2-§4, §6) — финальный бэкенд-этап фичи

Основание: `.feature-dev/15-telegram-bot-spec.md` целиком, `15b-integrations-
backend.md` (`IntegrationService.get_active_secret`/`decrypt_secret`), `15c-
ai-search.md` (`resolve_product_query(session, query, warehouse_id)`).
Схема НЕ менялась (ни один `models.py`/миграция не тронуты), `frontend/` не
тронут.

## Архитектура процесса (спека15 §6)

Отдельный долгоживущий asyncio-процесс, **polling**, НЕ встроен в uvicorn/
FastAPI worker, НЕ Celery-задача. Библиотека — `aiogram>=3` (установлена
`aiogram==3.30.0`, добавлена в `backend/pyproject.toml` основные зависимости).

```
backend/app/bot/
  __init__.py
  main.py       — entrypoint, `python -m app.bot.main`
  handlers.py   — aiogram Router, все диалоги (тонкий слой)
  logic.py      — бизнес-склейка БЕЗ единого импорта aiogram (тестируется напрямую)
  states.py     — FSM-состояния (IssuanceStates, ExpenseStates)
  keyboards.py  — reply/inline-клавиатуры
```

**Управление стартом/остановом через `integration_settings` (kind='telegram')**
(`app/bot/main.py`):
- при старте процесс читает токен и `is_enabled` через
  `IntegrationService.get_active_secret("telegram")` — тот же метод, что уже
  использует `modules/ai/service.py` для `ai_search`;
- выключено/токена нет → polling НЕ запускается, процесс ждёт 30с и
  перепроверяет БД в цикле (`run()`);
- пока polling идёт, фоновая задача `_watch_and_stop` раз в 30с
  перечитывает `is_enabled`; если админ выключил интеграцию через
  `POST /admin/integrations/telegram/disable` — `dispatcher.stop_polling()`
  останавливает бота БЕЗ перезапуска контейнера (задержка до 30с), процесс
  возвращается в цикл ожидания, не завершается.

**Зафиксированный компромисс.** Если админ меняет САМ ТОКЕН на уже
запущенном боте (не просто вкл/выкл), новый токен подхватится только после
рестарта процесса — hot-reload токена без рестарта не реализован. На
масштабе школы смена токена — редкая операция; в `docker-compose.yml`
добавлен сервис `bot` (`restart: unless-stopped`, образ общий с `api`),
рестарт — `docker compose restart bot` вручную или супервизором. Это прямо
разрешено текстом задачи («НЕ обязательно встраивать hot-reload... процесс
перезапускается вручную/супервизором после смены токена — это нормально для
этого масштаба»).

`docker-compose.yml`: добавлен `INTEGRATION_SECRET_KEY` в окружение сервиса
`api` (раньше отсутствовал явно, полагался на дефолт `Settings` — оставлено
консистентно тем же дефолтом) и сервису `bot` — ОБА расшифровывают один и
тот же `integration_settings.secret_encrypted`, ключ обязан совпадать.

## Диалоги (по спеке, `app/bot/handlers.py` + `app/bot/logic.py`)

### Привязка (§2)
`/start` (`cmd_start`) → если `telegram_chat_id` уже привязан
(`logic.find_user_by_chat_id`) — приветствие/отказ через общий
`_greet_or_reject`; иначе — reply-кнопка `request_contact` (`kb.
request_phone_keyboard`).

`on_contact` (любое сообщение с `message.contact`): отклоняет пересланный
ЧУЖОЙ контакт (`contact.user_id != message.from_user.id`) — не в спеке
буквально, но защищает от подтверждения чужого номера чужим Telegram;
нормализует телефон (`logic.normalize_phone`) → `logic.bind_telegram_account`:
- телефон не найден → «Ваш номер не найден в системе. Обратитесь к
  администратору.», кнопка привязки остаётся (повторная попытка разрешена);
- найден, `is_active=false` → «обратитесь к администратору»;
- найден, `role=admin` → вежливый отказ, бот только для teacher/worker
  (**и `telegram_chat_id` НЕ записывается** — `bind_telegram_account`
  проверяет `is_active`/`role` ДО записи, отказ формируется тем же
  `_greet_or_reject`, что и для повторного `/start`);
- найден, активен, teacher/worker → пишет `telegram_chat_id`, «Здравствуйте,
  {full_name}, вы авторизованы как {роль на русском}» + главное меню;
- гонка (chat_id уже занят ДРУГИМ пользователем, партиционный UNIQUE) →
  `IntegrityError` ловится, «Этот Telegram-аккаунт уже привязан к другому
  пользователю», исходная привязка не тронута.

Формат нормализации (спека15 §8, открытая мелочь): `logic.normalize_phone`
убирает всё, кроме цифр и `+`, разворачивает `00`-префикс в `+`, добавляет
`+`, если его нет (Telegram обычно шлёт `contact.phone_number` БЕЗ `+`) —
приводит к формату `^\+\d{9,15}$`, тому же, что `ck_users_phone_format`.

### Главное меню
Reply-клавиатура «📦 Заявка на товар» / «💵 Расход денег»
(`kb.main_menu_keyboard`). Оба пункта проходят общий guard
`_require_employee` (привязан + активен + не admin) — повторная проверка на
КАЖДОЕ действие, не только при `/start` (защита от «админ деактивировал
пользователя посреди диалога»).

### Заявка на товар (§3, §3a)
FSM `IssuanceStates` строго по спеке: `choosing_warehouse` (inline только
`allows_issuance=true` через `logic.list_issuance_warehouses`) →
`entering_product_query` (текст → `resolve_product_query(session, query,
warehouse_id)` из `modules/ai/service.py`, до 5 кандидатов кнопками +
«Показать весь список» ВСЕГДА в клавиатуре, даже при пустом результате) →
`choosing_product` (выбор кнопкой ИЛИ пагинация `find_all_paginated` по
`prodlist:{page}`) → `entering_qty` (`logic.parse_positive_decimal` — число
> 0 ДО отправки на сервер, спека15 §3 п.4) → `entering_reason` (непустой
текст) → резюме + «✅ Отправить»/«❌ Отмена» (`confirming`) → на «Отправить»:
`logic.submit_issuance_request` = `IssuanceService.create_request` +
`.confirm_request` от имени привязанного пользователя (`employee_id`
берётся заново из `telegram_chat_id` в момент подтверждения, не из старых
данных состояния — на случай, если пользователь стал недоступен между
шагами) → «Заявка REQ-000123 отправлена, ждите выдачи.» Отказ сервера
(`DomainError`, напр. SV-9 «склад не для заявок», 422) → `exc.message`
текстом как есть, состояние очищается, диалог не рвётся — новую заявку
можно начать через меню. Неожиданное исключение — тоже не роняет процесс
(`except Exception` + `logger.exception`, дружелюбный текст).

Одна заявка = одна позиция (`items=[RequestItemCreate(...)]`) — известное
упрощение по спеке, не усложнено.

### Расход денег (§4)
FSM `ExpenseStates`: `choosing_category` (активные `expense_categories`) →
`entering_amount` (число > 0) → `entering_description` (непустой текст) →
`waiting_photo` (ждёт `message.photo`; НЕ-фото при этом состоянии →
отдельный хендлер `expense_reject_non_photo` переспрашивает, диалог не
рвётся) → на фото: `bot.get_file` + `bot.download_file` → байты в
`FSMContext` (MemoryStorage хранит объекты в памяти процесса, не
JSON-сериализует — `bytes` совместимы без доп. кодирования) → резюме +
подтверждение → `logic.submit_cash_expense` = `CashService.create_expense`
с `receipt_bytes` (НЕ через HTTP multipart — тот же сервисный вызов на
уровне байтов, которого просила задача) → ответ суммой; `InsufficientFunds`
(тоже `DomainError`) — тем же путём, текстом как есть.

Дата расхода не запрашивается диалогом (спека15 §4 не описывает такой шаг) —
`logic.submit_cash_expense` подставляет `dt.date.today()` сама (параметр
`date` опционален, по умолчанию сегодня).

## Проверка — БЕЗ реального Telegram-токена (см. `INTEGRATION_SECRET_KEY`/БД: `ai_search.is_enabled=false`, `telegram` не настроен вовсе)

Токена нет физически в этой среде — то, что проверено РЕАЛЬНЫМ вызовом
aiogram/сети, и то, что проверено прямым вызовом бизнес-логики, разделено
честно:

**1. Прямой вызов aiogram-хендлеров с фейковыми `Message`.** `cmd_start` и
`on_contact` вызваны НАПРЯМУЮ (не через `Dispatcher`/`Bot`/сеть) с
дуцк-тайпнутым `SimpleNamespace` вместо `aiogram.types.Message`
(`.chat.id`, `.from_user.id`, `.contact`, `.answer` = `AsyncMock()`) и
НАСТОЯЩИМ `aiogram.fsm.context.FSMContext` на `MemoryStorage` (реальная
aiogram FSM-машинерия, не мок). Сценарии:
   - `/start` непривязанным чатом → кнопка «отправить телефон»
     (`test_handler_start_unbound_prompts_phone_button`);
   - привязка ПО РЕАЛЬНОМУ ТЕЛЕФОНУ teach1 (`id=4`), проставленному через
     `UsersService.update(..., UserUpdate(phone=...))` — сервисный слой,
     который вызывает `PATCH /users/{id}` (роутер добавляет только
     `require_admin` поверх того же вызова) — хендлер реально пишет
     `telegram_chat_id` в БД, ответ содержит «здравствуйте»/«учитель»
     (`test_handler_on_contact_binds_known_phone_and_greets`);
   - непривязанный номер → «не найден» (`test_handler_on_contact_
     unknown_phone_rejected`);
   - номер администратора → вежливый отказ, `telegram_chat_id` НЕ
     записывается (`test_handler_on_contact_admin_gets_polite_refusal`).
   Телефон teach1/admin ставится и ГАРАНТИРОВАННО откатывается в `finally`
   (`_clear_binding`) — сид не остаётся изменённым ни при успехе, ни при
   падении теста.

**2. Прямой вызов бизнес-функций `app/bot/logic.py` против живой БД**
(postgres:5433/sklad) — без единого импорта aiogram в самом модуле:
   - `normalize_phone`/`parse_positive_decimal` — табличные юнит-тесты
     форматов (с `+`, без `+`, `00`-префикс, пробелы/скобки, запятая вместо
     точки, мусор, 0/отрицательное);
   - `bind_telegram_account`: успех (уже описан выше на уровне хендлера,
     здесь — тот же сценарий на уровне функции), незнакомый телефон,
     admin (не пишет chat_id), `is_active=false` (TEST_-пользователь, не
     пишет chat_id), гонка «chat_id уже занят другим пользователем»
     (`worker_user` фикстура + teach1, второй `bind` получает
     `"chat_taken"`, первая привязка не пострадала);
   - `submit_issuance_request`: ПОЛНЫЙ цикл `create_request` +
     `confirm_request` на реальных данных сида (`WAREHOUSE_ISS`,
     `PRODUCT_ID`, `TEACHER_ID`) — после вызова заявка ПРОВЕРЕНА ПРЯМЫМ
     SQL-запросом к `requests`/`request_items` (статус `to_issue`, одна
     позиция, `qty`, `product_id`, `warehouse_id`, `employee_id`), плюс
     негативный сценарий SV-9 (склад без `allows_issuance` → `ValidationError`
     `warehouse_not_issuance` — тот же путь, каким прошёл бы диалог, если бы
     разрешил выбрать неверный склад);
   - `submit_cash_expense`: приход на кассу teacher → расход через
     `logic.submit_cash_expense` с фейковыми PNG-байтами (валиден по magic
     bytes `storage.sniff_receipt`) → баланс кассы списан, `receipt_url`
     заполнен (проверено прямым запросом `CashDesk` после вызова); плюс
     `InsufficientFunds` при сумме сверх баланса — баланс и чек НЕ созданы.

**3. Импорт модуля.** `test_bot_module_imports_without_error` (и ручной
прогон `python -c "from app.bot.main import run, main; from app.bot import
handlers, ..."` до написания тестов) — `app/bot/*` импортируется без ошибок,
`aiogram==3.30.0` установлен и работает, Router содержит 27 наблюдателей
(`handlers.router.observers`).

**Не проверено (честно).** Реальный polling против настоящего Telegram API
(нет токена — задача явно это допускает), диалоги `issuance_confirm`/
`expense_confirm`/выбор склада/товара/категории кнопками ЧЕРЕЗ настоящий
`CallbackQuery` (эти шаги проверены на уровне вызываемых ими функций
`logic.submit_issuance_request`/`logic.submit_cash_expense`/`resolve_
product_query`, а не через сам aiogram callback-хендлер — задача явно
допускает такой уровень, если полный mock aiogram избыточно хрупок;
callback-хендлеры (`issuance_pick_warehouse`, `expense_pick_category` и
т.д.) — тонкие обёртки в 3-5 строк над теми же функциями, риск расхождения
между «протестированной функцией» и «непротестированной оберткой» низкий).

## Результаты pytest

```
backend/tests/test_bot_logic.py — 30 passed
Полный прогон (98 существующих + 30 новых) — 128 passed in ~26s
```

БД после прогона проверена `psql`: `users` (id=3 admin, id=4 teach1) —
`phone`/`telegram_chat_id` снова `NULL` у обоих (тестовые значения
откатываются в `finally` каждого теста, который их ставит); `requests`,
`money_expense` — `0` строк (стандартная `clean_db`-очистка `conftest.py`
подмела всё транзакционное). Тестовый телефон teach1 НЕ оставлен — решено
откатывать, чтобы не плодить побочный эффект между независимыми прогонами
задач (в отличие от допущения задачи «можно оставить»).

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
Итог: `OK: backend code matches the data dictionary contract.` (бот не
добавляет ни моделей, ни Pydantic-схем таблиц — `app/bot/*` вне контракта,
гейт запущен, чтобы подтвердить, что существующие модули не задеты).

## (а) Отклонения от буквального текста задачи

1. **Отклонение пересланного чужого контакта** (`on_contact`:
   `contact.user_id != message.from_user.id`) — не описано в спеке
   буквально, добавлено как здравая защита: иначе учитель мог бы переслать
   боту контакт-карточку ЧУЖОГО номера и привязать её к своему аккаунту.
2. **`_require_employee` перепроверяет привязку/активность/роль НА КАЖДОЕ**
   действие меню, не только на `/start`** — спека описывает разовую
   проверку при привязке, но состояние пользователя (`is_active`, роль)
   может измениться администратором посреди диалога; без повторной проверки
   деактивированный сотрудник продолжил бы создавать заявки до следующего
   `/start`.
3. **Хендлер `expense_reject_non_photo`** (переспрос при не-фото на шаге
   ожидания чека) — прямое требование спеки §4 п.4, реализовано отдельным
   хендлером на том же состоянии, а не веткой внутри одного.
4. **Показ «Показать весь список» ВСЕГДА в клавиатуре после текстового
   поиска**, даже когда подстрока/ИИ дали результат — спека говорит «всегда
   доступна как ручная альтернатива на любом шаге» (§3 п.3), поэтому кнопка
   не исчезает даже при удачном совпадении (учитель мог не узнать нужный
   товар среди 5 кандидатов).
5. **`INTEGRATION_SECRET_KEY` добавлен в окружение сервиса `api`** в
   `docker-compose.yml` (раньше отсутствовал явно, полагался на дефолт
   `Settings`) — сделано для явной консистентности с новым сервисом `bot`:
   оба обязаны использовать ОДИН ключ шифрования, дефолт `Settings`
   формально совпал бы и без явного объявления, но неявная зависимость
   «два сервиса случайно используют один и тот же хардкод» показалась
   хрупкой при будущей правке `.env`.
6. **FSM-хранилище — `MemoryStorage`** (не Redis) — состояние диалога
   теряется при перезапуске процесса бота. Спека не требует конкретного
   хранилища; на масштабе школы (десятки сотрудников, короткие диалоги)
   это приемлемо и согласуется с уже принятым компромиссом «перезапуск
   процесса при смене токена» (§6) — оба случая означают «начните диалог
   заново через меню», не потерю данных.

## (б) Вопросы к заказчику / следующим агентам

1. **Reply-клавиатура «Заявка на товар» / «Расход денег» не может
   переключить диалог ПОСРЕДИ FSM-состояния** (её текст не обрабатывается
   отдельным хендлером с `StateFilter("*")`, если конкретный `IssuanceStates
   .entering_qty`/`ExpenseStates.entering_amount` и т.п. уже зарегистрирован
   раньше с фильтром "любой текст" на СВОЁМ состоянии — порядок регистрации
   в `handlers.py` ставит `menu_issuance`/`menu_expense` РАНЬШЕ
   состояние-специфичных хендлеров, так что переключение меню посреди
   диалога РАБОТАЕТ, но явного теста на этот конкретный сценарий (набор
   количества → вдруг нажал «Расход денег») нет — стоит добавить, если
   заказчик считает этот путь частым.
2. **Пагинация «Показать весь список» использует размер страницы 8**
   (`_PRODUCT_PAGE_SIZE` в `handlers.py`) — спека не фиксирует число,
   выбрано произвольно (Telegram inline-клавиатура визуально не должна
   быть слишком длинной). Легко поменять.
3. **`15b-integrations-backend.md` формулирует** («`PUT /admin/integrations/
   telegram` ... поднимает/перезапускает polling-процесс») **то, чего сам
   HTTP-эндпоинт физически не делает** (он лишь пишет БД) — бот-процесс
   ЭТОЙ задачи сам вычитывает `is_enabled` раз в 30с, так что «поднимает»
   происходит косвенно (до 30с задержки) для включения, а не мгновенно по
   вызову API. Если заказчику нужна мгновенная реакция на `PUT`/`disable` —
   потребуется межпроцессное уведомление (Redis pub/sub от api-контейнера
   к bot-контейнеру), сознательно не реализовано (не было в скоупе явного
   ТЗ на бота, только на 15b).

## (в) Django нет, гейт+существующие 98 тестов зелёные

Стек — FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 + aiogram 3, как и во
всём проекте. Django/DRF нигде не использованы. Гейт (см. выше) — `OK`.
Полный прогон `pytest`: **128 passed** (98 существующих ДО этой задачи +
30 новых в `tests/test_bot_logic.py`), ни один существующий тест не
изменён и не сломан.

## Файлы

- `backend/app/bot/__init__.py` (новый)
- `backend/app/bot/main.py` (новый) — entrypoint, `python -m app.bot.main`
- `backend/app/bot/handlers.py` (новый) — aiogram Router, все диалоги
- `backend/app/bot/logic.py` (новый) — бизнес-склейка (без импорта aiogram)
- `backend/app/bot/states.py` (новый) — `IssuanceStates`, `ExpenseStates`
- `backend/app/bot/keyboards.py` (новый) — reply/inline-клавиатуры
- `backend/tests/test_bot_logic.py` (новый) — 30 тестов
- `backend/pyproject.toml` (добавлен `aiogram>=3` в основные зависимости)
- `docker-compose.yml` (добавлен сервис `bot`; добавлен
  `INTEGRATION_SECRET_KEY` в окружение `api` для консистентности)
