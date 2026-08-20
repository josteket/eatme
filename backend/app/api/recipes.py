"""Меню, карточка блюда, поиск, категории."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Favorite, Recipe
from ..serializers import CATEGORY_LABELS, recipe_brief, recipe_full
from ..auth import current_user
from ..models import User

router = APIRouter()


def _load(db: Session):
    return select(Recipe).options(
        selectinload(Recipe.ingredients)
    )


@router.get("/categories")
def categories(db: Session = Depends(get_db)):
    counts = dict(
        db.execute(
            select(Recipe.category, func.count(Recipe.id))
            .where(Recipe.celiac_safe == True)  # noqa: E712
            .group_by(Recipe.category)
        ).all()
    )
    out = []
    for code, (label, emoji) in CATEGORY_LABELS.items():
        if counts.get(code):
            out.append(
                {"code": code, "label": label, "emoji": emoji, "count": counts[code]}
            )
    return out


@router.get("/recipes")
def list_recipes(
    category: str | None = None,
    q: str | None = None,
    tag: str | None = None,
    gdm: str | None = Query(default=None, description="yes|moderate — фильтр по нагрузке"),
    quick: bool = False,
    db: Session = Depends(get_db),
):
    # STRICT_GF_GDM: в меню попадают только безопасные для целиакии блюда
    stmt = _load(db).where(Recipe.celiac_safe == True)  # noqa: E712
    if category:
        stmt = stmt.where(Recipe.category == category)
    if gdm:
        stmt = stmt.where(Recipe.gdm_suitable == gdm)

    stmt = stmt.order_by(Recipe.category, Recipe.name)
    recipes = db.scalars(stmt).all()

    # Поиск и фильтр по тегу — в Python: SQLite LOWER() не понимает кириллицу,
    # поэтому регистронезависимый поиск делаем через str.lower() (работает для рус.).
    if q:
        ql = q.lower()
        recipes = [
            r for r in recipes
            if ql in (r.name or "").lower()
            or ql in (r.short_description or "").lower()
            or ql in (r.tags or "").lower()
            or ql in (r.cuisine or "").lower()
        ]
    if tag:
        tl = tag.lower()
        recipes = [r for r in recipes if tl in (r.tags or "").lower()]

    result = [recipe_brief(r) for r in recipes]
    if quick:
        result = [r for r in result if r["total_time"] <= 20]
    # добавляем счётчики лайков
    from .likes import likes_counts

    counts = likes_counts(db, [r["id"] for r in result])
    for r in result:
        r["likes"] = counts.get(r["id"], 0)
    return result


@router.get("/recipes/{recipe_id}")
def get_recipe(
    recipe_id: int,
    servings: int | None = Query(default=None, ge=1, le=8),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    recipe = db.scalar(_load(db).where(Recipe.id == recipe_id))
    if not recipe:
        raise HTTPException(status_code=404, detail="Блюдо не найдено")
    data = recipe_full(recipe, servings)
    fav = db.scalar(
        select(Favorite).where(
            Favorite.user_id == user.id, Favorite.recipe_id == recipe_id
        )
    )
    data["is_favorite"] = fav is not None
    from ..models import Like

    data["likes"] = db.scalar(
        select(func.count(Like.id)).where(Like.recipe_id == recipe_id)
    ) or 0
    data["is_liked"] = db.scalar(
        select(Like).where(Like.user_id == user.id, Like.recipe_id == recipe_id)
    ) is not None
    return data


@router.get("/similar/{recipe_id}")
def similar(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.scalar(_load(db).where(Recipe.id == recipe_id))
    if not recipe:
        raise HTTPException(status_code=404, detail="Блюдо не найдено")
    stmt = (
        _load(db)
        .where(Recipe.category == recipe.category, Recipe.id != recipe_id)
        .limit(3)
    )
    return [recipe_brief(r) for r in db.scalars(stmt).all()]
