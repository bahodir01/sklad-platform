"""Telegram-бот (спека15 §6) — отдельный долгоживущий процесс, НЕ часть
uvicorn/FastAPI worker и НЕ Celery-задача.

Запуск: ``python -m app.bot.main`` (см. ``app/bot/main.py``). Диалоги —
``app/bot/handlers.py`` (aiogram Router), состояния — ``app/bot/states.py``,
клавиатуры — ``app/bot/keyboards.py``, тестируемая бизнес-склейка (без
зависимости от aiogram-объектов) — ``app/bot/logic.py``.
"""
