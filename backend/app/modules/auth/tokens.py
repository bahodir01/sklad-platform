"""Хранилище refresh-сессий: ротация + детекция переиспользования (§9).

ПОЧЕМУ REDIS, А НЕ ТАБЛИЦА. Схема БД заморожена контрактом: 22 таблицы,
таблицы refresh-сессий среди них нет, а ротация с детекцией переиспользования
без состояния на сервере невозможна (нужно помнить, что конкретный jti уже
был обменян). Заводить 23-ю таблицу — значит разойтись с 02-contract.json,
который объявлен единственным источником правды. Redis в системе уже есть
(архитектура §2: broker + cache), TTL совпадает с жизнью токена, и данные
эти по своей природе эфемерны. Вынесено в отчёт этапа как решение,
требующее подтверждения.

Модель:
    refresh:{jti}  -> family_id | "USED"   TTL = 30 дней
    famrev:{fam}   -> "1"                  TTL = 30 дней (отзыв всей семьи)

Отзыв семьи, а не одного токена, — суть детекции: если старый jti предъявлен
повторно, значит либо его украли, либо украли новый. Кто из двух держателей
легитимен, сервер знать не может, поэтому гасится вся цепочка и оба идут на
повторный вход.
"""

import uuid

from redis.asyncio import Redis, from_url

from app.core.config import settings

_USED = "USED"
_TTL_SECONDS = settings.refresh_token_ttl_days * 24 * 60 * 60

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis  # noqa: PLW0603
    if _redis is None:
        _redis = from_url(settings.redis_url_str, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis  # noqa: PLW0603
    if _redis is not None:
        await _redis.aclose()
        _redis = None


class RefreshTokenStore:
    def __init__(self, redis: Redis | None = None) -> None:
        self._r = redis or get_redis()

    @staticmethod
    def new_family_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def new_jti() -> str:
        return uuid.uuid4().hex

    async def register(self, *, jti: str, family_id: str) -> None:
        """Выданный refresh-токен становится действительным ровно один раз."""
        await self._r.set(f"refresh:{jti}", family_id, ex=_TTL_SECONDS)

    async def is_family_revoked(self, family_id: str) -> bool:
        return await self._r.exists(f"famrev:{family_id}") == 1

    async def revoke_family(self, family_id: str) -> None:
        await self._r.set(f"famrev:{family_id}", "1", ex=_TTL_SECONDS)

    async def consume(self, *, jti: str, family_id: str) -> "ConsumeResult":
        """Атомарно погасить jti при ротации.

        GETSET, а не GET + SET: два параллельных refresh с одним токеном
        (двойной клик, гонка вкладок) при неатомарной проверке оба прочитали
        бы «действителен» и оба получили бы новую пару — детекция кражи
        превратилась бы в фикцию. GETSET гарантирует, что ровно один вызов
        увидит прежнее значение.
        """
        if await self.is_family_revoked(family_id):
            return ConsumeResult.REVOKED

        previous = await self._r.getset(f"refresh:{jti}", _USED)
        if previous is None:
            # Токена нет: истёк, вышли через logout или подделан.
            return ConsumeResult.UNKNOWN
        if previous == _USED:
            # Переиспользование: этот jti уже обменивали. Гасим всю семью.
            await self.revoke_family(family_id)
            return ConsumeResult.REUSED
        if previous != family_id:
            # jti есть, но семья не та, что в подписанном токене — попытка склейки.
            await self.revoke_family(family_id)
            return ConsumeResult.REUSED
        await self._r.expire(f"refresh:{jti}", _TTL_SECONDS)
        return ConsumeResult.OK

    async def logout(self, *, family_id: str) -> None:
        """Явный выход гасит всю семью: сессия закончилась целиком."""
        await self.revoke_family(family_id)


class ConsumeResult:
    OK = "ok"
    REUSED = "reused"
    REVOKED = "revoked"
    UNKNOWN = "unknown"
