# 05a · Frontend, ЭТАП 1 «Фундамент + М1 Справочники»

**Вход:** `02-contract.json` (источник правды, флаги соблюдены буквально) · `01-requirements.md` (ТЗ) · `03-architecture.md` §7 (принятые решения) · `04-backend-stage1.md` + живой код `backend/app/` (прочитан, не изменён).
**Стек — предписан ТЗ §2.1, не выбирался:** React 18 + TypeScript · shadcn/ui + Tailwind · TanStack Query (сервер) + Zustand (UI) · React Hook Form + Zod · типы из OpenAPI (`openapi-typescript`). Интерфейс русский, даты `ru-RU`, валюта UZS.
**Код не пишется** — это структура для `frontend-developer`.

**Scope этапа 1:** каркас (роутинг, провайдеры, layout, роли) · логин и хранение токенов · М1 CRUD (`units`, `products`, `warehouses`, `expense_types`, `expense_categories`) · галочка `allows_issuance` в карточке склада · архивация вместо удаления.
**Вне scope:** документы, заявки, очередь «К печати», кассы, отчёты, **экраны уведомлений** (контракт `notifications` меняется параллельно — спроектированное сейчас устареет).

---

## 1. Что уже отдаёт backend (проверено по коду, а не по документу)

| Факт | Значение | Источник |
|---|---|---|
| Префикс API | `/api/v1` | `core/config.py:21` |
| Эндпоинты М1 | `GET,POST /{units,products,warehouses,expense-types,expense-categories}` + `GET,PATCH /{...}/{id}` | `modules/catalog/router.py` |
| **DELETE** | **не существует ни для одного справочника** (SV-8) | там же |
| Auth | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout` (204), `GET /auth/me` | `modules/auth/router.py` |
| Тело логина | `{username, password}`, `username` 1..150, `password` 1..128 | `auth/schemas.py:109` |
| Ответ логина | `{access_token, token_type:"bearer", expires_in}` — **refresh в теле нет** | `auth/schemas.py:114` |
| Refresh-cookie | httpOnly + Secure + SameSite=lax, имя `refresh_token`, **path `/api/v1/auth`** | `core/config.py:45-50` |
| CORS | `allow_credentials=true`, origins `http://localhost:5173`, headers `Authorization, Content-Type, Idempotency-Key` | `main.py:49` |
| Конверт списка | `{items, total, page, size, pages}` | `shared/pagination.py` |
| Параметры списка | `page` (≥1), `size` (≥1, ≤200, по умолчанию 50) | там же |
| Конверт ошибки | `{code, message, details}` — `message` уже готовый русский текст | `core/exceptions.py` |
| Коды | 422 — доменные и валидация; **401/403/404/409 оставлены собой** (Б-6) | там же |
| Access TTL | 900 с | `core/config.py:40` |

**Реализованные фильтры списков — подмножество тех, что объявлены в контракте** (см. К-C в §11б):

| Эндпоинт | Есть в API | Объявлено в контракте, но в API нет |
|---|---|---|
| `/units` | `is_active` | `code` |
| `/products` | `status`, `unit_id` | `name__icontains`, `sku` |
| `/warehouses` | `status`, `allows_issuance` | `code`, `name__icontains` |
| `/expense-types` | `status` | `name__icontains`, `requires_employee` |
| `/expense-categories` | `status` | `name__icontains` |

Скилл `frontend-component-design` предписывает давать фильтры только по полям с `filter` в контракте. Уточняю правило до реализуемого: **фильтр рисуется на пересечении «объявлен в контракте» ∧ «принимается API»**. Отсюда — отсутствие строки поиска в таблицах на этапе 1 (§11а, п.5).

---

## 2. Выбор фреймворка

Не выбирался — предписан ТЗ §2.1 и зафиксирован в архитектуре §7 (feature-sliced, Query+Zustand, RHF+Zod, `openapi-typescript`). Подтверждаю применимость: контракт даёт конкретные типы и флаги, TypeScript их удерживает на компиляции; второй фреймворк в проект не вводится.

**Генерация типов** (единственная защита от расхождения фронта с бэком):

```
npm run api:types   →  openapi-typescript http://localhost:8000/openapi.json -o src/shared/api/schema.d.ts
```

`schema.d.ts` коммитится и в CI перегенерируется: расхождение с бэком = падение сборки. Ручных `interface Unit {...}` в проекте быть не должно — все типы выводятся из `components['schemas'][...]`.

---

## 3. Структура каталогов (feature-sliced, архитектура §3 и §7)

Импорт строго вниз: `app → pages → features → entities → shared`.

```
frontend/src/
├── app/
│   ├── main.tsx                    # createRoot, <html lang="ru"> в index.html
│   ├── providers/
│   │   ├── QueryProvider.tsx       # QueryClient + дефолты (§7.1)
│   │   ├── AuthBootstrap.tsx       # тихий refresh при старте — критично, см. §6
│   │   └── index.tsx               # композиция провайдеров
│   ├── router.tsx                  # createBrowserRouter, карта §5
│   └── layouts/
│       ├── AppLayout.tsx           # Sidebar + Header + <Outlet/>
│       └── AuthLayout.tsx          # центрированная карточка для /login
├── pages/
│   ├── login/LoginPage.tsx
│   ├── catalog/
│   │   ├── UnitsPage.tsx · ProductsPage.tsx · WarehousesPage.tsx
│   │   ├── ExpenseTypesPage.tsx · ExpenseCategoriesPage.tsx
│   └── errors/{ForbiddenPage,NotFoundPage}.tsx
├── features/
│   ├── auth/{login-form,logout-button}/
│   └── catalog/
│       ├── unit-form/ · product-form/ · warehouse-form/
│       ├── expense-type-form/ · expense-category-form/
│       │     каждая: <XCreateDialog>, <XEditDialog>, <XFormFields>, x.schema.ts
│       └── archive-action/{ArchiveAction.tsx, archive-adapter.ts}   # см. §9.6
├── entities/
│   ├── session/
│   │   ├── model/token-store.ts    # access в памяти JS (§6)
│   │   ├── model/session-store.ts  # Zustand: только статус сессии
│   │   ├── api/use-me.ts           # useQuery(['auth','me'])
│   │   └── lib/can.ts              # can(user,'catalog:write') === role==='admin'
│   ├── unit/ · product/ · warehouse/ · expense-type/ · expense-category/
│   │     каждая: model/fields.ts (§4) · model/types.ts (из schema.d.ts)
│   │              api/queries.ts · api/mutations.ts · ui/XSelect.tsx · ui/StatusBadge.tsx
├── shared/
│   ├── api/{schema.d.ts, client.ts, refresh.ts, errors.ts, query-keys.ts}
│   ├── ui/                         # shadcn: button, input, table, dialog, select,
│   │                               # checkbox, badge, skeleton, sonner, pagination…
│   ├── lib/{format.ts, zod-ru.ts, use-page-params.ts}
│   └── config/{routes.ts, roles.ts}
└── scripts/build-ui-manifest.ts    # генерирует ui_manifest.json из entities/*/fields.ts
```

