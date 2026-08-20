"""Подключение к БД (SQLite локально / Postgres в облаке) через SQLAlchemy 2.x."""
from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import PROJECT_ROOT, settings

log = logging.getLogger("eatme.db")


def _normalize(u: str) -> str:
    if u.startswith("sqlite:///./"):
        return f"sqlite:///{PROJECT_ROOT / u.replace('sqlite:///./', '')}"
    if u.startswith("postgres://"):  # Render/Heroku стиль
        return u.replace("postgres://", "postgresql://", 1)
    return u


def _make_engine(u: str):
    is_sqlite = u.startswith("sqlite")
    eng = create_engine(
        u,
        connect_args={"check_same_thread": False} if is_sqlite else {"connect_timeout": 15},
        pool_pre_ping=not is_sqlite,
        pool_recycle=1800 if not is_sqlite else -1,
        echo=False,
    )
    return eng, is_sqlite


_SQLITE_FALLBACK = f"sqlite:///{PROJECT_ROOT / 'eatme.db'}"

url = _normalize(settings.DATABASE_URL)
engine, IS_SQLITE = _make_engine(url)

# Если задан внешний Postgres — проверяем связь; при сбое НЕ роняем сервис, а
# откатываемся на локальный SQLite (данные будут эфемерными, но приложение живёт).
if not IS_SQLITE:
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        log.info("БД: подключён Postgres (%s)", engine.url.host)
    except Exception as e:  # noqa: BLE001
        log.error("БД: Postgres недоступен (%s) — откат на SQLite", str(e)[:150])
        engine.dispose()
        engine, IS_SQLITE = _make_engine(_SQLITE_FALLBACK)

ACTIVE_DIALECT = engine.dialect.name

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_columns() -> None:
    """Лёгкая миграция для SQLite: добавить недостающие колонки в существующую базу."""
    from sqlalchemy import text

    wanted = {
        "orders": [("checked_items", "TEXT DEFAULT ''")],
    }
    with engine.begin() as conn:
        for table, cols in wanted.items():
            existing = {
                row[1]
                for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            for name, decl in cols:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {decl}"))


def _migrate_statuses() -> None:
    """Перевести старые статусы заказов на новую схему buy/wait/cook/done."""
    from sqlalchemy import text

    mapping = {"planned": "buy", "cooking": "cook", "cancelled": "buy"}
    with engine.begin() as conn:
        for old, new in mapping.items():
            conn.execute(
                text("UPDATE orders SET status = :new WHERE status = :old"),
                {"new": new, "old": old},
            )


def init_db() -> None:
    from . import models  # noqa: F401  (регистрация моделей)

    Base.metadata.create_all(bind=engine)
    if IS_SQLITE:
        # лёгкие миграции для уже существующих SQLite-баз
        _ensure_columns()
        _migrate_statuses()


def seed_if_empty() -> None:
    """Наполнить базу блюдами, если она пустая (нужно в облаке при первом старте)."""
    import logging

    from .models import Recipe

    log = logging.getLogger("eatme.db")
    db = SessionLocal()
    try:
        count = db.query(Recipe).count()
    finally:
        db.close()
    if count == 0:
        log.info("База пустая — наполняю блюдами…")
        from .seed.seed import run as seed_run

        seed_run()
    else:
        log.info("В базе %d блюд — сид не нужен.", count)
