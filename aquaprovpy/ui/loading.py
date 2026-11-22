"""Loading overlays and background work for a responsive Qt interface."""

from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from functools import wraps
import gc
from time import monotonic

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QProgressBar, QPushButton, QTableView, QVBoxLayout, QWidget
from shiboken6 import isValid

from .branding import brand_stylesheet
from ..core.progress import (progress_listener, progress_stage, report_progress,
                             active_cancellation, CancellationToken, JobCancelled, check_cancelled)


_active_overlay = ContextVar('aquaprov_loading_overlay', default=None)


def is_loading():
    overlay = _active_overlay.get()
    return overlay is not None and overlay.active


def loading_checkpoint():
    """Let guarded UI construction paint between small batches of controls.

    Widgets must stay on the GUI thread. Only pump events inside a busy scope,
    where its input guard prevents interaction with the unfinished workspace.
    Slow imports and calculations still belong in run_worker().
    """
    overlay = _active_overlay.get()
    if overlay is None or not overlay.active:
        return
    now = monotonic()
    if now - overlay._last_checkpoint >= .04:
        overlay._last_checkpoint = now
        QApplication.instance().processEvents()


class _InputGuard(QObject):
    """Mediate edits/close: cancel plot work, then deliver the user's action."""
    EVENTS = {QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
              QEvent.Type.MouseButtonDblClick, QEvent.Type.Wheel,
              QEvent.Type.KeyPress, QEvent.Type.KeyRelease, QEvent.Type.Shortcut,
              QEvent.Type.ShortcutOverride, QEvent.Type.ContextMenu,
              QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop,
              QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd}

    def __init__(self, window, overlay):
        super().__init__(window)
        self.window = window
        self.overlay = overlay

    def eventFilter(self, watched, event):
        owner = watched
        while owner is not None and not isinstance(owner, QWidget):
            owner = owner.parent()
        if owner is not None and owner.window() is self.window:
            overlay = self.overlay
            if overlay.cancellation is not None:
                if (event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease, QEvent.Type.ShortcutOverride)
                        and event.key() == Qt.Key.Key_Escape):
                    overlay.request_cancel()
                    event.accept()
                    return True
                if owner is overlay.cancel_button or overlay.cancel_button.isAncestorOf(owner):
                    return False
                # Reading/scrolling a table does not change the running job.
                ancestor = owner
                while ancestor is not None:
                    if isinstance(ancestor, QTableView):
                        return False
                    ancestor = ancestor.parentWidget()
                if event.type() == QEvent.Type.Close and watched is self.window:
                    overlay._close_after_cancel = True
                    overlay.request_cancel()
                    event.ignore()
                    return True
                if event.type() in self.EVENTS:
                    escape = (event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease, QEvent.Type.ShortcutOverride)
                              and event.key() == Qt.Key.Key_Escape)
                    if not escape and not overlay.isAncestorOf(owner) and owner is not overlay:
                        # Replay navigation/editing once the worker releases its
                        # snapshot. Never destroy its owner or mix new settings
                        # into the result while that worker is still running.
                        if len(overlay._deferred_events) < 32:
                            # clone() returns a C++-owned event in PySide. Use
                            # the Python-owned copy constructor so postEvent
                            # can transfer its lifetime to Qt safely.
                            try:
                                copied = type(event)(event)
                            except TypeError:
                                copied = None
                            if copied is not None:
                                overlay._deferred_events.append((watched, copied))
                    overlay.request_cancel()
                    event.accept()
                    return True
            if event.type() in self.EVENTS:
                event.accept()
                return True
            if event.type() == QEvent.Type.Close and watched is self.window:
                event.ignore()
                return True
        return False


