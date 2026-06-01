"""
point_picker_view.py — 线扫标定点标记视图。

左键单击添加标定点（自动编号），右键单击删除最近的点，
中键或左键拖拽空白区域平移视图，滚轮缩放。
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


_POINT_RADIUS = 6.0
_HIT_RADIUS = 12.0


class PointPickerView(QWidget):
    points_changed = Signal(list)            # list[dict{id, x, y}]
    mouse_pos_changed = Signal(float, float) # image-space (x, y); (-1,-1) = off image

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._img_w = 0
        self._img_h = 0
        self._zoom = 1.0
        self._view_cx = 0.0
        self._view_cy = 0.0

        self._points: list[dict] = []          # [{id, x, y}]
        self._next_id = 1
        self._real_coords: dict[int, tuple[float, float]] = {}

        self._panning = False
        self._last_pan = QPoint()
        self._dragging_point_idx: int | None = None
        self._drag_offset = QPointF()

        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ── Public API ────────────────────────────────────────────────────

    def load_image(self, bgr_array: np.ndarray) -> None:
        h, w = bgr_array.shape[:2]
        rgb = bgr_array[..., ::-1].copy()
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        self._pixmap = QPixmap.fromImage(qimg)
        self._img_w, self._img_h = w, h
        self._zoom = 1.0
        self._view_cx = w / 2
        self._view_cy = h / 2
        self.update()

    def get_points(self) -> list[dict]:
        return list(self._points)

    def set_points_silent(self, points: list[dict]) -> None:
        self._points = list(points)
        if points:
            self._next_id = max(p["id"] for p in points) + 1
        self.update()

    def clear_points(self) -> None:
        self._points.clear()
        self._next_id = 1
        self._real_coords.clear()
        self.update()
        self.points_changed.emit([])

    def set_real_coords(self, real_coords_by_id: dict[int, tuple[float, float]]) -> None:
        self._real_coords = dict(real_coords_by_id)
        self.update()

    # ── Mouse events ──────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._pixmap is None:
            return

        pos_widget = event.position()

        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._last_pan = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            # 检查是否点击到了已有的点（拖拽模式）
            idx = self._point_at(pos_widget)
            if idx is not None:
                self._dragging_point_idx = idx
                p = self._points[idx]
                pos_img = self._widget_to_image(pos_widget)
                self._drag_offset = QPointF(p["x"] - pos_img.x(), p["y"] - pos_img.y())
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return

            # 点击空白区域：添加新点
            if self._point_in_image(event.pos()):
                pos_img = self._widget_to_image(pos_widget)
                self._points.append({"id": self._next_id, "x": pos_img.x(), "y": pos_img.y()})
                self._next_id += 1
                self.update()
                self.points_changed.emit(list(self._points))
            else:
                # 图像外区域：平移
                self._panning = True
                self._last_pan = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)

        if event.button() == Qt.MouseButton.RightButton:
            # 右键删除最近的点
            idx = self._point_at(pos_widget, radius=_HIT_RADIUS * 2)
            if idx is not None:
                self._points.pop(idx)
                self.update()
                self.points_changed.emit(list(self._points))

    def mouseMoveEvent(self, event):
        pos_widget = event.position()

        if self._point_in_image(event.pos()):
            pos_img = self._widget_to_image(pos_widget)
            self.mouse_pos_changed.emit(pos_img.x(), pos_img.y())
        else:
            self.mouse_pos_changed.emit(-1.0, -1.0)

        if self._panning and self._last_pan is not None:
            delta = event.pos() - self._last_pan
            self._last_pan = event.pos()
            scale = self._fit_scale() * self._zoom
            self._view_cx -= delta.x() / scale
            self._view_cy -= delta.y() / scale
            self._clamp_view_center()
            self.update()
            return

        if self._dragging_point_idx is not None:
            pos_img = self._widget_to_image(pos_widget)
            p = self._points[self._dragging_point_idx]
            p["x"] = max(0.0, min(float(self._img_w), pos_img.x() + self._drag_offset.x()))
            p["y"] = max(0.0, min(float(self._img_h), pos_img.y() + self._drag_offset.y()))
            self.update()
            return

        # 更新光标：悬停在点上显示 SizeAllCursor
        if self._point_at(pos_widget) is not None:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.CrossCursor)

        if event.button() == Qt.MouseButton.LeftButton:
            if self._panning:
                self._panning = False
                self.setCursor(Qt.CursorShape.CrossCursor)
            if self._dragging_point_idx is not None:
                self.points_changed.emit(list(self._points))
                self._dragging_point_idx = None
                self.setCursor(Qt.CursorShape.CrossCursor)

    def leaveEvent(self, event):
        self.mouse_pos_changed.emit(-1.0, -1.0)
        super().leaveEvent(event)

    def wheelEvent(self, event):
        if self._pixmap is None:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        step = 1.15 if delta > 0 else 1 / 1.15
        new_zoom = min(20.0, max(1.0, self._zoom * step))
        if abs(new_zoom - self._zoom) < 1e-6:
            return

        old_scale, ox, oy = self._transform()
        cursor = event.position()
        img_x = (cursor.x() - ox) / old_scale
        img_y = (cursor.y() - oy) / old_scale
        self._zoom = new_zoom
        new_scale = self._fit_scale() * self._zoom
        self._view_cx = img_x - (cursor.x() - self.width() / 2) / new_scale
        self._view_cy = img_y - (cursor.y() - self.height() / 2) / new_scale
        self._clamp_view_center()
        self.update()
        event.accept()

    # ── Paint ─────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if self._pixmap is None:
            painter.fillRect(self.rect(), QColor(234, 236, 240))
            painter.setPen(QColor(150, 155, 165))
            font = painter.font()
            font.setPointSize(13)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "打开图片后点击标记标定点")
            return

        scale, ox, oy = self._transform()
        painter.drawPixmap(int(ox), int(oy), int(self._img_w * scale), int(self._img_h * scale), self._pixmap)

        # 绘制标定点
        label_font = QFont()
        label_font.setPointSize(9)
        label_font.setBold(True)

        for p in self._points:
            w_pt = self._image_to_widget(QPointF(p["x"], p["y"]))
            r = _POINT_RADIUS

            # 圆圈
            painter.setPen(QPen(QColor(0, 0, 0), 1.5))
            painter.setBrush(QColor(255, 80, 80, 220))
            painter.drawEllipse(w_pt, r, r)

            # 编号
            label = str(p["id"])
            painter.setFont(label_font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(label)
            lx = w_pt.x() - tw / 2
            ly = w_pt.y() - r - 4

            painter.setPen(QColor(0, 0, 0))
            for ddx, ddy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                painter.drawText(QPointF(lx + ddx, ly + ddy), label)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(QPointF(lx, ly), label)

            # 真实坐标
            real = self._real_coords.get(p["id"])
            if real:
                real_str = f"({real[0]:.2f}, {real[1]:.2f})"
                small_font = QFont()
                small_font.setPointSize(7)
                painter.setFont(small_font)
                painter.setPen(QColor(80, 200, 120))
                painter.drawText(QPointF(w_pt.x() + r + 4, w_pt.y() + 4), real_str)

    def resizeEvent(self, event):
        self.update()

    # ── Helpers ───────────────────────────────────────────────────────

    def _point_at(self, pos_widget: QPointF, radius: float = _HIT_RADIUS) -> int | None:
        for i, p in enumerate(self._points):
            w_pt = self._image_to_widget(QPointF(p["x"], p["y"]))
            if math.hypot(pos_widget.x() - w_pt.x(), pos_widget.y() - w_pt.y()) <= radius:
                return i
        return None

    def _transform(self):
        if self._pixmap is None or self._img_w == 0:
            return 1.0, 0.0, 0.0
        scale = self._fit_scale() * self._zoom
        self._clamp_view_center(scale)
        ww, wh = self.width(), self.height()
        ox = ww / 2 - self._view_cx * scale
        oy = wh / 2 - self._view_cy * scale
        draw_w = self._img_w * scale
        draw_h = self._img_h * scale
        ox = (ww - draw_w) / 2 if draw_w <= ww else min(0.0, max(ww - draw_w, ox))
        oy = (wh - draw_h) / 2 if draw_h <= wh else min(0.0, max(wh - draw_h, oy))
        return scale, ox, oy

    def _fit_scale(self) -> float:
        if self._pixmap is None or self._img_w == 0 or self._img_h == 0:
            return 1.0
        return min(max(1, self.width()) / self._img_w, max(1, self.height()) / self._img_h)

    def _clamp_view_center(self, scale: float | None = None):
        if self._pixmap is None or self._img_w == 0 or self._img_h == 0:
            return
        scale = scale or (self._fit_scale() * self._zoom)
        ww, wh = self.width(), self.height()
        half_w = ww / (2 * scale)
        half_h = wh / (2 * scale)
        self._view_cx = self._img_w / 2 if self._img_w * scale <= ww else min(self._img_w - half_w, max(half_w, self._view_cx))
        self._view_cy = self._img_h / 2 if self._img_h * scale <= wh else min(self._img_h - half_h, max(half_h, self._view_cy))

    def _image_rect(self):
        from PySide6.QtCore import QRect
        scale, ox, oy = self._transform()
        return QRect(int(round(ox)), int(round(oy)), int(round(self._img_w * scale)), int(round(self._img_h * scale)))

    def _point_in_image(self, point: QPoint) -> bool:
        return self._pixmap is not None and self._image_rect().contains(point)

    def _widget_to_image(self, pt: QPointF) -> QPointF:
        scale, ox, oy = self._transform()
        return QPointF(
            min(float(self._img_w), max(0.0, (pt.x() - ox) / scale)),
            min(float(self._img_h), max(0.0, (pt.y() - oy) / scale)),
        )

    def _image_to_widget(self, pt: QPointF) -> QPointF:
        scale, ox, oy = self._transform()
        return QPointF(ox + pt.x() * scale, oy + pt.y() * scale)
