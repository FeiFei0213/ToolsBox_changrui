from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget


@dataclass
class RotatedRoi:
    center_x: float
    center_y: float
    width: float
    height: float
    angle_deg: float = 0.0

    def is_valid(self) -> bool:
        return self.width > 5 and self.height > 5


class ImageView(QWidget):
    roi_selected = Signal(object)            # emits RotatedRoi in image coordinates
    mouse_pos_changed = Signal(float, float) # image-space (x, y); (-1,-1) = off image

    _HANDLE_RADIUS = 6.0
    _ROTATE_HANDLE_DISTANCE = 26.0
    _MIN_ROI_SIZE = 8.0
    _RESIZE_HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")
    _HANDLE_FACTORS = {
        "nw": (-1, -1), "n": (0, -1), "ne": (1, -1), "e": (1, 0),
        "se": (1, 1),   "s": (0, 1),  "sw": (-1, 1), "w": (-1, 0),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._img_w = 0
        self._img_h = 0
        self._zoom = 1.0
        self._view_cx = 0.0
        self._view_cy = 0.0
        self._detected_ellipses: list[dict] = []

        self._drawing = False
        self._rotating = False
        self._moving = False
        self._resizing = False
        self._active_resize_handle: str | None = None
        self._move_offset = QPointF()
        self._resize_anchor = QPointF()

        self._start_widget = QPoint()
        self._end_widget = QPoint()
        self._roi_image: RotatedRoi | None = None

        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def load_image(self, bgr_array: np.ndarray):
        h, w = bgr_array.shape[:2]
        rgb = bgr_array[..., ::-1].copy()
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        self._pixmap = QPixmap.fromImage(qimg)
        self._img_w, self._img_h = w, h
        self._zoom = 1.0
        self._view_cx = w / 2
        self._view_cy = h / 2
        self._reset_interaction_state()
        self._roi_image = None
        self.clear_detected_ellipses()
        self.update()

    def clear_roi(self):
        self._roi_image = None
        self._reset_interaction_state()
        self.clear_detected_ellipses()
        self._update_cursor()
        self.update()

    def roi_in_image_coords(self) -> RotatedRoi | None:
        return self._roi_image

    def set_detected_ellipses(self, ellipses: list[dict]):
        self._detected_ellipses = ellipses
        self.update()

    def clear_detected_ellipses(self):
        self._detected_ellipses = []
        self.update()

    # ------------------------------------------------------------------ #
    # Mouse events
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event):
        if self._pixmap is None or event.button() != Qt.MouseButton.LeftButton:
            return

        pos_widget = event.position()
        pos_image = self._widget_point_to_image_point(pos_widget)

        if self._roi_image is not None:
            if self._point_hits_rotate_handle(pos_widget):
                self._reset_interaction_state()
                self._rotating = True
                self._update_roi_rotation(pos_widget)
                return

            resize_handle = self._resize_handle_at(pos_widget)
            if resize_handle is not None:
                self._reset_interaction_state()
                self._resizing = True
                self._active_resize_handle = resize_handle
                self._resize_anchor = self._opposite_anchor_point(self._roi_image, resize_handle)
                self._update_roi_resize(pos_image)
                return

            if self._point_in_roi(pos_image, self._roi_image):
                self._reset_interaction_state()
                self._moving = True
                self._move_offset = QPointF(
                    self._roi_image.center_x - pos_image.x(),
                    self._roi_image.center_y - pos_image.y(),
                )
                self._update_cursor(pos_widget)
                return

        if self._point_in_image(event.pos()):
            self._reset_interaction_state()
            self._drawing = True
            clamped = self._clamp_point_to_image(event.pos())
            self._start_widget = clamped
            self._end_widget = clamped

    def mouseMoveEvent(self, event):
        pos_widget = event.position()
        pos_image = self._widget_point_to_image_point(pos_widget)

        if self._point_in_image(event.pos()):
            self.mouse_pos_changed.emit(pos_image.x(), pos_image.y())
        else:
            self.mouse_pos_changed.emit(-1.0, -1.0)

        if self._drawing:
            self._end_widget = self._clamp_point_to_image(event.pos())
            self.update()
            return

        if self._rotating and self._roi_image is not None:
            self._update_roi_rotation(pos_widget)
            return

        if self._moving and self._roi_image is not None:
            self._update_roi_move(pos_image)
            return

        if self._resizing and self._roi_image is not None:
            self._update_roi_resize(pos_image)
            return

        self._update_cursor(pos_widget)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._drawing:
            self._drawing = False
            self._end_widget = self._clamp_point_to_image(event.pos())
            roi_img = self._widget_rect_to_image_roi(
                QRect(self._start_widget, self._end_widget).normalized()
            )
            self._roi_image = roi_img if roi_img and roi_img.is_valid() else None
            self.update()
            if self._roi_image is not None:
                self.roi_selected.emit(self._copy_roi(self._roi_image))

        self._rotating = False
        self._moving = False
        self._resizing = False
        self._active_resize_handle = None
        self._update_cursor(event.position())

    def leaveEvent(self, event):
        self.mouse_pos_changed.emit(-1.0, -1.0)
        self._update_cursor()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        if self._pixmap is None:
            return

        delta = event.angleDelta().y()
        if delta == 0:
            return

        scale_step = 1.15 if delta > 0 else 1 / 1.15
        new_zoom = min(20.0, max(1.0, self._zoom * scale_step))
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
        self._clamp_view_center(new_scale)
        self.update()
        event.accept()

    # ------------------------------------------------------------------ #
    # Painting
    # ------------------------------------------------------------------ #
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._pixmap is None:
            painter.fillRect(self.rect(), QColor(234, 236, 240))
            pen = QPen(QColor(180, 185, 195), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            margin = 24
            painter.drawRoundedRect(
                self.rect().adjusted(margin, margin, -margin, -margin), 12, 12
            )
            painter.setPen(QColor(150, 155, 165))
            font = painter.font()
            font.setPointSize(13)
            painter.setFont(font)
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Open an image and drag to create ROI",
            )
            return

        scale, ox, oy = self._transform()
        draw_w = int(self._img_w * scale)
        draw_h = int(self._img_h * scale)
        painter.drawPixmap(int(ox), int(oy), draw_w, draw_h, self._pixmap)

        if self._drawing:
            preview = QRect(self._start_widget, self._end_widget).normalized()
            self._draw_preview_roi(painter, preview)
        elif self._roi_image is not None:
            self._draw_rotated_roi(painter, self._roi_image)

        if self._detected_ellipses:
            self._draw_detected_ellipses(painter, scale)

        self._draw_axes(painter, int(ox), int(oy), draw_w, draw_h)

    def resizeEvent(self, event):
        self.update()

    # ------------------------------------------------------------------ #
    # ROI interaction
    # ------------------------------------------------------------------ #
    def _update_roi_rotation(self, pos_widget: QPointF):
        if self._roi_image is None:
            return

        center_widget = self._image_point_to_widget_point(
            QPointF(self._roi_image.center_x, self._roi_image.center_y)
        )
        dx = pos_widget.x() - center_widget.x()
        dy = pos_widget.y() - center_widget.y()
        if math.hypot(dx, dy) < 1e-6:
            return

        self._roi_image.angle_deg = math.degrees(math.atan2(dy, dx)) + 90.0
        self._emit_roi_updated()
        self.update()

    def _update_roi_move(self, pos_image: QPointF):
        if self._roi_image is None:
            return

        self._roi_image.center_x = self._clamp_float(
            pos_image.x() + self._move_offset.x(), 0.0, float(self._img_w)
        )
        self._roi_image.center_y = self._clamp_float(
            pos_image.y() + self._move_offset.y(), 0.0, float(self._img_h)
        )
        self._emit_roi_updated()
        self.update()

    def _update_roi_resize(self, pos_image: QPointF):
        if self._roi_image is None or self._active_resize_handle is None:
            return

        x_factor, y_factor = self._HANDLE_FACTORS[self._active_resize_handle]
        local_x, local_y = self._world_delta_to_local(
            pos_image.x() - self._resize_anchor.x(),
            pos_image.y() - self._resize_anchor.y(),
            self._roi_image.angle_deg,
        )

        width = self._roi_image.width
        height = self._roi_image.height

        if x_factor != 0:
            width = max(self._MIN_ROI_SIZE, x_factor * local_x)
        if y_factor != 0:
            height = max(self._MIN_ROI_SIZE, y_factor * local_y)

        center_dx = x_factor * width / 2.0 if x_factor != 0 else 0.0
        center_dy = y_factor * height / 2.0 if y_factor != 0 else 0.0
        world_dx, world_dy = self._local_delta_to_world(
            center_dx, center_dy, self._roi_image.angle_deg
        )

        self._roi_image.center_x = self._resize_anchor.x() + world_dx
        self._roi_image.center_y = self._resize_anchor.y() + world_dy
        self._roi_image.width = width
        self._roi_image.height = height
        self._emit_roi_updated()
        self.update()

    def _emit_roi_updated(self):
        if self._roi_image is not None and self._roi_image.is_valid():
            self.roi_selected.emit(self._copy_roi(self._roi_image))

    def _reset_interaction_state(self):
        self._drawing = False
        self._rotating = False
        self._moving = False
        self._resizing = False
        self._active_resize_handle = None

    # ------------------------------------------------------------------ #
    # Painting helpers
    # ------------------------------------------------------------------ #
    def _draw_preview_roi(self, painter: QPainter, rect: QRect):
        painter.fillRect(rect, QColor(0, 120, 255, 40))
        painter.setPen(QPen(QColor(0, 120, 255), 2, Qt.PenStyle.SolidLine))
        painter.drawRect(rect)

    def _draw_rotated_roi(self, painter: QPainter, roi: RotatedRoi):
        polygon = self._roi_polygon_in_widget(roi)
        if polygon.isEmpty():
            return

        painter.save()
        painter.setBrush(QColor(0, 120, 255, 40))
        painter.setPen(QPen(QColor(0, 120, 255), 2, Qt.PenStyle.SolidLine))
        painter.drawPolygon(polygon)

        top_center = self._edge_center(polygon, 0, 1)
        rotate_handle = self._rotate_handle_point(polygon)
        painter.drawLine(top_center, rotate_handle)

        for handle_name in self._RESIZE_HANDLES:
            handle_center = self._resize_handle_point(roi, handle_name)
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(handle_center, self._HANDLE_RADIUS, self._HANDLE_RADIUS)

        rotate_fill = QColor(255, 255, 255) if self._rotating else QColor(0, 120, 255)
        painter.setBrush(rotate_fill)
        painter.drawEllipse(rotate_handle, self._HANDLE_RADIUS + 1, self._HANDLE_RADIUS + 1)
        painter.restore()

    def _draw_axes(self, painter: QPainter, ox: int, oy: int, dw: int, dh: int):
        arrow_len = 44
        head_len = 8
        head_w = 4
        line_w = 2.0
        pad = 12

        box_w, box_h = 88, 88
        box_x = ox + 10
        box_y = oy + 10
        origin_x = box_x + pad + 4
        origin_y = box_y + box_h - pad

        painter.save()
        painter.setBrush(QBrush(QColor(0, 0, 0, 110)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRect(box_x, box_y, box_w, box_h), 8, 8)
        painter.restore()

        font = QFont()
        font.setPointSize(8)
        font.setBold(True)

        def draw_arrow(x0, y0, x1, y1, color, label, label_dx, label_dy):
            painter.save()
            pen = QPen(QColor(*color), line_w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(x0, y0), QPointF(x1, y1))

            dx, dy = x1 - x0, y1 - y0
            length = math.hypot(dx, dy)
            ux, uy = dx / length, dy / length
            px, py = -uy, ux

            tip = QPointF(x1, y1)
            base = QPointF(x1 - ux * head_len, y1 - uy * head_len)
            p1 = QPointF(base.x() + px * head_w, base.y() + py * head_w)
            p2 = QPointF(base.x() - px * head_w, base.y() - py * head_w)
            painter.setBrush(QBrush(QColor(*color)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(QPolygonF([tip, p1, p2]))

            painter.setFont(font)
            painter.setPen(QColor(*color))
            painter.drawText(QPointF(x1 + label_dx, y1 + label_dy), label)
            painter.restore()

        draw_arrow(origin_x, origin_y, origin_x + arrow_len, origin_y, (80, 200, 120), "X", -6, 14)
        draw_arrow(origin_x, origin_y, origin_x, origin_y - arrow_len, (100, 160, 255), "Y", 6, 4)

    def _draw_detected_ellipses(self, painter: QPainter, scale: float):
        if not self._detected_ellipses:
            return

        red_pen = QPen(QColor(255, 0, 0), 3, Qt.PenStyle.SolidLine)
        red_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(red_pen)
        for e in self._detected_ellipses:
            pts = e.get('contour_points')
            if pts:
                poly = QPolygonF([
                    self._image_point_to_widget_point(QPointF(px, py))
                    for (px, py) in pts
                ])
                painter.drawPoints(poly)

        painter.setPen(QPen(QColor(0, 255, 0), 2, Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        label_font = QFont()
        label_font.setPointSize(9)
        label_font.setBold(True)
        for idx, e in enumerate(self._detected_ellipses):
            center = self._image_point_to_widget_point(QPointF(e['center_x'], e['center_y']))
            ry = max(e['x_axis'], e['y_axis']) / 2.0 * scale
            rx = min(e['x_axis'], e['y_axis']) / 2.0 * scale
            painter.save()
            painter.translate(center.x(), center.y())
            painter.rotate(e['angle_deg'])
            painter.drawEllipse(QRectF(-rx, -ry, 2 * rx, 2 * ry))
            painter.restore()

            label = str(idx + 1)
            painter.setFont(label_font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(label)
            th = fm.ascent()
            lx = center.x() - tw / 2
            ly = center.y() + th / 2
            painter.setPen(QColor(0, 0, 0))
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                painter.drawText(QPointF(lx + dx, ly + dy), label)
            painter.setPen(QColor(255, 255, 0))
            painter.drawText(QPointF(lx, ly), label)
            painter.setPen(QPen(QColor(0, 255, 0), 2, Qt.PenStyle.SolidLine))

    # ------------------------------------------------------------------ #
    # Hit testing and cursor
    # ------------------------------------------------------------------ #
    def _update_cursor(self, pos_widget: QPointF | None = None):
        if self._rotating or self._moving:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self._resizing and self._active_resize_handle is not None:
            self.setCursor(self._cursor_for_resize_handle(self._active_resize_handle))
            return

        if pos_widget is None or self._roi_image is None:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return

        if self._point_hits_rotate_handle(pos_widget):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return

        resize_handle = self._resize_handle_at(pos_widget)
        if resize_handle is not None:
            self.setCursor(self._cursor_for_resize_handle(resize_handle))
            return

        pos_image = self._widget_point_to_image_point(pos_widget)
        if self._point_in_roi(pos_image, self._roi_image):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            return

        self.setCursor(Qt.CursorShape.CrossCursor)

    def _resize_handle_at(self, pos_widget: QPointF) -> str | None:
        if self._roi_image is None:
            return None
        for handle_name in self._RESIZE_HANDLES:
            center = self._resize_handle_point(self._roi_image, handle_name)
            if self._distance(pos_widget, center) <= self._HANDLE_RADIUS + 4:
                return handle_name
        return None

    def _point_hits_rotate_handle(self, pos_widget: QPointF) -> bool:
        if self._roi_image is None:
            return False
        handle = self._rotate_handle_point(self._roi_polygon_in_widget(self._roi_image))
        return self._distance(pos_widget, handle) <= self._HANDLE_RADIUS + 5

    def _point_in_roi(self, pos_image: QPointF, roi: RotatedRoi) -> bool:
        local_x, local_y = self._image_point_to_roi_local(pos_image, roi)
        return abs(local_x) <= roi.width / 2.0 and abs(local_y) <= roi.height / 2.0

    def _cursor_for_resize_handle(self, handle_name: str) -> Qt.CursorShape:
        if handle_name in {"nw", "se"}:
            return Qt.CursorShape.SizeFDiagCursor
        if handle_name in {"ne", "sw"}:
            return Qt.CursorShape.SizeBDiagCursor
        if handle_name in {"e", "w"}:
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    # ------------------------------------------------------------------ #
    # Geometry
    # ------------------------------------------------------------------ #
    def _widget_rect_to_image_roi(self, rect: QRect) -> RotatedRoi | None:
        if rect.width() <= 0 or rect.height() <= 0:
            return None
        top_left = self._widget_point_to_image_point(QPointF(rect.left(), rect.top()))
        bottom_right = self._widget_point_to_image_point(
            QPointF(rect.left() + rect.width(), rect.top() + rect.height())
        )
        x1, x2 = sorted((top_left.x(), bottom_right.x()))
        y1, y2 = sorted((top_left.y(), bottom_right.y()))
        return RotatedRoi(
            center_x=(x1 + x2) / 2.0, center_y=(y1 + y2) / 2.0,
            width=max(0.0, x2 - x1), height=max(0.0, y2 - y1), angle_deg=0.0,
        )

    def _roi_polygon_in_widget(self, roi: RotatedRoi) -> QPolygonF:
        return QPolygonF(
            [self._image_point_to_widget_point(p) for p in self._roi_corners_in_image(roi)]
        )

    def _roi_corners_in_image(self, roi: RotatedRoi) -> list[QPointF]:
        half_w, half_h = roi.width / 2.0, roi.height / 2.0
        return [self._roi_local_to_image(p, roi) for p in [
            QPointF(-half_w, -half_h), QPointF(half_w, -half_h),
            QPointF(half_w, half_h),   QPointF(-half_w, half_h),
        ]]

    def _resize_handle_point(self, roi: RotatedRoi, handle_name: str) -> QPointF:
        x_factor, y_factor = self._HANDLE_FACTORS[handle_name]
        local = QPointF(x_factor * roi.width / 2.0, y_factor * roi.height / 2.0)
        return self._image_point_to_widget_point(self._roi_local_to_image(local, roi))

    def _opposite_anchor_point(self, roi: RotatedRoi, handle_name: str) -> QPointF:
        x_factor, y_factor = self._HANDLE_FACTORS[handle_name]
        local = QPointF(-x_factor * roi.width / 2.0, -y_factor * roi.height / 2.0)
        return self._roi_local_to_image(local, roi)

    def _rotate_handle_point(self, polygon: QPolygonF) -> QPointF:
        top_center = self._edge_center(polygon, 0, 1)
        center = self._polygon_center(polygon)
        vx = top_center.x() - center.x()
        vy = top_center.y() - center.y()
        length = math.hypot(vx, vy)
        if length < 1e-6:
            return top_center
        return QPointF(
            top_center.x() + vx / length * self._ROTATE_HANDLE_DISTANCE,
            top_center.y() + vy / length * self._ROTATE_HANDLE_DISTANCE,
        )

    def _image_point_to_roi_local(self, point: QPointF, roi: RotatedRoi) -> tuple[float, float]:
        return self._world_delta_to_local(
            point.x() - roi.center_x, point.y() - roi.center_y, roi.angle_deg,
        )

    def _roi_local_to_image(self, point: QPointF, roi: RotatedRoi) -> QPointF:
        world_dx, world_dy = self._local_delta_to_world(point.x(), point.y(), roi.angle_deg)
        return QPointF(roi.center_x + world_dx, roi.center_y + world_dy)

    @staticmethod
    def _world_delta_to_local(dx: float, dy: float, angle_deg: float) -> tuple[float, float]:
        angle = math.radians(angle_deg)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        return dx * cos_a + dy * sin_a, -dx * sin_a + dy * cos_a

    @staticmethod
    def _local_delta_to_world(lx: float, ly: float, angle_deg: float) -> tuple[float, float]:
        angle = math.radians(angle_deg)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        return lx * cos_a - ly * sin_a, lx * sin_a + ly * cos_a

    @staticmethod
    def _edge_center(polygon: QPolygonF, ia: int, ib: int) -> QPointF:
        pa, pb = polygon[ia], polygon[ib]
        return QPointF((pa.x() + pb.x()) / 2.0, (pa.y() + pb.y()) / 2.0)

    @staticmethod
    def _polygon_center(polygon: QPolygonF) -> QPointF:
        xs = [p.x() for p in polygon]
        ys = [p.y() for p in polygon]
        return QPointF(sum(xs) / len(xs), sum(ys) / len(ys))

    @staticmethod
    def _copy_roi(roi: RotatedRoi) -> RotatedRoi:
        return RotatedRoi(roi.center_x, roi.center_y, roi.width, roi.height, roi.angle_deg)

    @staticmethod
    def _distance(a: QPointF, b: QPointF) -> float:
        return math.hypot(a.x() - b.x(), a.y() - b.y())

    @staticmethod
    def _clamp_float(value: float, lo: float, hi: float) -> float:
        return min(hi, max(lo, value))

    # ------------------------------------------------------------------ #
    # View transform
    # ------------------------------------------------------------------ #
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
        if draw_w <= ww:
            ox = (ww - draw_w) / 2
        else:
            ox = min(0.0, max(ww - draw_w, ox))
        if draw_h <= wh:
            oy = (wh - draw_h) / 2
        else:
            oy = min(0.0, max(wh - draw_h, oy))
        return scale, ox, oy

    def _fit_scale(self) -> float:
        if self._pixmap is None or self._img_w == 0 or self._img_h == 0:
            return 1.0
        ww, wh = max(1, self.width()), max(1, self.height())
        return min(ww / self._img_w, wh / self._img_h)

    def _clamp_view_center(self, scale: float | None = None):
        if self._pixmap is None or self._img_w == 0 or self._img_h == 0:
            return
        scale = scale or (self._fit_scale() * self._zoom)
        ww, wh = self.width(), self.height()
        half_w = ww / (2 * scale)
        half_h = wh / (2 * scale)
        self._view_cx = self._img_w / 2 if self._img_w * scale <= ww else min(self._img_w - half_w, max(half_w, self._view_cx))
        self._view_cy = self._img_h / 2 if self._img_h * scale <= wh else min(self._img_h - half_h, max(half_h, self._view_cy))

    def _image_rect(self) -> QRect:
        scale, ox, oy = self._transform()
        return QRect(int(round(ox)), int(round(oy)), int(round(self._img_w * scale)), int(round(self._img_h * scale)))

    def _point_in_image(self, point: QPoint) -> bool:
        return self._pixmap is not None and self._image_rect().contains(point)

    def _clamp_point_to_image(self, point: QPoint) -> QPoint:
        rect = self._image_rect()
        return QPoint(min(rect.right(), max(rect.left(), point.x())), min(rect.bottom(), max(rect.top(), point.y())))

    def _widget_point_to_image_point(self, point: QPointF) -> QPointF:
        scale, ox, oy = self._transform()
        return QPointF(
            self._clamp_float((point.x() - ox) / scale, 0.0, float(self._img_w)),
            self._clamp_float((point.y() - oy) / scale, 0.0, float(self._img_h)),
        )

    def _image_point_to_widget_point(self, point: QPointF) -> QPointF:
        scale, ox, oy = self._transform()
        return QPointF(ox + point.x() * scale, oy + point.y() * scale)
