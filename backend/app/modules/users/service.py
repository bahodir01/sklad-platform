"""Бизнес-правила М7 «Пользователи» (ОВ-12 — часть CRUD+email).

Правила модуля:
  * доступ — только admin (обеспечивает роутер, require_admin);
  * физического удаления НЕТ (стиль SV-8) — только is_active=false PATCH-ем;
  * INV-9 держится на ИТОГОВОМ состоянии при PATCH (частичное тело легально);
  * админ не может деактивировать или разжаловать САМ СЕБЯ — иначе одним
    запросом из системы выпиливается последний администратор;
  * email, если задан, — формат + домен settings.email_domain (дефолт
    npuu.uz), хранится в нижнем регистре, уникален среди непустых;
  * пароль хешируется существующим Argon2id (core/security.hash_password);
  * сброс пароля гасит все refresh-сессии пользователя в Redis
    (RefreshTokenStore.revoke_all_for_user) — украденный/старый refresh
    не должен переживать смену пароля.
"""

import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DomainError, DuplicateError, NotFoundError, ValidationError
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.auth.schemas import UserCreate, UserUpdate, _validate_inv9
from app.modules.auth.tokens import RefreshTokenStore
from app.modules.users.repository import UsersCrudRepository
from app.shared.enums import UserCategory, UserRole
from app.shared.pagination import PageParams

# Формат до проверки домена: локальная часть без пробелов/@, один @, домен
# с точкой. Полный RFC 5322 не воспроизводим сознательно — всё равно дальше
# требуется строгое равенство домена настройке.
_EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")


def normalize_and_validate_email(email: str | None) -> str | None:
    """Нижний регистр + формат + домен. None (почта не задана) — валиден.

    Русские тексты — прямо отсюда: это доменное правило, а не формат схемы.
    """
    if email is None:
        return None
    normalized = email.strip().lower()
    if not normalized:
        return None
    if not _EMAIL_RE.match(normalized):
        raise ValidationError(
            f'Некорректный формат email: "{email}"', code="email_invalid"
        )
    domain = normalized.rsplit("@", 1)[1]
    if domain != settings.email_domain.lower():
        raise ValidationError(
            f"Разрешена только корпоративная почта @{settings.email_domain}, "
            f'получено "{email}"',
            code="email_wrong_domain",
        )
    return normalized