---

## 4. Дескрипторы полей — почему не хардкод колонок

Скилл требует: «генерировать формы и таблицы из данных контракта, чтобы дрейф был невозможен по построению». В React это делается так:

`entities/<x>/model/fields.ts` — массив дескрипторов, **переписанный из контракта дословно** (имя, `label`, `input_type`, `required`, `max`, `disabled`, `validations`, `table_view`, четыре API-флага). Из одного массива выводятся:

1. **колонки таблицы** — `filter(f => f.api.get_index && f.table_view === '✓')`;
2. **состав формы создания** — `filter(f => f.api.create)`, правки — `filter(f => f.api.update)`;
3. **`ui_manifest.json`** — генерируется `scripts/build-ui-manifest.ts` и проверяется гейтом:

```
python .claude/skills/frontend-component-design/assets/ui_contract_validator.py \
       .feature-dev/02-contract.json  frontend/ui_manifest.json
```

В манифесте `table` — **имя таблицы контракта** (`expense_types`), а не сегмент URL (`expense-types`). Гейт добавить в CI рядом с `tsc --noEmit`.

> **Граница генерации.** Дескрипторы задают *состав и правила*, а не разметку. Верстка каждой формы пишется руками — таблично-генерируемые формы («один компонент рисует всё по конфигу») ломаются на первом же нестандартном поле, а такие тут есть (`unit_id` в правке товара — статикой, `allows_issuance` — с поясняющим текстом).

---

## 5. Карта роутинга по ролям

```
/login                       public · аутентифицированного редиректит на /
/                            RequireAuth → редирект по роли (см. ниже)
/catalog                     → redirect /catalog/products
/catalog/products            RequireAuth (any) · запись — admin
/catalog/units               RequireAuth (any) · запись — admin
/catalog/warehouses          RequireAuth (any) · запись — admin
/catalog/expense-types       RequireAuth (any) · запись — admin
/catalog/expense-categories  RequireAuth (any) · запись — admin
/403                         ForbiddenPage
*                            NotFoundPage
```

**Редирект с `/`:** `admin` → `/catalog/products`; `teacher|worker` → `/catalog/products` (этап 1; с этапа 3 — `/my/requests`). Обоснование обоих отклонений от карты §7 архитектуры — в §11а, п.3 и п.4.

**Два разных гварда, не один:**

- `<RequireAuth>` — статус сессии `authenticated`, иначе `<Navigate to="/login" state={{from}}/>`. Все экраны М1 этапа 1 — только под ним.
- `<RequireRole roles={['admin']}>` — на этапе 1 **не используется ни одним маршрутом** и пишется сразу: с этапа 3 под него уходят `/to-print`, `/notifications`, `/reports/*`, `/cash`. Отдаёт `/403`, не `/login`: «не твоя роль» ≠ «войди заново», и редирект на логин здесь запутывает пользователя.

**Разделение чтение/запись внутри экрана** — не роутером, а `can(user,'catalog:write')` (`role === 'admin'`). Не-админ видит те же таблицы без кнопок «Добавить», «Изменить», «В архив». Это UX-слой, а не защита: запись закрывает `require_admin` на бэкенде.

**Зарезервировано, на этапе 1 не строится:** `/dashboard`, `/to-print`, `/notifications`, `/acquisitions`, `/transfers`, `/writeoffs`, `/stock`, `/cash`, `/reports/*`, `/my/*`. Константы путей — сразу в `shared/config/routes.ts`, чтобы этапы 2–6 не расползались строковыми литералами.

---

## 6. Аутентификация и хранение токенов

**Правило (§9 архитектуры, ТЗ §7): access — в памяти JS, refresh — httpOnly cookie. localStorage/sessionStorage не используются нигде — это XSS-кража токена.**

**Где живёт access.** Модульный синглтон `entities/session/model/token-store.ts`: `let accessToken: string | null` + `get/set/clear`. **Не** React-состояние, **не** Zustand.
Почему не Zustand, хотя Zustand в проекте есть: (1) токен не является состоянием рендера — от него ничего не перерисовывается; (2) `client.ts` живёт вне React и обязан читать токен синхронно, без подписки на стор; (3) к сторам со временем прирастает `persist`/devtools-мидлварь — а `persist` на токене = ровно тот localStorage, который §9 запрещает. Синглтон физически нечем сериализовать.

**Что лежит в Zustand:** `session-store.ts` — только `status: 'unknown' | 'authenticated' | 'anonymous'`. Он нужен именно как Zustand, а не как Query-стейт: перевести приложение в `anonymous` обязан `client.ts` из обработчика 401 — императивно, вне дерева React. Это единственное место этапа 1, где Zustand делает работу, которую больше нечем сделать.

**`<AuthBootstrap>` — обязателен, иначе F5 разлогинивает.** Access-токен в памяти умирает при перезагрузке вкладки, а refresh-cookie живёт 30 дней. При монтировании приложения:

```
POST /api/v1/auth/refresh   (cookie уходит сама)
  200 → tokenStore.set(access_token); status='authenticated'; далее GET /auth/me
  401 → status='anonymous'  (нормальный путь для незалогиненного, не ошибка — тост не показывать)
пока не разрешилось → полноэкранный лоадер, роутер не рендерится
```
Без этого гейта гварды успеют отработать на пустом токене и выкинуть на `/login` живую сессию.

