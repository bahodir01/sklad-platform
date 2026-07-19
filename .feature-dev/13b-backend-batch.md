# 13b · Бэкенд: пакетная подпись и учёт передачи (ЭТАП 2)

**Вход:** `13-batch-signature-spec.md` (§2-§6), `13a-schema-batch.md` (схема 0002 уже накатана).
**Стек:** PostgreSQL 16 · SQLAlchemy 2.0 · Alembic · Pydantic v2 · FastAPI. **Django нет.**
**Схему БД не менял** (0002 остаётся head). Изменён только код + контракт (API-флаги новых read-полей).

Починен сломанный код issuance (ссылался на удалённые `RequestStatus.to_print/.printed` →
`import app.main` падал с AttributeError) и реализована статусная машина фичи 13.

---

## 1. Статусная машина (спека §2)

`draft → to_issue → issued → signed → submitted`

| Переход | Кто | Эндпоинт | Что происходит |
|---|---|---|---|
| draft→to_issue | сотрудник | `POST /requests/{id}/confirm` | условный UPDATE из draft |
| **to_issue→issued** | admin | `POST /requests/{id}/issue` | **СПИСАНИЕ ЗДЕСЬ**: проводка→ledger.post(−qty)→ОДИН UPDATE (status+issued_at+writeoff_id) WHERE status='to_issue' |
| (печать пачкой) | admin | `POST /requests/batch-print` | создаёт `signature_batches`, ставит `batch_id`+`printed_at`, один PDF по сотрудникам. **Статус не меняет** |
| issued→signed | admin | `POST /requests/mark-signed` | пачкой, исключённые остаются issued; `batch.signed_at` |
| signed→submitted | admin | `POST /requests/submit-to-accounting` | `submitted_at=today`, общий `submitted_register_no` (один на вызов) |

Списание перенесено с `printed→issued` на `to_issue→issued`. INV-2 (CHECK в БД, обновлён 0002):
`status IN ('issued','signed','submitted') ⟺ writeoff_id IS NOT NULL`. Порядок операций в `issue()`
(проводка → ledger → один UPDATE, rowcount=0 → Conflict) сохранён; Idempotency-Key в роутере сохранён.
Старый `print_request()` / переход `to_print`/`printed` удалены.

## 2. Эндпоинты

**Товар (`modules/issuance/router.py`):**
- `POST /requests` — черновик (teacher/worker)
- `POST /requests/{id}/confirm` — draft→to_issue (владелец)
- `GET /requests/my` — свои заявки (row-level)
- `GET /requests?status=to_issue|issued|signed|submitted` — список по статусу (admin)
- `GET /requests/count?status=...` — счётчик фильтр-карточки (admin)
- `POST /requests/{id}/issue` — выдача + списание (admin, Idempotency-Key)
- `POST /requests/batch-print` — пачка + один PDF по сотрудникам (admin)
- `GET /requests/batches/{id}/pdf` — PDF пачки
- `POST /requests/mark-signed` — issued→signed пачкой с исключениями (admin)
- `POST /requests/submit-to-accounting` — signed→submitted + №реестра (admin)
- `GET /requests/registry?register_no=&date=` — реестр передачи (admin)
- `GET /requests/{id}/pdf` — бланк одной заявки (перепечать копии)

**Деньги (`modules/cash/router.py`):**
- `GET /cash/expenses?submitted=true|false` — расходы с фильтром «Передано/Не передано» (admin)
- `POST /cash/expenses/submit-to-accounting` — bulk-передача + №реестра `MREG-` (admin, у денег нет подписи)
- `GET /cash/expenses/registry?register_no=&date=` — реестр передачи денег (admin)

Всё в транзакциях; `FOR UPDATE` на трогаемых строках (issued-заявки при печати/подписи, signed при передаче,
непереданные money_expense); защита от двойного проведения — условие статуса/`submitted_at IS NULL` в самом UPDATE.
Реестры товара и денег раздельны (серии `REG-` и `MREG-`).

## 3. Контракт / гейт

`build_dictionary.py`: новым server-managed read-полям выставлен `get_index/get_single=true` и добавлены в
Pydantic Read/List-схемы:
- `requests.batch_id`, `requests.submitted_at`, `requests.submitted_register_no` → `RequestList`/`RequestRead`
- `money_expense.submitted_at`, `money_expense.submitted_register_no` → `MoneyExpenseList`/`MoneyExpenseRead`

Контракт перегенерирован (`python .feature-dev/build_dictionary.py` → 23 таблицы, 145 строк).
Таблица `signature_batches` и её схема наружу через Read/List НЕ выводятся (server-managed, отдаются
транспортными конвертами без суффикса — вне проверки контракта).

**Гейт зелёный:**
```
OK: backend code matches the data dictionary contract.   (exit 0)
```

## 4. Проверка боем (живая БД :5433/sklad, сервисный слой, :8000 не тронут)

