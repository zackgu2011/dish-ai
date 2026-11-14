# 菜品识别网页版验收测试（playwright + 本机 Chrome channel）
# 用法：先在项目根起 python3 -m http.server 5200，再跑本脚本
import glob
import json
import shutil
from playwright.sync_api import sync_playwright

ROOT = "http://127.0.0.1:5200"
SRC = "/Users/zackgu/Projects/Evergrande Weight Loss Group/dish-ai/testimg/mapo-tofu.jpg"
TMP = "/tmp/rz_test_img.jpg"
NCLASS = len(json.load(open("/Users/zackgu/Projects/Evergrande Weight Loss Group/dish-ai/models/classes.json")))
shutil.copy(SRC, TMP)

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


READY = "document.querySelector('#rzStatus').className.includes('rz-ok')"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)

    # ── 场景 A：全新档案（localStorage 为空）→ 空库提示 + 周末提示 + 模型能加载 ──
    ctx1 = browser.new_context()
    pg1 = ctx1.new_page()
    errs1 = []
    pg1.on("pageerror", lambda e: errs1.append(str(e)))
    pg1.goto(ROOT + "/dish-ai/recognize.html", wait_until="domcontentloaded")
    pg1.wait_for_timeout(600)
    check("A1 空库提示出现", pg1.locator("#rzDbBanner").is_visible())
    check("A2 提示带选菜台链接", pg1.locator("#rzDbBanner a").first.get_attribute("href") == "../app.html")
    check("A3 今天是周末 → 菜单行提示", "周末" in pg1.locator("#rzMenuLine").inner_text(),
          pg1.locator("#rzMenuLine").inner_text())
    pg1.wait_for_function(READY, timeout=90000)
    check("A4 空库也能加载模型", True)
    check(f"A5 支持 {NCLASS} 道菜文案", f"{NCLASS} 道菜" in pg1.locator("#rzCaps").inner_text(),
          pg1.locator("#rzCaps").inner_text())
    check(f"A6 菜名 chips={NCLASS}", pg1.locator("#rzChips .rz-chip").count() == NCLASS)
    check("A7 空库无报错", not errs1, "; ".join(errs1[:3]))
    pg1.close()
    ctx1.close()

    # ── 场景 B：先开 app.html 入库，再走完整识别流程 ──
    ctx2 = browser.new_context()
    pg = ctx2.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(ROOT + "/app.html", wait_until="domcontentloaded")
    pg.wait_for_function(
        "JSON.parse(localStorage.getItem('hdfz:planner:dishes:v1')||'[]').length > 0", timeout=30000)
    n = pg.evaluate("JSON.parse(localStorage.getItem('hdfz:planner:dishes:v1')).length")
    check("B1 菜品库已入库", n > 300, str(n))

    pg.goto(ROOT + "/dish-ai/recognize.html?date=2026-09-14&meal=lunch", wait_until="domcontentloaded")
    check("B2 有库 → 无空库提示", not pg.locator("#rzDbBanner").is_visible())
    pg.wait_for_function(READY, timeout=90000)
    ml = pg.locator("#rzMenuLine").inner_text()
    check("B3 菜单行显示周一/第1周", ("9月14日 周一" in ml and "第1周" in ml), ml)

    pg.set_input_files("#rzFileAlbum", TMP)
    pg.wait_for_selector("#rzResults .rz-row", timeout=30000)
    row0 = pg.locator("#rzResults .rz-row").nth(0)
    check("B4 出 top-3", pg.locator("#rzResults .rz-row").count() == 3)
    check("B5 top1=麻婆豆腐", "麻婆豆腐" in row0.locator(".rz-name").inner_text(),
          row0.locator(".rz-name").inner_text())
    pct = row0.locator(".rz-pct").inner_text()
    check("B6 置信度>90%（未被二次 softmax）", float(pct.rstrip("%")) > 90, pct)
    check("B7 有供应标记", "今天" in row0.locator(".rz-tag").inner_text(),
          row0.locator(".rz-tag").inner_text())
    nut = row0.locator(".rz-nut").inner_text()
    check("B8 显示热量/蛋白", "115" in nut and "蛋白" in nut, nut)
    add = row0.locator(".rz-add")
    check("B9 按钮文案=加入午餐", "加入午餐" in add.inner_text(), add.inner_text())

    add.click()
    pg.wait_for_timeout(250)
    check("B10 点击后反馈 ×1", "×1" in add.inner_text(), add.inner_text())
    check("B11 当日合计 115", "115" in pg.locator("#rzDayTotal").inner_text(),
          pg.locator("#rzDayTotal").inner_text())
    add.click()
    pg.wait_for_timeout(250)
    check("B12 再点 → 合计 230", "230" in pg.locator("#rzDayTotal").inner_text(),
          pg.locator("#rzDayTotal").inner_text())
    cart = pg.evaluate("JSON.parse(localStorage.getItem('hdfz:planner:cart:v1')||'{}')")
    entry = (cart.get("2026-09-14") or {}).get("lunch", [])
    check("B13 cart 写入 qty=2", len(entry) == 1 and entry[0].get("qty") == 2,
          json.dumps(entry, ensure_ascii=False))
    check("B14 toast 出现过", pg.locator("#rzToast").is_visible())

    # 换餐次 → 用同一张图重算
    pg.locator('#rzMealTabs [data-meal="dinner"]').click()
    pg.wait_for_selector("#rzResults .rz-row", timeout=30000)
    add2 = pg.locator("#rzResults .rz-row").nth(0).locator(".rz-add")
    check("B15 换晚餐后按钮更新", "加入晚餐" in add2.inner_text(), add2.inner_text())

    # 回午餐，验证「本次已加」托盘
    pg.locator('#rzMealTabs [data-meal="lunch"]').click()
    pg.wait_for_selector("#rzResults .rz-row", timeout=30000)
    tray = pg.locator("#rzTrayCard")
    check("B19 托盘可见", tray.is_visible())
    check("B20 托盘标题带餐次", "本次已加 · 午餐" in pg.locator("#rzTrayTitle").inner_text(),
          pg.locator("#rzTrayTitle").inner_text())
    check("B21 托盘条目 ×2", "×2" in pg.locator("#rzTrayList").inner_text(),
          pg.locator("#rzTrayList").inner_text())
    pg.locator("#rzTrayList [data-op='minus']").click()
    pg.wait_for_timeout(200)
    check("B22 托盘 −1 后 ×1", "×1" in pg.locator("#rzTrayList").inner_text())
    check("B23 合计回落 115", "115" in pg.locator("#rzDayTotal").inner_text(),
          pg.locator("#rzDayTotal").inner_text())
    pg.locator("#rzTrayList [data-op='minus']").click()
    pg.wait_for_timeout(200)
    check("B24 减到 0 托盘隐藏", not tray.is_visible())
    pg.locator("#rzResults .rz-row").nth(0).locator(".rz-add").click()
    pg.wait_for_timeout(200)
    check("B25 再加后托盘复现 ×1", tray.is_visible() and "×1" in pg.locator("#rzTrayList").inner_text())
    pg.locator("#rzTrayList [data-op='del']").click()
    pg.wait_for_timeout(200)
    check("B26 ✕ 移除后托盘隐藏", not tray.is_visible())
    addbtn0 = pg.locator("#rzResults .rz-row").nth(0).locator(".rz-add")
    check("B27 移除后按钮复位", "加入午餐" in addbtn0.inner_text(), addbtn0.inner_text())
    addbtn0.click()
    addbtn0.click()
    pg.wait_for_timeout(200)

    # ── 纠错反馈闭环 ──
    fbcard = pg.locator("#rzFbCard")
    check("D0 无记录时反馈卡隐藏", not fbcard.is_visible())
    pg.set_input_files("#rzFileAlbum", TMP)
    pg.wait_for_selector("#rzResults .rz-row", timeout=30000)
    pg.wait_for_function("document.querySelector('#rzInfer').hidden === true", timeout=30000)
    pg.locator("#rzResults .rz-row").nth(1).locator(".rz-add").click()
    pg.wait_for_timeout(300)
    check("D1 加非top1 → implicit 记录", fbcard.is_visible() and pg.locator("#rzFbCount").inner_text() == "1",
          pg.locator("#rzFbCount").inner_text())
    pg.locator("#rzFbOpen").click()
    check(f"D2 纠错 chips={NCLASS}", pg.locator("#rzFbChips button").count() == NCLASS)
    pg.locator("#rzFbChips button", has_text="麻婆豆腐").first.click()
    pg.wait_for_timeout(250)
    check("D3 explicit 纠正 → 2 条", pg.locator("#rzFbCount").inner_text() == "2",
          pg.locator("#rzFbCount").inner_text())
    pg.reload(wait_until="domcontentloaded")
    pg.wait_for_function("document.querySelector('#rzStatus').className.includes('rz-ok')", timeout=90000)
    check("D4 刷新后记录持久", pg.locator("#rzFbCount").inner_text() == "2",
          pg.locator("#rzFbCount").inner_text())
    with pg.expect_download() as dl:
        pg.locator("#rzFbExport").click()
    payload = json.load(open(dl.value.path()))
    check("D5 导出 json 结构", payload.get("app") == "hdfz-recognize-feedback"
          and len(payload.get("records", [])) == 2,
          payload.get("app"))
    check("D6 记录带 JPEG 缩略图", all(
        r.get("img") and str(r["img"]).startswith("data:image/jpeg") for r in payload["records"]))
    check("D7 记录带 top3+答案", bool(payload["records"][0].get("top3"))
          and bool(payload["records"][0].get("correct")))
    pg.on("dialog", lambda dlg: dlg.accept())
    pg.locator("#rzFbClear").click()
    pg.wait_for_timeout(300)
    check("D8 清空后卡片隐藏", not fbcard.is_visible())

    # ── 跨页验收：回 app.html，翻到 09-14，看午餐区有没有这道菜 ──
    from datetime import date as _date
    pg.goto(ROOT + "/app.html", wait_until="domcontentloaded")
    pg.wait_for_timeout(1200)
    delta = (_date(2026, 9, 14) - _date.today()).days
    btn = "[data-date-next]" if delta >= 0 else "[data-date-prev]"
    for _ in range(abs(delta)):
        pg.locator(btn).click()
        pg.wait_for_timeout(150)
    pg.wait_for_timeout(500)
    label = pg.locator("[data-date-label]").inner_text()
    check("B16 app 翻到 9月14日", "9月14日" in label, label)
    lunch_zone = pg.locator('[data-meal-zone="lunch"]').inner_text()
    check("B17 app 午餐区看到麻婆豆腐 ×2", "麻婆豆腐" in lunch_zone, lunch_zone[:200])
    check("B18 全程无 JS 报错", not errs, "; ".join(errs[:3]))

    # ── 截图（桌面 + 手机） ──
    shot = ctx2.new_page()
    shot.set_viewport_size({"width": 1280, "height": 900})
    shot.goto(ROOT + "/dish-ai/recognize.html?date=2026-09-14&meal=lunch", wait_until="domcontentloaded")
    shot.wait_for_function(READY, timeout=90000)
    shot.set_input_files("#rzFileAlbum", TMP)
    shot.wait_for_selector("#rzResults .rz-row", timeout=30000)
    shot.wait_for_function("document.querySelector('#rzInfer').hidden === true", timeout=30000)
    shot.wait_for_timeout(600)
    shot.screenshot(path="/tmp/rz_desktop.png", full_page=True)
    shot.set_viewport_size({"width": 390, "height": 844})
    shot.wait_for_timeout(500)
    shot.screenshot(path="/tmp/rz_mobile.png", full_page=True)
    browser.close()

fails = 0
print("\n===== 验收结果 =====")
for name, ok, detail in results:
    line = ("PASS " if ok else "FAIL ") + name
    if detail and not ok:
        line += "  | " + str(detail)
    print(line)
    fails += 0 if ok else 1
print(f"通过 {len(results) - fails}/{len(results)}")
raise SystemExit(1 if fails else 0)
