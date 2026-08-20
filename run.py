"""Единая точка запуска: FastAPI (Mini App + API) и Telegram-бот в одном процессе.

    python run.py

Если BOT_TOKEN не задан — поднимется только веб-сервер (можно тестировать
Mini App в браузере при DEV_MODE=true).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# добавляем backend в путь импорта
BACKEND = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND))

import uvicorn  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import init_db  # noqa: E402
from app.logging_setup import LOG_FILE, setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger("eatme")


async def main() -> None:
    init_db()
    log.info("Лог пишется в файл: %s", LOG_FILE)

    config = uvicorn.Config(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
        access_log=False,  # свои логи запросов, чтобы не дублировать
    )
    server = uvicorn.Server(config)

    tasks = [asyncio.create_task(server.serve())]

    if settings.token_ok:
        from app.bot.bot import build_bot
        from app.notifier import register

        from app.bot.bot import setup_menu

        bot, dp = build_bot()
        register(bot, asyncio.get_running_loop())
        try:
            me = await bot.get_me()
            log.info("Бот подключён: @%s (id=%s). Запускаю polling…",
                     me.username, me.id)
            await setup_menu(bot)
        except Exception as e:  # noqa: BLE001
            log.error("Не удалось подключиться к боту (проверь BOT_TOKEN и интернет): %s", e)
        tasks.append(asyncio.create_task(dp.start_polling(bot)))
    else:
        log.warning(
            "BOT_TOKEN не задан — работает только веб-сервер. "
            "Открой http://localhost:%s (DEV_MODE=%s).",
            settings.PORT, settings.DEV_MODE,
        )

    if not settings.is_webapp_public:
        log.warning("‼️ WEBAPP_URL=%s — Mini App в Telegram НЕ откроется. "
                    "Нужен публичный HTTPS-туннель.", settings.WEBAPP_URL)

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Остановлено.")
