"""Объектное хранилище (MinIO/S3) с локальным фолбэком. Архитектура §3.

ТЗ §7 «Файлы»: PDF и чеки — MinIO (S3), приватные бакеты, presigned URL TTL 5 мин.

boto3 импортируется ЛЕНИВО — ровно как WeasyPrint в shared/pdf.py. На dev/CI без
поднятого MinIO приложение не должно падать из-за необязательного объектного
хранилища. Если S3 недоступен, объект кладётся в локальный каталог, а ключ
объекта (`bucket/key`) остаётся тем же — поэтому значение `pdf_url` в БД
одинаково в обоих режимах, и вышестоящий код про фолбэк ничего не знает.
"""

import logging
import os
import tempfile
from functools import lru_cache
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# Локальный фолбэк-каталог: всегда доступный на запись temp. Ключ объекта
# отображается в путь <tmp>/sklad_storage/<bucket>/<key>.
_LOCAL_ROOT = os.path.join(tempfile.gettempdir(), "sklad_storage")


@lru_cache(maxsize=1)
def _s3_client() -> Any | None:
    """boto3 S3-клиент к MinIO или None, если хранилище недоступно."""
    try:
        import boto3  # noqa: PLC0415 — ленивый импорт намеренно
        from botocore.config import Config  # noqa: PLC0415

        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=Config(signature_version="s3v4", connect_timeout=1, retries={"max_attempts": 0}),
        )
        return client
    except Exception:  # noqa: BLE001 — нет boto3/botocore или кривой конфиг
        return None


def _local_path(bucket: str, key: str) -> str:
    return os.path.join(_LOCAL_ROOT, bucket, key)


# ── Валидация загружаемых файлов (ТЗ §7 «Файлы») ────────────────────
# Whitelist jpg/png/pdf ПО MAGIC BYTES, а не по расширению/Content-Type из
# запроса: и то и другое подделывается клиентом. Сигнатура — свойство самого
# содержимого, обмануть её нельзя, не подсунув настоящий файл нужного типа.
_RECEIPT_MAGIC: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),          # JPEG (SOI + маркер)
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),      # PNG (8-байтная сигнатура)
    (b"%PDF-", "application/pdf", "pdf"),             # PDF («%PDF-»)
)


def sniff_receipt(data: bytes) -> tuple[str, str] | None:
    """Определить тип чека по magic bytes. Возвращает (content_type, ext) или None.

    None означает «не входит в whitelist jpg/png/pdf» — вызывающий сервис
    переводит это в доменную ошибку (storage не знает про HTTP/DomainError:
    слой хранилища не тащит бизнес-исключения, ТЗ §0 «Правило слоёв»).
    """
    for magic, content_type, ext in _RECEIPT_MAGIC:
        if data.startswith(magic):
            return content_type, ext
    return None


def put_object(
    bucket: str, key: str, data: bytes, *, content_type: str = "application/octet-stream"
) -> str:
    """Положить объект. Возвращает ключ вида ``bucket/key`` (в БД → pdf_url).

    Пытается MinIO; при любой ошибке — локальный каталог. Ключ идентичен в обоих
    режимах: снаружи неважно, где физически лежит файл.
    """
    object_ref = f"{bucket}/{key}"
    client = _s3_client()
    if client is not None:
        try:
            try:
                client.head_bucket(Bucket=bucket)
            except Exception:  # noqa: BLE001 — бакета нет → создаём
                client.create_bucket(Bucket=bucket)
            client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
            return object_ref
        except Exception:  # noqa: BLE001 — MinIO не отвечает → локальный фолбэк
            logger.warning("MinIO недоступен, PDF сохранён локально: %s", object_ref)

    path = _local_path(bucket, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return object_ref


def get_object(bucket: str, key: str) -> bytes | None:
    """Прочитать объект по (bucket, key). None, если объекта нет нигде."""
    client = _s3_client()
    if client is not None:
        try:
            resp = client.get_object(Bucket=bucket, Key=key)
            return resp["Body"].read()
        except Exception:  # noqa: BLE001 — нет объекта в S3 → пробуем локально
            pass
    path = _local_path(bucket, key)
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return fh.read()
    return None


def presigned_url(bucket: str, key: str) -> str | None:
    """Presigned URL с TTL 5 мин (ТЗ §7). None в локальном режиме."""
    client = _s3_client()
    if client is None:
        return None
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=settings.s3_presigned_ttl_seconds,
        )
    except Exception:  # noqa: BLE001
        return None
