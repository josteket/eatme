"""Дневник глюкозы (личный, для ГСД). Не ставит диагнозов — просто журнал."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..models import GlucoseEntry, Recipe, User
from ..timeutil import iso_utc

router = APIRouter()

KIND_LABELS = {"fasting": "Натощак", "before": "До еды", "after": "После еды"}


class GlucoseCreate(BaseModel):
    value: float = Field(ge=1, le=40)          # ммоль/л, разумный диапазон
    kind: str = "after"
    note: str | None = None
    recipe_id: int | None = None


def _serialize(e: GlucoseEntry) -> dict:
    return {
        "id": e.id,
        "value": round(e.value, 1),
        "kind": e.kind,
        "kind_label": KIND_LABELS.get(e.kind, e.kind),
        "note": e.note,
        "recipe_name": e.recipe_name,
        "created_at": iso_utc(e.created_at),
    }


@router.post("/glucose")
def add_entry(
    body: GlucoseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if body.kind not in KIND_LABELS:
        raise HTTPException(status_code=400, detail="Неизвестный тип замера")
    recipe_name = None
    if body.recipe_id:
        r = db.get(Recipe, body.recipe_id)
        if r:
            recipe_name = f"{r.emoji} {r.name}"
    entry = GlucoseEntry(
        user_id=user.id,
        value=body.value,
        kind=body.kind,
        note=(body.note or "").strip()[:256] or None,
        recipe_name=recipe_name,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _serialize(entry)


@router.get("/glucose")
def list_entries(
    limit: int = 60,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    rows = db.scalars(
        select(GlucoseEntry)
        .where(GlucoseEntry.user_id == user.id)
        .order_by(GlucoseEntry.created_at.desc())
        .limit(max(1, min(limit, 200)))
    ).all()
    entries = [_serialize(e) for e in rows]
    vals = [e["value"] for e in entries]
    summary = {
        "count": len(entries),
        "avg": round(sum(vals) / len(vals), 1) if vals else None,
        "last": entries[0] if entries else None,
    }
    return {"entries": entries, "summary": summary}


@router.delete("/glucose/{entry_id}")
def delete_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    e = db.get(GlucoseEntry, entry_id)
    if e and e.user_id == user.id:
        db.delete(e)
        db.commit()
    return {"ok": True}
