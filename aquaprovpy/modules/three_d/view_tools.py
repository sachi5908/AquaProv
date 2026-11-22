"""Camera controls for the 3D workspace."""

from time import monotonic

import numpy as np
from matplotlib.ticker import NullLocator
from PySide6.QtCore import QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QMenu, QToolButton, QWidget

from ...ui.branding import brand_stylesheet
from ...ui.icons import module_icon
from ...ui.theme import COMBO_ARROW


VIEWS = {
    '3D / isometric': (35.26438968, -45., None),
    'XY / top': (90., -90., 'z'),
    'XZ / front': (0., -90., 'y'),
    'YZ / side': (0., 0., 'x'),
}


def camera_preset(axis):
    for name, (elevation, azimuth, hidden) in VIEWS.items():
        angles = np.array([axis.elev - elevation, axis.azim - azimuth, axis.roll])
        if np.allclose((angles + 180) % 360 - 180, 0., atol=1e-6):
            if np.isinf(axis._focal_length):
                return name
    return 'Custom view'


def plane_decorations(axis):
    """Hide the collapsed axis's ticks/label, restoring them after rotation.

    Axes3D draws each axis even when Axis.visible is false, so suppress its
    ticks and individual artists instead. Preserve locators and source labels.
    State belongs to the axes so cached plots retain their own plane views.
    """
    hidden = VIEWS.get(camera_preset(axis), (None, None, None))[2]
    previous = getattr(axis, '_aquaprov_plane_axis', None)
    if previous is not None and previous[0] == hidden:
        return False
    if previous is None and hidden is None:
        return False
    if previous is not None:
        dimension, major, minor, visibility = previous
        component = getattr(axis, dimension + 'axis')
        component.set_major_locator(major)
        component.set_minor_locator(minor)
        for artist, visible in visibility:
            artist.set_visible(visible)
        axis._aquaprov_plane_axis = None
        for part, padding in axis._aquaprov_plane_padding:
            part.labelpad = padding
        axis._aquaprov_plane_padding = []
    if hidden is not None:
        component = getattr(axis, hidden + 'axis')
        # Axis visibility also excludes this empty axis from tight export bounds.
        artists = (component, component.label, component.offsetText, component.line)
        axis._aquaprov_plane_axis = (hidden, component.get_major_locator(),
            component.get_minor_locator(), [(artist, artist.get_visible()) for artist in artists])
        component.set_major_locator(NullLocator())
        component.set_minor_locator(NullLocator())
        for artist in artists:
            artist.set_visible(False)
        # Axes3D's label offsets shrink in an edge-on view. Leave room between
        # the remaining labels and their ticks, including coordinate decimals.
        axis._aquaprov_plane_padding = [(part, part.labelpad) for part in (axis.xaxis, axis.yaxis, axis.zaxis)
                                       if part is not component]
        for part, padding in axis._aquaprov_plane_padding:
            part.labelpad = padding + 10
    return True


