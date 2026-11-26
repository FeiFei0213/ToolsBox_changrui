"""在原图像素坐标系中显示、缩放和测距。"""

from math import floor

from PySide6.QtCore import QEvent, QLineF, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView


class ImageCanvas(QGraphicsView):
    coordinate_changed = Signal(object)
    zoom_changed = Signal(float)
    measurement_changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self._image = self.scene().addPixmap(QPixmap())
        self._image.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        self.setBackgroundBrush(QColor("#171e28"))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setAcceptDrops(False)
        self.viewport().setAcceptDrops(False)
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setAccessibleName("图片画布")
        self._fit = True
        self._crosshair = False
        self._measuring = False
        self._cursor_position: QPoint | None = None
        self._hover: QPoint | None = None
        self._points: list[QPoint] = []
        self._pan: tuple[Qt.MouseButton, QPoint] | None = None

    def set_image(self, pixmap: QPixmap):
        self._image.setPixmap(pixmap)
        self._set_hover(None)
        self.clear_measurement()
        self.fit_image()

    def fit_image(self):
        if not self._image.pixmap().isNull():
            self._fit = True
            self.resetTransform()
            self.setSceneRect(self._image.boundingRect())
            self.fitInView(self._image, Qt.AspectRatioMode.KeepAspectRatio)
            self.centerOn(self._image)
            self._refresh_hover()
            self.zoom_changed.emit(self.transform().m11())

    def actual_size(self):
        self._set_zoom(1.0, self.viewport().rect().center())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit:
            self.fit_image()
        else:
            origin = self.mapToScene(QPoint())
            self._update_scroll_bounds()
            self._pan_by(-self.mapFromScene(origin))
            self._refresh_hover()

    def _set_zoom(self, zoom: float, cursor: QPoint):
        if self._image.pixmap().isNull():
            return
        self._fit = False
        anchor = self.mapToScene(cursor)
        ratio = zoom / self.transform().m11()
        self.scale(ratio, ratio)
        self._update_scroll_bounds()
        self._pan_by(cursor - self.mapFromScene(anchor))
        self._refresh_hover()
        self.zoom_changed.emit(self.transform().m11())

    def _update_scroll_bounds(self):
        # 为缩放锚点保留平移空间。图像比视口窄时，Qt 否则会把它锁定在中心。
        scale = self.transform().m11()
        size = self.viewport().size()
        x_margin = max(0, size.width() - 1) / scale
        y_margin = max(0, size.height() - 1) / scale
        self.setSceneRect(self._image.boundingRect().adjusted(-x_margin, -y_margin, x_margin, y_margin))

    def _pan_by(self, delta: QPoint):
        horizontal = self.horizontalScrollBar()
        vertical = self.verticalScrollBar()
        horizontal.setValue(horizontal.value() - delta.x())
        vertical.setValue(vertical.value() - delta.y())

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120
        if not steps or self._image.pixmap().isNull():
            event.ignore()
            return
        self._cursor_position = event.position().toPoint()
        current = self.transform().m11()
        lower = min(current, 0.01)
        upper = max(current, 32.0)
        self._set_zoom(max(lower, min(upper, current * 1.25 ** steps)), self._cursor_position)
        event.accept()

    def set_crosshair(self, visible: bool):
        self._crosshair = visible
        self.viewport().update()

    def set_measuring(self, enabled: bool):
        self._measuring = enabled
        self.setDragMode(
            QGraphicsView.DragMode.NoDrag if enabled else QGraphicsView.DragMode.ScrollHandDrag
        )
        self.clear_measurement()

    def clear_measurement(self):
        self._points.clear()
        self.measurement_changed.emit(())
        self.viewport().update()

    def _pixel_at(self, position: QPoint) -> QPoint | None:
        point = self.mapToScene(position)
        bounds = self._image.boundingRect()
        if 0 <= point.x() < bounds.width() and 0 <= point.y() < bounds.height():
            return QPoint(floor(point.x()), floor(point.y()))
        return None

    def _set_hover(self, pixel: QPoint | None):
        if pixel != self._hover:
            self._hover = pixel
            self.coordinate_changed.emit(pixel)
            if self._crosshair:
                self.viewport().update()

    def _refresh_hover(self):
        position = self._cursor_position
        inside = position is not None and self.viewport().rect().contains(position)
        self._set_hover(self._pixel_at(position) if inside else None)

    def mousePressEvent(self, event):
        position = event.position().toPoint()
        button = event.button()
        if button in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._pan = (button, position)
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        elif button == Qt.MouseButton.LeftButton and self._measuring:
            pixel = self._pixel_at(position)
            if pixel is not None:
                if len(self._points) == 2:
                    self._points.clear()
                self._points.append(pixel)
                self.measurement_changed.emit(tuple(self._points))
                self.viewport().update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        position = event.position().toPoint()
        if self._pan is not None and not (event.buttons() & self._pan[0]):
            self._stop_pan()
        if self._pan is not None:
            button, previous = self._pan
            self._pan_by(position - previous)
            self._pan = (button, position)
            event.accept()
        else:
            super().mouseMoveEvent(event)
        self._cursor_position = position
        self._refresh_hover()

    def mouseReleaseEvent(self, event):
        if self._pan is not None and event.button() == self._pan[0]:
            self._stop_pan()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _stop_pan(self):
        self._pan = None
        self.viewport().unsetCursor()

    def viewportEvent(self, event):
        if event.type() == QEvent.Type.Leave:
            self._cursor_position = None
            self._set_hover(None)
        return super().viewportEvent(event)

    @staticmethod
    def _pixel_center(point: QPoint) -> QPointF:
        return QPointF(point.x() + 0.5, point.y() + 0.5)

    def drawForeground(self, painter: QPainter, rect):
        painter.save()
        if self._crosshair and self._hover is not None:
            bounds = self._image.boundingRect()
            point = self._pixel_center(self._hover)
            pen = QPen(QColor("#5ce1ff"), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLine(QLineF(0, point.y(), bounds.right(), point.y()))
            painter.drawLine(QLineF(point.x(), 0, point.x(), bounds.bottom()))

        if self._points:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor("#ffc85e"), 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            points = [self._pixel_center(point) for point in self._points]
            if len(points) == 2:
                painter.drawLine(QLineF(*points))
            radius = 4 / self.transform().m11()
            for point in points:
                painter.drawEllipse(point, radius, radius)
        painter.restore()