class BusyOverlay(QWidget):
    def __init__(self, parent, name):
        super().__init__(parent)
        self.setObjectName(name)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(brand_stylesheet('''
            QWidget#projectLoader, QWidget#plotLoader { background: rgba(240, 247, 250, 242); }
            QFrame#loadingCard { background: white; border: 1px solid @border@; border-radius: 12px; }
            QLabel#loadingTitle { background: transparent; border: 0; color: @ink@; font: 600 11pt 'Segoe UI'; }
            QLabel#loadingDetail { background: transparent; border: 0; color: @muted@; font: 9pt 'Segoe UI'; }
            QLabel#loadingPercent { background: transparent; border: 0; color: @teal@; font: 600 22pt 'Segoe UI'; }
            QLabel#loadingElapsed { background: transparent; border: 0; color: @muted@; font: 8pt 'Segoe UI'; }
            QProgressBar#loadingProgress { background: @border@; border: 0; border-radius: 5px; }
            QProgressBar#loadingProgress::chunk { background: @teal@; border-radius: 5px; }
        '''))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        self.card = QFrame()
        self.card.setObjectName('loadingCard')
        self.card.setMinimumWidth(300)
        self.card.setMaximumWidth(380)
        content = QVBoxLayout(self.card)
        content.setContentsMargins(28, 24, 28, 24)
        content.setSpacing(12)
        self.title = QLabel()
        self.title.setObjectName('loadingTitle')
        self.detail = QLabel()
        self.detail.setObjectName('loadingDetail')
        for label in (self.title, self.detail):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            content.addWidget(label)
        self.percent = QLabel('0%')
        self.percent.setObjectName('loadingPercent')
        self.percent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.percent)
        self.progress = QProgressBar()
        self.progress.setObjectName('loadingProgress')
        self.progress.setAccessibleName('Task completion')
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)
        content.addWidget(self.progress)
        self.elapsed = QLabel()
        self.elapsed.setObjectName('loadingElapsed')
        self.elapsed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.elapsed)
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.setObjectName('cancelPlotJob')
        self.cancel_button.setAccessibleName('Cancel plot generation')
        self.cancel_button.setToolTip('Stop this plot (Esc). Navigation or edits also stop the current plot.')
        self.cancel_button.clicked.connect(self.request_cancel)
        content.addWidget(self.cancel_button)
        self.cancel_button.hide()
        self.cancellation = None
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._update_elapsed)
        layout.addWidget(self.card, alignment=Qt.AlignmentFlag.AlignCenter)
        parent.installEventFilter(self)
        self.active = False
        self.hide()

    def _update_elapsed(self):
        seconds = int(monotonic() - self._started)
        self.elapsed.setText(f'Elapsed {seconds // 60:02d}:{seconds % 60:02d}')

    @Slot(float, str)
    def set_progress(self, value, detail=''):
        if not self.active or self._failed or self.cancelled:
            return
        # Only busy() can mark completion after the result is installed/painted.
        value = max(self.progress.value(), min(99, int(value)))
        self.progress.setValue(value)
        self.percent.setText(f'{value}%')
        if detail:
            self.detail.setText(detail)
            self.detail.show()
        self.progress.setAccessibleDescription(self.detail.text())

    def fail(self):
        self._failed = True
        self.hide()

    @property
    def cancelled(self):
        return self.cancellation is not None and self.cancellation.cancelled

    def request_cancel(self):
        if not self.active or self.cancellation is None or self.cancelled:
            return
        self.cancellation.cancel()
        self.detail.setText('Stopping calculation…')
        self.cancel_button.setEnabled(False)

    def _replay_interaction(self, events, close_window):
        if close_window:
            if isValid(close_window):
                close_window.close()
            return
        for receiver, event in events:
            if isValid(receiver):
                QCoreApplication.postEvent(receiver, event)

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.setGeometry(watched.rect())
            if self.active:
                self.raise_()
        return False

    @contextmanager
    def busy(self, title, detail='', *, cancellable=False):
        if self.active:
            yield
            return
        self.active = True
        self._failed = False
        self.cancellation = CancellationToken() if cancellable else None
        self._deferred_events = []
        self._close_after_cancel = False
        self.cancel_button.setVisible(cancellable)
        self.cancel_button.setEnabled(True)
        self.progress.setValue(0)
        self.percent.setText('0%')
        self.title.setText(title)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        self.setAccessibleName(title)
        guard = _InputGuard(self.window(), self)
        app = QApplication.instance()
        app.installEventFilter(guard)
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self._started = self._last_checkpoint = monotonic()
        self._update_elapsed()
        self.timer.start()
        token = _active_overlay.set(self)
        progress_token = progress_listener.set(self.set_progress)
        cancellation_token = active_cancellation.set(self.cancellation)
        try:
            app.processEvents()
            self.repaint()
            yield
        except BaseException:
            self._failed = True
            raise
        finally:
            # Finish queued canvas/layout paints before uncovering the result.
            if self.cancelled:
                self._failed = True
            if not self._failed:
                app.processEvents()
                self.progress.setValue(100)
                self.percent.setText('100%')
                self.detail.setText('Complete')
                # Give the completed bar one visible frame, keeping Qt responsive.
                loop = QEventLoop()
                QTimer.singleShot(100, loop.quit)
                loop.exec()
            self.timer.stop()
            self.cancel_button.hide()
            self.hide()
            self.active = False
            app.removeEventFilter(guard)
            guard.deleteLater()
            progress_listener.reset(progress_token)
            active_cancellation.reset(cancellation_token)
            _active_overlay.reset(token)
            if self._deferred_events or self._close_after_cancel:
                events = self._deferred_events
                self._deferred_events = []
                close_window = self.window() if self._close_after_cancel else None
                QTimer.singleShot(0, app, lambda: self._replay_interaction(events, close_window))


