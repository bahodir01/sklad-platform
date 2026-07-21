# 15e. Фронтенд экрана «Интеграции» (§5а спеки15)

Основание: `.feature-dev/15-telegram-bot-spec.md` §5а, `.feature-dev/15b-integrations-backend.md`
(готовый бэкенд на :8000). Последний кусок фичи Telegram-бота — админский
экран для секретов Telegram-бота и ИИ-поиска.

## Что сделано

### 1. Типы — перегенерированы из живого бэкенда
`npm run api:types` против `http://localhost:8000/openapi.json` →
`frontend/src/shared/api/schema.d.ts` дополнен `IntegrationRead`,
`IntegrationUpdate` и тремя операциями (`list_integrations_*`,
`update_integration_*`, `disable_integration_*`).

### 2. API-слой (`entities/integration`)
- `frontend/src/entities/integration/model/types.ts` — `Integration`,
  `IntegrationUpdate` из `components["schemas"]` (не объявлены руками),
  `IntegrationKind = "telegram" | "ai_search"` (сужение строкового `kind` для
  адресации `PUT/POST .../{kind}` — контракт держит его обычным varchar на
  случай будущего расширения набора).
- `frontend/src/entities/integration/api/queries.ts` — `useIntegrations()` →
  `GET /admin/integrations`.
- `frontend/src/entities/integration/api/mutations.ts` — `useUpdateIntegration()`
  → `PUT /admin/integrations/{kind}` тело `{secret}`; `useDisableIntegration()`
  → `POST /admin/integrations/{kind}/disable`. Обе инвалидируют
  `integrationKeys.all` на успехе.
- `frontend/src/shared/api/query-keys.ts` — добавлен `integrationKeys`.
- `frontend/src/shared/api/client.ts` — добавлен метод `api.put<T>()` (в клиенте
  был только `get/post/postForm/patch/del/getBlob` — `PUT` этой фиче
  понадобился впервые в проекте).

### 3. UI
- `frontend/src/features/integrations/integration-card/integration-secret.schema.ts`
  — zod-схема тела `{secret}` (клиент проверяет только «не пусто»; реальная
  валидация — на сервере: Telegram `getMe` / формат `sk-ant-...`, §5а).
- `frontend/src/features/integrations/integration-card/IntegrationCard.tsx` —
  одна карточка (переиспользуется для обеих интеграций):
  - Skeleton, пока `GET /admin/integrations` не ответил.
  - Бейдж статуса тем же `Badge`, что и `ActiveBadge` в catalog (`success`/`muted`),
    текст «Включена»/«Выключена» (дословно из контракта, label колонки
    `is_enabled`).
  - `display_name`, `masked_secret` (`font-mono`), `updated_at`
    (`formatDateTime`) — показаны, только если сервер их отдал (секрет ещё не
    задан → оба `null`, ничего лишнего не рендерится).
  - Поле нового секрета — `PasswordInput` (тот же компонент с глазком, что в
    users), плейсхолдер — текущая маска, если она есть. Кнопка «Сохранить и
    проверить» → `PUT`. Успех → тост + `form.reset` (секрет никогда не
    держится в поле после сохранения) + инвалидация карточки. Ошибка →
    `applyApiError` — тот же общий разбор, что и во всех формах проекта: при
    422 без `details.errors` (ровно так отвечает Telegram-ветка бэка) текст
    сервера идёт в toast как есть, без переписывания на клиенте.
  - Кнопка «Отключить» — видна только при `is_enabled`, `AlertDialog`
    (тот же компонент/паттерн, что `ArchiveAction` в catalog) с подтверждением
    → `POST .../disable`.
  - Пояснение под карточкой (`hint`, маленький текст) — ровно тексты из
    задачи для Telegram и ai_search, без изменений.
- `frontend/src/pages/integrations/IntegrationsPage.tsx` — `PageHeader` +
  сетка из двух `IntegrationCard` (`kind: telegram | ai_search`), общий
  error/retry-блок на весь экран (один запрос на обе карточки).

### 4. Роутинг и навигация
- `frontend/src/shared/config/routes.ts` — `ROUTES.integrations = "/admin/integrations"`.
- `frontend/src/app/layouts/nav-config.tsx` — пункт «Интеграции» (иконка
  `Plug`) в разделе «Администрирование», рядом с «Пользователи», `roles: ["admin"]`.
- `frontend/src/app/router.tsx` — маршрут под тем же `<RequireRole roles={["admin"]}>`,
  что и `/admin/users`.

## Проверено живьём (backend :8000, admin/admin12345)

Прямого браузерного автотеста не было — в окружении агента нет
Playwright/браузерного MCP-инструмента (проверил, в `frontend/` его тоже нет).
Проверил **тем же способом, каким код фактически бьёт по API** — теми же
методами/путями/телами, что вызывают хуки `useUpdateIntegration`/
`useDisableIntegration`/`useIntegrations`, плюс убедился, что `npm run build`
проходит и `npm run dev` поднимается без runtime-ошибки при загрузке бандла.

