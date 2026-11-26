"""生产工具箱的分类与搜索主页。"""

import logging

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from registry import CATEGORIES, TOOLS, load_tool_class

logger = logging.getLogger(__name__)

HOME_STYLE = """
QWidget#ToolHome { background: #f2f5f9; color: #17263a; }
QFrame#Navigation, QFrame#ToolCard {
    background: #ffffff; border: 1px solid #d9e2ed; border-radius: 10px;
}
QLabel#HomeTitle { font-size: 26px; font-weight: bold; color: #17263a; }
QLabel#SectionTitle { font-size: 16px; font-weight: bold; color: #17263a; }
QLabel#ToolName { font-size: 14px; font-weight: bold; color: #17263a; }
QLabel[muted="true"] { color: #4d6078; }
QLabel#ToolIcon {
    background: #edf3fb; color: #17263a; border-radius: 8px; font-size: 20px;
}
QLineEdit#ToolSearch {
    background: white; color: #17263a; border: 1px solid #b9c8db;
    border-radius: 8px; padding: 8px 12px;
}
QLineEdit#ToolSearch:focus { border: 1px solid #2365b2; }
QPushButton[category="true"] {
    text-align: left; padding: 9px 10px; border-radius: 6px;
    border: 1px solid transparent; background: transparent; color: #31465e;
}
QPushButton[category="true"]:hover { background: #f1f5fb; }
QPushButton[category="true"]:checked { background: #e7f0ff; color: #164e93; font-weight: bold; }
QPushButton[category="true"]:focus { border-color: #2365b2; }
QPushButton[toolOpen="true"] {
    background: #eaf2fd; color: #164e93; font-weight: bold;
    border: 1px solid transparent; border-radius: 6px; padding: 6px 14px;
}
QPushButton[toolOpen="true"]:hover { background: #dceaff; }
QPushButton[toolOpen="true"]:focus { border-color: #2365b2; }
"""


def muted_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setProperty("muted", True)
    return label


