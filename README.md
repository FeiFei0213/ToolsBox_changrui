# VGS 工具箱

集中管理常用小工具的独立启动器，基于 PySide6，点击卡片即可打开对应工具窗口。

---

## 环境要求

| 项目 | 版本 |
|------|------|
| Python | 3.11 |
| PySide6 | ≥ 6.0 |
| opencv-python | 任意 |
| numpy | 任意 |

---

## 快速开始

### 1. 激活环境

```bash
conda activate toolbox
```

### 2. 运行

```bash
cd D:\project\code\toolbox
python main.py
```

---

## 当前工具

### Mask 图像膨胀

对灰度（黑白）图片执行形态学膨胀处理。

| 参数 | 说明 |
|------|------|
| 输入图片 | 灰度图，支持 PNG / JPG / BMP / TIFF，可拖拽 |
| Kernel 大小 | 膨胀核的宽高（奇数），默认 3×3 |
| 迭代次数 | 膨胀执行次数，数值越大效果越明显 |
| 膨胀目标 | 膨胀白色区域 或 膨胀黑色区域 |
| 翻转选项 | 膨胀前 / 膨胀后可各自独立翻转颜色 |
| ROI 区域 | 限定膨胀范围，每行一个 `x1,y1,x2,y2`，留空表示整图 |
| 排除区域 | 指定不膨胀的区域，格式同上 |
| 输出路径 | 留空不保存，填写路径则保存结果图 |

执行后左右对比预览原图与结果图。

---

### TXT → YAML 转换

将安全区域坐标的 TXT 文件批量转换为 YAML 格式。

**输入格式（TXT）**

```
x1,y1
x2,y2
---
x3,y3
x4,y4
```

`---` 分隔多个轮廓。

**输出格式（YAML）**

```yaml
contour1:
  - [x1, y1]
  - [x2, y2]
contour2:
  - [x3, y3]
  - [x4, y4]
```

支持：打开文件、粘贴文本、拖拽 TXT 文件、批量转换、复制结果、另存 YAML。

---

### 像素坐标转换

在图片上点击拾取像素坐标，转换为星火坐标系，记录到表格并支持导出 CSV。

**使用步骤**

1. 选择设备（M7 / M23 / M24 / M25 / M26）和位置（0 / 1）
2. 点击"打开图片"加载图片
3. 点击"点击拾取坐标（P）"进入拾取模式
4. 在图片上点击，坐标自动转换并记录到下方表格
5. 可"导出 CSV"保存所有记录点

**快捷键**

| 键 | 功能 |
|----|------|
| Ctrl+O | 打开图片 |
| P | 切换拾取模式 |
| Ctrl+Z | 撤销最后一点 |

---

## 目录结构

```
toolbox/
├── main.py                 # 入口：启动 QApplication
├── launcher.py             # 主启动器窗口（卡片网格）
├── tool_base.py            # ToolBase 抽象基类
├── registry.py             # 工具注册表 ← 添加新工具改这里
├── requirements.txt
└── tools/
    ├── mask_dilate/
    │   ├── core.py         # 膨胀核心逻辑（纯函数）
    │   └── widget.py       # MaskDilateWidget（GUI）
    ├── txt_yaml/
    │   └── widget.py       # TxtYamlWidget（GUI + 转换逻辑）
    └── pixel_starfire/
        ├── pixel_to_starfire.py  # 坐标转换核心函数
        ├── widget.py             # PixelStarfireWidget（GUI）
        └── config/device/        # 各设备标定参数 JSON
            ├── M7/{0,1}/
            ├── M23/{0,1}/
            ├── M24/{0,1}/
            ├── M25/{0,1}/
            └── M26/{0,1}/
```

---

## 添加新工具

### 第一步：新建工具文件

在 `tools/` 下创建一个新目录（或直接新建 `.py` 文件），编写继承 `ToolBase` 的 widget 类：

```python
# tools/my_tool/widget.py
from tool_base import ToolBase

class MyToolWidget(ToolBase):
    tool_name = "我的新工具"
    tool_description = "一句话说明功能"
    tool_icon = "🛠"

    def init_ui(self):
        # 在这里构建 UI，self 即是 QWidget
        ...
```

**`ToolBase` 规范**

| 属性 / 方法 | 类型 | 说明 |
|------------|------|------|
| `tool_name` | `str` | 显示在卡片标题 |
| `tool_description` | `str` | 显示在卡片副标题 |
| `tool_icon` | `str` | 卡片图标（emoji 或留空） |
| `init_ui(self)` | 抽象方法 | 必须实现，构建 UI 布局 |

### 第二步：注册到 registry.py

```python
# registry.py
TOOLS = [
    ...
    {"module": "tools.my_tool.widget", "class": "MyToolWidget"},  # 加这一行
]
```

重启程序，新工具卡片自动出现。

---

## 注意事项

- **懒加载**：工具模块在点击卡片时才 import，缺少依赖只影响该工具，不影响主界面启动。
- **像素坐标转换的配置文件**：标定参数存储在 `tools/pixel_starfire/config/device/`，如需增加设备，按相同目录结构放入 `fit_params.json` 和 `polynomials_fit.json` 即可，无需修改代码。
- **conda 环境**：使用 `toolbox` 环境，解释器路径 `D:\project\miniconda3\envs\toolbox\python.exe`。
