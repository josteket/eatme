"""Подключение к SQLite через SQLAlchemy 2.x."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import PROJECT_ROOT, settings

# Приводим относительный sqlite-путь к абсолютному (чтобы база всегда была в корне)
url = settings.DATABASE_URL
if url.startswith("sqlite:///./"):
    db_path = PROJECT_ROOT / url.replace("sqlite:///./", "")
    url = f"sqlite:///{db_path}"
# Render/Heroku дают DATABASE_URL как postgres:// — SQLAlchemy ждёт postgresql://
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

IS_SQLITE = url.startswith("sqlite")

engine = create_engine(
    url,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    pool_pre_ping=not IS_SQLITE,
    echo=False,
)

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
