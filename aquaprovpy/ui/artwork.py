"""Supplied AquaProv logo and scalable interface illustrations."""
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget
from .branding import COLORS, ICON_PATH, LOGO_PATH


def app_icon():
    return QIcon(str(ICON_PATH))


class BrandLogo(QWidget):
    """Draw the original transparent artwork without stretching or cropping."""

    asset_path = LOGO_PATH

    def __init__(self, width, height, parent=None):
        super().__init__(parent)
        self._logo = QPixmap(str(self.asset_path))
        self.setFixedSize(width, height)
        self.setAccessibleName('AquaProv logo')
        self.setToolTip('AquaProv')

    def paintEvent(self, event):
        if self._logo.isNull():
            return
        size = self._logo.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF((self.width() - size.width()) / 2,
                        (self.height() - size.height()) / 2, size.width(), size.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(target, self._logo, QRectF(self._logo.rect()))
        painter.end()


class BrandIcon(BrandLogo):
    """Use the square application artwork in compact interface locations."""

    asset_path = ICON_PATH

    def __init__(self, size, parent=None):
        super().__init__(size, size, parent)
        self.setAccessibleName('AquaProv icon')


class WaterBanner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor(COLORS['surface']))
        gradient.setColorAt(1, QColor(COLORS['banner_end']))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(self.rect()), 18, 18)
        painter.setClipRect(self.rect())
        # Contour-like wave field is decorative, independent of project data.
        for row in range(17):
            path = QPainterPath()
            for step in range(101):
                x = self.width() * (.52 + step / 180)
                y = 35 + row * 11 + math.sin(step / 15 + row / 9) * (22 + row)
                if step == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.setPen(QPen(QColor(0, 149, 191, 10 + row * 2), 1.1))
            painter.drawPath(path)
        for x, y in ((.77, .28), (.86, .56), (.68, .69), (.93, .3)):
            painter.setPen(QPen(QColor(COLORS['cyan']), 1))
            painter.setBrush(QColor(COLORS['wash']))
            painter.drawEllipse(QPointF(x * self.width(), y * self.height()), 4, 4)
        painter.end()


class ModuleArt(QWidget):
    def __init__(self, module):
        super().__init__()
        self.module = module
        self.setFixedHeight(86)
        self.setMinimumWidth(180)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(self.module.tint))
        painter.translate(self.width() / 2 - 80, 4)
        painter.setPen(QPen(QColor(self.module.accent), 1.6))
        def line(a, b):
            painter.drawLine(QPointF(*a), QPointF(*b))
        if self.module.key == "groundwater":
            for offset in (8, 88):
                line((offset, 68), (offset + 30, 15))
                line((offset + 30, 15), (offset + 60, 68))
                line((offset, 68), (offset + 60, 68))
                for t in (.33, .66):
                    line((offset + 30 * t, 68 - 53 * t), (offset + 60 - 30 * t, 68 - 53 * t))
                painter.setBrush(QColor(self.module.accent))
                for x, y in ((23, 55), (36, 46), (29, 36), (42, 58)):
                    painter.drawEllipse(QPointF(offset + x, y), 2.4, 2.4)
                painter.setBrush(Qt.BrushStyle.NoBrush)
        elif self.module.key == "maps":
            painter.translate(80, 38)
            for ring in range(1, 7):
                path = QPainterPath()
                for step in range(65):
                    angle = step * math.pi / 32
                    r = ring * 7 + 3 * math.sin(angle * 3 + ring / 3)
                    point = QPointF(math.cos(angle) * r * 1.6, math.sin(angle) * r * .75)
                    if step == 0:
                        path.moveTo(point)
                    else:
                        path.lineTo(point)
                painter.drawPath(path)
        else:
            for row in range(7):
                for col in range(7):
                    def p(r, c):
                        return (30 + c * 13 + r * 6, 43 + r * 5 - c * 2 - 22 * math.exp(-((c-3)**2 + (r-3)**2) / 5))
                    if row < 6:
                        line(p(row, col), p(row + 1, col))
                    if col < 6:
                        line(p(row, col), p(row, col + 1))
        painter.end()
