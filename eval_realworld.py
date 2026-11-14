#!/usr/bin/env python3
"""食堂实拍测试集评估 —— 回答「这模型在真实食堂里到底准不准」

背景：models/dish-cls.onnx 的 83.92% 是 val 集成绩，而 val 与训练集同分布
（都是网络美食图：精致摆盘、专业打光、白瓷盘）。食堂实拍是不锈钢餐格 + 顶灯
+ 一勺份量，域差异很大，真实准确率一定更低。这个脚本就是来量这个差距的。

用法：
    .venv/bin/python eval_realworld.py --data /path/to/实拍图

数据格式（按菜名分文件夹，文件夹名必须是菜名）：
    实拍图/
    ├── 麻婆豆腐/
    │   ├── IMG_001.jpg
    │   └── IMG_002.jpg
    └── 炒青菜/
        └── IMG_003.jpg

判定标准（来自 README-POC结果.md）：
    top-1 >= 70%  → 可用，靠 top-3 + 人工确认兜住
    top-1 50-70%  → 需要采几百张实拍图微调
    top-1 <  50%  → 网络美食图帮不上忙，得完全靠自建数据
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = ROOT / "models" / "dish-cls.onnx"
CLASSES_JSON = ROOT / "models" / "classes.json"
KCAL_JSON = ROOT / "demo_dishes.json"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def scan(data_dir, valid_names):
    """扫描按菜名分文件夹的实拍图，返回 [(真值菜名, 图片路径)]"""
    items, unknown = [], set()
    for cls_dir in sorted(Path(data_dir).iterdir()):
        if not cls_dir.is_dir() or cls_dir.name.startswith("."):
            continue
        name = cls_dir.name
        if valid_names and name not in valid_names:
            unknown.add(name)
            continue
        imgs = [p for p in sorted(cls_dir.iterdir()) if p.suffix.lower() in IMG_EXTS]
        items.extend((name, p) for p in imgs)
    return items, unknown


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="实拍图根目录（按菜名分文件夹）")
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    ap.add_argument("--out", default=str(ROOT / "eval_realworld_report.md"))
    args = ap.parse_args()

    if not Path(args.data).is_dir():
        sys.exit(f"找不到数据目录：{args.data}")

    classes = load_json(CLASSES_JSON)
    kcal = load_json(KCAL_JSON)
    items, unknown = scan(args.data, set(classes))

    if not items:
        sys.exit(
            f"{args.data} 下没有可用的图片。\n"
            f"要求：按菜名分文件夹，且菜名必须是模型支持的 {len(classes)} 类之一。\n"
            f"支持的菜名：{'、'.join(classes)}"
            + (f"\n\n（跳过了不认识的目录：{'、'.join(sorted(unknown))}）" if unknown else "")
        )

    from ultralytics import YOLO

    print(f"加载模型 {args.model} ...")
    model = YOLO(args.model, task="classify")
    print(f"共 {len(items)} 张，开始推理...\n")

    rows, per_cls = [], defaultdict(lambda: {"n": 0, "t1": 0, "t3": 0})
    conf_when_right, conf_when_wrong = [], []

    for i, (truth, img) in enumerate(items, 1):
        res = model(str(img), verbose=False)[0]
        probs = res.probs
        # 注意：Ultralytics 的 Probs 只有 top1 / top5，没有 top3，从 top5 取前 3
        top5_idx = list(probs.top5)
        top1 = classes[probs.top1]
        top3 = [classes[j] for j in top5_idx[:3]]
        conf = float(probs.top1conf)
        ok = top1 == truth
        hit3 = truth in top3

        per_cls[truth]["n"] += 1
        per_cls[truth]["t1"] += int(ok)
        per_cls[truth]["t3"] += int(hit3)
        (conf_when_right if ok else conf_when_wrong).append(conf)

        rows.append({
            "图片": str(img),
            "真值": truth,
            "top1": top1,
            "置信度": round(conf, 4),
            "top1命中": "✅" if ok else "❌",
            "top3命中": "✅" if hit3 else "❌",
            "top2": top3[1] if len(top3) > 1 else "",
            "top3": top3[2] if len(top3) > 2 else "",
            "热量偏差": (kcal.get(top1, 0) - kcal.get(truth, 0)) if not ok else 0,
        })

        if i % 10 == 0 or i == len(items):
            print(f"  {i}/{len(items)}", end="\r")

    print()
    n = len(items)
    t1 = sum(r["top1命中"] == "✅" for r in rows)
    t3 = sum(r["top3命中"] == "✅" for r in rows)
    p1, p3 = t1 / n * 100, t3 / n * 100

    # ── 判定 ──
    if p1 >= 70:
        verdict = "✅ 可用 —— 靠 top-3 + 人工确认兜住，可以直接上产品"
    elif p1 >= 50:
        verdict = "⚠️ 需要微调 —— 采几百张实拍图做微调再上"
    else:
        verdict = "❌ 网络美食图帮不上忙 —— 得完全靠自建实拍数据重训"

    # ── 混淆：每类最常被认成什么 ──
    confuse = defaultdict(Counter)
    for r in rows:
        if r["top1命中"] == "❌":
            confuse[r["真值"]][r["top1"]] += 1

    # ── 认错的热量代价 ──
    diffs = [abs(r["热量偏差"]) for r in rows if r["top1命中"] == "❌"]
    avg_diff = sum(diffs) / len(diffs) if diffs else 0
    worst = sorted([r for r in rows if r["top1命中"] == "❌"],
                   key=lambda r: -abs(r["热量偏差"]))[:5]

    # ── 报告 ──
    L = []
    L.append("# 食堂实拍评估报告\n")
    L.append(f"- 模型：`{Path(args.model).name}`")
    L.append(f"- 数据：`{args.data}`")
    L.append(f"- 图片：{n} 张 / {len(per_cls)} 类\n")
    L.append("## 总体\n")
    L.append("| 指标 | 值 |")
    L.append("| --- | --- |")
    L.append(f"| **top-1** | **{p1:.2f}%**（{t1}/{n}） |")
    L.append(f"| top-3 | {p3:.2f}%（{t3}/{n}） |")
    if conf_when_right:
        L.append(f"| 答对时平均置信度 | {sum(conf_when_right)/len(conf_when_right):.3f} |")
    if conf_when_wrong:
        L.append(f"| **答错时平均置信度** | **{sum(conf_when_wrong)/len(conf_when_wrong):.3f}** |")
    L.append(f"| 认错时平均热量偏差 | {avg_diff:.0f} kcal |")
    L.append("")
    L.append(f"## 判定\n\n{verdict}\n")
    L.append("> 注意答错时的置信度。如果它和答对时一样高，说明**置信度不可信**，")
    L.append("> 绝不能按置信度自动采纳，必须 top-3 + 人工确认。\n")

    L.append("## 每类表现\n")
    L.append("| 菜名 | 张数 | top-1 | top-3 | 最常被认成 |")
    L.append("| --- | --- | --- | --- | --- |")
    for name in sorted(per_cls, key=lambda k: per_cls[k]["t1"] / per_cls[k]["n"]):
        s = per_cls[name]
        wrong = confuse.get(name)
        worst_other = f"{wrong.most_common(1)[0][0]} ×{wrong.most_common(1)[0][1]}" if wrong else "—"
        L.append(f"| {name} | {s['n']} | {s['t1']/s['n']*100:.0f}% | "
                 f"{s['t3']/s['n']*100:.0f}% | {worst_other} |")

    if worst:
        L.append("\n## 代价最大的错误（热量偏差 Top 5）\n")
        L.append("| 真值 | 认成 | 热量差 |")
        L.append("| --- | --- | --- |")
        for r in worst:
            L.append(f"| {r['真值']} | {r['top1']} | {r['热量偏差']:+d} kcal |")

    out_md = Path(args.out)
    out_md.write_text("\n".join(L), encoding="utf-8")
    out_csv = out_md.with_suffix(".csv")
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("\n".join(L))
    print(f"\n报告已写入：\n  {out_md}\n  {out_csv}")
    return 0 if p1 >= 50 else 1


if __name__ == "__main__":
    sys.exit(main())
