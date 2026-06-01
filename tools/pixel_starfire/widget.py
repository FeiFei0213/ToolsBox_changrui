"""
widget.py — 像素坐标 → 星火坐标转换工具 GUI。

PixelStarfireWidget 继承 ToolBase，功能包括：
- 选择设备（M7/M23/M24/M25/M26）和相机位置（0/1）
- 在图片上点击拾取像素坐标，自动转换并记录到表格
- 手动输入像素坐标单点转换
- 计算两点间距离（mm 单位）
- 导出所有记录点为 CSV

坐标转换依赖 pixel_to_starfire.py + config/device/ 下的标定参数 JSON。
"""
import csv
import json
import logging
from pathlib import Path

import numpy as np
import cv2

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import (
    QAction, QPixmap, QImage, QPen, QBrush, QColor, QFont, QKeySequence,
)
from PySide6.QtWidgets import (
    QWidget, QSplitter,
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsSimpleTextItem, QGraphicsPixmapItem,
    QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QToolBar, QSizePolicy, QAbstractItemView,
    QGroupBox, QMessageBox, QFrame,
)

from tool_base import ToolBase
from tools.pixel_starfire.pixel_to_starfire import pixel_to_mm, mm_to_starfire

logger = logging.getLogger(__name__)

DEVICE_BASE = Path(__file__).parent / "config" / "device"


def discover_devices() -> list[str]:
    if not DEVICE_BASE.exists():
        return []
    return sorted(d.name for d in DEVICE_BASE.iterdir() if d.is_dir())


def load_params_for(device: str, camera: int):
    cam_dir = DEVICE_BASE / device / str(camera)
    with open(cam_dir / "fit_params.json", encoding="utf-8") as f:
        params = json.load(f)
    with open(cam_dir / "polynomials_fit.json", encoding="utf-8") as f:
        poly_config = json.load(f)
    return params, poly_config


