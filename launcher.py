"""
launcher.py — 主启动器窗口。

从 registry.TOOLS 读取工具列表，渲染卡片网格（每行 3 列）。
点击卡片上的"打开"按钮，懒加载对应 widget 类并弹出独立窗口。
"""
import logging
import traceback
logger = logging.getLogger(__name__)

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea, QGridLayout, QMessageBox,
)
from PySide6.QtGui import QFont

from registry import TOOLS, load_tool_class

CARDS_PER_ROW = 3

CARD_STYLE = """
QFrame#ToolCard {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 10px;
}
QFrame#ToolCard:hover {
    border: 1px solid #1976D2;
    background-color: #f5f9ff;
}
"""

OPEN_BTN_STYLE = """
QPushButton {
    background-color: #1976D2;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 18px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #1565C0;
}
QPushButton:pressed {
    background-color: #0D47A1;
}
"""

WINDOW_STYLE = """
QMainWindow {
    background-color: #f5f5f5;
}
QWidget#central {
    background-color: #f5f5f5;
}
"""


class ToolCard(QFrame):
    def __init__(self, entry: dict, launcher: "LauncherWindow", parent=None):
        super().__init__(parent)
        self._entry = entry
        self._launcher = launcher
        self.setObjectName("ToolCard")
        self.setFixedSize(260, 220)
        self.setStyleSheet(CARD_STYLE)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 先用占位符加载元数据
        try:
            cls = load_tool_class(self._entry)
            icon = getattr(cls, "tool_icon", "🔧")
            name = getattr(cls, "tool_name", self._entry["class"])
            desc = getattr(cls, "tool_description", "")
        except Exception:
            icon = "🔧"
            name = self._entry["class"]
            desc = "（加载失败）"

        icon_label = QLabel(icon)
        icon_font = QFont()
        icon_font.setPointSize(28)
        icon_label.setFont(icon_font)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(icon_label)

        name_label = QLabel(name)
        name_font = QFont()
        name_font.setBold(True)
        name_font.setPointSize(11)
        name_label.setFont(name_font)
        name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        desc_label = QLabel(desc)
        desc_label.setStyleSheet("color: #777; font-size: 11px;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        layout.addStretch()

        open_btn = QPushButton("打开")
        open_btn.setStyleSheet(OPEN_BTN_STYLE)
        open_btn.clicked.connect(self._open)
        layout.addWidget(open_btn)

    def _open(self):
        self._launcher._open_tool(self._entry)


class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VGS 工具箱")
        self.setStyleSheet(WINDOW_STYLE)
        self._open_tools: list[QWidget] = []
        self._build()
        # 3列卡片(260) + 2间距(18) + 左右边距(30×2) + 滚动条余量
        n_cols = min(CARDS_PER_ROW, len(TOOLS))
        n_rows = (len(TOOLS) + CARDS_PER_ROW - 1) // CARDS_PER_ROW
        w = n_cols * 260 + (n_cols - 1) * 18 + 60 + 20
        h = n_rows * 220 + (n_rows - 1) * 18 + 160  # 160 = 标题区 + 边距
        self.resize(w, h)
        self.setMinimumSize(w, h)

    def _build(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(30, 24, 30, 24)
        root_layout.setSpacing(16)

        title = QLabel("VGS 工具箱")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        root_layout.addWidget(title)

        subtitle = QLabel("选择一个工具开始使用")
        subtitle.setStyleSheet("color: #888; font-size: 13px;")
        root_layout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root_layout.addWidget(scroll)

        card_container = QWidget()
        scroll.setWidget(card_container)

        grid = QGridLayout(card_container)
        grid.setSpacing(18)
        grid.setContentsMargins(0, 8, 0, 8)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        for idx, entry in enumerate(TOOLS):
            row, col = divmod(idx, CARDS_PER_ROW)
            card = ToolCard(entry, self)
            grid.addWidget(card, row, col)

    def _open_tool(self, entry: dict):
        try:
            cls = load_tool_class(entry)
            widget = cls()
            widget.setWindowFlag(Qt.WindowType.Window, True)
            widget.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            widget.destroyed.connect(lambda: self._open_tools.remove(widget) if widget in self._open_tools else None)
            self._open_tools.append(widget)
            widget.show()
            widget.raise_()
        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception("打开工具失败")
            QMessageBox.critical(self, "打开失败", f"无法加载工具:\n\n{tb}")
