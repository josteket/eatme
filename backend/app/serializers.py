"""Преобразование моделей в словари для JSON-ответов."""
from __future__ import annotations

from .models import Recipe, RecipeIngredient
from .nutrition import (
    carb_load_label,
    portion_weight_grams,
    recipe_per_serving,
    recipe_total_nutrition,
)

CATEGORY_LABELS = {
    "BREAKFAST": ("Завтраки", "🍳"),
    "LUNCH": ("Обеды", "🍲"),
    "DINNER": ("Ужины", "🍽"),
    "SOUP": ("Супы", "🥣"),
    "SALAD": ("Салаты", "🥗"),
    "SNACK": ("Перекусы", "🍓"),
    "DESSERT": ("Десерты", "🍰"),
    "DRINK": ("Напитки", "🥤"),
    "BAKING": ("Выпечка", "🥞"),
    "FASTFOOD": ("Хочется вредного", "😈"),
}

GDM_LABEL = {
    "yes": "Подходит для рациона с контролем углеводов",
    "moderate": "Можно периодически, следите за размером порции",
    "no": "Высокая углеводная нагрузка",
}


def _lines(text: str) -> list[str]:
    return [x.strip() for x in (text or "").split("\n") if x.strip()]


def ingredient_line(ri: RecipeIngredient, servings: int, base_servings: int) -> dict:
    factor = servings / max(base_servings, 1)
    amount = ri.amount * factor
    amount = round(amount) if ri.unit == "pcs" else round(amount)
    return {
        "name": ri.ingredient.name,
        "amount": amount,
        "unit": ri.unit,
        "optional": ri.optional,
        "gluten_status": ri.ingredient.gluten_status,
    }


def recipe_brief(recipe: Recipe) -> dict:
    per = recipe_per_serving(recipe)
    cat_label, cat_emoji = CATEGORY_LABELS.get(recipe.category, (recipe.category, "🍽"))
    return {
        "id": recipe.id,
        "slug": recipe.slug,
        "name": recipe.name,
        "emoji": recipe.emoji,
        "category": recipe.category,
        "category_label": cat_label,
        "cuisine": recipe.cuisine,
        "short_description": recipe.short_description,
        "total_time": recipe.prep_time + recipe.cook_time,
        "servings": recipe.servings,
        "gluten_free": recipe.gluten_free,
        "celiac_safe": recipe.celiac_safe,
        "gdm_suitable": recipe.gdm_suitable,
        "carb_load": carb_load_label(per),
        "tags": _lines(recipe.tags),
        "per_serving": per.rounded(),
    }


def recipe_full(recipe: Recipe, servings: int | None = None) -> dict:
    servings = servings or recipe.servings
    base = recipe_brief(recipe)
    per = recipe_per_serving(recipe)
    total = recipe_total_nutrition(recipe)
    base.update(
        {
            "description": recipe.description,
            "prep_time": recipe.prep_time,
            "cook_time": recipe.cook_time,
            "difficulty": recipe.difficulty,
            "storage": recipe.storage,
            "freezer_safe": recipe.freezer_safe,
            "warnings": _lines(recipe.warnings or ""),
            "instructions": _lines(recipe.instructions),
            "pros": _lines(recipe.pros),
            "cons": _lines(recipe.cons),
            "gdm_label": GDM_LABEL.get(recipe.gdm_suitable, ""),
            "portion_weight": round(portion_weight_grams(recipe)),
            "selected_servings": servings,
            "ingredients": [
                ingredient_line(ri, servings, recipe.servings)
                for ri in recipe.ingredients
            ],
            "nutrition_total": total.scaled(servings / max(recipe.servings, 1)).rounded(),
            "nutrition_per_serving": per.rounded(),
        }
    )
    return base
