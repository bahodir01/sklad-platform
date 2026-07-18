# ТЗ: Платформа складского учёта, документооборота и учёта денежных средств

**Источник:** `TZ_sklad.docx` (ред. 17.07.2026, согласовано) + `ARCHITECTURE.md` (архитектурные решения приняты и утверждены).
**Methodology:** traditional · **Complexity:** complex
**Статус шагов пайплайна:** шаг 1 (это ТЗ) и шаг 3 (архитектура) закрыты аналитиком. Агент `backend-architect` на проектирование НЕ запускается — архитектура зафиксирована в `ARCHITECTURE.md` и является источником правды.

---

## 0. ОБЯЗАТЕЛЬНЫЕ ОГРАНИЧЕНИЯ СТЕКА — читать до проектирования

> **Целевой стек — НЕ Django.** ТЗ §2.1 согласовано бумажной подписью и предписывает:
>
> | Слой | Технология | Запрещено |
> |---|---|---|
> | ORM / модели | **SQLAlchemy 2.0** (declarative, `Mapped[]`) | Django ORM, `models.Model` |
> | Миграции | **Alembic** | Django migrations |
> | Схемы / валидация | **Pydantic v2** | DRF serializers |
> | API | **FastAPI** | Django REST Framework |
> | СУБД | **PostgreSQL 16** | — |
>
> Скилл `database-schema-design` и агент `database-architect` по умолчанию ориентированы на Django. **В этом проекте Django-ветку не применять.** Конкретно:
> - Физические артефакты: SQL DDL + **SQLAlchemy-модели** + **Alembic**-миграции (агент это допускает: «migration stubs (Alembic or Django migrations)»).
> - Словарь данных (Excel + JSON-контракт) строится **обязательно** через `assets/data_dictionary_generator.py` `build_all(rows, xlsx_path, contract_path)` — формат словаря сохраняется, меняется только семантика колонок BACKEND.
> - Колонки BACKEND трактуются как SQLAlchemy/Pydantic, а не Django: `type` → тип колонки SQLAlchemy, `nullable` → `nullable=`, `unique` → `unique=`, `db_index` → `index=`, `on_delete` → `ondelete=` в `ForeignKey`, `choices` → Python `Enum` + `SAEnum`, `default` → `default=`/`server_default=`.
> - API-флаги (`get_index` / `get_single` / `create` / `update`) сохраняют смысл один-в-один, но реализуются раздельными Pydantic-схемами (`XxxCreate` / `XxxUpdate` / `XxxRead` / `XxxList`), а не одним сериализатором с `fields`.
> - `contract_validator.py` парсит Django-модели через `ast` и на SQLAlchemy работать не будет. Валидация кода против контракта на шаге 4 требует адаптации — **это известный технический долг, решается отдельно, не блокирует шаги 2–3.**

---

## 1. Проблема и пользователи

**Проблема.** Учёт товаров и денег ведётся вручную, нет единой картины: неизвестно, сколько товара реально лежит на складах, что ещё не докуплено по заявкам в отдел закупки, кто и что получил под подпись, каков остаток по кассам и на что потрачены деньги.

**Ключевая цель — прозрачность.** В любой момент времени должно быть точно известно: остатки по складам, недокупленное по уведомлениям, кто что получил под рукописную подпись на бумаге, баланс касс и структура расходов.

**Пользователи** (роли системы):

| Роль | Кто это | Что делает |
|---|---|---|
| `admin` | Заведующий складом | Справочники, уведомления, приобретения, перемещения, расходы, приход денег, все отчёты, печать документов-расходов, передача подписанных бумаг в бухгалтерию |
| `teacher` | Сотрудник-учитель | Заявка на товар + подтверждение; расход денег из кассы учителей; просмотр только своих заявок и расходов |
| `worker` | Сотрудник-работник | То же, но касса работников |

Отдел закупки отдельной ролью не выделяется — моделируется функцией `admin`. Согласования заявок нет: при наличии товара сотрудник забирает его сразу.

**Масштаб:** более 1500 сотрудников, проектировать под сотни одновременных пользователей.

---

## 2. Модули