**Обновление по 401 — single-flight.** В `shared/api/refresh.ts`: при 401 первый запрос дёргает `/auth/refresh`, остальные встают в очередь на тот же промис и после успеха повторяются один раз. Иначе таблица + `/auth/me` + селект дадут три параллельных refresh, а ротация с детекцией переиспользования (backend Б-1) погасит семью токенов и выкинет пользователя из системы — то есть наивная реализация ломается именно об эту защиту.
**Исключения из ретрая:** сами `/auth/login` и `/auth/refresh` (иначе рекурсия). Провал refresh → `tokenStore.clear()`, `status='anonymous'`, `queryClient.clear()`, редирект `/login`.

**Logout:** `POST /auth/logout` → `tokenStore.clear()` → **`queryClient.clear()`** → `/login`. Чистка кэша обязательна: без неё следующий пользователь на том же браузере увидит справочники и ФИО предыдущего из кэша Query до первого рефетча.

**Транспорт.** `credentials: 'include'` на всех вызовах API (cookie всё равно уходит только на `/api/v1/auth` — так задан её `path`). **Рекомендую dev-прокси Vite** `/api → http://localhost:8000` вместо кросс-оригинного `VITE_API_URL`: prod по архитектуре §2 — один origin за nginx, и прокси делает dev идентичным prod, снимая вопросы SameSite/Secure. CORS на бэке уже настроен и остаётся запасным путём.

**Экран `/login`.** Поля `username` + `password`, RHF+Zod, границы — **из `LoginRequest` (1..150 / 1..128), а не из контракта**: `users.username` в словаре имеет `validations: 3..150; без пробелов`, но это правило *создания* пользователя. Навесив его на логин, мы сделаем невходимой любую учётку с коротким логином. Ошибка `401 invalid_credentials` → общий текст под формой, без подсветки поля (не подсказываем, что именно не так). Кнопка блокируется на время запроса.

---

## 7. Состояние и кэш

Граница §7 архитектуры соблюдена: **сервер — в TanStack Query, локальный UI — в Zustand, не смешивать.** Ни один ответ API в Zustand не копируется.

### 7.1. Дефолты QueryClient

| Опция | Значение | Почему |
|---|---|---|
| `staleTime` | 5 мин для `['catalog', …]` | справочники меняются раз в неделю; дефолтный 0 даёт рефетч на каждый фокус окна впустую |
| `gcTime` | 5 мин (дефолт) | — |
| `retry` | 0 на 4xx, 2 на 5xx/сеть | ретраить 422/403 бессмысленно — ответ не изменится |
| `refetchOnWindowFocus` | `true` (дефолт) | со `staleTime` 5 мин стоит дёшево |
| `placeholderData` | `keepPreviousData` на списках | без него таблица мигает пустотой при смене страницы |

### 7.2. Ключи

Фабрика `shared/api/query-keys.ts`. Сегмент сущности = **сегмент URL** (`expense-types`), чтобы ключ и эндпоинт не разъехались:

```
catalogKeys.all(e)          = ['catalog', e]
catalogKeys.lists(e)        = ['catalog', e, 'list']
catalogKeys.list(e, params) = ['catalog', e, 'list', params]   // params = {page,size,...filters}
catalogKeys.detail(e, id)   = ['catalog', e, 'detail', id]
authKeys.me                 = ['auth', 'me']
```

`e ∈ 'units' | 'products' | 'warehouses' | 'expense-types' | 'expense-categories'`.
Иерархия неслучайна: `invalidateQueries({queryKey: ['catalog','units']})` накрывает **все** страницы, все фильтры и все детали разом — при 5 справочниках точечная инвалидация страниц не окупается.

### 7.3. Что и когда инвалидируется

| Мутация | Действие с кэшем |
|---|---|
| `POST /{e}` (создание) | `invalidate(['catalog', e])` |
| `PATCH /{e}/{id}` (правка **и архивация**) | `setQueryData(catalogKeys.detail(e,id), ответ)` + `invalidate(catalogKeys.lists(e))` |
| `PATCH /units/{id}` | дополнительно `invalidate(['catalog','products'])` — **см. ниже** |
| `POST /auth/login` | `invalidate(['auth','me'])` |
| `POST /auth/logout` | `queryClient.clear()` |

PATCH возвращает полный `XRead` — кладём его в деталь через `setQueryData` и не тратим лишний GET; списки инвалидируем, потому что запись могла уехать/приехать под текущий фильтр `status`.

**Единственная межсущностная связка этапа 1: `units → products`.** Таблица товаров рендерит код ЕИ, резолвя `unit_id` из кэша `['catalog','units']` (в контракте нет атрибута с названием ЕИ — К-F). Значит переименование ЕИ обязано обновить таблицу товаров. Инвалидация `['catalog','units']` перерисует её сама — но только если список ЕИ и есть источник резолва; поэтому резолв идёт **через тот же query-ключ**, а не через пропсы.

**Оптимистичных апдейтов на этапе 1 нет.** Списки маленькие, инвалидация возвращает свежие данные за один быстрый запрос, а откат оптимистики на 422 (дубль `code`) — лишний код с собственными багами. Это осознанный выбор, не упущение.

**Задел на этап 3 (не строить сейчас):** бейдж «К печати» — `refetchInterval: 30_000` на `['requests','count',{status:'to_print'}]`; `issue()` инвалидирует `['stock','balances']` + `['requests']` (архитектура §7). Ключ бейджа — **`requests`, не `writeoffs`**: по ADR-2 статусы принадлежат заявке (см. К-7 бэкенда).

### 7.4. Zustand — полный состав этапа 1

| Стор | Поля | Почему не Query и не useState |
|---|---|---|
| `session-store` | `status: 'unknown'|'authenticated'|'anonymous'` | пишется из `client.ts` вне React |
| `ui-store` | `sidebarCollapsed: boolean` | переживает навигацию между страницами |

Всё. Zustand на этапе 1 почти пуст — и это правильно: наполнять его копиями серверных данных ради «симметрии» значит завести второй источник правды на клиенте.

### 7.5. Фильтры и страница — в URL, не в сторе

Состояние `page`, `size`, `status`, `is_active`, `unit_id`, `allows_issuance` живёт в `useSearchParams` и оттуда попадает в ключ Query. Отклонение от буквы §7 («черновики фильтров» — в Zustand) с обоснованием в §11а, п.1.

---

## 8. План привязки данных

Легенда флагов: **I** = `get_index`, **S** = `get_single`, **C** = `create`, **U** = `update`. Всё — дословно из `02-contract.json`.

