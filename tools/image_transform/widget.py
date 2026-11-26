"""图片变换工具界面。"""

from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QSplitter, QToolButton, QVBoxLayout,
)

from tool_base import ToolBase
from tools.image_io import read_image
from tools.image_preview import PreviewLabel
from tools.image_transform.core import (
    IMAGE_SUFFIXES, OUTPUT_FORMATS, TransformHistory, flip_image, rotate_image,
    save_image, validate_image,
)

OPEN_FILTER = "图片文件 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"


class ImageTransformWidget(ToolBase):
    tool_name = "图片变换"
    tool_description = "镜像、旋转并导出图片，支持操作历史"
    tool_icon = "🔄"

    def init_ui(self):
        self.setMinimumSize(730, 440)
        self.resize(QSize(980, 640).boundedTo(self.screen().availableGeometry().size() - QSize(32, 64)))
        self.setAcceptDrops(True)
        self._source_path: Path | None = None
        self._history: TransformHistory | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        file_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("打开或拖入图片")
        file_row.addWidget(self._button("打开图片…", "Ctrl+O", self._browse_open))
        file_row.addWidget(self.path_edit, 1)
        save_btn = self._button("另存结果…", "Ctrl+S", self._browse_save)
        self.save_action = save_btn.defaultAction()
        file_row.addWidget(save_btn)
        root.addLayout(file_row)

        controls = QGroupBox("变换")
        controls_layout = QVBoxLayout(controls)
        quick = QHBoxLayout()
        clockwise = self._button("顺时针 90°", "Alt+Right", lambda: self._rotate(90))
        counterclockwise = self._button("逆时针 90°", "Alt+Left", lambda: self._rotate(-90))
        horizontal = self._button("左右镜像", "Alt+H", lambda: self._flip(True))
        vertical = self._button("上下镜像", "Alt+V", lambda: self._flip(False))
        for button in (counterclockwise, clockwise, horizontal, vertical):
            quick.addWidget(button)
        quick.addStretch()
        undo = self._button("撤销", "Ctrl+Z", self._undo)
        redo = self._button("重做", "Ctrl+Y", self._redo)
        reset = self._button("恢复原图", "Ctrl+R", self._reset)
        self.undo_action = undo.defaultAction()
        self.redo_action = redo.defaultAction()
        self.reset_action = reset.defaultAction()
        for button in (undo, redo, reset):
            quick.addWidget(button)
        controls_layout.addLayout(quick)

        angle_row = QHBoxLayout()
        self.angle_spin = QDoubleSpinBox()
        self.angle_spin.setRange(-360, 360)
        self.angle_spin.setDecimals(2)
        self.angle_spin.setSuffix("°")
        self.angle_spin.setAccessibleName("旋转角度，正值为顺时针")
        angle_row.addWidget(QLabel("旋转角度（正值为顺时针）"))
        angle_row.addWidget(self.angle_spin)
        apply = self._button("应用角度", "", lambda: self._rotate(self.angle_spin.value()))
        angle_row.addWidget(apply)
        angle_row.addStretch()
        controls_layout.addLayout(angle_row)
        self._transform_actions = [
            button.defaultAction() for button in
            (clockwise, counterclockwise, horizontal, vertical, apply)
        ]
        root.addWidget(controls)

        previews = QSplitter(Qt.Orientation.Horizontal)
        previews.setChildrenCollapsible(False)
        self.original_preview = PreviewLabel("尚未加载图片")
        self.result_preview = PreviewLabel("尚未加载图片")
        for title, preview in (("原图", self.original_preview), ("当前结果", self.result_preview)):
            box = QGroupBox(title)
            QVBoxLayout(box).addWidget(preview)
            previews.addWidget(box)
        previews.setSizes([480, 480])
        root.addWidget(previews, 1)

        footer = QHBoxLayout()
        self.dimensions = QLabel()
        self.status = QLabel("就绪")
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight)
        footer.addWidget(self.dimensions)
        footer.addStretch()
        footer.addWidget(self.status, 1)
        root.addLayout(footer)
        self._refresh_controls()

    @property
    def current_image(self) -> np.ndarray | None:
        return self._history.current if self._history is not None else None

    def _button(self, label, shortcut, callback) -> QToolButton:
        action = QAction(label, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            action.setAutoRepeat(False)
            action.setToolTip(f"{label}（{action.shortcut().toString()}）")
        action.triggered.connect(callback)
        self.addAction(action)
        button = QToolButton()
        button.setDefaultAction(action)
        return button

    def _refresh_controls(self):
        history = self._history
        loaded = history is not None
        self.angle_spin.setEnabled(loaded)
        for action in [self.save_action, *self._transform_actions]:
            action.setEnabled(loaded)
        self.undo_action.setEnabled(loaded and history.can_undo)
        self.redo_action.setEnabled(loaded and history.can_redo)
        self.reset_action.setEnabled(loaded and history.current is not history.source)

    def _show_result(self, message: str):
        image = self.current_image
        if image is None:
            return
        self.result_preview.set_array(image)
        height, width = image.shape[:2]
        channels = 1 if image.ndim == 2 else image.shape[2]
        self.dimensions.setText(f"结果 {width} × {height} px · {channels} 通道 · {image.dtype.itemsize * 8} 位")
        self.status.setText(message)
        self._refresh_controls()

    def _browse_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开图片", str(self._source_path or ""), OPEN_FILTER,
        )
        if path:
            self.load_image(path)

    def load_image(self, path: str | Path):
        path = Path(path)
        try:
            image = read_image(path)
            validate_image(image)
        except ValueError as exc:
            self.status.setText("图片加载失败")
            QMessageBox.warning(self, "图片加载失败", str(exc))
            return

        self._source_path = path
        self._history = TransformHistory(image)
        self.path_edit.setText(str(path))
        self.angle_spin.setValue(0)
        self.original_preview.set_array(image)
        self._show_result("图片已加载")

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
        if path is None:
            event.ignore()
            return
        self.load_image(path)
        event.acceptProposedAction()

    def _rotate(self, degrees: float):
        if degrees % 360:
            self._apply_transform(lambda image: rotate_image(image, degrees), f"已旋转 {degrees:g}°")

    def _flip(self, horizontal: bool):
        self._apply_transform(
            lambda image: flip_image(image, horizontal=horizontal),
            "已左右镜像" if horizontal else "已上下镜像",
        )

    def _apply_transform(self, operation: Callable[[np.ndarray], np.ndarray], message: str):
        history = self._history
        if history is None:
            return
        try:
            result = operation(history.current)
        except (ValueError, cv2.error, MemoryError) as exc:
            self.status.setText("变换失败")
            QMessageBox.warning(self, "变换失败", str(exc) or "图片太大，内存不足。")
            return
        history.apply(result)
        self._show_result(message)

    def _undo(self):
        if self._history is not None and self._history.can_undo:
            self._history.undo()
            self._show_result("已撤销")

    def _redo(self):
        if self._history is not None and self._history.can_redo:
            self._history.redo()
            self._show_result("已重做")

    def _reset(self):
        history = self._history
        if history is not None and history.current is not history.source:
            history.apply(history.source)
            self._show_result("已恢复原图")

    def _browse_save(self):
        if self._source_path is None:
            return
        suggested = self._source_path.with_name(f"{self._source_path.stem}_transformed.png")
        dialog = QFileDialog(self, "另存变换结果", str(suggested.parent))
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setNameFilters(list(OUTPUT_FORMATS))
        dialog.selectNameFilter(next(iter(OUTPUT_FORMATS)))
        dialog.setDefaultSuffix("png")
        dialog.filterSelected.connect(
            lambda chosen: dialog.setDefaultSuffix(OUTPUT_FORMATS[chosen].lstrip("."))
        )
        dialog.selectFile(suggested.name)
        if not dialog.exec():
            return
        path = dialog.selectedFiles()[0]
        try:
            self.save_current(path)
        except ValueError as exc:
            self.status.setText("保存失败")
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.status.setText(f"已保存 {Path(path).name}")

    def save_current(self, path: str | Path):
        image = self.current_image
        if image is None:
            raise ValueError("没有可保存的图片")
        save_image(Path(path), image)
