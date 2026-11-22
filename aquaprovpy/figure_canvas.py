"""Qt preview that scales typography with a figure's intended physical size."""
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backend_bases import DrawEvent
from PySide6.QtGui import QResizeEvent


class PreviewCanvas(FigureCanvasQTAgg):
    """Render busy previews in Agg workers and present their buffers with Qt."""
    _background_drawing = False
    _pending_resize = None

    def draw(self):
        from shiboken6 import isValid
        if not isValid(self):
            return
        from .ui.loading import is_loading, run_worker
        if self._background_drawing:
            return
        from .plot_legends import connect_legend_dragging
        connect_legend_dragging(self.figure)
        if not is_loading():
            return super().draw()
        from .core.plot_jobs import detached_figure
        from .core.progress import progress_stage
        from .core.progress import JobCancelled
        self._background_drawing = True
        self._is_drawing = True
        figure = self.figure
        def render():
            with detached_figure(figure) as canvas:
                canvas.draw()
                return canvas.renderer
        try:
            with progress_stage(90, 97, 'Rendering preview'):
                self.renderer = run_worker(render)
                # Progress bars can repaint the canvas synchronously. Install
                # the cache key before reporting progress, or get_renderer()
                # replaces the finished image with a new, empty bitmap.
                self._lastKey = (*figure.bbox.size, figure.dpi)
            DrawEvent('draw_event', self, self.renderer)._process()
        except JobCancelled:
            # Qt's idle-draw handler prints all exceptions. Cancellation is
            # handled by the owning plot scope, without a rendering traceback.
            self._draw_pending = False
            return
        finally:
            self._is_drawing = self._background_drawing = False
            if isValid(self):
                self.apply_pending_resize()
        if isValid(self):
            self.update()

    def paintEvent(self, event):
        if not self._background_drawing:
            super().paintEvent(event)

    def apply_pending_resize(self):
        if self._pending_resize is not None:
            size, old = self._pending_resize
            self._pending_resize = None
            self.resizeEvent(QResizeEvent(size, old))

    def resizeEvent(self, event):
        if self._background_drawing:
            self._pending_resize = (event.size(), event.oldSize())
            return
        super().resizeEvent(event)


class PublicationCanvas(PreviewCanvas):
    def __init__(self, figure, physical_size):
        self.physical_size = tuple(physical_size)
        super().__init__(figure)

    def resizeEvent(self, event):
        if self._background_drawing:
            self._pending_resize = (event.size(), event.oldSize())
            return
        width, height = self.physical_size
        # Qt otherwise changes figsize while retaining point-sized fonts. On a
        # short wide preview that crowds labels on square ternary diagrams.
        dpi = min(event.size().width() / width, event.size().height() / height)
        if dpi > 0:
            # Layouts can briefly give a newly shown panel a one-pixel size.
            # FreeType cannot render text at the resulting sub-pixel ppem.
            # Keep a usable lower bound; export still uses the requested DPI.
            self.figure.set_dpi(max(36, dpi * self.device_pixel_ratio))
        super().resizeEvent(event)
