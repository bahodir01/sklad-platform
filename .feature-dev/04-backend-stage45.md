# Backend — Этапы 4 и 5 (расход товара порча/брак + кассы/деньги)

**Стек:** SQLAlchemy 2.0 / Pydantic v2 / FastAPI / PostgreSQL 16. Django/DRF не
использованы (ТЗ §0). Схема БД не менялась (заморожена, проверена боем на этапах
1–3) — этапы 4/5 добавляют только service/router/schemas поверх готовых моделей и
ledger.

---

## 1. Что сделано

### ЭТАП 4 — расход товара порча/брак (прямое списание без заявки, §4.4)

Размещён в модуле `issuance` (там же, где вся логика writeoffs и issue() с этапа 3).

- **`POST /writeoffs`** (admin) — прямое создание проводки `writeoff` БЕЗ заявки,
  статусов, печати и подписи. Списывает немедленно через `ledger.post(−qty,
  'writeoff', writeoff.id)`.
- Принимаются только типы расхода с `requires_employee=false` (Порча/Брак).
  `employee_id` при них обязан быть `NULL` (INV-4).
- Тип «Выдача» (`requires_employee=true`) через этот эндпоинт **отклоняется** —
  выдача проводится только статусной машиной заявки (issue(), этап 3).
- Ограничение SV-9 (`allows_issuance`) на порчу/брак НЕ распространяется (ТЗ §3
  М1): порча может случиться на любом складе — склад на этот флаг не проверяется.
- INV-4 продублирован в БД (составной FK `(expense_type_id, requires_employee)` +
  `CHECK ck_writeoffs_employee_iff_required`) — последний рубеж; сервис даёт
  внятный русский текст до срабатывания CHECK.

### ЭТАП 5 — кассы, модуль `modules/cash`

- **`POST /cash/income`** — ТОЛЬКО admin (§7.2). `+balance` под `SELECT … FOR
  UPDATE` (защита от lost update). `author_id` — сервер из JWT.
- **`POST /cash/expenses`** — сотрудник (teacher/worker), multipart (поля формы +
  файл чека). Порядок строго по §5.4:
  1. **SV-6:** касса берётся сервером из `current_user.category`, не с клиента.
     Схема тела `MoneyExpenseSubmission` физически не содержит `cash_desk_id`.
  2. **INV-7:** чек обязателен — валидация magic bytes (whitelist jpg/png/pdf по
     СОДЕРЖИМОМУ, не по расширению) + лимит 10 МБ, до любой записи в БД.
  3. Вид расхода существует и активен.
  4. `SELECT balance … FOR UPDATE` по кассе (AP-9).
  5. `balance < amount` → **`InsufficientFunds`** (ОВ-2 жёсткая блокировка); файл
     ещё не сохранён, баланс цел.
  6. Чек → MinIO (бакет `receipts`, локальный фолбэк) → `receipt_url`.
  7. `INSERT money_expense; UPDATE cash_desks SET balance = balance − amount`.
- **`GET /cash/desks`** — балансы обеих касс (любая аутентифицированная роль).
- **`GET /cash/expenses/my`** — row-level: только расходы текущего сотрудника (§1.3).
- Суммы — `Decimal(18,2)`, никогда float. ОВ-2: жёсткая блокировка, `CHECK
  (balance >= 0)` в БД — последний рубеж; флага `CASH_OVERDRAFT_MODE` нет.

---

## 2. Файлы (все пути абсолютные)

Созданы:
- `c:\Users\user\Desktop\Новая папка\backend\app\modules\cash\schemas.py`
- `c:\Users\user\Desktop\Новая папка\backend\app\modules\cash\repository.py`
- `c:\Users\user\Desktop\Новая папка\backend\app\modules\cash\service.py`
- `c:\Users\user\Desktop\Новая папка\backend\app\modules\cash\router.py`

Изменены:
- `c:\Users\user\Desktop\Новая папка\backend\app\shared\storage.py` — добавлен
  `sniff_receipt()` (magic-byte whitelist jpg/png/pdf).
