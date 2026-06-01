"""
widget.py — Mask 图像膨胀工具 GUI。

MaskDilateWidget 继承 ToolBase，提供完整的参数配置界面：
- 输入/输出路径（支持拖拽）
- Kernel 大小、迭代次数、膨胀目标、颜色翻转选项
- ROI 区域 / 排除区域（文本框，每行 x1,y1,x2,y2）
- 执行后展示原图 vs 结果的左右对比预览
"""
import logging
from pathlib import Path

import cv2
import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QComboBox,
    QCheckBox, QPlainTextEdit, QGroupBox, QSplitter,
    QFileDialog, QMessageBox, QSizePolicy,
)

from tool_base import ToolBase
from tools.mask_dilate.core import invert_black_white_and_dilate

logger = logging.getLogger(__name__)

PREVIEW_MAX_HEIGHT = 320


class MaskDilateWidget(ToolBase):
    tool_name = "Mask 图像膨胀"
    tool_description = "对灰度图执行形态学膨胀，支持 ROI 区域指定"
    tool_icon = "🔲"

    def init_ui(self):
        self.resize(900, 700)
        self._original_img: np.ndarray | None = None
        self._result_img: np.ndarray | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # ── 输入/输出 ──────────────────────────────────
        io_group = QGroupBox("输入 / 输出")
        io_form = QFormLayout(io_group)
        io_form.setSpacing(8)

        input_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("选择或拖入灰度图片路径")
        self.input_edit.setReadOnly(True)
        self.input_edit.setAcceptDrops(True)
        browse_in_btn = QPushButton("浏览...")
        browse_in_btn.setFixedWidth(70)
        browse_in_btn.clicked.connect(self._browse_input)
        input_row.addWidget(self.input_edit)
        input_row.addWidget(browse_in_btn)
        io_form.addRow("输入图片:", input_row)

        output_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("留空则不保存，或选择输出路径")
        browse_out_btn = QPushButton("浏览...")
        browse_out_btn.setFixedWidth(70)
        browse_out_btn.clicked.connect(self._browse_output)
        output_row.addWidget(self.output_edit)
        output_row.addWidget(browse_out_btn)
        io_form.addRow("输出路径:", output_row)

        root.addWidget(io_group)

        # ── 膨胀参数 ────────────────────────────────────
        param_group = QGroupBox("膨胀参数")
        param_form = QFormLayout(param_group)
        param_form.setSpacing(8)

        kernel_row = QHBoxLayout()
        kernel_row.addWidget(QLabel("W:"))
        self.kernel_w = QSpinBox()
        self.kernel_w.setRange(1, 99)
        self.kernel_w.setSingleStep(2)
        self.kernel_w.setValue(3)
        kernel_row.addWidget(self.kernel_w)
        kernel_row.addSpacing(12)
        kernel_row.addWidget(QLabel("H:"))
        self.kernel_h = QSpinBox()
        self.kernel_h.setRange(1, 99)
        self.kernel_h.setSingleStep(2)
        self.kernel_h.setValue(3)
        kernel_row.addWidget(self.kernel_h)
        kernel_row.addStretch()
        param_form.addRow("Kernel 大小:", kernel_row)

        self.iter_spin = QSpinBox()
        self.iter_spin.setRange(1, 100)
        self.iter_spin.setValue(1)
        param_form.addRow("迭代次数:", self.iter_spin)

        self.target_combo = QComboBox()
        self.target_combo.addItem("膨胀白色区域", True)
        self.target_combo.addItem("膨胀黑色区域", False)
        param_form.addRow("膨胀目标:", self.target_combo)

        invert_row = QHBoxLayout()
        self.invert_before_cb = QCheckBox("膨胀前颜色翻转")
        self.invert_after_cb = QCheckBox("膨胀后颜色翻转")
        invert_row.addWidget(self.invert_before_cb)
        invert_row.addWidget(self.invert_after_cb)
        invert_row.addStretch()
        param_form.addRow("翻转选项:", invert_row)

        self.roi_edit = QPlainTextEdit()
        self.roi_edit.setFixedHeight(72)
        self.roi_edit.setPlaceholderText("每行一个 ROI: x1,y1,x2,y2\n留空表示整张图")
        param_form.addRow("ROI 区域:", self.roi_edit)

        self.exclude_edit = QPlainTextEdit()
        self.exclude_edit.setFixedHeight(72)
        self.exclude_edit.setPlaceholderText("每行一个排除区域: x1,y1,x2,y2\n留空表示不排除")
        param_form.addRow("排除区域:", self.exclude_edit)

        root.addWidget(param_group)

        # ── 执行按钮 ────────────────────────────────────
        run_btn = QPushButton("执行膨胀")
        run_btn.setFixedHeight(36)
        run_btn.setStyleSheet("""
            QPushButton {
                background-color: #1976D2; color: white;
                border: none; border-radius: 6px; font-size: 14px;
            }
            QPushButton:hover { background-color: #1565C0; }
            QPushButton:pressed { background-color: #0D47A1; }
        """)
        run_btn.clicked.connect(self._run)
        root.addWidget(run_btn)

        # ── 状态标签 ────────────────────────────────────
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #555; font-size: 12px;")
        root.addWidget(self.status_label)

        # ── 预览区 ──────────────────────────────────────
        preview_group = QGroupBox("预览（原图 vs 结果）")
        preview_layout = QHBoxLayout(preview_group)
        preview_layout.setSpacing(10)

        self.orig_label = QLabel("原图")
        self.orig_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.orig_label.setStyleSheet("background:#2a2a2a; color:#888; border-radius:4px;")
        self.orig_label.setMinimumSize(200, 160)
        self.orig_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.result_label = QLabel("结果")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_label.setStyleSheet("background:#2a2a2a; color:#888; border-radius:4px;")
        self.result_label.setMinimumSize(200, 160)
        self.result_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        preview_layout.addWidget(self.orig_label)
        preview_layout.addWidget(self.result_label)
        root.addWidget(preview_group, 1)

        # 拖拽支持
        self.setAcceptDrops(True)

    # ── 拖拽 ──────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        for url in urls:
            path = url.toLocalFile()
            if path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif")):
                self.input_edit.setText(path)
                out = str(Path(path).with_stem(Path(path).stem + "_dilated"))
                self.output_edit.setText(out)
                self._load_preview_original(path)
                break

    # ── 文件选择 ───────────────────────────────────────────
    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择灰度图片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.tiff *.tif)"
        )
        if not path:
            return
        self.input_edit.setText(path)
        out = str(Path(path).with_stem(Path(path).stem + "_dilated"))
        self.output_edit.setText(out)
        self._load_preview_original(path)

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存输出图片", self.output_edit.text() or "output.png",
            "图片文件 (*.png *.jpg *.bmp)"
        )
        if path:
            self.output_edit.setText(path)

    # ── ROI 解析 ───────────────────────────────────────────
    def _parse_roi_text(self, text: str) -> list[tuple] | None:
        result = []
        for line_no, line in enumerate(text.strip().splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) != 4:
                QMessageBox.warning(self, "格式错误", f"第 {line_no} 行不是 x1,y1,x2,y2 格式:\n{line}")
                return None
            try:
                result.append(tuple(int(p) for p in parts))
            except ValueError:
                QMessageBox.warning(self, "格式错误", f"第 {line_no} 行包含非整数:\n{line}")
                return None
        return result if result else None

    # ── 预览辅助 ───────────────────────────────────────────
    def _ndarray_to_pixmap(self, img: np.ndarray) -> QPixmap:
        if len(img.shape) == 2:
            h, w = img.shape
            qimg = QImage(img.data, w, h, w, QImage.Format.Format_Grayscale8)
        else:
            h, w, ch = img.shape
            qimg = QImage(img.data, w, h, ch * w, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimg)

    def _show_in_label(self, label: QLabel, img: np.ndarray):
        pm = self._ndarray_to_pixmap(img)
        label.setPixmap(
            pm.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)
        )

    def _load_preview_original(self, path: str):
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            self._original_img = img
            self._show_in_label(self.orig_label, img)
            self.result_label.setText("结果")
            self.result_label.setPixmap(QPixmap())
            self._result_img = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._original_img is not None:
            self._show_in_label(self.orig_label, self._original_img)
        if self._result_img is not None:
            self._show_in_label(self.result_label, self._result_img)

    # ── 执行膨胀 ───────────────────────────────────────────
    def _run(self):
        input_path = self.input_edit.text().strip()
        if not input_path:
            QMessageBox.warning(self, "未选择图片", "请先选择输入图片")
            return

        roi = self._parse_roi_text(self.roi_edit.toPlainText())
        if roi is None and self.roi_edit.toPlainText().strip():
            return  # 解析失败，错误已弹出
        exclude_roi = self._parse_roi_text(self.exclude_edit.toPlainText())
        if exclude_roi is None and self.exclude_edit.toPlainText().strip():
            return

        output_path = self.output_edit.text().strip() or None

        self.status_label.setText("处理中...")
        self.status_label.repaint()

        try:
            result = invert_black_white_and_dilate(
                image_path=input_path,
                output_path=output_path,
                kernel_size=(self.kernel_w.value(), self.kernel_h.value()),
                dilate_iterations=self.iter_spin.value(),
                dilate_white=self.target_combo.currentData(),
                invert_before=self.invert_before_cb.isChecked(),
                invert_after=self.invert_after_cb.isChecked(),
                roi=roi,
                exclude_roi=exclude_roi,
            )
        except Exception as exc:
            self.status_label.setText(f"失败: {exc}")
            QMessageBox.critical(self, "执行失败", str(exc))
            return

        self._result_img = result
        self._show_in_label(self.result_label, result)

        msg = "完成"
        if output_path:
            msg += f"，已保存到: {output_path}"
        self.status_label.setText(msg)
