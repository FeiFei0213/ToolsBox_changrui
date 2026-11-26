"""从 ToolsBox 打开并浏览同目录图片。"""

import re
from math import hypot
from pathlib import Path

import cv2
from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QToolBar, QVBoxLayout

from tool_base import ToolBase
from tools.image_io import read_image
from tools.image_preview import array_to_pixmap
from tools.image_viewer.canvas import ImageCanvas

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")
OPEN_FILTER = "图片文件 (" + " ".join(f"*{suffix}" for suffix in IMAGE_SUFFIXES) + ")"


def _filename_key(path: Path) -> tuple:
    parts = re.split(r"([0-9]+)", path.name.casefold())
    return tuple(int(part) if i % 2 else part for i, part in enumerate(parts)), path.name


class ImageViewerWidget(ToolBase):
    tool_name = "Ziv 看图"
    tool_description = "浏览同目录图片，支持缩放、准星和两点测距"
    tool_icon = "🖼️"

    def init_ui(self):
        self.setMinimumSize(640, 400)
        self.resize(QSize(1080, 720).boundedTo(self.screen().availableGeometry().size() - QSize(32, 64)))
        self.setAcceptDrops(True)
        self._images: list[Path] = []
        self._index = -1

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        toolbar = QToolBar("看图操作")
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        root.addWidget(toolbar)

        self.view = ImageCanvas()
        root.addWidget(self.view, 1)

        details = QHBoxLayout()
        details.setSpacing(14)
        self.file_label = QLabel("打开或拖入一张图片")
        self.file_label.setMinimumWidth(160)
        self.file_label.setWordWrap(True)
        self.file_label.setTextFormat(Qt.TextFormat.PlainText)
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.addWidget(self.file_label, 1)
        self.index_label = QLabel("0 / 0")
        self.size_label = QLabel("— × — px")
        self.zoom_label = QLabel("— %")
        self.coordinate_label = QLabel("X —  Y —")
        for label in (self.index_label, self.size_label, self.zoom_label, self.coordinate_label):
            details.addWidget(label)
        root.addLayout(details)

        footer = QHBoxLayout()
        self.measurement_label = QLabel("按 M 开始两点测距")
        self.notice_label = QLabel()
        self.notice_label.setTextFormat(Qt.TextFormat.PlainText)
        self.notice_label.setWordWrap(True)
        self.notice_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        footer.addWidget(self.measurement_label)
        footer.addWidget(self.notice_label, 1)
        root.addLayout(footer)

        self._action(toolbar, "打开图片…", "Ctrl+O", self._browse_image)
        toolbar.addSeparator()
        self.previous_action = self._action(toolbar, "上一张", "Left", lambda: self._step(-1))
        self.next_action = self._action(toolbar, "下一张", "Right", lambda: self._step(1))
        toolbar.addSeparator()
        self.fit_action = self._action(toolbar, "适应窗口", "F", self.view.fit_image)
        self.original_size_action = self._action(toolbar, "原始大小", "1", self.view.actual_size)
        toolbar.addSeparator()
        self.crosshair_action = self._action(toolbar, "十字准星", "C", self.view.set_crosshair, checkable=True)
        self.measurement_action = self._action(toolbar, "两点测距", "M", self.view.set_measuring, checkable=True)
        self.clear_action = self._action(toolbar, "清除测距", "Esc", self.view.clear_measurement)
        self.clear_action.setEnabled(False)

        self.view.coordinate_changed.connect(self._show_coordinates)
        self.view.zoom_changed.connect(lambda scale: self.zoom_label.setText(f"{scale:.1%}"))
        self.view.measurement_changed.connect(self._show_measurement)
        self._refresh_actions()

    def _action(self, toolbar, label, shortcut, callback, *, checkable=False) -> QAction:
        action = QAction(label, self)
        action.setShortcut(QKeySequence(shortcut))
        action.setToolTip(f"{label}（{action.shortcut().toString()}）")
        action.setCheckable(checkable)
        action.setAutoRepeat(not checkable)
        if checkable:
            action.toggled.connect(callback)
        else:
            action.triggered.connect(callback)
        toolbar.addAction(action)
        return action

    @property
    def current_path(self) -> Path | None:
        return self._images[self._index] if self._index >= 0 else None

    def _refresh_actions(self):
        browsing = self.current_path is not None
        for action in (self.fit_action, self.original_size_action, self.crosshair_action,
                       self.measurement_action):
            action.setEnabled(browsing)
        for action in (self.previous_action, self.next_action):
            action.setEnabled(len(self._images) > 1)

    def _browse_image(self):
        folder = str(self.current_path.parent) if self.current_path is not None else ""
        name, _ = QFileDialog.getOpenFileName(self, "打开图片", folder, OPEN_FILTER)
        if name:
            self.load_image(name)

    def load_image(self, path: str | Path):
        path = Path(path).absolute()
        try:
            pixmap = array_to_pixmap(read_image(path))
        except (ValueError, MemoryError, cv2.error) as exc:
            self.notice_label.setText(f"打开失败 · {path.name} · {exc}")
            return
        try:
            candidates = {
                item for item in path.parent.iterdir()
                if item.suffix.lower() in IMAGE_SUFFIXES and item.is_file()
            }
        except OSError:
            candidates = set()
        candidates.add(path)
        self._images = sorted(candidates, key=_filename_key)
        self._show_image(self._images.index(path), pixmap)

    def _step(self, step: int):
        count = len(self._images)
        skipped = 0
        for offset in range(1, count):
            index = (self._index + step * offset) % count
            try:
                pixmap = array_to_pixmap(read_image(self._images[index]))
            except (ValueError, MemoryError, cv2.error):
                skipped += 1
                continue
            self._show_image(index, pixmap)
            if skipped:
                self.notice_label.setText(f"已跳过 {skipped} 张无法打开的图片")
            return
        if count > 1:
            self.notice_label.setText("没有其他可打开的图片")

    def _show_image(self, index: int, pixmap: QPixmap):
        self._index = index
        path = self._images[index]
        self.file_label.setText(path.name)
        self.file_label.setToolTip(str(path))
        self.index_label.setText(f"{index + 1} / {len(self._images)}")
        self.size_label.setText(f"{pixmap.width()} × {pixmap.height()} px")
        self.notice_label.clear()
        self.view.set_image(pixmap)
        self.view.setFocus()
        self._refresh_actions()

    def _show_coordinates(self, pixel: QPoint | None):
        self.coordinate_label.setText(f"X {pixel.x()}  Y {pixel.y()}" if pixel is not None else "X —  Y —")

    def _show_measurement(self, points: tuple[QPoint, ...]):
        self.clear_action.setEnabled(bool(points))
        if not points:
            message = "点击图片选取起点" if self.measurement_action.isChecked() else "按 M 开始两点测距"
        elif len(points) == 1:
            start, = points
            message = f"起点 ({start.x()}, {start.y()}) · 请选择终点"
        else:
            start, end = points
            distance = hypot(end.x() - start.x(), end.y() - start.y())
            message = f"({start.x()}, {start.y()}) → ({end.x()}, {end.y()}) · {distance:.2f} px"
        self.measurement_label.setText(message)

    @staticmethod
    def _dropped_image(event) -> Path | None:
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.suffix.lower() in IMAGE_SUFFIXES:
                    return path
        return None

    def dragEnterEvent(self, event):
        if self._dropped_image(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._dropped_image(event)
        if path is not None:
            self.load_image(path)
            event.acceptProposedAction()
        else:
            event.ignore()
