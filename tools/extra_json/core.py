import json
import numpy as np


def extract_points_from_json(json_path: str) -> tuple[list[list[float]], str]:
    """
    从 X-anylabeling JSON 文件提取所有 shapes 中的点坐标。
    返回 (points列表, 格式化文本)。
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    points = []
    for shape in data.get('shapes', []):
        for point in shape.get('points', []):
            points.append([float(point[0]), float(point[1])])

    lines = [f"[{p[0]:.2f},{p[1]:.2f}]," for p in points]
    text = "\n".join(lines)
    return points, text