class _Task(QThread):
    progress = Signal(float, str)

    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.result = None
        self.error = None
        self.context = copy_context()

    def run(self):
        self.context.run(self._execute)

    def _execute(self):
        token = progress_listener.set(self.progress.emit)
        # A worker must never pump Qt events or touch an overlay.
        overlay_token = _active_overlay.set(None)
        try:
            check_cancelled()
            self.result = self.callback()
            check_cancelled()
        except BaseException as exc:
            self.error = exc
        finally:
            _active_overlay.reset(overlay_token)
            progress_listener.reset(token)


def run_worker(callback):
    """Run imports or data/figure preparation; callers create Qt widgets afterwards.

    Preserve the synchronous public workspace API while Qt timers and painting
    continue. All user interaction with the busy window is guarded by its overlay.
    """
    app = QApplication.instance()
    if app is None or QThread.currentThread() != app.thread():
        return callback()
    loop = QEventLoop()
    task = _Task(callback)
    listener = progress_listener.get()
    # A QObject slot ensures worker progress is delivered on the GUI thread.
    relay = _ProgressRelay(listener)
    task.progress.connect(relay.update, Qt.ConnectionType.QueuedConnection)
    task.finished.connect(loop.quit)
    # Dispatch input to the guard so clicks/shortcuts are discarded rather than
    # queued up and replayed against a different project or a completed plot.
    # Automatic cyclic GC runs in whichever Python thread crosses its allocation
    # threshold. During imports it can otherwise finalize unreachable GUI wrappers
    # on this worker, violating Qt thread affinity. Defer it until the GUI caller
    # has joined the worker; reference counting and explicit Qt deletion continue.
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        task.start()
        loop.exec()
    finally:
        # Never let a running QThread be destroyed during loop shutdown.
        task.wait()
        if gc_was_enabled:
            gc.enable()
    result, error = task.result, task.error
    # Release captured Qt owners on their GUI thread, including cancellation
    # tracebacks that would otherwise retain an entire workspace in a cycle.
    task.result = task.error = task.callback = task.context = None
    if isinstance(error, JobCancelled):
        error.__traceback__ = None
    task.deleteLater()
    relay.deleteLater()
    if error is not None:
        raise error
    return result


class _ProgressRelay(QObject):
    def __init__(self, listener):
        super().__init__()
        self.listener = listener

    @Slot(float, str)
    def update(self, value, detail):
        if self.listener is not None:
            self.listener(value, detail)


def run_figure_worker(figures, callback):
    """Keep live Qt canvases still while a worker styles or exports their figures."""
    from ..figure_canvas import PreviewCanvas
    canvases = [figure.canvas for figure in figures if isinstance(figure.canvas, PreviewCanvas)]
    for canvas in canvases:
        canvas._background_drawing = True
    try:
        return run_worker(callback)
    finally:
        for canvas in canvases:
            canvas._background_drawing = False
            canvas.apply_pending_resize()
            canvas.draw_idle()


def plot_loading(method):
    @wraps(method)
    def generate(self, *args, **kwargs):
        if getattr(self, '_plot_job_running', False):
            return
        if self.plot_loader.active:
            return method(self, *args, **kwargs)
        cancel = getattr(self, '_cancel_auto_update', None)
        if cancel is not None:
            cancel()
        self._generating_plot = True
        self._begin_plot_data_report()
        enabled = self.generate_button.isEnabled()
        self.generate_button.setEnabled(False)
        title = getattr(self, 'active_plot_title', self.diagram_combo)
        detail = title.text() if isinstance(title, QLabel) else title.currentText()
        try:
            with self.plot_loader.busy('Generating plot\u2026', detail, cancellable=True):
                report_progress(2, 'Preparing plot settings')
                result = method(self, *args, **kwargs)
                check_cancelled()
                if self.generated_plot is not None and self.plot_figures:
                    self._update_generated_filename()
                    self._attach_plot_data_report()
                    # Size the visible viewport before its final background draw.
                    QApplication.instance().processEvents()
                    if self.analysis_canvas is not None and self.analysis_canvas.figure.stale:
                        self.analysis_canvas.draw()
                    report_progress(98, 'Finishing preview')
                else:
                    self.plot_loader.fail()
        except JobCancelled:
            self._clear_analysis()
            self.generated_plot = None
            self.save_button.setEnabled(False)
            self._plot_data_report = None
            self._auto_update_error = True
            self.run_note.setText('Plot cancelled. Choose Generate when ready.')
            self.statusBar().showMessage('Plot cancelled.')
            result = None
        finally:
            self._generating_plot = False
            self.generate_button.setEnabled(enabled)
            self._update_generate_button(self.preview_tabs.currentIndex())
        if self.generated_plot is not None and self.plot_figures:
            self._show_missing_notice()
        return result
    return generate
