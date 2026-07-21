# 15f. Замена провайдера ИИ-поиска: Anthropic → Google Gemini

Основание: заказчик сменил провайдера — хочет Google Gemini, не Claude.
Контракт вызывающего кода (`suggest_products_ai(session, query, candidates)`,
`resolve_product_query`, `find_by_substring`, `find_all_paginated`) НЕ менялся
— переделан только провайдер внутри `modules/ai/service.py` и лёгкая проверка
формата ключа в `modules/admin/service.py`. Схема (`02-contract.json`) не
трогалась.

## Что заменено

### `backend/app/modules/ai/service.py`
- `import anthropic` → `from google import genai` + `from google.genai import
  types as genai_types`.
- `_AI_MODEL`: `"claude-haiku-4-5"` → `"gemini-2.5-flash-lite"` (дешёвая/
  быстрая модель — задача мелкая: классификация запроса по короткому списку
  id/name, тот же расчёт, что раньше был за выбором Haiku вместо полного
  Claude).
- Клиент: `anthropic.AsyncAnthropic(api_key=...)` + `client.with_options(
  timeout=5.0, max_retries=0).messages.create(...)` → `genai.Client(
  api_key=...)` + `client.aio.models.generate_content(model=..., contents=
  prompt, config=GenerateContentConfig(...))`.
- **Structured output включён** (как просила задача, вместо текстовой
  просьбы «верни строгий JSON»): `response_mime_type="application/json"`,
  `response_schema=list[int]` — пакет `google-genai` принимает питоновский
  generic-тип напрямую как схему (проверено локально: `GenerateContentConfig(
  response_schema=list[int])` строится без ошибок). Таймаут и отсутствие
  ретраев перенесены через `http_options=HttpOptions(timeout=5000,
  retry_options=HttpRetryOptions(attempts=1))` — тот же smysl, что был у
  `client.with_options(timeout=5.0, max_retries=0)` в Anthropic-варианте.
- `_extract_text` переписан под `response.text` (google-genai сам склеивает
  текстовые части ответа — аналог обхода `content`-блоков у Anthropic),
  оставлен в `try/except` на вызывающей стороне.
- `_parse_id_list` (текстовый парсинг `[...]` регэкспом как фолбэк) **оставлен
  без изменений** — используется как единственный способ разбора текста
  ответа (structured output гарантирует формат на стороне API, но парсинг
  результата всё равно проходит через тот же код, что раньше разбирал
  вольный текст — не блокировался на этом, как и разрешала задача).
- Таймаут 5с, `except Exception: return []` на обоих этапах (сетевой вызов и
  разбор ответа), сигнатура `suggest_products_ai` — не изменены.
- `_build_ai_prompt` — текст промпта не изменён по существу (только докстринг
  обновлён: упомянут structured output и что текстовый разбор — фолбэк).

### `backend/pyproject.toml`
- `"anthropic>=0.68"` → `"google-genai>=1.0"` (актуальный официальный пакет
  Google, `pip install google-genai`, НЕ `google-generativeai`). Установленная
  локально версия — 2.12.1.
- `anthropic` удалён из основных зависимостей: grep по всему `backend/`
  подтвердил, что кроме `pyproject.toml` и `modules/ai/service.py` пакет
  нигде не импортировался (`modules/admin/service.py` упоминал слово
  «Anthropic» только в комментариях/докстринге — обновлено ниже, кода
  зависимого от SDK там не было). Пакет `anthropic` также удалён из
  окружения (`pip uninstall -y anthropic`) — `import app.main` и
  `python -m pytest` прогнаны и до, и после удаления, оба раза чисто.

### `backend/app/modules/admin/service.py`
- `_AI_SEARCH_KEY_PREFIX = "sk-ant-"` — константа убрана целиком (жёсткая
  привязка к вендорскому префиксу Anthropic отсутствует).
- `_verify_ai_search_key`: теперь мягкая проверка — только `len(secret) >=
  _AI_SEARCH_KEY_MIN_LEN` (константа поднята с 10 до **20** символов, т.к.
  раньше 10 включало 7-символьный префикс `sk-ant-`; без префикса эта же
  цифра слишком низкая планка для реального ключа — 20 отсекает пустой/
  обрезанный ввод, не привязываясь к формату Google `AIza...`). Текст ошибки
  — `"Похоже, это не ключ API — ключ слишком короткий"` (без упоминания
  конкретного вендора/префикса).
- `display_name` для `ai_search`: `"Anthropic API"` → `"Google Gemini"`.
- Docstring модуля (шапка файла), докстринг `mask_secret` (пример маски
  `sk-ant-••••ab12` → `AIzaSyF••••ab12`) и докстринг `_verify_ai_search_key`
  — обновлены, ссылки на Anthropic заменены на Google Gemini/нейтральные
  формулировки, с явной пометкой, что провайдер менялся (см. этот файл).

