# 14b. Фронтенд «Пользователи» (М7, admin) — форма/таблица из контракта

Продолжение `.feature-dev/14-users-crud.md`: бэкенд был готов и жив на :8000
(98 тестов зелёные, гейт контракта зелёный) — задача была чисто клиентская.

## Что сделано

1. **`npm run api:types`** — типы перегенерированы с живого бэка. `schema.d.ts`
   теперь содержит `UserList/UserRead/UserCreate/UserUpdate/PasswordResetIn` и
   пути `/api/v1/users`, `/api/v1/users/{id}`, `/api/v1/users/{id}/reset-password`.

2. **Словарь поля → UI** — `frontend/src/entities/user/model/fields.ts`:
   `userFields` переписан из `02-contract.json` (таблица `users`) ДОСЛОВНО —
   те же 9 атрибутов, те же API-флаги (id/full_name/username/email/
   password_hash/role/category/is_active/created_at). `password` формы создания
   НЕ атрибут словаря (на бэке помечен `__contract_extra_fields__` — колонки
   `password` нет, есть только `password_hash`), поэтому добавлен в форму вручную
   в обход `createFieldNames()`, с явным комментарием об этом в трёх местах
   (`fields.ts`, `UserCreateDialog.tsx`, `build-ui-manifest.ts`).

   Расширил `shared/lib/field-descriptor.ts`: `InputType` дополнен `"email"` и
   `"password"` — контракт задаёт эти input_type для `email`/`password_hash`, а
   в общем словаре типов их раньше не было (ни один из 5 справочников этапа 1
   их не использовал).

3. **API-слой** (без переиспользования `catalogApi`/`CatalogEntity` — у users
   нет `status`/архивации, но есть отдельный `reset-password`, поэтому сделан
   параллельный, но однотипный слой, как у `notifications`):
   - `entities/user/api/queries.ts` — `useUsers(params)` (GET `/users` с
     page/size/role/is_active/q), `useUser(id)` (GET `/users/{id}`, не
     используется в UI — детали хватает из строки списка, см. ниже).
   - `entities/user/api/mutations.ts` — `useCreateUser`, `useUpdateUser`
     (инвалидирует список + `['auth','me']`, т.к. правка себя должна обновить
     шапку), `useResetPassword`.
   - `shared/api/query-keys.ts` — добавлен `userKeys`.

4. **Таблица и фильтры** — `frontend/src/pages/users/UsersPage.tsx`
   (роут `/admin/users`, только admin): колонки ФИО/Логин/Email/Роль
   (`RoleBadge`, цвет+текст)/Категория (`categoryLabel`, «—» для admin)/Статус
   (`ActiveBadge` — тот же компонент, что и в catalog, как просили). Фильтры:
   роль (select), статус активности (select true/false), поиск `q` по
   ФИО/логину/email с локальным дебаунсом 400мс. Пагинация — `TablePagination`,
   как у справочников.

5. **Создание** — `features/users/user-form/UserCreateDialog.tsx`: full_name,
   username, email (опционально, подпись-подсказка «формат имя@npuu.uz»,
   плейсхолдер), role/category (общий `RoleCategoryFields` — category скрыт и
   не отправляется для admin), password (`PasswordInput` — глаз показать/
   скрыть, мин. 8 символов). Zod (`user.schema.ts`) зеркалит INV-9 через
   `superRefine`: role=admin+category → ошибка на category; role≠admin без
   category → ошибка на category. `toUserCreate()` шлёт ровно create-поля
   контракта + password; для admin `category` явно `null`.

6. **Правка** — `features/users/user-form/UserEditDialog.tsx`: full_name,
   email, role/category (та же логика показа/обнуления), is_active. username
   показан read-only Input (не входит в `UserUpdate`, `api.update=false`).
   `UserList` уже несёт все поля, нужные форме правки (в отличие от
   `warehouses`, где `address` было `get_index=false`) — префилл из строки
   таблицы, без догрузки `GET /users/{id}` (тот же приём, что у `UnitEditDialog`).
   Самозащита: `useMe()` сверяется с `row.id`; если это сам пользователь —
   чекбокс «Активен» `disabled` + подпись «Нельзя деактивировать собственную
   учётную запись», и `onSubmit` дополнительно форсит `is_active: true` в теле
   запроса (defense in depth, зеркалит `self_deactivation_forbidden`). Смену
   своей роли на клиенте НЕ блокирую (в задаче явно требовалась защита только
   для is_active) — `self_demotion_forbidden` ловится сервером, текст — тостом.

