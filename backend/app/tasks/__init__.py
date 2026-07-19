"""Фоновые задачи Celery (архитектура §8).

Импорт celery_app здесь даёт единую точку входа:

    celery -A app.tasks worker  ...
    celery -A app.tasks beat    ...
"""

from app.tasks.celery_app import celery_app

__all__ = ["celery_app"]
