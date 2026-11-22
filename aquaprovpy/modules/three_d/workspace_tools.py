"""Shared 3D camera toolbar and canvas lifecycle for analytical workspaces."""
from PySide6.QtCore import QSignalBlocker

from .view_tools import ThreeDViewTools


class ThreeDWorkspaceToolsMixin:
    three_d_projection_name = 'projection_combo'

    def initialize_three_d_tools(self):
        # Install after connect_settings: toolbar actions only change the camera.
        self.three_d_tools = ThreeDViewTools(self)
        self._three_d_tools_layout.insertWidget(0, self.three_d_tools)

    def _build_workspace_tools(self, layout):
        super()._build_workspace_tools(layout)
        self._three_d_tools_layout = layout

    def _stop_rotation(self):
        if hasattr(self, 'three_d_tools'):
            self.three_d_tools.stop()

    def _dispose_figure_view(self):
        if hasattr(self, 'three_d_tools'):
            self.three_d_tools.unbind()
        super()._dispose_figure_view()

    def _switch_figure(self, index):
        super()._switch_figure(index)
        if hasattr(self, 'three_d_tools'):
            self.three_d_tools.bind(self.analysis_canvas)

    def _stash_plot(self):
        if hasattr(self, 'three_d_tools'):
            self.three_d_tools.unbind()
        super()._stash_plot()

    def _restore_cached_plot(self, key):
        restored = super()._restore_cached_plot(key)
        if restored:
            self.three_d_tools.bind(self.analysis_canvas)
            self._sync_view_controls()
        return restored

    def _sync_view_controls(self):
        super()._sync_view_controls()
        if hasattr(self, 'three_d_tools'):
            self.three_d_tools.sync()
            if self.three_d_tools.axes():
                with QSignalBlocker(getattr(self, self.three_d_projection_name)):
                    getattr(self, self.three_d_projection_name).setCurrentIndex(int(self.three_d_tools.orthographic.isChecked()))

    def _apply_camera(self):
        self._stop_rotation()
        super()._apply_camera()
        self._sync_view_controls()

    def reset_view(self):
        self._stop_rotation()
        super().reset_view()

    def _save_current_figures(self):
        self._stop_rotation()
        return super()._save_current_figures()

    def hideEvent(self, event):
        self._stop_rotation()
        super().hideEvent(event)

    def _camera_for_generation(self):
        if self.analysis_canvas is None:
            return None
        axis = next((axis for axis in self.analysis_canvas.figure.axes if hasattr(axis, 'view_init')), None)
        if axis is None:
            return None
        # Mouse rotation has fractional angles and roll that the two integer
        # camera controls cannot represent. Preserve them unless a control changed.
        angles = [value if round(value) == control.value() else control.value()
                  for value, control in ((axis.elev, self.elevation_spin), (axis.azim, self.azimuth_spin))]
        return (*angles, axis.roll)

    def _apply_generated_camera(self, camera):
        if camera is None:
            self._apply_camera()
        elif self.analysis_canvas is not None:
            figure = self.analysis_canvas.figure
            for axis in figure.axes:
                if hasattr(axis, 'view_init'):
                    axis.view_init(elev=camera[0], azim=camera[1], roll=camera[2])
                    initial = getattr(figure, '_aquaprov_initial_views', {}).get(axis)
                    if initial is not None:
                        initial.update(elev=camera[0], azim=camera[1], roll=camera[2])
            self.analysis_canvas.draw_idle()
        self._sync_view_controls()