7. **Сброс пароля** — `features/users/reset-password/ResetPasswordDialog.tsx`:
   отдельный диалог (не часть формы правки — `POST /users/{id}/reset-password`
   это отдельная операция), новый пароль + подтверждение (`PasswordInput`
   × 2, сверка равенства в zod `.refine`), успех — `toast.success`.

8. **Ошибки сервера** — везде `applyApiError` (существующий `shared/lib/
   apply-api-error.ts`, не менял): 422 с `details.errors` → поле; иначе —
   `toast.error(message)` готовым текстом с бэка. Проверено вживую для
   `email_wrong_domain`, `duplicate`, `self_deactivation_forbidden`,
   `self_demotion_forbidden` (см. ниже) — во всех message с сервера показывается
   как есть, без переписывания на клиенте.

9. **Меню и роутинг**: новый раздел сайдбара **«Администрирование»** →
   «Пользователи» (иконка `Users`, только `roles: ["admin"]`), между
   «Отчёты» и «Справочники» — рядом с другими admin-разделами, а не среди
   «Справочники» (те читает любая роль, тут — только admin). Маршрут
   `/admin/users` добавлен в `router.tsx` под существующим
   `<RequireRole roles={["admin"]}>` (там же, где `/reports`, `/cash` и т.д.) —
   отдельного вложенного гварда не создавал, использовал уже существующий.
   Роут задан константой `ROUTES.users` в `shared/config/routes.ts`.

10. **Гейт контракта фронтенда** — добавил `users` в
    `scripts/build-ui-manifest.ts` (`ENTITIES`) и перегенерировал
    `ui_manifest.json` (16 → 19 view). Прогнал
    `python .claude/skills/frontend-component-design/assets/ui_contract_validator.py
    .feature-dev/02-contract.json frontend/ui_manifest.json` → `OK: UI matches
    the data dictionary contract.` Это не было явно в задаче, но это тот же
    гейт, что покрывает остальные 5 экранов — оставлять `users` вне его значило
    бы оставить новый экран непроверяемым тем же механизмом.

## Файлы

Новые:
- `frontend/src/entities/user/model/{types.ts,fields.ts}`
- `frontend/src/entities/user/api/{queries.ts,mutations.ts}`
- `frontend/src/entities/user/ui/RoleBadge.tsx`
- `frontend/src/entities/user/lib/category-label.ts`
- `frontend/src/features/users/user-form/{user.schema.ts,RoleCategoryFields.tsx,UserCreateDialog.tsx,UserEditDialog.tsx}`
- `frontend/src/features/users/reset-password/{reset-password.schema.ts,ResetPasswordDialog.tsx}`
- `frontend/src/pages/users/UsersPage.tsx`
- `frontend/src/shared/ui/password-input.tsx`

Правки:
- `frontend/src/shared/lib/field-descriptor.ts` (InputType +email/+password)
- `frontend/src/shared/api/model-types.ts` (+`UserCategory` алиас)
- `frontend/src/shared/api/query-keys.ts` (+`userKeys`)
- `frontend/src/shared/api/schema.d.ts` (регенерирован `npm run api:types`)
- `frontend/src/shared/config/routes.ts` (+`ROUTES.users`)
- `frontend/src/app/layouts/nav-config.tsx` (+раздел «Администрирование»)
- `frontend/src/app/router.tsx` (+роут `/admin/users`)
- `frontend/scripts/build-ui-manifest.ts` (+сущность `users`)
- `frontend/ui_manifest.json` (регенерирован)

## Проверено вживую (порт 8000, admin/admin12345)

Через `curl` теми же телами запросов, что шлёт UI (создание/правка/сброс —
ровно `toUserCreate()`/`toUserUpdate()`/`{password}`):

1. **Создание** `POST /users` (worker, `fe_test_ui1@npuu.uz`) → 201, id=155.
2. **Список** `GET /users?role=worker&q=fe_test&page=1&size=20` → 1 запись,
   форма `Page<User>` совпадает с типом.
3. **Деталь** `GET /users/155` → `UserRead` с `created_at`, совпадает с типом.
4. **Правка** `PATCH /users/155` (full_name, role worker→teacher, category→
   teacher, is_active) → 200, тело ответа = `UserRead`.
5. **Сброс пароля** `POST /users/155/reset-password` → 204; логин новым
   паролем `POST /auth/login` → 200 (токен выдан, роль в токене — teacher,
   как после правки).
