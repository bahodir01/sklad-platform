"""М7. Аудит: модель audit_log + middleware, пишущий каждое изменяющее действие.

Архитектура §9: «Middleware пишет в audit_log каждое изменяющее действие:
user_id, action, entity, entity_id, payload_diff, ip, timestamp. Таблица
append-only, доступ на чтение — только admin».

Модель AuditLog живёт здесь, а не в modules/*/models.py, потому что в §3
архитектуры модуля «М7» нет: за аудит отвечает core/audit.py. Держать модель
рядом с её единственным писателем — так же вертикально, как и в модулях.
"""

import datetime as dt
import ipaddress
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.database import Base, SessionLocal

logger = logging.getLogger(__name__)

# ── Модель ──────────────────────────────────────────────────────────


class AuditLog(Base):
    """Append-only. Пишет middleware, читает только admin."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity", "entity_id"),
        Index("ix_audit_log_action", "action"),
        Index("ix_audit_log_created_at", text("created_at DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload_diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ── Middleware ──────────────────────────────────────────────────────

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# ТЗ §7: пароль никогда не логируется. Ключи режутся рекурсивно, по вхождению
# подстроки, чтобы password / new_password / password_confirm ловились разом.
SECRET_KEY_MARKERS = ("password", "token", "secret")
REDACTED = "***"

MAX_PAYLOAD_BYTES = 64 * 1024


class AuditMiddleware(BaseHTTPMiddleware):
    """Пишет в audit_log успешные изменяющие запросы аутентифицированных пользователей.

    Две сознательные границы:

    1. Анонимные запросы не логируются — `audit_log.user_id` NOT NULL, писать
       некого. Неудачные попытки входа — задача журнала приложения, а не
       таблицы аудита действий над сущностями.
    2. Логируются только ответы < 400. Отклонённый запрос ничего не изменил,
       и запись о нём засорила бы историю изменений документа.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method not in MUTATING_METHODS:
            return await call_next(request)

        body = await request.body()

        # Тело уже вычитано из потока — подкладываем его обратно, иначе
        # обработчик получит пустой body и упадёт на валидации.
        async def _replay_receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = _replay_receive  # noqa: SLF001

        response = await call_next(request)

        if response.status_code >= 400:
            return response

        user_id: int | None = getattr(request.state, "audit_user_id", None)
        if user_id is None:
            return response

        try:
            await self._write(request, response, user_id, body)
        except Exception:
            # Аудит не должен ронять успешно выполненную операцию: товар уже
            # выдан / деньги списаны, откатывать нечего. Но и молча терять
            # запись аудита нельзя — это дыра в §9 ТЗ, поэтому ERROR с
            # трассировкой: потерю аудита обязан увидеть мониторинг.
            logger.exception(
                "Не удалось записать audit_log: user_id=%s method=%s path=%s",
                user_id,
                request.method,
                request.url.path,
            )

        return response

    async def _write(
        self, request: Request, response: Response, user_id: int, body: bytes
    ) -> None:
        entity, entity_id = _resolve_entity(request)
        async with SessionLocal() as session:
            session.add(
                AuditLog(
                    user_id=user_id,
                    action=_resolve_action(request),
                    entity=entity,
                    entity_id=getattr(request.state, "audit_entity_id", None) or entity_id,
                    payload_diff=_safe_payload(body),
                    ip=_client_ip(request),
                )
            )
            await session.commit()


def _resolve_action(request: Request) -> str:
    """HTTP-метод → доменное действие. Переопределяется сервисом через
    request.state.audit_action (например, 'issue', 'confirm')."""
    override: str | None = getattr(request.state, "audit_action", None)
    if override:
        return override[:50]
    return {
        "POST": "create",
        "PATCH": "update",
        "PUT": "update",
        "DELETE": "delete",
    }.get(request.method, request.method.lower())


def _resolve_entity(request: Request) -> tuple[str, int | None]:
    """Сущность и её id из маршрута: /api/v1/products/12 → ('products', 12)."""
    path_params: dict[str, Any] = request.scope.get("path_params") or {}
    raw_id = path_params.get("id")
    entity_id: int | None = None
    if raw_id is not None:
        try:
            entity_id = int(raw_id)
        except (TypeError, ValueError):
            entity_id = None

    parts = [p for p in request.url.path.split("/") if p and p not in {"api", "v1"}]
    entity = parts[0] if parts else "unknown"
    return entity[:100], entity_id


def _client_ip(request: Request) -> str | None:
    """inet-колонка: X-Forwarded-For доверяем только первому адресу.

    Nginx (архитектура §2) ставит его сам; если заголовка нет — берём peer.
    Мусор в заголовке уронил бы INSERT на типе inet, поэтому при неудаче
    отдаём None: аудит без IP лучше, чем потерянная запись аудита.
    """
    forwarded = request.headers.get("x-forwarded-for")
    candidate = forwarded.split(",")[0].strip() if forwarded else None
    if not candidate and request.client:
        candidate = request.client.host
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _safe_payload(body: bytes) -> dict[str, Any] | None:
    """Тело запроса как payload_diff, с вырезанными секретами."""
    if not body or len(body) > MAX_PAYLOAD_BYTES:
        return None
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    redacted = _redact(parsed)
    if not isinstance(redacted, dict):
        return {"value": redacted}
    return redacted


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (REDACTED if _is_secret(k) else _redact(v)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _is_secret(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SECRET_KEY_MARKERS)