class UsersService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = UsersCrudRepository(session)

    # ── Чтение ──────────────────────────────────────────────────────

    async def list(
        self,
        params: PageParams,
        *,
        role: UserRole | None = None,
        is_active: bool | None = None,
        q: str | None = None,
    ) -> tuple[list[User], int]:
        filters: list = []
        if role is not None:
            filters.append(User.role == role)
        if is_active is not None:
            filters.append(User.is_active == is_active)
        if q:
            pattern = f"%{q.strip()}%"
            filters.append(
                User.full_name.ilike(pattern)
                | User.username.ilike(pattern)
                | User.email.ilike(pattern)
            )
        return await self._repo.list(params, filters=filters or None)

    async def get(self, user_id: int) -> User:
        user = await self._repo.get(user_id)
        if user is None:
            raise NotFoundError("Пользователь", user_id)
        return user

    # ── Создание ────────────────────────────────────────────────────

    async def create(self, payload: UserCreate) -> User:
        """INV-9 уже проверен схемой UserCreate (model_validator)."""
        email = normalize_and_validate_email(payload.email)

        # Предварительные проверки — для внятного текста; гарантию дают
        # UNIQUE-constraint/индекс, их нарушение ловит _commit (гонки).
        if await self._repo.username_taken(payload.username):
            raise DuplicateError("Логин", payload.username)
        if email is not None and await self._repo.email_taken(email):
            raise DuplicateError("Email", email)

        user = User(
            full_name=payload.full_name,
            username=payload.username,
            email=email,
            password_hash=hash_password(payload.password),  # Argon2id
            role=payload.role,
            category=payload.category,
            is_active=True,
        )
        self._repo.add(user)
        await self._commit()
        await self._session.refresh(user)
        return user

    # ── Правка ──────────────────────────────────────────────────────

    async def update(self, user_id: int, payload: UserUpdate, *, actor: User) -> User:
        """PATCH full_name/email/role/category/is_active.

        username не меняется (учётная константа — его в UserUpdate нет).
        Правила самозащиты: текущий админ не деактивирует и не разжалует
        сам себя — иначе последний администратор выпиливается одним PATCH.
        """
        user = await self.get(user_id)
        # exclude_unset: «не прислали» и «прислали null» — разные вещи
        # (email=null законно стирает почту, отсутствие email её не трогает).
        data = payload.model_dump(exclude_unset=True)

        if user.id == actor.id:
            if data.get("is_active") is False:
                raise ValidationError(
                    "Нельзя деактивировать собственную учётную запись: "
                    "система может остаться без администратора. "
                    "Попросите другого администратора",
                    code="self_deactivation_forbidden",
                )
            if "role" in data and data["role"] != UserRole.admin:
                raise ValidationError(
                    "Нельзя понизить роль собственной учётной записи: "
                    "система может остаться без администратора. "
                    "Попросите другого администратора",
                    code="self_demotion_forbidden",
                )

        # INV-9 — на итоговом состоянии (текущее + патч), тело PATCH частично.
        effective_role = data.get("role", user.role)
        effective_category = data["category"] if "category" in data else user.category
        # Удобство UX: роль стала admin, категорию явно не прислали — обнуляем
        # сами (клиент по словарю и так скрывает поле). Обратное (роль стала
        # teacher/worker без категории) — ошибка: кассу за клиента не угадываем.
        if (
            effective_role is UserRole.admin
            and "category" not in data
            and user.category is not None
        ):
            data["category"] = None
            effective_category = None
        try:
            _validate_inv9(effective_role, effective_category)
        except ValueError as exc:
            raise ValidationError(str(exc), code="inv9_violation") from exc

        if "email" in data:
            email = normalize_and_validate_email(data["email"])
            if email is not None and await self._repo.email_taken(email, exclude_id=user.id):
                raise DuplicateError("Email", email)
            data["email"] = email

        for field, value in data.items():
            setattr(user, field, value)

        await self._commit()
        await self._session.refresh(user)
        return user

    # ── Сброс пароля ────────────────────────────────────────────────

    async def reset_password(
        self, user_id: int, password: str, *, store: RefreshTokenStore
    ) -> int:
        """Админ задаёт новый пароль. Возвращает число погашенных refresh-семей.

        После смены хеша гасятся ВСЕ refresh-сессии пользователя (Redis,
        userfam-индекс): живой refresh со старым паролем — это ровно та
        сессия, от которой сброс и защищает. Access-токен доживает свои
        ≤15 минут — короче любого разумного окна реагирования.
        """
        user = await self.get(user_id)
        user.password_hash = hash_password(password)  # Argon2id
        await self._commit()
        return await store.revoke_all_for_user(user.id)

    # DELETE отсутствует намеренно (стиль SV-8): пользователи не удаляются
    # физически — на них ссылаются документы (author_id/employee_id, RESTRICT).
    # Отключение — PATCH is_active=false.

    # ── Общее ───────────────────────────────────────────────────────

    async def _commit(self) -> None:
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise _translate_integrity_error(exc) from exc


def _translate_integrity_error(exc: IntegrityError) -> DomainError:
    """Отказ constraint-а → русский текст (конкурентные гонки мимо предпроверок)."""
    text = str(getattr(exc, "orig", exc))
    if "uq_users_email_not_null" in text:
        return DuplicateError("Email", "")
    if "users_username_key" in text or ("unique" in text.lower() and "username" in text):
        return DuplicateError("Логин", "")
    if "ck_users_category_iff_admin" in text:
        return ValidationError(
            "Категория пользователя противоречит роли (INV-9): у администратора "
            "категории нет, у учителя и работника — обязательна",
            code="inv9_violation",
        )
    if "unique" in text.lower() or "duplicate key" in text.lower():
        return DuplicateError("Значение", "")
    return ValidationError("Пользователь: операция отклонена базой данных")
