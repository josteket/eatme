"""Критический тест (пункт 94): блюдо с глютеном не может попасть в GF-меню."""
from conftest import make_ingredient, make_recipe

from app.seed.seed import validate_recipe


def test_wheat_flour_makes_recipe_unsafe(db):
    flour = make_ingredient(db, "Пшеничная мука", carbs=76, gluten_status="CONTAINS_GLUTEN")
    egg = make_ingredient(db, "Яйцо", protein=13, gluten_status="SAFE")
    recipe = make_recipe(db, "test-wheat", [(flour, 200, "g"), (egg, 100, "g")],
                         gdm_suitable="yes")

    validate_recipe(recipe)

    assert recipe.celiac_safe is False
    assert recipe.gluten_free is False
    assert recipe.gdm_suitable == "no"
    assert "глютен" in (recipe.warnings or "").lower()


def test_barley_and_pasta_are_blocked(db):
    for name in ["Ячмень", "Обычные макароны", "Обычный хлеб"]:
        ing = make_ingredient(db, name, gluten_status="CONTAINS_GLUTEN")
        veg = make_ingredient(db, name + "-veg", gluten_status="SAFE")
        r = make_recipe(db, "r-" + name, [(ing, 100, "g"), (veg, 100, "g")])
        validate_recipe(r)
        assert r.celiac_safe is False, f"{name} должен блокировать блюдо"


def test_naturally_gf_recipe_is_safe(db):
    chicken = make_ingredient(db, "Курица", protein=31, gluten_status="SAFE")
    buckwheat = make_ingredient(db, "Гречка", carbs=20, gluten_status="SAFE")
    r = make_recipe(db, "safe-dish", [(chicken, 300, "g"), (buckwheat, 100, "g")],
                    gdm_suitable="yes")
    validate_recipe(r)
    assert r.celiac_safe is True
    assert r.gluten_free is True


def test_certified_gf_required_needs_check_but_stays_safe(db):
    oats = make_ingredient(db, "Овсянка GF", carbs=10, gluten_status="CERTIFIED_GF_REQUIRED",
                           note="только gluten-free")
    milk = make_ingredient(db, "Молоко", gluten_status="SAFE")
    r = make_recipe(db, "oatmeal", [(oats, 80, "g"), (milk, 200, "ml")], gdm_suitable="yes")
    validate_recipe(r)
    assert r.celiac_safe is True
    assert "проверить" in (r.warnings or "").lower()
