import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from registry import TOOLS, load_tool_class


@pytest.fixture
def transform_core():
    try:
        from tools.image_transform import core
    except ModuleNotFoundError:
        pytest.fail("图片变换核心尚未接入")
    return core


@pytest.fixture
def transform_widget():
    entries = [entry for entry in TOOLS if entry["name"] == "图片变换"]
    assert len(entries) == 1
    assert entries[0]["category"] == "图像处理"
    app = QApplication.instance() or QApplication([])
    window = load_tool_class(entries[0])()
    window.show()
    window.activateWindow()
    app.processEvents()
    yield window
    window.close()


def test_mirrors_and_right_angles_preserve_pixel_values_and_bit_depth(transform_core):
    source = np.array([[1, 2, 3], [4, 5, 50000]], dtype=np.uint16)
    np.testing.assert_array_equal(transform_core.flip_image(source, horizontal=True),
                                  [[3, 2, 1], [50000, 5, 4]])
    np.testing.assert_array_equal(transform_core.flip_image(source, horizontal=False),
                                  [[4, 5, 50000], [1, 2, 3]])
    clockwise = transform_core.rotate_image(source, 90)
    assert clockwise.dtype == np.uint16
    np.testing.assert_array_equal(clockwise, [[4, 1], [5, 2], [50000, 3]])
    np.testing.assert_array_equal(transform_core.rotate_image(clockwise, 90),
                                  [[50000, 5, 4], [3, 2, 1]])
    np.testing.assert_array_equal(transform_core.rotate_image(source, -90),
                                  [[3, 50000], [2, 5], [1, 4]])


def test_arbitrary_rotation_expands_bounds_and_keeps_alpha(transform_core):
    source = np.full((5, 9, 3), [10, 70, 180], dtype=np.uint8)
    result = transform_core.rotate_image(source, 45)
    assert result.shape == (10, 10, 4)
    np.testing.assert_array_equal(result[0, 0], [0, 0, 0, 0])
    np.testing.assert_array_equal(result[5, 5], [10, 70, 180, 255])


def test_transparent_pixels_do_not_bleed_color_when_rotated(transform_core):
    source = np.zeros((5, 5, 4), dtype=np.uint8)
    source[..., 0] = 255
    source[2, 2] = [0, 0, 255, 255]
    result = transform_core.rotate_image(source, 30)
    edge = result[(result[..., 3] > 0) & (result[..., 3] < 255)]
    assert len(edge)
    np.testing.assert_array_equal(edge[:, 0], 0)
    np.testing.assert_array_equal(edge[:, 2], 255)


def test_long_line_scan_only_hits_opencv_limit_for_arbitrary_angles(transform_core):
    source = np.zeros((40_000, 1), dtype=np.uint8)
    assert transform_core.rotate_image(source, 90).shape == (1, 40_000)
    with pytest.raises(ValueError, match="32,766"):
        transform_core.rotate_image(source, 0.01)


def test_editor_exports_transparent_png_and_composites_bmp_against_black(
    transform_core, tmp_path,
):
    source = np.array([[[0, 0, 65535, 0], [65535, 0, 0, 32896]]], dtype=np.uint16)
    png = tmp_path / "带透明.png"
    bmp = tmp_path / "黑色背景.bmp"
    transform_core.save_image(png, source)
    transform_core.save_image(bmp, source)
    np.testing.assert_array_equal(cv2.imdecode(np.fromfile(png, np.uint8), -1), source)
    np.testing.assert_array_equal(cv2.imdecode(np.fromfile(bmp, np.uint8), -1),
                                  [[[0, 0, 0], [128, 0, 0]]])


def test_keyboard_rotation_accumulates_and_supports_undo_redo_reset(transform_widget, tmp_path):
    window = transform_widget
    source_path = tmp_path / "输入图.png"
    source = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.uint8)
    source_path.write_bytes(cv2.imencode(".png", source)[1].tobytes())
    window.load_image(source_path)
    alt = Qt.KeyboardModifier.AltModifier
    ctrl = Qt.KeyboardModifier.ControlModifier
    QTest.keyClick(window, Qt.Key.Key_Right, alt)
    QTest.keyClick(window, Qt.Key.Key_Right, alt)
    np.testing.assert_array_equal(window.current_image, [[6, 5, 4], [3, 2, 1]])

    QTest.keyClick(window, Qt.Key.Key_Z, ctrl)
    np.testing.assert_array_equal(window.current_image, [[4, 1], [5, 2], [6, 3]])
    QTest.keyClick(window, Qt.Key.Key_Y, ctrl)
    np.testing.assert_array_equal(window.current_image, [[6, 5, 4], [3, 2, 1]])
    QTest.keyClick(window, Qt.Key.Key_R, ctrl)
    np.testing.assert_array_equal(window.current_image, source)

    QTest.keyClick(window, Qt.Key.Key_Z, ctrl)
    QTest.keyClick(window, Qt.Key.Key_H, alt)
    QTest.keyClick(window, Qt.Key.Key_Y, ctrl)
    output = tmp_path / "结果.png"
    window.save_current(output)
    np.testing.assert_array_equal(cv2.imdecode(np.fromfile(output, np.uint8), -1),
                                  [[4, 5, 6], [1, 2, 3]])
    assert not window.redo_action.isEnabled()


def test_save_dialog_prefills_complete_name_for_dotted_input(transform_widget, tmp_path):
    source_path = tmp_path / "capture.2026.png"
    source_path.write_bytes(cv2.imencode(".png", np.ones((2, 2), dtype=np.uint8))[1].tobytes())
    transform_widget.load_image(source_path)
    names = []

    def inspect_dialog():
        dialog = QApplication.activeModalWidget()
        names.extend(dialog.selectedFiles())
        dialog.reject()

    QTimer.singleShot(0, inspect_dialog)
    transform_widget.save_action.trigger()
    assert [os.path.basename(name) for name in names] == ["capture.2026_transformed.png"]