- `c:\Users\user\Desktop\Новая папка\backend\app\modules\issuance\schemas.py` —
  добавлены `WriteoffItemCreate`, `WriteoffCreate`.
- `c:\Users\user\Desktop\Новая папка\backend\app\modules\issuance\service.py` —
  добавлен `IssuanceService.create_writeoff()`.
- `c:\Users\user\Desktop\Новая папка\backend\app\modules\issuance\router.py` —
  добавлен `POST /writeoffs`.
- `c:\Users\user\Desktop\Новая папка\backend\app\main.py` — подключён
  `cash_router`.

Модели (`cash/models.py`, `issuance/models.py`) с этапа 1 — НЕ трогались.

Скрипт проверки боем:
- `C:\Users\user\AppData\Local\Temp\claude\c--Users-user-Desktop------------\0f64328f-456c-4294-a589-cf0ebf508399\scratchpad\verify_stage45.py`

---

## 3. Проверка боём — 10/10 PASS против живого PostgreSQL (порт 5433, sklad)

Скрипт драйвит сервисный слой напрямую (сессия на операцию, commit внутри
сервиса) — так проверяются транзакции, `FOR UPDATE` и constraint-ы на реальном
Postgres. Сиды не тронуты, всё созданное удалено, балансы касс возвращены в 0.

```
[PASS] 1. Порча 5 списана: движение −5, employee_id=NULL
       — writeoff#WOFF-000001 employee_id=None movement.qty=-5.000 balance 100.000→95.000
[PASS] 2. Порча с сотрудником → отказ (INV-4)
       — «При «Порче»/«Браке» сотрудник-получатель не указывается (INV-4)»
[PASS] 3. Выдача-тип в POST /writeoffs → отказ
       — «Тип расхода «Выдача» проводится только через заявку сотрудника (этап 3)…»
[PASS] 4. Приход 1000000 на кассу учителей → баланс 1000000
[PASS] 5. Расход 300000 учителем с чеком → баланс 700000
       — receipt=receipts/expenses/2026/07/<uuid>.png
[PASS] 6. Расход 800000 при 700000 → InsufficientFunds, баланс цел
       — balance 700000.00→700000.00 (не изменился)   ← ЖЁСТКАЯ БЛОКИРОВКА (ОВ-2)
[PASS] 7. Расход без чека → отказ (INV-7)
       — «Чек обязателен: файл не приложен (INV-7)»
[PASS] 8. Учитель → сервер берёт кассу teacher по category (SV-6)
       — expense.cash_desk_id=1 (teacher); касса worker 0.00→0.00 (цела)
[PASS] 9. Гонка: два расхода 400000 при 700000 → один ок, второй InsufficientFunds
       — results=['ok','insufficient'] balance_after=300000.00 (ровно ОДНО списание)  ← FOR UPDATE
[PASS] 10. GET /cash/expenses/my — только свои (§1.3)
       — вернулось 3 расхода, все employee_id=4

==== ИТОГ: 10 PASS / 0 FAIL ====
```

**#6 (жёсткая блокировка):** расход сверх баланса отклонён `InsufficientFunds` под
`FOR UPDATE`, файл чека не сохранён, баланс кассы не изменился. `CHECK (balance>=0)`
в БД остаётся последним рубежом, но до него не доходит.

**#9 (гонка, `FOR UPDATE`):** два конкурентных расхода по 400 000 при 700 000
запущены `asyncio.gather` в двух отдельных сессиях. `SELECT … FOR UPDATE`
сериализовал их: первый списал (→300 000), второй увидел уже уменьшенный баланс и
получил `InsufficientFunds`. Ровно одно списание, минуса нет.

Пост-проверка БД: `cash_desks` teacher=0.00 / worker=0.00; `money_expense`,
`money_income`, `writeoffs`, `writeoff_items`, `stock_movements`, `stock_balances`,
`expense_categories` — по 0 строк. Сиды целы.

---

## 4. Гейт — зелёный