**Два правила, из которых растёт вся таблица ниже:**

1. **Колонка = `get_index` ∧ `table_view = '✓'`.** У всех `id` стоит `get_index: true`, но `table_view: '—'` — значит `id` **приходит в списке и не рисуется**: он нужен как React-key и как параметр диалога правки. Скилл говорит «колонки — из `get_index`»; контракт уточняет это своим же полем `table_view`, и уточнение сильнее.
2. **Поля нет в форме, если флаг `false`.** Не «disabled», не «скрыто CSS» — **отсутствует в схеме Zod и в payload**.

### 8.1. `units` → `/catalog/units`

| Атрибут | label | Флаги | Список | Форма создания | Форма правки |
|---|---|---|---|---|---|
| `id` | ID | I S | — (key) | — | — |
| `code` | Код ЕИ | I S C U | ✓ | `text`, required, max 16, `1..16`, unique | то же |
| `name` | Наименование ЕИ | I S C U | ✓ | `text`, required, max 100 | то же |
| `is_active` | Активна | I S **U** | ✓ «Да/Нет» | **нет** (`create=false`) | `checkbox` |

`UnitRead` = `UnitList` → **отдельного экрана детали нет**, деталь = диалог правки.
`code` unique: контракт помечает `unique (async check)`, но эндпоинта проверки нет → полагаемся на `422 duplicate` от бэка и кладём `message` на поле `code` (§10).

### 8.2. `products` → `/catalog/products`

| Атрибут | label | Флаги | Список | Создание | Правка |
|---|---|---|---|---|---|
| `id` | ID | I S | — (key) | — | — |
| `name` | Номенклатура | I S C U | ✓ | `text`, required, max 255 | то же |
| `unit_id` | Единица измерения | I S **C** | ✓ (код ЕИ из кэша) | `select`, required, опции `GET /units?is_active=true` | **нет** (`update=false`) → **статикой** |
| `sku` | Артикул | I S C U | ✓ | `text`, max 64, необязателен | то же |
| `status` | Статус | I S **U** | ✓ badge | **нет** | `select` `active|archived` |

- `unit_id` в правке: `update=false` → поля нет в `ProductUpdate` и в payload. Показываем строкой «Единица измерения: шт» (из детали), **а не `disabled`-селектом внутри RHF** — disabled-контрол намекает «разблокируется при условии», а условия нет: смена ЕИ у товара с историей движений переопределила бы смысл проведённых количеств (К-2 бэкенда, согласен). Подсказка контракта `disabled: True (при update)` этому чуть противоречит — К-E.
- Селект ЕИ фильтруется `is_active=true` (`validations: выбор только из активных ЕИ`). Следствие: у товара с заархивированной ЕИ её не будет в опциях. На этапе 1 неважно (`unit_id` не редактируется), но при создании товара — верно.
- Колонка ЕИ: см. К-F.

### 8.3. `warehouses` → `/catalog/warehouses` — **несущий экран этапа 1**

| Атрибут | label | Флаги | Список | Создание | Правка |
|---|---|---|---|---|---|
| `id` | ID | I S | — (key) | — | — |
| `code` | Код склада | I S C U | ✓ | `text`, required, max 32, unique | то же |
| `name` | Наименование склада | I S C U | ✓ | `text`, required, max 255 | то же |
| `address` | Адрес | **—** S C U | **нет** (`get_index=false`) | `text`, max 500 | то же |
| **`allows_issuance`** | **Склад списания** | I S C U | ✓ «Да/Нет» | **`checkbox`** | **`checkbox`** |
| `status` | Статус | I S **U** | ✓ badge | **нет** | `select` |

- **`allows_issuance` — требование заказчика (ТЗ §3, SV-9, ОВ-5 закрыт).** Галочка «Склад списания» обязана быть в карточке склада и в создании, и в правке. Под чекбоксом — поясняющий текст: «Сотрудник может подать заявку только со склада с этим признаком. Отмеченных складов может быть несколько». Не `radio`, не «один из» — множественный выбор.
- **Снятие галочки не блокируется и задним числом ничего не ломает** (SV-9: FK на составной ключ намеренно не сделан, правило действует на момент подачи заявки). Значит фронт не должен ни предупреждать «есть заявки с этого склада», ни запрещать снятие.
- **`address` есть в детали, но нет в списке** (`get_index=false`, К-3 бэкенда). Прямое следствие для фронта: **диалог правки склада обязан догрузить `GET /warehouses/{id}`** — префилл из строки таблицы невозможен, адрес там физически отсутствует. Открытие правки = +1 запрос; на время загрузки — скелет в теле диалога. Соблюдено буквально; хочет заказчик адрес в таблице — меняется флаг в контракте, не код (К-H).
- Задел этапа 3: форма заявки берёт склады `GET /warehouses?allows_issuance=true&status=active` (AP-12), параметры в API уже есть.

### 8.4. `expense_types` (расход **товара**) → `/catalog/expense-types`

| Атрибут | label | Флаги | Список | Создание | Правка |
|---|---|---|---|---|---|
| `id` | ID | I S | — (key) | — | — |
| `name` | Тип расхода товара | I S C U | ✓ | `text`, required, max 100 | то же |
| `requires_employee` | Требует сотрудника | I S C U | ✓ «Да/Нет» | `checkbox`, required | `checkbox` (активен, см. К-A) |
| `status` | Статус | I S **U** | ✓ badge | **нет** | `select` |

- `requires_employee` = `required: True` при `input_type: checkbox` — читается как «поле обязано присутствовать в payload», **не** «галочка должна быть отмечена»: для «Порчи»/«Брака» правильное значение `false` (INV-4). Zod: `z.boolean()` без `.refine(v => v === true)`. Двусмысленность формулировки — К-B.
- Подсказку `disabled: True (при update, если по типу есть проводки)` **на этапе 1 реализовать нечем** — признака «по типу есть проводки» нет ни в контракте, ни в API. Чекбокс активен, запрет обеспечивает бэкенд (`422`, роутер обещает русский текст вместо 500). К-A.

### 8.5. `expense_categories` (расход **денег**) → `/catalog/expense-categories`

| Атрибут | label | Флаги | Список | Создание | Правка |
|---|---|---|---|---|---|
| `id` | ID | I S | — (key) | — | — |
| `name` | Вид расхода денег | I S C U | ✓ | `text`, required, max 100 | то же |
| `status` | Статус | I S **U** | ✓ badge | **нет** | `select` |

