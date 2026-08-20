"""Избранное."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..database import get_db
from ..models import Favorite, Recipe, User
from ..serializers import recipe_brief

router = APIRouter()


@router.get("/favorites")
def list_favorites(
    db: Session = Depends(get_db), user: User = Depends(current_user)
):
    stmt = (
        select(Recipe)
        .options(selectinload(Recipe.ingredients))
        .join(Favorite, Favorite.recipe_id == Recipe.id)
        .where(Favorite.user_id == user.id)
        .order_by(Recipe.name)
    )
    return [recipe_brief(r) for r in db.scalars(stmt).all()]


@router.post("/favorites/{recipe_id}")
def toggle_favorite(
    recipe_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if not db.get(Recipe, recipe_id):
        raise HTTPException(status_code=404, detail="Блюдо не найдено")
    fav = db.scalar(
        select(Favorite).where(
            Favorite.user_id == user.id, Favorite.recipe_id == recipe_id
        )
    )
    if fav:
        db.delete(fav)
        db.commit()
        return {"is_favorite": False}
    db.add(Favorite(user_id=user.id, recipe_id=recipe_id))
    db.commit()
    return {"is_favorite": True}
