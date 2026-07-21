"""Точка входа Telegram-бота (спека15 §6). Запуск: ``python -m app.bot.main``.

Отдельный долгоживущий asyncio-процесс — НЕ встроен в uvicorn/FastAPI worker,
НЕ Celery-задача. Режим — **polling** (спека15 §6: локальная dev-среда без
публичного HTTPS, webhook недостижим без доп. инфраструктуры).

Управление стартом/остановом — через ``integration_settings`` (kind=
'telegram', модуль admin, спека15 §5а):
  * при старте процесс читает токен и ``is_enabled``
    (``IntegrationService.get_active_secret("telegram")`` — тот же метод,
    что уже использует ``modules/ai/service.py`` для ``ai_search``);
  * если выключено/токена нет — polling НЕ запускается, процесс ждёт
    ``_POLL_CHECK_INTERVAL_SECONDS`` (30с) и перепроверяет БД;
  * пока polling идёт, фоновая задача ``_watch_and_stop`` каждые 30с
    перечитывает ``is_enabled`` — админ выключил интеграцию через
    ``POST /admin/integrations/telegram/disable`` → polling останавливается
    БЕЗ перезапуска процесса (задержка до 30с).

Задокументированный компромисс (спека15 §6 разрешает исполнителю выбрать
способ): если админ поменял САМ ТОКЕН на уже запущенном боте (не просто
включил/выключил интеграцию), новый токен подхватится только при следующем
перезапуске процесса — hot-reload токена без рестарта не реализован. На
масштабе школы это нормально: смена токена — редкая операция, процесс
перезапускается супервизором/вручную (см. ``docker-compose.yml``, сервис
``bot``, ``restart: unless-stopped`` — контейнер поднимется заново при
ручном ``docker compose restart bot``).
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

# Импорт реестра моделей обязателен (как в app/main.py и tests/conftest.py):
# без него SQLAlchemy не разрешит строковые ссылки в relationship() между
# модулями при первом обращении ORM бота к БД.
import app.models  # noqa: F401
from app.bot.handlers import router
from app.core.database import SessionLocal
from app.modules.admin.service import IntegrationService

logger = logging.getLogger(__name__)

_POLL_CHECK_INTERVAL_SECONDS = 30


async def _get_telegram_token() -> str | None:
    """Расшифрованный токен ВКЛЮЧЁННОЙ интеграции telegram, иначе ``None``
    (kind не настроен / is_enabled=false / секрет пуст) — та же семантика,
    что ``ai_search`` уже использует в ``modules/ai/service.py``."""
    async with SessionLocal() as session:
        return await IntegrationService(session).get_active_secret("telegram")


async def _watch_and_stop(dispatcher: Dispatcher) -> None:
    """Пока идёт polling — раз в 30с проверяет ``is_enabled``; выключили →
    останавливает polling (процесс возвращается в цикл ожидания в ``run()``,
    НЕ завершается)."""
    while True:
        await asyncio.sleep(_POLL_CHECK_INTERVAL_SECONDS)
        token = await _get_telegram_token()
        if token is None:
            logger.info("Telegram-интеграция выключена — останавливаю polling")
            await dispatcher.stop_polling()
            return


async def run() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        token = await _get_telegram_token()
        if token is None:
            logger.info(
                "Telegram-бот не запущен (integration_settings.kind='telegram' "
                "is_enabled=false или токен не задан) — жду %sс и перепроверяю",
                _POLL_CHECK_INTERVAL_SECONDS,
            )
            await asyncio.sleep(_POLL_CHECK_INTERVAL_SECONDS)
            continue

        # Без default parse_mode: reason/description — свободный текст
        # учителя и может содержать символы, ломающие Markdown/HTML-разбор
        # Telegram (напр. "<", "*"). Простой текст безопаснее принудительного
        # форматирования.
        bot = Bot(token=token)
        dispatcher = Dispatcher(storage=MemoryStorage())
        dispatcher.include_router(router)

        watcher = asyncio.create_task(_watch_and_stop(dispatcher))
        try:
            logger.info("Запускаю polling Telegram-бота")
            await dispatcher.start_polling(bot, handle_signals=False)
        except Exception:  # noqa: BLE001 — процесс обязан пережить сбой polling
            logger.exception(
                "Polling завершился с ошибкой, перезапускаю через %sс",
                _POLL_CHECK_INTERVAL_SECONDS,
            )
            await asyncio.sleep(_POLL_CHECK_INTERVAL_SECONDS)
        finally:
            watcher.cancel()
            await bot.session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