class ToolCard(QFrame):
    def __init__(self, entry: dict[str, str], launcher: "LauncherWindow"):
        super().__init__()
        self.entry = entry
        self.setObjectName("ToolCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        icon = QLabel(entry["icon"])
        icon.setObjectName("ToolIcon")
        icon.setFixedSize(38, 38)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel(entry["name"])
        title.setObjectName("ToolName")
        title.setWordWrap(True)
        description = muted_label(entry["description"])
        description.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(description)
        layout.addLayout(copy, 1)

        button = QPushButton("打开")
        button.setProperty("toolOpen", True)
        button.setAccessibleName(f'打开 {entry["name"]}')
        button.clicked.connect(lambda: launcher._open_tool(entry))
        layout.addWidget(button)

    def matches(self, category: str, words: list[str]) -> bool:
        if category != "全部工具" and self.entry["category"] != category:
            return False
        searchable = " ".join(self.entry[key] for key in (
            "name", "description", "category", "keywords",
        )).casefold()
        return all(word in searchable for word in words)


class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("生产工具箱")
        self.setMinimumSize(620, 390)
        self.resize(QSize(960, 660).boundedTo(self.screen().availableGeometry().size() - QSize(32, 64)))
        self._open_tools: list[QWidget] = []
        self._filtered_cards: list[ToolCard] = []
        self._build()
        self._build_menu()
        find = QShortcut(QKeySequence.StandardKey.Find, self)
        find.activated.connect(self._focus_search)

    def _build(self):
        central = QWidget()
        central.setObjectName("ToolHome")
        central.setStyleSheet(HOME_STYLE)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        heading = QHBoxLayout()
        title = QLabel("生产工具箱")
        title.setObjectName("HomeTitle")
        heading.addWidget(title)
        heading.addStretch(1)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("ToolSearch")
        self.search_edit.setAccessibleName("搜索工具")
        self.search_edit.setPlaceholderText("搜索工具、功能或关键词")
        self.search_edit.setToolTip("Ctrl+F 搜索，只有一项结果时按 Enter 打开")
        self.search_edit.setClearButtonEnabled(True)
        heading.addWidget(self.search_edit, 2)
        root.addLayout(heading)

        body = QHBoxLayout()
        body.setSpacing(16)
        root.addLayout(body, 1)
        nav = QFrame()
        nav.setObjectName("Navigation")
        nav.setFixedWidth(138)
        navigation = QVBoxLayout(nav)
        navigation.setContentsMargins(8, 10, 8, 10)
        navigation.setSpacing(3)
        self._category_group = QButtonGroup(self)
        self.category_buttons: dict[str, QPushButton] = {}
        for category in ("全部工具", *CATEGORIES):
            button = QPushButton(category)
            button.setProperty("category", True)
            button.setCheckable(True)
            self._category_group.addButton(button)
            self.category_buttons[category] = button
            navigation.addWidget(button)
        self.category_buttons["全部工具"].setChecked(True)
        navigation.addStretch()
        body.addWidget(nav)

        results = QVBoxLayout()
        results.setSpacing(8)
        result_heading = QHBoxLayout()
        self.section_title = QLabel()
        self.section_title.setObjectName("SectionTitle")
        self.result_count = muted_label()
        result_heading.addWidget(self.section_title)
        result_heading.addStretch()
        result_heading.addWidget(self.result_count)
        results.addLayout(result_heading)
        body.addLayout(results, 1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        container.setStyleSheet("QWidget#ToolResults { background: #f2f5f9; }")
        container.setObjectName("ToolResults")
        self.scroll.setWidget(container)
        results.addWidget(self.scroll, 1)

        cards = QVBoxLayout(container)
        cards.setContentsMargins(0, 0, 3, 0)
        cards.setSpacing(7)
        self._cards = [ToolCard(entry, self) for entry in TOOLS]
        for card in self._cards:
            cards.addWidget(card)
        self.empty_label = muted_label("没有匹配的工具，试试其他关键词或分类。")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setMinimumHeight(76)
        cards.addWidget(self.empty_label)
        cards.addStretch()

        self._category_group.buttonClicked.connect(self._apply_filter)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.search_edit.returnPressed.connect(self._open_search_result)
        self._apply_filter()

    def _focus_search(self):
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _apply_filter(self):
        category = self._category_group.checkedButton().text()
        words = self.search_edit.text().casefold().split()
        self._filtered_cards = []
        for card in self._cards:
            matches = card.matches(category, words)
            card.setVisible(matches)
            if matches:
                self._filtered_cards.append(card)
        self.section_title.setText(category)
        self.result_count.setText(f"{len(self._filtered_cards)} 个工具")
        self.empty_label.setVisible(not self._filtered_cards)
        self.scroll.verticalScrollBar().setValue(0)

    def _open_search_result(self):
        if len(self._filtered_cards) == 1:
            self._open_tool(self._filtered_cards[0].entry)

    def _build_menu(self):
        help_menu = self.menuBar().addMenu("帮助")
        about = QAction("关于", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    def _show_about(self):
        from build_info import __commit__, __version__

        versions = []
        for name, module in (("PySide6", "PySide6"), ("OpenCV", "cv2"), ("NumPy", "numpy")):
            try:
                version = __import__(module).__version__
            except Exception:
                version = "未知"
            versions.append(f"{name}: {version}")

        QMessageBox.about(
            self, "关于生产工具箱",
            f"<b>生产工具箱</b> v{__version__}<br>构建: {__commit__}<br><br>"
            + "<br>".join(versions),
        )

    def _open_tool(self, entry: dict[str, str]):
        try:
            widget = load_tool_class(entry)()
            widget.setWindowFlag(Qt.WindowType.Window, True)
            widget.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            widget.destroyed.connect(lambda: self._open_tools.remove(widget))
            self._open_tools.append(widget)
            widget.show()
            widget.raise_()
        except Exception as exc:
            logger.exception("打开工具失败: %s", entry["name"])
            QMessageBox.critical(self, "打开失败", f'无法打开 {entry["name"]}。\n\n{exc}')
