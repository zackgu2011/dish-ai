# Dish AI — 纯前端端侧菜品图像识别引擎

> 🍳 **零服务器成本 · 100% 浏览器本地推理 · 极速隐私安全**  
> 基于 YOLO 轻量分类模型 + ONNX Runtime Web，在用户设备浏览器（手机/电脑）内直接完成菜品图像识别与营养结构分析，无需将用户图片上传至云端。

---

## 🌟 核心特性

- **纯端侧推理（Client-side AI）**：模型在浏览器加载执行（支持 WebAssembly SIMD 加速与 WebGPU），零后端推理算力成本。
- **极致隐私保护**：用户拍摄的餐盘、食堂菜品照片完全保留在手机/电脑本地，不经过任何服务器网络传输，杜绝个人隐私与照片泄露。
- **离线与弱网可用**：模型与静态推理库下载缓存后，即使在无网络环境下（如地下食堂、信号盲区）依然能毫秒级出识别结果。
- **高鲁棒性预处理**：内置自适应长宽比缩放、归一化、Top-K 候选置信度过滤与备选菜品推荐算法。

---

## 📁 目录结构

```
dish-ai/
├── models/                     # 生产部署模型与类别映射
│   ├── classes.json            # 菜品类别与 ID 映射字典
│   ├── dish-cls.onnx           # 校园食堂高频菜品轻量分类模型 (~6MB)
│   └── pose-cls.onnx           # 姿态/动作识别辅助模型 (~11MB)
├── ort/                        # ONNX Runtime Web 静态依赖资源
│   ├── ort.min.js              # ONNX Runtime JS 封装层
│   ├── ort.wasm.min.js         # WASM 核心运行层
│   └── ort-wasm-simd-threaded* # SIMD 与多线程优化运行时
├── demo.html                   # 极简单页体验 Demo（双击或本地服务即开）
├── recognize.html              # 完整集成版选菜识别台
├── dish-recognizer.js          # 纯前端封装的推理 SDK（加载、预测、后处理）
├── train_poc.py                # YOLO 模型训练脚本
├── eval_realworld.py           # 实拍真实场景评测脚本
└── analyze_confusion.py        # 混淆矩阵与错误归因分析工具
```

---

## 🚀 快速开始

### 1. 本地免安装直接运行体验
由于浏览器安全策略限制加载本地 WASM 文件，推荐使用简单的 HTTP 服务启动：

```bash
# 在当前目录下启动轻量服务
python3 -m http.server 5200

# 浏览器访问体验 Demo
open http://127.0.0.1:5200/demo.html
```

### 2. 在业务网页中引入识别能力
```html
<!-- 1. 引入 ONNX Runtime Web -->
<script src="ort/ort.min.js"></script>

<!-- 2. 引入识别器 -->
<script src="dish-recognizer.js"></script>

<script>
  async function test() {
    const recognizer = new DishRecognizer({
      modelPath: 'models/dish-cls.onnx',
      classesPath: 'models/classes.json'
    });
    
    // 初始化并加载 WASM 模型
    await recognizer.init();
    
    // 传入 img 元素或 HTMLCanvasElement 进行预测
    const imgEl = document.getElementById('myDishPhoto');
    const results = await recognizer.predict(imgEl, { topK: 3 });
    console.log('Top 识别结果:', results);
  }
</script>
```

---

## 🛠️ 模型训练与评估

本模块基于 Ultralytics YOLO 分类管线微调定制：

1. **环境准备**：
   ```bash
   pip install ultralytics onnx onnxruntime Pillow
   ```
2. **启动训练**：
   ```bash
   python train_poc.py
   ```
3. **真实场景评估**：
   ```bash
   python eval_realworld.py
   ```
4. **导出为 Web 端 ONNX**：
   ```python
   from ultralytics import YOLO
   model = YOLO("runs/cls/best.pt")
   model.export(format="onnx", imgsz=224, dynamic=False)
   ```

---

## 📄 许可证

本项目遵循 MIT 开源许可证。
