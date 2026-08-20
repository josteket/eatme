"""FastAPI-приложение: REST API + отдача Mini App (статика)."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import PROJECT_ROOT, settings
from .database import init_db, seed_if_empty
from .api import cart, favorites, misc, orders, recipes

log = logging.getLogger("eatme.web")

FRONTEND_DIR = PROJECT_ROOT / "frontend"
WEBHOOK_PATH = "/tg/webhook"

app = FastAPI(title="EAT ME — семейное меню", version="1.0.0")

# бот и диспетчер в webhook-режиме (заполняются на старте)
_bot = None
_dp = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    client = request.client.host if request.client else "?"
    has_init = "да" if request.headers.get("x-telegram-init-data") else "нет"
    q = ("?" + request.url.query) if request.url.query else ""
    try:
        response = await call_next(request)
    except Exception:
        dur = (time.perf_counter() - start) * 1000
        log.exception(
            "❌ %s %s%s | client=%s | initData=%s | %.0f мс | ИСКЛЮЧЕНИЕ",
            request.method, request.url.path, q, client, has_init, dur,
        )
        raise
    dur = (time.perf_counter() - start) * 1000
    mark = "✅" if response.status_code < 400 else "⚠️"
    # шумную статику логируем тише
    if request.url.path.startswith("/static") or request.url.path == "/favicon.ico":
        log.debug("%s %s -> %s (%.0f мс)", request.method, request.url.path,
                  response.status_code, dur)
    else:
        log.info(
            "%s %s %s%s -> %s | client=%s | initData=%s | %.0f мс",
            mark, request.method, request.url.path, q, response.status_code,
            client, has_init, dur,
        )
    return response

app.include_router(recipes.router, prefix="/api", tags=["recipes"])
app.include_router(cart.router, prefix="/api", tags=["cart"])
app.include_router(orders.router, prefix="/api", tags=["orders"])
app.include_router(favorites.router, prefix="/api", tags=["favorites"])
app.include_router(misc.router, prefix="/api", tags=["misc"])


@app.on_event("startup")
async def _startup() -> None:
    import asyncio

    from .logging_setup import setup_logging

    setup_logging()  # чтобы логи работали и в облаке (uvicorn напрямую)
    init_db()
    seed_if_empty()  # в облаке база пустая на первом старте — наполняем блюдами

    # В облаке (Render) адрес постоянный — используем его для Mini App и webhook
    if settings.use_webhook:
        settings.WEBAPP_URL = settings.public_base_url

    log.info("=" * 64)
    log.info("EAT ME — старт веб-сервера")
    log.info("  Режим          : %s", "WEBHOOK (облако)" if settings.use_webhook else "локальный")
    log.info("  Адрес          : %s", settings.WEBAPP_URL)
    log.info("  Mini App URL   : %s",
             "✅ публичный HTTPS" if settings.is_webapp_public else "⚠️ НЕ публичный")
    log.info("  Токен бота     : %s (%s)", settings.token_masked,
             "ок" if settings.token_ok else "НЕ ЗАДАН")
    log.info("  Разрешённые ID : %s", settings.allowed_ids or "(пусто — DEV пускает всех)")
    log.info("  DEV_MODE       : %s", settings.DEV_MODE)
    log.info("=" * 64)

    if settings.use_webhook:
        global _bot, _dp
        from aiogram.exceptions import TelegramRetryAfter

        from .bot.bot import build_bot, setup_menu
        from .notifier import register

        _bot, _dp = build_bot()
        register(_bot, asyncio.get_running_loop())
        hook_url = settings.public_base_url + WEBHOOK_PATH
        try:
            await _bot.set_webhook(
                url=hook_url,
                secret_token=settings.webhook_secret,
                drop_pending_updates=True,
                allowed_updates=_dp.resolve_used_update_types(),
            )
            log.info("✅ Webhook установлен: %s", hook_url)
        except TelegramRetryAfter as e:
            log.warning("Telegram просит подождать %s c перед set_webhook", e.retry_after)
        except Exception as e:  # noqa: BLE001
            log.error("Не удалось установить webhook: %s", e)
        try:
            await setup_menu(_bot)
        except Exception as e:  # noqa: BLE001
            log.warning("Кнопка-меню будет поставлена позже: %s", e)


@app.on_event("shutdown")
async def _shutdown() -> None:
    if _bot is not None:
        try:
            await _bot.session.close()
        except Exception:  # noqa: BLE001
            pass


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """Приём обновлений от Telegram (webhook-режим в облаке)."""
    if _bot is None or _dp is None:
        return {"ok": False}
    secret = request.headers.get("x-telegram-bot-api-secret-token")
    if secret != settings.webhook_secret:
        return {"ok": False}  # чужой запрос
    from aiogram.types import Update

    data = await request.json()
    update = Update.model_validate(data, context={"bot": _bot})
    await _dp.feed_update(bot=_bot, update=update)
    return {"ok": True}


# --- отдача Mini App ---
if FRONTEND_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(FRONTEND_DIR)),
        name="static",
    )

    @app.get("/")
    def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))
