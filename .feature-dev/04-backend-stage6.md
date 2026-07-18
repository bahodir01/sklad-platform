# Backend — Этап 6 «Отчётность» (модуль `modules/reports`)

**Стек:** SQLAlchemy 2.0 / Pydantic v2 / FastAPI / PostgreSQL 16. Django/DRF **не
использованы** (ТЗ §0). Схема БД **не менялась** (заморожена): reports — это
ЧТЕНИЕ поверх готовых 22 таблиц, новых таблиц/моделей модуль не создаёт.
Контрактный гейт **зелёный**.

---

## 1. Что сделано (ТЗ §8, все эндпоинты admin, архитектура §6)

| Отчёт | Эндпоинт | ТЗ / AP | Пагинация |
|---|---|---|---|
| Остатки в реальном времени | `GET /reports/balances` | §8.1.1 / AP-10 | offset |
| Недокупленное по уведомлениям | `GET /reports/unpurchased` | §8.1.2 / AP-6 | offset |
| История движений | `GET /reports/movements` | §8.1.3 / AP-5 | **keyset** |
| ДДС (движение денежных средств) | `GET /reports/cashflow` | §8.2 / AP-8 | offset |

Каждый отчёт: `?format=json|xlsx|pdf` (ТЗ §8.1.1/§8.2).

### §8.1.1 Остатки (`/reports/balances`)
Проекция `stock_balances` JOIN `products`+`units`+`warehouses`. Фильтры:
`warehouse_id`, `product_id`, `unit_id` (единица товара — из `products.unit_id`,
в остатках её нет). Отдаёт код/имя склада, номенклатуру, артикул, ед., остаток.

### §8.1.2 Недокупленное (`/reports/unpurchased`)
`notification_items` LEFT JOIN агрегата `SUM(acquisition_items.qty)` по
`(notification_id, product_id)` через `acquisitions.notification_id`. Остаток к
приобретению = `qty_requested − purchased` — **расчётное, в БД не хранится**
(ТЗ §3, AP-6). В отчёт попадают только строки с остатком **> 0** (`HAVING`-логика
через `WHERE remaining > 0`). Фильтры: `notification_id`, `product_id`,
`date_from`/`date_to` (по дате уведомления).

### §8.1.3 История движений (`/reports/movements`)
Хронология `stock_movements` JOIN `products`+`units`+`warehouses`, сортировка
`(created_at DESC, id DESC)` — ложится на композитный индекс журнала. **Keyset,
не offset** (AP-5): курсор — непрозрачный base64(`created_at|id`), тот же формат,
что в `stock/repository.py`. Фильтры: `date_from`/`date_to`, `warehouse_id`,
`product_id`, `doc_type`. Знак `qty` сохранён (приход +, расход −); вид документа
переведён в русскую метку (`Приобретение`/`Перемещение`/`Расход`).

### §8.2 ДДС (`/reports/cashflow`)
`money_expense` JOIN `users` (ФИО, категория) + `expense_categories` (вид расхода).
**Фильтр по категории обязателен** (§8.2/AP-8): `category` ∈ {teacher, worker} —
разрешается в кассу этой категории и фильтрует `money_expense.cash_desk_id`
(ложится на индекс `ix_money_expense_cash_desk_date`). Опциональные фильтры:
`expense_category_id` (вид расхода), `employee_id` (сотрудник), `date_from`/
`date_to` (период). Плюс в ответе (ТЗ §8.2):
- **актуальный баланс каждой кассы** (обе строки `cash_desks`);
- **итоги за период**: приход по кассе категории, расход по отфильтрованному
  множеству, сальдо;
- **доступ к чекам**: `receipt_url` — presigned URL из `storage.presigned_url`
  (TTL 5 мин, ТЗ §7). В dev/локальном режиме без MinIO presigned = `null`, тогда
  у клиента остаётся `receipt_object` (ключ `bucket/key`).

> **Про «категорию» в §8.2/AP-8.** Значение фильтра — `teacher|worker`. Поскольку
> касса определяется категорией сотрудника (SV-6, 1:1), фильтр реализован через
> `money_expense.cash_desk_id` кассы этой категории — это архитектурно-заданный
> индекс (§4: «фильтр по категории + периоду → индекс `(cash_desk_id, date)`»).
> Отдельный опциональный фильтр «касса» был бы дублем и не заведён; поле
> `employee_category` выводится в строках отчёта через JOIN users.

