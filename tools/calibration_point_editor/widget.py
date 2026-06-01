import logging
logger = logging.getLogger(__name__)

import yaml

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QObject
from PySide6.QtGui import (
    QPixmap, QPen, QBrush, QAction, QImageReader,
    QIcon, QFont, QPainter, QColor,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsSimpleTextItem,
    QGraphicsItem,
    QToolBar,
    QFileDialog,
    QStatusBar,
    QSpinBox,
    QDoubleSpinBox,
    QMessageBox,
    QLabel,
    QDockWidget,
    QListWidget,
    QListWidgetItem,
    QSlider,
    QCheckBox,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QToolButton,
)
from PySide6.QtCore import QTimer

from tools.common_ui import VerticalTextButton, CollapsibleDockTitleBar, VerticalCollapsibleDockTitleBar
from tools.yaml_formatter import format_yaml_dict


class BackgroundImageItem(QGraphicsPixmapItem):
    def __init__(self, pixmap, parent=None):
        super().__init__(pixmap, parent)


class CalibrationPointItem(QGraphicsEllipseItem):
    def __init__(self, name, x, y, size=6, parent=None):
        radius = size / 2.0
        super().__init__(-radius, -radius, size, size, parent)

        self.name = name
        self.segments = []
        self.normal_brush = QBrush(Qt.red)
        self.selected_brush = QBrush(Qt.yellow)

        self.setFlags(
            QGraphicsEllipseItem.ItemIsMovable
            | QGraphicsEllipseItem.ItemIsSelectable
            | QGraphicsEllipseItem.ItemSendsGeometryChanges
        )
        self.setBrush(self.normal_brush)
        self.setPen(QPen(Qt.black, 1))

        self.label = QGraphicsSimpleTextItem(self.name, self)
        self.label.setFlag(QGraphicsSimpleTextItem.ItemIgnoresTransformations, True)
        self.updateLabelPosition()

        self.setPos(QPointF(x, y))

    def updateLabelPosition(self):
        b = self.label.boundingRect()
        self.label.setPos(4, -b.height() - 2)

    def setPointSize(self, size):
        radius = size / 2.0
        self.setRect(-radius, -radius, size, size)

    def itemChange(self, change, value):
        if change == QGraphicsEllipseItem.ItemPositionHasChanged:
            for seg in self.segments:
                seg.updatePosition()
        elif change == QGraphicsEllipseItem.ItemSelectedHasChanged:
            if value:
                self.setBrush(self.selected_brush)
                self.setPen(QPen(Qt.black, 2))
            else:
                self.setBrush(self.normal_brush)
                self.setPen(QPen(Qt.black, 1))
        return super().itemChange(change, value)


class SegmentItem(QGraphicsLineItem):
    def __init__(self, p1_item: CalibrationPointItem, p2_item: CalibrationPointItem, width=1.0, parent=None):
        super().__init__(parent)
        self.p1_item = p1_item
        self.p2_item = p2_item
        self.setPen(QPen(Qt.green, width))
        self.setZValue(-1)
        self.updatePosition()

        self.p1_item.segments.append(self)
        self.p2_item.segments.append(self)

    def updatePosition(self):
        p1 = self.p1_item.pos()
        p2 = self.p2_item.pos()
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())

    def setLineWidth(self, width):
        pen = self.pen()
        pen.setWidthF(width)
        self.setPen(pen)


class GraphicsView(QGraphicsView):
    mouseMoved = Signal(QPointF, object)

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
        self.move_mode = False
        self.setFocusPolicy(Qt.StrongFocus)

    def set_move_mode(self, enabled):
        self.move_mode = enabled
        self.setDragMode(QGraphicsView.RubberBandDrag if enabled else QGraphicsView.NoDrag)

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
            clicked_on_point = False

            temp_item = item
            while temp_item is not None:
                if isinstance(temp_item, CalibrationPointItem):
                    clicked_on_point = True
                    break
                temp_item = temp_item.parentItem()

            if clicked_on_point:
                if self.move_mode and event.modifiers() & Qt.ControlModifier:
                    item.setSelected(not item.isSelected())
                    event.accept()
                    return
                super().mousePressEvent(event)
            else:
                self._left_drag_panning = True
                self._last_pan_pos = event.pos()
                self.setCursor(Qt.ClosedHandCursor)
                event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        item = self.itemAt(event.position().toPoint())

        point_item = None
        while item is not None:
            if isinstance(item, CalibrationPointItem):
                point_item = item
                break
            item = item.parentItem()

        self.mouseMoved.emit(scene_pos, point_item)

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

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right, Qt.Key_M):
            parent_widget = self.parent()
            while parent_widget:
                if isinstance(parent_widget, CalibrationPointEditorWindow):
                    parent_widget.keyPressEvent(event)
                    if event.isAccepted():
                        return
                    break
                parent_widget = parent_widget.parent()

        if key == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
            event.ignore()
            return
        if key == Qt.Key_Escape:
            event.ignore()
            return

        super().keyPressEvent(event)


