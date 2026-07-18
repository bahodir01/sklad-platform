"""Валидация и приём загружаемых файлов (чеки). ТЗ §7 «Файлы» / архитектура §9.

Требование ТЗ §7: чеки — MinIO (S3), приватные бакеты, whitelist jpg/png/pdf,
лимит 10 МБ, проверка по MAGIC BYTES (а не по расширению — расширение подделать
тривиально, сигнатура файла — нет).

Хранение делегируется shared/storage.py (MinIO с локальным фолбэком), поэтому на
dev/CI без поднятого MinIO чек всё равно принимается и получает стабильный ключ
объекта, идентичный проду. Возвращаемое значение — ключ вида ``bucket/key``, он
кладётся в money_expense.receipt_url (INV-7).
"""

import uuid

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.shared.storage import put_object

# Сигнатуры разрешённых форматов. Проверяем ПЕРВЫЕ байты содержимого, а не
# Content-Type заголовка и не расширение имени: и то, и другое присылает клиент
# и может соврать. Ключ — (content_type, расширение) для объекта в MinIO.
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PDF_SIGNATURE = b"%PDF-"


def _sniff(data: bytes) -> tuple[str, str] | None:
    """(content_type, ext) по magic bytes или None, если формат не в whitelist."""
    if data.startswith(_JPEG_SIGNATURE):
        return "image/jpeg", ".jpg"
    if data.startswith(_PNG_SIGNATURE):
        return "image/png", ".png"
    if data.startswith(_PDF_SIGNATURE):
        return "application/pdf", ".pdf"
    return None


def validate_receipt(data: bytes) -> tuple[str, str]:
    """Проверить чек по правилам §7. Возвращает (content_type, ext).

    :raises ValidationError: пустой файл, превышен лимит 10 МБ или формат вне
        whitelist jpg/png/pdf (по magic bytes).
    """
    if not data:
        raise ValidationError("Файл чека пуст", code="receipt_empty")
    if len(data) > settings.s3_max_upload_bytes:
        limit_mb = settings.s3_max_upload_bytes // (1024 * 1024)
        raise ValidationError(
            f"Файл чека превышает лимит {limit_mb} МБ", code="receipt_too_large"
        )
    sniffed = _sniff(data)
    if sniffed is None:
        raise ValidationError(
            "Чек должен быть файлом JPG, PNG или PDF", code="receipt_bad_type"
        )
    return sniffed


def store_receipt(data: bytes) -> str:
    """Провалидировать и положить чек в бакет receipts. Возвращает ключ объекта.

    Ключ случаен (uuid) — имя файла клиента в него не попадает: оно
    небезопасно (path traversal, коллизии) и в учёте не нужно. Расширение
    берём из РАСПОЗНАННОГО формата, а не из присланного имени.
    """
    content_type, ext = validate_receipt(data)
    key = f"expenses/{uuid.uuid4().hex}{ext}"
    return put_object(
        settings.s3_bucket_receipts, key, data, content_type=content_type
    )
