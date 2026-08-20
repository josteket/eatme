"""Устойчивый запуск с публичным доступом для Telegram.

Что делает:
  1. Поднимает туннель cloudflared к localhost и берёт публичный HTTPS-адрес.
  2. Подставляет адрес в WEBAPP_URL (в память и в .env) и настраивает кнопку-меню бота.
  3. Стартует веб-сервер + бота.
  4. СЛЕДИТ за туннелем: если cloudflared упал или сеть пропала —
     автоматически переподнимает туннель, обновляет адрес и кнопку-меню.
  5. Бот (aiogram) переподключается сам; polling обёрнут в авто-перезапуск.

Полный крах процесса лечит планировщик Windows (см. install-autostart.ps1):
он перезапускает задачу.

    python run_public.py
"""
from __future__ import annotations

import asyncio
import atexit
import logging
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn  # noqa: E402

from app.config import ENV_FILE, settings  # noqa: E402
from app.database import init_db  # noqa: E402
from app.logging_setup import LOG_FILE, setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger("eatme")
tlog = logging.getLogger("eatme.tunnel")

CLOUDFLARED = ROOT / "tools" / "cloudflared.exe"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
TUNNEL_CHECK_SEC = 15          # как часто проверять живость туннеля
TUNNEL_URL_TIMEOUT = 60        # сколько ждать адрес от cloudflared

_tunnel: dict = {"proc": None, "url": None}


def _update_env_webapp_url(url: str) -> None:
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
        out, replaced = [], False
        for ln in lines:
            if ln.strip().startswith("WEBAPP_URL="):
                out.append(f"WEBAPP_URL={url}")
                replaced = True
            else:
                out.append(ln)
        if not replaced:
            out.append(f"WEBAPP_URL={url}")
        ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        tlog.warning("Не удалось обновить .env: %s", e)


