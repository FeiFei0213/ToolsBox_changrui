"""保持宽高比的 Qt 图像预览。"""

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy


class PreviewLabel(QLabel):
    def __init__(self, placeholder: str):
        super().__init__(placeholder)
        self._pixmap = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(240, 180)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setStyleSheet(
            "background-color:#202124; color:#b8bec7; border:1px solid #3c4043; "
            "border-radius:6px;"
        )

    def set_array(self, image: np.ndarray | None, placeholder: str = "等待加载图片") -> None:
        if image is None:
            self._pixmap = QPixmap()
            self.setText(placeholder)
            return

        # 仅转换显示用像素，导出仍使用变换后的原始位深。
        if image.dtype == np.uint16:
            image = np.rint(image / 257.0).astype(np.uint8)
        image = np.ascontiguousarray(image)
        if image.ndim == 2:
            pixel_format = QImage.Format.Format_Grayscale8
        elif image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
            pixel_format = QImage.Format.Format_RGBA8888
        else:
            pixel_format = QImage.Format.Format_BGR888
        height, width = image.shape[:2]
        qimage = QImage(image.data, width, height, image.strides[0], pixel_format)
        self._pixmap = QPixmap.fromImage(qimage.copy())
        self._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self):
        if not self._pixmap.isNull():
            self.setPixmap(self._pixmap.scaled(
                self.contentsRect().size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