| № | Модуль | Ответственность (одна строка) |
|---|---|---|
| М1 | Справочники (НСИ) | Единицы измерения, номенклатура, склады, типы расходов товара, виды расходов денег |
| М2 | Документооборот товаров | Уведомления, приобретения, перемещения |
| М3 | Складской учёт | Журнал движений (источник правды) и остатки (проекция) |
| М4 | Заявки и печать | Заявка сотрудника, очередь «К печати», бумажная подпись, выдача и списание |
| М5 | Кассы и деньги | Две кассы, приход, расход, чеки, балансы |
| М6 | Отчётность | Складские отчёты и отчёт ДДС с фильтрами, экспорт |
| М7 | Администрирование | Пользователи, роли, аудит действий |

---

## 3. Сущности и связи

Типы указаны как целевые типы PostgreSQL. **Деньги — всегда `NUMERIC(18,2)`, количество товара — всегда `NUMERIC(14,3)`** (в справочнике единиц есть кг и л, дробные количества обязательны; `float` для денег запрещён — ошибка округления в балансе кассы).

### М1. Справочники

**`users`** — пользователи
| Атрибут | Тип | Правила |
|---|---|---|
| id | bigserial PK | |
| full_name | varchar(255) NOT NULL | ФИО |
| username | varchar(150) NOT NULL | **UNIQUE** |
| password_hash | varchar(255) NOT NULL | Argon2id |
| role | enum `admin\|teacher\|worker` NOT NULL | |
| category | enum `teacher\|worker` NULL | NULL только для `admin`; определяет кассу сотрудника |
| is_active | boolean NOT NULL default true | |
| created_at | timestamptz NOT NULL | |

**`units`** — единицы измерения
| id bigserial PK | code varchar(16) **UNIQUE** NOT NULL (шт, кг, л, м) | name varchar(100) NOT NULL | is_active boolean NOT NULL default true |

**`products`** — номенклатура
| id bigserial PK | name varchar(255) NOT NULL | unit_id FK→`units` NOT NULL `ondelete=RESTRICT` | sku varchar(64) NULL | status enum `active\|archived` NOT NULL default active |

**`warehouses`** — склады
| Атрибут | Тип | Правила |
|---|---|---|
| id | bigserial PK | |
| code | varchar(32) NOT NULL | **UNIQUE** |
| name | varchar(255) NOT NULL | |
| address | varchar(500) NULL | |
| **allows_issuance** | **boolean NOT NULL default false** | **Галочка «Склад списания»** в карточке склада. Ставится администратором при создании и редактировании склада. Отмеченных складов может быть **несколько** |
| status | enum `active\|archived` NOT NULL default active | |

> **Правило SV-9 (уточнение заказчика от 17.07.2026, закрывает ОВ-5).** Сотрудник может подать заявку (`requests`) **только со склада, у которого `allows_issuance = true`**. В форме заявки выпадающий список складов фильтруется по `allows_issuance = true AND status = 'active'`.
>
> **Ограничение действует ТОЛЬКО на заявки сотрудников.** Порча и брак (`writeoffs` без заявки), приобретения и перемещения работают с **любым** складом без ограничений — товар может испортиться где угодно, и если списать его будет негде, он навечно зависнет в остатках.



**`expense_types`** — типы расхода **товара**
| id bigserial PK | name varchar(100) NOT NULL (Выдача сотруднику / Порча / Брак) | **requires_employee boolean NOT NULL** | status enum `active\|archived` NOT NULL |

**`expense_categories`** — виды расхода **денег** (не путать с `expense_types`)
| id bigserial PK | name varchar(100) NOT NULL (Канцелярия, Хознужды) | status enum `active\|archived` NOT NULL |

**Связи М1:** `products` N:1 `units`.

### М2. Документооборот товаров

**`notifications`** — уведомление в адрес отдела закупки
| id bigserial PK | number varchar(32) **UNIQUE** NOT NULL (авто) | date date NOT NULL | author_id FK→`users` NOT NULL RESTRICT | warehouse_id FK→`warehouses` NOT NULL RESTRICT (склад назначения) | status enum `draft\|in_progress\|closed` NOT NULL | comment text NULL | **body_text text NOT NULL** | **division_name varchar(255) NOT NULL** | **pdf_url varchar(500) NULL** | created_at timestamptz |