class ImageViewer(QGraphicsView):
    point_clicked = Signal(float, float)
    mouse_moved = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = None
        self._point_items = []
        self._pick_mode = False

        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHint(self.renderHints())
        self.setBackgroundBrush(QBrush(QColor(40, 40, 40)))
        self.setMinimumWidth(400)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def _load_pixmap(self, path: str) -> QPixmap | None:
        try:
            with open(path, "rb") as f:
                data = np.frombuffer(f.read(), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is None:
                return None
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w, ch = img_rgb.shape
            qimg = QImage(img_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            return QPixmap.fromImage(qimg)
        except Exception as e:
            logger.error(f"load image failed: {e}")
            return None

    def load_image(self, path: str):
        self._scene.clear()
        self._point_items.clear()
        pixmap = self._load_pixmap(path)
        if pixmap is None or pixmap.isNull():
            return False
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        return True

    def set_pick_mode(self, enabled: bool):
        self._pick_mode = enabled
        if enabled:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def add_point_marker(self, px: float, py: float, index: int):
        r = 3
        pen = QPen(QColor(255, 60, 60), 1)
        brush = QBrush(QColor(255, 60, 60, 120))
        ellipse = self._scene.addEllipse(px - r, py - r, r * 2, r * 2, pen, brush)
        ellipse.setZValue(10)

        cross_pen = QPen(QColor(255, 60, 60), 0)
        h_line = self._scene.addLine(px - 8, py, px + 8, py, cross_pen)
        v_line = self._scene.addLine(px, py - 8, px, py + 8, cross_pen)
        h_line.setZValue(10)
        v_line.setZValue(10)

        font = QFont("Arial", 7)
        text = self._scene.addSimpleText(str(index), font)
        text.setBrush(QBrush(QColor(255, 220, 0)))
        text.setPos(px + r + 2, py - r - 8)
        text.setZValue(11)

        self._point_items.append((ellipse, h_line, v_line, text))

    def remove_last_marker(self):
        if self._point_items:
            for item in self._point_items.pop():
                self._scene.removeItem(item)

    def clear_markers(self):
        for items in self._point_items:
            for item in items:
                self._scene.removeItem(item)
        self._point_items.clear()

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        if self._pixmap_item and self._pixmap_item.contains(scene_pos):
            self.mouse_moved.emit(scene_pos.x(), scene_pos.y())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if self._pick_mode and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            if self._pixmap_item and self._pixmap_item.contains(scene_pos):
                self.point_clicked.emit(scene_pos.x(), scene_pos.y())
                return
        super().mousePressEvent(event)


class ControlPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._params_cache = {}
        self._rows = []
        self._setup_ui()
        self.setMinimumWidth(340)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        sel_grid = QGridLayout()
        sel_grid.setColumnStretch(1, 1)
        sel_grid.setSpacing(6)

        sel_grid.addWidget(QLabel("设备:"), 0, 0)
        self.device_combo = QComboBox()
        self.device_combo.addItem("— 请先选择设备 —", "")
        for dev in discover_devices():
            self.device_combo.addItem(dev, dev)
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        sel_grid.addWidget(self.device_combo, 0, 1)

        sel_grid.addWidget(QLabel("位置:"), 1, 0)
        self.camera_combo = QComboBox()
        self.camera_combo.addItem("— 请先选择设备 —", -1)
        self.camera_combo.setEnabled(False)
        self.camera_combo.currentIndexChanged.connect(self._on_camera_changed)
        sel_grid.addWidget(self.camera_combo, 1, 1)

        layout.addLayout(sel_grid)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep1)

        single_group = QGroupBox("单点转换")
        sg = QVBoxLayout(single_group)
        sg.setSpacing(7)

        xy_row = QHBoxLayout()
        xy_row.addWidget(QLabel("X:"))
        self.x_input = QLineEdit()
        self.x_input.setPlaceholderText("像素 X")
        xy_row.addWidget(self.x_input)
        xy_row.addSpacing(8)
        xy_row.addWidget(QLabel("Y:"))
        self.y_input = QLineEdit()
        self.y_input.setPlaceholderText("像素 Y")
        xy_row.addWidget(self.y_input)
        sg.addLayout(xy_row)

        self.convert_btn = QPushButton("转  换")
        self.convert_btn.setFixedHeight(28)
        self.convert_btn.clicked.connect(self._convert_single)
        sg.addWidget(self.convert_btn)

        result_frame = QFrame()
        result_frame.setFrameShape(QFrame.Shape.StyledPanel)
        rf = QGridLayout(result_frame)
        rf.setContentsMargins(8, 6, 8, 6)
        rf.setSpacing(5)
        rf.setColumnStretch(1, 1)

        self.px_label = QLabel("—")
        self.sf_label = QLabel("—")
        self.sf_mm_label = QLabel("—")
        for lbl in (self.px_label, self.sf_label, self.sf_mm_label):
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl.setWordWrap(True)

        def _copy_btn(slot):
            b = QPushButton("复制")
            b.setFixedWidth(46)
            b.clicked.connect(slot)
            return b

        rf.addWidget(QLabel("像素坐标:"), 0, 0)
        rf.addWidget(self.px_label,       0, 1)
        rf.addWidget(_copy_btn(self._copy_px_result),    0, 2)
        rf.addWidget(QLabel("映射后:"),   1, 0)
        rf.addWidget(self.sf_label,       1, 1)
        rf.addWidget(_copy_btn(self._copy_single_result), 1, 2)
        rf.addWidget(QLabel("实际坐标:"), 2, 0)
        rf.addWidget(self.sf_mm_label,    2, 1)
        rf.addWidget(_copy_btn(self._copy_sf_mm_result), 2, 2)

        sg.addWidget(result_frame)
        layout.addWidget(single_group)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep2)

        table_group = QGroupBox("点击记录")
        tg = QVBoxLayout(table_group)
        tg.setSpacing(7)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["#", "像素X", "像素Y", "星火X", "星火Y", "→mmX", "→mmY"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(140)
        tg.addWidget(self.table)

        tbl_btns = QHBoxLayout()
        copy_rows_btn = QPushButton("复制选中行")
        copy_rows_btn.clicked.connect(self._copy_selected_rows)
        export_btn = QPushButton("导出 CSV")
        export_btn.clicked.connect(self._export_csv)
        tbl_btns.addWidget(copy_rows_btn)
        tbl_btns.addWidget(export_btn)
        tg.addLayout(tbl_btns)

        dist_frame = QFrame()
        dist_frame.setFrameShape(QFrame.Shape.StyledPanel)
        df = QVBoxLayout(dist_frame)
        df.setContentsMargins(8, 7, 8, 7)
        df.setSpacing(5)

        dist_btn = QPushButton("计算选中两点距离")
        dist_btn.setFixedHeight(28)
        dist_btn.clicked.connect(self._calc_distance)
        df.addWidget(dist_btn)

        dist_result_row = QHBoxLayout()
        dist_result_row.addWidget(QLabel("距离:"))
        self.dist_label = QLabel("—")
        self.dist_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.dist_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        dist_result_row.addWidget(self.dist_label, 1)
        df.addLayout(dist_result_row)

        tg.addWidget(dist_frame)
        layout.addWidget(table_group, 1)

    def _on_device_changed(self):
        self._params_cache.clear()
        device = self.device_combo.currentData()
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        if not device:
            self.camera_combo.addItem("— 请先选择设备 —", -1)
            self.camera_combo.setEnabled(False)
        else:
            self.camera_combo.addItem("— 请选择位置 —", -1)
            self.camera_combo.addItem("位置 0", 0)
            self.camera_combo.addItem("位置 1", 1)
            self.camera_combo.setEnabled(True)
        self.camera_combo.blockSignals(False)

    def _on_camera_changed(self):
        self._params_cache.clear()

    def _get_params(self):
        device = self.device_combo.currentData()
        if not device:
            QMessageBox.warning(self, "未选择设备", "请先选择设备")
            return None, None
        pos = self.camera_combo.currentData()
        if pos == -1:
            QMessageBox.warning(self, "未选择位置", "请选择位置 0 或位置 1")
            return None, None
        key = (device, pos)
        if key not in self._params_cache:
            try:
                self._params_cache[key] = load_params_for(device, pos)
            except Exception as e:
                QMessageBox.warning(self, "配置文件错误", f"无法加载参数:\n{e}")
                return None, None
        return self._params_cache[key]

    def _do_convert(self, px: float, py: float):
        params, poly_config = self._get_params()
        if params is None:
            return None
        x_mm, y_mm = pixel_to_mm(px, py, params, poly_config)
        sx, sy = mm_to_starfire(x_mm, y_mm)
        return x_mm, y_mm, sx, sy

    def _convert_single(self):
        try:
            px = float(self.x_input.text())
            py = float(self.y_input.text())
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的数字坐标")
            return
        result = self._do_convert(px, py)
        if result is None:
            return
        x_mm, y_mm, sx, sy = result
        sf_mm_x, sf_mm_y = sx / 1000 * 25.4, sy / 1000 * 25.4
        self.px_label.setText(f"{px:.0f}, {py:.0f}")
        self.sf_label.setText(f"{sx:.2f}, {sy:.2f}")
        self.sf_mm_label.setText(f"{sf_mm_x:.3f}, {sf_mm_y:.3f}")

    def _copy_px_result(self):
        text = self.px_label.text()
        if text and text != "—":
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)

    def _copy_single_result(self):
        text = self.sf_label.text()
        if text and text != "—":
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)

    def _copy_sf_mm_result(self):
        text = self.sf_mm_label.text()
        if text and text != "—":
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)

    def add_point(self, px: float, py: float) -> int:
        result = self._do_convert(px, py)
        if result is None:
            return -1
        x_mm, y_mm, sx, sy = result
        sf_mm_x, sf_mm_y = sx / 1000 * 25.4, sy / 1000 * 25.4
        index = self.table.rowCount() + 1
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, val in enumerate([
            index, f"{px:.0f}", f"{py:.0f}",
            f"{sx:.2f}", f"{sy:.2f}",
            f"{sf_mm_x:.3f}", f"{sf_mm_y:.3f}",
        ]):
            item = QTableWidgetItem(str(val))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, col, item)
        self.table.scrollToBottom()
        self._rows.append((index, px, py, sx, sy, sf_mm_x, sf_mm_y))

        self.x_input.setText(f"{px:.0f}")
        self.y_input.setText(f"{py:.0f}")
        self.px_label.setText(f"{px:.0f}, {py:.0f}")
        self.sf_label.setText(f"{sx:.2f}, {sy:.2f}")
        self.sf_mm_label.setText(f"{sf_mm_x:.3f}, {sf_mm_y:.3f}")
        return index

    def remove_last_point(self) -> bool:
        if self.table.rowCount() > 0:
            self.table.removeRow(self.table.rowCount() - 1)
            if self._rows:
                self._rows.pop()
            return True
        return False

    def clear_points(self):
        self.table.setRowCount(0)
        self._rows.clear()
        self.px_label.setText("—")
        self.sf_label.setText("—")
        self.sf_mm_label.setText("—")
        self.dist_label.setText("—")

    def _calc_distance(self):
        rows = sorted(set(item.row() for item in self.table.selectedItems()))
        if len(rows) != 2:
            QMessageBox.information(self, "提示", "请在表格中选中恰好 2 行")
            return
        r1, r2 = rows
        x1 = float(self.table.item(r1, 5).text())
        y1 = float(self.table.item(r1, 6).text())
        x2 = float(self.table.item(r2, 5).text())
        y2 = float(self.table.item(r2, 6).text())
        dist = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        self.dist_label.setText(f"{dist:.3f} mm")

    def _copy_selected_rows(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        rows = sorted(set(item.row() for item in selected))
        lines = []
        for row in rows:
            cols = [self.table.item(row, c).text() for c in range(self.table.columnCount())]
            lines.append("\t".join(cols))
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText("\n".join(lines))

    def _export_csv(self):
        if not self._rows:
            QMessageBox.information(self, "提示", "没有可导出的数据")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", "starfire_points.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["序号", "像素X", "像素Y", "星火X", "星火Y", "星火→mmX", "星火→mmY"])
            for row in self._rows:
                writer.writerow([
                    row[0], f"{row[1]:.0f}", f"{row[2]:.0f}",
                    f"{row[3]:.2f}", f"{row[4]:.2f}",
                    f"{row[5]:.3f}", f"{row[6]:.3f}",
                ])
        QMessageBox.information(self, "导出成功", f"已保存到:\n{path}")


