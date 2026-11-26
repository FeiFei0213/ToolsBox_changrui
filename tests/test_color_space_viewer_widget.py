import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


class ColorSpaceViewerWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_save_is_disabled_until_an_image_is_loaded(self):
        try:
            from tools.color_space_viewer.widget import ColorSpaceViewerWidget
        except ModuleNotFoundError:
            self.fail("Color space viewer widget is missing")

        widget = ColorSpaceViewerWidget()
        self.addCleanup(widget.close)

        self.assertFalse(widget.save_btn.isEnabled())

    def test_loading_image_creates_default_rgb_result_and_enables_save(self):
        from tools.color_space_viewer.widget import ColorSpaceViewerWidget

        widget = ColorSpaceViewerWidget()
        self.addCleanup(widget.close)
        source = np.array([[[10, 20, 30], [40, 50, 60]]], dtype=np.uint8)

        widget.set_source_image(source, source_path="示例.png")

        self.assertTrue(widget.save_btn.isEnabled())
        np.testing.assert_array_equal(widget.current_result, source)
        self.assertIn("2 × 1", widget.image_info_label.text())

    def test_selecting_hsv_updates_views_and_current_result(self):
        from tools.color_space_viewer.widget import ColorSpaceViewerWidget

        widget = ColorSpaceViewerWidget()
        self.addCleanup(widget.close)
        widget.set_source_image(np.array([[[0, 0, 255]]], dtype=np.uint8))

        widget.space_combo.setCurrentIndex(widget.space_combo.findData("HSV"))

        views = [widget.view_combo.itemData(i) for i in range(widget.view_combo.count())]
        self.assertEqual(views, ["Composite", "H", "S", "V"])

        widget.view_combo.setCurrentIndex(widget.view_combo.findData("S"))
        np.testing.assert_array_equal(widget.current_result, np.array([[255]], dtype=np.uint8))

    def test_saves_the_current_single_channel_result(self):
        from tools.color_space_viewer.core import read_image
        from tools.color_space_viewer.widget import ColorSpaceViewerWidget

        widget = ColorSpaceViewerWidget()
        self.addCleanup(widget.close)
        widget.set_source_image(np.array([[[0, 0, 255]]], dtype=np.uint8))
        widget.space_combo.setCurrentIndex(widget.space_combo.findData("HSV"))
        widget.view_combo.setCurrentIndex(widget.view_combo.findData("S"))

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "饱和度.png"
            widget.save_current(path)
            saved = read_image(path)

        np.testing.assert_array_equal(saved, np.array([[255]], dtype=np.uint8))

    def test_tool_registry_exposes_color_space_viewer(self):
        from registry import TOOLS, load_tool_class

        matches = [entry for entry in TOOLS if entry["class"] == "ColorSpaceViewerWidget"]

        self.assertEqual(len(matches), 1)
        self.assertEqual(load_tool_class(matches[0]).tool_name, "图像色彩空间查看器")


if __name__ == "__main__":
    unittest.main()