### `frontend/src/pages/integrations/IntegrationsPage.tsx`
- Подсказка карточки `ai_search`: `"API-ключ Anthropic (console.anthropic.com)
  — используется для поиска товаров по смыслу, если сотрудник написал
  название на другом языке."` → `"API-ключ Google Gemini
  (aistudio.google.com/apikey) — используется для поиска товаров по смыслу,
  если сотрудник написал название на другом языке."` — единственное место во
  фронтенде, где упоминался Anthropic (grep по всему `frontend/` подтвердил).

## Прогоны на живой БД (postgres:5433/sklad)

Сервер на :8000 не трогал (не убивал), тестировал прямыми Python-вызовами
сервисного слоя + `httpx.ASGITransport` поверх `app.main.app` (не отдельный
TCP-порт — тот же процесс, что и HTTP-роутер, без риска зацепить чужой
:8000 со старым кодом). Скрипт: `scratchpad/verify_gemini_swap.py`.

**Baseline до теста** (реальное состояние БД, не подготовлено мной):
`ai_search: is_enabled=false, has_secret=false, display_name=NULL`.

**1. `find_by_substring` / `find_all_paginated`** — не менялись, прогнаны для
подтверждения, что модуль по-прежнему импортируется и работает после замены
зависимостей:
```
find_by_substring('бумага')       -> [(1, 'Бумага')]
find_by_substring(garbage)        -> []
find_all_paginated(page=1,size=2) -> total=2, items=[(1,'Бумага'),(2,'Вода')]
```

**2. `PUT /api/v1/admin/integrations/ai_search`** с фиктивным ключом
`AIzaSyFAKE1234567890abcdefghij`, реальный HTTP-запрос через ASGI-транспорт
(с валидным JWT админа, сгенерированным `create_access_token`):
```
status: 200
body: {'kind': 'ai_search', 'display_name': 'Google Gemini',
       'is_enabled': True, 'masked_secret': 'AIzaSyF••••ghij', ...}
```
`display_name="Google Gemini"` — подтверждено. `masked_secret` —
`AIzaSyF••••ghij` (7-символьный видимый префикс + `••••` + последние 4
символа) — маска строится по общей логике `mask_secret` (не зависящей от
конкретного вендора), корректна.

**3. `suggest_products_ai` с включённой интеграцией и фиктивным ключом —
РЕАЛЬНЫЙ сетевой вызов к Google Gemini API** (не мок): интеграция осталась
включённой после шага 2 (с тем же фиктивным ключом), вызвал
`suggest_products_ai(session, "paper", candidates)` с кандидатом `(1,
'Бумага')`. Ушёл настоящий HTTPS-запрос на `generativelanguage.googleapis.com`
(таймаут 5с/`attempts=1` из `HttpOptions` реально применились — вызов не
завис), Google отклонил фиктивный ключ (401/403 — код не логировал тело
ответа, но исключение поймано), результат:
```
suggest_products_ai(session, "paper", [Бумага]) -> []
```
Без исключения наружу — тот же контракт, что был с Anthropic (см.
15c, п.4: там тоже проверялась ветка ошибки реальным вызовом, не мокoм).
**Честно: успешный содержательный вызов (модель реально находит "Бумага" по
смыслу "paper") не проверен** — реального рабочего ключа Google Gemini в
этом окружении нет, как и не было ключа Anthropic в 15c. Подтверждено только
то, что код доходит до сети с ключом из БД и гасит любую ошибку API в `[]`.

**4. `resolve_product_query` с выключенной интеграцией** (интеграцию
отключил после шага 3 через `IntegrationService.disable`, восстанавливая
контракт задачи — «выключенная интеграция»):
```
resolve_product_query(session, "zzz_nonexistent_query_xyz", warehouse_id=1)
  -> matches=[], source='none'
```

**БД возвращена в исходное состояние** — сверено `SELECT` до/после:
`ai_search: is_enabled=false, secret_encrypted=NULL, display_name=NULL` —
идентично baseline. `products` не менялись (id 1 «Бумага», id 2 «Вода» —
теми же, что и до работы).

## pytest

```
python -m pytest -q
```
`128 passed, 1 warning in 25.40s`. Единственное предупреждение —
`DeprecationWarning` внутри самого пакета `google.genai.types` про
`_UnionGenericAlias` под Python 3.14 (окружение новее, чем таргетировал
пакет на момент релиза) — не ошибка, не связано с логикой сервиса, не
требует правки нашего кода.

