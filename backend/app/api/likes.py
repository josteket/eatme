"""Лайки блюд (глобальные) и раздел «Популярное»."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..database import get_db
from ..models import Like, Recipe, User
from ..serializers import recipe_brief

router = APIRouter()


def likes_counts(db: Session, recipe_ids: list[int] | None = None) -> dict[int, int]:
    """Число лайков по рецептам: {recipe_id: count}."""
    stmt = select(Like.recipe_id, func.count(Like.id)).group_by(Like.recipe_id)
    if recipe_ids:
        stmt = stmt.where(Like.recipe_id.in_(recipe_ids))
    return {rid: c for rid, c in db.execute(stmt).all()}


def user_liked_ids(db: Session, user_id: int) -> set[int]:
    return set(
        db.scalars(select(Like.recipe_id).where(Like.user_id == user_id)).all()
    )


@router.post("/likes/{recipe_id}")
def toggle_like(
    recipe_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if not db.get(Recipe, recipe_id):
        raise HTTPException(status_code=404, detail="Блюдо не найдено")
    existing = db.scalar(
        select(Like).where(Like.user_id == user.id, Like.recipe_id == recipe_id)
    )
    if existing:
        db.delete(existing)
        liked = False
    else:
        db.add(Like(user_id=user.id, recipe_id=recipe_id))
        liked = True
    db.commit()
    count = db.scalar(
        select(func.count(Like.id)).where(Like.recipe_id == recipe_id)
    ) or 0
    return {"liked": liked, "likes": count}


@router.get("/popular")
def popular(
    limit: int = 12,
    db: Session = Depends(get_db),
):
    """Топ блюд по лайкам (только безопасные для целиакии)."""
    counts = likes_counts(db)
    if not counts:
        return []
    top_ids = [rid for rid, _ in sorted(counts.items(), key=lambda x: -x[1])][:limit]
    recipes = db.scalars(
        select(Recipe)
        .options(selectinload(Recipe.ingredients))
        .where(Recipe.id.in_(top_ids), Recipe.celiac_safe == True)  # noqa: E712
    ).all()
    by_id = {r.id: r for r in recipes}
    out = []
    for rid in top_ids:
        r = by_id.get(rid)
        if not r:
            continue
        b = recipe_brief(r)
        b["likes"] = counts.get(rid, 0)
        out.append(b)
    return out