class PixelStarfireWidget(ToolBase):
    tool_name = "像素坐标转换"
    tool_description = "图片点击拾取像素坐标，转换为星火坐标系，支持 CSV 导出"
    tool_icon = "📍"

    def init_ui(self):
        self.resize(1100, 700)
        self._pick_mode = False

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 工具栏
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(8)

        open_btn = QPushButton("打开图片 (Ctrl+O)")
        open_btn.clicked.connect(self._open_image)
        toolbar_layout.addWidget(open_btn)

        self.pick_btn = QPushButton("点击拾取坐标 (P)")
        self.pick_btn.setCheckable(True)
        self.pick_btn.toggled.connect(self._toggle_pick_mode)
        toolbar_layout.addWidget(self.pick_btn)

        undo_btn = QPushButton("撤销最后一点 (Ctrl+Z)")
        undo_btn.clicked.connect(self._undo_last)
        toolbar_layout.addWidget(undo_btn)

        clear_btn = QPushButton("清空所有点")
        clear_btn.clicked.connect(self._clear_all)
        toolbar_layout.addWidget(clear_btn)

        toolbar_layout.addStretch()
        self._pos_label = QLabel("像素: —, —")
        toolbar_layout.addWidget(self._pos_label)

        root_layout.addWidget(toolbar_widget)

        # 主体
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.viewer = ImageViewer()
        self.viewer.point_clicked.connect(self._on_point_clicked)
        self.viewer.mouse_moved.connect(self._on_mouse_moved)

        self.panel = ControlPanel()

        splitter.addWidget(self.viewer)
        splitter.addWidget(self.panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([780, 400])

        root_layout.addWidget(splitter, 1)

        # 快捷键
        from PySide6.QtGui import QShortcut
        QShortcut(QKeySequence.StandardKey.Open, self, self._open_image)
        QShortcut(QKeySequence("P"), self, lambda: self.pick_btn.toggle())
        QShortcut(QKeySequence.StandardKey.Undo, self, self._undo_last)

    def _open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开图片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.tiff *.tif)"
        )
        if not path:
            return
        if not self.viewer.load_image(path):
            QMessageBox.warning(self, "错误", f"无法加载图片:\n{path}")
            return
        self.panel.clear_points()
        self.setWindowTitle(f"像素坐标转换  [{Path(path).name}]")

    def _toggle_pick_mode(self, enabled: bool):
        self._pick_mode = enabled
        self.viewer.set_pick_mode(enabled)

    def _on_point_clicked(self, px: float, py: float):
        index = self.panel.add_point(px, py)
        if index > 0:
            self.viewer.add_point_marker(px, py, index)

    def _on_mouse_moved(self, px: float, py: float):
        self._pos_label.setText(f"像素: ({px:.0f}, {py:.0f})")

    def _undo_last(self):
        if self.panel.remove_last_point():
            self.viewer.remove_last_marker()

    def _clear_all(self):
        self.panel.clear_points()
        self.viewer.clear_markers()
