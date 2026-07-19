"""monthly_income_draft — черновик пополнения касс (архитектура §8, ТЗ §7.2).

Beat, 1-е число месяца. Формирует ЧЕРНОВИК ежемесячного пополнения обеих касс.

╔══════════════════════════════════════════════════════════════════════════╗
║ СТРОГО НЕ АВТОПРОВОДКА. §7.2: «подтверждение остаётся за администратором».  ║
║ Задача НЕ создаёт money_income и НЕ меняет cash_desks.balance — она только  ║
║ УВЕДОМЛЯЕТ администратора, что пора провести пополнение вручную.            ║
╚══════════════════════════════════════════════════════════════════════════╝

ПОЧЕМУ УВЕДОМЛЕНИЕ, А НЕ ЗАПИСЬ-ЧЕРНОВИК В БД. Схема заморожена (02-contract.json,
22 таблицы). У money_income НЕТ поля статуса draft/pending — «черновик прихода»
в текущей модели данных негде хранить, не меняя схему. Добавлять статус или
23-ю таблицу молча запрещено. Поэтому черновик реализован как АРТЕФАКТ-
УВЕДОМЛЕНИЕ администратору в объектном хранилище (drafts/income/<YYYY-MM>.json)
плюс структурный алерт в лог. Это:
  * не трогает схему и не пишет в транзакционные таблицы (read-only на БД);
  * физически не может провести приход (money_income не создаётся);
  * идемпотентно: ключ артефакта один на месяц, повторный прогон 1-го числа
    (ретрай beat) перезаписывает тот же объект, а не плодит черновики.

⚠ ЭТО ПРОВИЗОРНОЕ РЕШЕНИЕ — см. ВОПРОС в отчёте .feature-dev/08-celery-tasks.md.
Как именно моделировать «черновик пополнения» при замороженной схеме (отдельная
запись со спец-флагом / уведомление админу / иное) — решает заказчик. Выбран
самый безопасный вариант (уведомление), не требующий правки схемы.

Сумму пополнения задача НЕ придумывает: политики суммы в ТЗ/схеме нет, а угадать
её — значит подсунуть администратору неверную цифру. В черновик кладётся текущий
баланс каждой кассы и suggested_amount=null — сумму администратор вписывает сам
при ручном проведении POST /cash/income.
"""

import datetime as dt
import json
import logging

from sqlalchemy import select

from app.core.config import settings
from app.tasks.celery_app import celery_app
from app.tasks.runtime import run_async, task_session

logger = logging.getLogger(__name__)


def list_income_draft_alerts() -> list[dict]:
    """Прочитать артефакты drafts/income/*.json и вернуть НЕподтверждённые.

    Переиспользуется read-only эндпоинтом админ-панели GET /admin/alerts (§7.2,
    Q3 заказчика — «уведомление внутри админ-панели»). Возвращает список
    черновиков monthly_income_draft с ``posted == false``. Логику формирования
    черновика не дублирует — только читает то, что положила задача
    monthly_income_draft. Без БД и без побочных эффектов, идемпотентно.
    """
    from app.shared.storage import get_object, list_objects

    prefix = settings.s3_bucket_income_drafts_prefix.rstrip("/") + "/"
    drafts: list[dict] = []
    for key in list_objects(settings.s3_bucket_documents, prefix):
        if not key.endswith(".json"):
            continue
        raw = get_object(settings.s3_bucket_documents, key)
        if raw is None:
            continue
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue  # чужой/битый объект под тем же префиксом — пропускаем
        if data.get("kind") != "monthly_income_draft":
            continue
        if data.get("posted") is True:  # проведён администратором → не алерт
            continue
        data["object_ref"] = f"{settings.s3_bucket_documents}/{key}"
        drafts.append(data)
    # Свежие месяцы — выше.
    drafts.sort(key=lambda d: d.get("period", ""), reverse=True)
    return drafts


@celery_app.task(name="tasks.monthly_income_draft", bind=True)
def monthly_income_draft(self, period: str | None = None) -> dict:
    """Сформировать черновик-уведомление о пополнении касс за месяц.

    :param period: «YYYY-MM». По умолчанию — текущий месяц (beat 1-го числа).
    :returns: dict с черновиком (JSON-сериализуемый). money_income НЕ создаётся,
        балансы касс НЕ меняются.
    """
    return run_async(_monthly_income_draft(period))


async def _monthly_income_draft(period: str | None) -> dict:
    from app.modules.cash.models import CashDesk

    if period is None:
        period = dt.date.today().strftime("%Y-%m")

    async with task_session() as session:
        # ЧИСТОЕ ЧТЕНИЕ. Никаких INSERT/UPDATE — приход не проводится (§7.2).
        desks = list(await session.scalars(select(CashDesk).order_by(CashDesk.type)))
        desk_drafts = [
            {
                "cash_desk_id": d.id,
                "cash_desk_type": d.type.value,
                "current_balance": str(d.balance),
                # Сумму вписывает администратор при ручном проведении (см. docstring).
                "suggested_amount": None,
            }
            for d in desks
        ]

    draft = {
        "kind": "monthly_income_draft",
        "period": period,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "posted": False,  # инвариант: задача НИКОГДА не проводит приход
        "requires_admin_confirmation": True,  # §7.2
        "action": "POST /api/v1/cash/income (вручную, admin)",
        "desks": desk_drafts,
        "note": (
            "Черновик пополнения. НЕ проведён автоматически (§7.2). "
            "Администратор проводит приход вручную, указывая сумму."
        ),
    }

    # Артефакт-уведомление администратору. Ключ один на месяц → идемпотентно.
    from app.shared.storage import put_object

    key = f"{settings.s3_bucket_income_drafts_prefix}/{period}.json"
    object_ref = put_object(
        settings.s3_bucket_documents,
        key,
        json.dumps(draft, ensure_ascii=False, indent=2).encode("utf-8"),
        content_type="application/json",
    )

    # Структурный алерт: «администратор, пора пополнить кассы» (уведомление).
    logger.warning(
        "monthly_income_draft: сформирован ЧЕРНОВИК пополнения касс за %s "
        "(касс: %d). Приход НЕ проведён (§7.2) — требуется подтверждение "
        "администратора. Артефакт: %s",
        period,
        len(desk_drafts),
        object_ref,
    )

    return {"status": "ok", "object_ref": object_ref, "draft": draft}