Заголовок страницы — «Виды расхода денег», у `expense-types` — «Типы расхода товара». Контракт прямо предупреждает «НЕ путать»; два экрана с надписью «Расходы» в одном меню гарантируют путаницу.

### 8.6. `users` — экранов нет, но данные используются

CRUD пользователей — М7, вне этапа 1 (и роутера на бэке нет, Б-3). Используется только `GET /auth/me` → `UserRead`: `id`, `full_name`, `username`, `role`, `category`, `is_active`, `created_at`.
Фронт читает: `full_name` (шапка), `role` (гварды и `can()`). `LoginForm` **не входит в `ui_manifest.json`**: он привязан к DTO `LoginRequest`, а не к таблице словаря, и поля `password` в контракте нет вовсе (К-1 бэкенда → К-G).

### 8.7. Сводка манифеста (что проверит валидатор)

```json
{"views": [
  {"name":"UnitsTable",              "table":"units",              "kind":"list",  "fields":["code","name","is_active"]},
  {"name":"UnitCreateForm",          "table":"units",              "kind":"create","fields":["code","name"]},
  {"name":"UnitEditForm",            "table":"units",              "kind":"update","fields":["code","name","is_active"]},
  {"name":"ProductsTable",           "table":"products",           "kind":"list",  "fields":["name","unit_id","sku","status"]},
  {"name":"ProductCreateForm",       "table":"products",           "kind":"create","fields":["name","unit_id","sku"]},
  {"name":"ProductEditForm",         "table":"products",           "kind":"update","fields":["name","sku","status"]},
  {"name":"WarehousesTable",         "table":"warehouses",         "kind":"list",  "fields":["code","name","allows_issuance","status"]},
  {"name":"WarehouseDetail",         "table":"warehouses",         "kind":"detail","fields":["code","name","address","allows_issuance","status"]},
  {"name":"WarehouseCreateForm",     "table":"warehouses",         "kind":"create","fields":["code","name","address","allows_issuance"]},
  {"name":"WarehouseEditForm",       "table":"warehouses",         "kind":"update","fields":["code","name","address","allows_issuance","status"]},
  {"name":"ExpenseTypesTable",       "table":"expense_types",      "kind":"list",  "fields":["name","requires_employee","status"]},
  {"name":"ExpenseTypeCreateForm",   "table":"expense_types",      "kind":"create","fields":["name","requires_employee"]},
  {"name":"ExpenseTypeEditForm",     "table":"expense_types",      "kind":"update","fields":["name","requires_employee","status"]},
  {"name":"ExpenseCategoriesTable",  "table":"expense_categories", "kind":"list",  "fields":["name","status"]},
  {"name":"ExpenseCategoryCreateForm","table":"expense_categories","kind":"create","fields":["name"]},
  {"name":"ExpenseCategoryEditForm", "table":"expense_categories", "kind":"update","fields":["name","status"]}
]}
```

Файл **генерируется из `fields.ts`**, а не пишется руками — иначе он разойдётся с UI и станет проверять сам себя.

---

## 9. Дерево компонентов

### 9.1. Каркас

```
<QueryProvider>                       // QueryClient + дефолты §7.1
  <AuthBootstrap>                     // POST /auth/refresh; лоадер до разрешения
    <RouterProvider>
      ├── AuthLayout            → /login  → <LoginPage> → <LoginForm>
      └── AppLayout (RequireAuth)
            ├── <AppSidebar>          // навигация; пункты по can(); ui-store.sidebarCollapsed
            ├── <AppHeader>           // <UserMenu user={me}/> → <LogoutButton/>
            └── <Outlet/>             → страницы /catalog/*
    </RouterProvider>
  </AuthBootstrap>
  <Toaster/>                          // sonner, вне роутера — переживает навигацию
</QueryProvider>
```

### 9.2. Экран справочника — один шаблон на пять страниц

```
<CatalogScreen>                          // shared/ui, презентационный шелл
  ├── slot title      : <h1>Склады</h1>
  ├── slot actions    : {canWrite && <WarehouseCreateDialog/>}
  ├── slot filters    : <StatusFilter/> <AllowsIssuanceFilter/>   // ← только реализованные в API
  ├── slot table      : <DataTable columns={…} data={items} state={loading|empty|error}/>
  └── slot pagination : <TablePagination page size total pages/>
```

`CatalogScreen` и `DataTable` — **чистые презентационные**: ни `useQuery`, ни `useMutation` внутри. Данные тянет страница-контейнер (`WarehousesPage`) через хук сущности (`useWarehouses(params)`). Это граница «контейнер/презентация» из скилла.

### 9.3. Страница-контейнер (на примере складов)

```
WarehousesPage                                  // pages/catalog
 ├── useSearchParams()                          → {page,size,status,allows_issuance}
 ├── useMe()                                    → canWrite = can(me,'catalog:write')
 ├── useWarehouses(params)                      → entities/warehouse/api/queries
 ├── columns = buildColumns(warehouseFields, {canWrite})   // §4
 └── <CatalogScreen …>
       ├── <WarehouseCreateDialog/>             // features/catalog/warehouse-form
       └── row actions: <WarehouseEditDialog id/> · <ArchiveAction entity="warehouses" row/>
```

### 9.4. Форма — три файла на сущность

- `warehouse.schema.ts` — Zod, **типизированный ответным типом OpenAPI**: `z.ZodType<components['schemas']['WarehouseCreate']>`. Поле, отсутствующее в `WarehouseCreate`, не скомпилируется → флаги контракта охраняются компилятором, а не вниманием ревьюера.
- `WarehouseFormFields.tsx` — только поля; **create и update отдают разные наборы** (`mode` prop), потому что наборы флагов разные. Общая разметка, разные состав и схема.
- `WarehouseCreateDialog.tsx` / `WarehouseEditDialog.tsx` — `useMutation`, инвалидация (§7.3), тост, закрытие. Edit — плюс `useWarehouse(id)` (нужен `address`) и скелет на время загрузки.

### 9.5. Диалог, а не отдельная страница

