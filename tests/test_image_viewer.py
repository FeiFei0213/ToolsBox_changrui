import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from launcher import LauncherWindow
from registry import TOOLS, load_tool_class
from tools.image_io import write_image
from tools.image_preview import array_to_pixmap


@pytest.fixture
def viewer():
    app = QApplication.instance() or QApplication([])
    entries = [entry for entry in TOOLS if entry["name"] == "Ziv 看图"]
    assert len(entries) == 1 and entries[0]["category"] == "图像处理"
    window = load_tool_class(entries[0])()
    window.show()
    window.activateWindow()
    app.processEvents()
    yield window
    window.close()


def picture(folder: Path, name: str, *, width: int = 128, height: int = 96) -> Path:
    path = folder / name
    write_image(path, np.full((height, width), 50_000, dtype=np.uint16))
    return path


def test_launcher_can_search_and_open_ziv():
    app = QApplication.instance() or QApplication([])
    launcher = LauncherWindow()
    launcher.show()
    try:
        launcher.category_buttons["图像处理"].click()
        launcher.search_edit.setText("ziv")
        QTest.keyClick(launcher.search_edit, Qt.Key.Key_Return)
        assert len(launcher._open_tools) == 1
        assert launcher._open_tools[0].windowTitle() == "Ziv 看图"
    finally:
        for tool in launcher._open_tools[:]:
            tool.close()
        launcher.close()


def test_directory_navigation_is_naturally_sorted_wraps_and_skips_bad_images(viewer, tmp_path):
    first = picture(tmp_path, "线扫1.png")
    (tmp_path / "线扫2.png").write_bytes(b"not an image")
    (tmp_path / "线扫3.txt").write_text("not an image")
    second = picture(tmp_path, "线扫4.PNG")
    last = picture(tmp_path, "线扫10.png")
    viewer.load_image(first)

    QTest.keyClick(viewer.view, Qt.Key.Key_Right)
    assert viewer.current_path == second
    QTest.keyClick(viewer.view, Qt.Key.Key_Right)
    assert viewer.current_path == last
    QTest.keyClick(viewer.view, Qt.Key.Key_Right)
    assert viewer.current_path == first
    QTest.keyClick(viewer.view, Qt.Key.Key_Left)
    assert viewer.current_path == last


def test_mouse_reports_original_coordinates_and_measures_after_zoom(viewer, tmp_path):
    viewer.load_image(picture(tmp_path, "测量.png", width=1200, height=900))
    QTest.keyClick(viewer.view, Qt.Key.Key_1)
    viewport = viewer.view.viewport()
    anchor = viewport.rect().center() + QPoint(60, 40)
    before = viewer.view.mapToScene(anchor)
    wheel = QWheelEvent(
        QPointF(anchor), QPointF(viewport.mapToGlobal(anchor)), QPoint(), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    QApplication.sendEvent(viewport, wheel)
    assert viewer.view.transform().m11() > 1.0
    assert (viewer.view.mapToScene(anchor) - before).manhattanLength() < 2.0

    QTest.keyClick(viewer.view, Qt.Key.Key_C)
    assert viewer.crosshair_action.isChecked()
    QTest.keyClick(viewer.view, Qt.Key.Key_M)
    x, y = int(before.x()), int(before.y())
    start = viewer.view.mapFromScene(QPointF(x + 0.5, y + 0.5))
    end = viewer.view.mapFromScene(QPointF(x + 30.5, y + 40.5))
    QTest.mouseMove(viewport, start)
    assert viewer.coordinate_label.text() == f"X {x}  Y {y}"
    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=end)
    assert "50.00 px" in viewer.measurement_label.text()

    QTest.keyClick(viewer.view, Qt.Key.Key_Escape)
    assert "50.00 px" not in viewer.measurement_label.text()


