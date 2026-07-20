"""Бизнес-правила аутентификации. HTTP здесь не знают (архитектура §2)."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenReuseError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.modules.auth.models import User
from app.modules.auth.repository import UserRepository
from app.modules.auth.tokens import ConsumeResult, RefreshTokenStore


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    expires_in: int
    refresh_token: str
    user: User


class AuthService:
    def __init__(self, session: AsyncSession, store: RefreshTokenStore) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._store = store

    # ── Вход ────────────────────────────────────────────────────────

    async def login(self, username: str, password: str) -> TokenPair:
        user = await self._users.get_by_username(username)

        if user is None:
            # Считаем фиктивный хеш, чтобы время ответа не зависело от
            # существования логина: иначе разница таймингов превращает
            # эндпоинт в перечислитель пользователей.
            hash_password(password)
            raise InvalidCredentialsError()

        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise InactiveUserError()

        if password_needs_rehash(user.password_hash):
            # Прозрачный апгрейд параметров Argon2id при живом пароле.
            user.password_hash = hash_password(password)
            await self._session.commit()

        return await self._issue_pair(user, family_id=self._store.new_family_id())

    # ── Ротация ─────────────────────────────────────────────────────

    async def refresh(self, refresh_token: str | None) -> TokenPair:
        if not refresh_token:
            raise InvalidTokenError("Сессия не найдена. Войдите заново")

        payload = decode_token(refresh_token, expected_type="refresh")
        jti = str(payload["jti"])
        family_id = str(payload.get("fam", ""))
        user_id = int(payload["sub"])

        outcome = await self._store.consume(jti=jti, family_id=family_id)
        if outcome == ConsumeResult.REUSED:
            # Детекция переиспользования: семья погашена внутри consume().
            raise TokenReuseError()
        if outcome in (ConsumeResult.REVOKED, ConsumeResult.UNKNOWN):
            raise InvalidTokenError()

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise InvalidTokenError()
        if not user.is_active:
            await self._store.revoke_family(family_id)
            raise InactiveUserError()

        # Семья сохраняется: ротация продолжает ту же сессию.
        return await self._issue_pair(user, family_id=family_id)

    # ── Выход ───────────────────────────────────────────────────────

    async def logout(self, refresh_token: str | None) -> None:
        """Идемпотентен: выход по недействительному токену — не ошибка,
        клиент всё равно уже без сессии."""
        if not refresh_token:
            return
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except InvalidTokenError:
            return
        family_id = str(payload.get("fam", ""))
        if family_id:
            await self._store.logout(family_id=family_id)

    # ── Общее ───────────────────────────────────────────────────────

    async def _issue_pair(self, user: User, *, family_id: str) -> TokenPair:
        access_token, expires_in = create_access_token(user)
        jti = self._store.new_jti()
        refresh_token, _ = create_refresh_token(user.id, family_id=family_id, jti=jti)
        await self._store.register(jti=jti, family_id=family_id, user_id=user.id)
        return TokenPair(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=refresh_token,
            user=user,
        )