Тестов, завязанных на `anthropic`/`ai_search`/ключевые слова провайдера, в
`backend/tests/` не было ни до, ни после (grep по `anthropic|ai_search|
AI_SEARCH|claude-haiku|sk-ant` в `tests/` — 0 совпадений) — 15c не добавляла
тестов на этот модуль, менять было нечего.

## Гейт

```
python .claude/skills/database-schema-design/assets/contract_validator_sqlalchemy.py \
  .feature-dev/02-contract.json <models/schemas...>
```
`OK: backend code matches the data dictionary contract.` — схема/контракт
не менялись, ожидаемо зелёный.

## Frontend

```
cd frontend && npm run build
```
`tsc -b && vite build` — 0 ошибок TS, сборка прошла (`built in 2.33s`).
Единственное предупреждение — `chunk larger than 500 kB` от Vite,
предсуществующее, не связано с этой правкой (однострочная замена текста).

## (а) Отклонения от буквального текста задачи

1. **`_AI_SEARCH_KEY_MIN_LEN` поднята с 10 до 20**, а не оставлена как есть
   без префикса. С префиксом `sk-ant-` (7 символов) порог 10 фактически
   требовал 3+ символа самого ключа — без префикса тот же порог 10
   пропускал бы почти любую короткую строку. 20 — по формулировке задачи
   («разумной длины, например `len(secret) >= 20`») — использовано ровно
   предложенное задачей значение.
2. **`response_schema=list[int]`, а не JSON Schema словарём.** Пакет
   `google-genai` принимает питоновский generic-тип напрямую (`list[int]`)
   как `response_schema` — это задокументированная и более простая форма,
   чем ручной JSON Schema dict; функционально эквивалентна «список чисел» из
   задачи. Проверено, что `GenerateContentConfig` с таким `response_schema`
   строится без ошибок локально (офлайн, без сети).
3. **Таймаут выставлен через `HttpOptions(timeout=..., retry_options=
   HttpRetryOptions(attempts=1))` внутри `GenerateContentConfig`**, а не
   через отдельный `with_options()`-подобный вызов — у `google-genai` нет
   прямого аналога `client.with_options()` из Anthropic SDK; `http_options`
   в конфиге вызова — задокументированный эквивалент (таймаут в мс,
   `attempts=1` = без ретраев, `attempts=0/1` по докстрингу пакета
   означает «без повторов»).
4. **Пункт 3 «Проверки боем» (реальный вызов к Google API) подтверждён
   только на ветке ошибки**, не успешного смыслового совпадения — нет
   рабочего ключа Gemini в этом окружении, как и не было ключа Anthropic в
   15c. Задокументировано честно в разделе «Прогоны», п.3.
5. **Тест PUT-эндпоинта сделан через `httpx.ASGITransport` поверх
   `app.main.app`**, а не через живой TCP-запрос к порту 8000 или 8017.
   Порт 8000 не трогал (по инструкции), а поднимать отдельный процесс на
   8017 ради одного PUT-запроса было бы избыточно — ASGI-транспорт
   выполняет тот же роутер/middleware/DI-граф FastAPI без сети, с гарантией,
   что тестируется именно текущий код (а не потенциально устаревший процесс
   на 8000).

## (б) Вопросы

1. Нет вопросов по контракту — интерфейс `suggest_products_ai`/
   `resolve_product_query`/`find_by_substring`/`find_all_paginated` не
   менялся, вызывающий код (бот, спека15 §6, если уже реализован) не должен
   требовать правок.
2. Как и в 15c: при первом реальном включении интеграции админом (с рабочим
   ключом Google AI Studio) стоит вручную прогнать `resolve_product_query` с
   англ./узб. запросом и сверить, что `gemini-2.5-flash-lite` действительно
   находит смысловое совпадение через structured output — эта часть
   (содержательная работа модели) физически не проверяема без реального
   ключа ни в 15c, ни здесь.

## (в) Django нет, гейт+pytest зелёные

Стек не менялся — FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2, Django/DRF
по-прежнему не использованы. Гейт: `OK`. `pytest -q`: `128 passed`. Схема
(`models.py`/миграции) не тронута ни одним файлом.

## Файлы

- `backend/app/modules/ai/service.py` (изменён) — SDK Anthropic → Google
  Gemini, `_AI_MODEL`, вызов клиента, `_extract_text`, докстринги.
- `backend/pyproject.toml` (изменён) — `anthropic>=0.68` → `google-genai>=1.0`.
- `backend/app/modules/admin/service.py` (изменён) — убран
  `_AI_SEARCH_KEY_PREFIX`, мягкая проверка длины, `display_name="Google
  Gemini"`, обновлены докстринги/комментарии.
- `frontend/src/pages/integrations/IntegrationsPage.tsx` (изменён) — текст
  подсказки карточки `ai_search`.
