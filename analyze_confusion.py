"""混淆危害分析：模型认错时，实际热量差了多少？

关注点不是 top-1，而是「认错之后用户看到的热量偏了多少」——
家常豆腐和麻婆豆腐都是 115 kcal，认混了无所谓；
认错成热量差 150 kcal 的菜，才是真坑。
"""
import glob
import json
import os
from collections import Counter

from ultralytics import YOLO

HERE = os.path.dirname(os.path.abspath(__file__))
VAL = os.path.join(HERE, "data", "cls_poc31", "val")
KCAL = json.load(open(os.path.join(HERE, "demo_dishes.json"), encoding="utf-8"))

m = YOLO(os.path.join(HERE, "runs/cls/poc31/weights/best.pt"))
names = [m.names[i] for i in range(len(m.names))]

pairs = Counter()
per_class = Counter()
per_class_err = Counter()
total = 0
err = 0

for cls in sorted(os.listdir(VAL)):
    d = os.path.join(VAL, cls)
    if not os.path.isdir(d):
        continue
    files = sorted(glob.glob(os.path.join(d, "*.jpg")))[:40]
    if not files:
        continue
    for r in m.predict(files, imgsz=224, device="mps", verbose=False):
        pred = names[int(r.probs.top1)]
        total += 1
        per_class[cls] += 1
        if pred != cls:
            err += 1
            per_class_err[cls] += 1
            pairs[(cls, pred)] += 1

print(f"抽样 {total} 张（每类最多 40），top-1 = {(1 - err / total) * 100:.2f}%")
print(f"错误 {err} 张\n")

rows = []
for (t, p), n in pairs.most_common():
    kt, kp = KCAL.get(t), KCAL.get(p)
    diff = abs(kt - kp) if (kt is not None and kp is not None) else None
    rows.append((n, diff if diff is not None else -1, t, kt, p, kp))

print("=== 高频混淆对（按次数）===")
for n, diff, t, kt, p, kp in rows[:12]:
    flag = "🔴 热量差大" if diff >= 80 else ("🟡 中等" if diff >= 40 else "🟢 基本无害")
    print(f"  {t}({kt}) → {p}({kp})   差 {diff} kcal   ×{n}   {flag}")

print("\n=== 按「单次错误的热量偏差」排序（最坑的混淆）===")
for n, diff, t, kt, p, kp in sorted(rows, key=lambda x: -x[1])[:8]:
    print(f"  差 {diff:>4} kcal   {t}({kt}) → {p}({kp})   ×{n}")

print("\n=== 最容易认错的菜（错误率）===")
for cls, n in per_class.most_common():
    e = per_class_err[cls]
    if e:
        print(f"  {cls:8s} 错 {e}/{n}  ({e / n * 100:.0f}%)")

harm = sum(d for _, d, *_ in rows if d > 0)
print(f"\n认错时平均热量偏差: {harm / max(err, 1):.0f} kcal")
