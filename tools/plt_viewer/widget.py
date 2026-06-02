#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
logger = logging.getLogger(__name__)

"""
PLT 轮廓查看器
用于显示 contour.plt 文件的轮廓和点
"""

import re
import json
import os
import tempfile
from pathlib import Path
import numpy as np
import yaml

from tools.plt_viewer.inverse_transform import apply_inverse_transform
from tools.common_ui import VerticalTextButton, CollapsibleDockTitleBar
from tools.vgs_context import get_vgs_root, packaged_resource_path

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import QPen, QBrush, QAction, QImageReader, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsItem,
    QToolBar,
    QFileDialog,
    QStatusBar,
    QSpinBox,
    QDoubleSpinBox,
    QMessageBox,
    QLabel,
    QSlider,
    QCheckBox,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QFormLayout,
    QDockWidget,
    QWidget,
    QToolButton,
)


class BackgroundImageItem(QGraphicsPixmapItem):
    def __init__(self, pixmap, parent=None):
        super().__init__(pixmap, parent)


class ContourPointItem(QGraphicsEllipseItem):
    def __init__(self, x, y, size=4, parent=None):
        radius = size / 2.0
        super().__init__(-radius, -radius, size, size, parent)
        self.setBrush(QBrush(Qt.red))
        self.setPen(QPen(Qt.black, 1))
        self.setPos(QPointF(x, y))
        self.setZValue(10)


