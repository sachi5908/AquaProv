"""Module heading, typography controls and project actions."""

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)
from ..modules.registry import MODULES, module_for
from .artwork import BrandLogo
from .branding import brand_stylesheet
from .icons import decorate_button
from .sidebar_scroll import SidebarWheelFilter
from .theme import COMBO_ARROW


class ModuleCaption(QLabel):
    def __init__(self):
        super().__init__()
        self.caption = ''
        self.setObjectName('moduleCaption')
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setMinimumWidth(110)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_caption(self, text):
        self.caption = text
        self.setToolTip(text)
        self._refresh()

    def _refresh(self):
        self.setText(self.fontMetrics().elidedText(self.caption, Qt.TextElideMode.ElideRight, self.width()))

    def resizeEvent(self, event):
        self._refresh()
        super().resizeEvent(event)


class ModuleHeader(QFrame):
    def __init__(self, shell):
        super().__init__()
        self.setObjectName('moduleHeader')
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(brand_stylesheet("""
            QFrame#moduleHeader { background: white; border-bottom: 1px solid @border@; }
            QLabel#moduleCaption { font-size: 9pt; color: @muted@; }
            QLabel#activePlotTitle { font-size: 11pt; font-weight: 700; color: @ink@; }
            QPushButton#headerAction { font-size: 9pt; font-weight: 600; color: @ink@;
                background: @soft@; border: 1px solid transparent; border-radius: 5px; padding: 4px 10px; }
            QPushButton#headerAction:hover, QPushButton#headerAction:checked { background: @selected@; }
            QPushButton#headerAction:focus { border-color: @cyan@; }
            QPushButton#autoSave { background: @soft@; border: 1px solid transparent;
                border-radius: 5px; padding: 0; }
            QPushButton#autoSave:checked { background: @selected@; border-color: @teal@; }
            QPushButton#autoSave:hover { background: @hover@; }
            QComboBox#moduleSwitch { font-size: 9pt; color: @ink@; background: @soft@;
                border: 1px solid @border@; border-radius: 5px; padding: 4px 8px; }
            QComboBox#moduleSwitch::drop-down { border: 0; width: 24px; }
            QComboBox#moduleSwitch::down-arrow { image: url("__COMBO_ARROW__"); width: 10px; height: 10px; }
            QFrame#headerSeparator { background: @border@; border: 0; }
        """).replace('__COMBO_ARROW__', COMBO_ARROW))
        self._workspace = None
        self._module_key = 'groundwater'
        self._project_name = 'Untitled project'
        self._dirty = False
        self._narrow = None
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(14, 7, 14, 7)
        self._grid.setHorizontalSpacing(18)
        self._grid.setVerticalSpacing(6)
        self.identity = QWidget()
        identity = QHBoxLayout(self.identity)
        identity.setContentsMargins(0, 0, 0, 0)
        identity.setSpacing(14)
        self.logo = BrandLogo(124, 49)
        identity.addWidget(self.logo)
        self.caption_host = QWidget()
        self._caption_layout = QVBoxLayout(self.caption_host)
        self._caption_layout.setContentsMargins(0, 0, 0, 0)
        self._caption_layout.setSpacing(2)
        self.project = ModuleCaption()
        self._caption_layout.addWidget(self.project)
        identity.addWidget(self.caption_host, 1)
        self.tools = QWidget()
        tools = QHBoxLayout(self.tools)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(7)
        self.typography_host = QWidget()
        self._typography_layout = QHBoxLayout(self.typography_host)
        self._typography_layout.setContentsMargins(0, 0, 0, 0)
        tools.addWidget(self.typography_host)
        self.view_host = QWidget()
        self._view_layout = QHBoxLayout(self.view_host)
        self._view_layout.setContentsMargins(0, 0, 0, 0)
        tools.addWidget(self.view_host)
        separator = QFrame()
        separator.setObjectName('headerSeparator')
        separator.setFixedSize(1, 24)
        tools.addWidget(separator)
        self.actions = QWidget()
        actions = QHBoxLayout(self.actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(7)

        def action(text, icon, tooltip, callback, width=34):
            control = decorate_button(QPushButton(text), icon)
            control.setObjectName('headerAction')
            control.setFixedSize(width, 34)
            control.setToolTip(tooltip)
            control.setAccessibleName(tooltip)
            control.setCursor(Qt.CursorShape.PointingHandCursor)
            control.clicked.connect(callback)
            actions.addWidget(control)
            return control

        self.import_button = action('Load data', 'import', 'Import CSV or Excel (Ctrl+I)', shell.import_data, 104)
        self.save = action('', 'save', 'Save project (Ctrl+S)', shell.save_project)
        self.auto_save = decorate_button(QPushButton(), 'auto_save', size=22)
        self.auto_save.setObjectName('autoSave')
        self.auto_save.setFixedSize(34, 34)
        self.auto_save.setCheckable(True)
        self.auto_save.setChecked(True)
        self.auto_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_save.setAccessibleName('Auto save project')
        self.auto_save.setToolTip('Auto save project: save changes automatically. Click to toggle.')
        self.auto_save.toggled.connect(shell.set_auto_save_enabled)
        actions.addWidget(self.auto_save)
        self.modules = QComboBox()
        self.modules.setObjectName('moduleSwitch')
        self.modules.setAccessibleName('Switch analysis module')
        self.modules.setToolTip('Switch analysis module')
        for module in MODULES:
            self.modules.addItem(module.short_title, module.key)
        self.modules.setFixedSize(164, 34)
        self.modules.activated.connect(lambda index: shell.open_module(self.modules.itemData(index)))
        actions.addWidget(self.modules)
        self.fullscreen = action('', 'fullscreen', 'Full screen (F11)', shell.toggle_fullscreen)
        self.fullscreen.setCheckable(True)
        self.home = action('', 'home', 'Home (Alt+Home)', lambda: shell.show_page('home'))
        self._wheel_filter = SidebarWheelFilter(self)
        self._arrange()
        self._update_caption()

    def _arrange(self):
        narrow = self.width() < 1400
        if self._narrow == narrow:
            return
        self._narrow = narrow
        self._grid.removeWidget(self.identity)
        self._grid.removeWidget(self.tools)
        self._grid.removeWidget(self.actions)
        self._grid.addWidget(self.identity, 0, 0, 1, 2 if narrow else 1)
        self._grid.addWidget(self.tools, 1 if narrow else 0, 0 if narrow else 1, 1, 3 if narrow else 1,
                             alignment=Qt.AlignmentFlag.AlignRight)
        self._grid.addWidget(self.actions, 0, 2, alignment=Qt.AlignmentFlag.AlignRight)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 0)
        self._grid.setColumnStretch(2, 0)

    def resizeEvent(self, event):
        self._arrange()
        super().resizeEvent(event)

    def set_workspace(self, workspace):
        if self._workspace is workspace:
            return
        self.clear_workspace()
        self._workspace = workspace
        workspace.typography_dock.hide()
        for control, target in self._workspace_controls(workspace):
            workspace.typography_layout.removeWidget(control)
            target.insertWidget(0, control)
            control.show()
        workspace.quick_typography.sync()

    def clear_workspace(self):
        """Return controls to their owner before switching or deleting a workspace."""
        if self._workspace is not None:
            workspace, self._workspace = self._workspace, None
            for control, source in self._workspace_controls(workspace):
                source.removeWidget(control)
                workspace.typography_layout.addWidget(control, 1 if control is workspace.active_plot_title else 0)
                control.show()
            workspace.typography_dock.show()

    def _workspace_controls(self, workspace):
        return ((workspace.active_plot_title, self._caption_layout),
                (workspace.quick_typography, self._typography_layout),
                (workspace.view_tools, self._view_layout))

    def set_module(self, key):
        self._module_key = key
        with QSignalBlocker(self.modules):
            self.modules.setCurrentIndex(self.modules.findData(key))
        self._update_caption()

    def set_project(self, name, dirty):
        self._project_name, self._dirty = name, dirty
        self._update_caption()

    def _update_caption(self):
        text = f'{module_for(self._module_key).short_title} · {self._project_name}'
        self.project.set_caption(text + (' *' if self._dirty else ''))
        if self._dirty:
            self.project.setToolTip(text + ' — Unsaved changes')

    def set_fullscreen(self, enabled):
        self.fullscreen.setChecked(enabled)
        caption = 'Exit full screen (Esc)' if enabled else 'Full screen (F11)'
        self.fullscreen.setToolTip(caption)
        self.fullscreen.setAccessibleName(caption)
