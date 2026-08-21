"""Модели БД: пользователи, ингредиенты, рецепты, корзина, заказы."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# Статусы глютена для ингредиента
GLUTEN_SAFE = "SAFE"
GLUTEN_CERTIFIED_REQUIRED = "CERTIFIED_GF_REQUIRED"
GLUTEN_UNKNOWN = "UNKNOWN"
GLUTEN_CONTAINS = "CONTAINS_GLUTEN"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="user")  # wife | husband | user
    # ситуация пользователя: pregnant | gdm | celiac | healthy
    profile_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    unit: Mapped[str] = mapped_column(String(8), default="g")  # g | ml | pcs
    # КБЖУ на 100 г (или на 100 мл)
    kcal: Mapped[float] = mapped_column(Float, default=0)
    protein: Mapped[float] = mapped_column(Float, default=0)
    fat: Mapped[float] = mapped_column(Float, default=0)
    carbs: Mapped[float] = mapped_column(Float, default=0)
    fiber: Mapped[float] = mapped_column(Float, default=0)
    sugar: Mapped[float] = mapped_column(Float, default=0)
    caffeine: Mapped[float] = mapped_column(Float, default=0)  # мг на 100 г/мл
    gluten_status: Mapped[str] = mapped_column(String(24), default=GLUTEN_SAFE)
    # Вес одной штуки в граммах (для unit == 'pcs'), напр. яйцо = 55
    piece_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Категория покупок для группировки списка (овощи, мясо, молочка...)
    shop_group: Mapped[str] = mapped_column(String(32), default="прочее")
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    emoji: Mapped[str] = mapped_column(String(8), default="🍽")
    category: Mapped[str] = mapped_column(String(32), index=True)
    cuisine: Mapped[str | None] = mapped_column(String(48), nullable=True)
    short_description: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")

    servings: Mapped[int] = mapped_column(Integer, default=2)
    prep_time: Mapped[int] = mapped_column(Integer, default=0)   # минуты
    cook_time: Mapped[int] = mapped_column(Integer, default=0)
    difficulty: Mapped[str] = mapped_column(String(16), default="просто")

    # шаги, плюсы, минусы, теги — храним как \n-разделённый текст
    instructions: Mapped[str] = mapped_column(Text, default="")
    pros: Mapped[str] = mapped_column(Text, default="")
    cons: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="")

    storage: Mapped[str | None] = mapped_column(String(256), nullable=True)
    freezer_safe: Mapped[bool] = mapped_column(Boolean, default=False)

    gluten_free: Mapped[bool] = mapped_column(Boolean, default=True)
    celiac_safe: Mapped[bool] = mapped_column(Boolean, default=True)
    gdm_suitable: Mapped[str] = mapped_column(String(16), default="yes")  # yes | moderate | no
    warnings: Mapped[str | None] = mapped_column(Text, nullable=True)

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    amount: Mapped[float] = mapped_column(Float)   # в единицах ingredient.unit, на servings рецепта
    unit: Mapped[str] = mapped_column(String(8), default="g")
    optional: Mapped[bool] = mapped_column(Boolean, default=False)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    ingredient: Mapped[Ingredient] = relationship()


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "recipe_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))


class GlucoseEntry(Base):
    """Личный замер глюкозы (дневник для ГСД). Не диагноз — просто дневник."""
    __tablename__ = "glucose_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    value: Mapped[float] = mapped_column(Float)          # ммоль/л
    kind: Mapped[str] = mapped_column(String(16), default="after")  # fasting|before|after
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    recipe_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Like(Base):
    """Глобальный лайк блюда (общий на всех пользователей → популярность)."""
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("user_id", "recipe_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("user_id", "recipe_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    servings: Mapped[int] = mapped_column(Integer, default=2)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    status: Mapped[str] = mapped_column(String(16), default="buy")  # buy | wait | cook | done
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # JSON-список ключей отмеченных позиций списка покупок ("ingredientId:unit")
    checked_items: Mapped[str] = mapped_column(Text, default="")

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    user: Mapped[User] = relationship()


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    servings: Mapped[int] = mapped_column(Integer, default=2)
    # снимок названия на момент заказа
    recipe_name: Mapped[str] = mapped_column(String(256), default="")

    order: Mapped[Order] = relationship(back_populates="items")
    recipe: Mapped[Recipe] = relationship()

    # чекбоксы «куплено» для списка покупок хранить не будем — список динамический
