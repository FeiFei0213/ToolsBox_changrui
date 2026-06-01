"""
tool_base.py — 所有工具 Widget 的抽象基类。

继承 ToolBase 并实现 init_ui() 即可接入启动器。
类属性 tool_name / tool_description / tool_icon 由 launcher 读取用于渲染卡片。
"""
from abc import abstractmethod
from PySide6.QtWidgets import QWidget


class ToolBase(QWidget):
    """工具 Widget 基类。子类必须定义三个类属性并实现 init_ui()。"""
    tool_name: str = ""
    tool_description: str = ""
    tool_icon: str = "🔧"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tool_name)
        self.init_ui()

    @abstractmethod
    def init_ui(self):
        ...
