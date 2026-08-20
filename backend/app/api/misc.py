"""Профиль, случайный подбор блюда, дисклеймер."""
from __future__ import annotations

import random

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..config import PROJECT_ROOT
from ..database import get_db
from ..models import Recipe, User
from ..serializers import recipe_brief

router = APIRouter()

IMAGES_DIR = PROJECT_ROOT / "frontend" / "images"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@router.get("/images")
def available_images() -> dict[str, str]:
    """Карта slug -> URL фото. Файл frontend/images/<slug>.jpg → /static/images/<slug>.jpg.

    Блюда без файла остаются с эмодзи. Так фото можно добавлять по мере готовки.
    """
    out: dict[str, str] = {}
    if IMAGES_DIR.exists():
        for f in IMAGES_DIR.iterdir():
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                out[f.stem] = f"/static/images/{f.name}"
    return out

DISCLAIMER = (
    "Приложение помогает планировать питание и выбирать блюда. "
    "Оно не заменяет врача или индивидуальный план питания. При ГСД цели по "
    "углеводам, калорийности и контролю глюкозы определяет медицинский специалист."
)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "first_name": user.first_name,
        "username": user.username,
        "role": user.role,
        "role_label": "Жена" if user.role == "wife" else "Муж",
    }


@router.get("/disclaimer")
def disclaimer():
    return {"text": DISCLAIMER}


@router.get("/stats")
def stats(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Аналитика по заказам семьи: по дням недели, КБЖУ, топ блюд, статусы."""
    from collections import Counter
    from datetime import datetime, timedelta

    from ..models import Order
    from ..nutrition import recipe_per_serving

    orders = db.scalars(
        select(Order).options(selectinload(Order.items))
    ).all()

    rids = {it.recipe_id for o in orders for it in o.items}
    recipes: dict[int, Recipe] = {}
    if rids:
        rows = db.scalars(
            select(Recipe).options(selectinload(Recipe.ingredients))
            .where(Recipe.id.in_(rids))
        ).all()
        recipes = {r.id: r for r in rows}

    now = datetime.now()
    today = now.date()
    week_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    ru_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    daily = {d: {"orders": 0, "dishes": 0} for d in week_days}
    week_start = week_days[0]

    nutrition_week = {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fiber": 0.0}
    top = Counter()
    status_counts = Counter()
    total_dishes = 0

    for o in orders:
        d = (o.created_at or now).date()
        status_counts[o.status] += 1
        n_items = len(o.items)
        total_dishes += n_items
        if d in daily:
            daily[d]["orders"] += 1
            daily[d]["dishes"] += n_items
        for it in o.items:
            top[it.recipe_name] += 1
            if d >= week_start:
                r = recipes.get(it.recipe_id)
                if r:
                    per = recipe_per_serving(r)
                    f = it.servings
                    nutrition_week["kcal"] += per.kcal * f
                    nutrition_week["protein"] += per.protein * f
                    nutrition_week["carbs"] += per.carbs * f
                    nutrition_week["fiber"] += per.fiber * f

    daily_list = [
        {
            "date": d.isoformat(),
            "label": ru_days[d.weekday()],
            "orders": daily[d]["orders"],
            "dishes": daily[d]["dishes"],
        }
        for d in week_days
    ]
    return {
        "total_orders": len(orders),
        "total_dishes": total_dishes,
        "week_orders": sum(x["orders"] for x in daily_list),
        "week_dishes": sum(x["dishes"] for x in daily_list),
        "daily": daily_list,
        "nutrition_week": {k: round(v) for k, v in nutrition_week.items()},
        "top_dishes": [{"name": n, "count": c} for n, c in top.most_common(5)],
        "status_counts": [
            {"status": s, "count": c} for s, c in status_counts.most_common()
        ],
    }


@router.get("/random")
def random_dish(
    category: str | None = None,
    gdm: str | None = None,
    quick: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(Recipe).options(selectinload(Recipe.ingredients))
    if category:
        stmt = stmt.where(Recipe.category == category)
    if gdm:
        stmt = stmt.where(Recipe.gdm_suitable == gdm)
    recipes = db.scalars(stmt).all()
    briefs = [recipe_brief(r) for r in recipes]
    if quick:
        briefs = [b for b in briefs if b["total_time"] <= 20]
    if not briefs:
        return None
    return random.choice(briefs)
