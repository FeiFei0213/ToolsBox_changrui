"""图像色彩空间查看器的无界面核心逻辑。"""

from dataclasses import dataclass

import cv2
import numpy as np

from tools.image_io import read_image, write_image


@dataclass(frozen=True)
class ColorSpaceSpec:
    """一个色彩空间及其可选视图。"""

    label: str
    channels: tuple[str, ...]
    conversion_code: int | None
    first_channel_max: int = 255

    @property
    def views(self) -> tuple[str, ...]:
        if len(self.channels) == 1:
            return self.channels
        return ("Composite", *self.channels)


COLOR_SPACES: dict[str, ColorSpaceSpec] = {
    "RGB": ColorSpaceSpec("RGB / 原图", ("R", "G", "B"), None),
    "GRAY": ColorSpaceSpec("灰度", ("Gray",), cv2.COLOR_BGR2GRAY),
    "HSV": ColorSpaceSpec("HSV", ("H", "S", "V"), cv2.COLOR_BGR2HSV, 179),
    "LAB": ColorSpaceSpec("LAB", ("L", "a", "b"), cv2.COLOR_BGR2LAB),
    "HLS": ColorSpaceSpec("HLS", ("H", "L", "S"), cv2.COLOR_BGR2HLS, 179),
    "YCrCb": ColorSpaceSpec("YCrCb", ("Y", "Cr", "Cb"), cv2.COLOR_BGR2YCrCb),
    "XYZ": ColorSpaceSpec("XYZ", ("X", "Y", "Z"), cv2.COLOR_BGR2XYZ),
}


def _to_uint8(image: np.ndarray) -> np.ndarray:
    if image.dtype == np.uint8:
        return image.copy()
    if image.dtype == np.uint16:
        return np.rint(image.astype(np.float64) / 257.0).astype(np.uint8)
    if image.dtype == np.bool_:
        return image.astype(np.uint8) * 255
    if np.issubdtype(image.dtype, np.floating):
        values = np.nan_to_num(image.astype(np.float64), nan=0.0, posinf=255.0, neginf=0.0)
        if values.size and values.min() >= 0.0 and values.max() <= 1.0:
            values *= 255.0
        return np.rint(np.clip(values, 0.0, 255.0)).astype(np.uint8)
    if np.issubdtype(image.dtype, np.integer):
        limits = np.iinfo(image.dtype)
        values = image.astype(np.float64)
        values = (values - limits.min) * (255.0 / (limits.max - limits.min))
        return np.rint(np.clip(values, 0.0, 255.0)).astype(np.uint8)
    raise ValueError(f"不支持的像素类型: {image.dtype}")


def normalize_image(image: np.ndarray) -> np.ndarray:
    """将灰度/BGR/BGRA 和常见位深统一成 8 位 BGR 图。"""
    if not isinstance(image, np.ndarray) or image.size == 0:
        raise ValueError("图片数据为空")

    image = _to_uint8(image)
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim != 3:
        raise ValueError("图片维度必须为灰度、BGR 或 BGRA")
    if image.shape[2] == 1:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 3:
        return image
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    raise ValueError(f"不支持的通道数: {image.shape[2]}")


def available_views(space: str) -> tuple[str, ...]:
    """返回指定色彩空间支持的合成/单通道视图。"""
    try:
        return COLOR_SPACES[space].views
    except KeyError as exc:
        raise ValueError(f"不支持的色彩空间: {space}") from exc


def convert_image(image: np.ndarray, space: str, view: str) -> np.ndarray:
    """生成适合直接显示和保存的 8 位 BGR 或单通道图。"""
    try:
        spec = COLOR_SPACES[space]
    except KeyError as exc:
        raise ValueError(f"不支持的色彩空间: {space}") from exc
    if view not in spec.views:
        raise ValueError(f"{space} 不支持视图: {view}")

    bgr = normalize_image(image)
    if space == "GRAY":
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    if space == "RGB":
        if view == "Composite":
            return bgr
        channel_index = {"B": 0, "G": 1, "R": 2}[view]
        return bgr[:, :, channel_index]

    converted = cv2.cvtColor(bgr, spec.conversion_code)
    if view != "Composite":
        return converted[:, :, spec.channels.index(view)]

    visual_channels = list(cv2.split(converted))
    if spec.first_channel_max != 255:
        visual_channels[0] = np.rint(
            visual_channels[0].astype(np.float32) * (255.0 / spec.first_channel_max)
        ).astype(np.uint8)
    # 把三个数值通道依次映射到可见的 R/G/B，用于比较通道分布；
    # ndarray 仍保持 OpenCV 的 BGR 存储顺序，便于直接显示和保存。
    return cv2.merge((visual_channels[2], visual_channels[1], visual_channels[0]))
