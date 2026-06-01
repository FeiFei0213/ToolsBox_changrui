"""
widget.py — 标注点工具

轻量级图像点标注工具：
- 点击添加标注点（自动编号）
- 拖动单点 / 框选多点后整体拖动
- 右键重命名 / 删除，Delete 键删除选中
- Ctrl+Z / Ctrl+Y 撤销 / 重做
- 自动保存到同目录 {图片名}.json，下次打开同一图片自动加载
- 导出 JSON / CSV，复制坐标到剪贴板
"""
import json
import csv
import logging
from pathlib import Path

import numpy as np
import cv2

from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QTimer
from PySide6.QtGui import (
    QPixmap, QImage, QPen, QBrush, QColor, QFont,
    QPainterPath, QKeySequence, QShortcut, QPainter,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPixmapItem,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QInputDialog, QMenu, QAbstractItemView,
    QGroupBox, QFrame, QApplication, QPlainTextEdit,
)

from tool_base import ToolBase

logger = logging.getLogger(__name__)

_R = 7              # 点的半径（场景像素）
_C_NORMAL   = QColor(255,  80,  80)
_C_SELECTED = QColor(255, 200,   0)
_C_LABEL    = QColor(255, 255, 100)
_C_COORD    = QColor(170, 220, 170)


# ─────────────────────────────────────────────────────────────────
# AnnotationPoint
# ─────────────────────────────────────────────────────────────────

class AnnotationPoint(QGraphicsItem):
    """可拖动、可选择的单个标注点，自定义绘制（圆形 + 标签 + 坐标）。"""

    def __init__(self, x: float, y: float, index: int, label: str = ""):
        super().__init__()
        self.setPos(x, y)
        self.index = index
        self.label = label or f"P{index}"
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(10)

    # ── Qt overrides ──────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        # 包含圆形 + 右侧文字区域
        return QRectF(-_R - 2, -_R - 16, _R * 2 + 90, _R * 2 + 24)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        hit = _R + 4   # 略大于圆半径，更容易点中
        path.addEllipse(-hit, -hit, hit * 2, hit * 2)
        return path

    def paint(self, painter: QPainter, option, widget=None):
        c = _C_SELECTED if self.isSelected() else _C_NORMAL
        painter.setPen(QPen(c, 2))
        painter.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), 160)))
        painter.drawEllipse(-_R, -_R, _R * 2, _R * 2)

        pos = self.pos()

        # 标签（黄色，粗体，右上方）
        painter.setPen(QPen(_C_LABEL))
        f1 = QFont("Arial", 8)
        f1.setBold(True)
        painter.setFont(f1)
        painter.drawText(QPointF(_R + 5, -2), self.label)

        # 坐标（浅绿色，右下方）
        painter.setPen(QPen(_C_COORD))
        f2 = QFont("Arial", 7)
        painter.setFont(f2)
        painter.drawText(QPointF(_R + 5, _R + 9), f"({pos.x():.0f}, {pos.y():.0f})")

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            sc = self.scene()
            if sc and hasattr(sc, "_on_point_moved"):
                sc._on_point_moved(self)
        return super().itemChange(change, value)

    def to_dict(self) -> dict:
        pos = self.pos()
        return {
            "index": self.index,
            "label": self.label,
            "x": round(pos.x(), 1),
            "y": round(pos.y(), 1),
        }


# ─────────────────────────────────────────────────────────────────
# AnnotationScene
# ─────────────────────────────────────────────────────────────────

