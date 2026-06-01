import cv2
import numpy as np


def detect_ellipses(gray_img: np.ndarray, threshold: int | None = None,
                    min_area: int = 200, max_area: int = 500000) -> list[dict]:
    """Detect ellipses with sub-pixel accuracy using moments centroid + AMS fitting."""
    # 1. 二值化：threshold=None 时用 OTSU 自动，否则用固定值
    flag_inv = cv2.THRESH_BINARY_INV + (cv2.THRESH_OTSU if threshold is None else 0)
    flag     = cv2.THRESH_BINARY     + (cv2.THRESH_OTSU if threshold is None else 0)
    thr_val  = 0 if threshold is None else threshold
    _, binary_inv = cv2.threshold(gray_img, thr_val, 255, flag_inv)
    _, binary     = cv2.threshold(gray_img, thr_val, 255, flag)
    binary = binary_inv if np.sum(binary_inv == 255) < np.sum(binary == 255) else binary

    # 3. 提取轮廓（保留所有点，为椭圆拟合提供充足样本）
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    h, w = gray_img.shape[:2]
    results = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        if len(cnt) < 5:
            continue

        # 过滤触及 crop 边界的轮廓（ROI 边框 / 被裁切的圆）
        pts = cnt[:, 0, :]
        if np.any(pts[:, 0] == 0) or np.any(pts[:, 0] == w - 1) or \
           np.any(pts[:, 1] == 0) or np.any(pts[:, 1] == h - 1):
            continue

        # 几何过滤 1：圆度（轮廓面积 / 最小外接圆面积）
        (_, _), radius = cv2.minEnclosingCircle(cnt)
        circle_area = np.pi * radius * radius
        if circle_area > 0 and area / circle_area < 0.5:
            continue

        # 几何过滤 2：圆形度（4π·面积 / 周长²）
        perimeter = cv2.arcLength(cnt, True)
        if perimeter > 0 and 4 * np.pi * area / (perimeter ** 2) < 0.5:
            continue

        # --- 亚像素中心：矩方法（重心法），比拟合中心更稳定 ---
        # 在填充 mask 上计算，消除轮廓离散化偏差
        mask = np.zeros(gray_img.shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, [cnt], 0, 255, -1)
        M = cv2.moments(mask)
        if M['m00'] < 1:
            continue
        cx = M['m10'] / M['m00']
        cy = M['m01'] / M['m00']

        # --- 椭圆轴拟合：AMS 对噪声和离群点鲁棒 ---
        # 直接使用原始轮廓点（CHAIN_APPROX_NONE 已保留所有边缘点）
        # 注意：不用 cornerSubPix，该函数专为角点设计，用于圆形边缘会引入误差
        cnt_float = cnt.astype(np.float32)
        try:
            ellipse_data = cv2.fitEllipseAMS(cnt_float)
        except (AttributeError, cv2.error):
            ellipse_data = cv2.fitEllipse(cnt_float)

        (_, _), (minor, major), angle = ellipse_data

        if minor < 1 or major < 1:
            continue

        # cv2.fitEllipse angle = major axis rotation from vertical (Y-axis), clockwise
        if angle < 45 or angle > 135:
            y_axis = major
            x_axis = minor
        else:
            y_axis = minor
            x_axis = major

        if x_axis < 1:
            continue

        ratio = y_axis / x_axis
        if ratio > 10 or ratio < 0.1:
            continue

        results.append({
            "center": (cx, cy),
            "x_axis": x_axis,
            "y_axis": y_axis,
            "ratio": ratio,
            "angle": angle,
            "contour": cnt.reshape(-1, 2),  # shape (N,2), 原始像素级轮廓点
        })

    return results
