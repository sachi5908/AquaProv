"""Figure navigation, panel toggles and camera controls for module toolbars."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QFrame, QHBoxLayout, QMenu, QPushButton,
    QSpinBox, QToolButton, QWidget, QWidgetAction,
)

from .branding import brand_stylesheet
from .icons import action_icon
from .sidebar_scroll import SidebarWheelFilter
from .theme import COMBO_ARROW, SPIN_UP_ARROW


class ModuleViewTools(QFrame):
    def __init__(self, workspace):
        super().__init__()
        self.setObjectName('moduleViewTools')
        self.setStyleSheet(brand_stylesheet("""
            QFrame#moduleViewTools { background: transparent; border: 0; }
            QPushButton, QToolButton { font-size: 9pt; color: @ink@;
                background: @soft@; border: 1px solid transparent; border-radius: 5px; padding: 0; }
            QPushButton:hover, QToolButton:hover { background: @selected@; }
            QPushButton:focus, QToolButton:focus { border-color: @cyan@; }
            QToolButton#autoUpdate:checked { background: @selected@; border-color: @teal@; }
            QToolButton#autoUpdate:checked:hover { background: @hover@; border-color: @teal@; }
            QToolButton#viewOptions { background: white; border: 1px solid @border@;
                border-radius: 6px; padding: 0 18px 0 7px; }
            QToolButton#viewOptions:hover, QToolButton#viewOptions:focus { background: @wash@; border-color: @cyan@; }
            QToolButton#viewOptions:pressed { background: @selected@; border-color: @teal@; }
            QToolButton#viewOptions::menu-indicator { image: url("__COMBO_ARROW__"); width: 12px; height: 12px;
                subcontrol-origin: border; subcontrol-position: right center; right: 6px; }
            QComboBox, QSpinBox { font-size: 9pt; color: @ink@; background: @soft@;
                border: 1px solid @border@; border-radius: 5px; padding: 4px 6px; }
            QComboBox::drop-down { border: 0; width: 22px; }
            QComboBox::down-arrow { image: url("__COMBO_ARROW__"); width: 9px; height: 9px; }
            QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 16px; border: 0; }
            QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 16px; border: 0; }
            QSpinBox::up-arrow { image: url("__SPIN_UP__"); width: 8px; height: 8px; }
            QSpinBox::down-arrow { image: url("__COMBO_ARROW__"); width: 8px; height: 8px; }
            QMenu { background: white; color: @ink@; font-size: 9pt; }
            QMenu#viewOptionsMenu { border: 1px solid @border@; border-radius: 7px; padding: 4px; }
            QMenu::item { padding: 7px 24px; }
            QMenu::item:selected { background: @selected@; }
            QLabel { color: @ink@; font-size: 9pt; }
        """).replace('__COMBO_ARROW__', COMBO_ARROW).replace('__SPIN_UP__', SPIN_UP_ARROW))
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        workspace.figure_combo = QComboBox()
        workspace.figure_combo.setFixedSize(150, 34)
        workspace.figure_combo.setAccessibleName('Displayed figure')
        workspace.figure_combo.currentIndexChanged.connect(workspace._switch_figure)
        row.addWidget(workspace.figure_combo)
        # Model notifications still arrive when rendering blocks combo signals.
        self.figure_combo = workspace.figure_combo
        for signal in (self.figure_combo.model().rowsInserted, self.figure_combo.model().rowsRemoved,
                       self.figure_combo.model().modelReset, self.figure_combo.currentTextChanged):
            signal.connect(self._sync_figures)
        self._sync_figures()
        reset = workspace._make_reset_view_button()
        reset.setText('')
        reset.setFixedSize(34, 34)
        reset.setAccessibleName('Reset view')
        reset.setToolTip('Reset view: restore original plot bounds and 3D camera')
        row.addWidget(reset)
        self.view = QToolButton()
        self.view.setObjectName('viewOptions')
        self.view.setIcon(action_icon('tabs'))
        self.view.setIconSize(QSize(20, 20))
        self.view.setFixedSize(54, 34)
        self.view.setCursor(Qt.CursorShape.PointingHandCursor)
        self.view.setToolTip('View: show or hide panels and adjust the 3D camera')
        self.view.setAccessibleName('View options')
        self.view.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu = QMenu(self)
        self.menu.setObjectName('viewOptionsMenu')
        self.menu.setMinimumWidth(190)
        self.view.setMenu(self.menu)
        row.addWidget(self.view)
        workspace.auto_update_check = QToolButton()
        workspace.auto_update_check.setObjectName('autoUpdate')
        workspace.auto_update_check.setIcon(action_icon('auto_update'))
        workspace.auto_update_check.setIconSize(QSize(22, 22))
        workspace.auto_update_check.setFixedSize(34, 34)
        workspace.auto_update_check.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        workspace.auto_update_check.setCursor(Qt.CursorShape.PointingHandCursor)
        workspace.auto_update_check.setCheckable(True)
        workspace.auto_update_check.setChecked(True)
        workspace.auto_update_check.setAccessibleName('Auto update plot')
        workspace.auto_update_check.setToolTip(
            'Auto update: refresh the plot after edits. Click to toggle; turn off to apply edits with Generate.')
        row.addWidget(workspace.auto_update_check)
        for name, label in (('library_toggle', 'Plot library'), ('settings_toggle', 'Settings inspector')):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(True)
            self.menu.addAction(action)
            setattr(workspace, name, action)

        self.camera_menu = self.menu.addMenu(action_icon('three_d'), '3D camera')
        self.camera_menu.menuAction().setVisible(workspace.module_key == 'three_d')
        workspace.camera_panel = QWidget()
        camera = QFormLayout(workspace.camera_panel)
        camera.setContentsMargins(12, 10, 12, 10)
        workspace.elevation_spin, workspace.azimuth_spin = QSpinBox(), QSpinBox()
        workspace.elevation_spin.setRange(-90, 90)
        workspace.elevation_spin.setValue(30)
        workspace.azimuth_spin.setRange(-180, 180)
        workspace.azimuth_spin.setValue(-60)
        for label, spin in (('Elevation', workspace.elevation_spin), ('Azimuth', workspace.azimuth_spin)):
            spin.setFixedSize(90, 34)
            spin.setSuffix('\N{DEGREE SIGN}')
            spin.setAccessibleName('3D camera ' + label.lower())
            camera.addRow(label, spin)
        workspace.view_button = QPushButton('Apply view')
        workspace.view_button.setMinimumHeight(32)
        workspace.view_button.clicked.connect(workspace._apply_camera)
        camera.addRow(workspace.view_button)
        camera_action = QWidgetAction(self.camera_menu)
        camera_action.setDefaultWidget(workspace.camera_panel)
        self.camera_menu.addAction(camera_action)
        self.camera_menu.aboutToShow.connect(workspace._sync_view_controls)
        for control in (workspace.elevation_spin, workspace.azimuth_spin, workspace.view_button):
            control.setEnabled(False)
        self._wheel_filter = SidebarWheelFilter(self)

    def _sync_figures(self, *_):
        self.figure_combo.setVisible(self.figure_combo.count() > 1)
        self.figure_combo.setToolTip('Displayed figure: ' + self.figure_combo.currentText())
