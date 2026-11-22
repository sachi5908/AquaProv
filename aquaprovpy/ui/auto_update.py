"""Debounced plot updates shared by every analysis module."""
from PySide6.QtCore import QSignalBlocker, QTimer
from PySide6.QtWidgets import QApplication


class AutoUpdateMixin:
    def initialize_auto_update(self):
        self._pending_auto_updates = set()
        self._auto_updating = False
        self._auto_update_timer = QTimer(self)
        self._auto_update_timer.setSingleShot(True)
        self._auto_update_timer.timeout.connect(self._run_auto_update)
        self.auto_update_check.toggled.connect(self._auto_update_toggled)

    def _auto_update_kind(self, control):
        ignored = {getattr(self, name, None) for name in (
            'auto_update_check', 'diagram_search', 'sheet_combo', 'folder_edit',
            'name_edit', 'format_combo', 'dpi_spin', 'results_format_combo',
            'figure_combo', 'result_combo')}
        # Plot navigation itself decides whether a retained result needs work.
        ignored.update(getattr(self, name) for name in getattr(self, '_route_names', ()))
        style = set(self.style_controls.values()) | {self.quick_typography}
        camera = {self.elevation_spin, self.azimuth_spin}
        # Spin boxes and editable combos also contain line edits.
        while control is not None and control is not self:
            if control in ignored:
                return None
            if control in style:
                return 'style'
            if control in camera:
                return 'camera'
            control = control.parent()
        return 'render'

    def _queue_auto_update(self, kind='render'):
        if (kind is None or not hasattr(self, '_auto_update_timer')
                or self._restoring or getattr(self, '_switching_plot', False)
                or getattr(self, '_updating_data', False)
                or getattr(self, '_generating_plot', False) or self._auto_updating):
            return
        self._pending_auto_updates.add(kind)
        if self.auto_update_check.isChecked() and self.isVisible():
            self._auto_update_timer.start(350 if 'render' in self._pending_auto_updates else 120)

    def _cancel_auto_update(self):
        if hasattr(self, '_auto_update_timer'):
            self._auto_update_timer.stop()
            self._pending_auto_updates.clear()

    def _auto_update_toggled(self, enabled):
        self.settings_changed.emit()
        self._refresh_auto_update_note()
        if enabled:
            if self._pending_auto_updates or not self.plot_figures:
                self._queue_auto_update('style')
        else:
            self._auto_update_timer.stop()

    def _refresh_auto_update_note(self):
        self.run_note.setText(
            'Auto update is on. Load data or edit settings to refresh this plot.'
            if self.auto_update_check.isChecked() else
            'Auto update is off. Edit settings, then Generate to update this plot.')

    def _run_auto_update(self):
        if not self.auto_update_check.isChecked() or not self.isVisible():
            return
        if self.data is None or self.data.empty:
            return
        window = self.window()
        loader = getattr(window, 'project_loader', None)
        if (self._restoring or getattr(self, '_updating_data', False)
                or getattr(self, '_switching_plot', False)
                or getattr(self, '_generating_plot', False) or self.plot_loader.active
                or (loader is not None and loader.active)
                or QApplication.activeModalWidget() is not None):
            self._auto_update_timer.start(100)
            return
        changes = self._pending_auto_updates.copy()
        self._pending_auto_updates.clear()
        if not changes:
            return
        self._auto_updating = True
        self._auto_update_error = False
        try:
            if 'render' in changes or not self.plot_figures:
                self.generate()
            else:
                if 'style' in changes:
                    self.apply_plot_style()
                if 'camera' in changes:
                    self._apply_camera()
        except Exception as exc:
            self._report_plot_error('Could not update plot', exc)
        finally:
            self._auto_updating = False
            if not self._auto_update_error:
                self._refresh_auto_update_note()

    def capture_state(self):
        state = super().capture_state()
        state['auto_update'] = self.auto_update_check.isChecked()
        return state

    def restore_state(self, state):
        self._cancel_auto_update()
        with QSignalBlocker(self.auto_update_check):
            self.auto_update_check.setChecked(state.get('auto_update', True) is not False)
        super().restore_state(state)
        self._queue_auto_update()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, '_auto_update_timer'):
            if not self.plot_figures:
                self._queue_auto_update()
            elif self._pending_auto_updates:
                self._queue_auto_update('style')

    def hideEvent(self, event):
        if hasattr(self, '_auto_update_timer'):
            self._auto_update_timer.stop()
        super().hideEvent(event)
