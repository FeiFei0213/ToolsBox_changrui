"""
core.py — Mask 图像膨胀核心逻辑。

对外暴露唯一公共函数 invert_black_white_and_dilate()，无 GUI 依赖，
可在脚本中直接调用，也被 MaskDilateWidget 内部使用。
"""
import logging
logger = logging.getLogger(__name__)

import cv2
import numpy as np


def invert_black_white_and_dilate(
        image_path: str,
        output_path: str = None,
        kernel_size: tuple = (3, 3),
        dilate_iterations: int = 1,
        show_result: bool = False,
        dilate_white: bool = True,
        invert_before: bool = False,
        invert_after: bool = False,
        roi: list = None,
        exclude_roi: list = None,
) -> np.ndarray:
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"无法读取图片，请检查路径是否正确：{image_path}")
    if len(img.shape) != 2:
        raise ValueError("输入图片必须是黑白（灰度）图片，请勿传入彩色图")

    base_img = 255 - img if invert_before else img
    process_img = base_img if dilate_white else 255 - base_img

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, kernel_size)
    dilated_img = cv2.dilate(process_img, kernel, iterations=dilate_iterations)

    if not dilate_white:
        dilated_img = 255 - dilated_img
    if invert_after:
        dilated_img = 255 - dilated_img

    if roi:
        if isinstance(roi, tuple):
            roi = [roi]
        mask = np.zeros_like(img)
        for x1, y1, x2, y2 in roi:
            mask[y1:y2, x1:x2] = 255
        result_img = np.where(mask == 255, dilated_img, img)
    else:
        result_img = dilated_img

    if exclude_roi:
        if isinstance(exclude_roi, tuple):
            exclude_roi = [exclude_roi]
        exclude_mask = np.ones_like(img) * 255
        for x1, y1, x2, y2 in exclude_roi:
            exclude_mask[y1:y2, x1:x2] = 0
        result_img = np.where(exclude_mask == 255, result_img, img)

    if output_path:
        cv2.imwrite(output_path, result_img)

    return result_img
