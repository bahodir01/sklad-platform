"""Роутер М7 «Пользователи» (ОВ-12 — часть CRUD+email).

GET,POST /users · GET,PATCH /users/{id} · POST /users/{id}/reset-password
ВСЕ операции — только admin (require_admin): пользователей заводит
завсклад/админ через админ-панель (решение заказчика, ОВ-12). Сотрудники
свои учётки не видят и не правят — им это не нужно (они не логинятся по
целевой модели ОВ-12, а сейчас пользуются только /auth/me).

DELETE отсутствует намеренно (стиль SV-8): отключение — PATCH is_active=false.
Router не знает про SQLAlchemy (архитектура §2) — только DTO и сервис.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import require_admin
from app.modules.auth.models import User
from app.modules.auth.tokens import RefreshTokenStore
from app.modules.users.schemas import (
    PasswordResetIn,
    UserCreate,
    UserList,
    UserRead,
    UserUpdate,
)
from app.modules.users.service import UsersService
from app.shared.enums import UserRole
from app.shared.pagination import Page, PageParamsDep

router = APIRouter(prefix="/users", tags=["users"])

UserId = Annotated[int, Path(ge=1, description="Идентификатор пользователя")]


def get_users_service(session: AsyncSession = Depends(get_session)) -> UsersService:
    return UsersService(session)


@router.get(
    "",
    response_model=Page[UserList],
    summary="Список пользователей (admin)",
)
async def list_users(
    params: PageParamsDep,
    role: Annotated[UserRole | None, Query(description="Фильтр по роли")] = None,
    is_active: Annotated[bool | None, Query(description="Фильтр по активности")] = None,
    q: Annotated[
        str | None,
        Query(max_length=255, description="Поиск по ФИО, логину или email (ilike)"),
    ] = None,
    _admin: User = Depends(require_admin),
    service: UsersService = Depends(get_users_service),
) -> Page[UserList]:
    items, total = await service.list(params, role=role, is_active=is_active, q=q)
    return Page.build([UserList.model_validate(u) for u in items], total, params)


@router.get(
    "/{id}",
    response_model=UserRead,
    summary="Пользователь (admin)",
)
async def get_user(
    id: UserId,
    _admin: User = Depends(require_admin),
    service: UsersService = Depends(get_users_service),
) -> User:
    return await service.get(id)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать пользователя (admin)",
)
async def create_user(
    payload: UserCreate,
    _admin: User = Depends(require_admin),
    service: UsersService = Depends(get_users_service),
) -> User:
    """INV-9 (admin ⟺ без категории) — схема+CHECK; email — формат и домен
    @npuu.uz (settings.email_domain); пароль ≥ 8 символов, хеш Argon2id."""
    return await service.create(payload)


@router.patch(
    "/{id}",
    response_model=UserRead,
    summary="Изменить/деактивировать пользователя (admin)",
)
async def update_user(
    id: UserId,
    payload: UserUpdate,
    admin: User = Depends(require_admin),
    service: UsersService = Depends(get_users_service),
) -> User:
    """username не меняется (учётная константа). Деактивация — is_active=false
    здесь же (DELETE нет, стиль SV-8). Сам себя админ не деактивирует и не
    разжалует — 422."""
    return await service.update(id, payload, actor=admin)


@router.post(
    "/{id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Сбросить пароль пользователя (admin)",
)
async def reset_password(
    id: UserId,
    payload: PasswordResetIn,
    _admin: User = Depends(require_admin),
    service: UsersService = Depends(get_users_service),
) -> None:
    """Новый пароль задаёт админ (мин. 8 символов). Все refresh-сессии
    пользователя гасятся в Redis — старые сессии не переживают сброс."""
    await service.reset_password(id, payload.password, store=RefreshTokenStore())
