"""图片变换和导出，无 GUI 依赖。"""

from math import ceil, isfinite
from pathlib import Path

import cv2
import numpy as np

from tools.image_io import write_image


OUTPUT_FORMATS = {
    "PNG 图片 (*.png)": ".png",
    "JPEG 图片 (*.jpg *.jpeg)": ".jpg",
    "BMP 图片 (*.bmp)": ".bmp",
    "TIFF 图片 (*.tif *.tiff)": ".tiff",
    "WebP 图片 (*.webp)": ".webp",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
MAX_WARP_SIDE = 32_766
MAX_WARP_PIXELS = 40_000_000


def validate_image(image: np.ndarray) -> None:
    valid_channels = image.ndim == 2 or (image.ndim == 3 and image.shape[2] in (3, 4))
    if not image.size or not valid_channels or image.dtype not in (np.uint8, np.uint16):
        raise ValueError("请选择 8 位或 16 位的灰度、彩色或带透明通道的图片。")


def flip_image(image: np.ndarray, *, horizontal: bool) -> np.ndarray:
    return cv2.flip(image, 1 if horizontal else 0)


def rotate_image(image: np.ndarray, degrees: float) -> np.ndarray:
    """按顺时针角度旋转。直角旋转逐像素重排，其他角度扩展画布。"""
    if not isfinite(degrees):
        raise ValueError("请输入有效角度。")
    degrees %= 360
    if degrees % 90 == 0:
        return np.rot90(image, -int(degrees // 90)).copy(order="C")

    height, width = image.shape[:2]
    center = ((width - 1) / 2, (height - 1) / 2)
    matrix = cv2.getRotationMatrix2D(center, -degrees, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    out_width = ceil(width * cos + height * sin)
    out_height = ceil(height * cos + width * sin)
    # OpenCV remap 使用有符号 16 位索引，先检查尺寸以避免底层断言。
    if max(width, height, out_width, out_height) > MAX_WARP_SIDE:
        raise ValueError(f"任意角度旋转的输入和输出边长最多为 {MAX_WARP_SIDE:,} px。")
    if out_width * out_height > MAX_WARP_PIXELS:
        raise ValueError(
            f"旋转后的画布为 {out_width} × {out_height} px，超过 "
            f"{MAX_WARP_PIXELS:,} 像素上限。"
        )
    matrix[0, 2] += (out_width - width) / 2
    matrix[1, 2] += (out_height - height) / 2

    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGRA)
    elif image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)

    # 先乘 Alpha 再插值，避免透明像素中的颜色渗到旋转边缘。
    limit = np.iinfo(image.dtype).max
    premultiplied = image.astype(np.float32)
    premultiplied[..., :3] *= premultiplied[..., 3:] / limit
    rotated = cv2.warpAffine(premultiplied, matrix, (out_width, out_height))
    channels, alpha = rotated[..., :3], rotated[..., 3:]
    np.divide(channels, alpha / limit, out=channels, where=alpha > 0)
    np.rint(rotated, out=rotated)
    np.clip(rotated, 0, limit, out=rotated)
    return rotated.astype(image.dtype)


def save_image(path: Path, image: np.ndarray) -> None:
    suffix = path.suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        raise ValueError(f"不支持的图片格式: {suffix or '无扩展名'}")
    if suffix in {".jpg", ".jpeg", ".bmp"} and image.ndim == 3 and image.shape[2] == 4:
        alpha = image[..., 3:].astype(np.float32) / np.iinfo(image.dtype).max
        image = np.rint(image[..., :3] * alpha).astype(image.dtype)
    if suffix in {".jpg", ".jpeg", ".bmp", ".webp"} and image.dtype == np.uint16:
        image = np.rint(image / 257.0).astype(np.uint8)
    write_image(path, image)


class TransformHistory:
    """记录当前结果及最近的操作，限制高分辨率图片的历史占用。"""

    def __init__(self, source: np.ndarray):
        self.source = source
        self.current = source
        self._undo: list[np.ndarray] = []
        self._redo: list[np.ndarray] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def apply(self, result: np.ndarray) -> None:
        self._redo.clear()
        self._undo.append(self.current)
        self.current = result
        while len(self._undo) > 1 and (
            len(self._undo) > 12
            or sum(image.nbytes for image in self._undo if image is not self.source)
            > 128 * 1024 * 1024
        ):
            self._undo.pop(0)

    def undo(self) -> None:
        if self._undo:
            self._redo.append(self.current)
            self.current = self._undo.pop()

    def redo(self) -> None:
        if self._redo:
            self._undo.append(self.current)
            self.current = self._redo.pop()
