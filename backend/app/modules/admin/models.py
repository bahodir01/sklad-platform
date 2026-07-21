"""М7: integration_settings — единое место внешних ключей интеграций.

Спека15 §5а «Экран Интеграции»: ОДНА строка на тип интеграции (kind —
telegram | ai_search), не отдельные таблицы под каждый тип. kind — обычный
varchar(32), не enum: набор типов интеграций может расшириться (новый tip —
это INSERT новой строки, как миграция 0004 сеет telegram/ai_search, а не
ALTER TYPE ... ADD VALUE).

Модель живёт в modules/admin — том же модуле, что и роутер алертов
(modules/admin/router.py, фича 13), так как экран «Интеграции» — часть
той же зоны админ-панели «Администрирование».

Схема НЕ занимается шифрованием: secret_encrypted хранит уже готовый
шифротекст (симметричный ключ — из .env сервиса, следующий этап). Секрет
никогда не отдаётся в открытом виде ни в одной Pydantic-схеме — эти схемы
(Read с маской, Create/Update с новым секретом) добавляет следующий агент
вместе с эндпоинтами GET/PUT/POST /admin/integrations.
"""

import datetime as dt

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IntegrationSetting(Base):
    """Ровно одна строка на kind — гарантирует UNIQUE(kind).

    Сид (миграция 0004): по одной строке 'telegram' и 'ai_search',
    is_enabled=false, secret_encrypted=NULL, updated_by=NULL — до первой
    настройки админом через экран «Интеграции».
    """

    __tablename__ = "integration_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    # Шифротекст. NULL, пока интеграция не настроена (сид-строки).
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # bot username (telegram) / имя модели (ai_search) — ставит сервер после
    # успешной проверки секрета (getMe / тестовый вызов), клиент не присылает.
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # Администратор, последним менявший настройку. NULL для сид-строк.
    # RESTRICT: пользователя с историей правок интеграции нельзя физически
    # удалить (в системе и так нет физического удаления пользователей, SV-8).
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
