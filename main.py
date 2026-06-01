"""
main.py — 程序入口。

运行方式：
    conda activate toolbox
    python main.py
"""
import sys
import logging
from pathlib import Path

# 确保项目根目录在 sys.path 中，以便各 tool 模块可以 import tool_base
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication
from launcher import LauncherWindow

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
