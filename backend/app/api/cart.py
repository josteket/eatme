"""Корзина: выбранные блюда с числом порций и «для кого» (едоки)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..database import get_db
from ..models import CartItem, Friendship, Recipe, User
from ..nutrition import build_shopping_list
from ..serializers import recipe_brief

router = APIRouter()


class AddToCart(BaseModel):
    recipe_id: int
    servings: int = Field(default=2, ge=1, le=8)
    eaters: list[int] = []  # id друзей, для кого блюдо (я — всегда, неявно)


class UpdateCart(BaseModel):
    servings: int = Field(ge=1, le=8)


def _friend_ids(db: Session, user_id: int) -> set[int]:
    return set(
        db.scalars(
            select(Friendship.friend_id).where(Friendship.user_id == user_id)
        ).all()
    )


def parse_eaters(raw: str | None) -> list[int]:
    if not raw:
        return []
    try:
        return [int(x) for x in json.loads(raw)]
    except (ValueError, TypeError):
        return []


def _clean_eaters(db: Session, user: User, ids: list[int]) -> str | None:
    """Оставляем только реальных друзей (и не самого себя)."""
    friends = _friend_ids(db, user.id)
    valid = sorted({i for i in ids if i in friends and i != user.id})
    return json.dumps(valid) if valid else None


def _cart_recipes(db: Session, user: User) -> list[tuple[CartItem, Recipe]]:
    rows = db.execute(
        select(CartItem, Recipe)
        .join(Recipe, Recipe.id == CartItem.recipe_id)
        .where(CartItem.user_id == user.id)
        .options(selectinload(Recipe.ingredients))
        .order_by(CartItem.id)
    ).all()
    return [(ci, r) for ci, r in rows]


def _cart_payload(db: Session, user: User) -> dict:
    pairs = _cart_recipes(db, user)
    # соберём имена всех едоков разом
    all_ids = set()
    for ci, _ in pairs:
        all_ids.update(parse_eaters(ci.eaters))
    names = {}
    if all_ids:
        for u in db.scalars(select(User).where(User.id.in_(all_ids))).all():
            names[u.id] = u.first_name or u.username or "Друг"
    items = []
    for ci, r in pairs:
        brief = recipe_brief(r)
        brief["cart_servings"] = ci.servings
        eids = parse_eaters(ci.eaters)
        brief["eaters"] = eids
        brief["eater_names"] = [names.get(i, "Друг") for i in eids]
        items.append(brief)
    return {"items": items, "count": len(items)}


@router.get("/cart")
def get_cart(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _cart_payload(db, user)


@router.post("/cart/items")
def add_item(
    body: AddToCart,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if not db.get(Recipe, body.recipe_id):
        raise HTTPException(status_code=404, detail="Блюдо не найдено")
    existing = db.scalar(
        select(CartItem).where(
            CartItem.user_id == user.id, CartItem.recipe_id == body.recipe_id
        )
    )
    eaters = _clean_eaters(db, user, body.eaters)
    if existing:
        existing.servings = body.servings
        existing.eaters = eaters
    else:
        db.add(
            CartItem(
                user_id=user.id,
                recipe_id=body.recipe_id,
                servings=body.servings,
                eaters=eaters,
            )
        )
    db.commit()
    return _cart_payload(db, user)


@router.patch("/cart/items/{recipe_id}")
def update_item(
    recipe_id: int,
    body: UpdateCart,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    item = db.scalar(
        select(CartItem).where(
            CartItem.user_id == user.id, CartItem.recipe_id == recipe_id
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Нет в корзине")
    item.servings = body.servings
    db.commit()
    return _cart_payload(db, user)


@router.delete("/cart/items/{recipe_id}")
def remove_item(
    recipe_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    item = db.scalar(
        select(CartItem).where(
            CartItem.user_id == user.id, CartItem.recipe_id == recipe_id
        )
    )
    if item:
        db.delete(item)
        db.commit()
    return _cart_payload(db, user)


@router.delete("/cart")
def clear_cart(db: Session = Depends(get_db), user: User = Depends(current_user)):
    for ci in db.scalars(
        select(CartItem).where(CartItem.user_id == user.id)
    ).all():
        db.delete(ci)
    db.commit()
    return _cart_payload(db, user)


@router.get("/cart/shopping-list")
def cart_shopping_list(
    db: Session = Depends(get_db), user: User = Depends(current_user)
):
    pairs = _cart_recipes(db, user)
    sl = build_shopping_list([(r, ci.servings) for ci, r in pairs])
    from .orders import shopping_list_payload  # локальный импорт во избежание цикла

    return shopping_list_payload(sl)
