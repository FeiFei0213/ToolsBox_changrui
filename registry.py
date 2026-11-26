"""工具目录。主页只读取元数据，打开工具时才导入其界面。"""

from importlib import import_module


CATEGORIES = ("图像处理", "标定与坐标", "生产配置", "日志")


def tool_entry(
    module: str, class_name: str, name: str, description: str,
    category: str, icon: str, keywords: str = "",
) -> dict[str, str]:
    return {
        "module": module,
        "class": class_name,
        "name": name,
        "description": description,
        "category": category,
        "icon": icon,
        "keywords": keywords,
    }


TOOLS = [
    tool_entry("tools.image_viewer.widget", "ImageViewerWidget",
               "Ziv 看图", "打开或拖入图片，缩放、连续翻图、显示准星和两点测距",
               "图像处理", "🖼️", "图片查看器 坐标 像素 image viewer"),
    tool_entry("tools.image_transform.widget", "ImageTransformWidget",
               "图片变换", "上下和左右镜像、90° 快捷旋转与任意角度旋转",
               "图像处理", "🔄", "图像 旋转 翻转 flip rotate 镜像"),
    tool_entry("tools.color_space_viewer.widget", "ColorSpaceViewerWidget",
               "图像色彩空间查看器", "对比原图与色彩空间转换结果，查看和保存各通道",
               "图像处理", "🌈", "HSV LAB RGB HLS YCrCb XYZ 灰度"),
    tool_entry("tools.mask_dilate.widget", "MaskDilateWidget",
               "Mask 图像膨胀", "对灰度图执行形态学膨胀，支持指定 ROI",
               "图像处理", "🔲", "掩膜 二值"),
    tool_entry("tools.mask_painter.widget", "MaskPainterWidget",
               "Mask 手绘编辑器", "绘制或修改二值 Mask，导出遮罩和提取后的图像",
               "图像处理", "🖌️", "掩膜 画笔"),
    tool_entry("tools.pixel_starfire.widget", "PixelStarfireWidget",
               "像素坐标转换", "从图像拾取像素坐标，转换为星火坐标并导出 CSV",
               "标定与坐标", "✨", "Starfire"),
    tool_entry("tools.extra_json.widget", "ExtraJsonWidget",
               "JSON 点坐标提取", "从 X-anylabeling 标注文件提取点坐标",
               "标定与坐标", "📍"),
    tool_entry("tools.plt_viewer.widget", "PltViewerWindow",
               "PLT 轮廓查看器", "查看轮廓和点，支持背景图对照与逆变换",
               "标定与坐标", "📐"),
    tool_entry("tools.calibration_point_editor.widget", "CalibrationPointEditorWindow",
               "标定点编辑", "在图像上编辑 YAML 标定点，支持图层与坐标微调",
               "标定与坐标", "🎯"),
    tool_entry("tools.point_annotator.widget", "PointAnnotatorWidget",
               "标注点工具", "在图片上点选标注，支持拖动、撤销和导出",
               "标定与坐标", "📌", "JSON CSV"),
    tool_entry("tools.board_calibration.widget", "BoardCalibrationWindow",
               "标定分析", "检测线扫相机椭圆轴比，标记并核对标定点",
               "标定与坐标", "🔭"),
    tool_entry("tools.txt_yaml.widget", "TxtYamlWidget",
               "替换碰撞区域文件（txt转yaml）", "转换安全区域坐标并部署到 VGS 碰撞配置",
               "生产配置", "📄", "TXT YAML"),
    tool_entry("tools.log_viewer.widget", "LogViewerWidget",
               "日志查看器", "查看 VGS 运行日志，按级别和关键字筛选",
               "日志", "📋"),
]


def load_tool_class(entry: dict[str, str]):
    return getattr(import_module(entry["module"]), entry["class"])