> **Печатная форма BILDIRISHNOMA (уточнение заказчика 17.07.2026).** Заказчик предоставил реальный бланк — узбекская форма на имя ректора. Шаблон: `backend/app/templates/pdf/notification.html`, превью: `.feature-dev/preview/bildirishnoma_preview.pdf`. Отсюда три новые колонки:
>
> | Элемент бланка | Источник | Примечание |
> |---|---|---|
> | Абзац-обращение «Sizdan… so'rayman:» | `body_text` | Меняется в каждом уведомлении, пишет администратор |
> | `Bo'linma nomi` | `division_name` | **Не склад и не справочник** — свободный текст (решение заказчика). Подразделение и склад назначения — разные сущности |
> | `Tovar (xizmat)ning nomi… va soni` | `notification_items` | Все позиции рендерятся списком **внутри одной ячейки**, по позиции в строку |
> | `Ehtiyojning asoslanishi` | `comment` | Причина покупки. Существующая колонка, новой не нужно |
> | Готовый PDF | `pdf_url` | Снимок в MinIO |
> | Ректор, проректор, подпись | настройки приложения | Константы, в БД не хранятся |
>
> **Номер и дата на бланке не печатаются.** В БД остаются — нужны для поиска и связи с приобретениями. Свой входящий номер канцелярия ставит от руки при регистрации.
>
> **Печать не меняет статус, перепечатка безопасна.** На бланке нет колонок «приобретено» и «остаток к приобретению» — только запрошенное количество. Поэтому частичные закупки на бумагу не влияют, и повторная печать даёт тот же документ.
>
> **Шапка хранится целыми строками, а не «ФИО + окончание».** В узбекском аффикс зависит от последней буквы основы (`Umarova`+`ga`, но `Yo'ldosh`+`qa`). Склейка окончания в шаблоне однажды напечатала бы в официальном документе неверную форму — окончание входит в саму настройку.

**`notification_items`**
| id bigserial PK | notification_id FK→`notifications` NOT NULL **CASCADE** | product_id FK→`products` NOT NULL RESTRICT | qty_requested NUMERIC(14,3) NOT NULL CHECK > 0 |

> **`qty_purchased` и `остаток к приобретению` НЕ ХРАНЯТСЯ.** ТЗ помечает их «расчётное, только чтение». Считаются как `SUM(acquisition_items.qty)` по связанным приобретениям. Хранение создало бы второй источник правды и рассинхрон при удалении приобретения. Единица измерения в строке тоже не хранится — подтягивается из `products.unit_id`.

**`acquisitions`** — приобретение (частичная закупка)
| id bigserial PK | number varchar(32) **UNIQUE** NOT NULL | date date NOT NULL | **notification_id FK→`notifications` NOT NULL RESTRICT** | warehouse_id FK→`warehouses` NOT NULL RESTRICT | supplier varchar(255) NULL | author_id FK→`users` NOT NULL RESTRICT |

**`acquisition_items`**
| id bigserial PK | acquisition_id FK→`acquisitions` NOT NULL CASCADE | product_id FK→`products` NOT NULL RESTRICT | qty NUMERIC(14,3) NOT NULL CHECK > 0 | price NUMERIC(18,2) NULL |

**Связь-ключ:** одно `notifications` → **много** `acquisitions` (закупка частями в разные даты). Приобретение строго привязано к одному уведомлению.

**`transfers`** — перемещение между складами
| id bigserial PK | number varchar(32) **UNIQUE** NOT NULL | date date NOT NULL | from_warehouse_id FK→`warehouses` NOT NULL RESTRICT | to_warehouse_id FK→`warehouses` NOT NULL RESTRICT | author_id FK→`users` NOT NULL RESTRICT |

**`transfer_items`**
| id bigserial PK | transfer_id FK→`transfers` NOT NULL CASCADE | product_id FK→`products` NOT NULL RESTRICT | qty NUMERIC(14,3) NOT NULL CHECK > 0 |

### М4 + М2. Заявка (основание) и расход товара (проводка)

