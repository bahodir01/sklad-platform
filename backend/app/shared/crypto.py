"""Симметричное шифрование секретов интеграций (спека15 §5а).

`integration_settings.secret_encrypted` хранит уже готовый шифротекст —
ключ шифрования живёт в `.env` (`INTEGRATION_SECRET_KEY`), тем же принципом,
что `jwt_secret`/`argon2_*` в `core/config.py`: секрет из окружения, не из
схемы БД и не хардкод (см. `.feature-dev/15a-schema-telegram.md`).

Fernet требует ключ строго 32 «сырых» байта, закодированных в urlsafe-base64.
`INTEGRATION_SECRET_KEY` в `.env` — произвольная строка любой длины (как
`jwt_secret`), поэтому берём SHA-256 от неё и кодируем результат в
urlsafe-base64: детерминированно, одно и то же значение `.env` всегда даёт
один и тот же ключ Fernet, а формат Fernet соблюдён при любой длине исходной
строки (лишь бы settings.integration_secret_key был >= 32 символов, как того
уже требует `Field(min_length=32)` в config.py).

Секрет в открытом виде НИКОГДА не логируется этим модулем и не должен
логироваться вызывающим кодом — см. `modules/admin/service.py`, где текст
ошибок Telegram/ai_search строится без включения самого токена.
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.integration_secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    """Шифрует секрет интеграции. Результат — то, что кладётся в secret_encrypted."""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(cipher: str) -> str:
    """Расшифровывает secret_encrypted обратно в открытый секрет.

    Бросает ValueError, если данные повреждены или INTEGRATION_SECRET_KEY
    сменили после того, как секрет был зашифрован прежним ключом.
    """
    try:
        return _fernet().decrypt(cipher.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Не удалось расшифровать секрет интеграции") from exc