class CalibrationPointEditorWindow(QMainWindow):
    tool_name = "标定点编辑"
    tool_description = "在图像上编辑 YAML 标定点坐标，支持拖拽和方向键微调"
    tool_icon = "🎯"

    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.tool_name)

        self.scene = QGraphicsScene(self)
        self.view = GraphicsView(self.scene, self)
        self.setCentralWidget(self.view)

        self.bg_item = None
        self.points = {}
        self.segments = []
        self.current_yaml_path = None
        self.yaml_data = None
        self.single_points = {}
        self.polygon_items = {}
        self.layer_eye_buttons = {}

        self._create_toolbar()
        self._create_statusbar()
        self._create_layer_panel()

        self.view.mouseMoved.connect(self.on_mouse_moved)

        self.point_size_spin.setValue(20)
        self.line_width_spin.setValue(10)
        self.step_spin.setValue(1.0)

    def _create_toolbar(self):
        toolbar = QToolBar("Main Toolbar", self)
        self.addToolBar(toolbar)

        open_img_action = QAction("打开图片", self)
        open_img_action.triggered.connect(self.open_image)
        toolbar.addAction(open_img_action)

        open_yaml_action = QAction("打开YAML", self)
        open_yaml_action.triggered.connect(self.open_yaml)
        toolbar.addAction(open_yaml_action)

        save_yaml_action = QAction("保存YAML", self)
        save_yaml_action.triggered.connect(self.save_yaml)
        toolbar.addAction(save_yaml_action)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel("点大小:", self))
        self.point_size_spin = QSpinBox(self)
        self.point_size_spin.setRange(2, 100)
        self.point_size_spin.valueChanged.connect(self.on_point_size_changed)
        toolbar.addWidget(self.point_size_spin)

        toolbar.addWidget(QLabel("  线宽:", self))
        self.line_width_spin = QSpinBox(self)
        self.line_width_spin.setRange(1, 50)
        self.line_width_spin.valueChanged.connect(self.on_line_width_changed)
        toolbar.addWidget(self.line_width_spin)

        toolbar.addWidget(QLabel("  步长:", self))
        self.step_spin = QDoubleSpinBox(self)
        self.step_spin.setDecimals(3)
        self.step_spin.setRange(0.001, 1000.0)
        self.step_spin.setSingleStep(0.1)
        toolbar.addWidget(self.step_spin)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel("  背景透明度:", self))
        self.alpha_slider = QSlider(Qt.Horizontal, self)
        self.alpha_slider.setRange(0, 100)
        self.alpha_slider.setValue(50)
        self.alpha_slider.setMaximumWidth(150)
        self.alpha_slider.valueChanged.connect(self.on_alpha_changed)
        toolbar.addWidget(self.alpha_slider)

        self.alpha_label = QLabel("100%", self)
        self.alpha_label.setMinimumWidth(40)
        toolbar.addWidget(self.alpha_label)

        toolbar.addSeparator()

        self.show_names_checkbox = QCheckBox("显示名字", self)
        self.show_names_checkbox.setChecked(True)
        self.show_names_checkbox.stateChanged.connect(self.on_show_names_changed)
        toolbar.addWidget(self.show_names_checkbox)

        toolbar.addSeparator()

        self.move_mode_checkbox = QCheckBox("移动模式", self)
        self.move_mode_checkbox.setChecked(False)
        self.move_mode_checkbox.stateChanged.connect(self.on_move_mode_changed)
        toolbar.addWidget(self.move_mode_checkbox)

        select_all_action = QAction("全选点", self)
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(self.on_select_all_points)
        toolbar.addAction(select_all_action)

        deselect_all_action = QAction("取消选择", self)
        deselect_all_action.setShortcut("Escape")
        deselect_all_action.triggered.connect(self.on_deselect_all_points)
        toolbar.addAction(deselect_all_action)

    def _create_statusbar(self):
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self._mouse_label = QLabel("鼠标: (-, -)", self)
        self._selected_label = QLabel("  选中: 无", self)
        self.status.addWidget(self._mouse_label)
        self.status.addWidget(self._selected_label)

    def _create_layer_panel(self):
        self.layer_dock = QDockWidget("图层列表", self)
        self.layer_list = QListWidget()
        self.layer_dock.setWidget(self.layer_list)
        self.layer_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.layer_dock.setMinimumWidth(200)

        title_bar = VerticalCollapsibleDockTitleBar(self.layer_dock, self)
        self.layer_dock.setTitleBarWidget(title_bar)

        self.addDockWidget(Qt.RightDockWidgetArea, self.layer_dock)

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

    def open_yaml(self):
        fn, _ = QFileDialog.getOpenFileName(self, "选择YAML文件", "", "YAML (*.yml *.yaml)")
        if fn:
            self.load_yaml(fn)

    def _is_coordinate(self, value):
        if not isinstance(value, list) or len(value) != 2:
            return False
        try:
            float(value[0])
            float(value[1])
            return True
        except (ValueError, TypeError, IndexError):
            return False

    def _is_coordinate_array(self, value):
        if not isinstance(value, list) or len(value) == 0:
            return False
        return self._is_coordinate(value[0])

    def load_yaml(self, path):
        self.statusBar().showMessage("正在读取 YAML 文件...")
        QApplication.processEvents()

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            self.statusBar().clearMessage()
            QMessageBox.warning(self, "错误", f"读取 YAML 失败：{e}")
            return

        if not isinstance(data, dict):
            self.statusBar().clearMessage()
            QMessageBox.warning(self, "错误", "YAML 根节点不是字典结构")
            return

        self.current_yaml_path = path
        self.yaml_data = data

        self.statusBar().showMessage("正在清理旧数据...")
        QApplication.processEvents()

        self.scene.blockSignals(True)

        for seg in self.segments:
            self.scene.removeItem(seg)
        self.segments.clear()
        for p in self.points.values():
            self.scene.removeItem(p)
        self.points.clear()
        self.single_points.clear()
        self.polygon_items.clear()

        point_size = self.point_size_spin.value()
        line_width = self.line_width_spin.value()

        single_count = 0
        polygon_count = 0
        total_points_count = 0

        self.statusBar().showMessage("正在创建标定点...")
        QApplication.processEvents()

        for key, value in data.items():
            if self._is_coordinate(value):
                x, y = float(value[0]), float(value[1])
                p_item = CalibrationPointItem(key, x, y, size=point_size)
                self.scene.addItem(p_item)
                self.points[key] = p_item
                self.single_points[key] = p_item
                single_count += 1

            elif self._is_coordinate_array(value):
                poly_list = []
                last_item = None
                first_item = None

                for idx, xy in enumerate(value):
                    x, y = float(xy[0]), float(xy[1])
                    name = f"{key}[{idx}]"
                    p_item = CalibrationPointItem(name, x, y, size=point_size)
                    self.scene.addItem(p_item)
                    self.points[name] = p_item
                    poly_list.append(p_item)

                    if first_item is None:
                        first_item = p_item
                    if last_item is not None:
                        s_item = SegmentItem(last_item, p_item, width=line_width)
                        self.scene.addItem(s_item)
                        self.segments.append(s_item)
                    last_item = p_item

                if first_item is not None and last_item is not None and first_item is not last_item:
                    s_item = SegmentItem(last_item, first_item, width=line_width)
                    self.scene.addItem(s_item)
                    self.segments.append(s_item)

                self.polygon_items[key] = poly_list
                polygon_count += 1
                total_points_count += len(poly_list)

        self.scene.blockSignals(False)

        self.statusBar().showMessage("正在更新界面...")
        QApplication.processEvents()

        self._update_all_labels_visibility()
        self._update_layer_list()

        msg = f"加载完成: {single_count}个单点, {polygon_count}个多边形({total_points_count}点), 共{len(self.points)}个点"
        self.statusBar().showMessage(msg, 3000)

    def save_yaml(self):
        if self.yaml_data is None:
            QMessageBox.warning(self, "错误", "没有加载任何 YAML")
            return

        if self.current_yaml_path is None:
            fn, _ = QFileDialog.getSaveFileName(self, "保存YAML文件", "", "YAML (*.yml *.yaml)")
            if not fn:
                return
            self.current_yaml_path = fn
        else:
            fn = self.current_yaml_path

        for key, p_item in self.single_points.items():
            pos = p_item.pos()
            self.yaml_data[key] = [float(pos.x()), float(pos.y())]

        for key, poly_list in self.polygon_items.items():
            self.yaml_data[key] = [[float(p.pos().x()), float(p.pos().y())] for p in poly_list]

        try:
            format_yaml_dict(self.yaml_data, fn)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存 YAML 失败：{e}")
            return

        QMessageBox.information(self, "成功", f"已保存到：\n{fn}")

    # ── 图层列表 ─────────────────────────────────────────────

    def _create_layer_item_widget(self, text, is_visible, layer_type, key):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(5)

        eye_btn = QPushButton()
        eye_btn.setFixedSize(24, 24)
        eye_btn.setFlat(True)
        eye_btn.setText("👁️" if is_visible else "🚫")
        eye_btn.setStyleSheet("QPushButton { border: none; font-size: 16px; }")
        eye_btn.clicked.connect(lambda: self._toggle_layer_visibility(layer_type, key))
        layout.addWidget(eye_btn)

        label = QLabel(text)
        layout.addWidget(label, 1)

        widget.setLayout(layout)
        return widget, eye_btn

    def _update_layer_list(self):
        self.layer_list.clear()
        self.layer_eye_buttons = {}

        if self.single_points or self.polygon_items:
            all_visible = all(p.isVisible() for p in self.points.values())
            widget, eye_btn = self._create_layer_item_widget("✅ 全选", all_visible, "select_all", None)
            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            self.layer_list.addItem(item)
            self.layer_list.setItemWidget(item, widget)
            self.layer_eye_buttons[("select_all", None)] = eye_btn

            label = widget.findChild(QLabel)
            if label:
                font = label.font()
                font.setBold(True)
                label.setFont(font)

        for key, p_item in self.single_points.items():
            widget, eye_btn = self._create_layer_item_widget(f"🔴 {key}", p_item.isVisible(), "single", key)
            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            self.layer_list.addItem(item)
            self.layer_list.setItemWidget(item, widget)
            self.layer_eye_buttons[("single", key)] = eye_btn

        for key, poly_list in self.polygon_items.items():
            all_visible = all(p.isVisible() for p in poly_list)
            widget, eye_btn = self._create_layer_item_widget(f"🔷 {key} ({len(poly_list)}点)", all_visible, "polygon", key)
            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            self.layer_list.addItem(item)
            self.layer_list.setItemWidget(item, widget)
            self.layer_eye_buttons[("polygon", key)] = eye_btn

    def _toggle_layer_visibility(self, layer_type, key):
        if layer_type == "select_all":
            all_visible = all(p.isVisible() for p in self.points.values())
            new_visible = not all_visible
            for p_item in self.points.values():
                p_item.setVisible(new_visible)
            self._update_all_labels_visibility()
            for seg in self.segments:
                seg.setVisible(new_visible)
            for btn in self.layer_eye_buttons.values():
                btn.setText("👁️" if new_visible else "🚫")

        elif layer_type == "single":
            if key in self.single_points:
                p_item = self.single_points[key]
                new_visible = not p_item.isVisible()
                p_item.setVisible(new_visible)
                self._update_label_visibility(p_item)
                if ("single", key) in self.layer_eye_buttons:
                    self.layer_eye_buttons[("single", key)].setText("👁️" if new_visible else "🚫")
            self._update_select_all_button()

        elif layer_type == "polygon":
            if key in self.polygon_items:
                poly_list = self.polygon_items[key]
                all_visible = all(p.isVisible() for p in poly_list)
                new_visible = not all_visible
                for p_item in poly_list:
                    p_item.setVisible(new_visible)
                    self._update_label_visibility(p_item)
                for p_item in poly_list:
                    for seg in p_item.segments:
                        seg.setVisible(new_visible)
                if ("polygon", key) in self.layer_eye_buttons:
                    self.layer_eye_buttons[("polygon", key)].setText("👁️" if new_visible else "🚫")
            self._update_select_all_button()

    def _update_select_all_button(self):
        if ("select_all", None) in self.layer_eye_buttons:
            all_visible = all(p.isVisible() for p in self.points.values())
            self.layer_eye_buttons[("select_all", None)].setText("👁️" if all_visible else "🚫")

    # ── 参数变化 ─────────────────────────────────────────────

    def on_point_size_changed(self, value):
        for p in self.points.values():
            p.setPointSize(value)

    def on_line_width_changed(self, value):
        for s in self.segments:
            s.setLineWidth(value)

    def on_alpha_changed(self, value):
        self.alpha_label.setText(f"{value}%")
        if self.bg_item is not None:
            self.bg_item.setOpacity(value / 100.0)

    def _update_label_visibility(self, p_item):
        show_names = self.show_names_checkbox.isChecked()
        p_item.label.setVisible(p_item.isVisible() and show_names)

    def _update_all_labels_visibility(self):
        show_names = self.show_names_checkbox.isChecked()
        for p_item in self.points.values():
            p_item.label.setVisible(p_item.isVisible() and show_names)

    def on_show_names_changed(self, state):
        self._update_all_labels_visibility()

    def on_move_mode_changed(self, state):
        is_move_mode = (state == Qt.Checked)
        self.view.set_move_mode(is_move_mode)
        if is_move_mode:
            self.statusBar().showMessage("移动模式：框选或点击选择多个点，然后拖动或使用方向键移动", 3000)
        else:
            self.statusBar().showMessage("普通模式", 2000)

    def on_select_all_points(self):
        count = 0
        for p_item in self.points.values():
            if p_item.isVisible():
                p_item.setSelected(True)
                count += 1
        self.statusBar().showMessage(f"已选择 {count} 个点", 2000)

    def on_deselect_all_points(self):
        for p_item in self.points.values():
            p_item.setSelected(False)
        self.statusBar().showMessage("已取消所有选择", 2000)

    # ── 鼠标 / 键盘 ──────────────────────────────────────────

    def on_mouse_moved(self, scene_pos: QPointF, point_item):
        self._mouse_label.setText(f"鼠标: ({scene_pos.x():.2f}, {scene_pos.y():.2f})")

        selected_items = [it for it in self.scene.selectedItems() if isinstance(it, CalibrationPointItem)]

        if len(selected_items) == 0:
            if point_item is not None:
                pos = point_item.pos()
                self._selected_label.setText(f"  悬停: {point_item.name} ({pos.x():.2f}, {pos.y():.2f})")
            else:
                self._selected_label.setText("  选中: 无")
        elif len(selected_items) == 1:
            p = selected_items[0]
            pos = p.pos()
            self._selected_label.setText(f"  选中: {p.name} ({pos.x():.2f}, {pos.y():.2f})")
        else:
            self._selected_label.setText(f"  选中: {len(selected_items)} 个点")

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key_M and not event.modifiers():
            self.move_mode_checkbox.setChecked(not self.move_mode_checkbox.isChecked())
            event.accept()
            return

        step = self.step_spin.value()
        if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
            dx, dy = 0.0, 0.0
            if key == Qt.Key_Up:
                dy = -step
            elif key == Qt.Key_Down:
                dy = step
            elif key == Qt.Key_Left:
                dx = -step
            elif key == Qt.Key_Right:
                dx = step

            moved_any = False
            for item in self.scene.selectedItems():
                if isinstance(item, CalibrationPointItem):
                    pos = item.pos()
                    item.setPos(pos.x() + dx, pos.y() + dy)
                    moved_any = True

            if moved_any:
                event.accept()
                count = len([it for it in self.scene.selectedItems() if isinstance(it, CalibrationPointItem)])
                self.statusBar().showMessage(f"移动了 {count} 个点", 1000)
                return

        super().keyPressEvent(event)