1. **Baseline** `GET /admin/integrations` — `ai_search` уже был включён с
   прошлого прогона backend-агента (`sk-ant-••••7890`), `telegram` пуст.
2. **(а) Заведомо невалидный Telegram-токен** `PUT /admin/integrations/telegram
   {"secret":"not-a-real-token"}` → `422 {"code":"validation_error","message":
   "Telegram отклонил токен: Not Found"}`. Прогнал через `applyApiError`
   логику вручную: `details.errors` нет → `fieldErrors()` пуст →
   `toast.error(error.message)` = ровно текст Telegram, без переформулировки.
   `GET` после — `telegram.is_enabled:false, masked_secret:null` — не
   сохранился, карточка не включилась бы.
3. **(б) `ai_search` тестовый ключ** `PUT /admin/integrations/ai_search
   {"secret":"sk-ant-test123"}` → `200 {"is_enabled":true,
   "masked_secret":"sk-ant-••••t123","display_name":"Anthropic API"}` — карточка
   показала бы маску и «Включена».
4. **«Отключить»** `POST /admin/integrations/ai_search/disable` →
   `200 {"is_enabled":false, "masked_secret":"sk-ant-••••t123"}` — статус
   сменился, секрет не стёрт (по дизайну бэка, см. 15b).
5. **403/404** — `GET /admin/integrations` с токеном teacher → `403 forbidden`
   (страница защищена `RequireRole admin`, тот же гвард, что у `/admin/users`);
   `POST /admin/integrations/nope/disable` → `404 not_found`.
6. **Возврат в чистое состояние** — финальный `GET /admin/integrations`:
   `ai_search.is_enabled:false`, `telegram.is_enabled:false` (телеграм вообще
   не трогался успешно ни разу — секрет как был `null`, так и остался).

## Build

```
cd frontend && npm run build
> tsc -b && vite build
✓ 1898 modules transformed
✓ built in 2.57s
```
0 ошибок TypeScript. (Существующее предупреждение vite про размер чанка
>500кБ — не по этой фиче, было в проекте и раньше.)

## Файлы

- `frontend/src/entities/integration/model/types.ts` (новый)
- `frontend/src/entities/integration/api/queries.ts` (новый)
- `frontend/src/entities/integration/api/mutations.ts` (новый)
- `frontend/src/features/integrations/integration-card/integration-secret.schema.ts` (новый)
- `frontend/src/features/integrations/integration-card/IntegrationCard.tsx` (новый)
- `frontend/src/pages/integrations/IntegrationsPage.tsx` (новый)
- `frontend/src/shared/api/query-keys.ts` (дополнен: `integrationKeys`)
- `frontend/src/shared/api/client.ts` (дополнен: `api.put`)
- `frontend/src/shared/config/routes.ts` (дополнен: `ROUTES.integrations`)
- `frontend/src/app/layouts/nav-config.tsx` (дополнен: пункт «Интеграции»)
- `frontend/src/app/router.tsx` (дополнен: маршрут `/admin/integrations`)
- `frontend/src/shared/api/schema.d.ts` (перегенерирован `npm run api:types`)

## (а) Отклонения от буквального текста задачи

1. **Нет отдельного эндпоинта/поля «удалить секрет полностью»** — «Отключить»
   вызывает только `disable` (как и определяет бэк, см. 15b «Отклонения» п.2).
   Плейсхолдер поля секрета при уже сохранённом секрете показывает текущую
   маску (`masked_secret`) как визуальную подсказку «что уже стоит», а не
   реальное значение — само поле всегда пустое при открытии/после сохранения.
2. **Проверка «живьём» — без браузерного клика**, инструментов
   Playwright/browser-MCP в окружении нет. Верифицировал контракт запросов
   (методы/пути/тела) 1:1 с кодом хуков напрямую через `curl` против :8000, и
   отдельно — что бандл собирается и dev-сервер поднимает страницу без
   runtime-исключения при загрузке. Рекомендую `ui-test-automator` прогнать
   реальный E2E (Playwright), когда/если он появится в проекте.

## (б) Вопросы к следующим агентам / заказчику

1. `masked_secret` используется как плейсхолдер поля ввода — не как реальное
   значение поля (оно расшифровке не подлежит по дизайну бэка). Если
   заказчик ожидает, что поле по умолчанию видит «начало» текущего секрета
   даже под маской для UX — сейчас это не так и не может быть (сервер не
   отдаёт секрет вообще).
2. Как и в 15b: если появится реальный вызов Anthropic при первом
   использовании ИИ-поиска и `display_name` начнёт обновляться не только по
   `PUT`, экран не потребует правок — он просто читает `display_name` из
   ответа `GET`, откуда бы он ни обновился.

## (в) Что мешало

- В окружении агента нет браузерного/Playwright MCP-инструмента, поэтому
  «живая» проверка ограничена API-уровнем (см. выше) + сборкой + успешным
  стартом dev-сервера, а не кликом по реальной странице в браузере.
