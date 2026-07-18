"""Доменные ошибки и их маппинг в HTTP.

Архитектура §6 «Правила уровня API»: доменные исключения централизованно
маппятся в 422 с телом {code, message, details}, где message — готовый русский
текст для тостера (формат из §4.2 ТЗ).

Ошибки аутентификации/авторизации из этого правила исключены осознанно:
401/403 — не доменные ошибки, а протокольные, и клиент обязан различать их,
чтобы понимать, дёргать ли refresh (см. §9 ТЗ).
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Базовая доменная ошибка → HTTP 422 {code, message, details}."""

    code: str = "domain_error"
    # 422 числом, а не константой Starlette: HTTP_422_UNPROCESSABLE_ENTITY
    # объявлена deprecated в пользу ..._CONTENT, а код ответа архитектура §6
    # фиксирует буквально — он не должен зависеть от переименований в библиотеке.
    http_status: int = 422

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details: dict[str, Any] = details or {}

    def to_body(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


# ── Общие доменные ошибки этапа 1 ───────────────────────────────────


class NotFoundError(DomainError):
    """Сущности нет. 404, а не 422: это не нарушение бизнес-правила."""

    code = "not_found"
    http_status = status.HTTP_404_NOT_FOUND

    def __init__(self, entity_title: str, entity_id: Any) -> None:
        super().__init__(
            f"{entity_title} с идентификатором {entity_id} не найден(а)",
            details={"entity_id": entity_id},
        )


class ConflictError(DomainError):
    """Конкурентный конфликт состояния (SV-5 и подобные)."""

    code = "conflict"
    http_status = status.HTTP_409_CONFLICT


class DuplicateError(DomainError):
    """Нарушение UNIQUE справочника — понятным русским текстом."""

    code = "duplicate"

    def __init__(self, field_title: str, value: Any) -> None:
        super().__init__(
            f'{field_title} "{value}" уже существует',
            details={"value": value},
        )


class ValidationError(DomainError):
    """Нарушение бизнес-правила, не покрытое схемой Pydantic."""

    code = "validation_error"


class ReferencedError(DomainError):
    """SV-8: справочник используется — физическое удаление невозможно."""

    code = "referenced"

    def __init__(self, entity_title: str) -> None:
        super().__init__(
            f"{entity_title} используется в документах и не может быть удалён(а). "
            f"Переведите запись в архив.",
        )


class InsufficientStock(DomainError):
    """SV-3: на складе-источнике не хватает товара для списания.

    Поднимается ЛЕДЖЕРОМ (stock/ledger.py) ДО вставки движения, когда
    balance + qty < 0. Это единственный правильный момент проверки: ловить
    CHECK (qty >= 0) постфактум значит полагаться на IntegrityError вместо
    доменного правила и отдавать пользователю 500 вместо внятного текста.

    Ледгер знает только id (имён товаров он не резолвит — это не его слой).
    Вызывающий сервис, у которого имя под рукой, может перевыбросить эту же
    ошибку с product_name для читаемого сообщения.
    """

    code = "insufficient_stock"

    def __init__(
        self,
        *,
        product_id: int,
        warehouse_id: int,
        available: Any,
        requested: Any,
        product_name: str | None = None,
    ) -> None:
        subject = f'«{product_name}»' if product_name else f"(id={product_id})"
        super().__init__(
            f"Недостаточно товара {subject} на складе (id={warehouse_id}): "
            f"доступно {available}, списывается {requested}",
            details={
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "available": str(available),
                "requested": str(requested),
            },
        )
        self.product_id = product_id
        self.warehouse_id = warehouse_id
        self.available = available
        self.requested = requested
        self.product_name = product_name


class InsufficientFunds(DomainError):
    """SV-4/§5.4, ОВ-2 (жёсткая блокировка): в кассе не хватает денег на расход.

    Поднимается СЕРВИСОМ кассы (cash/service.py) ДО вставки money_expense, под
    `SELECT balance ... FOR UPDATE`, когда balance < amount. Это единственный
    правильный момент проверки: ловить CHECK (balance >= 0) постфактум значит
    полагаться на IntegrityError вместо доменного правила и отдавать пользователю
    500 вместо внятного текста. ОВ-2 закрыт заказчиком жёсткой блокировкой —
    режима-предупреждения (флага CASH_OVERDRAFT_MODE) в системе нет.
    """

    code = "insufficient_funds"

    def __init__(self, *, available: Any, requested: Any, desk: str | None = None) -> None:
        where = f" в кассе «{desk}»" if desk else ""
        super().__init__(
            f"Недостаточно средств{where}: доступно {available}, "
            f"списывается {requested}",
            details={
                "available": str(available),
                "requested": str(requested),
                "desk": desk,
            },
        )
        self.available = available
        self.requested = requested
        self.desk = desk


# ── Ошибки аутентификации / авторизации ─────────────────────────────


class AuthError(DomainError):
    code = "unauthorized"
    http_status = status.HTTP_401_UNAUTHORIZED


class InvalidCredentialsError(AuthError):
    code = "invalid_credentials"

    def __init__(self) -> None:
        # Осознанно не уточняем, что именно неверно: логин или пароль —
        # иначе эндпоинт становится оракулом существования пользователей.
        super().__init__("Неверный логин или пароль")


class InactiveUserError(AuthError):
    code = "user_inactive"

    def __init__(self) -> None:
        super().__init__("Учётная запись отключена. Обратитесь к администратору")


class InvalidTokenError(AuthError):
    code = "invalid_token"

    def __init__(self, message: str = "Сессия недействительна. Войдите заново") -> None:
        super().__init__(message)


class TokenReuseError(AuthError):
    """Детекция переиспользования refresh-токена (архитектура §9)."""

    code = "token_reuse_detected"

    def __init__(self) -> None:
        super().__init__(
            "Обнаружено повторное использование сессии. Все сессии завершены, войдите заново"
        )


class ForbiddenError(DomainError):
    code = "forbidden"
    http_status = status.HTTP_403_FORBIDDEN

    def __init__(self, message: str = "Недостаточно прав для выполнения операции") -> None:
        super().__init__(message)


# ── Регистрация обработчиков ────────────────────────────────────────


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, AuthError) else None
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_body(),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Приводим ошибки Pydantic к тому же телу {code, message, details},
        # чтобы фронт имел ровно один формат ошибки на все случаи.
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "Проверьте правильность заполнения полей",
                "details": {"errors": _safe_errors(exc)},
            },
        )


def _safe_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Ошибки валидации без значений полей.

    ТЗ §7: пароль не логируется и не отдаётся наружу ни в одной схеме.
    Pydantic кладёт присланное значение в error['input'] — при ошибке в
    теле /auth/login это вернуло бы пароль клиенту в эхо. Вырезаем input целиком.
    """
    result: list[dict[str, Any]] = []
    for err in exc.errors():
        result.append(
            {
                "loc": [str(part) for part in err.get("loc", [])],
                "type": err.get("type", ""),
                "msg": err.get("msg", ""),
            }
        )
    return result