CRUD справочников — до 6 полей, ни одного вложенного списка. Диалог (shadcn `Dialog`, Radix: фокус-трап, Esc, `aria-labelledby` из `DialogTitle`) даёт правку без потери контекста таблицы. **С этапа 2 правило меняется**: у документов есть строки-позиции — приобретения/перемещения/заявки будут полноценными страницами `/…/new` и `/…/{id}`. Диалог здесь — решение под размер формы, а не общий шаблон проекта.

### 9.6. `ArchiveAction` — единственное место, где живёт расхождение контракта

**Кнопки «Удалить» в проекте нет вообще** (SV-8; DELETE отсутствует и на бэке). Единственный необратимый-на-вид жест — «В архив», и он всегда `PATCH`.

`units` архивируется через `is_active: false`, остальные четыре — через `status: 'archived'` (К-5 бэкенда, подтверждаю). Чтобы это расхождение не расползлось по пяти экранам, — адаптер в одном файле:

```ts
// features/catalog/archive-action/archive-adapter.ts
units:               { field: 'is_active', archived: false,      active: true }
products | warehouses | expense-types | expense-categories:
                     { field: 'status',    archived: 'archived', active: 'active' }
```

`ArchiveAction` спрашивает подтверждение (`AlertDialog`), шлёт PATCH адаптированным телом, инвалидирует. Разархивация — тем же компонентом в обратную сторону. Если словарь когда-нибудь унифицируют до `status` — правится один файл.

---

## 10. Точки обращения к API

| Экран / компонент | Метод | Эндпоинт | Ключ / инвалидация |
|---|---|---|---|
| `AuthBootstrap` | POST | `/api/v1/auth/refresh` | — (пишет в tokenStore) |
| `LoginForm` | POST | `/api/v1/auth/login` | → `invalidate(['auth','me'])` |
| `AppHeader`, гварды | GET | `/api/v1/auth/me` | `['auth','me']` |
| `LogoutButton` | POST | `/api/v1/auth/logout` | → `queryClient.clear()` |
| `client.ts` (401) | POST | `/api/v1/auth/refresh` | single-flight, §6 |
| `UnitsPage` | GET | `/units?page&size&is_active` | `['catalog','units','list',p]` |
| `UnitCreateDialog` | POST | `/units` | → `['catalog','units']` |
| `UnitEditDialog` / `ArchiveAction` | PATCH | `/units/{id}` | → detail `setQueryData` + lists + `['catalog','products']` |
| `ProductsPage` | GET | `/products?page&size&status&unit_id` | `['catalog','products','list',p]` |
| `ProductForm` (селект ЕИ) | GET | `/units?is_active=true&size=200` | `['catalog','units','list',{is_active:true,size:200}]` |
| `ProductCreateDialog` | POST | `/products` | → `['catalog','products']` |
| `ProductEditDialog` / `ArchiveAction` | PATCH | `/products/{id}` | → detail + lists |
| `WarehousesPage` | GET | `/warehouses?page&size&status&allows_issuance` | `['catalog','warehouses','list',p]` |
| **`WarehouseEditDialog`** | **GET** | **`/warehouses/{id}`** | `['catalog','warehouses','detail',id]` — **обязателен ради `address`** |
| `WarehouseCreateDialog` | POST | `/warehouses` | → `['catalog','warehouses']` |
| `WarehouseEditDialog` / `ArchiveAction` | PATCH | `/warehouses/{id}` | → detail + lists |
| `ExpenseTypesPage` | GET | `/expense-types?page&size&status` | `['catalog','expense-types','list',p]` |
| `ExpenseType{Create,Edit}` / `ArchiveAction` | POST / PATCH | `/expense-types[/{id}]` | → `['catalog','expense-types']` |
| `ExpenseCategoriesPage` | GET | `/expense-categories?page&size&status` | `['catalog','expense-categories','list',p]` |
| `ExpenseCategory{Create,Edit}` / `ArchiveAction` | POST / PATCH | `/expense-categories[/{id}]` | → `['catalog','expense-categories']` |

**Передача в `api-integration specialist`.** Из `schema.d.ts` берутся типы `{Unit,Product,Warehouse,ExpenseType,ExpenseCategory}{List,Read,Create,Update}` и `Page<T>` — руками их не объявлять. Единый клиент `shared/api/client.ts`: base `/api/v1`, `credentials:'include'`, `Authorization: Bearer` из tokenStore, разбор `{code,message,details}` в `ApiError`, single-flight refresh на 401.

**Обработка ошибок (конверт бэка уже готов к этому):**

| Код | Поведение фронта |
|---|---|
| 401 | single-flight refresh → повтор; провал → `/login` |
| 403 | тост `message` («Недостаточно прав…»); на маршруте — `/403` |
| 404 | `NotFoundPage` / «Запись не найдена» в диалоге |
| 409 | тост `message` |
| 422 | если `details.errors` есть → `setError` на поля по `loc` (имена = атрибуты контракта); иначе `message` в тост (доменные ошибки типа `duplicate` уже несут готовый русский текст) |
| 5xx / сеть | тост «Не удалось связаться с сервером» + Retry; 2 ретрая уже сделал Query |

`message` **никогда не переписывается на клиенте**: §6 архитектуры гарантирует готовый русский текст (формат §4.2 ТЗ), и дублировать формулировки на фронте — значит завести второй словарь ошибок, который разойдётся с бэкендом.

---

## 11. Доступность и дизайн-система

Макета заказчика нет (см. §12в) → базой берётся дефолтная тема shadcn/ui; токены (`--background`, `--foreground`, `--primary`, `--destructive`, `--muted`, радиусы) — CSS-переменные в `index.css`, шкала отступов — Tailwind 4/8/12/16/24/32/48. **Хардкод цветов и «магических» пикселей в компонентах запрещён** — только токены и утилиты: тогда приход макета = правка переменных, а не 15 файлов.

По скиллу `frontend-component-design`:

- `<html lang="ru">` — иначе скринридер прочтёт русский текст английским голосом.
- **Семантика:** `<table>` для таблиц (`<th scope="col">`, `<caption class="sr-only">Справочник складов</caption>`), `<button>` для действий, `<a>`/`<Link>` для навигации, заголовки по порядку (`h1` — один на страницу), `<nav>` для сайдбара, `<main>` для контента. Никаких div-кнопок.
- **Формы:** видимый `<label htmlFor>` у каждого поля; обязательные — визуально `*` **и** `aria-required`; ошибка — `aria-invalid` + `aria-describedby` на текст ошибки рядом с полем (не только сводкой сверху); submit заблокирован на время запроса (защита от дабл-клика); ошибки сервера ложатся на поля по имени атрибута контракта.
- **Чекбоксы `allows_issuance` / `requires_employee` / `is_active`:** Radix Checkbox — не нативный `<input>`, поэтому `id` + `htmlFor` обязательны явно; поясняющий текст — через `aria-describedby`.
- **Цвет — никогда единственный сигнал:** статус `active|archived` — `<Badge>` с текстом «Активен»/«В архиве»; булевы колонки — «Да»/«Нет» текстом (иконка допустима только вместе с текстом). Разница между активным и архивным складом обязана читаться в ч/б.
- **Клавиатура:** все действия достижимы Tab, фокус виден (`focus-visible`), диалоги — фокус-трап + Esc + возврат фокуса на кнопку-триггер (даёт Radix), skip-link на `<main>`.
- **Четыре состояния у каждого экрана:** loading — скелет строк (не пустой экран и не спиннер на всю страницу); empty — «Записей нет» + «Добавить» (только `canWrite`); error — текст + Retry; data.
- Тосты — sonner (`aria-live`), уважать `prefers-reduced-motion`.
- **Форматирование:** даты — `Intl.DateTimeFormat('ru-RU')`; деньги — `Intl.NumberFormat('ru-RU',{style:'currency',currency:'UZS'})` в `shared/lib/format.ts` уже на этапе 1 (денежных экранов пока нет, но хелпер должен появиться раньше первого `toFixed(2)` руками); числа — вправо, текст — влево.
- Контраст: пары text/background — не ниже WCAG AA 4.5:1; проверять при приходе фирменных цветов заказчика.

---

## 12. Итоги

### (а) Что решено иначе, чем предписано

| # | Предписание | Решение | Почему |
|---|---|---|---|
| **Ф-1** | Архитектура §7: Zustand — «черновики фильтров» | Фильтры и пагинация — в **URL** (`useSearchParams`); в Zustand их нет | Фильтр — вход в ключ Query, а не UI-состояние. В URL он шарится ссылкой, переживает F5 и «назад», и не может рассинхрониться со стором. Буква §7 нарушена, граница §7 («сервер в Query, UI в Zustand») — нет: фильтр не переехал в Query, он переехал в адрес. **Черновики фильтров** (набранное, но не применённое) остаются локальным `useState` формы фильтра |
| **Ф-2** | §7: «локальный UI — в Zustand» | Access-токен — в **модульном синглтоне**, не в Zustand | Токен не UI-состояние и не состояние рендера; `client.ts` читает его вне React синхронно. Главное: к сторам прирастает `persist`, а `persist` на токене = localStorage, запрещённый §9. Синглтон нечем сериализовать |
| **Ф-3** | §7: карта маршрутов admin включает `/dashboard` | `/dashboard` **не строится**; admin после логина → `/catalog/products` | Дашборд — метрики и бейдж «К печати» (этап 3). Сейчас его эндпоинтов не существует: получился бы пустой экран как точка входа админа |
| **Ф-4** | §7: `/catalog/*` перечислен только у admin; teacher/worker — `/my/*` | `/catalog/*` доступен **всем аутентифицированным** в режиме чтения; запись — `can()`=admin. teacher/worker после логина → `/catalog/products` | ТЗ и API прямо говорят «чтение любой ролью, запись только admin» (`require_any_role` на GET уже стоит). `/my/*` появится на этапе 3; до тех пор teacher/worker иначе попадают в приложение без единого экрана |
| **Ф-5** | Скилл: «фильтры — по полям с `filter` в контракте» | Строки поиска на этапе 1 **нет**; фильтры только те, что принимает API (§1) | Контракт объявляет `name__icontains`, API его не принимает (К-C). Поиск по загруженной странице при серверной пагинации искал бы в 50 из 500 записей и молча врал бы пользователю. Лучше отсутствие поиска, чем поиск, который не находит |
| **Ф-6** | Скилл: «колонки таблицы — из `get_index`» | Колонки = `get_index` ∧ `table_view='✓'` → `id` приходит, но не рисуется | Контракт у всех `id` ставит `table_view: '—'`. Своё же уточнение словаря сильнее общего правила скилла |
| **Ф-7** | — (решение уровня dev-окружения) | Vite-прокси `/api` вместо кросс-оригинного `VITE_API_URL` | Refresh-cookie имеет `path=/api/v1/auth`, `Secure`, `SameSite=lax`. Прокси делает dev тем же одним origin, что и prod за nginx (§2), и снимает целый класс «в проде работает, локально нет». CORS на бэке настроен и остаётся запасным путём |

### (б) Что в контракте показалось неверным — **сообщаю, не «чиню»**

Контракт не редактировался. Ниже — только то, что видно с фронта; К-1…К-7 бэкенда не дублирую, кроме мест, где у фронта есть **своя** цена вопроса.