6. **Ошибки** (тексты — то, что покажет `applyApiError` тостом):
   - `email=@gmail.com` → 422 `email_wrong_domain`,
     «Разрешена только корпоративная почта @npuu.uz…».
   - дубль `username=fe_test_ui1` → 422 `duplicate`,
     «Логин "fe_test_ui1" уже существует».
   - `PATCH /users/3 {is_active:false}` (сам admin) → 422
     `self_deactivation_forbidden` — в UI этот сценарий физически недостижим:
     чекбокс задизейблен для `me.id === row.id`.
   - `PATCH /users/3 {role:worker,category:worker}` (сам admin) → 422
     `self_demotion_forbidden` — на клиенте не блокируется (по ТЗ — только
     is_active), покажется тостом с этим текстом.
   - `POST /users` с `role=admin&category=worker` → 422 `validation_error`
     (INV-9). В UI недостижимо: при `role=admin` поле category скрыто и не
     попадает в тело (`toUserCreate`/`toUserUpdate` шлют `category: null`).
     См. «Что мешало» — у этой конкретной серверной ошибки `loc:["body"]`, не
     `["body","category"]`.
7. **RBAC** `GET /users` под `teach1/teach12345` → 403 (страница и так под
   `RequireRole admin`, но подтвердил, что бэк не откроется даже прямым вызовом).
8. **Уборка**: тестового пользователя удалить нельзя (DELETE нет, SV-8) —
   деактивировал `PATCH /users/155 {is_active:false}` в конце. Финально
   проверил `admin` (id=3, роль/is_active не изменились) и `teach1` (id=4,
   не тронут) — сиды чистые.

## Build

```
npm run build
> tsc -b && vite build
✓ 1893 modules transformed
✓ built in 2.70s
```
0 ошибок TypeScript. `npm run lint` (`tsc --noEmit`) — тоже чисто.

## (а) Отклонения от инструкции

- Не создавал отдельный `entities/user/ui`-компонент детали и не завожу
  «карточку пользователя» — задача просила таблицу + create/edit/reset-password
  диалоги, детального экрана не запрашивала; `created_at` (единственное поле
  только детали, `get_single=true`/`get_index=false`) нигде не показывается.
  Если он нужен — это один `<FormField disabled>` в `UserEditDialog`, добавлю
  по запросу.
- Добавил `users` в `scripts/build-ui-manifest.ts` и прогнал
  `ui_contract_validator.py` — не входило в явный список задач, но это тот же
  механизм проверки, что покрывает остальные 5 экранов; без этого новый экран
  выпадал бы из контрактного гейта фронтенда молча.
- Расширил `InputType` (`shared/lib/field-descriptor.ts`) значениями `"email"`
  и `"password"` — контракт явно указывает эти input_type для полей
  `email`/`password_hash`, а общий тип их раньше не описывал (ни один из 5
  справочников этапа 1 их не использовал). Без этого пришлось бы либо соврать
  тип поля как `"text"`, либо расширить словарь — выбрал расширение, т.к. это
  честнее отражает контракт.

## (б) Вопросы

- Нет открытых вопросов по реализации.

## (в) Что мешало

- `curl -d '{...кириллица...}'` в Git Bash на Windows один раз отдал бэку
  «There was an error parsing the body» — не баг бэка, а точка входа curl
  ломает UTF-8 кириллицу в инлайн-аргументе на этой платформе. Обошёл через
  `--data-binary @файл.json` (файл сохранён в utf-8 через Write) — все
  последующие проверки прошли штатно. Самого UI/fetch (`credentials:'include'`,
  `JSON.stringify`) это не касается — там кодировка тела не зависит от shell.
- Обнаружил (не чинил, вне периметра задачи и общий для всех форм проекта):
  ошибка INV-9 от `model_validator(mode="after")` на бэке приходит как
  `{"code":"validation_error","details":{"errors":[{"loc":["body"], "msg":
  "...категория не указывается"}]}}` — `loc` длиной 1 (`["body"]`), без имени
  поля. `shared/lib/apply-api-error.ts` берёт последний сегмент `loc` как имя
  поля и явно пропускает `loc==="body"` (`if (name && name !== "body")`), то
  есть в этом конкретном случае `setError` не сработает и юзер увидит общий
  тост «Проверьте правильность заполнения полей» вместо точного текста с
  сервера. На практике для М7 это недостижимо через UI (category скрыт для
  role=admin), поэтому не стал трогать общий `apply-api-error.ts` — правка
  задела бы все формы проекта, а не только users, и не входила в задачу.
  Если стоит почистить — это отдельная маленькая правка (доставать
  `details.errors[0].msg` в общий toast, когда `fieldErrors()` не смог
  распределить ни одной ошибки по полям).
