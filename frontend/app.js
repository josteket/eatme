/* EAT ME — Telegram Mini App (vanilla JS) */
"use strict";

const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
if (tg) { tg.ready(); tg.expand(); try { tg.setHeaderColor("#f6f5f1"); } catch (e) {} }

const INIT_DATA = tg && tg.initData ? tg.initData : "";

/* ---------- API ---------- */
async function api(path, opts = {}) {
  const headers = Object.assign(
    { "Content-Type": "application/json", "X-Telegram-Init-Data": INIT_DATA },
    opts.headers || {}
  );
  const res = await fetch("/api" + path, { ...opts, headers });
  if (!res.ok) {
    let msg = "Ошибка " + res.status;
    try { const j = await res.json(); if (j.detail) msg = j.detail; } catch (e) {}
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

/* ---------- state ---------- */
const state = {
  tab: "menu",
  category: null,
  query: "",
  me: null,
  cartCount: 0,
};

/* ---------- utils ---------- */
const $ = (sel) => document.querySelector(sel);
const view = () => $("#view");
async function getCategories() {
  if (!state._cats) state._cats = await api("/categories");
  return state._cats;
}
function photoOf(slug) { return (state._images && state._images[slug]) || null; }

/* ---- генеративная обложка блюда (уникальный градиентный меш по слагу) ---- */
function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
function mulberry(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function hexToRgba(hex, a) {
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
function shade(hex, amt) {
  const n = parseInt(hex.replace("#", ""), 16);
  const cl = (v) => Math.max(0, Math.min(255, v));
  const r = cl(((n >> 16) & 255) + amt), g = cl(((n >> 8) & 255) + amt), b = cl((n & 255) + amt);
  return `rgb(${r},${g},${b})`;
}
const _coverCache = {};
function coverBg(slug, category) {
  const key = slug + category;
  if (_coverCache[key]) return _coverCache[key];
  const base = catColor(category);
  const r = mulberry(hashStr(slug));
  const blobs = [];
  for (let i = 0; i < 4; i++) {
    const x = Math.round(r() * 100), y = Math.round(r() * 100);
    const size = 44 + Math.round(r() * 46);
    const tint = i % 2 === 0 ? base : shade(base, i === 1 ? 22 : -14);
    const alpha = (0.62 - i * 0.11).toFixed(2);
    blobs.push(`radial-gradient(${size}% ${size}% at ${x}% ${y}%, ${i % 2 ? tint : hexToRgba(base, alpha)} 0%, transparent 62%)`);
  }
  const bg = blobs.join(",") + `, linear-gradient(155deg, #ffffff 2%, ${base})`;
  _coverCache[key] = bg;
  return bg;
}
function coverHTML(r, cls) {
  const photo = photoOf(r.slug);
  if (photo) return `<div class="${cls} photo" style="background-image:url('${photo}')"></div>`;
  return `<div class="${cls} cover" style="background:${coverBg(r.slug, r.category)}"><span class="cover-emoji">${r.emoji}</span></div>`;
}
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function haptic(kind = "light") { try { tg && tg.HapticFeedback.impactOccurred(kind); } catch (e) {} }

let toastTimer = null;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 2200);
}

function carbClass(load) {
  return load === "низкая" ? "b-carb-low" : load === "умеренная" ? "b-carb-mod" : "b-carb-high";
}

/* цвет-подложка по категории (для плиток и карточек) */
const CAT_COLORS = {
  BREAKFAST: "#f8e3bf", LUNCH: "#dcecca", DINNER: "#d3e5ef", SOUP: "#f1ddc4",
  SALAD: "#d8edd0", SNACK: "#f6dbe8", DESSERT: "#efd8e6", DRINK: "#d3ece7",
  BAKING: "#eee0c8", FASTFOOD: "#f5d6c4",
};
const catColor = (c) => CAT_COLORS[c] || "#e9e0d1";

/* ---------- card ---------- */
function cardHTML(r) {
  return `<div class="card" data-id="${r.id}">
    ${coverHTML(r, "card-emoji")}
    <div class="card-body">
      <div class="card-name">${esc(r.name)}</div>
      <div class="card-meta"><span>⏱ ${r.total_time} мин</span><span>🔥 ${r.per_serving.kcal} ккал</span></div>
      <div class="card-badges">
        <span class="badge-pill b-gf">GF</span>
        <span class="badge-pill ${carbClass(r.carb_load)}">${r.per_serving.carbs} г угл</span>
      </div>
    </div>
  </div>`;
}

function bindCards(root) {
  root.querySelectorAll(".card").forEach((c) =>
    c.addEventListener("click", () => openDish(c.dataset.id)));
}

/* ---------- MENU ---------- */
async function renderMenu() {
  $("#searchWrap").classList.remove("hidden");
  if (state.query) return renderSearchResults();
  if (state.category) return renderCategory(state.category);
  return renderCategoryTiles();
}

async function renderCategoryTiles() {
  const v = view();
  v.innerHTML = `<div class="loader">Загрузка…</div>`;
  const [cats, quick, fast] = await Promise.all([
    getCategories(),
    api("/recipes?quick=true"),
    api("/recipes?category=FASTFOOD"),
  ]);

  const tiles = cats.map((c) => {
    const col = catColor(c.code);
    return `<button class="cat-tile" data-cat="${c.code}">
      <div>
        <div class="cat-emoji" style="background:${col}">${c.emoji}</div>
        <div class="cat-label">${esc(c.label)}</div>
        <div class="cat-count">${c.count} блюд</div>
      </div>
      <div class="cat-arc" style="background:${col}"></div>
    </button>`;
  }).join("");

  let html = `<div class="section-title"><span class="st-accent">Категории</span></div>
    <div class="cat-grid">${tiles}</div>`;

  if (quick.length) {
    html += `<div class="section-title">⚡ За 20 минут</div>
      <div class="h-scroll" id="rowQuick">${quick.slice(0, 10).map(cardHTML).join("")}</div>`;
  }
  if (fast.length) {
    html += `<div class="section-title">😈 Хочется вредного</div>
      <div class="h-scroll" id="rowFast">${fast.map(cardHTML).join("")}</div>`;
  }
  v.innerHTML = html;

  v.querySelectorAll(".cat-tile").forEach((t) =>
    t.addEventListener("click", () => { state.category = t.dataset.cat; renderMenu(); }));
  bindCards(v);
}

async function renderCategory(code) {
  const v = view();
  v.innerHTML = `<div class="loader">Загрузка блюд…</div>`;
  const cats = await getCategories();
  const cat = cats.find((c) => c.code === code) || { label: "Блюда", emoji: "🍽" };
  const recipes = await api("/recipes?category=" + encodeURIComponent(code));

  v.innerHTML = `
    <div class="menu-head">
      <button class="menu-back" id="backCat">←</button>
      <div><h2>${cat.emoji} ${esc(cat.label)}</h2><div class="mh-count">${recipes.length} блюд</div></div>
    </div>
    <div class="grid">${recipes.map(cardHTML).join("")}</div>`;
  $("#backCat").addEventListener("click", () => { state.category = null; renderMenu(); });
  bindCards(v);
}

async function renderSearchResults() {
  const v = view();
  v.innerHTML = `<div class="loader">Ищу…</div>`;
  const recipes = await api("/recipes?q=" + encodeURIComponent(state.query));
  if (!recipes.length) {
    v.innerHTML = `<div class="empty"><div class="em">🔍</div><p>По запросу «${esc(state.query)}»<br>ничего не нашлось.</p></div>`;
    return;
  }
  v.innerHTML = `<div class="section-title">Найдено: ${recipes.length}</div>
    <div class="grid">${recipes.map(cardHTML).join("")}</div>`;
  bindCards(v);
}

/* ---------- DISH DETAIL ---------- */
async function openDish(id) {
  haptic();
  const sheet = $("#sheet");
  const inner = $("#sheetInner");
  inner.innerHTML = `<div class="loader">Загрузка…</div>`;
  sheet.classList.remove("hidden");
  document.body.style.overflow = "hidden";

  let servings = 2;
  let r = await api(`/recipes/${id}?servings=${servings}`);

  function render() {
    const n = r.nutrition_per_serving;
    const ingRows = r.ingredients.map((ing) => {
      const needCheck = ing.gluten_status === "CERTIFIED_GF_REQUIRED" || ing.gluten_status === "UNKNOWN";
      const unit = ing.unit === "pcs" ? "шт" : ing.unit === "ml" ? "мл" : "г";
      return `<div class="ing-row"><span>${esc(ing.name)}${needCheck ? ' <span class="ing-check">⚠️</span>' : ""}</span><span class="amt">${ing.amount} ${unit}</span></div>`;
    }).join("");

    const warns = (r.warnings || []).map((w) => `<div class="warn-box">${esc(w)}</div>`).join("");
    const steps = r.instructions.map((s) => `<li>${esc(s)}</li>`).join("");
    const pros = r.pros.map((s) => `<li>${esc(s)}</li>`).join("");
    const cons = r.cons.map((s) => `<li>${esc(s)}</li>`).join("");
    const tags = r.tags.map((t) => `<span class="tag">#${esc(t)}</span>`).join("");

    const heroPhoto = photoOf(r.slug);
    const heroStyle = heroPhoto
      ? `background-image:url('${heroPhoto}');background-size:cover;background-position:center`
      : `background:${coverBg(r.slug, r.category)}`;
    inner.innerHTML = `
      <div class="detail-hero ${heroPhoto ? "photo" : "cover"}" style="${heroStyle}">
        ${heroPhoto ? "" : `<span class="cover-emoji hero-emoji">${r.emoji}</span>`}
        <button class="fav-btn" id="favBtn">${r.is_favorite ? "❤️" : "🤍"}</button>
        <button class="sheet-close" id="closeSheet">✕</button>
      </div>
      <div class="detail-body">
        <div class="detail-name">${esc(r.name)}</div>
        ${r.cuisine ? `<div class="cuisine-chip">${esc(r.cuisine)} кухня</div>` : ""}
        <div class="detail-desc">${esc(r.description)}</div>

        <div class="nutri">
          <div><b>${n.kcal}</b><span>ккал</span></div>
          <div><b>${n.protein}</b><span>белки</span></div>
          <div><b>${n.fat}</b><span>жиры</span></div>
          <div><b>${n.carbs}</b><span>углев</span></div>
        </div>
        <div class="info-line">🌿 Клетчатка: ${n.fiber} г · 🍬 Сахара: ${n.sugar} г${n.caffeine ? " · ☕ Кофеин: " + n.caffeine + " мг" : ""}</div>
        <div class="info-line">⚖️ Порция ~${r.portion_weight} г · ⏱ ${r.total_time} мин · 👥 ${r.difficulty}</div>
        <div class="info-line">🏷 <b>${r.gdm_label}</b></div>

        <div class="tags">${tags}</div>
        ${warns}

        <div class="serv-row">
          <span class="lbl">Порций</span>
          <div class="stepper">
            <button id="servMinus">−</button>
            <span class="val" id="servVal">${r.selected_servings}</span>
            <button id="servPlus">+</button>
          </div>
        </div>

        <div class="blk"><h4>🧺 Состав</h4>${ingRows}</div>
        <div class="blk"><h4>👨‍🍳 Приготовление</h4><ol class="steps">${steps}</ol></div>
        ${pros ? `<div class="blk"><h4>✔ Плюсы</h4><ul class="plain pros">${pros}</ul></div>` : ""}
        ${cons ? `<div class="blk"><h4>➖ На заметку</h4><ul class="plain cons">${cons}</ul></div>` : ""}
        ${r.storage ? `<div class="info-line" style="margin-top:14px">📦 Хранение: ${esc(r.storage)}${r.freezer_safe ? " · ❄️ можно заморозить" : ""}</div>` : ""}
      </div>
      <div class="sticky-cta">
        <button class="btn btn-primary" id="addCart">🛒 Добавить в план — ${r.selected_servings} порц.</button>
      </div>`;

    $("#closeSheet").addEventListener("click", closeSheet);
    $("#favBtn").addEventListener("click", async () => {
      const res = await api(`/favorites/${r.id}`, { method: "POST" });
      r.is_favorite = res.is_favorite;
      $("#favBtn").textContent = res.is_favorite ? "❤️" : "🤍";
      haptic();
    });
    $("#servMinus").addEventListener("click", () => changeServ(-1));
    $("#servPlus").addEventListener("click", () => changeServ(1));
    $("#addCart").addEventListener("click", addToCart);
  }

  async function changeServ(d) {
    const next = Math.min(8, Math.max(1, r.selected_servings + d));
    if (next === r.selected_servings) return;
    r = await api(`/recipes/${id}?servings=${next}`);
    render();
  }

  async function addToCart() {
    await api("/cart/items", {
      method: "POST",
      body: JSON.stringify({ recipe_id: r.id, servings: r.selected_servings }),
    });
    await refreshCartCount();
    haptic("medium");
    toast("Добавлено в план 🛒");
    closeSheet();
  }

  render();
}

function closeSheet() {
  $("#sheet").classList.add("hidden");
  document.body.style.overflow = "";
}
$("#sheet").addEventListener("click", (e) => { if (e.target.id === "sheet") closeSheet(); });

/* ---------- FAVORITES ---------- */
async function renderFavorites() {
  const v = view();
  $("#searchWrap").classList.add("hidden");
  v.innerHTML = `<div class="loader">Загрузка…</div>`;
  const favs = await api("/favorites");
  if (!favs.length) {
    v.innerHTML = `<div class="empty"><div class="em">❤️</div><p>Пока нет избранного.<br>Открой блюдо и нажми 🤍</p></div>`;
    return;
  }
  v.innerHTML = `<div class="section-title">❤️ Избранное</div><div class="grid">${favs.map(cardHTML).join("")}</div>`;
  bindCards(v);
}

/* ---------- CART ---------- */
async function renderCart() {
  const v = view();
  $("#searchWrap").classList.add("hidden");
  v.innerHTML = `<div class="loader">Загрузка…</div>`;
  const cart = await api("/cart");
  if (!cart.items.length) {
    v.innerHTML = `<div class="empty"><div class="em">🛒</div><p>План пуст.<br>Выбери блюда в меню.</p></div>`;
    return;
  }

  const rows = cart.items.map((r) => `
    <div class="list-row" data-id="${r.id}">
      <div class="r-top">
        <div><div class="r-name">${r.emoji} ${esc(r.name)}</div>
        <div class="r-sub">⏱ ${r.total_time} мин · 🔥 ${r.per_serving.kcal} ккал/порц</div></div>
      </div>
      <div class="r-actions">
        <div class="stepper">
          <button class="cm" data-id="${r.id}">−</button>
          <span class="val">${r.cart_servings}</span>
          <button class="cp" data-id="${r.id}">+</button>
        </div>
        <button class="link-del" data-id="${r.id}">Убрать</button>
      </div>
    </div>`).join("");

  v.innerHTML = `
    <div class="section-title">🛒 План еды · ${cart.count} блюд</div>
    ${rows}
    <textarea class="note-input" id="orderNote" placeholder="Комментарий к плану (необязательно)…" style="margin:8px 0 4px"></textarea>
    <button class="btn btn-primary" id="checkout" style="margin-top:8px">✅ Оформить план и собрать список покупок</button>
    <button class="btn btn-ghost" id="previewShop" style="margin-top:10px">🧾 Показать список покупок</button>
    <button class="btn btn-danger" id="clearCart" style="margin-top:10px">Очистить план</button>`;

  v.querySelectorAll(".cp").forEach((b) => b.addEventListener("click", () => updateServ(b.dataset.id, +1)));
  v.querySelectorAll(".cm").forEach((b) => b.addEventListener("click", () => updateServ(b.dataset.id, -1)));
  v.querySelectorAll(".link-del").forEach((b) => b.addEventListener("click", () => removeItem(b.dataset.id)));
  $("#checkout").addEventListener("click", checkout);
  $("#previewShop").addEventListener("click", previewShopping);
  $("#clearCart").addEventListener("click", clearCart);
}

async function updateServ(id, d) {
  const row = view().querySelector(`.list-row[data-id="${id}"] .val`);
  const cur = parseInt(row.textContent, 10);
  const next = Math.min(8, Math.max(1, cur + d));
  if (next === cur) return;
  await api(`/cart/items/${id}`, { method: "PATCH", body: JSON.stringify({ servings: next }) });
  row.textContent = next;
  haptic();
}

async function removeItem(id) {
  await api(`/cart/items/${id}`, { method: "DELETE" });
  await refreshCartCount();
  renderCart();
}

async function clearCart() {
  if (tg) { tg.showConfirm("Очистить весь план?", async (ok) => { if (ok) { await api("/cart", { method: "DELETE" }); await refreshCartCount(); renderCart(); } }); }
  else { await api("/cart", { method: "DELETE" }); await refreshCartCount(); renderCart(); }
}

function shoppingListHTML(data) {
  if (!data.total_items) return `<div class="empty"><p>Список пуст.</p></div>`;
  return data.groups.map((g) => `
    <div class="shop-group-title">${esc(g.group)}</div>
    ${g.items.map((it) => {
      const unit = it.unit === "pcs" ? "шт" : it.unit === "ml" ? "мл" : "г";
      return `<label class="shop-item ${it.checked ? "checked" : ""}" data-key="${it.key}">
        <input type="checkbox" ${it.checked ? "checked" : ""} />
        <span class="s-name">${esc(it.name)}${it.check_marker ? '<br><span class="s-check-tag">⚠️ проверь маркировку GF</span>' : ""}</span>
        <span class="s-amt">${it.amount} ${unit}</span>
      </label>`;
    }).join("")}`).join("");
}

// orderId задан — отметки сохраняются на сервере (общие для семьи);
// null — временный список (корзина), отметки только визуальные.
function bindShopChecks(root, orderId) {
  root.querySelectorAll(".shop-item input").forEach((cb) =>
    cb.addEventListener("change", async () => {
      const label = cb.closest(".shop-item");
      label.classList.toggle("checked", cb.checked);
      haptic();
      if (orderId) {
        try {
          await api(`/orders/${orderId}/check`, {
            method: "PATCH",
            body: JSON.stringify({ key: label.dataset.key, checked: cb.checked }),
          });
        } catch (e) { toast("Не удалось сохранить отметку"); }
      }
    }));
}

async function previewShopping() {
  const data = await api("/cart/shopping-list");
  const inner = $("#sheetInner");
  inner.innerHTML = `<div class="detail-body">
    <div class="r-top"><div class="detail-name">🧾 Что купить</div><button class="sheet-close" id="closeSheet" style="position:static">✕</button></div>
    <p class="detail-desc">Одинаковые продукты объединены. Отмечай купленное.</p>
    <div id="shopList">${shoppingListHTML(data)}</div>
  </div>`;
  $("#sheet").classList.remove("hidden");
  document.body.style.overflow = "hidden";
  $("#closeSheet").addEventListener("click", closeSheet);
  bindShopChecks(inner);
}

async function checkout() {
  const note = $("#orderNote") ? $("#orderNote").value.trim() : "";
  const btn = $("#checkout");
  btn.disabled = true;
  btn.textContent = "Оформляем…";
  try {
    const order = await api("/orders", { method: "POST", body: JSON.stringify({ note: note || null }) });
    await refreshCartCount();
    haptic("medium");
    showOrderSuccess(order);
  } catch (e) {
    toast(e.message);
    btn.disabled = false;
    btn.textContent = "✅ Оформить план";
  }
}

function showOrderSuccess(order) {
  const inner = $("#sheetInner");
  inner.innerHTML = `<div class="detail-body" style="text-align:center">
      <div style="font-size:64px;margin:10px 0">🎉</div>
      <div class="detail-name">План №${order.id} готов!</div>
      <p class="detail-desc">${order.items.length} блюд · список покупок собран.<br>Второй в семье получит уведомление в Telegram.</p>
    </div>
    <div class="detail-body" style="padding-top:0">
      <div class="shop-group-title" style="margin-top:4px">🧾 Список покупок</div>
      <div id="shopList">${shoppingListHTML(order.shopping_list)}</div>
    </div>
    <div class="sticky-cta"><button class="btn btn-primary" id="doneOrder">Готово</button></div>`;
  $("#sheet").classList.remove("hidden");
  document.body.style.overflow = "hidden";
  bindShopChecks(inner, order.id);
  $("#doneOrder").addEventListener("click", () => { closeSheet(); switchTab("orders"); });
}

/* ---------- ORDERS ---------- */
async function renderOrders() {
  const v = view();
  $("#searchWrap").classList.add("hidden");
  v.innerHTML = `<div class="loader">Загрузка…</div>`;
  const orders = await api("/orders");
  if (!orders.length) {
    v.innerHTML = `<div class="empty"><div class="em">📦</div><p>Пока нет планов еды.</p></div>`;
    return;
  }
  const stClass = (s) => "st-" + s;
  v.innerHTML = `<div class="section-title">📦 Планы еды</div>` + orders.map((o) => {
    const date = new Date(o.created_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    const who = o.author_role === "wife" ? "👩" : "👨";
    return `<div class="list-row tappable" data-oid="${o.id}">
      <div class="r-top">
        <div><div class="r-name">План №${o.id} ${who}</div>
        <div class="r-sub">${date} · ${o.items.length} блюд · ${esc(o.author)}</div></div>
        <span class="status ${stClass(o.status)}">${o.status_label}</span>
      </div>
      <div class="r-sub" style="margin-top:8px">${o.items.map((i) => esc(i.name)).join(", ")}</div>
      <div class="r-sub" style="margin-top:8px;color:var(--accent);font-weight:600">Открыть · изменить статус · список покупок →</div>
    </div>`;
  }).join("");
  v.querySelectorAll(".list-row").forEach((row) =>
    row.addEventListener("click", () => openOrder(row.dataset.oid)));
}

async function openOrder(id) {
  const o = await api(`/orders/${id}`);
  const inner = $("#sheetInner");
  const statusOpts = [
    ["buy", "🛒 Купить"], ["wait", "⏳ Ожидание"],
    ["cook", "👨‍🍳 Готовить"], ["done", "✅ Выполнено"],
  ].map(([s, l]) => `<button class="status-opt st-opt-${s} ${o.status === s ? "active" : ""}" data-st="${s}">${l}</button>`).join("");

  inner.innerHTML = `<div class="detail-body">
      <div class="r-top"><div class="detail-name">План №${o.id}</div><button class="sheet-close" id="closeSheet" style="position:static">✕</button></div>
      <p class="detail-desc">${o.items.map((i) => `${esc(i.name)} — ${i.servings} порц.`).join("<br>")}</p>
      ${o.note ? `<div class="warn-box" style="background:var(--card);border-color:var(--line);color:var(--muted)">💬 ${esc(o.note)}</div>` : ""}
      <div class="blk"><h4>📋 Изменить статус</h4>
        <div class="status-picker">${statusOpts}</div>
      </div>
      <div class="shop-group-title" style="margin-top:18px">🧾 Список покупок</div>
      <div id="shopList">${shoppingListHTML(o.shopping_list)}</div>
    </div>
    <div class="sticky-cta"><button class="btn btn-primary" id="repeatOrder">🔁 Повторить (в корзину)</button></div>`;
  $("#sheet").classList.remove("hidden");
  document.body.style.overflow = "hidden";
  $("#closeSheet").addEventListener("click", closeSheet);
  bindShopChecks(inner, id);
  inner.querySelectorAll(".status-opt[data-st]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (b.classList.contains("active")) return;
      await api(`/orders/${id}/status`, { method: "PATCH", body: JSON.stringify({ status: b.dataset.st }) });
      haptic("medium");
      toast("Статус обновлён");
      openOrder(id);
    }));
  $("#repeatOrder").addEventListener("click", async () => {
    const res = await api(`/orders/${id}/repeat`, { method: "POST" });
    await refreshCartCount();
    toast(`Добавлено ${res.added} блюд в план 🛒`);
    closeSheet();
    switchTab("cart");
  });
}

/* ---------- PROFILE + STATS ---------- */
function statsHTML(s) {
  const maxD = Math.max(1, ...s.daily.map((d) => d.dishes));
  const bars = s.daily.map((d) => {
    const h = Math.round((d.dishes / maxD) * 100);
    const on = d.dishes > 0;
    return `<div class="bar-col">
      <div class="bar-track"><div class="bar-fill ${on ? "on" : ""}" style="height:${on ? Math.max(h, 8) : 2}%">${on ? `<span class="bar-val">${d.dishes}</span>` : ""}</div></div>
      <div class="bar-lbl">${d.label}</div>
    </div>`;
  }).join("");

  const n = s.nutrition_week;
  const nutri = `<div class="stat-nutri">
    <div><b>${n.kcal}</b><span>ккал</span></div>
    <div><b>${n.protein}</b><span>белок, г</span></div>
    <div><b>${n.carbs}</b><span>углев, г</span></div>
    <div><b>${n.fiber}</b><span>клетч, г</span></div>
  </div>`;

  const top = s.top_dishes.length
    ? `<div class="blk"><h4>🏆 Чаще всего</h4>${s.top_dishes.map((t, i) =>
        `<div class="top-row"><span class="top-rank">${i + 1}</span><span class="top-name">${esc(t.name)}</span><span class="top-cnt">${t.count}×</span></div>`).join("")}</div>`
    : "";

  return `<div class="profile-card stat-card">
      <h3>📊 Статистика</h3>
      <div class="stat-big">
        <div><b>${s.total_orders}</b><span>всего планов</span></div>
        <div><b>${s.total_dishes}</b><span>блюд заказано</span></div>
        <div><b>${s.week_orders}</b><span>за неделю</span></div>
      </div>
      <div class="stat-sub">Блюд по дням (последние 7 дней)</div>
      <div class="bar-chart">${bars}</div>
      <div class="stat-sub">КБЖУ за неделю (сумма по заказам)</div>
      ${nutri}
      ${top}
    </div>`;
}

async function renderProfile() {
  const v = view();
  $("#searchWrap").classList.add("hidden");
  v.innerHTML = `<div class="loader">Загрузка…</div>`;
  const me = state.me || (await api("/me"));
  const [disc, stats] = await Promise.all([api("/disclaimer"), api("/stats").catch(() => null)]);
  v.innerHTML = `
    <div class="profile-card">
      <h3>${me.role_label === "Жена" ? "👩" : "👨"} ${esc(me.first_name || "Профиль")}</h3>
      <div class="r-sub">Роль в семье: ${me.role_label}</div>
      <span class="profile-badge">STRICT GF + ГСД</span>
      <div class="r-sub" style="margin-top:8px">Строго без глютена · контроль углеводов · беременность</div>
    </div>
    ${stats ? statsHTML(stats) : ""}
    <div class="profile-card">
      <h3>ℹ️ О проекте</h3>
      <div class="r-sub" style="line-height:1.5">Семейное меню на двоих. Все блюда — без глютена и с учётом углеводной нагрузки при ГСД. Выбирай блюда, собирай план, получай список покупок.</div>
    </div>
    <div class="disclaimer">${esc(disc.text)}</div>`;
}

/* ---------- RANDOM ("что поесть") ---------- */
async function randomDish() {
  haptic();
  const r = await api("/random");
  if (!r) { toast("Нет блюд"); return; }
  openDish(r.id);
}

/* ---------- tabs ---------- */
const RENDERERS = {
  menu: renderMenu, favorites: renderFavorites, cart: renderCart,
  orders: renderOrders, profile: renderProfile,
};

function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll("#bottomNav button").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === tab));
  view().scrollTop = 0;
  window.scrollTo(0, 0);
  RENDERERS[tab]().catch((e) => {
    view().innerHTML = `<div class="empty"><div class="em">⚠️</div><p>${esc(e.message)}</p></div>`;
  });
}

async function refreshCartCount() {
  try {
    const cart = await api("/cart");
    state.cartCount = cart.count;
    const badge = $("#cartBadge");
    badge.textContent = cart.count;
    badge.classList.toggle("hidden", cart.count === 0);
  } catch (e) {}
}

/* ---------- init ---------- */
let searchTimer = null;
$("#search").addEventListener("input", (e) => {
  state.query = e.target.value.trim();
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { if (state.tab === "menu") renderMenu(); }, 300);
});
$("#dice").addEventListener("click", randomDish);
document.querySelectorAll("#bottomNav button").forEach((b) =>
  b.addEventListener("click", () => switchTab(b.dataset.tab)));

(async function boot() {
  try {
    state.me = await api("/me");
    $("#hello").textContent = `Привет, ${state.me.first_name || "друг"}! 👋`;
  } catch (e) {
    $("#hello").textContent = "Привет! 👋";
  }
  state._images = await api("/images").catch(() => ({}));
  await refreshCartCount();
  switchTab("menu");
})();