| # | Где | Что не так | Предложение |
|---|---|---|---|
| **К-A** | `expense_types.requires_employee` → `frontend.disabled` | Подсказка `True (при update, если по типу есть проводки)` **нереализуема**: признака «по типу есть проводки» нет ни в контракте (нет атрибута), ни в API этапа 1 (нет счётчика в `ExpenseTypeRead`). Клиент не может вычислить условие | Либо добавить в `get_single` признак вида `is_used` / `writeoffs_count`, либо снять подсказку и честно записать «запрет обеспечивает сервер». Пока: чекбокс активен, отказ приходит 422 с русским текстом. **Ставлю первым: это единственный пункт, где фронт этапа 1 физически не может исполнить подсказку контракта** |
| **К-B** | `expense_types.requires_employee` → `frontend.required` | `required: True` при `input_type: checkbox` двусмысленно. Для «Порчи»/«Брака» правильное значение — `false` (INV-4), значит «required» здесь = «обязано присутствовать в payload», а не «должно быть отмечено» | Реализую как `z.boolean()` без `.refine(v => v===true)`. Уточнить формулировку в словаре: иначе следующий разработчик прочитает буквально и сделает галочку обязательной к простановке — «Порча» станет несоздаваемой |
| **К-C** | `backend.filter` у `products.name`, `warehouses.name/code`, `expense_types.name/requires_employee`, `expense_categories.name`, `units.code`, `products.sku` | Фильтры объявлены в словаре, но **в API этапа 1 их нет** — роутер принимает только `status`/`is_active`/`unit_id`/`allows_issuance` | Расхождение словаря и реализации. Либо добавить параметры в `catalog/router.py` (тогда фронт даёт поиск), либо убрать `filter` из словаря. Сейчас **блокирует строку поиска во всех пяти таблицах** — на 500+ позициях номенклатуры это заметно |
| **К-D** | `units.is_active` vs `status` у четырёх остальных (подтверждаю К-5 бэкенда) | «Косметическое» расхождение на фронте стоит конкретного: адаптер архивации, два разных фильтра (`is_active` vs `status`), разные `Update`-схемы, разные бейджи | Унифицировать до `status: active|archived` при следующей ревизии словаря. Цена сейчас — один файл `archive-adapter.ts`, в который расхождение локализовано; цена потом растёт с каждым новым экраном, читающим справочники |
| **К-E** | `products.unit_id` → `frontend.disabled` | `disabled: True (при update)` при `api.update = false`. Подсказка предполагает, что поле в форме правки есть и заблокировано; флаг говорит, что его там нет вовсе | Мелкое, но именно из таких подсказок рождается disabled-поле в форме и лишний ключ в payload. Реализовано по флагу: в правке `unit_id` **отсутствует**, ЕИ показана статикой. Само `update=false` считаю осознанным и правильным (согласен с К-2) |
| **К-F** | `products` — нет атрибута с названием/кодом ЕИ | `get_index` у `unit_id` даёт **число**. Таблица товаров без клиентского join показала бы «Единица измерения: 3» | Решено без правки контракта: резолв из кэша `['catalog','units']` (справочник крошечный, один запрос `size=200`, инвалидация связкой units→products уже описана §7.3). Если заказчик хочет серверный join (`unit_code` в `ProductList`) — это **новый атрибут в контракте**, а не «поправка в коде». Отмечаю как выбор, о котором стоит знать |
| **К-G** | `users` — нет атрибута `password` (подтверждаю К-1 бэкенда) | Фронтовое следствие: `LoginForm` невозможно покрыть `ui_contract_validator` — `password` валидатор сочтёт неизвестным полем | Не блокирует (форма привязана к DTO `LoginRequest`, а не к таблице), но означает: гейт контракта **не покрывает экран логина**. Если словарь должен покрывать входные поля API — нужна строка `password` (`create=true`, остальные `false`) |
| **К-H** | `warehouses.address` `get_index=false` (подтверждаю К-3) | Фронтовая цена: диалог правки склада обязан догружать `GET /warehouses/{id}` — префилл из строки таблицы невозможен | Соблюдено буквально. Если адрес нужен в таблице — **менять флаг в контракте**, не код. Указываю цену: +1 запрос на открытие правки |
| **К-I** | Задел, не этап 1 | `NUMERIC(18,2)`/`NUMERIC(14,3)` через Pydantic уедут в JSON числами → в JS это `float64` | Для реальных сумм UZS точности хватает, паники нет. Но к этапу 5 (кассы) стоит решить осознанно — сериализовать `Decimal` строкой безопаснее, чем ловить округление в балансе. Поднимаю сейчас, потому что позже это правка контракта + типов + всех форм денег |

### (в) Что заблокировано

| Экран / функция | Чем заблокировано | Можно ли строить сейчас |
|---|---|---|
| **Все пять экранов М1** | **Макет админ-панели (ТЗ §6.3) утверждён, но нам не передан** | **Да, структурно.** Спроектировано на стандартных компонентах shadcn/ui. При приходе макета меняются CSS-переменные темы и, возможно, шелл `AppLayout`; **не меняются** дерево компонентов, роутинг, ключи Query, привязка полей и валидации. Это главная зависимость этапа и осознанный размен: ждать макет = не сдать этап 1 |
| Строка поиска в таблицах справочников | **К-C** — фильтры объявлены в словаре, но не приняты API | Нет. Разблокируется параметром `q`/`name__icontains` в `catalog/router.py` (~час работы бэка) |
| Блокировка `requires_employee` в правке типа расхода | **К-A** — нет признака «по типу есть проводки» | Частично: чекбокс активен, отказ приходит с сервера. Разблокируется полем в `ExpenseTypeRead` |
| Адрес в таблице складов | **К-H** — `get_index=false` (по контракту, намеренно) | Нет и не нужно — соблюдаем флаг. Разблокируется только правкой контракта заказчиком |
| `/dashboard` | Нет эндпоинтов метрик и бейджа (этап 3) | Нет. Маршрут зарезервирован |
| Экраны пользователей (М7) | Нет роутера CRUD пользователей (Б-3) + нет `password` в контракте (К-G) | Нет. Вне scope этапа 1 |
| **Экраны уведомлений** | **Прямое указание: контракт `notifications` меняется параллельно** (`body_text`, `division_name`, `pdf_url`) | **Нет и не проектировалось.** Спроектированное сейчас устарело бы к моменту реализации |
| Заявки, очередь «К печати», кассы, отчёты | Этапы 2–6, эндпоинтов нет | Нет. Маршруты зарезервированы в `routes.ts` |

**Открытые вопросы ТЗ, на этап 1 не влияющие:** ОВ-3 (кто ставит «Напечатан»), ОВ-4 (справочник поставщиков) — оба про этапы 2–3.

**Не проверено запуском.** Документ — проектный; фронта в репозитории ещё нет, и бэкенд, по `04-backend-stage1.md` §4, сам ни разу не поднимался на живой БД (нет Docker/PostgreSQL на машине). Значит **связка «логин → refresh → CRUD справочника» вживую не проверялась ни разу ни с одной стороны**. Первое, что должен сделать `frontend-developer` после каркаса, — прогнать её руками на поднятом `docker compose`, до того как писать пять экранов: если что-то не так с `path` refresh-cookie, SameSite или CORS, это выяснится на первом экране, а не на пятом.

---

**Следующий шаг:** `frontend-developer` реализует по этому документу — каркас (§3, §6), затем `warehouses` первым экраном (он несёт `allows_issuance` и единственный требует догрузку детали — самый показательный из пяти), затем остальные четыре по шаблону §9.2. Параллельно `api-integration specialist` генерирует `schema.d.ts` и типизированный клиент по §10.
