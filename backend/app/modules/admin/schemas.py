"""Pydantic v2-схемы М7 «Интеграции» (спека15 §5а).

`integration_settings` — по одной строке на `kind` (`telegram` | `ai_search`,
модель — `modules/admin/models.py`). Секрет в открытом виде НИКОГДА не
возвращается ни в одной схеме — только `masked_secret`, вычисленный
`modules/admin/service.py` (расшифровка + маска), не `from_attributes`:
секрет в БД лежит зашифрованным, схема сама его не читает и не расшифровывает.

Отдельной схемы для `GET /admin/alerts` (`AdminAlert`/`AdminAlertsResponse`)
здесь нет — она уже объявлена прямо в `admin/router.py` (М7 «Уведомления»,
фича 13); эти классы её не трогают.
"""

import datetime as dt

from pydantic import BaseModel, Field


class IntegrationRead(BaseModel):
    """`GET /admin/integrations` — секрет отдан только маской.

    `__contract_table__ = None`: в 02-contract.json у `integration_settings`
    ВСЕ атрибуты помечены `api.create=false`/`api.update=false` (обновление —
    это сервисное действие «проверить и зашифровать», а не прямая запись
    столбца), а `masked_secret` вообще не столбец — это вычисляемое поле
    (расшифровка + маска в `admin/service.py`). Строгая построчная сверка
    get_single-флагов (которая потребовала бы `id`/`updated_by` в этой схеме)
    здесь бессмысленна по той же причине, что и `MoneyExpenseSubmission` в
    `cash/schemas.py`, — это осознанный конверт, а не проекция таблицы.
    """

    __contract_table__ = None

    kind: str
    display_name: str | None = None
    is_enabled: bool
    updated_at: dt.datetime
    masked_secret: str | None = Field(
        default=None,
        description="Маска секрета (напр. 123456:AAE••••1234); None — секрет ещё не задан",
    )


class IntegrationUpdate(BaseModel):
    """`PUT /admin/integrations/{kind}` — новый секрет (bot-токен / API-ключ).

    `__contract_table__ = None` (см. `IntegrationRead` выше): `secret` — это
    ВХОДНОЙ открытый текст, который сервис проверяет (Telegram `getMe` / формат
    ключа) и лишь потом шифрует в `secret_encrypted`; прямого столбца `secret`
    не существует, а `secret_encrypted.api.update` в контракте — `false`.
    """

    __contract_table__ = None

    secret: str = Field(min_length=1, max_length=4096)
