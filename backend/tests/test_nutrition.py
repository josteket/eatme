"""КБЖУ считается из ингредиентов; список покупок объединяет одинаковое."""
from conftest import make_ingredient, make_recipe

from app.nutrition import (
    build_shopping_list,
    portion_weight_grams,
    recipe_per_serving,
    recipe_total_nutrition,
)


def test_nutrition_scales_by_amount(db):
    # 150 г продукта со 100 ккал/100г -> 150 ккал
    ing = make_ingredient(db, "Продукт", kcal=100, protein=10, carbs=5)
    r = make_recipe(db, "one-ing", [(ing, 150, "g")], servings=1)
    total = recipe_total_nutrition(r)
    assert round(total.kcal) == 150
    assert round(total.protein) == 15
    assert round(total.carbs, 1) == 7.5


def test_pieces_use_piece_weight(db):
    egg = make_ingredient(db, "Яйцо", unit="pcs", kcal=155, protein=13, piece_weight=55)
    r = make_recipe(db, "eggs", [(egg, 2, "pcs")], servings=2)
    total = recipe_total_nutrition(r)
    # 2 шт * 55 г = 110 г -> 155*1.1 = 170.5 ккал
    assert round(total.kcal, 1) == 170.5
    per = recipe_per_serving(r)
    assert round(per.kcal) == 85


def test_portion_weight(db):
    a = make_ingredient(db, "A")
    b = make_ingredient(db, "B")
    r = make_recipe(db, "pw", [(a, 300, "g"), (b, 100, "g")], servings=2)
    assert portion_weight_grams(r) == 200


def test_shopping_list_merges_same_ingredient(db):
    chicken = make_ingredient(db, "Курица", protein=31)
    rice = make_ingredient(db, "Рис", carbs=78)
    r1 = make_recipe(db, "d1", [(chicken, 200, "g"), (rice, 100, "g")], servings=2)
    r2 = make_recipe(db, "d2", [(chicken, 150, "g")], servings=2)

    # берём r1 на 2 порции (x1) и r2 на 4 порции (x2)
    sl = build_shopping_list([(r1, 2), (r2, 4)])
    by_name = {ln.name: ln.amount for ln in sl.lines}
    # курица: 200*1 + 150*2 = 500
    assert by_name["Курица"] == 500
    assert by_name["Рис"] == 100


def test_shopping_list_scales_with_servings(db):
    veg = make_ingredient(db, "Овощи")
    r = make_recipe(db, "veg", [(veg, 100, "g")], servings=2)
    sl = build_shopping_list([(r, 4)])  # 4 порции = x2
    assert sl.lines[0].amount == 200
