"""菜品分类 POC 训练：ChineseFoodNet 10 类 → YOLO 分类模型 → 导出 ONNX

用法：
    .venv/bin/python train_poc.py                 # 默认 50 epoch / 224px / MPS
    .venv/bin/python train_poc.py --epochs 30     # 快速验证
"""
import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "cls_poc"  # 可由 --data 覆盖

# YOLO26 是当前主线，老版本 ultralytics 没有该权重时回退
MODEL_CANDIDATES = ["yolo26n-cls.pt", "yolo11n-cls.pt", "yolov8n-cls.pt"]


def pick_model():
    from ultralytics import YOLO
    last_err = None
    for name in MODEL_CANDIDATES:
        try:
            m = YOLO(name)
            print(f"[model] 使用 {name}")
            return m, name
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[model] {name} 不可用：{type(e).__name__}")
    raise RuntimeError(f"没有可用的分类模型权重：{last_err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=224)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--data", default=None, help="数据集目录名，默认 data/cls_poc")
    ap.add_argument("--name", default="poc10", help="runs 下的实验名")
    ap.add_argument("--cache", default="disk", choices=["ram", "disk", "false"],
                    help="图片缓存：MPS/Mac 上 workers 会被强制降为 0，I/O 是瓶颈，"
                         "开 cache 能快 2-3 倍。16GB 内存时 ram 约需 3.5GB（31 类），disk 更稳")
    args = ap.parse_args()

    global DATA
    if args.data:
        DATA = HERE / "data" / args.data

    if not DATA.exists():
        sys.exit(f"找不到数据集：{DATA}\n先跑 node scripts/prepare-poc-dataset.mjs --top=10")

    n_train = sum(len(list(p.glob("*.jpg"))) for p in (DATA / "train").iterdir())
    n_val = sum(len(list(p.glob("*.jpg"))) for p in (DATA / "val").iterdir())
    classes = sorted(p.name for p in (DATA / "train").iterdir())
    print(f"[data] {len(classes)} 类 / train {n_train} 张 / val {n_val} 张")
    print(f"[data] 类别：{classes}")

    import torch
    if args.device == "mps" and not torch.backends.mps.is_available():
        print("[device] MPS 不可用，回退 CPU")
        args.device = "cpu"
    print(f"[device] {args.device}  torch={torch.__version__}")

    model, model_name = pick_model()

    model.train(
        data=str(DATA),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        cache=False if args.cache == "false" else args.cache,
        plots=False,  # 省时间，结果看 results.csv
        project=str(HERE / "runs" / "cls"),
        name=args.name,
        exist_ok=True,
        verbose=False,  # 进度条会疯狂刷 \r，重定向到日志时关掉
    )

    print("\n=== 验证 ===")
    metrics = model.val()
    top1 = getattr(metrics, "top1", None)
    top5 = getattr(metrics, "top5", None)
    print(f"top1 = {top1}  top5 = {top5}")

    print("\n=== 导出 ONNX ===")
    out = model.export(format="onnx", imgsz=args.imgsz, simplify=True)
    print(f"ONNX: {out}")

    print("\n=== 汇总 ===")
    print(f"model      : {model_name}")
    print(f"classes    : {len(classes)}")
    print(f"train/val  : {n_train} / {n_val}")
    print(f"top1       : {top1}")
    print(f"top5       : {top5}")
    print(f"onnx       : {out}")


if __name__ == "__main__":
    main()
