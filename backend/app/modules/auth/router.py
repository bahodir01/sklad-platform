"""Роутер auth. Архитектура §6: POST /auth/login, /auth/refresh, GET /auth/me.

Router не знает про SQLAlchemy (архитектура §2) — только про DTO и сервис.
"""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.security import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import LoginRequest, TokenResponse, UserRead
from app.modules.auth.service import AuthService, TokenPair
from app.modules.auth.tokens import RefreshTokenStore

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(session, RefreshTokenStore())


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """httpOnly + Secure + SameSite (ТЗ §7, архитектура §9).

    path ограничен /api/v1/auth: cookie не нужна ни одному другому эндпоинту,
    и не отправлять её с каждым запросом — меньше поверхности для утечки.
    """
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def _to_response(pair: TokenPair, response: Response) -> TokenResponse:
    _set_refresh_cookie(response, pair.refresh_token)
    return TokenResponse(access_token=pair.access_token, expires_in=pair.expires_in)


@router.post("/login", response_model=TokenResponse, summary="Вход в систему")
async def login(
    payload: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    pair = await service.login(payload.username, payload.password)
    return _to_response(pair, response)


@router.post("/refresh", response_model=TokenResponse, summary="Обновление access-токена")
async def refresh(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Ротация refresh с детекцией переиспользования (§9).

    Токен берётся ТОЛЬКО из httpOnly-cookie. Принимать его из тела или
    заголовка означало бы, что JS обязан его хранить, — а именно этого
    httpOnly и не допускает.
    """
    token = request.cookies.get(settings.refresh_cookie_name)
    pair = await service.refresh(token)
    return _to_response(pair, response)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Выход (гасит всю цепочку refresh-сессии)",
)
async def logout(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> None:
    token = request.cookies.get(settings.refresh_cookie_name)
    await service.logout(token)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserRead, summary="Текущий пользователь")
async def me(user: User = Depends(get_current_user)) -> User:
    """Доступ — любая аутентифицированная роль. password_hash не входит в
    UserRead: наружу пароль не выходит ни в каком виде."""
    return user
