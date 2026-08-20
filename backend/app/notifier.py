"""Мост между API (sync) и Telegram-ботом (async) для уведомлений.

run.py регистрирует сюда экземпляр бота и работающий event loop.
Sync-эндпоинты вызывают notify(...) — сообщение планируется в loop бота.
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("eatme.notifier")

_bot = None
_loop: asyncio.AbstractEventLoop | None = None


def register(bot, loop: asyncio.AbstractEventLoop) -> None:
    global _bot, _loop
    _bot = bot
    _loop = loop


async def _send(chat_id: int, text: str) -> None:
    try:
        await _bot.send_message(chat_id, text, disable_web_page_preview=True)
    except Exception as e:  # noqa: BLE001
        log.warning("Не удалось отправить сообщение %s: %s", chat_id, e)


def notify(chat_ids: list[int], text: str) -> None:
    """Отправить текст нескольким пользователям (не блокирует API)."""
    if _bot is None or _loop is None:
        log.info("Бот не запущен — уведомление пропущено: %s", text[:60])
        return
    for cid in chat_ids:
        try:
            asyncio.run_coroutine_threadsafe(_send(cid, text), _loop)
        except RuntimeError as e:
            log.warning("Loop недоступен: %s", e)