class ThreeDViewTools(QWidget):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.canvas = None
        self.callbacks = []
        self.degrees_per_second = 18.
        self.direction = 1
        self._last_tick = 0.
        self.timer = QTimer(self)
        self.timer.setInterval(60)
        self.timer.timeout.connect(self._rotate)
        workspace.view_tools.camera_menu.aboutToShow.connect(self.stop)
        self.setObjectName('threeDViewTools')
        self.setStyleSheet(brand_stylesheet('''
            QWidget#threeDViewTools { background: @soft@; border-radius: 5px; }
            QToolButton { color: @ink@; background: white; border: 1px solid @border@;
                border-radius: 4px; padding: 5px; font-size: 9pt; }
            QToolButton:checked { background: @selected@; border-color: @cyan@; }
            QToolButton:disabled { color: #85949e; }
            QToolButton#threeDViewOptions { border-radius: 6px; padding: 0 18px 0 6px;
                font-weight: 600; }
            QToolButton#threeDViewOptions:hover, QToolButton#threeDViewOptions:focus {
                background: @wash@; border-color: @cyan@; }
            QToolButton#threeDViewOptions:pressed, QToolButton#threeDViewOptions:open {
                background: @selected@; border-color: @teal@; }
            QToolButton#threeDViewOptions:disabled {
                color: @disabled@; background: @soft@; border-color: @border@; }
            QToolButton#threeDViewOptions::menu-indicator { image: url("__COMBO_ARROW__");
                width: 12px; height: 12px; subcontrol-origin: border;
                subcontrol-position: right center; right: 5px; }
            QMenu { background: white; color: @ink@; font-size: 9pt;
                border: 1px solid @border@; border-radius: 7px; padding: 4px; }
            QMenu::item { padding: 7px 24px; border-radius: 4px; }
            QMenu::item:selected { background: @wash@; color: @teal@; }
            QMenu::separator { height: 1px; background: @border@; margin: 4px 8px; }
        ''').replace('__COMBO_ARROW__', COMBO_ARROW))
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 4, 4, 4)
        row.setSpacing(4)
        self.view = QComboBox()
        self.view.addItems([*VIEWS, 'Custom view'])
        self.view.model().item(self.view.count() - 1).setEnabled(False)
        self.view.setMinimumContentsLength(7)
        self.view.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.view.setAccessibleName('3D viewing plane')
        self.view.setToolTip('Choose a camera view. Plane views use orthographic projection; coordinates stay unchanged.')
        self.view.activated.connect(self._select_view)
        row.addWidget(self.view, 1)
        self.rotate = QToolButton()
        self.rotate.setText('Auto rotate')
        self.rotate.setCheckable(True)
        self.rotate.setAccessibleName('Auto rotate 3D plot')
        self.rotate.setToolTip('Rotate the preview. Stops on dragging, changing views or export. Images save the current angle.')
        self.rotate.toggled.connect(self._toggle_rotation)
        row.addWidget(self.rotate)
        self.options = QToolButton()
        self.options.setObjectName('threeDViewOptions')
        self.options.setText('View')
        self.options.setIcon(module_icon('three_d'))
        self.options.setIconSize(QSize(16, 16))
        self.options.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.options.setMinimumHeight(34)
        self.options.setCursor(Qt.CursorShape.PointingHandCursor)
        self.options.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.options.setAccessibleName('3D view options')
        self.options.setToolTip('3D view options: projection, rotation speed and camera angles')
        self.options.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.options)
        menu.setMinimumWidth(230)
        self.options.setMenu(menu)
        self.orthographic = menu.addAction('Orthographic projection')
        self.orthographic.setCheckable(True)
        self.orthographic.toggled.connect(self._projection_changed)
        speed_menu = menu.addMenu('Rotation speed')
        self.speed_group = QActionGroup(self)
        for label, speed in [('Slow (9\N{DEGREE SIGN}/s)', 9.), ('Normal (18\N{DEGREE SIGN}/s)', 18.),
                             ('Fast (36\N{DEGREE SIGN}/s)', 36.)]:
            action = speed_menu.addAction(label)
            action.setCheckable(True)
            action.setData(speed)
            self.speed_group.addAction(action)
            action.setChecked(speed == self.degrees_per_second)
        self.speed_group.triggered.connect(self._speed_changed)
        self.reverse = menu.addAction('Reverse rotation')
        self.reverse.setCheckable(True)
        self.reverse.toggled.connect(self._reverse_changed)
        menu.addSeparator()
        menu.addAction('Exact camera angles\u2026', self._show_camera)
        menu.addAction('Reset view', workspace.reset_view)
        row.addWidget(self.options)
        self.setEnabled(False)

    def axes(self):
        return [] if self.canvas is None else [axis for axis in self.canvas.figure.axes if hasattr(axis, 'view_init')]

    def bind(self, canvas):
        self.unbind()
        self.canvas = canvas
        if canvas is not None:
            self.callbacks = [canvas.mpl_connect(event, callback) for event, callback in (
                ('button_press_event', self._pressed), ('draw_event', self._drawn))]
        self.sync()

    def unbind(self):
        self.stop()
        if self.canvas is not None:
            for callback in self.callbacks:
                self.canvas.mpl_disconnect(callback)
        self.callbacks = []
        self.canvas = None
        self.setEnabled(False)

    def stop(self):
        self.timer.stop()
        with QSignalBlocker(self.rotate):
            self.rotate.setChecked(False)

    def sync(self):
        axes = self.axes()
        self.setEnabled(bool(axes))
        if not axes:
            return
        axis = axes[0]
        with QSignalBlocker(self.view), QSignalBlocker(self.orthographic):
            self.view.setCurrentText(camera_preset(axis))
            self.orthographic.setChecked(bool(np.isinf(axis._focal_length)))
        changed = False
        for axis in axes:
            changed |= plane_decorations(axis)
        if changed:
            self.canvas.draw_idle()

    def _changed(self):
        self.workspace._sync_view_controls()
        self.workspace.settings_changed.emit()
        self.canvas.draw_idle()

    def _select_view(self, index):
        name = self.view.itemText(index)
        if name not in VIEWS or not self.axes():
            return
        self.stop()
        elevation, azimuth, _ = VIEWS[name]
        for axis in self.axes():
            axis.view_init(elev=elevation, azim=azimuth, roll=0)
            axis.set_proj_type('ortho')
        self._changed()

    def _projection_changed(self, orthographic):
        if not self.axes():
            return
        self.stop()
        for axis in self.axes():
            axis.set_proj_type('ortho' if orthographic else 'persp')
        self._changed()

    def _toggle_rotation(self, enabled):
        if not enabled or not self.axes():
            self.stop()
            return
        # Rotating a top view around its vertical axis would not reveal depth.
        for axis in self.axes():
            if np.isclose(axis.elev % 90, 0.):
                axis.view_init(elev=30, azim=-60, roll=0)
        self._last_tick = monotonic()
        self.timer.start()
        self._changed()

    def _rotate(self):
        if (not self.axes() or not self.workspace.isVisible()
                or getattr(self.workspace, '_generating_plot', False) or self.workspace.plot_loader.active):
            self.stop()
            return
        now = monotonic()
        # Avoid a large jump after a busy renderer or a blocked event loop.
        elapsed = min(now - self._last_tick, .25)
        self._last_tick = now
        for axis in self.axes():
            azimuth = (axis.azim + elapsed * self.degrees_per_second * self.direction + 180) % 360 - 180
            axis.view_init(elev=axis.elev, azim=azimuth, roll=axis.roll)
        self._changed()

    def _speed_changed(self, action):
        self.degrees_per_second = action.data()
        self._last_tick = monotonic()

    def _reverse_changed(self, reverse):
        self.direction = -1 if reverse else 1
        self._last_tick = monotonic()

    def _pressed(self, event):
        self.stop()

    def _drawn(self, event):
        self.sync()

    def _show_camera(self):
        self.stop()
        self.workspace.view_tools.camera_menu.popup(self.options.mapToGlobal(self.options.rect().bottomLeft()))
