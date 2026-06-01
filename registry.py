"""
工具注册表。
添加新工具：在 TOOLS 列表末尾追加一条 dict，其余无需改动。
"""

TOOLS = [
    {"module": "tools.mask_dilate.widget",                   "class": "MaskDilateWidget"},
    {"module": "tools.txt_yaml.widget",                      "class": "TxtYamlWidget"},
    {"module": "tools.pixel_starfire.widget",                "class": "PixelStarfireWidget"},
    {"module": "tools.extra_json.widget",                    "class": "ExtraJsonWidget"},
    {"module": "tools.plt_viewer.widget",                    "class": "PltViewerWindow"},
    {"module": "tools.calibration_point_editor.widget",      "class": "CalibrationPointEditorWindow"},
    {"module": "tools.point_annotator.widget",               "class": "PointAnnotatorWidget"},
    {"module": "tools.board_calibration.widget",             "class": "BoardCalibrationWindow"},
    {"module": "tools.log_viewer.widget",                    "class": "LogViewerWidget"},
]


def load_tool_class(entry: dict):
    """懒加载：点击卡片时才 import，缺少依赖时只影响该工具。"""
    import importlib
    module = importlib.import_module(entry["module"])
    return getattr(module, entry["class"])