> **Архитектурное решение ADR-2 — читать внимательно, здесь чаще всего ошибаются.**
> Это **две отдельные таблицы**, связанные `requests.writeoff_id`, который заполняется **только в момент выдачи**. До нажатия «Выдано» строки в `writeoffs` не существует.
> Статусы принадлежат **заявке**, а не расходу. §6.2 ТЗ по старой памяти называет заявку «документом-расходом» — это терминологический хвост, структура определена здесь и в §10 ТЗ.

**`requests`** — заявка сотрудника на получение товара
| Атрибут | Тип | Правила |
|---|---|---|
| id | bigserial PK | |
| number | varchar(32) **UNIQUE** NOT NULL | своя серия нумерации; **именно этот номер печатается на бланке** |
| employee_id | FK→`users` NOT NULL RESTRICT | заполняется сервером из текущего пользователя |
| warehouse_id | FK→`warehouses` NOT NULL RESTRICT | склад выдачи |
| reason | text NOT NULL | обоснование получения |
| status | enum `draft\|to_print\|printed\|issued` NOT NULL default draft | |
| printed_at | timestamptz NULL | |
| issued_at | timestamptz NULL | |
| **writeoff_id** | FK→`writeoffs` NULL **UNIQUE** RESTRICT | проводка; NULL до выдачи |
| pdf_url | varchar(500) NULL | MinIO |
| created_at | timestamptz NOT NULL | фиксируется при подтверждении |

**`request_items`**
| id bigserial PK | request_id FK→`requests` NOT NULL CASCADE | product_id FK→`products` NOT NULL RESTRICT | qty NUMERIC(14,3) NOT NULL CHECK > 0 |

**`writeoffs`** — расход товара / учётная проводка списания
| id bigserial PK | number varchar(32) **UNIQUE** NOT NULL (**своя, независимая серия** — порча/брак заявки не имеют) | date date NOT NULL | warehouse_id FK→`warehouses` NOT NULL RESTRICT | expense_type_id FK→`expense_types` NOT NULL RESTRICT | **employee_id FK→`users` NULL** RESTRICT | author_id FK→`users` NOT NULL RESTRICT |

**`writeoff_items`**
| id bigserial PK | writeoff_id FK→`writeoffs` NOT NULL CASCADE | product_id FK→`products` NOT NULL RESTRICT | qty NUMERIC(14,3) NOT NULL CHECK > 0 | reason varchar(500) NULL |

**Связи:** `requests` 1:0..1 `writeoffs` (через `requests.writeoff_id`, UNIQUE). `writeoffs` без заявки — это порча/брак.

### М3. Ядро учёта

**`stock_movements`** — журнал движений, **append-only, единственный источник правды**
| id bigserial PK | product_id FK→`products` NOT NULL RESTRICT | warehouse_id FK→`warehouses` NOT NULL RESTRICT | **qty NUMERIC(14,3) NOT NULL со знаком** (приход +, расход −) | doc_type enum `acquisition\|transfer\|writeoff` NOT NULL | doc_id bigint NOT NULL (полиморфная ссылка на документ-основание) | created_at timestamptz NOT NULL |

> Записи **никогда не редактируются и не удаляются**. Перемещение порождает **две** записи: `−qty` у склада-источника и `+qty` у склада-получателя, обе с `doc_type='transfer'`.

**`stock_balances`** — актуальный остаток, **проекция журнала**
| id bigserial PK | product_id FK→`products` NOT NULL RESTRICT | warehouse_id FK→`warehouses` NOT NULL RESTRICT | qty NUMERIC(14,3) NOT NULL default 0 **CHECK (qty >= 0)** |
| **UNIQUE (product_id, warehouse_id)** |

> Денормализация **осознанная**, обоснование — access pattern AP-1: `SUM(stock_movements)` по миллионам строк не уложится в требуемые ≤500 мс. Обновляется **в той же транзакции**, что и вставка движения. Ночная задача-ревизор сверяет проекцию с журналом.

### М5. Кассы и деньги

**`cash_desks`** — ровно две строки, seed-данные
| id bigserial PK | type enum `teacher\|worker` NOT NULL **UNIQUE** | balance NUMERIC(18,2) NOT NULL default 0 |

