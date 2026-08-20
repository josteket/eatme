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
from .database import init_db
from .api import cart, favorites, misc, orders, recipes

log = logging.getLogger("eatme.web")

FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(title="EAT ME — семейное меню", version="1.0.0")

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
def _startup() -> None:
    init_db()
    log.info("=" * 64)
    log.info("EAT ME — старт веб-сервера")
    log.info("  Адрес локально : http://localhost:%s", settings.PORT)
    log.info("  WEBAPP_URL     : %s", settings.WEBAPP_URL)
    if settings.is_webapp_public:
        log.info("  Mini App URL   : ✅ похоже на публичный HTTPS — ок для Telegram")
    else:
        log.warning("  Mini App URL   : ⚠️ НЕ публичный HTTPS!")
        log.warning("     Кнопка в Telegram НЕ откроется, пока WEBAPP_URL = localhost.")
        log.warning("     Подними туннель (cloudflared) и впиши его адрес в .env.")
    log.info("  Токен бота     : %s (%s)", settings.token_masked,
             "ок" if settings.token_ok else "НЕ ЗАДАН")
    log.info("  Разрешённые ID : %s", settings.allowed_ids or "(пусто — DEV пускает всех)")
    log.info("  ID жены        : %s", settings.wife_id or "(не задан)")
    log.info("  DEV_MODE       : %s", settings.DEV_MODE)
    log.info("=" * 64)


@app.get("/api/health")
def health():
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
