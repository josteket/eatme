import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.database import Base  # noqa: E402
from app import models  # noqa: E402,F401


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _seed_min(session):
    """Пара безопасных блюд + одно с глютеном (для проверки исключения из меню)."""
    from app.seed.seed import validate_recipe

    chicken = make_ingredient(session, "Курица", protein=31, kcal=165)
    rice = make_ingredient(session, "Рис", carbs=78, kcal=344)
    berries = make_ingredient(session, "Ягоды", carbs=12, kcal=52, shop_group="фрукты и ягоды")
    flour = make_ingredient(session, "Пшеничная мука", carbs=76,
                            gluten_status="CONTAINS_GLUTEN")

    r1 = make_recipe(session, "kuritsa-ris",
                     [(chicken, 300, "g"), (rice, 100, "g")],
                     name="Курица с рисом", category="LUNCH", gdm_suitable="yes")
    r2 = make_recipe(session, "yagody-snack",
                     [(berries, 150, "g")],
                     name="Ягоды", category="SNACK", gdm_suitable="yes")
    bad = make_recipe(session, "gluten-cake",
                      [(flour, 200, "g")],
                      name="Тортик с мукой", category="DESSERT", gdm_suitable="yes")
    for r in (r1, r2, bad):
        validate_recipe(r)
    session.commit()


@pytest.fixture()
def client():
    """FastAPI TestClient с общей in-memory базой (StaticPool) и сид-данными.

    TestClient без контекст-менеджера НЕ вызывает startup — реальная eatme.db
    не трогается.
    """
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)

    seed_session = TestingSession()
    _seed_min(seed_session)
    seed_session.close()

    def override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_ingredient(db, name, **kw):
    from app.models import Ingredient

    defaults = dict(
        unit="g", kcal=0, protein=0, fat=0, carbs=0, fiber=0, sugar=0,
        gluten_status="SAFE", shop_group="прочее",
    )
    defaults.update(kw)
    ing = Ingredient(name=name, **defaults)
    db.add(ing)
    db.commit()
    return ing


def make_recipe(db, slug, ings, servings=2, **kw):
    """ings: list of (Ingredient, amount, unit)."""
    from app.models import Recipe, RecipeIngredient

    kw.setdefault("name", slug)
    kw.setdefault("category", "LUNCH")
    r = Recipe(slug=slug, servings=servings, **kw)
    db.add(r)
    db.flush()
    for ing, amount, unit in ings:
        r.ingredients.append(
            RecipeIngredient(ingredient_id=ing.id, amount=amount, unit=unit)
        )
    db.commit()
    db.refresh(r)
    return r
