"""Единая настройка логов: подробный вывод в консоль + файл logs/eatme.log."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import PROJECT_ROOT

LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "eatme.log"


def setup_logging(level: int = logging.INFO) -> Path:
    LOG_DIR.mkdir(exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)-18s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # файл (UTF-8, с ротацией)
    fh = RotatingFileHandler(
        LOG_FILE, maxBytes=3_000_000, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # консоль (может отсутствовать при запуске через pythonw / скрытый автозапуск)
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        root.addHandler(ch)

    # uvicorn/aiogram пусть тоже идут через наши хендлеры
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "aiogram"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    return LOG_FILE
