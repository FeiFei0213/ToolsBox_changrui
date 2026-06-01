"""
widget.py — X-anylabeling JSON 点坐标提取工具 GUI。

ExtraJsonWidget 继承 ToolBase，功能包括：
- 打开 JSON 文件 / 拖拽 JSON 文件到窗口
- 提取所有 shapes 中的点坐标，格式为 [x, y],
- 复制结果到剪贴板
"""
import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QFileDialog,
    QMessageBox,
    QStatusBar,
)

from tool_base import ToolBase
from tools.extra_json.core import extract_points_from_json

logger = logging.getLogger(__name__)


class ExtraJsonWidget(ToolBase):
    tool_name = "JSON 点坐标提取"
    tool_description = "从 X-anylabeling 标注 JSON 提取所有点坐标"
    tool_icon = "📍"

    def init_ui(self):
        self.resize(700, 520)
        self._current_path: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # 文件选择行
        file_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择或拖入 X-anylabeling JSON 文件")
        self.path_edit.setReadOnly(True)
        browse_btn = QPushButton("浏览...")
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._browse)
        file_row.addWidget(self.path_edit)
        file_row.addWidget(browse_btn)
        root.addLayout(file_row)

        # 提取按钮
        extract_btn = QPushButton("提取坐标")
        extract_btn.setFixedHeight(36)
        extract_btn.setStyleSheet("""
            QPushButton {
                background-color: #1976D2; color: white;
                border: none; border-radius: 6px; font-size: 14px;
            }
            QPushButton:hover { background-color: #1565C0; }
            QPushButton:pressed { background-color: #0D47A1; }
        """)
        extract_btn.clicked.connect(self._extract)
        root.addWidget(extract_btn)

        # 结果区
        result_header = QHBoxLayout()
        result_header.addWidget(QLabel("提取结果（格式：[x, y],）："))
        result_header.addStretch()
        copy_btn = QPushButton("复制")
        copy_btn.setFixedWidth(60)
        copy_btn.clicked.connect(self._copy)
        result_header.addWidget(copy_btn)
        clear_btn = QPushButton("清空")
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self._clear)
        result_header.addWidget(clear_btn)
        root.addLayout(result_header)

        self.result_edit = QPlainTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setPlaceholderText("提取后结果显示在这里…")
        root.addWidget(self.result_edit, 1)

        self.status = QStatusBar()
        root.addWidget(self.status)
        self.status.showMessage("就绪")

        self.setAcceptDrops(True)

    # ── 拖拽 ──────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".json"):
                self._load(path)
                break

    # ── 操作 ──────────────────────────────────────────────
    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 JSON 文件", "", "JSON 文件 (*.json)"
        )
        if path:
            self._load(path)

    def _load(self, path: str):
        self._current_path = Path(path)
        self.path_edit.setText(path)
        self.status.showMessage(f"已选择: {path}")
        self._extract()

    def _extract(self):
        if not self._current_path or not self._current_path.exists():
            QMessageBox.warning(self, "未选择文件", "请先选择 JSON 文件")
            return

        try:
            points, text = extract_points_from_json(str(self._current_path))
        except Exception as exc:
            QMessageBox.critical(self, "提取失败", str(exc))
            self.status.showMessage(f"提取失败: {exc}")
            return

        self.result_edit.setPlainText(text)
        self.status.showMessage(f"提取完成，共 {len(points)} 个点")

    def _copy(self):
        text = self.result_edit.toPlainText()
        if not text:
            self.status.showMessage("没有内容可复制")
            return
        QGuiApplication.clipboard().setText(text)
        self.status.showMessage("已复制到剪贴板")

    def _clear(self):
        self._current_path = None
        self.path_edit.clear()
        self.result_edit.clear()
        self.status.showMessage("已清空")
