# 补充验收：✅ 状态截图 / file:// 报错 / 断网识别
import glob
import json
import shutil
from playwright.sync_api import sync_playwright

ROOT = "http://127.0.0.1:5200"
CLASS_NAMES = ["农家小炒肉", "宫保鸡丁", "家常豆腐", "炒青菜", "糖醋排骨",
               "红烧带鱼", "红烧牛肉", "酸辣土豆丝", "香菇青菜", "麻婆豆腐"]
TARGET = "麻婆豆腐"  # 夹具图 dish-ai/testimg/mapo-tofu.jpg
MENU_ANCHOR = "2026-09-07"  # 锚点周一是第2周

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def parse_key(k):
    y, m, d = map(int, k.split("-"))
    return datetime_date(y, m, d)


from datetime import date as datetime_date

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context()
    pg = ctx.new_page()

    pg.goto(ROOT + "/app.html", wait_until="domcontentloaded")
    pg.wait_for_function(
        "JSON.parse(localStorage.getItem('hdfz:planner:dishes:v1')||'[]').length > 0", timeout=30000)

    # ── C1: 找一个 10 类菜在当餐菜单里的 (日期, 餐次) ──
    recs = pg.evaluate("JSON.parse(localStorage.getItem('hdfz:planner:menu:v1')).records")
    hit = None
    d = parse_key("2026-09-07")
    from datetime import timedelta
    for _ in range(40):
        if d.weekday() < 5:
            mon = d - timedelta(days=d.weekday())
            weeks = round((mon - parse_key(MENU_ANCHOR)).days / 7)
            wk = 2 if ((weeks % 2) + 2) % 2 == 0 else 1
            key = f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
            for meal in ("breakfast", "lunch", "dinner"):
                # days 存的是 getDay() 编号（周一=1…周五=5），Python 用 isoweekday() 对齐
                names = {r[0] for r in recs if r[3] == wk and r[2] == meal and str(d.isoweekday()) in str(r[4])}
                if TARGET in names:
                    hit = (key, meal, TARGET)
                    break
        if hit:
            break
        d += timedelta(days=1)
    check("C1 找到 ✅ 场景", bool(hit), str(hit))
    print("C1 场景:", hit)

    if hit:
        date_key, meal, dish_name = hit
        src = "/Users/zackgu/Projects/Evergrande Weight Loss Group/dish-ai/testimg/mapo-tofu.jpg"
        tmp = "/tmp/rz_test_img2.jpg"
        shutil.copy(src, tmp)
        shot = ctx.new_page()
        shot.set_viewport_size({"width": 1280, "height": 900})
        shot.goto(ROOT + f"/dish-ai/recognize.html?date={date_key}&meal={meal}", wait_until="domcontentloaded")
        shot.wait_for_function("document.querySelector('#rzStatus').className.includes('rz-ok')", timeout=90000)
        shot.set_input_files("#rzFileAlbum", tmp)
        shot.wait_for_selector("#rzResults .rz-row", timeout=30000)
        shot.wait_for_function("document.querySelector('#rzInfer').hidden === true", timeout=30000)
        row0 = shot.locator("#rzResults .rz-row").nth(0)
        tag = row0.locator(".rz-tag").inner_text()
        check("C2 top1 tag 为「今天这餐有」", "今天这餐有" in tag, tag)
        check("C3 top1 即目标菜", dish_name in row0.locator(".rz-name").inner_text(),
              row0.locator(".rz-name").inner_text())
        nut0 = row0.locator(".rz-nut").inner_text()
        check("C2b 在菜单行也有热量（无 undefined）", "undefined" not in nut0 and "kcal" in nut0, nut0)
        shot.wait_for_timeout(500)
        shot.screenshot(path="/tmp/rz_green.png", full_page=True)
        shot.close()

    # ── C4: 断网识别（READY 后拦截一切请求） ──
    pg2 = ctx.new_page()
    pg2.goto(ROOT + "/dish-ai/recognize.html", wait_until="domcontentloaded")
    pg2.wait_for_function("document.querySelector('#rzStatus').className.includes('rz-ok')", timeout=90000)
    pg2.route("**/*", lambda route: route.abort())
    pg2.set_input_files("#rzFileAlbum", "/tmp/rz_test_img.jpg")
    pg2.wait_for_selector("#rzResults .rz-row", timeout=30000)
    top = pg2.locator("#rzResults .rz-row").nth(0).locator(".rz-name").inner_text()
    check("C5 断网后仍能识别", "麻婆豆腐" in top, top)
    pg2.close()

    # ── C6: file:// 打开 → 友好报错不白屏 ──
    pg3 = browser.new_page()
    pg3.goto("file:///Users/zackgu/Projects/Evergrande Weight Loss Group/dish-ai/recognize.html")
    pg3.wait_for_timeout(2500)
    status = pg3.locator("#rzStatus").inner_text()
    check("C7 file:// 显示加载失败提示", ("失败" in status or "错误" in status or "没有加载" in status), status)
    body_visible = pg3.locator("h1").is_visible()
    check("C8 file:// 页面结构仍在（不白屏）", body_visible)
    pg3.close()

    browser.close()

fails = 0
print("\n===== 补充验收 =====")
for name, ok, detail in results:
    line = ("PASS " if ok else "FAIL ") + name
    if detail and not ok:
        line += "  | " + str(detail)
    print(line)
    fails += 0 if ok else 1
print(f"通过 {len(results) - fails}/{len(results)}")
raise SystemExit(1 if fails else 0)