```
ПРОГОН 1: полный цикл
  создана заявка id=1, статус=draft, остаток=100.000
  confirm → статус=to_issue, остаток=100.000 (списания НЕТ)
  issue   → статус=issued, остаток=90.000 (упал ТУТ), writeoff №WOFF-000001, requests.writeoff_id=1
  проводок writeoff-движений: 1
  batch-print → пачка №BATCH-000001, printed=[1], skipped=[], статус=issued (НЕ изменился)
  PDF по сотрудникам: разделов-заявок=1, сотрудник='Учитель'
  mark-signed → signed=[1], статус=signed
  submit  → submitted=[1], register_no=REG-000001, статус=submitted

ПРОГОН 2: списание ровно на issue(); двойной issue → одна проводка
  до issue: остаток=50.000, проводок=0
  два параллельных issue() → ['ConflictError', 'ok']
  после: остаток=40.000 (50-10), проводок=1, движений=1, статус=issued

ПРОГОН 3: mark-signed с исключением (3 заявки, 1 исключить)
  подписаны [r1, r3], исключён r2
  статусы: r1=signed, r2=issued, r3=signed

ПРОГОН 4: деньги — расход→submit→submitted; фильтр submitted=false не показывает
  расход id=1; фильтр Не передано → 1 шт (id в списке: True)
  submit → submitted=[1], register_no=MREG-000001
  после: Не передано → 0 шт (не показывает: True); Передано → 1 шт (показывает: True)

ПРОГОН 5: счётчики 4 карточек
  {'to_issue': 1, 'issued': 1, 'signed': 1, 'submitted': 1}   ← совпало с ожиданием

БД очищена (сиды не тронуты): requests=0, signature_batches=0, writeoffs=0, money_expense=0,
stock_movements=0; users(3,4)=2, cash_desks=2 — на месте.
```

WeasyPrint без нативных pango/cairo → PDF не рендерится, роутер отдаёт готовый HTML (штатный фолбэк,
`rendered_pdf=False`); ключ объекта фиксируется, `GET .../pdf` рендерит на лету.

## 5. Pytest

Обновлён под новую модель:
- `tests/test_issuance_flow.py` — `_make_issuable_request` (draft→confirm, без печати), INV-2 расширен
  на signed/submitted, все «printed»→«to_issue»; двойной issue() теперь конфликтует на `WHERE status='to_issue'`.
- `tests/test_reports.py` — убран шаг print (выдача идёт из to_issue).
- `tests/test_batch_signature_flow.py` (**новый**) — batch-print без смены статуса, skip не-issued,
  mark-signed с исключением, submit с общим register_no, submit только signed, счётчики 4 карточек.
- `tests/test_cash.py` — добавлены передача расхода + фильтр submitted, идемпотентность повторной передачи.
- `tests/conftest.py` — `signature_batches` добавлена в список truncate (иначе пачки текли между прогонами).

```
python -m pytest -q  →  78 passed in ~14s
```

---

## Итог

### (а) Отклонения от задания
1. **Реестры товара и денег — раздельные серии номеров** (`REG-` и `MREG-`), как требует спека §4
   «Отдельно для товара и денег». Номера независимы (считаются из своих колонок).
2. **`GET /requests/registry` переосмыслен как реестр ПЕРЕДАЧИ** (status='submitted', фильтр по
   `submitted_register_no`/дате), а не прежний реестр «выданных» (issued). Соответствует спека §4
   «Реестр передачи — доказательство передачи». Оба номера (заявки+проводки) в строке сохранены.
3. **Период пачки** (`period_from/period_to`) выводится из диапазона дат выдачи вошедших заявок
   (min/max `issued_at::date`), fallback — сегодня. В спеке период задан как поля таблицы, способ
   заполнения не оговорён (§7 «формат — по ходу»).
4. **`request.printed_at`** проставляется при пакетной печати вместе с `batch.printed_at` (спека §3:
   «выбранным ставится batch_id, printed_at»). Признак «напечатано» = `batch_id IS NOT NULL`.
5. `POST /requests/batch-print` при пустом наборе issued-заявок возвращает Conflict (`empty_batch`),
   а не создаёт пустую пачку.

### (б) Вопросы / на будущее
1. **Формат номера пачки/реестра** — принял серверные серии `BATCH-`/`REG-`/`MREG-` по конвенции прочих
   документов (спека §7). Если заказчик хочет годовой сброс/иной формат — правится в одном месте (`numbering`).
2. **Отдельный статус «К выдаче»** (спека §7 открытый вопрос) — заложен `to_issue`, как в схеме 0002.
3. **`GET /requests/batches`** (список пачек) не заведён — в спеке экран оперирует заявками, не пачками;
   пачка адресуется по id из ответа `batch-print` (`GET /requests/batches/{id}/pdf`). Добавить тривиально при нужде.

### (в) Django нет; гейт+pytest зелёные
- Django/DRF не использовались: SQLAlchemy 2.0 модели, Pydantic v2 схемы, FastAPI роутеры, Alembic 0002 (head, не тронут).
- Гейт: `OK: backend code matches the data dictionary contract.` (exit 0).
- Pytest: `78 passed`.
- БД оставлена чистой (транзакционные таблицы пусты, сиды не тронуты).
