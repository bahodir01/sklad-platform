# Обогащение ответов заявок ФИО + категорией сотрудника (§6.3 / §6.4)

Модуль `issuance`. Схема ЗАМОРОЖЕНА — новых колонок/таблиц нет. В Read-ответы
заявок добавлены **вычисляемые** `employee_full_name` и `employee_category`,
резолвятся JOIN-ом на `users` по `employee_id` — тот же приём, что в отчёте ДДС
(`reports`, `User.full_name` / `User.category` в `_cashflow_stmt`).

## Что изменено

### `backend/app/modules/issuance/schemas.py`
- `RequestList` (get_index — очередь «К печати», `/requests/my`): добавлены поля
  `employee_full_name: str | None` и `employee_category: UserCategory | None`,
  внесены в `__contract_extra_fields__` (приём `UserCreate.password`: поле есть в
  DTO, но НЕ в контракте — как computed-величины отчётов).
- `RequestRead` (get_single — деталь, ответы create/confirm/print/issue): те же
  два поля, добавлены к существующему `__contract_extra_fields__ = {"items", …}`.
- `RegistryRow` (§6.4, реестр): те же два поля рядом с обоими номерами. Схема
  суффикса Create/Update/Read/List не имеет → гейтом не проверяется, whitelist
  не требуется.
- Импорт `UserCategory` из `app.shared.enums`.

### `backend/app/modules/issuance/repository.py`
- Добавлен импорт `User` и хелпер `_attach_employee(req, full_name, category)` —
  навешивает вычисляемые ФИО/категорию как атрибуты экземпляра ORM (Pydantic
  `from_attributes` их читает; в БД не пишутся).
- `get_request_with_items(...)` — теперь `JOIN users`, отдаёт заявку со строками
  + ФИО/категорию; добавлен `populate_existing` для синхронизации после
  условного UPDATE.
- `list_requests(...)` — `JOIN users`, обогащает каждую строку (покрывает
  очередь «К печати» AP-2, «Мои» AP-4, generic-фильтр).
- `registry(...)` — `JOIN users`, обогащает `Request` в кортеже `(Request,
  Writeoff)`.

### `backend/app/modules/issuance/service.py`
- `_reload(...)` теперь делегирует в `repo.get_request_with_items(...,
  populate_existing=True)` — тот же путь обогащения (ответы confirm/print).

### `backend/app/modules/issuance/router.py`
- Конструктор `RegistryRow` в `/requests/registry` пробрасывает
  `employee_full_name` / `employee_category` из обогащённой заявки.

### PDF `backend/app/templates/pdf/writeoff.html`
- **Изменений не потребовалось.** Сервис (`_render_html`) уже прокидывал ORM
  `employee` (`employee.full_name`, `employee.category.value`), а не `#id`.
  Подтверждено боевым прогоном (ФИО и категория присутствуют в отрендеренном
  бланке).

## Проверка боем (env из задания, БД оставлена чистой)

Создание заявки от teacher id=4 → confirm → print → issue; затем реестр и PDF.
Все проверки пройдены:

| Точка | employee_full_name | employee_category |
|---|---|---|
| create → RequestRead | «Учитель» | teacher |
| GET /requests?status=to_print → RequestList | «Учитель» | teacher |
| GET /requests/my → RequestList | «Учитель» | teacher |
| деталь (get_own_request) → RequestRead | «Учитель» | teacher |
| issued → RequestRead | «Учитель» | teacher |
| реестр §6.4 → RegistryRow (REQ-000002 / WOFF-000002) | «Учитель» | teacher |
| PDF-бланк (writeoff.html) | «Учитель» присутствует | «teacher» присутствует |

Созданные строки (заявка/проводка/движение) удалены, остаток
`stock_balances(product=1, warehouse=1)` восстановлен в 2.000. Сиды не тронуты.

## Гейт
Зелёный: `OK: backend code matches the data dictionary contract.`

## (а) Отклонения
- PDF-шаблон не менялся — ФИО/категория уже прокидывались сервисом; задача
  требовала лишь убедиться в этом.
- `employee_full_name` / `employee_category` объявлены с `| None = None`
  (defensive default): пути, не проходящие через JOIN-загрузчики, не падают
  валидацией; во всех сериализуемых ответах значения фактически заполнены.
- ФИО/категория навешиваются на ORM-экземпляр как ненавязчивые атрибуты (не
  mapped-колонки, в БД не пишутся) — минимальная альтернатива Row-проекциям
  reports, сохраняющая загрузку `items` через `selectinload`.

## (б) Вопросы
- Нет. Всё в рамках §6.3/§6.4 и без правки контракта.

## (в) Django — нет. Гейт — зелёный.