---

## 2. Экспорт Excel/PDF — синхронно, но с готовым швом под Celery

Задание §8: тяжёлый экспорт по-хорошему через Celery (`export_report`,
архитектура §8), но **Celery/Redis в этой среде не подняты** — сделано
**синхронно**, структурировано так, что вынос в фон **тривиален**:

- **Сбор данных** отделён от **генерации файла**:
  - `ReportsService.build_*_table()` — session + фильтры → `ReportTable`
    (формат-независимая структура: заголовок, колонки, строки, итоги). Без HTTP.
  - `exporters.table_to_xlsx()` / `table_to_pdf()` / `export_table()` — **чистые
    функции** `ReportTable → bytes`. Не знают ни про HTTP, ни про сессию, ни про
    FastAPI.
- Роутер делает ровно `table = await svc.build_*_table(...)` →
  `export_table(table, fmt)` → `Response`. Чтобы перенести в Celery, задача
  вызывает те же две строки и кладёт байты в MinIO; роутер меняется на
  «поставить задачу + 202 + polling», **сами функции не трогаются**.
- Потолок синхронной выгрузки — `EXPORT_ROW_CAP = 100_000` строк (не тянуть
  миллионы строк истории в память одного воркера). В Celery потолок снимается
  server-side стримингом.

**Форматы.** Excel — `openpyxl` (чистый Python, добавлен в `pyproject.toml`).
PDF — существующий `shared/pdf.py` (WeasyPrint, ленивый импорт). В этой среде
нативные pango/cairo отсутствуют → PDF-ветка отдаёт **готовый к печати HTML**
(тот же фолбэк, что во всей системе: `notification.html`/`writeoff.html`), честно
меняя расширение файла на `.html`. Шаблон отчёта — `templates/pdf/report.html`.

---

## 3. Файлы (пути абсолютные)

Созданы:
- `c:\Users\user\Desktop\Новая папка\backend\app\modules\reports\__init__.py`
- `c:\Users\user\Desktop\Новая папка\backend\app\modules\reports\schemas.py`
- `c:\Users\user\Desktop\Новая папка\backend\app\modules\reports\repository.py`
- `c:\Users\user\Desktop\Новая папка\backend\app\modules\reports\service.py`
- `c:\Users\user\Desktop\Новая папка\backend\app\modules\reports\exporters.py`
- `c:\Users\user\Desktop\Новая папка\backend\app\modules\reports\router.py`
- `c:\Users\user\Desktop\Новая папка\backend\app\templates\pdf\report.html`

Изменены:
- `c:\Users\user\Desktop\Новая папка\backend\app\main.py` — подключён
  `reports_router`.
- `c:\Users\user\Desktop\Новая папка\backend\pyproject.toml` — зависимость
  `openpyxl>=3.1`.

Схема (`models.py`, миграции) и этапы 1–5 **не тронуты**.

---

## 4. Проверка боем (5 сценариев + очистка)

Скрипт: `…/scratchpad/verify_reports.py`. Наполняет БД через РЕАЛЬНЫЕ сервисы
(`documents`, `issuance`, `cash`, `ledger`), гоняет отчёты, затем удаляет всё
созданное и сбрасывает балансы касс — **сиды нетронуты** (проверено `psql`:
users=2, product=1, warehouses=2, cash_desks=0, все транзакционные таблицы пусты).

Env: `DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/sklad`
(+ REDIS_URL / SECRET_KEY / JWT_SECRET_KEY / PYTHONIOENCODING=utf-8).

**Итог: 26/26 проверок зелёные.** По сценариям:

1. **Остатки.** Приход 10 на W-ISS + перемещение 3 W-ISS→W-NO → отчёт:
   **W-ISS = 7, W-NO = 3**. ✅ (проверка сделана сразу после этих двух операций,
   до сценариев 2–4, которые дальше двигают тот же товар).
2. **Недокуп.** Уведомление на 10, приобретено 4 → строка недокупа:
   запрошено 10, приобретено 4, **остаток к приобретению = 6**. Закрытое
   уведомление (10/10) в недокупе отсутствует. ✅
