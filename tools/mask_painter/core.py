"""Mask 手绘编辑器的无界面图像处理逻辑。"""

from pathlib import Path

import cv2
import numpy as np


def create_blank_mask(width: int, height: int, color: int) -> np.ndarray:
    """创建指定尺寸的纯黑或纯白 Mask。"""
    return np.full((height, width), color, dtype=np.uint8)


def normalize_mask(image: np.ndarray) -> np.ndarray:
    """将灰度 Mask 二值化为严格的 0/255。"""
    if image.ndim == 3:
        code = cv2.COLOR_BGRA2GRAY if image.shape[2] == 4 else cv2.COLOR_BGR2GRAY
        image = cv2.cvtColor(image, code)
    return np.where(image >= 128, 255, 0).astype(np.uint8)


def apply_mask_to_image(
        original: np.ndarray,
        mask: np.ndarray,
        keep_value: int,
        fill_value: int,
) -> np.ndarray:
    """保留 Mask 指定颜色对应的原图像素，其余像素填充黑色或白色。"""
    if original.shape[:2] != mask.shape[:2]:
        raise ValueError("原图与 Mask 尺寸必须一致")
    keep = mask == keep_value
    if original.ndim == 3:
        keep = keep[..., np.newaxis]
        fill = np.full(original.shape[2], fill_value, dtype=original.dtype)
        if original.shape[2] == 4:
            fill[3] = 255
    else:
        fill = fill_value
    return np.where(keep, original, fill).astype(original.dtype)


def read_image(path: str | Path) -> np.ndarray:
    """读取支持中文路径的图片。"""
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"无法读取图片: {path}")
    return image


def write_image(path: str | Path, image: np.ndarray) -> None:
    """保存到支持中文路径的图片文件。"""
    suffix = Path(path).suffix or ".png"
    ok, encoded = cv2.imencode(suffix, image)
    if not ok:
        raise ValueError(f"不支持的输出格式: {suffix}")
    encoded.tofile(str(path))


def draw_stroke(
        mask: np.ndarray,
        start: tuple[int, int],
        end: tuple[int, int],
        color: int,
        width: int,
) -> None:
    """在 Mask 上原地绘制一段带圆角的黑白画笔轨迹。"""
    cv2.line(mask, start, end, color, width, lineType=cv2.LINE_8)
