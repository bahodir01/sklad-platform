# 05 · Frontend, ЭТАП 1 — реализация (продолжение + дизайн)

**Вход:** живой код `frontend/src/` (~86 файлов от прошлой сессии, оборванной по лимиту) · архитектура `05a-frontend-architecture.md` · контракт `02-contract.json` (заморожен, не трогался) · дизайн-токены `05-design-tokens.json` · эталонный макет `sklad-ui-mockup.html`.
**Задача:** дописать недостающее и наложить утверждённый дизайн (бирюзовый акцент, светлая/тёмная темы). Контракт, backend, .claude — не изменялись (только чтение).

---

## 1. Что было готово до этой сессии

Прошлый агент успел собрать **нижние слои FSD полностью**, но не дошёл до каркаса и экранов:

- **`shared/`** — весь слой: HTTP-клиент (`credentials:'include'`, Bearer из синглтона, single-flight refresh на 401), `refresh.ts` (коллапс параллельных refresh в один промис), `token-store` (access в памяти JS, не localStorage), `errors.ts`/`apply-api-error.ts`, `query-keys.ts`, `catalog-crud.ts` + `catalog-hooks.ts` (обобщённый CRUD с инвалидацией §7.3, связка units→products), `use-page-params.ts` (фильтры в URL), `field-descriptor.ts`, `format.ts`, `zod-ru.ts`, `schema.d.ts` (типы этапа 1 руками, до `npm run api:types`), базовые shadcn-компоненты + `catalog-screen`/`data-table`/`status-filter`/`table-pagination`/`catalog-status-badge`/`form-field`.
- **`entities/`** — session (token/session-store, use-me, can), unit (+UnitSelect), product, warehouse, expense-type, expense-category: `model/fields.ts` (дескрипторы дословно из контракта), `model/types.ts`, `api/queries.ts`+`mutations.ts`.
- **`features/`** — `auth/login-form`, `auth/logout-button`, `catalog/archive-action` (+adapter), формы `unit`/`product`/`warehouse`/`expense-type` (create/edit/fields/schema).

**Чего не было (приложение физически не запускалось** — `index.html` ссылается на несуществующий `src/app/main.tsx`**):** весь `src/app/` (main, провайдеры, роутер, layouts, sidebar, topbar, гварды), весь `src/pages/`, форма `expense-category`, дизайн (в `index.css` стоял дефолтный slate shadcn), скрипт манифеста + `ui_manifest.json`.

---

## 2. Что дописано в эту сессию

### Каркас `src/app/`
- `main.tsx` — createRoot, импорт `../index.css`, `installZodRu()`, `AppProviders` → `RouterProvider`.
- `providers/QueryProvider.tsx` — QueryClient с дефолтами §7.1 (staleTime 5 мин, retry 0 на 4xx / 2 на 5xx через `isClientError`).
- `providers/AuthBootstrap.tsx` — тихий `POST /auth/refresh` при старте, полноэкранный лоадер до разрешения, регистрация обработчика «сессия потеряна» (гасит сессию + `queryClient.clear()`).
- `providers/ThemeProvider.tsx` — **новое**: переключатель тем (light/dark/system), предпочтение в localStorage (это UI-настройка, не секрет — запрет §6 касается только access-токена), применяет к `<html>` и класс `.dark`, и атрибут `data-theme`.
- `providers/index.tsx` — композиция Theme → Query → AuthBootstrap + `<Toaster/>` вне роутера.
- `router.tsx` — `createBrowserRouter`: публичный `AuthLayout`→`/login`; под `RequireAuth`→`AppLayout` — редирект `/`→`/catalog/products`, `/catalog`→products, 5 экранов справочников, `/403`, заглушки этапов 2–6, `*`→NotFound.
- `layouts/AppLayout.tsx` (sidebar+topbar+`<main>`+skip-link), `AuthLayout.tsx` (центрированная карточка), `AppSidebar.tsx`, `AppHeader.tsx`, `nav-config.tsx`.

### Гварды и права `entities/session/ui|lib`
- `RequireAuth.tsx` (статус сессии → `/login` с `from`), `RequireRole.tsx` (пишется заранее, на этапе 1 маршрутами не используется, отдаёт `/403`), `lib/use-can.ts` (хук над `can()`).

