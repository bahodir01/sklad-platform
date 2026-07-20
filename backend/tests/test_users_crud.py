"""М7 «Пользователи» (ОВ-12 — часть CRUD+email).

Formalises the manual verification run: CRUD + email domain validation,
INV-9 (category IFF admin) at both schema and service layers, self-protection
on PATCH (admin can't deactivate/demote themselves), password reset revoking
refresh sessions, and the admin-only list/search/filter.

Usernames use the `test_` prefix (see conftest.TEST_PREFIX) so the autouse
`clean_db` fixture sweeps them up — seed users (id=3 admin, id=4 teach1) are
never touched.
"""

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.core.security import verify_password
from app.modules.auth.models import User
from app.modules.auth.schemas import UserCreate, UserUpdate
from app.modules.auth.tokens import RefreshTokenStore
from app.modules.users.service import UsersService, normalize_and_validate_email
from app.shared.enums import UserCategory, UserRole
from app.shared.pagination import PageParams
from tests import constants as c
from tests.conftest import TEST_PREFIX


async def _get_admin(session) -> User:
    return await session.scalar(select(User).where(User.id == c.ADMIN_ID))


# ── Создание ────────────────────────────────────────────────────────


async def test_create_worker_with_valid_email_ok(session):
    payload = UserCreate(
        full_name="Тестовый Работник",
        username=f"{TEST_PREFIX}worker_email",
        email="worker_email@npuu.uz",
        role=UserRole.worker,
        category=UserCategory.worker,
        password="pass1234",
    )
    async with SessionLocal() as s:
        user = await UsersService(s).create(payload)
        assert user.id is not None
        assert user.email == "worker_email@npuu.uz"
        assert user.is_active is True
        # password_hash никогда не совпадает с сырым паролем и проверяется Argon2id
        assert verify_password("pass1234", user.password_hash)

    row = await session.get(User, user.id)
    assert row is not None
    assert row.username == f"{TEST_PREFIX}worker_email"


async def test_create_wrong_email_domain_rejected():
    with pytest.raises(ValidationError) as exc_info:
        normalize_and_validate_email("someone@gmail.com")
    assert exc_info.value.code == "email_wrong_domain"


async def test_create_malformed_email_rejected():
    with pytest.raises(ValidationError) as exc_info:
        normalize_and_validate_email("not-an-email")
    assert exc_info.value.code == "email_invalid"


async def test_create_email_none_is_valid():
    assert normalize_and_validate_email(None) is None


async def test_create_wrong_domain_via_service_rejected(session):
    payload = UserCreate(
        full_name="Плохой Домен",
        username=f"{TEST_PREFIX}bad_domain",
        email="bad_domain@gmail.com",
        role=UserRole.worker,
        category=UserCategory.worker,
        password="pass1234",
    )
    async with SessionLocal() as s:
        with pytest.raises(ValidationError) as exc_info:
            await UsersService(s).create(payload)
    assert exc_info.value.code == "email_wrong_domain"

    row = await session.scalar(
        select(User).where(User.username == f"{TEST_PREFIX}bad_domain")
    )
    assert row is None


async def test_create_duplicate_username_rejected(session):
    payload = UserCreate(
        full_name="Первый",
        username=f"{TEST_PREFIX}dup_user",
        email="dup_user@npuu.uz",
        role=UserRole.worker,
        category=UserCategory.worker,
        password="pass1234",
    )
    async with SessionLocal() as s:
        await UsersService(s).create(payload)

    dup_payload = UserCreate(
        full_name="Второй",
        username=f"{TEST_PREFIX}dup_user",  # тот же логин
        email="dup_user2@npuu.uz",
        role=UserRole.worker,
        category=UserCategory.worker,
        password="pass5678",
    )
    async with SessionLocal() as s:
        with pytest.raises(DuplicateError):
            await UsersService(s).create(dup_payload)


async def test_create_duplicate_email_rejected(session):
    payload = UserCreate(
        full_name="Первый",
        username=f"{TEST_PREFIX}dup_email1",
        email="dup_shared@npuu.uz",
        role=UserRole.worker,
        category=UserCategory.worker,
        password="pass1234",
    )
    async with SessionLocal() as s:
        await UsersService(s).create(payload)

    dup_payload = UserCreate(
        full_name="Второй",
        username=f"{TEST_PREFIX}dup_email2",
        email="dup_shared@npuu.uz",  # тот же email
        role=UserRole.teacher,
        category=UserCategory.teacher,
        password="pass5678",
    )
    async with SessionLocal() as s:
        with pytest.raises(DuplicateError):
            await UsersService(s).create(dup_payload)


async def test_create_admin_with_category_rejected_by_schema_inv9():
    """INV-9 проверяется уже на уровне Pydantic-схемы UserCreate — до сервиса."""
    with pytest.raises(PydanticValidationError):
        UserCreate(
            full_name="Плохой Админ",
            username=f"{TEST_PREFIX}bad_admin",
            role=UserRole.admin,
            category=UserCategory.worker,
            password="pass1234",
        )


async def test_create_non_admin_without_category_rejected_by_schema_inv9():
    with pytest.raises(PydanticValidationError):
        UserCreate(
            full_name="Без Категории",
            username=f"{TEST_PREFIX}no_category",
            role=UserRole.worker,
            category=None,
            password="pass1234",
        )


# ── Правка ──────────────────────────────────────────────────────────