def _kill_stray_cloudflared() -> None:
    """Убить возможные зависшие cloudflared от прошлого запуска (это приложение
    единственное, кто использует cloudflared на этом ПК)."""
    try:
        subprocess.run(
            ["taskkill", "/IM", "cloudflared.exe", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    except Exception:  # noqa: BLE001
        pass


def _spawn_tunnel():
    proc = subprocess.Popen(
        [str(CLOUDFLARED), "tunnel", "--no-autoupdate", "--url",
         f"http://localhost:{settings.PORT}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    found = threading.Event()

    def reader():
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.rstrip()
            if not line:
                continue
            m = URL_RE.search(line)
            if m and not found.is_set():
                _tunnel["url"] = m.group(0)
                found.set()
            else:
                tlog.debug("cf: %s", line)

    threading.Thread(target=reader, daemon=True).start()
    return proc, found


def start_or_restart_tunnel(timeout: int = TUNNEL_URL_TIMEOUT) -> str | None:
    """(Пере)поднять туннель СИНХРОННО. Возвращает новый URL или None."""
    if not CLOUDFLARED.exists():
        tlog.error("Нет %s — работаю только локально. Скачай cloudflared в tools/.",
                   CLOUDFLARED)
        return None

    old = _tunnel.get("proc")
    if old and old.poll() is None:
        try:
            old.terminate()
        except Exception:  # noqa: BLE001
            pass

    _tunnel["url"] = None
    tlog.info("Поднимаю туннель cloudflared → http://localhost:%s …", settings.PORT)
    proc, found = _spawn_tunnel()
    _tunnel["proc"] = proc

    if found.wait(timeout):
        url = _tunnel["url"]
        settings.WEBAPP_URL = url          # применяем в памяти сразу
        _update_env_webapp_url(url)
        tlog.info("Туннель готов: %s", url)
        return url
    tlog.error("Не удалось получить адрес туннеля за %d сек", timeout)
    return None


def _short(e: object) -> str:
    return str(e).replace("\n", " ")[:90]


async def _apply_url(bot, url: str) -> None:
    if not bot:
        return
    try:
        from app.bot.bot import setup_menu
        await setup_menu(bot)  # обновит кнопку-меню на новый адрес
    except Exception as e:  # noqa: BLE001
        log.debug("Кнопка-меню обновится позже: %s", _short(e))


async def menu_keeper(bot) -> None:
    """Держит кнопку-меню бота актуальной. Повторяет, пока Telegram недоступен
    (провайдер может резать api.telegram.org — ловим момент, когда связь есть)."""
    if not bot:
        return
    from app.bot.bot import setup_menu

    applied = None
    warned = False
    while True:
        if settings.is_webapp_public:
            try:
                await setup_menu(bot, log_success=False)
                if settings.WEBAPP_URL != applied:
                    applied = settings.WEBAPP_URL
                    warned = False
                    log.info("✅ Кнопка-меню в Telegram актуальна: %s", applied)
            except Exception as e:  # noqa: BLE001
                if not warned:
                    log.warning(
                        "Кнопка-меню пока не поставлена — Telegram недоступен (%s). "
                        "Похоже на блокировку api.telegram.org провайдером; помогает "
                        "прокси/VPN (TELEGRAM_PROXY в .env). Повторяю каждую минуту.",
                        _short(e),
                    )
                    warned = True
        await asyncio.sleep(60)


async def tunnel_supervisor(bot) -> None:
    """Следит за туннелем и переподнимает его при обрыве/потере сети."""
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(TUNNEL_CHECK_SEC)
        proc = _tunnel.get("proc")
        died = proc is None or proc.poll() is not None
        if not died:
            continue
        log.warning("⚠️ Туннель недоступен — переподключаюсь…")
        url = await loop.run_in_executor(None, start_or_restart_tunnel, TUNNEL_URL_TIMEOUT)
        if url:
            log.info("✅ Туннель восстановлен: %s", url)
            await _apply_url(bot, url)
        else:
            log.error("Переподключение не удалось, повтор через %d сек", TUNNEL_CHECK_SEC)


async def _supervise(factory, name: str) -> None:
    """Перезапускать корутину при падении (для polling бота)."""
    while True:
        try:
            await factory()
            return
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.error("%s упал: %s — перезапуск через 5 сек", name, e)
            await asyncio.sleep(5)


async def serve() -> None:
    init_db()
    log.info("Лог: %s", LOG_FILE)

    loop = asyncio.get_running_loop()
    _kill_stray_cloudflared()
    url = await loop.run_in_executor(None, start_or_restart_tunnel, TUNNEL_URL_TIMEOUT)
    if url:
        log.info("=" * 64)
        log.info("✅ ВСЁ ГОТОВО. Открой бота в Telegram — кнопка «Меню» уже работает")
        log.info("   Публичный адрес: %s", url)
        log.info("=" * 64)
    else:
        log.warning("Туннель не поднялся — сервер работает локально, супервизор повторит.")

    config = uvicorn.Config(
        "app.main:app", host=settings.HOST, port=settings.PORT,
        log_level="info", access_log=False,
    )
    server = uvicorn.Server(config)
    tasks = [asyncio.create_task(server.serve())]

    bot = None
    if settings.token_ok:
        from app.bot.bot import build_bot, setup_menu
        from app.notifier import register

        bot, dp = build_bot()
        register(bot, loop)
        try:
            me = await asyncio.wait_for(bot.get_me(), timeout=20)
            log.info("Бот подключён: @%s. Polling…", me.username)
        except Exception as e:  # noqa: BLE001
            log.warning("Бот пока не достучался до Telegram (%s). "
                        "Polling будет повторять сам.", _short(e))
        tasks.append(asyncio.create_task(
            _supervise(lambda: dp.start_polling(bot), "Бот-polling")
        ))
        tasks.append(asyncio.create_task(menu_keeper(bot)))
    else:
        log.warning("BOT_TOKEN не задан — только веб-сервер.")

    tasks.append(asyncio.create_task(tunnel_supervisor(bot)))
    await asyncio.gather(*tasks)


def _cleanup() -> None:
    proc = _tunnel.get("proc")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass


_lock_sock: socket.socket | None = None
_mutex_handle = None


def _acquire_single_instance() -> bool:
    """Не дать запуститься второму экземпляру (иначе два бота на один токен → 409).

    На Windows используем именованный мьютекс (надёжно), иначе — сокет-лок.
    """
    global _lock_sock, _mutex_handle
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        _mutex_handle = kernel32.CreateMutexW(None, False, "Local\\EATME_MiniApp_v1")
        # 183 = ERROR_ALREADY_EXISTS
        if kernel32.GetLastError() == 183:
            return False
        return True

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 8766))
        s.listen(1)
        _lock_sock = s
        return True
    except OSError:
        return False


def main() -> None:
    if not _acquire_single_instance():
        log.warning("EAT ME уже запущен (второй экземпляр не нужен). Выход.")
        return
    atexit.register(_cleanup)
    try:
        asyncio.run(serve())
    except (KeyboardInterrupt, SystemExit):
        log.info("Остановлено.")
    finally:
        _cleanup()


if __name__ == "__main__":
    main()
