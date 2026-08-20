"""Расчёт КБЖУ блюда из ингредиентов и сборка списка покупок.

Все значения ингредиентов заданы на 100 г / 100 мл. Для штучных (unit='pcs')
используется ingredient.piece_weight — вес одной штуки в граммах.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Ingredient, Recipe, RecipeIngredient


def _grams(ri: RecipeIngredient) -> float:
    """Перевести количество ингредиента строки рецепта в граммы (для КБЖУ)."""
    ing = ri.ingredient
    if ri.unit == "pcs":
        pw = ing.piece_weight or 0
        return ri.amount * pw
    # g и ml считаем 1:1 по массе для КБЖУ
    return ri.amount


@dataclass
class Nutrition:
    kcal: float = 0
    protein: float = 0
    fat: float = 0
    carbs: float = 0
    fiber: float = 0
    sugar: float = 0
    caffeine: float = 0

    def scaled(self, factor: float) -> "Nutrition":
        return Nutrition(
            kcal=self.kcal * factor,
            protein=self.protein * factor,
            fat=self.fat * factor,
            carbs=self.carbs * factor,
            fiber=self.fiber * factor,
            sugar=self.sugar * factor,
            caffeine=self.caffeine * factor,
        )

    def rounded(self) -> dict[str, float]:
        return {
            "kcal": round(self.kcal),
            "protein": round(self.protein, 1),
            "fat": round(self.fat, 1),
            "carbs": round(self.carbs, 1),
            "fiber": round(self.fiber, 1),
            "sugar": round(self.sugar, 1),
            "caffeine": round(self.caffeine),
        }


def recipe_total_nutrition(recipe: Recipe) -> Nutrition:
    """КБЖУ на весь рецепт (на recipe.servings порций)."""
    total = Nutrition()
    for ri in recipe.ingredients:
        g = _grams(ri)
        f = g / 100.0
        ing = ri.ingredient
        total.kcal += ing.kcal * f
        total.protein += ing.protein * f
        total.fat += ing.fat * f
        total.carbs += ing.carbs * f
        total.fiber += ing.fiber * f
        total.sugar += ing.sugar * f
        total.caffeine += ing.caffeine * f
    return total


def recipe_per_serving(recipe: Recipe) -> Nutrition:
    total = recipe_total_nutrition(recipe)
    servings = max(recipe.servings, 1)
    return total.scaled(1.0 / servings)


def carb_load_label(per_serving: Nutrition) -> str:
    """Ориентировочная углеводная нагрузка на порцию (внутренний показатель, не диагноз)."""
    c = per_serving.carbs
    if c <= 20:
        return "низкая"
    if c <= 40:
        return "умеренная"
    return "высокая"


def portion_weight_grams(recipe: Recipe) -> float:
    """Вес одной порции в граммах (сумма всех ингредиентов / servings)."""
    total_g = sum(_grams(ri) for ri in recipe.ingredients)
    return total_g / max(recipe.servings, 1)


# ---------- список покупок ----------

@dataclass
class ShopLine:
    ingredient_id: int
    name: str
    unit: str
    amount: float
    shop_group: str
    gluten_status: str
    note: str | None = None
    check_marker: bool = False  # нужно ли проверять маркировку


CHECK_MARK_GROUPS = {"CERTIFIED_GF_REQUIRED", "UNKNOWN"}


@dataclass
class ShoppingList:
    lines: list[ShopLine] = field(default_factory=list)

    def grouped(self) -> dict[str, list[ShopLine]]:
        out: dict[str, list[ShopLine]] = {}
        for line in self.lines:
            out.setdefault(line.shop_group, []).append(line)
        for grp in out.values():
            grp.sort(key=lambda x: x.name)
        return out


def build_shopping_list(items: list[tuple[Recipe, int]]) -> ShoppingList:
    """Собрать список покупок из [(рецепт, нужное_число_порций), ...].

    Количества масштабируются: recipe рассчитан на recipe.servings,
    нужно servings порций -> множитель servings / recipe.servings.
    Одинаковые ингредиенты суммируются (в исходных единицах измерения строки).
    """
    acc: dict[tuple[int, str], ShopLine] = {}
    for recipe, need_servings in items:
        factor = need_servings / max(recipe.servings, 1)
        for ri in recipe.ingredients:
            ing: Ingredient = ri.ingredient
            key = (ing.id, ri.unit)
            amount = ri.amount * factor
            if key in acc:
                acc[key].amount += amount
            else:
                acc[key] = ShopLine(
                    ingredient_id=ing.id,
                    name=ing.name,
                    unit=ri.unit,
                    amount=amount,
                    shop_group=ing.shop_group,
                    gluten_status=ing.gluten_status,
                    note=ing.note,
                    check_marker=ing.gluten_status in CHECK_MARK_GROUPS,
                )
    # округление количеств
    for line in acc.values():
        if line.unit == "pcs":
            line.amount = round(line.amount)
        else:
            line.amount = round(line.amount)
    return ShoppingList(lines=list(acc.values()))
