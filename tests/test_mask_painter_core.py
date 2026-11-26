import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np


class CreateBlankMaskTests(unittest.TestCase):
    def test_creates_white_mask_with_requested_dimensions(self):
        try:
            from tools.mask_painter.core import create_blank_mask
        except ModuleNotFoundError:
            self.fail("Mask painter core module is missing")

        result = create_blank_mask(width=3, height=2, color=255)

        np.testing.assert_array_equal(
            result,
            np.array([[255, 255, 255], [255, 255, 255]], dtype=np.uint8),
        )


class NormalizeMaskTests(unittest.TestCase):
    def test_thresholds_grayscale_mask_to_strict_black_and_white(self):
        try:
            from tools.mask_painter.core import normalize_mask
        except ImportError:
            self.fail("normalize_mask is missing")

        source = np.array([[0, 127, 128, 255]], dtype=np.uint8)

        result = normalize_mask(source)

        np.testing.assert_array_equal(
            result,
            np.array([[0, 0, 255, 255]], dtype=np.uint8),
        )

    def test_converts_color_mask_to_single_channel_binary_mask(self):
        from tools.mask_painter.core import normalize_mask

        source = np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8)

        result = normalize_mask(source)

        np.testing.assert_array_equal(
            result,
            np.array([[0, 255]], dtype=np.uint8),
        )


class ApplyMaskTests(unittest.TestCase):
    def test_keeps_original_pixels_where_mask_is_black_and_fills_rest_white(self):
        try:
            from tools.mask_painter.core import apply_mask_to_image
        except ImportError:
            self.fail("apply_mask_to_image is missing")

        original = np.array(
            [[[10, 20, 30], [40, 50, 60]], [[70, 80, 90], [100, 110, 120]]],
            dtype=np.uint8,
        )
        mask = np.array([[0, 255], [255, 0]], dtype=np.uint8)

        result = apply_mask_to_image(original, mask, keep_value=0, fill_value=255)

        np.testing.assert_array_equal(
            result,
            np.array(
                [
                    [[10, 20, 30], [255, 255, 255]],
                    [[255, 255, 255], [100, 110, 120]],
                ],
                dtype=np.uint8,
            ),
        )

    def test_rejects_mask_with_different_dimensions_from_original(self):
        from tools.mask_painter.core import apply_mask_to_image

        original = np.zeros((2, 3, 3), dtype=np.uint8)
        mask = np.zeros((3, 2), dtype=np.uint8)

        with self.assertRaisesRegex(ValueError, "尺寸"):
            apply_mask_to_image(original, mask, keep_value=255, fill_value=0)

    def test_filled_pixels_in_bgra_image_remain_opaque(self):
        from tools.mask_painter.core import apply_mask_to_image

        original = np.array([[[10, 20, 30, 40], [50, 60, 70, 80]]], dtype=np.uint8)
        mask = np.array([[0, 255]], dtype=np.uint8)

        result = apply_mask_to_image(original, mask, keep_value=0, fill_value=0)

        np.testing.assert_array_equal(
            result,
            np.array([[[10, 20, 30, 40], [0, 0, 0, 255]]], dtype=np.uint8),
        )


class ImageIoTests(unittest.TestCase):
    def test_round_trips_image_through_unicode_path(self):
        try:
            from tools.mask_painter.core import read_image, write_image
        except ImportError:
            self.fail("Unicode-safe image I/O is missing")

        source = np.array([[0, 127], [200, 255]], dtype=np.uint8)
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "测试_mask.png"

            write_image(path, source)
            result = read_image(path)

        np.testing.assert_array_equal(result, source)


class DrawStrokeTests(unittest.TestCase):
    def test_white_brush_overwrites_black_mask_at_stroke_position(self):
        try:
            from tools.mask_painter.core import draw_stroke
        except ImportError:
            self.fail("draw_stroke is missing")

        mask = np.zeros((5, 5), dtype=np.uint8)

        draw_stroke(mask, start=(2, 2), end=(2, 2), color=255, width=1)

        expected = np.zeros((5, 5), dtype=np.uint8)
        expected[2, 2] = 255
        np.testing.assert_array_equal(mask, expected)


if __name__ == "__main__":
    unittest.main()