**`money_income`** — приход денег (только `admin`)
| id bigserial PK | cash_desk_id FK→`cash_desks` NOT NULL RESTRICT | amount NUMERIC(18,2) NOT NULL CHECK > 0 | date date NOT NULL | author_id FK→`users` NOT NULL RESTRICT | comment varchar(500) NULL |

**`money_expense`** — расход денег (сотрудник)
| id bigserial PK | cash_desk_id FK→`cash_desks` NOT NULL RESTRICT | employee_id FK→`users` NOT NULL RESTRICT | expense_category_id FK→`expense_categories` NOT NULL RESTRICT | amount NUMERIC(18,2) NOT NULL CHECK > 0 | description text NOT NULL | **receipt_url varchar(500) NOT NULL** (чек обязателен) | date date NOT NULL |

### М7. Аудит

**`audit_log`** — append-only
| id bigserial PK | user_id FK→`users` NOT NULL RESTRICT | action varchar(50) NOT NULL | entity varchar(100) NOT NULL | entity_id bigint NULL | payload_diff jsonb NULL | ip inet NULL | created_at timestamptz NOT NULL |

---

## 4. Access patterns (определяют индексы и денормализацию)

| # | Операция | Частота | Фильтр / сортировка | Требование |
|---|---|---|---|---|
| AP-1 | Остаток товара на складе | **очень горячо**, при каждом списании | `(product_id, warehouse_id)` | точечный поиск + `FOR UPDATE`; **обоснование денормализации `stock_balances`** |
| AP-2 | Очередь «К печати» | **очень горячо** | `status = 'to_print'` | частичный индекс — селективность высокая, индекс крошечный |
| AP-3 | Счётчик бейджа | **каждые 30 сек на каждого админа** | `COUNT WHERE status='to_print'` | должен быть покрыт тем же частичным индексом |
| AP-4 | «Мои заявки» сотрудника | горячо | `employee_id`, sort `created_at DESC` | 1500+ пользователей |
| AP-5 | История движений (§8.1.3) | отчёт | период + склад + товар + вид документа, sort `created_at DESC` | **keyset-пагинация**, offset деградирует на длинной истории |
| AP-6 | Недокупленное (§8.1.2) | отчёт | `notification_items` LEFT JOIN `acquisition_items`, остаток > 0 | агрегат по `(notification_id, product_id)` |
| AP-7 | Контроль перезакупки | при каждом приобретении | `SUM(acquisition_items.qty)` по `(notification, product)` | `FOR UPDATE` на `notification_items` |
| AP-8 | Отчёт ДДС (§8.2) | отчёт | **фильтр по категории обязателен**, + касса, вид расхода, период, сотрудник | `money_expense` JOIN `users` |
| AP-9 | Баланс кассы | при каждом расходе | `cash_desks.id` | `FOR UPDATE` |
| AP-10 | Остатки по складам (§8.1.1) | отчёт | склад, товар, единица | пагинация |
| AP-11 | Проводка → заявка → бумага | поиск бухгалтерии | `requests.writeoff_id` | индекс для обратного поиска |
| AP-12 | Список складов в форме заявки | при каждом открытии формы сотрудником | `allows_issuance = true AND status = 'active'` | справочник крошечный — индекс не нужен, фильтр в запросе |

---

## 5. Data rules и инварианты

**Инварианты уровня БД (CHECK / UNIQUE — обязательны, не только код):**

| # | Инвариант | Где |
|---|---|---|
| INV-1 | `stock_balances.qty >= 0` | CHECK |
| INV-2 | **`(requests.status = 'issued') = (requests.writeoff_id IS NOT NULL)`** | CHECK — заявка выдана ⟺ есть проводка |
| INV-3 | `requests.writeoff_id` UNIQUE | одна проводка не принадлежит двум заявкам |
| INV-4 | `writeoffs.employee_id IS NOT NULL` ⟺ `expense_types.requires_employee = true` | CHECK или триггер: при «Порче»/«Браке» сотрудник не указывается, при «Выдаче» — обязателен |
| INV-5 | `transfers.from_warehouse_id <> to_warehouse_id` | CHECK |
| INV-6 | `qty > 0` во всех `*_items` | CHECK |
| INV-7 | `money_expense.receipt_url` NOT NULL | чек обязателен (§7.3) |
| INV-8 | `cash_desks.balance >= 0` | **см. открытый вопрос ОВ-2** — блокировка или предупреждение |
| INV-9 | `users.category IS NULL` ⟺ `users.role = 'admin'` | CHECK |