def test_first_zoom_from_fit_preserves_off_center_mouse_anchor(viewer, tmp_path):
    viewer.resize(800, 500)
    QApplication.processEvents()
    viewer.load_image(picture(tmp_path, "缩放锚点.png", width=1200, height=900))
    viewport = viewer.view.viewport()
    anchor = viewer.view.mapFromScene(QPointF(960, 675))
    before = viewer.view.mapToScene(anchor)
    wheel = QWheelEvent(
        QPointF(anchor), QPointF(viewport.mapToGlobal(anchor)), QPoint(), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    QApplication.sendEvent(viewport, wheel)
    after = viewer.view.mapToScene(anchor)
    assert max(abs(after.x() - before.x()), abs(after.y() - before.y())) <= 1.25


def test_16_bit_preview_preserves_full_range_and_rounds_nearest(viewer):
    source = np.array([[0, 128, 129, 32767, 32768, 65535]], dtype=np.uint16)
    preview = array_to_pixmap(source).toImage()
    assert [preview.pixelColor(x, 0).red() for x in range(source.shape[1])] == [
        0, 0, 1, 127, 128, 255,
    ]


def test_switching_images_clears_measurement_and_refits(viewer, tmp_path):
    first = picture(tmp_path, "1.png")
    second = picture(tmp_path, "2.png", width=64, height=48)
    viewer.load_image(first)
    QTest.keyClick(viewer.view, Qt.Key.Key_M)
    clicked = viewer.view.mapFromScene(QPointF(20.5, 30.5))
    QTest.mouseClick(viewer.view.viewport(), Qt.MouseButton.LeftButton, pos=clicked)
    assert "20, 30" in viewer.measurement_label.text()

    QTest.keyClick(viewer.view, Qt.Key.Key_Right)
    assert viewer.current_path == second
    assert "20, 30" not in viewer.measurement_label.text()
    assert viewer.view.sceneRect().size().toSize().width() == 64


def test_drop_loads_image_and_middle_drag_pans_in_measurement_mode(viewer, tmp_path):
    source = picture(tmp_path, "拖拽打开.png", width=1200, height=900)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source))])
    position = viewer.rect().center()
    drag = QDragEnterEvent(
        position, Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    drop = QDropEvent(
        QPointF(position), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(viewer, drag)
    assert drag.isAccepted()
    QApplication.sendEvent(viewer, drop)
    assert drop.isAccepted() and viewer.current_path == source

    QTest.keyClick(viewer.view, Qt.Key.Key_1)
    QTest.keyClick(viewer.view, Qt.Key.Key_M)
    viewport = viewer.view.viewport()
    center = viewport.rect().center()
    before = viewer.view.mapToScene(center)
    QTest.mousePress(viewport, Qt.MouseButton.MiddleButton, pos=center)
    QTest.mouseMove(viewport, center + QPoint(35, 25))
    QTest.mouseRelease(viewport, Qt.MouseButton.MiddleButton, pos=center + QPoint(35, 25))
    assert before - viewer.view.mapToScene(center) == QPointF(35, 25)
    assert "点击图片选取起点" in viewer.measurement_label.text()


def test_hover_coordinates_update_when_fit_changes_without_moving_mouse(viewer, tmp_path):
    viewer.load_image(picture(tmp_path, "坐标.png", width=1200, height=900))
    viewport = viewer.view.viewport()
    anchor = viewport.rect().center() + QPoint(75, 50)
    QTest.mouseMove(viewport, anchor)
    prior = viewer.coordinate_label.text()
    QTest.keyClick(viewer.view, Qt.Key.Key_1)
    point = viewer.view.mapToScene(anchor)
    assert viewer.coordinate_label.text() != prior
    assert viewer.coordinate_label.text() == f"X {int(point.x())}  Y {int(point.y())}"


def test_pointer_leaving_canvas_clears_coordinates(viewer, tmp_path):
    viewer.load_image(picture(tmp_path, "准星.png"))
    viewport = viewer.view.viewport()
    QTest.mouseMove(viewport, viewport.rect().center())
    assert viewer.coordinate_label.text() != "X —  Y —"
    QApplication.sendEvent(viewport, QEvent(QEvent.Type.Leave))
    assert viewer.coordinate_label.text() == "X —  Y —"


def test_fit_includes_transparent_pixels_at_the_edges(viewer, tmp_path):
    source = tmp_path / "透明区域.png"
    image = np.zeros((80, 1600, 4), dtype=np.uint8)
    image[:, :5] = [0, 0, 255, 255]
    write_image(source, image)
    viewer.load_image(source)
    assert viewer.view.sceneRect().width() == 1600
    assert viewer.view.mapFromScene(viewer.view.sceneRect()).boundingRect().width() <= viewer.view.viewport().width()


def test_pan_stops_when_mouse_capture_is_lost(viewer, tmp_path):
    viewer.load_image(picture(tmp_path, "平移.png", width=1200, height=900))
    QTest.keyClick(viewer.view, Qt.Key.Key_1)
    viewport = viewer.view.viewport()
    center = viewport.rect().center()
    before = viewer.view.mapToScene(center)
    QTest.mousePress(viewport, Qt.MouseButton.MiddleButton, pos=center)
    position = center + QPoint(40, 20)
    move_without_button = QMouseEvent(
        QMouseEvent.Type.MouseMove, QPointF(position), QPointF(viewport.mapToGlobal(position)),
        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(viewport, move_without_button)
    QTest.mouseRelease(viewport, Qt.MouseButton.MiddleButton, pos=position)
    assert viewer.view.mapToScene(center) == before