### Страницы `src/pages/`
- `login/LoginPage.tsx` (редиректит уже вошедшего), 5 экранов-контейнеров `catalog/*` (usePageParams + useCan + query + колонки из дескрипторов + CatalogScreen/DataTable/фильтры/пагинация/диалоги), `errors/{ForbiddenPage,NotFoundPage}`, `stub/StubPage` («в разработке»).
- Колонки строятся из `fields.ts` (заголовки через `fieldByName(...).label`), рендер ячеек — руками (граница генерации §4). Фильтры — только принимаемые API (`status`, `is_active`, `unit_id`, `allows_issuance`), поиска нет (Ф-5, К-C).

### Недостающая форма
- `features/catalog/expense-category-form/` — `schema.ts` (create=name, update=name+status), `ExpenseCategoryFormFields`, `Create`/`Edit` диалоги. Заголовок «Виды расхода денег» (контракт: НЕ путать с типами расхода товара).

### Манифест
- `scripts/build-ui-manifest.ts` — генерит `ui_manifest.json` из дескрипторов (`table` = имя таблицы контракта `expense_types`, а не URL-сегмент), + detail-вью склада. `frontend/ui_manifest.json` — 16 view.

---

## 3. Как наложен дизайн

Дизайн-токены (`05-design-tokens.json`, стиль «modern-with-accent», бирюза `#0D7D8A`/`#3BB0BD`) наложены **через переменные, а не переписыванием компонентов** — как и требует §11 («приход макета = правка переменных»):

- **`index.css`** — хекс-токены переведены в HSL и разложены по семантическим переменным shadcn (`--background`←surface-app, `--card`←surface-panel, `--primary`←accent-бирюза, `--muted`/`--secondary`←нейтральные поверхности, `--destructive`←danger, `--border`/`--ring`←border/focus-ring, `--radius`=8px). Так **все** существующие компоненты (button, input, select, dialog, badge…) приняли палитру без правок. Плюс отдельные переменные семантики статусов (`--success/--warning/--info` + `-soft`) и мягкого бренда (`--brand-soft/--brand-text`) для sidebar и бейджей.
- **Обе темы**: светлая (`:root`) и тёмная — тёмная включается классом `.dark` **и** атрибутом `[data-theme="dark"]` (их ставит ThemeProvider), плюс фолбэк `@media (prefers-color-scheme: dark)` до гидрации. Переключатель — кнопка в topbar (Sun/Moon).
- **`tailwind.config.js`** — добавлены `fontFamily` (Inter/JetBrains Mono из токенов) и цвета `success/warning/info` (+`soft`/`soft-foreground`) и `brand.{soft,text}`.
- **App shell по макету**: sidebar с брендом и разделами (Дашборд, К печати, Документы, Склад, Деньги, Отчёты, **Справочники** — живой раздел с 5 экранами), активный пункт — мягкий бренд `bg-brand-soft` (не сплошной акцент); topbar с поиском (отключён — К-C), переключателем темы, юзером (инициалы+ФИО+роль) и выходом.
- **Таблицы плотные, статусы — цветные бейджи**: `active`→`success` (мягкий), `archived`→`muted`; булевы колонки — «Да/Нет» текстом (цвет никогда не единственный сигнал, §11). Семантика статусов отделена от бренд-акцента (философия токенов).
- Пункты меню этапов 2–6 показаны, но `live:false` → ведут на `StubPage` «в разработке». Живой только М1.

---

## 4. Результат сборки

```
$ npm install            → 0 vulnerabilities
$ npm run ui:manifest    → ui_manifest.json записан: 16 view(s)
$ python ui_contract_validator.py 02-contract.json ui_manifest.json
                         → OK: UI matches the data dictionary contract.
$ npm run build          → tsc -b (без ошибок TypeScript) + vite build
   ✓ 1820 modules transformed
   dist/index.html                0.41 kB
   dist/assets/index-*.css       25.14 kB │ gzip: 5.56 kB
   dist/assets/index-*.js       563.10 kB │ gzip: 172.23 kB
   ✓ built in ~2.2s
```

Единственное предупреждение — размер JS-чанка > 500 kB (не ошибка). Код-сплиттинг маршрутов (`React.lazy`) — задел на потом, на этапе 1 не требовался.

**Попутно починены три бага прошлой сессии, из-за которых проект не собирался:**
1. `schema.d.ts` и `scripts/*` — в JSDoc-комментариях подстрока `entities/*/model` содержит `*/`, который **преждевременно закрывал блочный комментарий** → каскад синтаксических ошибок. Заменено на `entities/<x>/model`.
2. `tsconfig.app.json` — добавлен `vite-env.d.ts` в `include`, иначе декларация `*.css` не видна из `src/app/main.tsx` (main.tsx появился только сейчас).
3. `tsconfig.node.json` — добавлены `baseUrl`+`paths` `@/*`, т.к. `scripts/build-ui-manifest.ts` затягивает файлы `src/` в node-проект, где alias иначе не резолвился.