**Инварианты уровня сервиса (транзакции):**

| # | Правило | Реализация |
|---|---|---|
| SV-1 | **Контроль перезакупки.** `SUM(acquisition_items.qty)` по товару ≤ `qty_requested` в уведомлении | `FOR UPDATE` на `notification_items`, иначе TOCTOU: два параллельных приобретения оба прочитают остаток 10 и оба пройдут. Текст ошибки строго по §4.2: `Товар "Бумага A4": остаток к приобретению 10 шт, невозможно приобрести 15 шт` |
| SV-2 | **Остаток не редактируется напрямую** — только через `stock_movements` | единая точка записи `ledger.post()` |
| SV-3 | **Нельзя переместить больше, чем есть** на складе-источнике | `FOR UPDATE` на `stock_balances` |
| SV-4 | **Списание строго на `printed → issued`** | статусы `draft/to_print/printed` остаток не трогают |
| SV-5 | **Защита от двойного списания** | `UPDATE requests SET status='issued' WHERE id=? AND status='printed'` → rowcount 0 = конфликт. Условие **внутри** UPDATE, не проверка перед ним |
| SV-6 | **Касса определяется сервером** из `users.category` | клиент не может её прислать — иначе учитель спишет из кассы работников |
| SV-7 | **Автозакрытие уведомления** при остатке 0 по всем строкам | `status → closed` |
| SV-8 | Справочники **не удаляются физически** | `status → archived`, FK `ondelete=RESTRICT` |
| SV-9 | **Заявка возможна только со склада списания** (`warehouses.allows_issuance = true`). На порчу/брак/приобретения/перемещения НЕ распространяется | Проверка **в момент создания заявки** + BEFORE INSERT/UPDATE триггер на `requests`. **Не делать это внешним ключом на составной ключ `(id, allows_issuance)`**: FK запретил бы админу когда-либо снять галочку со склада, у которого есть исторические заявки. Правило действует на момент подачи, задним числом старые заявки не инвалидирует |

**Enums (закрытые множества):**
`users.role`: admin\|teacher\|worker · `users.category`: teacher\|worker · `notifications.status`: draft\|in_progress\|closed · `requests.status`: draft\|to_print\|printed\|issued · `stock_movements.doc_type`: acquisition\|transfer\|writeoff · `cash_desks.type`: teacher\|worker · статусы справочников: active\|archived

---

## 6. Legacy mapping

**Отсутствует.** Проект greenfield, миграции с существующей БД нет. Все атрибуты — новые (`legacy.is_new = true`, 🆕 во всех строках словаря данных).

---

## 7. Нефункциональные требования

| Категория | Требование |
|---|---|
| Масштаб | 1500+ сотрудников, сотни одновременных пользователей |
| Производительность | Отклик API ≤ **500 мс** для типовых операций; отчёты — пагинация и индексы |
| Целостность | Все операции с остатками и деньгами — в транзакциях; остаток не редактируется напрямую |
| Безопасность | JWT access 15 мин + refresh 30 дней (httpOnly cookie), RBAC, **Argon2id**, HTTPS, защита от перезакупки и минусового баланса |
| Аудит | Кто, когда, какой документ создал/изменил — `audit_log` |
| Файлы | Чеки и PDF — MinIO (S3), приватные бакеты, presigned URL TTL 5 мин, whitelist jpg/png/pdf, лимит 10 МБ, проверка по magic bytes |
| Локализация | Интерфейс **русский**, валюта **только UZS**, локальные форматы дат |
| Отказоустойчивость | Регулярные бэкапы БД, Docker |
| Расширяемость | Возможность добавить роль отдела закупки, интеграцию 1С/банк, ЭП |
| **Стек (предписан)** | **PostgreSQL 16 · FastAPI · SQLAlchemy 2.0 · Alembic · Pydantic v2 · React 18 + TS · Docker.** Django/DRF — запрещены, см. §0 |

---

## 8. Scope

