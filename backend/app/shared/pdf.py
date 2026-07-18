"""Печатные формы: Jinja2-рендер + WeasyPrint (HTML → PDF). Архитектура §3.

ТЗ §2.1: «Печатные формы → WeasyPrint → PDF-бланки для печати и подписи».
ЭП нет нигде (ADR-4) — единственный артефакт печати это PDF на бумагу.

WeasyPrint импортируется ЛЕНИВО. На машине заказчика он есть (нативные
зависимости pango/cairo стоят), но на dev-машинах и в CI может отсутствовать,
а падение импорта на старте приложения из-за печатной формы недопустимо —
это опциональная возможность, а не ядро. Если WeasyPrint не установлен,
``html_to_pdf`` возвращает None, и роутер отдаёт готовый HTML (его всё равно
можно распечатать из браузера), не притворяясь, что выдал PDF.
"""

from functools import lru_cache
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(settings.templates_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render_template(template_name: str, context: dict[str, Any]) -> str:
    """Отрендерить Jinja2-шаблон печатной формы в HTML-строку."""
    return _env().get_template(template_name).render(**context)


def html_to_pdf(html: str, *, base_url: str | None = None) -> bytes | None:
    """HTML → PDF через WeasyPrint. None, если WeasyPrint недоступен.

    base_url нужен WeasyPrint для разрешения относительных ресурсов; шаблон
    уведомления самодостаточен (инлайновый <style>), поэтому по умолчанию None.
    """
    try:
        from weasyprint import HTML  # noqa: PLC0415 — ленивый импорт намеренно
    except Exception:  # noqa: BLE001 — отсутствие нативных зависимостей тоже сюда
        return None
    return HTML(string=html, base_url=base_url).write_pdf()


def build_org_context() -> dict[str, str]:
    """Реквизиты организации для бланка — из настроек (в БД не хранятся)."""
    return {
        "addressee_line1": settings.org_addressee_line1,
        "addressee_line2": settings.org_addressee_line2,
        "sender_line1": settings.org_sender_line1,
        "sender_line2": settings.org_sender_line2,
        "signer_position": settings.org_signer_position,
        "signer_name": settings.org_signer_name,
    }