async def test_update_full_name_and_category_ok(session, worker_user):
    admin = await _get_admin(session)
    async with SessionLocal() as s:
        actor = await s.get(User, admin.id)
        updated = await UsersService(s).update(
            worker_user,
            UserUpdate(full_name="Переименованный Работник", category=UserCategory.worker),
            actor=actor,
        )
    assert updated.full_name == "Переименованный Работник"
    assert updated.category == UserCategory.worker


async def test_admin_cannot_deactivate_self(session):
    async with SessionLocal() as s:
        actor = await s.get(User, c.ADMIN_ID)
        with pytest.raises(ValidationError) as exc_info:
            await UsersService(s).update(
                c.ADMIN_ID, UserUpdate(is_active=False), actor=actor
            )
    assert exc_info.value.code == "self_deactivation_forbidden"

    row = await session.get(User, c.ADMIN_ID)
    assert row.is_active is True  # не тронуто


async def test_admin_cannot_demote_self(session):
    async with SessionLocal() as s:
        actor = await s.get(User, c.ADMIN_ID)
        with pytest.raises(ValidationError) as exc_info:
            await UsersService(s).update(
                c.ADMIN_ID, UserUpdate(role=UserRole.worker), actor=actor
            )
    assert exc_info.value.code == "self_demotion_forbidden"

    row = await session.get(User, c.ADMIN_ID)
    assert row.role == UserRole.admin


async def test_admin_can_deactivate_other_user(session, worker_user):
    async with SessionLocal() as s:
        actor = await s.get(User, c.ADMIN_ID)
        updated = await UsersService(s).update(
            worker_user, UserUpdate(is_active=False), actor=actor
        )
    assert updated.is_active is False


async def test_update_inv9_role_change_to_admin_clears_category(session, worker_user):
    """UX-удобство сервиса: role -> admin без явной category в теле — она
    обнуляется автоматически, а не требует второго PATCH."""
    async with SessionLocal() as s:
        actor = await s.get(User, c.ADMIN_ID)
        updated = await UsersService(s).update(
            worker_user, UserUpdate(role=UserRole.admin), actor=actor
        )
    assert updated.role == UserRole.admin
    assert updated.category is None


async def test_update_inv9_role_change_to_worker_without_category_rejected(
    session, worker_user
):
    """Обратное: worker/teacher без категории сервер не угадывает — 422."""
    async with SessionLocal() as s:
        actor = await s.get(User, c.ADMIN_ID)
        # Сначала переведём в admin (категория обнулится автоматически).
        await UsersService(s).update(worker_user, UserUpdate(role=UserRole.admin), actor=actor)

    async with SessionLocal() as s:
        actor = await s.get(User, c.ADMIN_ID)
        with pytest.raises(ValidationError) as exc_info:
            await UsersService(s).update(
                worker_user, UserUpdate(role=UserRole.worker), actor=actor
            )
    assert exc_info.value.code == "inv9_violation"


async def test_update_wrong_email_domain_rejected(session, worker_user):
    async with SessionLocal() as s:
        actor = await s.get(User, c.ADMIN_ID)
        with pytest.raises(ValidationError) as exc_info:
            await UsersService(s).update(
                worker_user, UserUpdate(email="wrong@gmail.com"), actor=actor
            )
    assert exc_info.value.code == "email_wrong_domain"


async def test_update_nonexistent_user_raises_not_found(session):
    async with SessionLocal() as s:
        actor = await s.get(User, c.ADMIN_ID)
        with pytest.raises(NotFoundError):
            await UsersService(s).update(999_999, UserUpdate(full_name="X"), actor=actor)


# ── Сброс пароля ────────────────────────────────────────────────────


async def test_reset_password_changes_hash_and_revokes_sessions(session, worker_user):
    async with SessionLocal() as s:
        row = await s.get(User, worker_user)
        old_hash = row.password_hash

    store = RefreshTokenStore()
    await store.register(jti="test-jti-1", family_id="test-fam-1", user_id=worker_user)

    async with SessionLocal() as s:
        revoked = await UsersService(s).reset_password(worker_user, "brandnew99", store=store)
    assert revoked >= 1

    row = await session.get(User, worker_user)
    await session.refresh(row)
    assert row.password_hash != old_hash
    assert verify_password("brandnew99", row.password_hash)
    assert not verify_password("x", row.password_hash)  # старый пароль worker_user фикстуры — "x"

    assert await store.is_family_revoked("test-fam-1") is True


# ── Список / фильтры ───────────────────────────────────────────────


async def test_list_filters_by_role_and_search(session, worker_user):
    async with SessionLocal() as s:
        actor = await s.get(User, c.ADMIN_ID)
        await UsersService(s).update(
            worker_user, UserUpdate(full_name="Уникальное Имя Ксюндра"), actor=actor
        )

    async with SessionLocal() as s:
        items, total = await UsersService(s).list(PageParams(page=1, size=50), role=UserRole.worker)
        assert any(u.id == worker_user for u in items)
        assert all(u.role == UserRole.worker for u in items)

    async with SessionLocal() as s:
        items, total = await UsersService(s).list(PageParams(page=1, size=50), q="Ксюндра")
        assert total == 1
        assert items[0].id == worker_user

    async with SessionLocal() as s:
        items, total = await UsersService(s).list(PageParams(page=1, size=50), is_active=True)
        assert all(u.is_active for u in items)


async def test_get_by_id_and_not_found(session, worker_user):
    async with SessionLocal() as s:
        user = await UsersService(s).get(worker_user)
        assert user.id == worker_user

    async with SessionLocal() as s:
        with pytest.raises(NotFoundError):
            await UsersService(s).get(999_999)
