# 工具箱

基于 PySide6 的生产工具箱，集中管理图像处理、标定与坐标、生产配置和日志工具。

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

左侧选择分类，或按 `Ctrl+F` 搜索工具名称、说明和关键词。只有一条匹配结果时，按 `Enter` 打开。工具各自在独立窗口运行。

---

## 当前工具

### 🖼️ Ziv 看图

打开或拖入 PNG、JPG、BMP、TIFF 或 WebP 图片，按文件名中的数字顺序浏览同目录图片。到末尾后循环回到第一张，无法解码的文件会跳过。

| 操作 | 快捷方式 |
|------|----------|
| 打开图片 | Ctrl+O |
| 上一张 / 下一张 | ← / → |
| 缩放 | 滚轮，以鼠标位置为缩放锚点 |
| 平移 | 拖动鼠标，测距时用中键或右键 |
| 适应窗口 / 原始大小 | F / 1 |
| 切换十字准星 | C |
| 两点测距 / 清除 | M 后点击两个像素，Esc 清除 |

状态栏显示左上角为 `(0, 0)` 的原图像素坐标。测距结果以像素为单位，缩放不会改变测量值。Ziv 看图是 ToolsBox 内置功能，随 ToolsBox 源码与本体构建。

---

### 🔄 图片变换

打开或拖入 PNG、JPG、BMP、TIFF 或 WebP 图片，左右对照原图和当前结果。镜像和旋转可以连续应用，例如按两次 `Alt+→` 得到 180° 旋转。

| 快捷键 | 操作 |
|--------|------|
| Ctrl+O / Ctrl+S | 打开图片 / 另存结果 |
| Alt+← / Alt+→ | 逆时针 / 顺时针旋转 90° |
| Alt+H / Alt+V | 左右 / 上下镜像 |
| Ctrl+Z / Ctrl+Y | 撤销 / 重做 |
| Ctrl+R | 恢复原图，也可撤销此操作 |

也可输入自定义角度，正值表示顺时针。任意角度旋转会自动扩展画布。另存为 PNG、TIFF 或 WebP 可保留透明区域，另存为 JPG 或 BMP 会以黑色填充。需要保留 16 位数据时，请选 PNG 或 TIFF。

任意角度旋转的输入与输出边长均需小于 32,767 像素，输出最多为 4,000 万像素。较长的线扫图仍可使用镜像和 90° 旋转。

---

### 🌈 图像色彩空间查看器

加载图片后左右对比原图与转换结果，便于在正式处理前观察不同色彩空间及通道的分布。

- 支持 PNG / JPG / JPEG / BMP / TIFF / WebP、中文路径，以及灰度、透明通道和常见 8/16 位输入
- 支持灰度、RGB、HSV、LAB、HLS、YCrCb、XYZ
- 三通道空间可查看伪彩色合成图，也可分别查看各通道灰度图
- 切换色彩空间或通道时实时更新，并显示图片尺寸、通道数、数据类型与数值范围
- 可将右侧当前结果单独保存为常见图片格式
- 支持拖入图片；快捷键 `Ctrl+O` 打开、`Ctrl+S` 保存当前结果

> 伪彩色视图把三个数值通道依次映射到 R / G / B，仅用于比较通道分布，不代表真实颜色。

---

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

### 🖌️ Mask 手绘编辑器

在原图上使用黑白画笔创建或微调二值 Mask，并按 Mask 提取原图区域。

**主要功能**

- 新建纯黑 / 纯白背景 Mask，或加载已有 Mask 继续修改
- 黑色 / 白色画笔切换，画笔宽度 1–300 px
- 原图与 Mask 半透明叠加预览，透明度可调
- 撤销 / 重做、整图填黑 / 填白、黑白反转
- 导出当前纯黑白 Mask
- 选择保留 Mask 的黑色或白色区域，并将原图其余区域填充为黑色或白色后导出
- 支持滚轮缩放、右键 / 中键拖动平移和拖入原图

**快捷键**

| 键 | 功能 |
|----|------|
| Ctrl+O | 打开原图 |
| Ctrl+Z / Ctrl+Y | 撤销 / 重做 |
| B / W | 切换黑色 / 白色画笔 |
| F | 图片适应窗口 |

---

### 📄 替换碰撞区域文件（txt转yaml）

将安全区域坐标 TXT 文件转换为 YAML 格式，并部署或新增到 VGS 碰撞配置目录。

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

### 📌 标注点工具

在图片上点击标注坐标点，支持拖动、撤销/重做、自动保存复用。

**功能**

