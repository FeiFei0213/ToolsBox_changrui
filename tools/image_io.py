"""OpenCV 图像读写，兼容 Windows 中文文件路径。"""

from pathlib import Path

import cv2
import numpy as np


def read_image(path: str | Path) -> np.ndarray:
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED) if data.size else None
    except (OSError, cv2.error) as exc:
        raise ValueError(f"无法读取图片: {path}") from exc
    if image is None:
        raise ValueError(f"无法读取图片: {path}")
    return image


def write_image(path: str | Path, image: np.ndarray) -> None:
    path = Path(path)
    suffix = path.suffix.lower() or ".png"
    try:
        ok, encoded = cv2.imencode(suffix, image)
    except cv2.error as exc:
        raise ValueError(f"无法编码为 {suffix} 图片") from exc
    if not ok:
        raise ValueError(f"不支持的输出格式: {suffix}")
    try:
        encoded.tofile(str(path))
    except OSError as exc:
        raise ValueError(f"无法保存图片: {path}") from exc
