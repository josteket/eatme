"""Интеграционные тесты API: меню, корзина, заказы, список покупок, отметки."""


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert "db" in body


def test_menu_excludes_gluten_dishes(client):
    """Блюдо с глютеном не появляется в меню (STRICT_GF_GDM)."""
    recipes = client.get("/api/recipes").json()
    names = [r["name"] for r in recipes]
    assert "Курица с рисом" in names
    assert "Тортик с мукой" not in names  # celiac_safe = False


def test_categories(client):
    cats = client.get("/api/categories").json()
    codes = {c["code"] for c in cats}
    assert "LUNCH" in codes
    assert "DESSERT" not in codes  # единственный десерт был с глютеном -> исключён


def test_recipe_detail_has_nutrition(client):
    recipes = client.get("/api/recipes").json()
    rid = recipes[0]["id"]
    detail = client.get(f"/api/recipes/{rid}?servings=2").json()
    assert "nutrition_per_serving" in detail
    assert detail["nutrition_per_serving"]["kcal"] > 0
    assert len(detail["ingredients"]) >= 1


def test_servings_scaling(client):
    recipes = client.get("/api/recipes").json()
    rid = next(r["id"] for r in recipes if r["name"] == "Курица с рисом")
    two = client.get(f"/api/recipes/{rid}?servings=2").json()
    four = client.get(f"/api/recipes/{rid}?servings=4").json()
    ing2 = {i["name"]: i["amount"] for i in two["ingredients"]}
    ing4 = {i["name"]: i["amount"] for i in four["ingredients"]}
    assert ing4["Курица"] == ing2["Курица"] * 2


def test_cart_and_order_flow(client):
    recipes = client.get("/api/recipes").json()
    rid = recipes[0]["id"]

    # добавить в корзину
    cart = client.post("/api/cart/items", json={"recipe_id": rid, "servings": 2}).json()
    assert cart["count"] == 1

    # список покупок из корзины
    sl = client.get("/api/cart/shopping-list").json()
    assert sl["total_items"] >= 1

    # оформить заказ
    order = client.post("/api/orders", json={"note": "тест"}).json()
    assert order["id"]
    assert order["shopping_list"]["total_items"] >= 1

    # корзина очищена после заказа
    assert client.get("/api/cart").json()["count"] == 0


def test_order_status_change(client):
    recipes = client.get("/api/recipes").json()
    client.post("/api/cart/items", json={"recipe_id": recipes[0]["id"], "servings": 2})
    order = client.post("/api/orders", json={}).json()
    oid = order["id"]

    upd = client.patch(f"/api/orders/{oid}/status", json={"status": "cook"}).json()
    assert upd["status"] == "cook"

    # неизвестный статус отклоняется
    bad = client.patch(f"/api/orders/{oid}/status", json={"status": "hacked"})
    assert bad.status_code == 400


def test_shopping_check_persists(client):
    recipes = client.get("/api/recipes").json()
    client.post("/api/cart/items", json={"recipe_id": recipes[0]["id"], "servings": 2})
    order = client.post("/api/orders", json={}).json()
    oid = order["id"]
    key = order["shopping_list"]["groups"][0]["items"][0]["key"]

    # отметить куплено
    client.patch(f"/api/orders/{oid}/check", json={"key": key, "checked": True})

    # переоткрыть заказ — отметка сохранилась
    again = client.get(f"/api/orders/{oid}").json()
    checked = [
        it["checked"]
        for g in again["shopping_list"]["groups"]
        for it in g["items"]
        if it["key"] == key
    ]
    assert checked == [True]

    # снять отметку
    client.patch(f"/api/orders/{oid}/check", json={"key": key, "checked": False})
    again2 = client.get(f"/api/orders/{oid}").json()
    still = [
        it["checked"]
        for g in again2["shopping_list"]["groups"]
        for it in g["items"]
        if it["key"] == key
    ]
    assert still == [False]


def test_favorites_toggle(client):
    recipes = client.get("/api/recipes").json()
    rid = recipes[0]["id"]
    r1 = client.post(f"/api/favorites/{rid}").json()
    assert r1["is_favorite"] is True
    assert any(f["id"] == rid for f in client.get("/api/favorites").json())
    r2 = client.post(f"/api/favorites/{rid}").json()
    assert r2["is_favorite"] is False


def test_repeat_order(client):
    recipes = client.get("/api/recipes").json()
    client.post("/api/cart/items", json={"recipe_id": recipes[0]["id"], "servings": 3})
    order = client.post("/api/orders", json={}).json()
    res = client.post(f"/api/orders/{order['id']}/repeat").json()
    assert res["added"] >= 1
    assert client.get("/api/cart").json()["count"] >= 1


def test_search(client):
    res = client.get("/api/recipes?q=курица").json()
    assert any("Курица" in r["name"] for r in res)


def test_empty_cart_order_rejected(client):
    client.delete("/api/cart")
    resp = client.post("/api/orders", json={})
    assert resp.status_code == 400


def test_new_order_status_is_buy(client):
    recipes = client.get("/api/recipes").json()
    client.post("/api/cart/items", json={"recipe_id": recipes[0]["id"], "servings": 2})
    order = client.post("/api/orders", json={}).json()
    assert order["status"] == "buy"
    assert "Купить" in order["status_label"]


def test_stats_reflects_orders(client):
    recipes = client.get("/api/recipes").json()
    client.post("/api/cart/items", json={"recipe_id": recipes[0]["id"], "servings": 2})
    client.post("/api/orders", json={})

    s = client.get("/api/stats").json()
    assert s["total_orders"] >= 1
    assert s["total_dishes"] >= 1
    assert len(s["daily"]) == 7
    assert s["nutrition_week"]["kcal"] >= 0
    assert isinstance(s["top_dishes"], list)
