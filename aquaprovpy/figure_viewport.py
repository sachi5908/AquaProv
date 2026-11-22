"""Scrollable, magnifiable figures without cropping their analytical axes."""
import math

from PySide6.QtCore import QPointF, QSize, Qt, QTimer
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QScrollArea, QSizePolicy

from .figure_canvas import PublicationCanvas


class FigureViewport(QScrollArea):
    MIN_PREVIEW_DPI = 72
    MAX_PIXELS = 24_000_000
    MAX_SIDE = 32760

    def __init__(self, canvas, physical_size):
        super().__init__()
        self.canvas = canvas
        self.physical_size = tuple(physical_size)
        self._sizing = False
        self._drag_anchor = None
        self._drag_cursor = None
        self._restore_pending = getattr(canvas.figure, '_aquaprov_viewport_state', None)
        self.zoom = (self._restore_pending or {}).get('zoom', 1.0)
        self._map_base_dpi = 100
        self.setObjectName('figureScrollArea')
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(0, 0)
        self.horizontalScrollBar().setAccessibleName('Scroll plot horizontally')
        self.verticalScrollBar().setAccessibleName('Scroll plot vertically')
        self.setStyleSheet('''
            QScrollArea#figureScrollArea { border: 0; background: #edf2f5; }
            QScrollBar:horizontal { height: 7px; background: #edf2f5; margin: 0; }
            QScrollBar:vertical { width: 7px; background: #edf2f5; margin: 0; }
            QScrollBar::handle { background: #a8bec9; border-radius: 3px; }
            QScrollBar::handle:horizontal { min-width: 28px; }
            QScrollBar::handle:vertical { min-height: 28px; }
            QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
            QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
        ''')
        self.setWidget(canvas)
        canvas._aquaprov_viewport = self
        for bar in (self.horizontalScrollBar(), self.verticalScrollBar()):
            bar.valueChanged.connect(self.save_state)

    def sizeHint(self):
        # A long dendrogram must grow the scrollable page, not the window.
        return QSize(640, 480)

    def minimumSizeHint(self):
        return QSize(120, 100)

    def _scroll_position(self):
        return {name: bar.value() / max(1, bar.maximum()) for name, bar in (
            ('x', self.horizontalScrollBar()), ('y', self.verticalScrollBar()))}

    def save_state(self, *_):
        if self.isVisible() and not self._sizing and self._restore_pending is None:
            self.canvas.figure._aquaprov_viewport_state = dict(zoom=self.zoom, **self._scroll_position())

    def restore_state(self, state):
        self.zoom = state.get('zoom', 1.0)
        self._restore_pending = dict(state)

    def refresh_size(self, physical_size=None, *, anchor=None):
        if self._sizing:
            return
        if getattr(self.canvas, '_background_drawing', False):
            # Resizing must not mutate a figure while Agg is using it.
            if not getattr(self, '_resize_deferred', False):
                self._resize_deferred = True
                QTimer.singleShot(50, self._refresh_deferred_size)
            return
        if physical_size is not None:
            self.physical_size = tuple(physical_size)
        if not self.isVisible():
            return
        viewport = self.viewport().size()
        if viewport.width() < 32 or viewport.height() < 32:
            return
        width, height = self.physical_size
        dpi = max(self.MIN_PREVIEW_DPI, min(viewport.width() / width, viewport.height() / height))
        ratio = self.canvas.device_pixel_ratio
        # Limit the backing bitmap on high-DPI displays and very long figures.
        maximum = min(8., self.MAX_SIDE / (width * dpi * ratio),
                      self.MAX_SIDE / (height * dpi * ratio),
                      math.sqrt(self.MAX_PIXELS / (width * height * (dpi * ratio) ** 2)))
        self.zoom = min(maximum, max(.5, self.zoom))
        size = QSize(max(1, round(width * dpi * self.zoom)), max(1, round(height * dpi * self.zoom)))
        position = self._restore_pending or self._scroll_position()
        self._sizing = True
        try:
            if isinstance(self.canvas, PublicationCanvas):
                self.canvas.physical_size = self.physical_size
            else:
                # Map labels keep their screen size at the starting zoom.
                self.canvas.figure.set_dpi(self._map_base_dpi * self.zoom * ratio)
            unchanged = self.canvas.size() == size
            self.canvas.resize(size)
            if unchanged:
                # Applying a style resets figsize even when the Qt geometry
                # stays the same; restore its preview DPI and physical size.
                self.canvas.resizeEvent(QResizeEvent(size, size))
            if anchor is None:
                self.horizontalScrollBar().setValue(round(position.get('x', 0) * self.horizontalScrollBar().maximum()))
                self.verticalScrollBar().setValue(round(position.get('y', 0) * self.verticalScrollBar().maximum()))
            else:
                fractions, point = anchor
                self.horizontalScrollBar().setValue(round(fractions.x() * size.width() - point.x()))
                self.verticalScrollBar().setValue(round(fractions.y() * size.height() - point.y()))
        finally:
            self._sizing = False
        self._restore_pending = None
        self.save_state()
        self.canvas.draw_idle()

    def _refresh_deferred_size(self):
        self._resize_deferred = False
        self.refresh_size()

    def zoom_at(self, step, position):
        if not math.isfinite(step) or not step:
            return
        fractions = QPointF(position.x() / max(1, self.canvas.width()),
                            position.y() / max(1, self.canvas.height()))
        point = self.canvas.mapTo(self.viewport(), position.toPoint())
        self.zoom *= 1.2 ** max(-10, min(10, step))
        self.refresh_size(anchor=(fractions, point))

    def reset(self):
        self.end_drag()
        self.zoom = 1.0
        self._restore_pending = {'x': 0, 'y': 0}
        self.refresh_size()

    def begin_drag(self, position):
        point = self.canvas.mapTo(self.viewport(), position.toPoint())
        self._drag_anchor = (point, self.horizontalScrollBar().value(), self.verticalScrollBar().value())
        self._drag_cursor = self.canvas.cursor()
        self.canvas.setCursor(Qt.CursorShape.ClosedHandCursor)

    def drag_to(self, position):
        if self._drag_anchor is None:
            return
        # Canvas coordinates change while scrolling. Measure pointer movement
        # in the stationary viewport to avoid jumps or accelerating the drag.
        point = self.canvas.mapTo(self.viewport(), position.toPoint())
        start, horizontal, vertical = self._drag_anchor
        self.horizontalScrollBar().setValue(horizontal - (point.x() - start.x()))
        self.verticalScrollBar().setValue(vertical - (point.y() - start.y()))

    def end_drag(self):
        self._drag_anchor = None
        if self._drag_cursor is not None:
            self.canvas.setCursor(self._drag_cursor)
            self._drag_cursor = None
        self.save_state()

    def resizeEvent(self, event):
        position = self._restore_pending or dict(zoom=self.zoom, **self._scroll_position())
        sizing = self._sizing
        self._sizing = True
        try:
            super().resizeEvent(event)
        finally:
            self._sizing = sizing
        if not sizing:
            self._restore_pending = position
            self.refresh_size()

    def showEvent(self, event):
        self._restore_pending = self._restore_pending or getattr(self.canvas.figure, '_aquaprov_viewport_state', None)
        super().showEvent(event)
        self.refresh_size()

    def hideEvent(self, event):
        self.save_state()
        super().hideEvent(event)

    def wheelEvent(self, event):
        # Wheel gestures over the empty border magnify the page as well.
        step = event.angleDelta().y() / 120 or event.pixelDelta().y() / 120
        position = self.canvas.mapFrom(self.viewport(), event.position().toPoint())
        self.zoom_at(step, QPointF(position))
        event.accept()
