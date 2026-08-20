"""Наполнение базы: ингредиенты, рецепты, проверка глютена.

Запуск:  python seed.py   (из корня проекта)
Или:     cd backend && python -m app.seed.seed
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from ..database import SessionLocal, init_db
from ..models import (
    GLUTEN_CONTAINS,
    Ingredient,
    Recipe,
    RecipeIngredient,
)
from .ingredients_data import INGREDIENTS
from .ingredients_extra import INGREDIENTS_EXTRA
from .ingredients_extra2 import INGREDIENTS_EXTRA2
from .recipes_data import RECIPES
from .recipes_extra import RECIPES_EXTRA
from .recipes_extra2 import RECIPES_EXTRA2

ALL_INGREDIENTS = INGREDIENTS + INGREDIENTS_EXTRA + INGREDIENTS_EXTRA2
ALL_RECIPES = RECIPES + RECIPES_EXTRA + RECIPES_EXTRA2

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("eatme.seed")

# Углеводы на порцию, выше которых блюдо не может быть "yes" для ГСД
GDM_CARB_YES_LIMIT = 45.0
NEEDS_CHECK = {"CERTIFIED_GF_REQUIRED", "UNKNOWN"}


def _normalize_ing(entry) -> tuple[str, float, str, bool]:
    """(name, amount) | (name, amount, unit) | (name, amount, unit, optional)."""
    name = entry[0]
    amount = float(entry[1])
    unit = entry[2] if len(entry) > 2 else "g"
    optional = entry[3] if len(entry) > 3 else False
    return name, amount, unit, optional


def seed_ingredients(db) -> dict[str, Ingredient]:
    existing = {i.name: i for i in db.scalars(select(Ingredient)).all()}
    for data in ALL_INGREDIENTS:
        ing = existing.get(data["name"])
        if ing is None:
            ing = Ingredient(name=data["name"])
            db.add(ing)
            existing[data["name"]] = ing
        for k, v in data.items():
            setattr(ing, k, v)
    db.commit()
    log.info("Ингредиентов: %d", len(existing))
    return {i.name: i for i in db.scalars(select(Ingredient)).all()}


def _per_serving_carbs(recipe: Recipe) -> float:
    from ..nutrition import recipe_per_serving

    return recipe_per_serving(recipe).carbs


def validate_recipe(recipe: Recipe) -> None:
    """Проверка глютена и углеводной нагрузки. Меняет флаги на месте."""
    contains_gluten = []
    needs_check = []
    for ri in recipe.ingredients:
        st = ri.ingredient.gluten_status
        if st == GLUTEN_CONTAINS:
            contains_gluten.append(ri.ingredient.name)
        elif st in NEEDS_CHECK:
            needs_check.append(ri.ingredient.name)

    warnings = [w for w in (recipe.warnings or "").split("\n") if w.strip()]

    if contains_gluten:
        recipe.celiac_safe = False
        recipe.gluten_free = False
        recipe.gdm_suitable = "no"
        warnings.insert(
            0,
            "⛔ Содержит глютен: " + ", ".join(contains_gluten)
            + ". Не для рациона при целиакии.",
        )
    else:
        recipe.gluten_free = True
        recipe.celiac_safe = True
        if needs_check and not any("маркировк" in w.lower() for w in warnings):
            warnings.append(
                "⚠️ Проверить маркировку/состав: " + ", ".join(sorted(set(needs_check)))
            )

    # углеводная нагрузка
    carbs = _per_serving_carbs(recipe)
    if recipe.gdm_suitable == "yes" and carbs > GDM_CARB_YES_LIMIT:
        recipe.gdm_suitable = "moderate"

    recipe.warnings = "\n".join(warnings)


def seed_recipes(db, ing_map: dict[str, Ingredient]) -> None:
    count = 0
    for data in ALL_RECIPES:
        recipe = db.scalar(select(Recipe).where(Recipe.slug == data["slug"]))
        if recipe is None:
            recipe = Recipe(slug=data["slug"])
            db.add(recipe)
        # скалярные поля
        recipe.name = data["name"]
        recipe.emoji = data["emoji"]
        recipe.category = data["category"]
        recipe.cuisine = data["cuisine"]
        recipe.short_description = data["short_description"]
        recipe.description = data["description"]
        recipe.servings = data["servings"]
        recipe.prep_time = data["prep_time"]
        recipe.cook_time = data["cook_time"]
        recipe.difficulty = data["difficulty"]
        recipe.instructions = "\n".join(data["instructions"])
        recipe.pros = "\n".join(data["pros"])
        recipe.cons = "\n".join(data["cons"])
        recipe.tags = "\n".join(data["tags"])
        recipe.storage = data["storage"]
        recipe.freezer_safe = data["freezer_safe"]
        recipe.gdm_suitable = data["gdm_suitable"]
        recipe.warnings = "\n".join(data.get("warnings", []))

        # ингредиенты — пересобираем
        recipe.ingredients.clear()
        db.flush()
        for entry in data["ingredients"]:
            name, amount, unit, optional = _normalize_ing(entry)
            ing = ing_map.get(name)
            if ing is None:
                raise ValueError(
                    f"Рецепт '{data['slug']}': нет ингредиента '{name}' в базе"
                )
            recipe.ingredients.append(
                RecipeIngredient(
                    ingredient_id=ing.id, amount=amount, unit=unit, optional=optional
                )
            )
        db.flush()
        validate_recipe(recipe)
        count += 1
    db.commit()
    log.info("Рецептов: %d", count)


def run() -> None:
    init_db()
    db = SessionLocal()
    try:
        ing_map = seed_ingredients(db)
        seed_recipes(db, ing_map)

        # краткий отчёт валидации
        unsafe = db.scalars(select(Recipe).where(Recipe.celiac_safe == False)).all()  # noqa: E712
        if unsafe:
            log.warning("Небезопасные для целиакии (исключены из меню): %d", len(unsafe))
            for r in unsafe:
                log.warning("  - %s", r.name)
        else:
            log.info("Все рецепты безопасны для целиакии ✅")
        log.info("Готово. База наполнена.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
