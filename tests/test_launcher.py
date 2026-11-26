import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from launcher import LauncherWindow
from registry import TOOLS


@pytest.fixture
def launcher():
    app = QApplication.instance() or QApplication([])
    window = LauncherWindow()
    window.show()
    app.processEvents()
    yield window
    window.close()


def test_home_does_not_import_tool_modules():
    result = subprocess.run(
        [sys.executable, "-c", """
import sys
from PySide6.QtWidgets import QApplication
from launcher import LauncherWindow
app = QApplication([])
window = LauncherWindow()
assert not any(name.endswith('.widget') and name.startswith('tools.') for name in sys.modules)
"""],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_category_and_keywords_filter_together(launcher):
    launcher.category_buttons["图像处理"].click()
    launcher.search_edit.setText("  MaSk  ")
    names = {
        button.accessibleName() for button in launcher.findChildren(QPushButton)
        if button.isVisible() and button.property("toolOpen")
    }
    assert names == {"打开 Mask 图像膨胀", "打开 Mask 手绘编辑器"}
    launcher.category_buttons["日志"].click()
    assert launcher.empty_label.isVisible()
    launcher.search_edit.clear()
    assert not launcher.empty_label.isVisible()


def test_search_enter_opens_a_separate_tool_window(launcher):
    launcher.search_edit.setText("hsv")
    QTest.keyClick(launcher.search_edit, Qt.Key.Key_Return)
    assert len(launcher._open_tools) == 1
    tool = launcher._open_tools[0]
    assert tool.isVisible() and tool.isWindow()
    assert tool.windowTitle() == "图像色彩空间查看器"
    tool.close()


def test_home_stays_compact_as_more_tools_are_registered(monkeypatch):
    monkeypatch.setattr("launcher.TOOLS", TOOLS * 5)
    app = QApplication.instance() or QApplication([])
    window = LauncherWindow()
    window.resize(720, 500)
    window.show()
    app.processEvents()
    assert window.height() <= 500
    assert window.scroll.verticalScrollBar().maximum() > 0
    window.close()
