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

engine = create_engine(
    url,
    connect_args={"check_same_thread": False},
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
    _ensure_columns()
    _migrate_statuses()