3. **История.** Приобретение(+10), перемещение(−3/+3), расход-выдача(−2) →
   хронология со знаками и русскими видами документа
   (`Приобретение`/`Перемещение`/`Расход`). Keyset: первая страница 2 строки +
   курсор; вторая страница по курсору **не пересекается** с первой. ✅
4. **ДДС.** Приход 500000 (учителя) + 300000 (работники); расход 150000 (учитель)
   + 90000 (работник). Фильтр `category=teacher` → **только строка учителя**
   (worker отфильтрован); итоги приход=500000 / расход=150000 / сальдо=350000;
   **балансы касс** teacher=350000, worker=210000. `category=worker` показывает
   свой расход 90000. ✅
5. **Экспорт xlsx.** Отчёт остатков → `.xlsx` (сигнатура ZIP `PK`, открывается
   `openpyxl.load_workbook`), строки складов и их числовые остатки на месте.
   Бонусом ДДС в pdf-ветку → HTML-фолбэк сформирован (WeasyPrint без нативных
   зависимостей). ✅

Прогон печатает предупреждения WeasyPrint об отсутствии pango/cairo — это
ожидаемо и обрабатывается фолбэком, на результат не влияет.

---

## 5. Контрактный гейт

```
python .claude/skills/database-schema-design/assets/contract_validator_sqlalchemy.py \
  .feature-dev/02-contract.json backend/app/modules/auth/models.py … backend/app/modules/cash/schemas.py
→ OK: backend code matches the data dictionary contract.
```

reports новых таблиц не создаёт; отчётные Pydantic-схемы **намеренно** не
оканчиваются на `Create/Update/Read/List` и не совпадают с именами таблиц —
валидатор их не привязывает к сущностям (это проекции JOIN-ов, у них нет своей
таблицы). Гейт зелёный.

---

## 6. Отклонения, замечания по контракту/ТЗ, стек

### (а) Отклонения от задания
- **PDF отдаётся как HTML-фолбэк**, а не как настоящий PDF — потому что WeasyPrint
  в этой среде без нативных pango/cairo (ровно как на этапах 2–3 для бланков).
  Код PDF-ветки полноценный (`html_to_pdf` → при наличии зависимостей вернёт PDF);
  расширение файла честно переключается `pdf`↔`html`. Это не дефект reports, а
  свойство окружения.
- **Экспорт синхронный** (не Celery) — по прямому указанию задания (Celery/Redis
  не подняты). Шов под вынос в фон описан в §2.

### (б) Что в контракте/ТЗ неверно — СООБЩАЮ, не чиню
- **§8.2/AP-8 «фильтр по категории» терминологически двусмыслен.** Слово
  «категория» в системе занято дважды: `users.category` (teacher|worker) и
  `expense_categories` (вид расхода денег — Канцелярия/Хознужды). AP-8
  перечисляет фильтры «**категория** … + касса, **вид расхода** …», из чего
  «категория» ≠ «вид расхода» и ≠ «касса», хотя `users.category` и касса связаны
  1:1 (SV-6). Реализовано как обязательный `category` (teacher|worker) →
  `cash_desk_id`. Рекомендация: в след. ревизии ТЗ переименовать в «касса
  (категория сотрудника)», чтобы фильтр «касса» из AP-8 не читался как отдельная
  третья ось.
- **`money_income` не имеет ни сотрудника, ни вида расхода** (ТЗ §3), поэтому в
  итогах ДДС «приход за период» считается только по кассе+периоду, а фильтры
  `employee_id`/`expense_category_id` к приходу неприменимы (применяются к
  расходу). Это следствие схемы, не дефект; отражено в коде и в этом отчёте.
- Прочие расхождения (терминологический хвост §6.2/§6.3, ОВ-11 правка черновиков)
  относятся к этапам 2–4 и здесь не затрагиваются.

### (в) Django не использован; гейт зелёный
Подтверждаю: модуль reports — FastAPI + SQLAlchemy 2.0 (Core-select для JOIN-ов) +
Pydantic v2, без Django/DRF. Контрактный валидатор возвращает
`OK: backend code matches the data dictionary contract`. Схема БД заморожена и не
менялась; этапы 1–5 не сломаны (импорт приложения и все прежние роутеры на месте).
