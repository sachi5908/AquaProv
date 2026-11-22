"""Compact module launcher and recent-project rows modeled on FracSTAT Home."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
    QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from .home import label
from .icons import ICON_ROOT, action_icon, module_icon
from .sidebar_scroll import SidebarWheelFilter
from ..modules.registry import MODULES, module_for


HOME_STYLE = """
QWidget#homeContent { background: #f5f7fc; }
QLabel#homeWelcome { font-size: 20pt; font-weight: 700; color: #25364c; }
QLabel#homeSection { font-size: 11pt; font-weight: 600; color: #25364c; }
QLabel#homeMuted { color: #7b8ca9; font-size: 9pt; }
QFrame#moduleTray, QFrame#recentPanel { background: white; border: 1px solid #dfe6f2; border-radius: 16px; }
QToolButton#homeModule { border: 1px solid transparent; border-radius: 12px; background: transparent; color: #163455; font-size: 9pt; font-weight: 600; padding: 6px; }
QToolButton#homeModule:hover, QToolButton#homeModule:focus { background: #f5f8fd; border-color: #dce5f4; }
QToolButton#homeModule:pressed { background: #e9f1fb; }
QPushButton#homeAction, QToolButton#openProject { background: white; border: 1px solid #d7e2f2; border-radius: 8px; color: #345d8a; padding: 8px 13px; font-size: 9pt; }
QPushButton#homeAction:hover, QToolButton#openProject:hover { background: #f0f5fd; }
QToolButton#openProject::menu-indicator { image: url("__COMBO_ARROW__"); width: 9px; height: 9px; subcontrol-origin: padding; subcontrol-position: right center; right: 9px; }
QToolButton#openProject { padding-right: 24px; }
QLineEdit#projectSearch, QComboBox#projectSort { background: white; border: 1px solid #d7e2f2; border-radius: 8px; padding: 8px; color: #345d8a; font-size: 9pt; }
QComboBox#projectSort::drop-down { border: 0; width: 22px; }
QComboBox#projectSort::down-arrow { image: url("__COMBO_ARROW__"); width: 9px; height: 9px; }
QScrollArea#projectRows, QWidget#projectRowsContent { background: transparent; border: 0; }
QFrame#projectRow { background: transparent; border: 1px solid transparent; border-radius: 10px; }
QFrame#projectRow[available="true"]:hover { background: #f0f5fd; }
QFrame#projectRow[available="true"]:focus { background: #f0f5fd; border-color: #91b8da; }
QPushButton#projectNameLink { background: transparent; border: 0; padding: 0; text-align: left; color: #193658; font-weight: 600; font-size: 9pt; }
QPushButton#projectNameLink:hover { color: #2870da; }
QLabel#projectPath, QLabel#projectDate { color: #8293af; font-size: 8pt; }
QPushButton#homeLink { border: 0; background: transparent; color: #7c3aed; padding: 2px 0; font-size: 9pt; text-align: left; }
QPushButton#homeLink:hover { color: #5b21b6; text-decoration: underline; }
""".replace('__COMBO_ARROW__', (ICON_ROOT.parent / 'dropdown.svg').as_posix())


def project_date(entry):
    try:
        return datetime.fromisoformat(entry['modified'].replace('Z', '+00:00')).astimezone()
    except (KeyError, TypeError, ValueError):
        return None


class ElidedLabel(QLabel):
    def __init__(self, text, name):
        super().__init__()
        self.full_text = text
        self.setObjectName(name)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setToolTip(text)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def resizeEvent(self, event):
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideMiddle, self.width()))
        super().resizeEvent(event)


class RecentProjectRow(QFrame):
    open_requested = Signal(str)
    open_in_requested = Signal(str, str)

    def __init__(self, entry):
        super().__init__()
        self.entry = entry
        self.setObjectName('projectRow')
        self.setFixedHeight(78)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 10, 16, 10)
        layout.setSpacing(18)
        folder = QLabel()
        folder.setPixmap(action_icon('open', '#4b8bfa').pixmap(28, 28))
        layout.addWidget(folder)
        details = QVBoxLayout()
        details.setSpacing(5)
        self.name_button = QPushButton(entry['name'].replace('&', '&&'))
        self.name_button.setObjectName('projectNameLink')
        self.name_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.name_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.name_button.setToolTip(entry['name'])
        self.name_button.clicked.connect(lambda: self.open_requested.emit(entry['path']))
        details.addWidget(self.name_button)
        missing = not Path(entry['path']).is_file()
        self.available = not missing
        self._press_position = None
        self.setProperty('available', self.available)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        if self.available:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        path = str(Path(entry['path']).parent)
        details.addWidget(ElidedLabel(('File moved or missing · ' if missing else '') + path, 'projectPath'))
        layout.addLayout(details, 1)
        try:
            module = module_for(entry.get('module', 'groundwater'))
        except StopIteration:
            module = module_for('groundwater')
        self.setAccessibleName(f"Open {entry['name']} in {module.short_title}")
        self.setToolTip('Click to resume the last-used module' if self.available else 'Project file moved or missing')
        metadata = QVBoxLayout()
        metadata.setSpacing(6)
        badge = QHBoxLayout()
        badge.addStretch()
        glyph = QLabel()
        glyph.setPixmap(module_icon(module.key).pixmap(18, 18))
        badge.addWidget(glyph)
        name = label(module.short_title)
        name.setStyleSheet(f'color: {module.accent}; font-size: 8pt;')
        badge.addWidget(name)
        metadata.addLayout(badge)
        date = project_date(entry)
        timestamp = label(date.strftime('%Y-%m-%d %H:%M') if date else '', 'projectDate')
        timestamp.setAlignment(Qt.AlignmentFlag.AlignRight)
        metadata.addWidget(timestamp)
        layout.addLayout(metadata)
        self.open_button = QToolButton()
        self.open_button.setObjectName('openProject')
        self.open_button.setText('Open in')
        self.open_button.setToolTip('Choose a module to open this project')
        self.open_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self.open_button)
        for target in MODULES:
            action = menu.addAction(module_icon(target.key), target.short_title.replace('&', '&&'))
            action.triggered.connect(lambda checked=False, key=target.key: self.open_in_requested.emit(entry['path'], key))
        self.open_button.setMenu(menu)
        self.open_button.setEnabled(not missing)
        self.name_button.setEnabled(not missing)
        layout.addWidget(self.open_button)

    def mousePressEvent(self, event):
        if self.available and event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.position().toPoint()
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        start, self._press_position = self._press_position, None
        if self.available and start is not None and event.button() == Qt.MouseButton.LeftButton:
            end = event.position().toPoint()
            event.accept()
            if self.rect().contains(end) and (end - start).manhattanLength() < QApplication.startDragDistance():
                self.open_requested.emit(self.entry['path'])
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self.available and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            event.accept()
            if not event.isAutoRepeat():
                self.open_requested.emit(self.entry['path'])
            return
        super().keyPressEvent(event)


class RecentProjectList(QWidget):
    open_requested = Signal(str)
    open_in_requested = Signal(str, str)
    summary_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.entries, self.rows = [], []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        filters = QHBoxLayout()
        filters.setSpacing(10)
        self.search = QLineEdit()
        self.search.setObjectName('projectSearch')
        self.search.setPlaceholderText('Find a project by name, location or folder...')
        self.search.setClearButtonEnabled(True)
        self.search.addAction(action_icon('search', '#8293af'), QLineEdit.ActionPosition.LeadingPosition)
        filters.addWidget(self.search, 1)
        self.sort = QComboBox()
        self.sort.setObjectName('projectSort')
        for title, value in [('Newest first', 'newest'), ('Oldest first', 'oldest'), ('Name A–Z', 'name')]:
            self.sort.addItem(title, value)
        self.sort.setFixedWidth(124)
        filters.addWidget(self.sort)
        layout.addLayout(filters)
        panel = QFrame()
        panel.setObjectName('recentPanel')
        panel.setMinimumHeight(210)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(2, 8, 2, 8)
        scroll = QScrollArea()
        scroll.setObjectName('projectRows')
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName('projectRowsContent')
        self.row_layout = QVBoxLayout(content)
        self.row_layout.setContentsMargins(0, 0, 0, 0)
        self.row_layout.setSpacing(0)
        scroll.setWidget(content)
        panel_layout.addWidget(scroll)
        self.empty = label('No recent projects yet.', 'homeMuted')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(self.empty)
        self.scroll = scroll
        layout.addWidget(panel, 1)
        self.search.textChanged.connect(self.render)
        self.sort.currentIndexChanged.connect(self.render)

    def refresh(self, entries):
        self.entries = list(entries)
        self.render()

    def render(self, *_):
        while self.row_layout.count():
            item = self.row_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        query = self.search.text().strip().casefold()
        entries = [entry for entry in self.entries if query in ' '.join(
            str(entry.get(key, '')) for key in ('name', 'location', 'path')).casefold()]
        if self.sort.currentData() == 'name':
            entries.sort(key=lambda entry: entry['name'].casefold())
        else:
            entries.sort(key=lambda entry: project_date(entry).timestamp() if project_date(entry) else 0,
                         reverse=self.sort.currentData() == 'newest')
        self.rows = []
        for entry in entries:
            row = RecentProjectRow(entry)
            row.open_requested.connect(self.open_requested)
            row.open_in_requested.connect(self.open_in_requested)
            self.row_layout.addWidget(row)
            self.rows.append(row)
        self.row_layout.addStretch()
        self.scroll.setVisible(bool(entries))
        self.empty.setVisible(not entries)
        self.empty.setText('No projects match your search.' if query else 'No recent projects yet.')
        count = len(entries)
        summary = f'{count} project' + ('' if count == 1 else 's')
        if query:
            summary = f'{count} of {len(self.entries)} projects'
        self.summary_changed.emit(summary)


class HomePage(QScrollArea):
    def __init__(self, shell):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(HOME_STYLE)
        content = QWidget()
        content.setObjectName('homeContent')
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 20, 30, 18)
        layout.setSpacing(12)
        welcome = QVBoxLayout()
        welcome.setSpacing(0)
        welcome.addWidget(label('Welcome to AquaProv', 'homeWelcome'))
        welcome.addWidget(label('Start something new. Pick up where you left off.', 'homeMuted'))
        layout.addLayout(welcome)
        layout.addSpacing(12)
        layout.addWidget(label('New project', 'homeSection'))
        tray = QFrame()
        tray.setObjectName('moduleTray')
        tray.setFixedHeight(150)
        modules = QHBoxLayout(tray)
        modules.setContentsMargins(20, 14, 20, 14)
        self.module_buttons = {}
        for module in MODULES:
            tile = QToolButton()
            tile.setObjectName('homeModule')
            tile.setText(module.short_title.replace('&', '&&'))
            tile.setIcon(module_icon(module.key))
            tile.setIconSize(QSize(64, 64))
            tile.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            tile.setCursor(Qt.CursorShape.PointingHandCursor)
            tile.setToolTip(f'Create a {module.short_title} project')
            tile.clicked.connect(lambda checked=False, key=module.key: shell.new_project(module=key))
            modules.addWidget(tile, 1)
            self.module_buttons[module.key] = tile
        layout.addWidget(tray)
        layout.addSpacing(6)
        heading = QHBoxLayout()
        heading.addWidget(label('Recent projects', 'homeSection'))
        self.recent_count = label('0 projects', 'homeMuted')
        heading.addWidget(self.recent_count)
        heading.addStretch()
        open_project = QPushButton('Open another project')
        open_project.setObjectName('homeAction')
        open_project.setIcon(action_icon('open', '#4b8bfa'))
        open_project.setIconSize(QSize(14, 14))
        open_project.clicked.connect(shell.open_project_dialog)
        heading.addWidget(open_project)
        layout.addLayout(heading)
        self.projects = RecentProjectList()
        self.projects.open_requested.connect(shell.resume_project)
        self.projects.open_in_requested.connect(shell.resume_project)
        self.projects.summary_changed.connect(self.recent_count.setText)
        layout.addWidget(self.projects, 1)
        footer = QHBoxLayout()
        def link(text, callback):
            control = QPushButton(text)
            control.setObjectName('homeLink')
            control.setCursor(Qt.CursorShape.PointingHandCursor)
            control.clicked.connect(callback)
            footer.addWidget(control)
        link('View all projects →', lambda: shell.show_page('projects'))
        footer.addStretch()
        link('Documentation', lambda: shell.show_page('guide'))
        footer.addSpacing(18)
        link('About AquaProv', lambda: shell.show_page('about'))
        layout.addLayout(footer)
        self.setWidget(content)
        self._wheel_filter = SidebarWheelFilter(self)
