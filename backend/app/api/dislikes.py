"""«Не люблю»: персональный список нелюбимых ингредиентов.

Такие ингредиенты исключаются из меню (см. api/recipes.py). Храним как
JSON-список id в User.disliked.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..models import Ingredient, User

router = APIRouter()

SEARCH_LIMIT = 40


def disliked_ids(user: User | None) -> set[int]:
    """Разобрать User.disliked в множество id (безопасно к мусору)."""
    if not user or not user.disliked:
        return set()
    try:
        raw = json.loads(user.disliked)
        return {int(x) for x in raw}
    except (ValueError, TypeError):
        return set()


def _ing_view(i: Ingredient) -> dict:
    return {"id": i.id, "name": i.name}


@router.get("/ingredients")
def search_ingredients(q: str | None = None, db: Session = Depends(get_db)):
    """Поиск ингредиентов для пикера. Кириллица — фильтр в Python."""
    rows = db.scalars(select(Ingredient).order_by(Ingredient.name)).all()
    if q:
        ql = q.lower().strip()
        rows = [i for i in rows if ql in (i.name or "").lower()]
    return [_ing_view(i) for i in rows[:SEARCH_LIMIT]]


@router.get("/dislikes")
def get_dislikes(db: Session = Depends(get_db), user: User = Depends(current_user)):
    ids = disliked_ids(user)
    items = (
        db.scalars(select(Ingredient).where(Ingredient.id.in_(ids))).all() if ids else []
    )
    return {"ingredients": [_ing_view(i) for i in items]}


class DislikesUpdate(BaseModel):
    ids: list[int] = []


@router.put("/dislikes")
def set_dislikes(
    body: DislikesUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    # оставляем только реально существующие id
    valid = set(
        db.scalars(
            select(Ingredient.id).where(Ingredient.id.in_(set(body.ids)))
        ).all()
    )
    user.disliked = json.dumps(sorted(valid))
    db.commit()
    items = (
        db.scalars(select(Ingredient).where(Ingredient.id.in_(valid))).all()
        if valid
        else []
    )
    return {"ingredients": [_ing_view(i) for i in items]}
