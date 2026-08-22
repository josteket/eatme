"""Трекер кофеина. Актуально при беременности/ГСД: врачи обычно советуют
держаться в пределах ~200 мг кофеина в сутки. Это дневник, а не диагноз.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..models import CaffeineEntry, User
from ..timeutil import iso_utc

router = APIRouter()

DAILY_LIMIT_MG = 200  # ориентир при беременности

# Готовые источники (мг на порцию) — для быстрого ввода
PRESETS = [
    {"source": "Эспрессо", "mg": 63, "emoji": "☕"},
    {"source": "Капучино", "mg": 63, "emoji": "☕"},
    {"source": "Кофе (чашка)", "mg": 95, "emoji": "☕"},
    {"source": "Чёрный чай", "mg": 47, "emoji": "🍵"},
    {"source": "Зелёный чай", "mg": 28, "emoji": "🍵"},
    {"source": "Матча", "mg": 70, "emoji": "🍵"},
    {"source": "Кола", "mg": 34, "emoji": "🥤"},
    {"source": "Какао", "mg": 12, "emoji": "🍫"},
]


class CaffeineCreate(BaseModel):
    mg: float = Field(ge=1, le=1000)
    source: str | None = None
    note: str | None = None


def _serialize(e: CaffeineEntry) -> dict:
    return {
        "id": e.id,
        "mg": round(e.mg),
        "source": e.source,
        "note": e.note,
        "created_at": iso_utc(e.created_at),
    }


@router.post("/caffeine")
def add_entry(
    body: CaffeineCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    entry = CaffeineEntry(
        user_id=user.id,
        mg=body.mg,
        source=(body.source or "").strip()[:64] or None,
        note=(body.note or "").strip()[:256] or None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _serialize(entry)


@router.get("/caffeine")
def list_entries(
    limit: int = 60,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    rows = db.scalars(
        select(CaffeineEntry)
        .where(CaffeineEntry.user_id == user.id)
        .order_by(CaffeineEntry.created_at.desc())
        .limit(max(1, min(limit, 200)))
    ).all()
    entries = [_serialize(e) for e in rows]
    today = datetime.now(timezone.utc).date().isoformat()
    today_mg = sum(
        e["mg"] for e in entries if (e["created_at"] or "").startswith(today)
    )
    return {
        "entries": entries,
        "presets": PRESETS,
        "summary": {
            "today_mg": today_mg,
            "limit": DAILY_LIMIT_MG,
            "over": today_mg > DAILY_LIMIT_MG,
            "count": len(entries),
        },
    }


@router.delete("/caffeine/{entry_id}")
def delete_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    e = db.get(CaffeineEntry, entry_id)
    if e and e.user_id == user.id:
        db.delete(e)
        db.commit()
    return {"ok": True}
