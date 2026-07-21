"""Сервис М7 «Интеграции» (спека15 §5а): проверка и сохранение внешних ключей.

  telegram:  проверяется вызовом Telegram Bot API `getMe` ПЕРЕД сохранением —
             невалидный токен НЕ сохраняется, ошибка Telegram видна пользователю
             как есть (422). При успехе display_name = username бота из ответа.
  ai_search: полноценный вызов Anthropic на этом этапе НЕ обязателен (по прямому
             указанию спеки) — лёгкая проверка формата ключа (непустой,
             `sk-ant-...`). Реальный вызов делает следующий агент при первом
             использовании поиска (shared/ai_search.py, спека15 §3a).

Транзакция открывается и коммитится здесь (архитектура §2 — «сервис коммитит,
когда бизнес-инвариант целостен»), роутер только вызывает сервис.

Секрет НИКОГДА не логируется. Тексты ошибок ниже собраны из description/
класса исключения httpx — сам токен/ключ в них не попадает ни в одной ветке.
"""

from typing import Final

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.admin.models import IntegrationSetting
from app.modules.admin.schemas import IntegrationRead
from app.shared.crypto import decrypt_secret, encrypt_secret

ALLOWED_KINDS: Final[frozenset[str]] = frozenset({"telegram", "ai_search"})
_TELEGRAM_API_TIMEOUT_SECONDS: Final[float] = 10.0
# Требование спеки §5а: ключ Anthropic — облегчённая проверка формата, без
# реального вызова. "sk-ant-" — задокументированный префикс ключей Anthropic;
# 10 символов — префикс (7) + хотя бы несколько символов самого ключа, чтобы
# отсечь пустой/обрезанный ввод, не будучи излишне строгим к длине.
_AI_SEARCH_KEY_PREFIX: Final[str] = "sk-ant-"
_AI_SEARCH_KEY_MIN_LEN: Final[int] = 10


def mask_secret(kind: str, plain: str) -> str:
    """`123456:AAE••••1234` (telegram, формат `<bot_id>:<token>`) /
    `sk-ant-••••ab12` (ai_search и любой другой kind без двоеточия).

    Секрет никогда не возвращается целиком: видна только служебная часть
    (bot_id/префикс) и последние 4 символа — достаточно, чтобы админ отличил
    один сохранённый ключ от другого, не восстанавливая исходное значение.
    """
    if not plain:
        return ""
    if kind == "telegram" and ":" in plain:
        bot_id, _, token = plain.partition(":")
        head = token[:3]
        tail = token[-4:] if len(token) >= 4 else token
        return f"{bot_id}:{head}••••{tail}"
    head_len = min(7, max(len(plain) - 4, 0))
    head = plain[:head_len]
    tail = plain[-4:] if len(plain) >= 4 else plain
    return f"{head}••••{tail}"


class IntegrationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get(self, kind: str) -> IntegrationSetting:
        if kind not in ALLOWED_KINDS:
            raise NotFoundError("Интеграция", kind)
        setting = await self._session.scalar(
            select(IntegrationSetting).where(IntegrationSetting.kind == kind)
        )
        if setting is None:
            # Обе строки сеет миграция 0004 — сюда дойти в норме не должны,
            # но не полагаемся на это молча (напр. БД без сида в тестах).
            raise NotFoundError("Интеграция", kind)
        return setting

    @staticmethod
    def _to_read(setting: IntegrationSetting) -> IntegrationRead:
        masked = None
        if setting.secret_encrypted:
            plain = decrypt_secret(setting.secret_encrypted)
            masked = mask_secret(setting.kind, plain)
        return IntegrationRead(
            kind=setting.kind,
            display_name=setting.display_name,
            is_enabled=setting.is_enabled,
            updated_at=setting.updated_at,
            masked_secret=masked,
        )

    async def list_all(self) -> list[IntegrationRead]:
        rows = (
            await self._session.scalars(select(IntegrationSetting).order_by(IntegrationSetting.kind))
        ).all()
        return [self._to_read(row) for row in rows]

    async def update_secret(self, kind: str, secret: str, *, admin_id: int) -> IntegrationRead:
        setting = await self._get(kind)
        secret = secret.strip()
        if not secret:
            raise ValidationError("Секрет не может быть пустым")

        if kind == "telegram":
            display_name = await _verify_telegram_token(secret)
        else:  # ai_search — единственный оставшийся kind из ALLOWED_KINDS
            display_name = _verify_ai_search_key(secret)

        setting.secret_encrypted = encrypt_secret(secret)
        setting.display_name = display_name
        setting.is_enabled = True
        setting.updated_by = admin_id
        await self._commit()
        await self._session.refresh(setting)
        return self._to_read(setting)

    async def get_active_secret(self, kind: str) -> str | None:
        """Расшифрованный секрет ВКЛЮЧЁННОЙ интеграции — для внутренних
        сервисных вызовов (напр. modules/ai/service.py, спека15 §3a), НЕ
        HTTP-эндпоинт и нигде не сериализуется в ответ API.

        ``None`` при любой причине недоступности (kind не из ALLOWED_KINDS,
        строки нет, is_enabled=false, секрет пуст, расшифровка не удалась) —
        вызывающий код трактует это как «функция сейчас не работает», не как
        ошибку (спека15 §3a: «is_enabled=false → сразу [] без ошибки»).
        """
        if kind not in ALLOWED_KINDS:
            return None
        setting = await self._session.scalar(
            select(IntegrationSetting).where(IntegrationSetting.kind == kind)
        )
        if setting is None or not setting.is_enabled or not setting.secret_encrypted:
            return None
        try:
            return decrypt_secret(setting.secret_encrypted)
        except ValueError:
            return None

    async def disable(self, kind: str, *, admin_id: int) -> IntegrationRead:
        """Гасит интеграцию. Секрет НЕ стирается — повторный PUT включит заново
        без пересохранения ключа (спека15 §5а: «для telegram — останавливает
        polling; для ai_search — поиск товара просто пропускает шаг 2»)."""
        setting = await self._get(kind)
        setting.is_enabled = False
        setting.updated_by = admin_id
        await self._commit()
        await self._session.refresh(setting)
        return self._to_read(setting)

    async def _commit(self) -> None:
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            raise


async def _verify_telegram_token(token: str) -> str:
    """Telegram Bot API `getMe`. Возвращает username бота или бросает
    ValidationError (→ 422) с текстом ошибки Telegram — токен при этом
    НЕ сохраняется (вызывается ДО setting.secret_encrypted = ...)."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=_TELEGRAM_API_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        # Текст исключения httpx не содержит токен в safe-варианте (только
        # класс ошибки: TimeoutException/ConnectError и т.п.) — секрет не утечёт в лог/ответ.
        raise ValidationError(
            f"Telegram API недоступен ({exc.__class__.__name__}). "
            f"Проверьте соединение и повторите"
        ) from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise ValidationError("Telegram API вернул нераспознаваемый ответ") from exc

    if not body.get("ok"):
        description = body.get("description", "неизвестная ошибка")
        raise ValidationError(f"Telegram отклонил токен: {description}")

    result = body.get("result") or {}
    username = result.get("username")
    if not username:
        raise ValidationError("Telegram не вернул username бота")
    return str(username)


def _verify_ai_search_key(secret: str) -> str:
    """Облегчённая проверка формата ключа Anthropic (спека15 §5а) — без
    реального тестового вызова API на этом этапе."""
    if not secret.startswith(_AI_SEARCH_KEY_PREFIX) or len(secret) < _AI_SEARCH_KEY_MIN_LEN:
        raise ValidationError(
            "Похоже, это не ключ Anthropic API — ожидается формат sk-ant-..."
        )
    return "Anthropic API"