- 点击空白处添加标注点（自动编号）
- 拖动单点 / 框选多点后整体拖动
- 右键重命名 / 删除，Delete 键删除选中点
- 自动保存到同目录 `{图片名}.json`，下次打开同一图片自动还原
- 侧边栏实时列表，支持偏移选中点（方向键 + 自定义步长）
- 导出 JSON / CSV
- **Extra JSON 坐标**：自动将当前所有标注点格式化为 `[x,y],` 文本，可一键复制或另存为 TXT

**快捷键**

| 键 | 功能 |
|----|------|
| Ctrl+O | 打开图片 |
| Tab | 切换标注 / 选择模式 |
| Ctrl+Z | 撤销 |
| Ctrl+Y | 重做 |
| Ctrl+A | 全选所有点 |
| Delete | 删除选中点 |

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

### 📋 日志查看器

查看 VGS 运行日志，解决 UI 关闭后日志消失的问题。首次启动时若目录不存在会弹出选择框，也可点击工具栏"切换目录"随时更换。目录选择会保存到 `~/.toolbox/log_viewer_settings.json`。

**功能**

- 左侧文件列表，按修改时间倒序排列，当前日志置顶
- 后台线程解析，不阻塞 UI；默认隐藏 DEBUG（应对 81MB 大文件）
- 支持 DEBUG / INFO / WARNING / ERROR 四级独立过滤
- 实时关键词搜索（匹配消息内容 + 模块名）
- 行颜色按级别区分：WARNING 橙色、ERROR 红色
- 底部详情面板，点击任意行显示时间/级别/模块/来源/线程/完整消息
- **自动刷新**（仅当前日志）：每 3 秒检查新增内容，追加显示不全量重载
- 勾选 DEBUG 且文件 >5MB 时，只读末尾 20MB 控制内存

**快捷键**

| 键 | 功能 |
|----|------|
| Ctrl+R | 重新加载当前文件 |
| Ctrl+F | 聚焦关键词输入框 |
| Ctrl+E | 切换"仅看错误"模式（只显示 WARNING/ERROR） |

---

## 目录结构

```
toolbox/
├── main.py                      # 入口
├── launcher.py                  # 工具分类与搜索主页
├── tool_base.py                 # ToolBase 抽象基类
├── registry.py                  # 工具注册表 ← 添加新工具改这里
├── requirements.txt
├── icon/
│   └── icon.png                 # 应用图标（打包时使用）
└── tools/
    ├── common_ui.py             # 共享 UI 组件（可折叠 Dock 标题栏等）
    ├── image_io.py              # 支持中文路径的图像读写
    ├── image_preview.py         # 保持宽高比的图像预览
    ├── image_viewer/            # Ziv 看图窗口、坐标映射和测距画布
    ├── image_transform/
    │   ├── core.py              # 镜像、旋转、导出和操作历史
    │   └── widget.py            # 图片变换窗口
    ├── yaml_formatter.py        # YAML 格式化工具
    ├── color_space_viewer/
    │   ├── core.py              # 色彩空间转换、格式归一化与图片读写
    │   └── widget.py            # 原图/结果对比与保存界面
    ├── mask_dilate/
    │   ├── core.py
    │   └── widget.py
    ├── mask_painter/
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
    ├── log_viewer/
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

**第二步**：在 `registry.py` 的 `TOOLS` 中添加模块路径、类名与主页元数据：

```python
tool_entry("tools.my_tool.widget", "MyToolWidget",
           "我的新工具", "一句话说明功能", "图像处理", "🛠", "搜索关键词"),
```

重启程序后，就可以在对应分类中找到它。

---

## 打包发布 EXE

GitHub Actions 会在干净的 Windows 云端环境中安装依赖、编译源码、打包 EXE，
并实际启动打包后的程序执行自检。下载者不需要安装 Python 或项目依赖。

支持 Windows 10/11 x64。

当前发布包未做商业代码签名，Windows SmartScreen 首次运行时可能显示安全提示；
如需消除此提示，需要配置受信任的代码签名证书。

### 普通推送

推送到 `master` 或 `main` 后，会自动生成可下载的 Actions Artifact：

1. 打开仓库的 **Actions**
2. 进入最新一次 `Build Windows EXE`
3. 在页面底部下载 `ToolsBox-Windows-x64-*`

Artifact 内包含：

- `ToolsBox.exe`：独立可执行文件
- `SHA256SUMS.txt`：文件完整性校验值

也可以在 Actions 页面手动运行该工作流。

### 正式发布

推送 Git tag 会在完成相同构建和自检后，自动创建 GitHub Release。

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

- **懒加载**：主页从注册表读取分类、名称和描述。打开工具窗口时才导入对应模块。
- **图标**：打包时使用 `icon/icon.png`。
- **board_calibration**：图片路径须为纯英文，不支持中文路径。
