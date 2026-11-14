/* 菜品识别模块 · 独立文件，不依赖 planner.js
   与 planner.js 通过 localStorage 共享数据（菜品库 / 菜单 / 购物车），键名与结构保持一致。
   推理完全在浏览器本地完成，图片不上传。

   用法：
     await DishRecognizer.load();                       // 懒加载模型 + 类别表
     const res = await DishRecognizer.predict(imgEl);   // → [{name, prob, onMenu, dish}]
     DishRecognizer.addToCart(dish.id, 'lunch', dateKey);
*/
(function () {
  'use strict';

  const KEY_DISHES = 'hdfz:planner:dishes:v1';
  const KEY_CART = 'hdfz:planner:cart:v1';
  const KEY_MENU = 'hdfz:planner:menu:v1';
  const MENU_ANCHOR = '2026-09-07';
  const MEALS = ['breakfast', 'lunch', 'dinner'];
  const MEAL_LABEL = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' };

  let MODEL_URL = 'models/dish-cls.onnx';
  let CLASSES_URL = 'models/classes.json';
  let ORT_CDN = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/';

  let session = null;
  let classes = null;
  let ready = false;

  /* ---------- 基础工具 ---------- */
  const readLS = (key, fallback) => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (err) {
      return fallback;
    }
  };
  const writeLS = (key, value) => {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (err) { /* 隐私模式降级 */ }
  };
  const keyOf = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const parseKey = (key) => {
    const [y, m, d] = key.split('-').map(Number);
    return new Date(y, m - 1, d);
  };
  const dishes = () => readLS(KEY_DISHES, []);
  const menuRecords = () => {
    const raw = readLS(KEY_MENU, null);
    if (!raw || !Array.isArray(raw.records)) return [];
    return raw.records.map((r) => ({
      name: r[0], cat: r[1], meal: r[2], wk: r[3], days: String(r[4]).split('').map(Number),
    }));
  };

  /* ---------- 当餐菜单（复刻 planner.js 的 dayMenuFor） ---------- */
  function dayMenuFor(dateKey) {
    const d = parseKey(dateKey);
    const dow = d.getDay();
    if (dow === 0 || dow === 6) return null;
    const monday = parseKey(dateKey);
    monday.setDate(monday.getDate() - (dow - 1));
    const anchor = parseKey(MENU_ANCHOR);
    const weeks = Math.round((monday.getTime() - anchor.getTime()) / 604800000);
    const wk = ((weeks % 2) + 2) % 2 === 0 ? 2 : 1;
    const index = new Map(dishes().map((x) => [x.name + '|' + x.cat, x.id]));
    const out = { wk, breakfast: [], lunch: [], dinner: [] };
    const used = new Set();
    for (const rec of menuRecords()) {
      if (rec.wk !== wk || !rec.days.includes(dow)) continue;
      const id = index.get(rec.name + '|' + rec.cat);
      if (!id) continue;
      const dedupe = rec.meal + ':' + id;
      if (used.has(dedupe)) continue;
      used.add(dedupe);
      out[rec.meal].push({ id, cat: rec.cat, name: rec.name });
    }
    return out;
  }

  /* ---------- 模型 ---------- */
  async function load(onProgress) {
    if (ready) return true;
    if (typeof ort === 'undefined') throw new Error('onnxruntime-web 未加载');
    if (onProgress) onProgress('加载类别表…');
    const res = await fetch(CLASSES_URL);
    if (!res.ok) throw new Error('读不到 ' + CLASSES_URL);
    classes = await res.json();
    if (onProgress) onProgress(`加载模型（${classes.length} 类）…`);
    ort.env.wasm.wasmPaths = ORT_CDN;
    session = await ort.InferenceSession.create(MODEL_URL, { executionProviders: ['wasm'] });
    ready = true;
    if (onProgress) onProgress('模型就绪');
    return true;
  }

  function toTensor(src, size) {
    const cv = document.createElement('canvas');
    cv.width = size; cv.height = size;
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(src, 0, 0, size, size);
    const { data } = ctx.getImageData(0, 0, size, size);
    const n = size * size;
    const arr = new Float32Array(n * 3);
    for (let i = 0; i < n; i += 1) {
      arr[i] = data[i * 4] / 255;
      arr[n + i] = data[i * 4 + 1] / 255;
      arr[n * 2 + i] = data[i * 4 + 2] / 255;
    }
    return new ort.Tensor('float32', arr, [1, 3, size, size]);
  }

  /* Ultralytics 分类 ONNX 输出已经是概率（和为 1），不要二次 softmax */
  function toProbs(vals) {
    const sum = vals.reduce((a, b) => a + b, 0);
    const isProb = Math.abs(sum - 1) < 0.01 && Math.min.apply(null, vals) >= 0;
    if (isProb) return vals;
    const mx = Math.max.apply(null, vals);
    const ex = vals.map((v) => Math.exp(v - mx));
    const s = ex.reduce((a, b) => a + b, 0);
    return ex.map((v) => v / s);
  }

  async function predictRaw(src, size) {
    const out = await session.run({ images: toTensor(src, size || 224) });
    return toProbs(Array.from(out[Object.keys(out)[0]].data));
  }

  /* 菜名 → 菜品库里的条目；优先取当餐菜单里的那个 */
  function matchDish(name, meal, dateKey) {
    const menu = dayMenuFor(dateKey);
    const inMeal = (menu && menu[meal]) || [];
    const byName = (list) => list.filter((x) => x.name === name);
    const hit = byName(inMeal)[0]
      || dishes().find((d) => d.name === name)
      || dishes().find((d) => d.name && name && (d.name.includes(name) || name.includes(d.name)));
    return hit || null;
  }

  /* 识别：返回 top-N，带「今天这餐有没有」标记与菜品库信息 */
  async function predict(src, opts) {
    const o = opts || {};
    const dateKey = o.date || keyOf(new Date());
    const meal = o.meal || currentMeal();
    const topN = o.topN || 3;
    const menu = dayMenuFor(dateKey);
    const menuNames = new Set(((menu && menu[meal]) || []).map((x) => x.name));
    const probs = await predictRaw(src, o.size);
    const ranked = probs.map((p, i) => ({ i, p })).sort((a, b) => b.p - a.p).slice(0, topN);
    return ranked.map(({ i, p }) => {
      const name = classes[i];
      const dish = matchDish(name, meal, dateKey);
      return {
        name,
        prob: p,
        /* 必须是布尔值：dish 为 null 时 `dish && ...` 会返回 null，UI 上判断会出错 */
        onMenu: Boolean(menuNames.has(name) || (dish && menuNames.has(dish.name))),
        dish,
        kcal: dish ? dish.kcalS : null,
        protein: dish ? dish.pS : null,
      };
    });
  }

  const currentMeal = () => {
    const h = new Date().getHours();
    return h < 10 ? 'breakfast' : h < 16 ? 'lunch' : 'dinner';
  };

  /* ---------- 写购物车（与 planner.js 的 commitAdd 行为一致） ---------- */
  function addToCart(dishId, meal, dateKey) {
    const date = dateKey || keyOf(new Date());
    const cart = readLS(KEY_CART, {}) || {};
    const day = cart[date] && typeof cart[date] === 'object'
      ? cart[date] : { breakfast: [], lunch: [], dinner: [] };
    if (!Array.isArray(day.breakfast)) day.breakfast = [];
    if (!Array.isArray(day.lunch)) day.lunch = [];
    if (!Array.isArray(day.dinner)) day.dinner = [];
    const hit = day[meal].find((i) => i.id === dishId);
    if (hit) hit.qty += 1;
    else day[meal].push({ id: dishId, qty: 1 });
    cart[date] = day;
    writeLS(KEY_CART, cart);
    return day[meal].find((i) => i.id === dishId);
  }

  function dayTotal(dateKey) {
    const cart = readLS(KEY_CART, {}) || {};
    const day = cart[dateKey];
    if (!day) return 0;
    const map = new Map(dishes().map((d) => [d.id, d]));
    return MEALS.reduce((sum, m) => sum + (day[m] || []).reduce((s, it) => {
      const d = map.get(it.id);
      return s + (d ? (d.kcalS || 0) * it.qty : 0);
    }, 0), 0);
  }

  window.DishRecognizer = {
    load, predict, predictRaw, addToCart, dayMenuFor, matchDish, dayTotal,
    currentMeal, keyOf, dishes,
    MEALS, MEAL_LABEL,
    isReady: () => ready,
    classList: () => classes || [],
    configure: (opts) => {
      if (opts.model) MODEL_URL = opts.model;
      if (opts.classes) CLASSES_URL = opts.classes;
      if (opts.ortCdn) ORT_CDN = opts.ortCdn;
    },
  };
})();
