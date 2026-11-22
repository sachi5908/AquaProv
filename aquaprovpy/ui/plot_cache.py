"""Retain live results and canvases while navigating a module's plot library."""
from PySide6.QtCore import QSignalBlocker


class PlotCacheMixin:
    _CACHED_ATTRIBUTES = (
        'plot_figures', 'generated_plot', 'analysis_result', 'analysis_canvas',
        'analysis_scroll_area',
        'analysis_toolbar', 'figure_navigation', 'figure_is_map', 'rendered_style',
        'preview_pixmap', 'map_preview_pixmap', 'preview_tempdir', 'map_basemap',
        '_render_frame', '_render_config',
        '_plot_data_report',
    )
    _CACHED_TEXT = ('plot_details', 'map_details', 'map_status', 'result_notes')

    def _stash_plot(self):
        if not self.plot_figures or self.generated_plot is None:
            return
        state = {name: getattr(self, name, None) for name in self._CACHED_ATTRIBUTES}
        state['texts'] = {name: getattr(self, name).text() for name in self._CACHED_TEXT}
        state['labels'] = [self.figure_combo.itemText(i) for i in range(self.figure_combo.count())]
        state['figure_index'] = self.figure_combo.currentIndex()
        state['result_name'] = self.result_combo.currentText()
        state['pending'] = self._pending_auto_updates.copy()
        self._plot_cache[self._active_plot] = state
        if self.analysis_scroll_area is not None:
            self.analysis_scroll_area.save_state()
            state['viewport_state'] = dict(zoom=self.analysis_scroll_area.zoom,
                                           **self.analysis_scroll_area._scroll_position())
        for widget in (self.analysis_scroll_area, self.analysis_toolbar):
            if widget is not None:
                widget.hide()
                widget.parentWidget().layout().removeWidget(widget)
                widget.setParent(self)
        if self.map_basemap is not None:
            self.map_basemap.status_changed.disconnect(self._map_background_status)
        # The normal clear path must not dispose of the retained result.
        self.plot_figures = []
        self.analysis_result = self.analysis_canvas = self.analysis_toolbar = self.analysis_scroll_area = None
        self.figure_navigation = self.map_basemap = self.preview_tempdir = None

    def _restore_cached_plot(self, key):
        state = self._plot_cache.pop(key, None)
        if state is None:
            return False
        for name in self._CACHED_ATTRIBUTES:
            setattr(self, name, state[name])
        if self.analysis_scroll_area is not None:
            self.analysis_scroll_area.restore_state(state['viewport_state'])
        for name, text in state['texts'].items():
            getattr(self, name).setText(text)
        with QSignalBlocker(self.figure_combo):
            self.figure_combo.addItems(state['labels'])
            self.figure_combo.setCurrentIndex(state['figure_index'])
        target = self.map_interactive_panel if self.figure_is_map else self.interactive_panel
        for widget in (self.analysis_toolbar, self.analysis_scroll_area):
            if widget is not None:
                target.layout().addWidget(widget)
                widget.show()
        target.show()
        (self.map_image if self.figure_is_map else self.plot_image).hide()
        if self.analysis_result is not None:
            self.result_combo.addItems(list(self.analysis_result.tables))
            self.result_combo.setCurrentText(state['result_name'])
        self.tables_button.setEnabled(self.analysis_result is not None)
        self.save_button.setEnabled(True)
        self.reset_view_button.setEnabled(bool(self.figure_navigation and self.figure_navigation.axes))
        has_3d = any(hasattr(axis, 'view_init') for axis in self.analysis_canvas.figure.axes)
        for control in (self.elevation_spin, self.azimuth_spin, self.view_button):
            control.setEnabled(has_3d)
        if hasattr(self, 'replay_button'):
            self.replay_button.setEnabled(self._render_frame is not None and self.analysis_result is not None)
        if self.map_basemap is not None:
            self.map_basemap.status_changed.connect(self._map_background_status)
            self.map_basemap._report()
        self._pending_auto_updates = state['pending']
        self._refresh_legend_items()
        self.analysis_canvas.draw_idle()
        return True

    def _clear_plot_cache(self):
        import matplotlib.pyplot as plt
        for state in getattr(self, '_plot_cache', {}).values():
            if state['figure_navigation'] is not None:
                state['figure_navigation'].disconnect()
            if state['map_basemap'] is not None:
                state['map_basemap'].close()
                state['map_basemap'].deleteLater()
            for figure in state['plot_figures']:
                plt.close(figure)
            for name in ('analysis_scroll_area', 'analysis_toolbar'):
                if state[name] is not None:
                    state[name].deleteLater()
            if state['preview_tempdir'] is not None:
                state['preview_tempdir'].cleanup()
        self._plot_cache = {}
