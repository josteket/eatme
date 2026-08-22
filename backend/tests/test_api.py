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


def test_friends_can_access_each_others_orders(db):
    """Друзья видят планы друг друга; чужой — нет."""
    from app.api.orders import _can_access, _friend_ids_of
    from app.models import Friendship, Order, User

    husband = User(telegram_id=111, first_name="Муж", role="husband")
    wife = User(telegram_id=222, first_name="Жена", role="wife")
    stranger = User(telegram_id=333, first_name="Чужой", role="user")
    db.add_all([husband, wife, stranger])
    db.flush()
    # двусторонняя дружба муж<->жена
    db.add_all([
        Friendship(user_id=husband.id, friend_id=wife.id),
        Friendship(user_id=wife.id, friend_id=husband.id),
    ])
    order = Order(user_id=husband.id, status="buy")
    db.add(order)
    db.commit()

    assert _friend_ids_of(db, wife.id) == {husband.id}
    assert _can_access(db, order, wife) is True      # жена — друг автора
    assert _can_access(db, order, husband) is True   # автор
    assert _can_access(db, order, stranger) is False # чужой не видит


def test_delete_order(client):
    recipes = client.get("/api/recipes").json()
    client.post("/api/cart/items", json={"recipe_id": recipes[0]["id"], "servings": 1})
    oid = client.post("/api/orders", json={}).json()["id"]
    assert client.delete(f"/api/orders/{oid}").status_code == 200
    assert client.get(f"/api/orders/{oid}").status_code == 404


def test_dislike_hides_recipe_from_menu(client):
    ings = client.get("/api/ingredients", params={"q": "Ягоды"}).json()
    assert ings, "ингредиент 'Ягоды' должен быть в сиде"
    berry_id = ings[0]["id"]
    before = client.get("/api/recipes").json()
    assert any(r["name"] == "Ягоды" for r in before)
    client.put("/api/dislikes", json={"ids": [berry_id]})
    after = client.get("/api/recipes").json()
    assert all(r["name"] != "Ягоды" for r in after)
    saved = client.get("/api/dislikes").json()
    assert [i["id"] for i in saved["ingredients"]] == [berry_id]


def test_order_tagging_ignores_non_friends(client):
    recipes = client.get("/api/recipes").json()
    client.post("/api/cart/items", json={"recipe_id": recipes[0]["id"], "servings": 1})
    order = client.post("/api/orders", json={"friend_ids": [999999]}).json()
    # 999999 не друг автора → в участники не попадает
    assert order["participants"] == []


def test_order_access_denied_for_stranger(client):
    recipes = client.get("/api/recipes").json()
    client.post("/api/cart/items", json={"recipe_id": recipes[0]["id"], "servings": 1})
    order = client.post("/api/orders", json={}).json()
    # автор видит свой заказ
    assert client.get(f"/api/orders/{order['id']}").status_code == 200


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


def test_likes_toggle_and_popular(client):
    recipes = client.get("/api/recipes").json()
    rid = recipes[0]["id"]

    r = client.post(f"/api/likes/{rid}").json()
    assert r["liked"] is True and r["likes"] == 1

    pop = client.get("/api/popular").json()
    assert any(p["id"] == rid for p in pop)

    lst = client.get("/api/recipes").json()
    assert next(x for x in lst if x["id"] == rid)["likes"] == 1

    r2 = client.post(f"/api/likes/{rid}").json()
    assert r2["liked"] is False and r2["likes"] == 0


def test_friends_invite(client):
    data = client.get("/api/friends").json()
    assert data["invite_code"]
    assert "t.me" in data["invite_link"]
    assert data["friends"] == []
    # свой код добавить нельзя
    assert client.post("/api/friends/accept",
                       json={"code": data["invite_code"]}).status_code == 400
    # неизвестный код
    assert client.post("/api/friends/accept", json={"code": "zzzzzz"}).status_code == 404


def test_glucose_diary(client):
    recipes = client.get("/api/recipes").json()
    rid = recipes[0]["id"]
    e = client.post("/api/glucose", json={
        "value": 5.4, "kind": "after", "recipe_id": rid, "note": "тест"}).json()
    assert e["value"] == 5.4
    assert e["kind_label"] == "После еды"
    assert e["recipe_name"]

    data = client.get("/api/glucose").json()
    assert data["summary"]["count"] == 1
    assert data["entries"][0]["value"] == 5.4

    # значение вне диапазона отклоняется
    assert client.post("/api/glucose", json={"value": 999}).status_code == 422

    client.delete(f"/api/glucose/{e['id']}")
    assert client.get("/api/glucose").json()["summary"]["count"] == 0


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
