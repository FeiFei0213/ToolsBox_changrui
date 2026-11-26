import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


class MaskPainterWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_export_and_mask_controls_require_an_original_image(self):
        try:
            from tools.mask_painter.widget import MaskPainterWidget
        except ModuleNotFoundError:
            self.fail("Mask painter widget is missing")

        widget = MaskPainterWidget()
        self.addCleanup(widget.close)

        self.assertFalse(widget.load_mask_btn.isEnabled())
        self.assertFalse(widget.export_mask_btn.isEnabled())
        self.assertFalse(widget.export_result_btn.isEnabled())

    def test_tool_registry_exposes_mask_painter(self):
        from registry import TOOLS, load_tool_class

        matches = [entry for entry in TOOLS if entry["class"] == "MaskPainterWidget"]

        self.assertEqual(len(matches), 1)
        self.assertEqual(load_tool_class(matches[0]).tool_name, "Mask 手绘编辑器")

    def test_setting_original_creates_white_mask_and_enables_mask_actions(self):
        from tools.mask_painter.widget import MaskPainterWidget

        widget = MaskPainterWidget()
        self.addCleanup(widget.close)
        original = np.zeros((2, 3, 3), dtype=np.uint8)

        self.assertTrue(
            hasattr(widget, "set_original_image"),
            "set_original_image is missing",
        )
        widget.set_original_image(original, source_path="example.png")

        self.assertTrue(widget.load_mask_btn.isEnabled())
        self.assertTrue(widget.export_mask_btn.isEnabled())
        self.assertTrue(widget.export_result_btn.isEnabled())
        np.testing.assert_array_equal(
            widget.canvas.mask,
            np.full((2, 3), 255, dtype=np.uint8),
        )

    def test_setting_existing_mask_normalizes_it_before_editing(self):
        from tools.mask_painter.widget import MaskPainterWidget

        widget = MaskPainterWidget()
        self.addCleanup(widget.close)
        widget.set_original_image(np.zeros((1, 2, 3), dtype=np.uint8))
        source_mask = np.array([[[0, 0, 0], [200, 200, 200]]], dtype=np.uint8)

        self.assertTrue(hasattr(widget, "set_mask_image"), "set_mask_image is missing")
        widget.set_mask_image(source_mask)

        np.testing.assert_array_equal(
            widget.canvas.mask,
            np.array([[0, 255]], dtype=np.uint8),
        )

    def test_default_export_keeps_black_mask_region_and_fills_rest_white(self):
        from tools.mask_painter.widget import MaskPainterWidget

        widget = MaskPainterWidget()
        self.addCleanup(widget.close)
        original = np.array([[[10, 20, 30], [40, 50, 60]]], dtype=np.uint8)
        widget.set_original_image(original)
        widget.set_mask_image(np.array([[0, 255]], dtype=np.uint8))

        self.assertTrue(
            hasattr(widget, "build_masked_result"),
            "build_masked_result is missing",
        )
        result = widget.build_masked_result()

        np.testing.assert_array_equal(
            result,
            np.array([[[10, 20, 30], [255, 255, 255]]], dtype=np.uint8),
        )

    def test_save_mask_writes_current_binary_mask(self):
        from tools.mask_painter.core import read_image
        from tools.mask_painter.widget import MaskPainterWidget

        widget = MaskPainterWidget()
        self.addCleanup(widget.close)
        widget.set_original_image(np.zeros((1, 2, 3), dtype=np.uint8))
        widget.set_mask_image(np.array([[0, 255]], dtype=np.uint8))

        self.assertTrue(hasattr(widget, "save_mask"), "save_mask is missing")
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "手绘_mask.png"
            widget.save_mask(path)
            saved = read_image(path)

        np.testing.assert_array_equal(saved, np.array([[0, 255]], dtype=np.uint8))

    def test_save_masked_result_writes_selected_original_region(self):
        from tools.mask_painter.core import read_image
        from tools.mask_painter.widget import MaskPainterWidget

        widget = MaskPainterWidget()
        self.addCleanup(widget.close)
        original = np.array([[[10, 20, 30], [40, 50, 60]]], dtype=np.uint8)
        widget.set_original_image(original)
        widget.set_mask_image(np.array([[0, 255]], dtype=np.uint8))

        self.assertTrue(
            hasattr(widget, "save_masked_result"),
            "save_masked_result is missing",
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "覆盖原图.png"
            widget.save_masked_result(path)
            saved = read_image(path)

        np.testing.assert_array_equal(
            saved,
            np.array([[[10, 20, 30], [255, 255, 255]]], dtype=np.uint8),
        )


class MaskCanvasHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_completed_stroke_can_be_undone_and_redone(self):
        from tools.mask_painter.widget import MaskCanvas

        canvas = MaskCanvas()
        self.addCleanup(canvas.close)
        canvas.set_images(
            np.zeros((3, 3, 3), dtype=np.uint8),
            np.full((3, 3), 255, dtype=np.uint8),
        )
        canvas.brush_color = 0
        canvas.brush_width = 1

        self.assertTrue(hasattr(canvas, "begin_stroke"), "begin_stroke is missing")
        canvas.begin_stroke((1, 1))
        canvas.end_stroke()
        self.assertEqual(int(canvas.mask[1, 1]), 0)

        canvas.undo()
        self.assertEqual(int(canvas.mask[1, 1]), 255)

        canvas.redo()
        self.assertEqual(int(canvas.mask[1, 1]), 0)

    def test_invert_mask_can_be_undone(self):
        from tools.mask_painter.widget import MaskCanvas

        canvas = MaskCanvas()
        self.addCleanup(canvas.close)
        canvas.set_images(
            np.zeros((1, 2, 3), dtype=np.uint8),
            np.array([[0, 255]], dtype=np.uint8),
        )

        self.assertTrue(hasattr(canvas, "invert_mask"), "invert_mask is missing")
        canvas.invert_mask()
        np.testing.assert_array_equal(canvas.mask, np.array([[255, 0]], dtype=np.uint8))

        canvas.undo()
        np.testing.assert_array_equal(canvas.mask, np.array([[0, 255]], dtype=np.uint8))

    def test_fill_mask_replaces_all_pixels_and_can_be_undone(self):
        from tools.mask_painter.widget import MaskCanvas

        canvas = MaskCanvas()
        self.addCleanup(canvas.close)
        canvas.set_images(
            np.zeros((1, 2, 3), dtype=np.uint8),
            np.array([[0, 255]], dtype=np.uint8),
        )

        self.assertTrue(hasattr(canvas, "fill_mask"), "fill_mask is missing")
        canvas.fill_mask(0)
        np.testing.assert_array_equal(canvas.mask, np.array([[0, 0]], dtype=np.uint8))

        canvas.undo()
        np.testing.assert_array_equal(canvas.mask, np.array([[0, 255]], dtype=np.uint8))


if __name__ == "__main__":
    unittest.main()