class GraphicsView(QGraphicsView):
    mouseMoved = Signal(QPointF)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.NoDrag)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self._panning = False
        self._last_pan_pos = None
        self._left_drag_panning = False
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 1.0 / 1.25
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._last_pan_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        elif event.button() == Qt.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if isinstance(item, ContourPointItem):
                super().mousePressEvent(event)
            else:
                self._left_drag_panning = True
                self._last_pan_pos = event.pos()
                self.setCursor(Qt.ClosedHandCursor)
                event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.mouseMoved.emit(self.mapToScene(event.position().toPoint()))
        if (self._panning or self._left_drag_panning) and self._last_pan_pos is not None:
            delta = event.pos() - self._last_pan_pos
            self._last_pan_pos = event.pos()
            self.translate(delta.x() * -1, delta.y() * -1)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        elif event.button() == Qt.LeftButton and self._left_drag_panning:
            self._left_drag_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class PltViewerWindow(QMainWindow):
    tool_name = "PLT 轮廓查看器"
    tool_description = "查看 contour.plt 文件的轮廓和点，支持逆变换叠加背景图"
    tool_icon = "📐"

    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.tool_name)

        self.scene = QGraphicsScene(self)
        self.view = GraphicsView(self.scene, self)
        self.setCentralWidget(self.view)

        self.bg_item = None
        self.contours = []
        self.point_items = []
        self.line_items = []

        self._create_toolbar()
        self._create_statusbar()
        self._create_params_dock()

        self.view.mouseMoved.connect(self.on_mouse_moved)

        self.point_size_spin.setValue(10)
        self.line_width_spin.setValue(10)

        self.params_filepath = None
        self.params_data = None
        self.params_temp_filepath = None
        self.poly_filepath = None
        self.poly_data = None
        self.plt_filepath = None

        self._load_default_params()
        self._load_default_poly()

    def _create_toolbar(self):
        toolbar = QToolBar("Main Toolbar", self)
        self.addToolBar(toolbar)

        open_img_action = QAction("打开图片", self)
        open_img_action.triggered.connect(self.open_image)
        toolbar.addAction(open_img_action)

        open_plt_action = QAction("打开PLT", self)
        open_plt_action.triggered.connect(self.open_plt)
        toolbar.addAction(open_plt_action)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel("点大小:", self))
        self.point_size_spin = QSpinBox(self)
        self.point_size_spin.setRange(1, 50)
        self.point_size_spin.valueChanged.connect(self.on_point_size_changed)
        toolbar.addWidget(self.point_size_spin)

        toolbar.addWidget(QLabel("  线宽:", self))
        self.line_width_spin = QSpinBox(self)
        self.line_width_spin.setRange(1, 50)
        self.line_width_spin.valueChanged.connect(self.on_line_width_changed)
        toolbar.addWidget(self.line_width_spin)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel("  背景透明度:", self))
        self.alpha_slider = QSlider(Qt.Horizontal, self)
        self.alpha_slider.setRange(0, 100)
        self.alpha_slider.setValue(50)
        self.alpha_slider.setMaximumWidth(150)
        self.alpha_slider.valueChanged.connect(self.on_alpha_changed)
        toolbar.addWidget(self.alpha_slider)

        self.alpha_label = QLabel("50%", self)
        self.alpha_label.setMinimumWidth(40)
        toolbar.addWidget(self.alpha_label)

        toolbar.addSeparator()

        self.show_points_checkbox = QCheckBox("显示点", self)
        self.show_points_checkbox.setChecked(True)
        self.show_points_checkbox.stateChanged.connect(self.on_show_points_changed)
        toolbar.addWidget(self.show_points_checkbox)

        self.show_lines_checkbox = QCheckBox("显示线", self)
        self.show_lines_checkbox.setChecked(True)
        self.show_lines_checkbox.stateChanged.connect(self.on_show_lines_changed)
        toolbar.addWidget(self.show_lines_checkbox)

    def _create_statusbar(self):
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self._mouse_label = QLabel("鼠标: (-, -)", self)
        self._info_label = QLabel("  轮廓: 0 个", self)
        self.status.addWidget(self._mouse_label)
        self.status.addWidget(self._info_label)

    def _create_params_dock(self):
        dock = QDockWidget("参数编辑", self)
        dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        dock.setMinimumWidth(200)

        title_bar = CollapsibleDockTitleBar(dock, self)
        dock.setTitleBarWidget(title_bar)

        params_widget = QWidget()
        layout = QVBoxLayout(params_widget)

        layout.addWidget(QLabel("<b>mapping_params_file:</b>", self))
        self.params_file_label = QLabel("未加载文件", self)
        self.params_file_label.setWordWrap(True)
        layout.addWidget(self.params_file_label)

        layout.addWidget(QLabel("参数值:", self))

        form_layout = QFormLayout()
        self.param_inputs = []
        param_names = ["参数1", "参数2", "参数3", "参数4", "参数5", "参数6", "参数7"]

        for name in param_names:
            line_edit = QLineEdit(self)
            line_edit.setPlaceholderText("请输入数值")
            line_edit.textChanged.connect(self.on_param_changed)
            form_layout.addRow(f"{name}:", line_edit)
            self.param_inputs.append(line_edit)

        layout.addLayout(form_layout)

        params_button_layout = QHBoxLayout()
        self.load_params_btn = QPushButton("加载JSON", self)
        self.load_params_btn.clicked.connect(self.open_params_json)
        params_button_layout.addWidget(self.load_params_btn)

        self.save_params_btn = QPushButton("保存", self)
        self.save_params_btn.clicked.connect(self.save_params)
        self.save_params_btn.setEnabled(False)
        params_button_layout.addWidget(self.save_params_btn)
        layout.addLayout(params_button_layout)

        layout.addWidget(QLabel("─" * 20, self))

        layout.addWidget(QLabel("<b>mapping_poly_file:</b>", self))
        self.poly_file_label = QLabel("未加载文件", self)
        self.poly_file_label.setWordWrap(True)
        layout.addWidget(self.poly_file_label)

        poly_button_layout = QHBoxLayout()
        self.load_poly_btn = QPushButton("加载JSON", self)
        self.load_poly_btn.clicked.connect(self.open_poly_json)
        poly_button_layout.addWidget(self.load_poly_btn)
        layout.addLayout(poly_button_layout)
        layout.addStretch()

        dock.setWidget(params_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.params_dock = dock

    def open_image(self):
        fn, _ = QFileDialog.getOpenFileName(
            self, "选择图片文件", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"
        )
        if not fn:
            return

        self.statusBar().showMessage("正在加载图片...")
        QApplication.processEvents()

        pix = QPixmap(fn)
        if pix.isNull():
            self.statusBar().clearMessage()
            QMessageBox.warning(self, "错误", "无法加载图片")
            return

        if self.bg_item is not None:
            self.scene.removeItem(self.bg_item)
            self.bg_item = None

        self.bg_item = BackgroundImageItem(pix)
        self.bg_item.setZValue(-1000)
        self.bg_item.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        self.bg_item.setFlag(QGraphicsPixmapItem.ItemIsMovable, False)
        self.bg_item.setFlag(QGraphicsPixmapItem.ItemIsSelectable, False)
        self.scene.addItem(self.bg_item)

        self.scene.setSceneRect(QRectF(0, 0, pix.width(), pix.height()))
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        self.on_alpha_changed(self.alpha_slider.value())

        self.statusBar().showMessage(f"图片加载完成: {pix.width()}x{pix.height()}", 2000)

    def parse_plt_file(self, filepath):
        self.statusBar().showMessage("正在解析 PLT 文件...")
        QApplication.processEvents()

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取 PLT 文件失败：{e}")
            return False

        for item in self.point_items + self.line_items:
            self.scene.removeItem(item)
        self.point_items.clear()
        self.line_items.clear()
        self.contours.clear()

        pu_pattern = r'PU(-?\d+\.?\d*),(-?\d+\.?\d*);'
        pd_pattern = r'PD([^;]+);'
        pu_matches = list(re.finditer(pu_pattern, content))

        if len(pu_matches) == 0:
            QMessageBox.warning(self, "错误", "PLT 文件中没有找到有效的点数据")
            return False

        for i, pu_match in enumerate(pu_matches):
            try:
                pu_x = float(pu_match.group(1))
                pu_y = float(pu_match.group(2))
            except ValueError:
                continue

            pu_end = pu_match.end()
            next_pu_start = pu_matches[i + 1].start() if i + 1 < len(pu_matches) else len(content)
            pg_match = re.search(r'PG;', content[pu_end:next_pu_start])
            if pg_match:
                next_pu_start = pu_end + pg_match.start()

            segment = content[pu_end:next_pu_start]
            pd_match = re.search(pd_pattern, segment)

            if pd_match:
                pd_coords = pd_match.group(1)
                try:
                    coords = [float(c.strip()) for c in pd_coords.split(',')]
                except ValueError:
                    self.contours.append([(pu_x, pu_y)])
                    continue

                contour_points = [(pu_x, pu_y)]
                for j in range(0, len(coords), 2):
                    if j + 1 < len(coords):
                        contour_points.append((coords[j], coords[j + 1]))

                if contour_points:
                    self.contours.append(contour_points)
            else:
                self.contours.append([(pu_x, pu_y)])

        if not self.contours:
            QMessageBox.warning(self, "错误", "PLT 文件中没有找到有效的轮廓数据")
            return False

        return True

    def open_plt(self):
        fn, _ = QFileDialog.getOpenFileName(self, "选择PLT文件", "", "PLT (*.plt)")
        if not fn:
            return

        self.plt_filepath = fn

        if not self.parse_plt_file(fn):
            return

        params_file = self.params_temp_filepath if self.params_temp_filepath else self.params_filepath
        if self.poly_filepath and params_file:
            self.statusBar().showMessage("正在应用逆变换...")
            QApplication.processEvents()
            try:
                contours_array = [np.array(contour, dtype=np.float64) for contour in self.contours]
                transformed_contours = apply_inverse_transform(contours_array, self.poly_filepath, params_file)
                self.contours = [c.tolist() if isinstance(c, np.ndarray) else c for c in transformed_contours]
                self.statusBar().showMessage("逆变换完成", 2000)
            except Exception as e:
                QMessageBox.warning(self, "警告", f"逆变换失败: {e}\n将使用原始坐标")
                self.statusBar().showMessage("逆变换失败，使用原始坐标", 2000)
        else:
            if not self.poly_filepath or not params_file:
                QMessageBox.information(
                    self, "提示",
                    "未加载 mapping_poly_file 或 mapping_params_file，\n将使用原始PLT坐标（未应用逆变换）"
                )

        self._draw_contours()

    def _draw_contours(self):
        self.statusBar().showMessage("正在绘制轮廓...")
        QApplication.processEvents()

        point_size = self.point_size_spin.value()
        line_width = self.line_width_spin.value()
        show_pts = self.show_points_checkbox.isChecked()
        show_lns = self.show_lines_checkbox.isChecked()

        self.scene.blockSignals(True)

        for contour in self.contours:
            if not contour:
                continue
            for x, y in contour:
                point_item = ContourPointItem(x, y, size=point_size)
                point_item.setVisible(show_pts)
                self.scene.addItem(point_item)
                self.point_items.append(point_item)

            if len(contour) > 1:
                for i in range(len(contour) - 1):
                    x1, y1 = contour[i]
                    x2, y2 = contour[i + 1]
                    line_item = QGraphicsLineItem(x1, y1, x2, y2)
                    line_item.setPen(QPen(Qt.green, line_width))
                    line_item.setZValue(5)
                    line_item.setVisible(show_lns)
                    self.scene.addItem(line_item)
                    self.line_items.append(line_item)

        self.scene.blockSignals(False)

        total_points = sum(len(c) for c in self.contours)
        self._info_label.setText(f"  轮廓: {len(self.contours)} 个, 点: {total_points} 个")
        self.statusBar().showMessage(f"PLT 加载完成: {len(self.contours)} 个轮廓, {total_points} 个点", 3000)

    def on_point_size_changed(self, value):
        for item in self.point_items:
            radius = value / 2.0
            item.setRect(-radius, -radius, value, value)

    def on_line_width_changed(self, value):
        for item in self.line_items:
            pen = item.pen()
            pen.setWidth(value)
            item.setPen(pen)

    def on_alpha_changed(self, value):
        self.alpha_label.setText(f"{value}%")
        if self.bg_item is not None:
            self.bg_item.setOpacity(value / 100.0)

    def on_show_points_changed(self, state):
        show = (state == Qt.Checked)
        for item in self.point_items:
            item.setVisible(show)

    def on_show_lines_changed(self, state):
        show = (state == Qt.Checked)
        for item in self.line_items:
            item.setVisible(show)

    def on_mouse_moved(self, scene_pos: QPointF):
        self._mouse_label.setText(f"鼠标: ({scene_pos.x():.2f}, {scene_pos.y():.2f})")

    def _get_relative_path(self, filepath):
        try:
            rel = os.path.relpath(filepath, os.getcwd())
            return ("..." + rel[-47:]) if len(rel) > 50 else rel
        except Exception:
            return os.path.basename(filepath)

    def _load_default_params(self):
        for path in self._default_config_candidates("M7", "0", "fit_params.json"):
            if path.exists():
                self._load_params_file(str(path), silent=True)
                break

    def _load_default_poly(self):
        for path in self._default_config_candidates("M7", "0", "polynomials_fit.json"):
            if path.exists():
                self._load_poly_file(str(path), silent=True)
                break

    def _default_config_candidates(self, device: str, camera: str, filename: str) -> list:
        rel = Path("config") / "device" / device / camera / filename
        candidates = []
        vgs_root = get_vgs_root(auto_detect=True)
        if vgs_root:
            candidates.append(vgs_root / rel)
        candidates.append(packaged_resource_path("tools", "pixel_starfire", rel))
        candidates.append(Path.cwd() / rel)
        return candidates

    def _load_params_file(self, filepath, silent=False):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                params_data = json.load(f)
        except Exception as e:
            if not silent:
                QMessageBox.warning(self, "错误", f"读取JSON文件失败：{e}")
            return False

        self.params_filepath = filepath
        self.params_data = params_data
        self.params_file_label.setText(f"文件: {self._get_relative_path(filepath)}")
        self._load_params_to_sidebar()
        self.save_params_btn.setEnabled(True)

        if not silent:
            self.statusBar().showMessage(f"已加载参数文件: {self._get_relative_path(filepath)}", 2000)
        return True

    def open_params_json(self):
        fn, _ = QFileDialog.getOpenFileName(self, "选择参数JSON文件 (mapping_params_file)", "", "JSON (*.json)")
        if fn:
            self._load_params_file(fn, silent=False)

    def open_poly_json(self):
        fn, _ = QFileDialog.getOpenFileName(self, "选择多项式JSON文件 (mapping_poly_file)", "", "JSON (*.json)")
        if fn:
            self._load_poly_file(fn, silent=False)

    def _load_poly_file(self, filepath, silent=False):
        try:
            if filepath.endswith('.json'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    poly_data = json.load(f)
            elif filepath.endswith('.yaml'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    poly_data = yaml.safe_load(f)
            else:
                if not silent:
                    QMessageBox.warning(self, "错误", "不支持的文件类型")
                return False
        except Exception as e:
            if not silent:
                QMessageBox.warning(self, "错误", f"读取文件失败：{e}")
            return False

        self.poly_filepath = filepath
        self.poly_data = poly_data
        self.poly_file_label.setText(f"文件: {self._get_relative_path(filepath)}")

        if not silent:
            self.statusBar().showMessage(f"已加载多项式文件: {self._get_relative_path(filepath)}", 2000)
        return True

    def _load_params_to_sidebar(self):
        if not self.params_data:
            return

        values = []
        if 'x_params' in self.params_data and 'y_params' in self.params_data:
            all_values = list(self.params_data['x_params']) + list(self.params_data['y_params'])
            values = all_values[:7]
        elif 'x_new' in self.params_data and 'y_new' in self.params_data:
            x_new = self.params_data['x_new']
            y_new = self.params_data['y_new']
            values = [x_new.get('a', 0), x_new.get('b', 0), x_new.get('f', 0),
                      y_new.get('g', 0), y_new.get('h', 0), y_new.get('i', 0), y_new.get('j', 0)]
        elif isinstance(self.params_data, list) and len(self.params_data) >= 7:
            values = self.params_data[:7]
        else:
            QMessageBox.warning(self, "警告", "无法识别参数格式，请手动输入")
            return

        for w in self.param_inputs:
            w.blockSignals(True)
        for i, w in enumerate(self.param_inputs):
            w.setText(str(values[i]) if i < len(values) else "")
        for w in self.param_inputs:
            w.blockSignals(False)

        self._save_to_temp_file()

    def on_param_changed(self):
        if not hasattr(self, '_param_change_timer'):
            self._param_change_timer = QTimer(self)
            self._param_change_timer.setSingleShot(True)
            self._param_change_timer.timeout.connect(self._on_param_changed_delayed)
        else:
            self._param_change_timer.stop()
        self._param_change_timer.start(500)

    def _on_param_changed_delayed(self):
        if self._save_to_temp_file() and self.plt_filepath:
            self._redraw_plt()

    def _get_params_values(self):
        values = []
        for w in self.param_inputs:
            text = w.text().strip()
            if not text:
                return None
            try:
                values.append(float(text))
            except ValueError:
                return None
        return values

    def _save_to_temp_file(self):
        if not self.params_filepath or not self.params_data:
            return False

        values = self._get_params_values()
        if values is None or len(values) != 7:
            return False

        try:
            if not self.params_temp_filepath:
                temp_dir = tempfile.gettempdir()
                self.params_temp_filepath = os.path.join(temp_dir, f"plt_viewer_params_{os.getpid()}.json")

            if 'x_params' in self.params_data and 'y_params' in self.params_data:
                original_y = self.params_data['y_params']
                new_data = {"x_params": values[:3], "y_params": values[3:]}
                if len(original_y) == 5 and len(values) >= 7:
                    new_data["y_params"] = values[3:7] + [original_y[4]]
            elif 'x_new' in self.params_data and 'y_new' in self.params_data:
                y_new = self.params_data.get('y_new', {})
                new_data = {
                    "x_new": {"a": values[0], "b": values[1], "f": values[2]},
                    "y_new": {"g": values[3], "h": values[4], "i": values[5], "j": values[6], "p": y_new.get('p', 0)},
                }
            else:
                new_data = values

            with open(self.params_temp_filepath, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, indent=2, ensure_ascii=False)
            return True

        except Exception as e:
            print(f"保存临时文件失败: {e}")
            return False

    def _redraw_plt(self):
        if not self.plt_filepath:
            return

        for item in self.point_items + self.line_items:
            self.scene.removeItem(item)
        self.point_items.clear()
        self.line_items.clear()

        if not self.parse_plt_file(self.plt_filepath):
            return

        params_file = self.params_temp_filepath if self.params_temp_filepath else self.params_filepath
        if self.poly_filepath and params_file:
            self.statusBar().showMessage("正在应用逆变换...")
            QApplication.processEvents()
            try:
                contours_array = [np.array(contour, dtype=np.float64) for contour in self.contours]
                transformed = apply_inverse_transform(contours_array, self.poly_filepath, params_file)
                self.contours = [c.tolist() if isinstance(c, np.ndarray) else c for c in transformed]
            except Exception as e:
                print(f"逆变换失败: {e}")

        self._draw_contours()
        self.statusBar().showMessage("已重新绘制", 1000)

    def save_params(self):
        if not self.params_filepath or not self.params_data:
            QMessageBox.warning(self, "错误", "请先加载参数文件")
            return

        values = self._get_params_values()
        if values is None or len(values) != 7:
            QMessageBox.warning(self, "错误", "所有参数都必须填写且为有效数字")
            return

        try:
            if 'x_params' in self.params_data and 'y_params' in self.params_data:
                original_y = self.params_data['y_params']
                new_data = {"x_params": values[:3], "y_params": values[3:]}
                if len(original_y) == 5 and len(values) >= 7:
                    new_data["y_params"] = values[3:7] + [original_y[4]]
            elif 'x_new' in self.params_data and 'y_new' in self.params_data:
                y_new = self.params_data.get('y_new', {})
                new_data = {
                    "x_new": {"a": values[0], "b": values[1], "f": values[2]},
                    "y_new": {"g": values[3], "h": values[4], "i": values[5], "j": values[6], "p": y_new.get('p', 0)},
                }
            else:
                new_data = values

            with open(self.params_filepath, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, indent=2, ensure_ascii=False)

            self.params_data = new_data

            if self.params_temp_filepath and os.path.exists(self.params_temp_filepath):
                try:
                    os.remove(self.params_temp_filepath)
                    self.params_temp_filepath = None
                except Exception:
                    pass

            self._save_to_temp_file()
            QMessageBox.information(self, "成功", "参数已保存到原文件")
            self.statusBar().showMessage("参数已保存", 2000)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败：{e}")
