import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np


class NormalizeImageTests(unittest.TestCase):
    def test_scales_sixteen_bit_grayscale_to_eight_bit_bgr(self):
        try:
            from tools.color_space_viewer.core import normalize_image
        except ModuleNotFoundError:
            self.fail("Color space viewer core module is missing")

        source = np.array([[0, 32768, 65535]], dtype=np.uint16)

        result = normalize_image(source)

        np.testing.assert_array_equal(
            result,
            np.array([[[0, 0, 0], [128, 128, 128], [255, 255, 255]]], dtype=np.uint8),
        )

    def test_discards_alpha_and_keeps_bgr_channels(self):
        from tools.color_space_viewer.core import normalize_image

        source = np.array([[[10, 20, 30, 40]]], dtype=np.uint8)

        result = normalize_image(source)

        np.testing.assert_array_equal(result, np.array([[[10, 20, 30]]], dtype=np.uint8))


class ConvertImageTests(unittest.TestCase):
    def test_converts_red_pixel_to_opencv_grayscale(self):
        try:
            from tools.color_space_viewer.core import convert_image
        except ImportError:
            self.fail("convert_image is missing")

        source = np.array([[[0, 0, 255]]], dtype=np.uint8)

        result = convert_image(source, "GRAY", "Gray")

        np.testing.assert_array_equal(result, np.array([[76]], dtype=np.uint8))

    def test_exposes_hsv_channels_as_grayscale_images(self):
        from tools.color_space_viewer.core import convert_image

        source = np.array([[[0, 0, 255]]], dtype=np.uint8)

        self.assertEqual(int(convert_image(source, "HSV", "H")[0, 0]), 0)
        self.assertEqual(int(convert_image(source, "HSV", "S")[0, 0]), 255)
        self.assertEqual(int(convert_image(source, "HSV", "V")[0, 0]), 255)

    def test_hsv_composite_maps_normalized_h_s_v_to_visible_r_g_b(self):
        from tools.color_space_viewer.core import convert_image

        source = np.array([[[0, 255, 0]]], dtype=np.uint8)

        result = convert_image(source, "HSV", "Composite")

        np.testing.assert_array_equal(result, np.array([[[255, 255, 85]]], dtype=np.uint8))

    def test_exposes_lab_channels_for_black_and_white(self):
        from tools.color_space_viewer.core import convert_image

        source = np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8)

        np.testing.assert_array_equal(
            convert_image(source, "LAB", "L"),
            np.array([[0, 255]], dtype=np.uint8),
        )
        np.testing.assert_array_equal(
            convert_image(source, "LAB", "a"),
            np.array([[128, 128]], dtype=np.uint8),
        )
        np.testing.assert_array_equal(
            convert_image(source, "LAB", "b"),
            np.array([[128, 128]], dtype=np.uint8),
        )

    def test_rejects_unknown_space_and_view(self):
        from tools.color_space_viewer.core import convert_image

        source = np.zeros((1, 1, 3), dtype=np.uint8)

        with self.assertRaisesRegex(ValueError, "色彩空间"):
            convert_image(source, "CMYK", "Composite")
        with self.assertRaisesRegex(ValueError, "视图"):
            convert_image(source, "HSV", "X")

    def test_extended_spaces_provide_composite_and_each_grayscale_channel(self):
        from tools.color_space_viewer.core import available_views, convert_image

        source = np.array([[[10, 20, 30], [40, 50, 60]]], dtype=np.uint8)
        expected = {
            "HLS": ("Composite", "H", "L", "S"),
            "YCrCb": ("Composite", "Y", "Cr", "Cb"),
            "XYZ": ("Composite", "X", "Y", "Z"),
        }

        for space, views in expected.items():
            with self.subTest(space=space):
                self.assertEqual(available_views(space), views)
                self.assertEqual(convert_image(source, space, "Composite").shape, (1, 2, 3))
                for channel in views[1:]:
                    self.assertEqual(convert_image(source, space, channel).shape, (1, 2))


class ImageIoTests(unittest.TestCase):
    def test_round_trips_image_through_unicode_path(self):
        try:
            from tools.color_space_viewer.core import read_image, write_image
        except ImportError:
            self.fail("Unicode-safe image I/O is missing")

        source = np.array([[[1, 2, 3], [4, 5, 6]]], dtype=np.uint8)
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "色彩空间.png"

            write_image(path, source)
            result = read_image(path)

        np.testing.assert_array_equal(result, source)


if __name__ == "__main__":
    unittest.main()
