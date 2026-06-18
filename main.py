"""
main.py — 程序入口。

运行方式：
    conda activate toolbox
    python main.py
"""
import sys
import logging
import os
import tempfile
from pathlib import Path

from build_info import __commit__, __version__

# 确保项目根目录在 sys.path 中，以便各 tool 模块可以 import tool_base
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication
from launcher import LauncherWindow


def _configure_logging() -> Path | None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_path = None
    candidates = [
        Path(os.environ["LOCALAPPDATA"]) / "ToolsBox"
        if os.environ.get("LOCALAPPDATA")
        else None,
        Path.home() / ".toolbox",
        Path(tempfile.gettempdir()) / "ToolsBox",
    ]

    for log_dir in candidates:
        if log_dir is None:
            continue
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "toolbox.log"
            handlers.insert(0, logging.FileHandler(log_path, encoding="utf-8"))
            break
        except OSError:
            continue

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    return log_path


LOG_PATH = _configure_logging()


def run_smoke_test() -> int:
    """Validate imports and packaged resources without opening the GUI."""
    from registry import TOOLS, load_tool_class
    from tools.vgs_context import packaged_resource_path

    for entry in TOOLS:
        load_tool_class(entry)

    required_resources = [
        packaged_resource_path(
            "tools",
            "pixel_starfire",
            "config",
            "device",
            "M7",
            "0",
            "fit_params.json",
        ),
        packaged_resource_path("icon", "icon.ico"),
    ]
    missing = [str(path) for path in required_resources if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing packaged resources: {missing}")

    logging.info(
        "Smoke test passed: version=%s commit=%s tools=%d",
        __version__,
        __commit__,
        len(TOOLS),
    )
    return 0


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if "--smoke-test" in sys.argv:
        try:
            return run_smoke_test()
        except Exception:
            logging.exception("Smoke test failed")
            return 1

    window = LauncherWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
