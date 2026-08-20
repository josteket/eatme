"""Заказы = сохранённые планы еды. Создание генерирует список покупок и
уведомляет обоих членов семьи через бота."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..config import settings
from ..database import get_db
from ..models import CartItem, Order, OrderItem, Recipe, User
from ..notifier import notify
from ..nutrition import ShopLine, ShoppingList, build_shopping_list

router = APIRouter()

STATUS_LABELS = {
    "buy": "🛒 Купить",
    "wait": "⏳ Ожидание",
    "cook": "👨‍🍳 Готовить",
    "done": "✅ Выполнено",
    # старые значения (для заказов из прошлых версий)
    "planned": "🛒 Купить",
    "cooking": "👨‍🍳 Готовить",
    "cancelled": "❌ Отменён",
}

# Порядок стадий заказа-плана
STATUS_FLOW = ["buy", "wait", "cook", "done"]

SHOP_GROUP_ORDER = [
    "мясо и птица", "рыба", "яйца и молочка", "овощи", "фрукты и ягоды",
    "крупы и мука", "бобовые", "орехи и семена", "масло и специи",
    "бакалея", "напитки", "прочее",
]


class CreateOrder(BaseModel):
    note: str | None = None


def shop_key(ingredient_id: int, unit: str) -> str:
    return f"{ingredient_id}:{unit}"


def shopping_list_payload(sl: ShoppingList, checked: set[str] | None = None) -> dict:
    checked = checked or set()
    grouped = sl.grouped()
    groups = []
    ordered_keys = [g for g in SHOP_GROUP_ORDER if g in grouped]
    ordered_keys += [g for g in grouped if g not in SHOP_GROUP_ORDER]
    checked_count = 0
    for gkey in ordered_keys:
        lines: list[ShopLine] = grouped[gkey]
        items = []
        for ln in lines:
            key = shop_key(ln.ingredient_id, ln.unit)
            is_checked = key in checked
            if is_checked:
                checked_count += 1
            items.append(
                {
                    "key": key,
                    "ingredient_id": ln.ingredient_id,
                    "name": ln.name,
                    "amount": ln.amount,
                    "unit": ln.unit,
                    "check_marker": ln.check_marker,
                    "checked": is_checked,
                    "note": ln.note,
                }
            )
        groups.append({"group": gkey, "items": items})
    total_items = sum(len(g["items"]) for g in groups)
    return {"groups": groups, "total_items": total_items, "checked_count": checked_count}


def _load_checked(order: Order) -> set[str]:
    raw = (order.checked_items or "").strip()
    if not raw:
        return set()
    try:
        import json

        return set(json.loads(raw))
    except (ValueError, TypeError):
        return set()


def _order_recipes(db: Session, order: Order) -> list[tuple[Recipe, int]]:
    out = []
    for it in order.items:
        r = db.scalar(
            select(Recipe)
            .options(selectinload(Recipe.ingredients))
            .where(Recipe.id == it.recipe_id)
        )
        if r:
            out.append((r, it.servings))
    return out


def _order_payload(db: Session, order: Order, with_list: bool = True) -> dict:
    items = [
        {
            "recipe_id": it.recipe_id,
            "name": it.recipe_name,
            "servings": it.servings,
        }
        for it in order.items
    ]
    data = {
        "id": order.id,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "status": order.status,
        "status_label": STATUS_LABELS.get(order.status, order.status),
        "note": order.note,
        "author": order.user.first_name or order.user.username or "—",
        "author_role": order.user.role,
        "items": items,
    }
    if with_list:
        sl = build_shopping_list(_order_recipes(db, order))
        data["shopping_list"] = shopping_list_payload(sl, _load_checked(order))
    return data


def _notify_targets(author: User) -> list[int]:
    """Кому слать уведомление — всем разрешённым (муж+жена)."""
    ids = list(settings.allowed_ids)
    if author.telegram_id not in ids:
        ids.append(author.telegram_id)
    return ids


@router.post("/orders")
def create_order(
    body: CreateOrder,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    cart = db.scalars(
        select(CartItem).where(CartItem.user_id == user.id)
    ).all()
    if not cart:
        raise HTTPException(status_code=400, detail="Корзина пуста")

    order = Order(user_id=user.id, note=body.note, status="buy")
    db.add(order)
    db.flush()

    for ci in cart:
        recipe = db.get(Recipe, ci.recipe_id)
        if recipe:
            db.add(
                OrderItem(
                    order_id=order.id,
                    recipe_id=recipe.id,
                    servings=ci.servings,
                    recipe_name=f"{recipe.emoji} {recipe.name}",
                )
            )
        db.delete(ci)  # очищаем корзину
    db.commit()
    db.refresh(order)

    _send_new_order_notification(db, order, user)
    return _order_payload(db, order)


def _send_new_order_notification(db: Session, order: Order, author: User) -> None:
    who = author.first_name or ("Жена" if author.role == "wife" else "Муж")
    lines = [f"🛎 {who} собрал(а) план еды №{order.id}:", ""]
    for it in order.items:
        lines.append(f"• {it.recipe_name} — {it.servings} порц.")
    lines.append("")
    lines.append("🛒 Список покупок готов — откройте приложение.")
    notify(_notify_targets(author), "\n".join(lines))


@router.get("/orders")
def list_orders(db: Session = Depends(get_db), user: User = Depends(current_user)):
    # Показываем заказы всей семьи (общий дом), новые сверху
    stmt = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.user))
        .order_by(Order.created_at.desc())
    )
    orders = db.scalars(stmt).all()
    return [_order_payload(db, o, with_list=False) for o in orders]


@router.get("/orders/{order_id}")
def get_order(
    order_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    order = db.scalar(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.user))
        .where(Order.id == order_id)
    )
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return _order_payload(db, order)


class CheckUpdate(BaseModel):
    key: str
    checked: bool


@router.patch("/orders/{order_id}/check")
def toggle_check(
    order_id: int,
    body: CheckUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Отметить/снять позицию списка покупок. Отметки общие для семьи."""
    import json

    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    checked = _load_checked(order)
    if body.checked:
        checked.add(body.key)
    else:
        checked.discard(body.key)
    order.checked_items = json.dumps(sorted(checked))
    db.commit()
    return {"key": body.key, "checked": body.checked, "checked_count": len(checked)}


class StatusUpdate(BaseModel):
    status: str


@router.patch("/orders/{order_id}/status")
def update_status(
    order_id: int,
    body: StatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if body.status not in STATUS_FLOW:
        raise HTTPException(status_code=400, detail="Неизвестный статус")
    order = db.scalar(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.user))
        .where(Order.id == order_id)
    )
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    order.status = body.status
    db.commit()
    db.refresh(order)

    notify(
        _notify_targets(user),
        f"🔔 План еды №{order.id}: статус — {STATUS_LABELS[body.status]}",
    )
    return _order_payload(db, order)


@router.post("/orders/{order_id}/repeat")
def repeat_order(
    order_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    order = db.scalar(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    added = 0
    for it in order.items:
        if not db.get(Recipe, it.recipe_id):
            continue
        existing = db.scalar(
            select(CartItem).where(
                CartItem.user_id == user.id, CartItem.recipe_id == it.recipe_id
            )
        )
        if existing:
            existing.servings = it.servings
        else:
            db.add(
                CartItem(
                    user_id=user.id, recipe_id=it.recipe_id, servings=it.servings
                )
            )
        added += 1
    db.commit()
    return {"added": added}