class AnnotationScene(QGraphicsScene):
    """场景：管理点的增删改，提供撤销/重做栈。"""

    points_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._add_mode = True
        self._undo_stack: list[list[dict]] = []
        self._redo_stack: list[list[dict]] = []
        self._pre_drag_state: list[dict] | None = None

    # ── 图片 ──────────────────────────────────────────────────────

    def load_image(self, path: str) -> tuple[bool, int, int]:
        """加载图片，返回 (成功, 宽, 高)。"""
        self.clear()
        self._pixmap_item = None
        self._undo_stack.clear()
        self._redo_stack.clear()
        try:
            with open(path, "rb") as f:
                data = np.frombuffer(f.read(), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is None:
                return False, 0, 0
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            pm = QPixmap.fromImage(qimg)
        except Exception as e:
            logger.error(f"load image: {e}")
            return False, 0, 0
        self._pixmap_item = self.addPixmap(pm)
        self._pixmap_item.setZValue(0)
        self.setSceneRect(QRectF(pm.rect()))
        return True, pm.width(), pm.height()

    # ── 点操作 ────────────────────────────────────────────────────

    def annotation_points(self) -> list[AnnotationPoint]:
        return [i for i in self.items() if isinstance(i, AnnotationPoint)]

    def _next_index(self) -> int:
        pts = self.annotation_points()
        return max((p.index for p in pts), default=0) + 1

    def add_point(self, x: float, y: float,
                  index: int | None = None, label: str = "") -> AnnotationPoint:
        idx = index if index is not None else self._next_index()
        pt = AnnotationPoint(x, y, idx, label)
        self.addItem(pt)
        self.points_changed.emit()
        return pt

    def delete_point(self, pt: AnnotationPoint):
        self._push_undo()
        self.removeItem(pt)
        self.points_changed.emit()

    def delete_selected(self):
        sel = [i for i in self.selectedItems() if isinstance(i, AnnotationPoint)]
        if not sel:
            return
        self._push_undo()
        for pt in sel:
            self.removeItem(pt)
        self.points_changed.emit()

    def rename_point(self, pt: AnnotationPoint, new_label: str):
        self._push_undo()
        pt.label = new_label
        pt.update()
        self.points_changed.emit()

    def clear_all_points(self):
        if not self.annotation_points():
            return
        self._push_undo()
        for pt in self.annotation_points():
            self.removeItem(pt)
        self.points_changed.emit()

    def load_points(self, data: list[dict]):
        for d in data:
            self.add_point(
                float(d["x"]), float(d["y"]),
                int(d.get("index", self._next_index())),
                str(d.get("label", ""))
            )

    def select_all(self):
        for pt in self.annotation_points():
            pt.setSelected(True)

    def offset_selected(self, dx: float, dy: float):
        """将所有选中点整体平移 (dx, dy) 像素，可撤销。"""
        sel = [i for i in self.selectedItems() if isinstance(i, AnnotationPoint)]
        if not sel:
            return
        self._push_undo()
        for pt in sel:
            pt.setPos(pt.pos().x() + dx, pt.pos().y() + dy)
        self.points_changed.emit()

    # ── 撤销 / 重做 ───────────────────────────────────────────────

    def _serialize(self) -> list[dict]:
        return [
            p.to_dict()
            for p in sorted(self.annotation_points(), key=lambda p: p.index)
        ]

    def _push_undo(self):
        self._undo_stack.append(self._serialize())
        self._redo_stack.clear()

    def _restore(self, state: list[dict]):
        for pt in self.annotation_points():
            self.removeItem(pt)
        for d in state:
            pt = AnnotationPoint(float(d["x"]), float(d["y"]), int(d["index"]), str(d["label"]))
            self.addItem(pt)
        self.points_changed.emit()

    def undo(self):
        if self._undo_stack:
            self._redo_stack.append(self._serialize())
            self._restore(self._undo_stack.pop())

    def redo(self):
        if self._redo_stack:
            self._undo_stack.append(self._serialize())
            self._restore(self._redo_stack.pop())

    # ── 鼠标事件 ──────────────────────────────────────────────────

    def _on_point_moved(self, _pt: AnnotationPoint):
        self.points_changed.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            hits = [i for i in self.items(event.scenePos())
                    if isinstance(i, AnnotationPoint)]
            if hits:
                # 点击在已有点上 → 记录拖动前快照
                self._pre_drag_state = self._serialize()
            elif (self._add_mode
                  and self._pixmap_item is not None
                  and self._pixmap_item.contains(event.scenePos())):
                # 点击空白图像区域 → 新增点
                self._push_undo()
                self.add_point(event.scenePos().x(), event.scenePos().y())
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._pre_drag_state is not None:
            current = self._serialize()
            if self._pre_drag_state != current:
                # 位置真的变了 → 把拖动前快照压栈
                self._undo_stack.append(self._pre_drag_state)
                self._redo_stack.clear()
                self.points_changed.emit()
            self._pre_drag_state = None

    def contextMenuEvent(self, event):
        hits = [i for i in self.items(event.scenePos())
                if isinstance(i, AnnotationPoint)]
        if not hits:
            return
        pt = hits[0]
        sel = [i for i in self.selectedItems() if isinstance(i, AnnotationPoint)]

        menu = QMenu()
        rename_act  = menu.addAction(f'重命名 "{pt.label}"')
        menu.addSeparator()
        delete_act  = menu.addAction(f'删除 "{pt.label}"')
        del_sel_act = None
        if len(sel) > 1:
            del_sel_act = menu.addAction(f"删除选中的 {len(sel)} 个点")

        view = self.views()[0] if self.views() else None
        result = menu.exec(event.screenPos().toPoint())

        if result == rename_act:
            new_label, ok = QInputDialog.getText(
                view, "重命名", f"新标签（当前：{pt.label}）：", text=pt.label
            )
            if ok and new_label.strip():
                self.rename_point(pt, new_label.strip())
        elif result == delete_act:
            self.delete_point(pt)
        elif del_sel_act and result == del_sel_act:
            self.delete_selected()


# ─────────────────────────────────────────────────────────────────
# AnnotationViewer
# ─────────────────────────────────────────────────────────────────

class AnnotationViewer(QGraphicsView):
    """图片查看器：滚轮缩放，中键平移，支持标注/选择两种模式。"""

    mouse_moved = Signal(float, float)  # 场景坐标，用于状态栏显示

    def __init__(self, scene: AnnotationScene, parent=None):
        super().__init__(scene, parent)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setMinimumWidth(500)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._panning = False
        self._pan_start: QPointF | None = None

    def set_mode(self, add_mode: bool):
        ann_scene: AnnotationScene = self.scene()
        ann_scene._add_mode = add_mode
        if add_mode:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_start is not None:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(
                int(self.verticalScrollBar().value() - delta.y()))
            event.accept()
            return
        # 发出鼠标场景坐标
        sp = self.mapToScene(event.position().toPoint())
        self.mouse_moved.emit(sp.x(), sp.y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            ann_scene: AnnotationScene = self.scene()
            self.setCursor(
                Qt.CursorShape.CrossCursor if ann_scene._add_mode
                else Qt.CursorShape.ArrowCursor
            )
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ─────────────────────────────────────────────────────────────────
# PointListPanel
# ─────────────────────────────────────────────────────────────────

class PointListPanel(QWidget):
    """侧边栏：点列表（实时同步）+ 导出操作。"""

    selected_indices_changed  = Signal(set)         # 用户在表格中选了哪些行
    offset_requested          = Signal(float, float) # (dx, dy)
    select_all_requested      = Signal()
    save_extra_json_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._build()
        self.setMinimumWidth(260)
        self.setMaximumWidth(340)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── 列表 ──────────────────────────────────────────────────
        list_group = QGroupBox("标注点列表")
        lg = QVBoxLayout(list_group)
        lg.setSpacing(4)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "标签", "X", "Y"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 32)
        self.table.setColumnWidth(2, 58)
        self.table.setColumnWidth(3, 58)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(220)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        lg.addWidget(self.table)

        layout.addWidget(list_group, 1)

        # ── 操作 ──────────────────────────────────────────────────
        op_group = QGroupBox("操作")
        og = QVBoxLayout(op_group)
        og.setSpacing(6)

        self.export_json_btn = QPushButton("导出 JSON")
        self.export_csv_btn  = QPushButton("导出 CSV")
        self.copy_btn        = QPushButton("复制坐标到剪贴板")
        self.clear_btn       = QPushButton("清空所有点")
        self.clear_btn.setStyleSheet("QPushButton { color: #cc0000; }")

        for btn in (self.export_json_btn, self.export_csv_btn,
                    self.copy_btn, self.clear_btn):
            og.addWidget(btn)

        layout.addWidget(op_group)

        # ── 偏移调整 ──────────────────────────────────────────────
        off_group = QGroupBox("偏移选中点")
        fl = QVBoxLayout(off_group)
        fl.setSpacing(6)

        # 步长输入
        from PySide6.QtWidgets import QSpinBox, QGridLayout
        step_row = QHBoxLayout()
        step_row.addWidget(QLabel("步长:"))
        self.step_spin = QSpinBox()
        self.step_spin.setRange(1, 9999)
        self.step_spin.setValue(1)
        self.step_spin.setSuffix(" px")
        step_row.addWidget(self.step_spin, 1)
        fl.addLayout(step_row)

        # 方向按钮（十字形排列）
        arrow_grid = QGridLayout()
        arrow_grid.setSpacing(4)
        arrow_grid.setContentsMargins(0, 0, 0, 0)

        self._up_btn    = QPushButton("↑")
        self._down_btn  = QPushButton("↓")
        self._left_btn  = QPushButton("←")
        self._right_btn = QPushButton("→")

        for b in (self._up_btn, self._down_btn, self._left_btn, self._right_btn):
            b.setFixedSize(40, 32)

        arrow_grid.addWidget(self._up_btn,    0, 1)
        arrow_grid.addWidget(self._left_btn,  1, 0)
        arrow_grid.addWidget(self._right_btn, 1, 2)
        arrow_grid.addWidget(self._down_btn,  2, 1)

        center_lbl = QLabel("·")
        center_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow_grid.addWidget(center_lbl, 1, 1)

        fl.addLayout(arrow_grid)

        # 全选
        self.select_all_btn = QPushButton("全选所有点  (Ctrl+A)")
        fl.addWidget(self.select_all_btn)

        layout.addWidget(off_group)

        # 连接方向按钮信号
        self._up_btn.clicked.connect(
            lambda: self.offset_requested.emit(0, -self.step_spin.value()))
        self._down_btn.clicked.connect(
            lambda: self.offset_requested.emit(0, self.step_spin.value()))
        self._left_btn.clicked.connect(
            lambda: self.offset_requested.emit(-self.step_spin.value(), 0))
        self._right_btn.clicked.connect(
            lambda: self.offset_requested.emit(self.step_spin.value(), 0))
        self.select_all_btn.clicked.connect(self.select_all_requested)

        # ── Extra JSON 提取 ───────────────────────────────────────
        extra_group = QGroupBox("Extra JSON 坐标")
        eg = QVBoxLayout(extra_group)
        eg.setSpacing(4)

        self.extra_json_edit = QPlainTextEdit()
        self.extra_json_edit.setReadOnly(True)
        self.extra_json_edit.setPlaceholderText("[x,y],\n格式输出…")
        self.extra_json_edit.setMaximumHeight(110)
        eg.addWidget(self.extra_json_edit)

        extra_btn_row = QHBoxLayout()
        self.extra_copy_btn = QPushButton("复制")
        self.extra_save_btn = QPushButton("保存")
        extra_btn_row.addWidget(self.extra_copy_btn)
        extra_btn_row.addWidget(self.extra_save_btn)
        eg.addLayout(extra_btn_row)

        layout.addWidget(extra_group)

        self.extra_copy_btn.clicked.connect(self._copy_extra_json)
        self.extra_save_btn.clicked.connect(self.save_extra_json_requested)

    # ── 刷新 ──────────────────────────────────────────────────────

    def refresh(self, points: list[AnnotationPoint]):
        self._updating = True
        prev_sel = self._selected_indices()
        self.table.setRowCount(0)
        for pt in sorted(points, key=lambda p: p.index):
            row = self.table.rowCount()
            self.table.insertRow(row)
            pos = pt.pos()
            for col, val in enumerate([
                str(pt.index), pt.label,
                f"{pos.x():.0f}", f"{pos.y():.0f}"
            ]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setData(Qt.ItemDataRole.UserRole, pt.index)
                self.table.setItem(row, col, item)
        self._updating = False
        self.sync_selection(prev_sel)

    def sync_selection(self, indices: set[int]):
        self._updating = True
        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) in indices:
                self.table.selectRow(row)
        self._updating = False

    def _selected_indices(self) -> set[int]:
        result = set()
        for item in self.table.selectedItems():
            idx = item.data(Qt.ItemDataRole.UserRole)
            if idx is not None:
                result.add(idx)
        return result

    def _on_table_selection(self):
        if self._updating:
            return
        self.selected_indices_changed.emit(self._selected_indices())

    def refresh_extra_json(self, points: list):
        lines = [
            f"[{p.pos().x():.2f},{p.pos().y():.2f}],"
            for p in sorted(points, key=lambda p: p.index)
        ]
        self.extra_json_edit.setPlainText("\n".join(lines))

    def _copy_extra_json(self):
        text = self.extra_json_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)