---

## 5. Что осталось до живого подключения к бэкенду

Спроектировано и собрано **структурно**; вживую связка ни разу не проверялась (по 05a §12в бэкенд сам не поднимался на БД). До «живого»:

1. **Поднять backend** (`docker compose`) и прогнать вручную первый сценарий: `login → refresh → CRUD справочника`. Если что-то не так с `path` refresh-cookie / SameSite / CORS — выяснится на первом экране (§12в).
2. **`npm run api:types`** — заменить рукописный `schema.d.ts` на сгенерированный из `/openapi.json`. Расхождение с бэком станет падением сборки. Если формы/типы разойдутся — правятся `schema.d.ts`-производные, компилятор укажет где.
3. **Гейт манифеста и `tsc` в CI** рядом (`ui_contract_validator.py` + `tsc --noEmit`).
4. Данные (`items/total/pages`), коды ошибок (401/403/404/409/422) и русский `message` уже обрабатываются клиентом — проверить на реальных ответах.

---

## 6. (а) Отклонения от архитектуры/токенов и почему

| # | Предписание | Решение | Почему |
|---|---|---|---|
| Д-1 | Токены — hex, tailwind — `hsl(var(--x))` | Токены переведены в **HSL** и разложены по **семантическим** переменным shadcn (не как «сырые» hex-переменные) | Так палитру принимают ВСЕ существующие компоненты без правок. Сохранена структура shadcn, значения — из токенов. Небольшая потеря точности при hex→HSL допустима (акцент и поверхности узнаваемы). |
| Д-2 | Тема через `data-theme` (макет) | ThemeProvider ставит **и** `.dark`-класс, **и** `data-theme` | Tailwind `darkMode:["class"]` + редкие `dark:`-варианты требуют класс; `data-theme` — паритет с макетом и CSS-фолбэком. Оба механизма + `prefers-color-scheme`. |
| Д-3 | Тема — UI-состояние (в Zustand по §7.4 — только sidebar) | Тема в **ThemeProvider (context) + localStorage**, не в Zustand | Тема должна примениться к `<html>` до/вне дерева и пережить перезагрузку; context+localStorage проще Zustand-persist. Access-токен по-прежнему НИКОГДА не в localStorage. |
| Д-4 | Макет: sidebar сворачивается | Свернутый режим (иконки) реализован через существующий `ui-store.sidebarCollapsed` | По §7.4 — да; кнопка-переключатель в topbar. |
| Д-5 | Макет показывает бейдж «К печати = 7» | Пункт «К печати» есть, но **без числа** | Числа неоткуда взять (эндпоинт `['requests','count']` — этап 3). Показать фейковое число = соврать пользователю (принцип §12а Ф-5). Слот бейджа готов (`NavItem.badge`), включится на этапе 3. |
| Д-6 | Макет: активная строка поиска | Поиск в topbar **отключён** (`disabled`, «в разработке») | API не принимает `name__icontains` (К-C, Ф-5). Показан для полноты shell, но не притворяется рабочим. |
| Д-7 | Архитектура §3: `entities/<x>/ui/StatusBadge.tsx` на сущность | Один общий `shared/ui/catalog-status-badge` | Уже так у прошлого агента; статус active/archived одинаков у всех — дублировать бейдж по сущностям = дрейф. Оставлено. |

Все привязки полей, флаги API, ключи Query, роутинг, auth — строго по 05a; отклонения §12а прошлого агента (Ф-1…Ф-7) соблюдены.

## 6. (б) Что мешало

- **Три бага-«невидимки» прошлой сессии** (см. §4): `*/` внутри `entities/*/model` в комментариях рушил парсер, и это всплыло только сейчас, потому что до появления `main.tsx`/скрипта эти файлы не втягивались в сборку в проблемной конфигурации. Диагностировалось по каскадным `TS1005`/`TS2307`.
- **Бэкенд не поднят** — сквозная проверка «логин→CRUD» невозможна в этой сессии; сдано структурно, живой прогон вынесен в §5 как первый шаг.
- **Рукописный `schema.d.ts`** — приходится держать его в синхроне с контрактом руками до `api:types`; тип-безопасность форм опирается на его точность.
- Контракт заморожен: открытые вопросы К-A…К-I (05a §12б) не «чинились» — реализовано строго по флагам, расхождения обеспечивает бэкенд (422 с русским текстом).
