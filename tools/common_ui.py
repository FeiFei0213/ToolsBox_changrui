#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
logger = logging.getLogger(__name__)

"""
公共UI组件
用于 plt_viewer 和 calibration_point_editor 的共享UI组件
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPainter, QColor
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QToolButton,
    QLabel,
    QDockWidget,
    QMainWindow,
    QToolBar,
)


class VerticalTextButton(QPushButton):
    """垂直文字按钮"""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        self.setStyleSheet("""
            QPushButton {
                border: 1px solid #555;
                border-radius: 3px;
                background-color: #2b2b2b;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))

        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(90)
        painter.translate(-self.height() / 2, -self.width() / 2)

        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(self.text)
        text_height = metrics.height()
        x = (self.height() - text_width) / 2
        y = (self.width() + text_height) / 2 - metrics.descent()

        painter.drawText(int(x), int(y), self.text)


class CollapsibleDockTitleBar(QWidget):
    """可折叠的Dock标题栏"""

    def __init__(self, dock_widget, parent=None):
        super().__init__(parent)
        self.dock_widget = dock_widget
        self.is_collapsed = False
        self.saved_width = None

        self.expanded_layout = QHBoxLayout()
        self.expanded_layout.setContentsMargins(5, 2, 2, 2)
        self.expanded_layout.setSpacing(5)

        self.title_label = QLabel(dock_widget.windowTitle())
        self.expanded_layout.addWidget(self.title_label)
        self.expanded_layout.addStretch()

        self.toggle_button = QToolButton()
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_button.setFixedSize(20, 20)
        self.toggle_button.setToolTip("折叠/展开")
        self.toggle_button.clicked.connect(self.toggle_collapse)
        self.expanded_layout.addWidget(self.toggle_button)

        self.collapsed_layout = QVBoxLayout()
        self.collapsed_layout.setContentsMargins(2, 5, 2, 5)
        self.collapsed_layout.setSpacing(0)

        self.vertical_button = VerticalTextButton(dock_widget.windowTitle())
        self.vertical_button.setFixedSize(25, 80)
        self.vertical_button.setToolTip(f"展开{dock_widget.windowTitle()}")
        self.vertical_button.clicked.connect(self.toggle_collapse)
        self.collapsed_layout.addWidget(self.vertical_button)
        self.collapsed_layout.addStretch()

        self.expanded_container = QWidget()
        self.expanded_container.setLayout(self.expanded_layout)

        self.collapsed_container = QWidget()
        self.collapsed_container.setLayout(self.collapsed_layout)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.main_layout.addWidget(self.expanded_container)
        self.main_layout.addWidget(self.collapsed_container)

        self.current_layout = self.expanded_layout
        self._update_layout_visibility()

        dock_widget.visibilityChanged.connect(self.on_visibility_changed)

    def toggle_collapse(self):
        if self.is_collapsed:
            self.dock_widget.setMinimumWidth(200)
            self.dock_widget.setMaximumWidth(16777215)
            if self.saved_width is not None and self.saved_width >= 200:
                self.dock_widget.resize(self.saved_width, self.dock_widget.height())
            else:
                self.dock_widget.resize(200, self.dock_widget.height())
            self.dock_widget.widget().show()
            self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
            self.is_collapsed = False
            self._switch_layout(self.expanded_layout)
            QTimer.singleShot(10, lambda: self._ensure_dock_position())
        else:
            if self.saved_width is None:
                current_width = self.dock_widget.width()
                if current_width >= 200:
                    self.saved_width = current_width
            self.dock_widget.widget().hide()
            self.dock_widget.setFixedWidth(30)
            self.toggle_button.setArrowType(Qt.ArrowType.LeftArrow)
            self.is_collapsed = True
            self._switch_layout(self.collapsed_layout)

    def _switch_layout(self, new_layout):
        if self.current_layout == new_layout:
            return
        self.current_layout = new_layout
        self._update_layout_visibility()

    def _update_layout_visibility(self):
        if self.current_layout == self.expanded_layout:
            self.expanded_container.show()
            self.collapsed_container.hide()
        else:
            self.collapsed_container.show()
            self.expanded_container.hide()

    def _ensure_dock_position(self):
        if not self.is_collapsed:
            main_window = self.dock_widget.parent()
            if main_window and isinstance(main_window, QMainWindow):
                toolbar_height = 0
                for toolbar in main_window.findChildren(QToolBar):
                    if toolbar.isVisible():
                        toolbar_height = max(toolbar_height, toolbar.height())

                dock_geometry = self.dock_widget.geometry()
                if dock_geometry.y() < toolbar_height:
                    new_y = toolbar_height
                    self.dock_widget.move(self.dock_widget.x(), new_y)
                    window_height = main_window.height()
                    statusbar_height = main_window.statusBar().height() if main_window.statusBar() else 0
                    max_height = window_height - new_y - statusbar_height
                    if dock_geometry.height() > max_height:
                        self.dock_widget.resize(dock_geometry.width(), max_height)

            self.dock_widget.raise_()
            self.dock_widget.show()

    def on_visibility_changed(self, visible):
        if not visible:
            self.is_collapsed = False
            self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
            self._switch_layout(self.expanded_layout)


# 别名，保持兼容
VerticalCollapsibleDockTitleBar = CollapsibleDockTitleBar