**В scope:** М1–М7 полностью; две кассы; бумажная подпись; печатные формы PDF; отчёты с экспортом Excel/PDF; аудит; RBAC на три роли.

**Вне scope (явно):**
- Электронная / квалифицированная подпись — **нигде и ни в каком виде** (§6, §6.1; будущее расширение по §9)
- Интеграция с 1С и банком
- Отдельная роль отдела закупки (моделируется как `admin`)
- Резервирование товара под заявку (`qty_reserved` — задел на будущее, сейчас не делаем)
- Мультивалютность (только UZS)
- Согласование заявок (его нет по требованию §1.3)

---

## 9. Открытые вопросы и допущения

| # | Вопрос | Статус | Принятое допущение для проектирования |
|---|---|---|---|
| ОВ-1а | Шаблон **уведомления** (BILDIRISHNOMA) | **ЗАКРЫТ заказчиком 17.07.2026** | Бланк получен и реализован: `backend/app/templates/pdf/notification.html`, превью `.feature-dev/preview/bildirishnoma_preview.pdf`. Схема дополнена тремя колонками — см. §3 М2 |
| ОВ-1б | Шаблон **документа-расхода** (бланк с рукописной подписью) | **отложен заказчиком 17.07.2026, придёт позже** | **Этап 3 НЕ блокирует.** Шаблон — это файл, а не архитектура: статусная машина, очередь «К печати», `issue()` с проводкой и списанием строятся без него. До получения бланка используется черновой шаблон-заглушка со всеми полями по §6.4 (реквизиты, ФИО и категория сотрудника, склад, таблица товаров, причина, место для подписи); при получении настоящего бланка подменяется только HTML, код не трогается |
| ОВ-2 | Недостаток средств: блокировка или предупреждение | **ЗАКРЫТ заказчиком 17.07.2026** | **Жёсткая блокировка.** `CHECK (balance >= 0)` остаётся в DDL, схема финальна. Флага `CASH_OVERDRAFT_MODE` НЕ делать — ранняя формулировка «флаг, схема не меняется» была ошибочной: CHECK живёт в БД и приложением не обходится |
| ОВ-3 | Кто ставит статус «Напечатан» | открыт | **Допущение: вручную завскладом** — открытие PDF ≠ факт печати |
| ОВ-4 | Справочник поставщиков | открыт | **Допущение: `supplier` — строка в `acquisitions`**, отдельной таблицы нет |
| ОВ-5 | Может ли сотрудник заказывать с любого склада | **ЗАКРЫТ заказчиком 17.07.2026** | **Нет.** Только со складов с галочкой `allows_issuance`. Отмеченных может быть несколько. Ограничение — только на заявки сотрудников. См. `warehouses.allows_issuance` в §3 и правило SV-9 в §5 |
| ОВ-6 | Два номера на выдачу | решён аналитиком | На бумаге физически может стоять только номер заявки (проводки в момент печати ещё нет). Реестр §6.4 показывает **оба номера**, поиск по любому |
| ОВ-7 | Валидация контракта на SQLAlchemy | техдолг | `contract_validator.py` — Django-only. Не блокирует шаги 2–3 |

**Допущение по нумерации:** `notifications`, `acquisitions`, `transfers`, `requests`, `writeoffs` имеют независимые серии номеров, генерируемые сервером.

| ОВ-11 | **Редактирование черновиков документов** | открыт, найден на этапе 2 | В контракте у `notifications` (и `requests` — ОВ-10) нет ни одного `update=true`, статус `editable=False`. Значит созданный черновик нельзя ни исправить, ни удалить (удаления нет по SV-8). Админ с опечаткой в черновике уведомления попадает в тупик. **Допущение до ответа заказчика: не блокируем этапы, но перед сдачей нужен ответ** — либо добавить `update`-флаги на поля черновика + `PATCH` (правка контракта), либо разрешить отмену черновика (новый статус `cancelled`). Рекомендую первое: правка черновика до первого приобретения безопасна, историю не трогает. |
| — | Момент перехода `notifications.draft → in_progress` | **решён на этапе 2** | В ТЗ не задан (в отличие от чёткого SV-7 для `closed`). Принято: первое приобретение по уведомлению переводит его `draft → in_progress`. |
