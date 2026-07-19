"""db_backup — резервная копия БД (архитектура §8, ТЗ §9 «Отказоустойчивость»).

Beat, ежедневно 02:00. Снимает дамп PostgreSQL и кладёт его в MinIO (бакет
documents, префикс backups/), с локальным фолбэком — тем же приёмом graceful-
fallback, что MinIO→локально в shared/storage.py.

Два режима дампа:
  * ОСНОВНОЙ (prod) — ``pg_dump`` в custom-формате (-Fc). В prod-образе бинарь
    pg_dump лежит на PATH (postgresql-client). Настоящий, восстановимый через
    pg_restore дамп схемы+данных.
  * ФОЛБЭК — если pg_dump недоступен (нет клиента), задача делает логический
    дамп ДАННЫХ через ``COPY <table> TO STDOUT (CSV)`` по всем таблицам схемы.
    Это честный снимок данных (не пустышка ради size>0), восстановимый в чистую
    схему. Схему определяют модели (Base.metadata) — второго источника правды нет.

Дамп именуется ``backups/sklad_<YYYYmmdd_HHMMSS>.<ext>`` и кладётся в хранилище;
задача возвращает ключ объекта и размер в байтах (для контроля «size > 0»).
Идемпотентность здесь не нужна и вредна: каждый прогон — отдельная точка
восстановления со своей меткой времени.
"""

import datetime as dt
import io
import logging
import shutil
import subprocess

from sqlalchemy.engine import make_url

from app.core.config import settings
from app.tasks.celery_app import celery_app
from app.tasks.runtime import run_async, task_session

logger = logging.getLogger(__name__)


def _pg_conn_parts() -> dict:
    """Разобрать DATABASE_URL в параметры подключения (без драйвера +asyncpg)."""
    url = make_url(settings.database_url_str)
    return {
        "host": url.host or "127.0.0.1",
        "port": url.port or 5432,
        "user": url.username or "postgres",
        "password": url.password or "",
        "database": url.database or "postgres",
    }


@celery_app.task(name="tasks.db_backup", bind=True)
def db_backup(self) -> dict:
    """Снять дамп БД и положить в хранилище. Вернуть {object_ref, bytes, mode}."""
    parts = _pg_conn_parts()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    pg_dump = shutil.which(settings.pg_dump_path)
    if pg_dump is not None:
        content, ext, mode = _dump_via_pg_dump(pg_dump, parts)
    else:
        logger.warning(
            "db_backup: pg_dump (%r) не найден на PATH — логический COPY-фолбэк.",
            settings.pg_dump_path,
        )
        content, ext, mode = run_async(_dump_via_copy(parts))

    if not content:
        raise RuntimeError("db_backup: дамп пуст — резервная копия не создана")

    from app.shared.storage import put_object

    key = f"{settings.s3_bucket_backups_prefix}/sklad_{stamp}.{ext}"
    object_ref = put_object(
        settings.s3_bucket_documents,
        key,
        content,
        content_type="application/octet-stream",
    )
    logger.info(
        "db_backup: дамп создан (%s, %d байт, режим=%s) → %s",
        key,
        len(content),
        mode,
        object_ref,
    )
    return {"status": "ok", "object_ref": object_ref, "bytes": len(content), "mode": mode}


def _dump_via_pg_dump(pg_dump: str, parts: dict) -> tuple[bytes, str, str]:
    """Основной путь: pg_dump -Fc в stdout. PGPASSWORD — через окружение."""
    import os

    env = os.environ.copy()
    env["PGPASSWORD"] = parts["password"]
    cmd = [
        pg_dump,
        "-h", parts["host"],
        "-p", str(parts["port"]),
        "-U", parts["user"],
        "-d", parts["database"],
        "-F", "c",           # custom-формат → pg_restore
        "--no-owner",
        "--no-privileges",
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, check=False)  # noqa: S603
    if proc.returncode != 0:
        raise RuntimeError(
            f"pg_dump завершился с кодом {proc.returncode}: "
            f"{proc.stderr.decode('utf-8', 'replace')[:500]}"
        )
    return proc.stdout, "dump", "pg_dump"


async def _dump_via_copy(parts: dict) -> tuple[bytes, str, str]:
    """Фолбэк: логический дамп ДАННЫХ через COPY ... TO STDOUT (CSV) по таблицам.

    Порядок таблиц — Base.metadata.sorted_tables (родители раньше детей),
    чтобы дамп можно было залить в чистую схему без нарушения FK.
    """
    # Реестр всех 22 таблиц. Импорт app.models регистрирует модели в Base.metadata.
    import app.models  # noqa: F401
    from app.core.database import Base

    buf = io.StringIO()
    buf.write("-- sklad logical data backup (COPY CSV fallback)\n")
    buf.write(f"-- generated_at: {dt.datetime.now().isoformat()}\n\n")

    async with task_session() as session:
        raw = await session.connection()
        # asyncpg-соединение под SQLAlchemy для COPY (высокоуровневого API нет).
        asyncpg_conn = (await raw.get_raw_connection()).driver_connection
        for table in Base.metadata.sorted_tables:
            cols = list(table.columns.keys())
            buf.write(f"-- TABLE {table.name} ({', '.join(cols)})\n")
            out = io.BytesIO()
            await asyncpg_conn.copy_from_table(
                table.name, output=out, columns=cols, format="csv", header=True
            )
            buf.write(out.getvalue().decode("utf-8", "replace"))
            buf.write("\n")

    return buf.getvalue().encode("utf-8"), "sql", "copy-fallback"
