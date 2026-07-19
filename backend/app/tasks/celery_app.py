"""Celery-приложение и beat-расписание фоновых задач (архитектура §8).

Стек — Celery 5.x + Redis (брокер и result backend). Django НЕ используется
(ТЗ §0): Celery подключён как самостоятельная библиотека к тому же FastAPI-
приложению, задачи вызывают существующие сервисы (ledger, reports, storage),
бизнес-логику не дублируют.

Redis-протокол. Брокер и backend берут URL из настроек с ``?protocol=2``:
redis-py 8 по умолчанию RESP3 и шлёт HELLO, которого Redis 5 не понимает —
protocol=2 держит соединение на RESP2. См. app/core/config.py.

Задачи из архитектуры §8:
  * generate_writeoff_pdf / generate_notification_pdf — прогрев PDF (по событию);
  * export_report                                     — выгрузка отчёта (по запросу);
  * reconcile_stock       — beat, ежедневно 03:00 (сверка баланса с журналом, ADR-1);
  * monthly_income_draft  — beat, 1-е число (черновик пополнения касс, §7.2);
  * db_backup             — beat, ежедневно (pg_dump, §9).
"""

import redis.connection as _redis_connection
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

# ── RESP2 для Redis 5 ────────────────────────────────────────────────
# Развёрнутый Redis — версии 5, он не знает RESP3-команду HELLO и
# maintenance-notifications (те появились в Redis 7.4). Поэтому клиент обязан
# говорить RESP2. Основная гарантия — пин redis-py 5.x в pyproject (5.x по
# умолчанию RESP2 и совместим с Redis 5, kombu и app). Ниже — защитный пояс на
# случай, если в окружение всё же затянется redis-py 8 (там дефолт RESP3):
# принудительно опускаем версию протокола до 2 В ПРОЦЕССЕ Celery. На FastAPI
# (отдельный процесс) это не влияет; на redis-py 5.x атрибут просто
# перезапишется тем же смыслом. Делается ДО первого соединения с брокером.
if hasattr(_redis_connection, "DEFAULT_RESP_VERSION"):
    _redis_connection.DEFAULT_RESP_VERSION = 2

celery_app = Celery(
    "sklad",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    # Явный список модулей задач — надёжнее autodiscover без Django app-registry.
    include=[
        "app.tasks.pdf_tasks",
        "app.tasks.export_tasks",
        "app.tasks.reconcile",
        "app.tasks.income",
        "app.tasks.backup",
    ],
)

celery_app.conf.update(
    timezone=settings.celery_timezone,
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,  # задача переедет к другому воркеру, если этот упал
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # тяжёлые задачи (экспорт/бэкап) не копим пачками
    result_expires=24 * 60 * 60,  # результаты живут сутки — хватает на polling выгрузки
    task_default_queue="default",
    # Ретраи по сети/брокеру: экспорт и прогрев PDF идемпотентны по ключу объекта.
    task_acks_on_failure_or_timeout=True,
)

# ── Beat-расписание (архитектура §8) ────────────────────────────────
celery_app.conf.beat_schedule = {
    # Ревизор остатков — ежедневно 03:00 местного времени (ADR-1).
    "reconcile-stock-nightly": {
        "task": "tasks.reconcile_stock",
        "schedule": crontab(hour=3, minute=0),
    },
    # Черновик пополнения касс — 1-е число месяца, 06:00. НЕ автопроводка (§7.2).
    "monthly-income-draft": {
        "task": "tasks.monthly_income_draft",
        "schedule": crontab(day_of_month=1, hour=6, minute=0),
    },
    # Бэкап БД — ежедневно 02:00 (до ревизии остатков), §9.
    "db-backup-nightly": {
        "task": "tasks.db_backup",
        "schedule": crontab(hour=2, minute=0),
    },
}
