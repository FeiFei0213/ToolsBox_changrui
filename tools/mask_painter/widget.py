"""Mask 手绘编辑器界面。"""

from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from tool_base import ToolBase
from tools.mask_painter.core import (
    apply_mask_to_image,
    create_blank_mask,
    draw_stroke,
    normalize_mask,
    read_image,
    write_image,
)


IMAGE_FILTER = "图片文件 (*.png *.jpg *.jpeg *.bmp *.tiff *.tif)"
MASK_FILTER = "无损 Mask 图片 (*.png *.bmp *.tiff *.tif)"


class MaskCanvas(QGraphicsView):
    """显示原图和半透明 Mask，处理绘制、缩放、平移与历史记录。"""

    mask_changed = Signal()
    history_changed = Signal(bool, bool)
    cursor_moved = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.original: np.ndarray | None = None
        self.mask: np.ndarray | None = None
        self.brush_color = 0
        self.brush_width = 20
        self.overlay_opacity = 0.45
        self._last_point: tuple[int, int] | None = None
        self._undo_stack: list[np.ndarray] = []
        self._redo_stack: list[np.ndarray] = []
        self._panning = False
        self._pan_start: QPointF | None = None

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setZValue(0)
        self._scene.addItem(self._pixmap_item)
        self._cursor_item = self._scene.addEllipse(
            QRectF(), QPen(QColor(255, 80, 80), 1.5), QBrush(Qt.BrushStyle.NoBrush)
        )
        self._cursor_item.setZValue(10)
        self._cursor_item.hide()

        self.setBackgroundBrush(QBrush(QColor(32, 34, 38)))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumSize(560, 420)

    def set_images(self, original: np.ndarray, mask: np.ndarray) -> None:
        self.original = original.copy()
        self.mask = mask.copy()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._last_point = None
        self._render()
        self.history_changed.emit(False, False)
        QTimer.singleShot(0, self.fit_image)

    def set_brush(self, color: int, width: int) -> None:
        self.brush_color = color
        self.brush_width = width
        pen_color = QColor(255, 80, 80) if color == 255 else QColor(255, 215, 0)
        self._cursor_item.setPen(QPen(pen_color, 1.5))

    def set_overlay_opacity(self, percent: int) -> None:
        self.overlay_opacity = percent / 100.0
        self._render()

    def _push_undo(self) -> None:
        if self.mask is None:
            return
        self._undo_stack.append(self.mask.copy())
        if len(self._undo_stack) > 30:
            del self._undo_stack[0]
        self._redo_stack.clear()
        self.history_changed.emit(True, False)

    def begin_stroke(self, point: tuple[int, int]) -> None:
        if self.mask is None:
            return
        self._push_undo()
        self._last_point = point
        draw_stroke(self.mask, point, point, self.brush_color, self.brush_width)
        self._render()

    def continue_stroke(self, point: tuple[int, int]) -> None:
        if self.mask is None or self._last_point is None:
            return
        draw_stroke(self.mask, self._last_point, point, self.brush_color, self.brush_width)
        self._last_point = point
        self._render()

    def end_stroke(self) -> None:
        if self._last_point is not None:
            self.mask_changed.emit()
        self._last_point = None

    def undo(self) -> None:
        if self.mask is None or not self._undo_stack:
            return
        self._redo_stack.append(self.mask.copy())
        self.mask = self._undo_stack.pop()
        self._render()
        self.mask_changed.emit()
        self.history_changed.emit(bool(self._undo_stack), True)

    def redo(self) -> None:
        if self.mask is None or not self._redo_stack:
            return
        self._undo_stack.append(self.mask.copy())
        self.mask = self._redo_stack.pop()
        self._render()
        self.mask_changed.emit()
        self.history_changed.emit(True, bool(self._redo_stack))

    def invert_mask(self) -> None:
        if self.mask is None:
            return
        self._push_undo()
        self.mask = 255 - self.mask
        self._render()
        self.mask_changed.emit()

    def fill_mask(self, color: int) -> None:
        if self.mask is None:
            return
        self._push_undo()
        self.mask.fill(color)
        self._render()
        self.mask_changed.emit()

    def fit_image(self) -> None:
        if self._pixmap_item.pixmap().isNull():
            return
        self.resetTransform()
        self.fitInView(
            self._pixmap_item.boundingRect(),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def _display_rgb(self) -> np.ndarray:
        if self.original is None:
            raise ValueError("未加载原图")
        if self.original.ndim == 2:
            return cv2.cvtColor(self.original, cv2.COLOR_GRAY2RGB)
        if self.original.shape[2] == 4:
            return cv2.cvtColor(self.original, cv2.COLOR_BGRA2RGB)
        return cv2.cvtColor(self.original, cv2.COLOR_BGR2RGB)

    def _render(self) -> None:
        if self.original is None or self.mask is None:
            return
        original_rgb = self._display_rgb()
        mask_rgb = cv2.cvtColor(self.mask, cv2.COLOR_GRAY2RGB)
        display = cv2.addWeighted(
            original_rgb,
            1.0 - self.overlay_opacity,
            mask_rgb,
            self.overlay_opacity,
            0,
        )
        height, width, channels = display.shape
        image = QImage(
            display.data,
            width,
            height,
            channels * width,
            QImage.Format.Format_RGB888,
        ).copy()
        self._pixmap_item.setPixmap(QPixmap.fromImage(image))
        self._scene.setSceneRect(QRectF(0, 0, width, height))

    def _image_point(self, viewport_position: QPointF) -> tuple[int, int] | None:
        if self.mask is None:
            return None
        scene_position = self.mapToScene(viewport_position.toPoint())
        x = int(round(scene_position.x()))
        y = int(round(scene_position.y()))
        height, width = self.mask.shape
        if 0 <= x < width and 0 <= y < height:
            return x, y
        return None

    def _update_brush_cursor(self, viewport_position: QPointF) -> None:
        if self.mask is None:
            self._cursor_item.hide()
            return
        scene_position = self.mapToScene(viewport_position.toPoint())
        radius = self.brush_width / 2.0
        self._cursor_item.setRect(
            scene_position.x() - radius,
            scene_position.y() - radius,
            self.brush_width,
            self.brush_width,
        )
        self._cursor_item.show()

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            point = self._image_point(event.position())
            if point is not None:
                self.begin_stroke(point)
                event.accept()
                return
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._update_brush_cursor(event.position())
        point = self._image_point(event.position())
        if point is not None:
            self.cursor_moved.emit(*point)
        if self._panning and self._pan_start is not None:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                int(self.horizontalScrollBar().value() - delta.x())
            )
            self.verticalScrollBar().setValue(
                int(self.verticalScrollBar().value() - delta.y())
            )
            event.accept()
            return
        if event.buttons() & Qt.MouseButton.LeftButton and point is not None:
            self.continue_stroke(point)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.end_stroke()
            event.accept()
            return
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._panning = False
            self._pan_start = None
            self.setCursor(Qt.CursorShape.CrossCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self._cursor_item.hide()
        super().leaveEvent(event)


class MaskPainterWidget(ToolBase):
    tool_name = "Mask 手绘编辑器"
    tool_description = "用黑白画笔绘制或微调 Mask，并导出覆盖后的原图"
    tool_icon = "🖌️"

    def init_ui(self):
        self.resize(1120, 760)
        self.setMinimumSize(900, 620)
        self.source_path = ""
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(8)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        controls = QWidget()
        controls.setMinimumWidth(285)
        controls.setMaximumWidth(350)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 8, 0)
        controls_layout.setSpacing(8)
        splitter.addWidget(controls)

        file_group = QGroupBox("图片与 Mask")
        file_layout = QVBoxLayout(file_group)
        self.open_image_btn = QPushButton("打开原图…")
        self.open_image_btn.clicked.connect(self._open_original)
        self.source_label = QLabel("尚未加载原图")
        self.source_label.setWordWrap(True)
        self.source_label.setStyleSheet("color:#666; font-size:11px;")
        self.load_mask_btn = QPushButton("加载已有 Mask…")
        self.load_mask_btn.clicked.connect(self._open_mask)
        self.new_background_combo = QComboBox()
        self.new_background_combo.addItem("纯白背景", 255)
        self.new_background_combo.addItem("纯黑背景", 0)
        self.new_mask_btn = QPushButton("新建空白 Mask")
        self.new_mask_btn.clicked.connect(self._new_blank_mask)
        file_layout.addWidget(self.open_image_btn)
        file_layout.addWidget(self.source_label)
        file_layout.addWidget(self.load_mask_btn)
        blank_row = QHBoxLayout()
        blank_row.addWidget(self.new_background_combo, 1)
        blank_row.addWidget(self.new_mask_btn)
        file_layout.addLayout(blank_row)
        controls_layout.addWidget(file_group)

        brush_group = QGroupBox("画笔")
        brush_form = QFormLayout(brush_group)
        self.brush_color_combo = QComboBox()
        self.brush_color_combo.addItem("黑色画笔", 0)
        self.brush_color_combo.addItem("白色画笔", 255)
        self.brush_width_spin = QSpinBox()
        self.brush_width_spin.setRange(1, 300)
        self.brush_width_spin.setValue(20)
        self.brush_width_spin.setSuffix(" px")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(45)
        self.opacity_value = QLabel("45%")
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value)
        brush_form.addRow("颜色:", self.brush_color_combo)
        brush_form.addRow("宽度:", self.brush_width_spin)
        brush_form.addRow("Mask 透明度:", opacity_row)
        controls_layout.addWidget(brush_group)

        edit_group = QGroupBox("编辑")
        edit_layout = QVBoxLayout(edit_group)
        history_row = QHBoxLayout()
        self.undo_btn = QPushButton("撤销")
        self.redo_btn = QPushButton("重做")
        history_row.addWidget(self.undo_btn)
        history_row.addWidget(self.redo_btn)
        fill_row = QHBoxLayout()
        self.fill_black_btn = QPushButton("全部填黑")
        self.fill_white_btn = QPushButton("全部填白")
        fill_row.addWidget(self.fill_black_btn)
        fill_row.addWidget(self.fill_white_btn)
        self.invert_btn = QPushButton("黑白反转")
        edit_layout.addLayout(history_row)
        edit_layout.addLayout(fill_row)
        edit_layout.addWidget(self.invert_btn)
        controls_layout.addWidget(edit_group)

        export_group = QGroupBox("导出")
        export_layout = QVBoxLayout(export_group)
        self.export_mask_btn = QPushButton("导出当前 Mask…")
        self.keep_combo = QComboBox()
        self.keep_combo.addItem("保留黑色区域", 0)
        self.keep_combo.addItem("保留白色区域", 255)
        self.fill_combo = QComboBox()
        self.fill_combo.addItem("其余填充白色", 255)
        self.fill_combo.addItem("其余填充黑色", 0)
        self.export_result_btn = QPushButton("导出覆盖后的原图…")
        self.export_result_btn.setStyleSheet(
            "QPushButton { background:#1976D2; color:white; border:none; "
            "border-radius:5px; padding:7px; }"
            "QPushButton:hover { background:#1565C0; }"
            "QPushButton:disabled { background:#aaa; }"
        )
        export_layout.addWidget(self.export_mask_btn)
        export_layout.addWidget(QLabel("覆盖原图规则："))
        export_layout.addWidget(self.keep_combo)
        export_layout.addWidget(self.fill_combo)
        export_layout.addWidget(self.export_result_btn)
        controls_layout.addWidget(export_group)
        controls_layout.addStretch()

        help_label = QLabel(
            "左键绘制 · 滚轮缩放 · 右键/中键拖动平移\n"
            "快捷键：B 黑笔 · W 白笔 · Ctrl+Z/Y 撤销/重做"
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color:#777; font-size:11px;")
        controls_layout.addWidget(help_label)

        self.canvas = MaskCanvas()
        splitter.addWidget(self.canvas)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.status_label = QLabel("请先打开原图，或将图片拖入窗口")
        self.status_label.setStyleSheet("color:#555; padding:2px 4px;")
        root.addWidget(self.status_label)

        self._connect_controls()
        self._set_image_actions_enabled(False)
        self.canvas.set_brush(0, 20)

    def _connect_controls(self) -> None:
        self.brush_color_combo.currentIndexChanged.connect(self._update_brush)
        self.brush_width_spin.valueChanged.connect(self._update_brush)
        self.opacity_slider.valueChanged.connect(self._update_opacity)
        self.undo_btn.clicked.connect(self.canvas.undo)
        self.redo_btn.clicked.connect(self.canvas.redo)
        self.fill_black_btn.clicked.connect(lambda: self.canvas.fill_mask(0))
        self.fill_white_btn.clicked.connect(lambda: self.canvas.fill_mask(255))
        self.invert_btn.clicked.connect(self.canvas.invert_mask)
        self.export_mask_btn.clicked.connect(self._export_mask)
        self.export_result_btn.clicked.connect(self._export_masked_result)
        self.canvas.history_changed.connect(self._update_history_buttons)
        self.canvas.cursor_moved.connect(self._update_coordinates)
        self.canvas.mask_changed.connect(self._update_mask_stats)

        QShortcut(QKeySequence.StandardKey.Open, self, activated=self._open_original)
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.canvas.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=self.canvas.redo)
        QShortcut(
            QKeySequence("B"), self,
            activated=lambda: self.brush_color_combo.setCurrentIndex(0),
        )
        QShortcut(
            QKeySequence("W"), self,
            activated=lambda: self.brush_color_combo.setCurrentIndex(1),
        )
        QShortcut(QKeySequence("F"), self, activated=self.canvas.fit_image)

    def _set_image_actions_enabled(self, enabled: bool) -> None:
        for widget in (
                self.load_mask_btn,
                self.new_background_combo,
                self.new_mask_btn,
                self.brush_color_combo,
                self.brush_width_spin,
                self.opacity_slider,
                self.fill_black_btn,
                self.fill_white_btn,
                self.invert_btn,
                self.export_mask_btn,
                self.keep_combo,
                self.fill_combo,
                self.export_result_btn,
        ):
            widget.setEnabled(enabled)
        self.undo_btn.setEnabled(False)
        self.redo_btn.setEnabled(False)

    def _update_brush(self, *_args) -> None:
        self.canvas.set_brush(
            self.brush_color_combo.currentData(),
            self.brush_width_spin.value(),
        )

    def _update_opacity(self, value: int) -> None:
        self.opacity_value.setText(f"{value}%")
        self.canvas.set_overlay_opacity(value)

    def _update_history_buttons(self, can_undo: bool, can_redo: bool) -> None:
        self.undo_btn.setEnabled(can_undo)
        self.redo_btn.setEnabled(can_redo)

    def _update_coordinates(self, x: int, y: int) -> None:
        if self.canvas.mask is not None:
            height, width = self.canvas.mask.shape
            self.status_label.setText(f"坐标: ({x}, {y})　图片: {width} × {height}")

    def _update_mask_stats(self) -> None:
        if self.canvas.mask is None:
            return
        black = int(np.count_nonzero(self.canvas.mask == 0))
        total = self.canvas.mask.size
        self.status_label.setText(
            f"Mask 已更新　黑色: {black:,} px　白色: {total - black:,} px"
        )

    def set_original_image(self, image: np.ndarray, source_path: str = "") -> None:
        """设置原图，并按当前背景选项创建空白 Mask。"""
        height, width = image.shape[:2]
        mask = create_blank_mask(
            width,
            height,
            self.new_background_combo.currentData(),
        )
        self.canvas.set_images(image, mask)
        self.source_path = source_path
        self.source_label.setText(source_path or f"未命名图片（{width} × {height}）")
        self._set_image_actions_enabled(True)
        self.status_label.setText(f"已加载原图：{width} × {height}")

    def set_mask_image(self, image: np.ndarray) -> None:
        """载入并标准化已有 Mask。"""
        if self.canvas.original is None:
            raise ValueError("请先加载原图")
        mask = normalize_mask(image)
        if mask.shape != self.canvas.original.shape[:2]:
            raise ValueError(
                f"原图与 Mask 尺寸必须一致：原图 {self.canvas.original.shape[1]} × "
                f"{self.canvas.original.shape[0]}，Mask {mask.shape[1]} × {mask.shape[0]}"
            )
        self.canvas.set_images(self.canvas.original, mask)
        self._update_mask_stats()

    def build_masked_result(self) -> np.ndarray:
        """按当前保留颜色与背景颜色生成覆盖原图。"""
        if self.canvas.original is None or self.canvas.mask is None:
            raise ValueError("请先加载原图")
        return apply_mask_to_image(
            self.canvas.original,
            self.canvas.mask,
            keep_value=self.keep_combo.currentData(),
            fill_value=self.fill_combo.currentData(),
        )

    def save_mask(self, path: str | Path) -> None:
        """保存当前二值 Mask。"""
        if self.canvas.mask is None:
            raise ValueError("请先加载原图")
        write_image(path, self.canvas.mask)

    def save_masked_result(self, path: str | Path) -> None:
        """保存按当前规则提取后的原图。"""
        write_image(path, self.build_masked_result())

    def _open_original(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开原图", "", IMAGE_FILTER)
        if not path:
            return
        try:
            self.set_original_image(read_image(path), path)
        except Exception as exc:
            QMessageBox.critical(self, "打开失败", str(exc))

    def _open_mask(self) -> None:
        start_dir = str(Path(self.source_path).parent) if self.source_path else ""
        path, _ = QFileDialog.getOpenFileName(self, "加载已有 Mask", start_dir, IMAGE_FILTER)
        if not path:
            return
        try:
            self.set_mask_image(read_image(path))
            self.status_label.setText(f"已加载 Mask：{path}")
        except Exception as exc:
            QMessageBox.warning(self, "Mask 加载失败", str(exc))

    def _new_blank_mask(self) -> None:
        if self.canvas.original is None:
            return
        color = self.new_background_combo.currentData()
        height, width = self.canvas.original.shape[:2]
        mask = create_blank_mask(width, height, color)
        self.canvas.set_images(self.canvas.original, mask)
        self.status_label.setText("已新建纯白 Mask" if color == 255 else "已新建纯黑 Mask")

    def _default_output_path(self, suffix: str) -> str:
        if not self.source_path:
            return suffix.lstrip("_") + ".png"
        source = Path(self.source_path)
        return str(source.with_name(source.stem + suffix + ".png"))

    @staticmethod
    def _ensure_suffix(path: str) -> str:
        return path if Path(path).suffix else path + ".png"

    def _export_mask(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出当前 Mask",
            self._default_output_path("_mask"),
            MASK_FILTER,
        )
        if not path:
            return
        path = self._ensure_suffix(path)
        try:
            self.save_mask(path)
            self.status_label.setText(f"Mask 已保存：{path}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _export_masked_result(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出覆盖后的原图",
            self._default_output_path("_masked"),
            IMAGE_FILTER,
        )
        if not path:
            return
        path = self._ensure_suffix(path)
        try:
            self.save_masked_result(path)
            self.status_label.setText(f"覆盖原图已保存：{path}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif")):
                try:
                    self.set_original_image(read_image(path), path)
                except Exception as exc:
                    QMessageBox.critical(self, "打开失败", str(exc))
                event.acceptProposedAction()
                return
        event.ignore()
