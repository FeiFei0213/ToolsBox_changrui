# 工具箱

集中管理常用小工具的独立启动器，基于 PySide6，点击卡片即可打开对应工具窗口。

---

## 环境要求

| 包 | 版本要求 | 用途 |
|----|----------|------|
| Python | 3.11+ | — |
| PySide6 | ≥ 6.6 | GUI 框架 |
| opencv-python | ≥ 4.8 | 图像处理（膨胀、椭圆检测、旋转裁剪） |
| numpy | ≥ 1.26 | 数值计算 |
| pyyaml | ≥ 6.0 | YAML 读写（PLT 查看器、标定点编辑） |

安装依赖：

```bash
pip install -r requirements.txt
```

---

## 快速开始

```bash
cd D:\project\code\toolbox
python main.py
```

---

## 当前工具

### 🔲 Mask 图像膨胀

对灰度图执行形态学膨胀，支持 ROI 区域指定。

| 参数 | 说明 |
|------|------|
| 输入图片 | 灰度图，支持 PNG / JPG / BMP / TIFF，可拖拽 |
| Kernel 大小 | 膨胀核宽高（奇数），默认 3×3 |
| 迭代次数 | 膨胀执行次数 |
| 膨胀目标 | 白色区域 / 黑色区域 |
| 翻转选项 | 膨胀前 / 后独立翻转颜色 |
| ROI 区域 | 每行一个 `x1,y1,x2,y2`，留空表示整图 |
| 排除区域 | 不膨胀的区域，格式同上 |
| 输出路径 | 留空不保存 |

执行后左右对比预览原图与结果。

---

### 📄 TXT → YAML 转换

将安全区域坐标 TXT 文件批量转换为 YAML 格式。

**输入格式（TXT）**

```
x1,y1
x2,y2
---
x3,y3
```

`---` 分隔多个轮廓。

**输出格式（YAML）**

```yaml
contour1:
  - [x1, y1]
  - [x2, y2]
contour2:
  - [x3, y3]
```

支持打开文件、粘贴文本、拖拽、批量转换、复制结果、另存 YAML。

---

### ✨ 像素坐标转换（Pixel Starfire）

在图片上点击拾取像素坐标，转换为星火坐标系，记录到表格并支持导出 CSV。

**使用步骤**

1. 选择设备（M7 / M23 / M24 / M25 / M26）和位置（0 / 1）
2. 打开图片
3. 进入拾取模式，点击图片记录坐标
4. 导出 CSV

**快捷键**

| 键 | 功能 |
|----|------|
| Ctrl+O | 打开图片 |
| P | 切换拾取模式 |
| Ctrl+Z | 撤销最后一点 |

---

### 📍 JSON 点坐标提取

从 X-anylabeling 标注 JSON 文件提取所有 shapes 中的点坐标，输出 `[x, y],` 格式，一键复制。

支持拖拽 JSON 文件到窗口。

---

### 📐 PLT 轮廓查看器

查看 `contour.plt` 文件的轮廓和点，可叠加背景图对比。

- 支持加载背景图片（PNG / JPG / TIFF）
- 可调整点大小、线宽、背景透明度
- 支持加载 `mapping_params_file`（fit_params.json）和 `mapping_poly_file`，实时编辑参数并重绘逆变换结果
- 默认自动加载 `config/device/M7/0/` 下的配置文件

---

### 🎯 标定点编辑

在图片上编辑 YAML 格式的标定点坐标。

- 自动识别 YAML 中的单个坐标和坐标数组（多边形）
- 拖拽移动点，方向键微调（可配置步长）
- 图层面板控制各组点的显示/隐藏
- 框选多点批量移动
- 保存时自动格式化输出 YAML

---

### 🔭 标定分析（Board Calibration）

线扫相机椭圆轴比检测与标定点标记工具。

**椭圆检测模式**

1. 打开图片（路径须为纯英文）
2. 在图片上拖拽选定 ROI（支持旋转）
3. 点击"检测椭圆"，自动计算各椭圆 Y/X 轴比
4. 输出平均比值、乘法器、后分配器建议值
5. 填写圆直径（mm）可进一步计算像素比例尺（mm/px）

**线扫标定模式**

1. 在图片上左键单击标记像素点（自动编号），右键删除
2. 导入真实坐标文件（`xst_start` / `xst_end` 格式）
3. 像素坐标与真实坐标自动对应展示

---

## 目录结构

```
toolbox/
├── main.py                      # 入口
├── launcher.py                  # 卡片网格启动器
├── tool_base.py                 # ToolBase 抽象基类
├── registry.py                  # 工具注册表 ← 添加新工具改这里
├── requirements.txt
├── icon/
│   └── icon.png                 # 应用图标（打包时使用）
└── tools/
    ├── common_ui.py             # 共享 UI 组件（可折叠 Dock 标题栏等）
    ├── yaml_formatter.py        # YAML 格式化工具
    ├── mask_dilate/
    │   ├── core.py
    │   └── widget.py
    ├── txt_yaml/
    │   └── widget.py
    ├── pixel_starfire/
    │   ├── pixel_to_starfire.py
    │   ├── widget.py
    │   └── config/device/{M7,M23,M24,M25,M26}/{0,1}/
    ├── extra_json/
    │   ├── core.py
    │   └── widget.py
    ├── plt_viewer/
    │   ├── inverse_transform.py # 多项式逆变换算法（脱离 vgs 独立运行）
    │   └── widget.py
    ├── calibration_point_editor/
    │   └── widget.py
    ├── point_annotator/
    │   └── widget.py
    └── board_calibration/       # 来自 github.com/pipihuang2/board_calibration
        ├── ellipse_detector.py
        ├── image_view.py
        ├── point_picker_view.py
        └── widget.py
```

---

## 添加新工具

**第一步**：在 `tools/` 下新建目录，编写继承 `ToolBase` 的 widget 类：

```python
# tools/my_tool/widget.py
from tool_base import ToolBase

class MyToolWidget(ToolBase):
    tool_name = "我的新工具"
    tool_description = "一句话说明功能"
    tool_icon = "🛠"

    def init_ui(self):
        ...  # 构建 UI，self 即是 QWidget
```

> 若工具需要 `QMainWindow`（带 Dock / Toolbar），直接继承 `QMainWindow` 并声明三个类属性即可，无需继承 `ToolBase`。

**第二步**：在 `registry.py` 追加一行：

```python
{"module": "tools.my_tool.widget", "class": "MyToolWidget"},
```

重启程序，卡片自动出现。

---

## 打包发布 EXE

推送 Git tag 即可触发 GitHub Actions 自动打包，无需本地操作。

### 触发方式

```bash
git tag v1.0.0
git push origin v1.0.0
```

tag 格式须以 `v` 开头（如 `v1.0.0`、`v1.2.3`）。

### 流程

1. GitHub Actions 在 Windows 云端机器上自动执行
2. 安装依赖 → PyInstaller 打包 → 生成单文件 `ToolsBox.exe`
3. 自动创建 GitHub Release，exe 作为附件上传

全程约 **3–5 分钟**，完成后在仓库 **Releases** 页面下载。

### 费用

| 仓库类型 | 费用 |
|----------|------|
| 公开仓库 | 完全免费 |
| 私有仓库 | 每月 2000 分钟免费，Windows 按 2× 计约 1000 分钟；日常使用够用 |

---

## 注意事项

- **懒加载**：工具模块在点击卡片时才 import，缺少依赖只影响该工具，不影响主界面启动。
- **图标**：打包时使用 `icon/icon.png`。
- **board_calibration**：图片路径须为纯英文，不支持中文路径。