```
python .claude/skills/database-schema-design/assets/contract_validator_sqlalchemy.py .feature-dev/02-contract.json \
  backend/app/modules/auth/models.py backend/app/modules/catalog/models.py \
  backend/app/modules/documents/models.py backend/app/modules/stock/models.py \
  backend/app/modules/issuance/models.py backend/app/modules/cash/models.py \
  backend/app/core/audit.py \
  backend/app/modules/catalog/schemas.py backend/app/modules/auth/schemas.py \
  backend/app/modules/documents/schemas.py backend/app/modules/stock/schemas.py \
  backend/app/modules/issuance/schemas.py backend/app/modules/cash/schemas.py
```
Результат: `OK: backend code matches the data dictionary contract.`

---

## 5. Итоги

### (а) Отклонения от буквальной формулировки задания

1. **Нет схемы `MoneyExpenseCreate`.** Расход денег — multipart-запрос (поля формы
   + ФАЙЛ чека). `receipt_url` в контракте помечен `api.create=true`, но физически
   это файл, а не строка-ключ (ключ вычисляет сервер после загрузки в MinIO).
   Единой JSON-схемы тела здесь быть не может. Поля объявлены как `Form()`/`File()`
   в роутере, а суммa/описание валидируются моделью `MoneyExpenseSubmission` (имя
   без суффикса Create/Read/List → намеренно вне проверки контракта). `Create`-схемы
   остальных сущностей (`MoneyIncomeCreate`, `WriteoffCreate`) — на месте и в гейте.
   Read/List-схемы кассы полностью соответствуют `api.get_single`/`api.get_index`.

2. **`GET /cash/desks` — простой список, без пагинации.** Касс ровно две (seed,
   `type UNIQUE`), пагинировать нечего.

### (б) Что неверно в контракте / ТЗ — СООБЩАЮ, не чиню

1. **Архитектура §6 vs INV-7 — противоречие в модели загрузки чека.** §6
   перечисляет отдельный эндпоинт `POST /cash/expenses/{id}/receipt` (двухшаговый
   сценарий: сначала создать расход, потом прикрепить чек). Но `money_expense.
   receipt_url` — `NOT NULL` + `CHECK (length(trim(receipt_url)) > 0)` (INV-7):
   расход НЕ МОЖЕТ существовать без чека ни на миг, значит двухшаговая схема
   нереализуема без временно-невалидной строки. Реализован единственный
   консистентный с INV-7 вариант — **однократный multipart-`POST /cash/expenses`
   с чеком в том же запросе**. Отдельный `…/{id}/receipt` не делал. Рекомендую
   убрать его из §6 либо явно оговорить как «замену чека» (перезагрузка уже
   приложенного), что уже другая операция.

2. **`money_expense.receipt_url` `api.create=true` формально некорректен для
   бэкенда.** Клиент никогда не присылает строку `receipt_url` — он присылает файл,
   а ключ ставит сервер. Флаг `create=true` осмыслен только для фронта
   (`input_type: file`). Для валидатора контракта это означает, что поле-файл
   нельзя проверить как обычное create-поле JSON-схемы (см. отклонение (а)-1). Не
   ошибка данных, но флаг вводит в заблуждение — стоит пометить в контракте как
   «file-backed, server-computed».

3. **`expense_categories` в предоставленной БД пуст (0 строк).** Для расхода денег
   нужен хотя бы один активный вид расхода. Скрипт проверки создаёт его сам и
   удаляет в конце. Если сиды должны включать деньги-справочник — стоит добавить
   строку (напр. «Канцелярия») в начальную миграцию/сиды. Кода это не касается.

### (в) Контроль

- **Django не использован** — только SQLAlchemy 2.0 / Pydantic v2 / FastAPI /
  PostgreSQL 16.
- **Гейт зелёный** (см. §4).
- **Схема не менялась**, этапы 1–3 не сломаны (гейт валидирует все модели/схемы,
  приложение импортируется целиком, 5 новых маршрутов зарегистрированы:
  `POST /writeoffs`, `GET /cash/desks`, `POST /cash/income`,
  `POST /cash/expenses`, `GET /cash/expenses/my`).
- **`frontend/` не тронут.**
