"""JWT, Argon2id, зависимости RBAC. Архитектура §3/§9.

ТЗ §7: JWT access 15 мин + refresh 30 дней (httpOnly cookie), RBAC, Argon2id.
Пароли — только Argon2id, никогда не логируются и не отдаются наружу.
"""

import datetime as dt
import uuid
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.exceptions import (
    ForbiddenError,
    InactiveUserError,
    InvalidTokenError,
)
from app.modules.auth.models import User
from app.shared.enums import UserRole

TokenType = Literal["access", "refresh"]

# ── Argon2id ────────────────────────────────────────────────────────
# type=Type.ID — именно Argon2id, а не Argon2i/Argon2d (ТЗ §7 буквально).
_password_hasher = PasswordHasher(
    time_cost=settings.argon2_time_cost,
    memory_cost=settings.argon2_memory_cost,
    parallelism=settings.argon2_parallelism,
    hash_len=settings.argon2_hash_len,
    salt_len=settings.argon2_salt_len,
    type=Type.ID,
)


def hash_password(password: str) -> str:
    """Argon2id-хеш. Возвращаемая строка кладётся ТОЛЬКО в users.password_hash."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True, если хеш сделан старыми параметрами Argon2 — прозрачный апгрейд."""
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# ── JWT ─────────────────────────────────────────────────────────────


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def create_access_token(user: User) -> tuple[str, int]:
    """Access-токен на 15 минут. Живёт в памяти JS, не в localStorage (§9).

    Возвращает (token, expires_in_seconds).
    """
    expires_delta = dt.timedelta(minutes=settings.access_token_ttl_minutes)
    now = _now()
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role.value,
        "category": user.category.value if user.category else None,
        "type": "access",
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def create_refresh_token(user_id: int, *, family_id: str, jti: str) -> tuple[str, dt.datetime]:
    """Refresh-токен на 30 дней. Только httpOnly+Secure+SameSite cookie.

    family_id — идентификатор цепочки ротаций одной сессии. При детекции
    переиспользования гасится вся семья, а не один токен: укравший старый
    токен иначе просто продолжил бы ротацию своей веткой.
    """
    now = _now()
    expires_at = now + dt.timedelta(days=settings.refresh_token_ttl_days)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "refresh",
        "fam": family_id,
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": jti,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """Разбор и проверка подписи. Тип токена сверяется обязательно:
    без этого refresh-токен (30 дней) прошёл бы как access."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("Срок действия сессии истёк. Войдите заново") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError() from exc

    if payload.get("type") != expected_type:
        raise InvalidTokenError()
    return payload


# ── Текущий пользователь ────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Текущий пользователь по access-токену из заголовка Authorization.

    Пользователь перечитывается из БД на каждый запрос, а не берётся из
    payload: иначе отключённый администратором сотрудник (is_active=false)
    продолжал бы работать до истечения access-токена — до 15 минут.
    """
    if credentials is None or not credentials.credentials:
        raise InvalidTokenError("Требуется авторизация")

    payload = decode_token(credentials.credentials, expected_type="access")
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError() from exc

    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise InvalidTokenError()
    if not user.is_active:
        raise InactiveUserError()

    # Для AuditMiddleware: middleware не имеет доступа к зависимостям.
    request.state.audit_user_id = user.id
    return user


def require_role(*roles: UserRole) -> Any:
    """RBAC-зависимость: Depends(require_role(UserRole.admin)).

    Архитектура §6: ролевой доступ — через зависимости FastAPI. Row-level
    фильтр («сотрудник видит только свои заявки») этим не покрывается и
    остаётся обязанностью сервиса.
    """
    allowed = frozenset(roles)

    async def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise ForbiddenError()
        return user

    return _guard


# Готовые зависимости под §6 архитектуры: чтение справочников — любая роль,
# запись — только admin.
require_admin = require_role(UserRole.admin)
require_any_role = require_role(UserRole.admin, UserRole.teacher, UserRole.worker)
