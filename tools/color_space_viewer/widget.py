"""图像色彩空间查看器 GUI。"""

from pathlib import Path

import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
)

from tool_base import ToolBase
from tools.color_space_viewer.core import (
    COLOR_SPACES,
    available_views,
    convert_image,
    normalize_image,
    read_image,
    write_image,
)


IMAGE_FILTER = "图片文件 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"
SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


class PreviewLabel(QLabel):
    """保持宽高比显示 ndarray 的预览标签。"""

    def __init__(self, placeholder: str):
        super().__init__(placeholder)
        self._image: np.ndarray | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(
            "background-color:#202124; color:#9aa0a6; border:1px solid #3c4043; "
            "border-radius:6px;"
        )

    def set_array(self, image: np.ndarray | None, placeholder: str = "等待加载图片") -> None:
        self._image = image
        if image is None:
            self.clear()
            self.setText(placeholder)
            return
        self._refresh_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._image is not None:
            self._refresh_pixmap()

    def _refresh_pixmap(self) -> None:
        image = np.ascontiguousarray(self._image)
        if image.ndim == 2:
            height, width = image.shape
            qimage = QImage(
                image.data,
                width,
                height,
                image.strides[0],
                QImage.Format.Format_Grayscale8,
            )
        else:
            height, width, _ = image.shape
            qimage = QImage(
                image.data,
                width,
                height,
                image.strides[0],
                QImage.Format.Format_BGR888,
            )
        pixmap = QPixmap.fromImage(qimage.copy())
        self.setPixmap(
            pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class ColorSpaceViewerWidget(ToolBase):
    tool_name = "图像色彩空间查看器"
    tool_description = "预览灰度、HSV、LAB 等色彩空间及各通道，并保存当前结果"
    tool_icon = "🌈"

    def init_ui(self):
        self.resize(1160, 720)
        self.setMinimumSize(820, 560)
        self.setAcceptDrops(True)
        self._source_image: np.ndarray | None = None
        self._source_path: Path | None = None
        self.current_result: np.ndarray | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        input_group = QGroupBox("输入图片")
        input_layout = QHBoxLayout(input_group)
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("选择或拖入图片（支持 PNG / JPG / BMP / TIFF / WebP）")
        open_btn = QPushButton("打开图片…")
        open_btn.clicked.connect(self._browse_image)
        input_layout.addWidget(self.path_edit, 1)
        input_layout.addWidget(open_btn)
        root.addWidget(input_group)

        controls_group = QGroupBox("显示设置")
        controls_layout = QHBoxLayout(controls_group)
        controls_layout.addWidget(QLabel("色彩空间:"))
        self.space_combo = QComboBox()
        for key, spec in COLOR_SPACES.items():
            self.space_combo.addItem(spec.label, key)
        self.space_combo.setMinimumWidth(150)
        controls_layout.addWidget(self.space_combo)

        controls_layout.addSpacing(12)
        controls_layout.addWidget(QLabel("显示内容:"))
        self.view_combo = QComboBox()
        self.view_combo.setMinimumWidth(130)
        controls_layout.addWidget(self.view_combo)
        controls_layout.addStretch()

        self.save_btn = QPushButton("保存当前结果…")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._browse_save)
        self.save_btn.setStyleSheet(
            "QPushButton { background:#1976D2; color:white; border:none; "
            "border-radius:5px; padding:7px 16px; } "
            "QPushButton:hover { background:#1565C0; } "
            "QPushButton:disabled { background:#9e9e9e; }"
        )
        controls_layout.addWidget(self.save_btn)
        root.addWidget(controls_group)

        self.view_note_label = QLabel()
        self.view_note_label.setWordWrap(True)
        self.view_note_label.setStyleSheet("color:#666; font-size:12px;")
        root.addWidget(self.view_note_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        original_group = QGroupBox("原图")
        original_layout = QVBoxLayout(original_group)
        self.original_preview = PreviewLabel("拖入图片或点击“打开图片”")
        original_layout.addWidget(self.original_preview)

        result_group = QGroupBox("转换结果")
        result_layout = QVBoxLayout(result_group)
        self.result_preview = PreviewLabel("转换结果")
        result_layout.addWidget(self.result_preview)

        splitter.addWidget(original_group)
        splitter.addWidget(result_group)
        splitter.setSizes([560, 560])
        root.addWidget(splitter, 1)

        footer = QHBoxLayout()
        self.image_info_label = QLabel("尚未加载图片")
        self.image_info_label.setStyleSheet("color:#555; font-size:12px;")
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.status_label.setStyleSheet("color:#555; font-size:12px;")
        footer.addWidget(self.image_info_label, 1)
        footer.addWidget(self.status_label, 1)
        root.addLayout(footer)

        self._populate_views()
        self.space_combo.currentIndexChanged.connect(self._on_space_changed)
        self.view_combo.currentIndexChanged.connect(self._update_result)

        open_shortcut = QShortcut(QKeySequence.StandardKey.Open, self)
        open_shortcut.activated.connect(self._browse_image)
        save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        save_shortcut.activated.connect(self._browse_save)

    def dragEnterEvent(self, event):
        if any(Path(url.toLocalFile()).suffix.lower() in SUPPORTED_SUFFIXES for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in SUPPORTED_SUFFIXES:
                self.load_image(path)
                event.acceptProposedAction()
                return
        event.ignore()

    def _browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", IMAGE_FILTER)
        if path:
            self.load_image(path)

    def load_image(self, path: str | Path) -> None:
        try:
            source = read_image(path)
            self.set_source_image(source, path)
        except Exception as exc:
            self.status_label.setText("加载失败")
            QMessageBox.critical(self, "加载失败", str(exc))

    def set_source_image(self, image: np.ndarray, source_path: str | Path | None = None) -> None:
        normalized = normalize_image(image)
        self._source_image = normalized
        self._source_path = Path(source_path) if source_path else None
        self.path_edit.setText(str(source_path) if source_path else "（内存图片）")
        self.original_preview.set_array(normalized)

        height, width = image.shape[:2]
        channels = 1 if image.ndim == 2 else image.shape[2]
        value_min = float(np.nanmin(image))
        value_max = float(np.nanmax(image))
        value_range = f"{value_min:g}–{value_max:g}"
        self.image_info_label.setText(
            f"{width} × {height} | {channels} 通道 | {image.dtype} | 数值范围 {value_range}"
        )
        self.save_btn.setEnabled(True)
        self.status_label.setText("图片已加载")
        self._update_result()

    def _populate_views(self) -> None:
        space = self.space_combo.currentData()
        self.view_combo.blockSignals(True)
        self.view_combo.clear()
        for view in available_views(space):
            label = "三通道伪彩色" if view == "Composite" and space != "RGB" else view
            if view == "Composite" and space == "RGB":
                label = "真实颜色"
            self.view_combo.addItem(label, view)
        self.view_combo.blockSignals(False)
        self._update_note()

    def _on_space_changed(self) -> None:
        self._populate_views()
        self._update_result()

    def _update_note(self) -> None:
        space = self.space_combo.currentData()
        view = self.view_combo.currentData()
        spec = COLOR_SPACES[space]
        if view == "Composite" and space != "RGB":
            channels = " / ".join(spec.channels)
            note = f"伪彩色把 {channels} 依次映射到 R / G / B，仅用于直观看通道分布，不代表真实颜色。"
        elif space == "RGB" and view == "Composite":
            note = "按图片的真实颜色显示。选择 R、G、B 可分别查看单通道灰度图。"
        else:
            note = f"当前显示 {space} 的 {view} 单通道灰度图。"
        self.view_note_label.setText(note)

    def _update_result(self) -> None:
        self._update_note()
        if self._source_image is None:
            return
        try:
            space = self.space_combo.currentData()
            view = self.view_combo.currentData()
            self.current_result = convert_image(self._source_image, space, view)
            self.result_preview.set_array(self.current_result)
            channels = 1 if self.current_result.ndim == 2 else self.current_result.shape[2]
            self.status_label.setText(f"当前: {space} / {view}（{channels} 通道）")
        except Exception as exc:
            self.current_result = None
            self.result_preview.set_array(None, "转换失败")
            self.save_btn.setEnabled(False)
            self.status_label.setText(f"转换失败: {exc}")

    def _browse_save(self) -> None:
        if self.current_result is None:
            return
        stem = self._source_path.stem if self._source_path else "image"
        space = self.space_combo.currentData()
        view = self.view_combo.currentData()
        default_name = f"{stem}_{space}_{view}.png"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存当前结果",
            default_name,
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;BMP 图片 (*.bmp);;TIFF 图片 (*.tif *.tiff);;WebP 图片 (*.webp)",
        )
        if not path:
            return
        try:
            self.save_current(path)
            self.status_label.setText(f"已保存: {path}")
        except Exception as exc:
            self.status_label.setText("保存失败")
            QMessageBox.critical(self, "保存失败", str(exc))

    def save_current(self, path: str | Path) -> None:
        if self.current_result is None:
            raise ValueError("没有可保存的转换结果")
        write_image(path, self.current_result)