# ─────────────────────────────────────────────────────────────────
# PointAnnotatorWidget
# ─────────────────────────────────────────────────────────────────

class PointAnnotatorWidget(ToolBase):
    tool_name        = "标注点工具"
    tool_description = "图片上点击标注坐标点，支持拖动/撤销/自动保存复用"
    tool_icon        = "📌"

    def init_ui(self):
        self.resize(1200, 720)
        self._image_path: str | None = None

        # 自动保存防抖（500ms）
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._auto_save)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scene  = AnnotationScene()
        self._viewer = AnnotationViewer(self._scene)

        root.addWidget(self._build_toolbar())
        self._panel  = PointListPanel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._viewer)
        splitter.addWidget(self._panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([900, 300])
        root.addWidget(splitter, 1)

        # ── 底部状态栏（左：状态文字，右：实时坐标）────────────────
        status_bar = QWidget()
        status_bar.setStyleSheet(
            "QWidget { background:#f8f8f8; border-top:1px solid #ddd; }"
        )
        sb = QHBoxLayout(status_bar)
        sb.setContentsMargins(10, 3, 10, 3)
        sb.setSpacing(0)

        self._status = QLabel("就绪  |  打开图片开始标注")
        self._status.setStyleSheet("color:#555; font-size:12px;")
        sb.addWidget(self._status, 1)

        self._coord_label = QLabel("—")
        self._coord_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._coord_label.setStyleSheet(
            "color:#1565C0; font-size:14px; font-weight:bold;"
            "background:#ddeeff; border-radius:4px; padding:1px 10px;"
            "min-width:160px;"
        )
        sb.addWidget(self._coord_label)

        root.addWidget(status_bar)

        # ── 信号连接 ──────────────────────────────────────────────
        self._scene.points_changed.connect(self._on_points_changed)
        self._viewer.mouse_moved.connect(self._on_mouse_moved)

        self._panel.export_json_btn.clicked.connect(self._export_json)
        self._panel.export_csv_btn.clicked.connect(self._export_csv)
        self._panel.copy_btn.clicked.connect(self._copy_coords)
        self._panel.clear_btn.clicked.connect(self._clear_all)
        self._panel.selected_indices_changed.connect(self._on_table_selection_changed)
        self._panel.offset_requested.connect(self._scene.offset_selected)
        self._panel.select_all_requested.connect(self._select_all)
        self._panel.save_extra_json_requested.connect(self._save_extra_json)

        # ── 快捷键 ────────────────────────────────────────────────
        QShortcut(QKeySequence.StandardKey.Undo,      self, self._scene.undo)
        QShortcut(QKeySequence.StandardKey.Redo,      self, self._scene.redo)
        QShortcut(QKeySequence.StandardKey.Open,      self, self._open_image)
        QShortcut(QKeySequence.StandardKey.SelectAll, self, self._select_all)
        QShortcut(QKeySequence(Qt.Key.Key_Delete),    self, self._scene.delete_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Tab),       self, self._toggle_mode)

    # ── 工具栏 ────────────────────────────────────────────────────

    def _build_toolbar(self) -> QWidget:
        tb = QWidget()
        tb.setStyleSheet(
            "QWidget { background:#f0f0f0; border-bottom:1px solid #ccc; }"
            "QPushButton { padding: 4px 12px; }"
            "QPushButton:checked { background:#1976D2; color:white; border-radius:4px; }"
        )
        layout = QHBoxLayout(tb)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        open_btn = QPushButton("打开图片")
        open_btn.setToolTip("Ctrl+O")
        open_btn.clicked.connect(self._open_image)
        layout.addWidget(open_btn)

        layout.addWidget(self._vline())

        self._add_btn = QPushButton("📌 标注模式")
        self._add_btn.setCheckable(True)
        self._add_btn.setChecked(True)
        self._add_btn.setToolTip("点击图片空白处添加点  （Tab 切换）")
        self._add_btn.toggled.connect(lambda on: self._set_mode(add_mode=on))
        layout.addWidget(self._add_btn)

        self._sel_btn = QPushButton("🔲 选择模式")
        self._sel_btn.setCheckable(True)
        self._sel_btn.setChecked(False)
        self._sel_btn.setToolTip("框选多个点再拖动  （Tab 切换）")
        self._sel_btn.toggled.connect(lambda on: self._set_mode(add_mode=not on))
        layout.addWidget(self._sel_btn)

        layout.addWidget(self._vline())

        undo_btn = QPushButton("↩ 撤销")
        undo_btn.setToolTip("Ctrl+Z")
        undo_btn.clicked.connect(self._scene.undo)
        layout.addWidget(undo_btn)

        redo_btn = QPushButton("↪ 重做")
        redo_btn.setToolTip("Ctrl+Y")
        redo_btn.clicked.connect(self._scene.redo)
        layout.addWidget(redo_btn)

        layout.addWidget(self._vline())

        fit_btn = QPushButton("适应窗口")
        fit_btn.clicked.connect(self._fit_view)
        layout.addWidget(fit_btn)

        layout.addWidget(self._vline())

        import_pts_btn = QPushButton("导入点")
        import_pts_btn.setToolTip("从 JSON 文件读取点坐标，替换当前画布上的标注点")
        import_pts_btn.clicked.connect(self._import_points_from_file)
        layout.addWidget(import_pts_btn)

        layout.addStretch()

        self._pos_label = QLabel("")
        self._pos_label.setStyleSheet("color:#333; font-size:12px; min-width:120px;")
        layout.addWidget(self._pos_label)

        return tb

    @staticmethod
    def _vline() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFrameShadow(QFrame.Shadow.Sunken)
        return f

    # ── 模式切换 ──────────────────────────────────────────────────

    def _set_mode(self, add_mode: bool):
        self._add_btn.blockSignals(True)
        self._sel_btn.blockSignals(True)
        self._add_btn.setChecked(add_mode)
        self._sel_btn.setChecked(not add_mode)
        self._add_btn.blockSignals(False)
        self._sel_btn.blockSignals(False)
        self._viewer.set_mode(add_mode)

    def _toggle_mode(self):
        self._set_mode(not self._scene._add_mode)

    # ── 图片加载 ──────────────────────────────────────────────────

    def _open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.tiff *.tif)"
        )
        if not path:
            return
        ok, w, h = self._scene.load_image(path)
        if not ok:
            QMessageBox.warning(self, "错误", f"无法加载图片:\n{path}")
            return
        self._image_path = path
        self.setWindowTitle(f"标注点工具 — {Path(path).name}")
        self._fit_view()

        # 自动加载上次标注
        annot = self._annot_path()
        if annot and annot.exists():
            try:
                saved = json.loads(annot.read_text(encoding="utf-8"))
                pts = saved.get("points", [])
                self._scene.load_points(pts)
                self._set_status(
                    f"已加载上次标注（{len(pts)} 个点）  |  图片: {w}×{h}"
                )
            except Exception as e:
                logger.warning(f"load annot: {e}")
                self._set_status(f"图片已加载  |  {w}×{h}")
        else:
            self._set_status(f"图片已加载  |  {w}×{h}  |  点击添加标注点")

    def _fit_view(self):
        if self._scene.sceneRect().isValid():
            self._viewer.fitInView(
                self._scene.sceneRect(),
                Qt.AspectRatioMode.KeepAspectRatio
            )

    # ── 自动保存 ──────────────────────────────────────────────────

    def _annot_path(self) -> Path | None:
        return Path(self._image_path).with_suffix(".json") if self._image_path else None

    def _auto_save(self):
        path = self._annot_path()
        if not path:
            return
        pts = sorted(self._scene.annotation_points(), key=lambda p: p.index)
        data = {
            "image":  self._image_path,
            "points": [p.to_dict() for p in pts],
        }
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"auto-save: {e}")

    # ── 事件响应 ──────────────────────────────────────────────────

    def _on_points_changed(self):
        pts = self._scene.annotation_points()
        self._panel.refresh(pts)
        self._panel.refresh_extra_json(pts)
        sel_idx = {p.index for p in self._scene.selectedItems()
                   if isinstance(p, AnnotationPoint)}
        self._panel.sync_selection(sel_idx)
        self._set_status(f"共 {len(pts)} 个标注点")
        self._save_timer.start()

    def _on_mouse_moved(self, x: float, y: float):
        self._pos_label.setText(f"({x:.0f}, {y:.0f})")
        self._coord_label.setText(f"X: {x:.0f}   Y: {y:.0f}")

    def _on_table_selection_changed(self, indices: set[int]):
        self._scene.clearSelection()
        for pt in self._scene.annotation_points():
            if pt.index in indices:
                pt.setSelected(True)

    # ── 操作 ──────────────────────────────────────────────────────

    def _select_all(self):
        self._scene.select_all()

    def _clear_all(self):
        if not self._scene.annotation_points():
            return
        reply = QMessageBox.question(
            self, "确认清空", "删除所有标注点？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._scene.clear_all_points()

    def _export_json(self):
        pts = sorted(self._scene.annotation_points(), key=lambda p: p.index)
        if not pts:
            QMessageBox.information(self, "提示", "没有标注点")
            return
        default = (str(Path(self._image_path).with_suffix(".json"))
                   if self._image_path else "points.json")
        path, _ = QFileDialog.getSaveFileName(self, "导出 JSON", default, "JSON (*.json)")
        if not path:
            return
        data = {"image": self._image_path, "points": [p.to_dict() for p in pts]}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        QMessageBox.information(self, "导出成功", f"已保存到:\n{path}")

    def _export_csv(self):
        pts = sorted(self._scene.annotation_points(), key=lambda p: p.index)
        if not pts:
            QMessageBox.information(self, "提示", "没有标注点")
            return
        default = (str(Path(self._image_path).with_suffix(".csv"))
                   if self._image_path else "points.csv")
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", default, "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["index", "label", "x", "y"])
            for p in pts:
                d = p.to_dict()
                writer.writerow([d["index"], d["label"], d["x"], d["y"]])
        QMessageBox.information(self, "导出成功", f"已保存到:\n{path}")

    def _copy_coords(self):
        pts = sorted(self._scene.annotation_points(), key=lambda p: p.index)
        if not pts:
            QMessageBox.information(self, "提示", "没有标注点")
            return
        lines = [f"{p.label}\t{p.pos().x():.0f}\t{p.pos().y():.0f}" for p in pts]
        QApplication.clipboard().setText("\n".join(lines))
        self._set_status(f"已复制 {len(pts)} 个点的坐标到剪贴板")

    def _import_points_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择标注文件", "", "JSON 文件 (*.json)"
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            pts = data.get("points", [])
            if not pts:
                QMessageBox.information(self, "提示", "文件中没有找到点数据")
                return
        except Exception as e:
            QMessageBox.critical(self, "读取失败", str(e))
            return

        if self._scene.annotation_points():
            reply = QMessageBox.question(
                self, "替换确认",
                f"当前画布已有 {len(self._scene.annotation_points())} 个点，\n"
                f"是否替换为文件中的 {len(pts)} 个点？\n\n"
                "（Yes=替换  No=追加）",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No  |
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._scene._push_undo()
                for pt in self._scene.annotation_points():
                    self._scene.removeItem(pt)
        self._scene.load_points(pts)
        self._set_status(f"已导入 {len(pts)} 个点（来自 {Path(path).name}）")

    def _save_extra_json(self):
        text = self._panel.extra_json_edit.toPlainText()
        if not text:
            QMessageBox.information(self, "提示", "没有坐标数据")
            return
        default = (str(Path(self._image_path).with_suffix(".coords.txt"))
                   if self._image_path else "coords.txt")
        path, _ = QFileDialog.getSaveFileName(
            self, "保存坐标文本", default, "文本文件 (*.txt);;所有文件 (*)"
        )
        if not path:
            return
        Path(path).write_text(text, encoding="utf-8")
        self._set_status(f"Extra JSON 坐标已保存到: {Path(path).name}")

    def _set_status(self, text: str):
        self._status.setText(text)
