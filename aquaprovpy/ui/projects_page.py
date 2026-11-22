"""Searchable saved-project table with resume and per-module actions."""
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMenu, QPushButton, QSizePolicy, QToolButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from ..modules.registry import MODULES
from .branding import brand_stylesheet
from .home import button, label
from .home_dashboard import ElidedLabel
from .icons import action_icon, module_icon
from .sidebar_scroll import SidebarWheelFilter
from .theme import COMBO_ARROW

PROJECTS_STYLE = brand_stylesheet("""
QWidget#projectsPage { background: @background@; }
QFrame#projectsHeader, QFrame#projectFilters { background: white; border: 0; border-radius: 8px; }
QLabel#projectsTitle { font-size: 20pt; font-weight: 700; }
QLabel#projectsSubtitle { font-size: 9pt; color: @muted@; }
QLabel#projectCount { background: @wash@; color: @teal@; padding: 9px 12px; border-radius: 7px; font-size: 9pt; font-weight: 600; }
QLineEdit#savedProjectSearch, QComboBox#savedProjectSort { font-size: 9pt; background: white; padding: 8px; border: 1px solid @border@; border-radius: 6px; }
QComboBox#savedProjectSort::drop-down { width: 24px; border: 0; }
QComboBox#savedProjectSort::down-arrow { image: url("__ARROW__"); width: 10px; height: 10px; }
QTreeWidget#savedProjectTable { background: white; alternate-background-color: @soft@; border: 1px solid @border@; border-radius: 8px; font-size: 9pt; }
QTreeWidget#savedProjectTable::item { padding: 0; border: 0; border-bottom: 1px solid @border@; }
QTreeWidget#savedProjectTable::item:hover, QTreeWidget#savedProjectTable::item:selected { background: @wash@; color: @ink@; }
QTreeWidget#savedProjectTable QHeaderView::section { background: @wash@; color: @muted@; font-size: 9pt; font-weight: 600; border: 0; padding: 12px 10px; }
QWidget#projectNameCell, QWidget#projectActions { background: transparent; }
QPushButton#savedProjectName { background: transparent; border: 0; color: @ink@; text-align: left; padding: 0; font-size: 9pt; font-weight: 600; }
QPushButton#savedProjectName:hover { color: @cyan@; }
QLabel#savedProjectPath { font-size: 8pt; color: @muted@; }
QPushButton#projectResume, QToolButton#projectOpenIn { background: @wash@; color: @ink@; border: 1px solid @border@; border-radius: 6px; font-size: 9pt; font-weight: 600; padding: 6px 10px; }
QPushButton#projectResume:hover, QPushButton#projectResume:focus,
QToolButton#projectOpenIn:hover, QToolButton#projectOpenIn:focus { background: @selected@; border-color: @cyan@; }
QPushButton#projectResume:disabled, QToolButton#projectOpenIn:disabled { background: @soft@; color: @disabled@; border-color: @border@; }
QToolButton#projectOpenIn { padding-right: 26px; }
QToolButton#projectOpenIn::menu-indicator { image: url("__ARROW__"); width: 12px; height: 12px; subcontrol-origin: border; subcontrol-position: right center; right: 7px; }
QPushButton#projectRemove { background: #fff0f1; border: 1px solid #f0c2c8; border-radius: 6px; padding: 4px; }
QPushButton#projectRemove:hover, QPushButton#projectRemove:focus { background: #ffdade; border-color: #c44958; }
""").replace('__ARROW__', COMBO_ARROW)


def entry_date(entry, key):
    value = entry.get(key)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone()
    except ValueError:
        return None


def opened_text(entry):
    opened = entry_date(entry, 'last_opened')
    date = opened or entry_date(entry, 'modified')
    if date is None:
        return 'Not recorded'
    if opened is None:
        detail = 'Last saved'
    else:
        minutes = max(0, int((datetime.now(timezone.utc) - opened).total_seconds() // 60))
        if minutes < 1:
            detail = 'Just now'
        elif minutes < 60:
            detail = f'{minutes} min ago'
        elif minutes < 1440:
            hours = minutes // 60
            detail = f'{hours} hour' + ('s' if hours != 1 else '') + ' ago'
        else:
            days = minutes // 1440
            detail = f'{days} day' + ('s' if days != 1 else '') + ' ago'
    return date.strftime('%Y-%m-%d %H:%M') + '\n' + detail


class ProjectActions(QWidget):
    def __init__(self, entry, table):
        super().__init__()
        self.setObjectName('projectActions')
        self.path = entry['path']
        available = Path(self.path).is_file()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)
        self.module_group = QWidget()
        modules = QHBoxLayout(self.module_group)
        modules.setContentsMargins(0, 0, 0, 0)
        modules.setSpacing(6)
        self.module_buttons = {}
        for module in MODULES:
            title = {'maps': 'Maps', 'three_d': '3D'}.get(module.key, module.short_title)
            control = QPushButton(title)
            control.setFixedHeight(34)
            control.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            control.setCursor(Qt.CursorShape.PointingHandCursor)
            control.setToolTip(f'Open in {module.short_title}')
            hover = QColor(module.accent).darker(112).name()
            control.setStyleSheet(f'QPushButton {{ background: {module.accent}; color: white; border: 1px solid {module.accent}; border-radius: 6px; padding: 6px 10px; font-size: 9pt; font-weight: 600; }}'
                                 f'QPushButton:hover, QPushButton:focus {{ background: {hover}; border-color: {hover}; }}'
                                 'QPushButton:disabled { background: #e7eef2; color: #829aa8; }')
            control.setEnabled(available)
            control.clicked.connect(lambda checked=False, key=module.key: table.open_in_requested.emit(self.path, key))
            modules.addWidget(control)
            self.module_buttons[module.key] = control
        layout.addWidget(self.module_group)
        self.open_in = QToolButton()
        self.open_in.setObjectName('projectOpenIn')
        self.open_in.setText('Open in')
        self.open_in.setFixedHeight(34)
        self.open_in.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.open_in.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.open_in.setToolTip('Choose a module to open this project')
        self.open_in.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.open_in.setEnabled(available)
        self.open_in.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self.open_in)
        for module in MODULES:
            action = menu.addAction(module_icon(module.key), module.short_title.replace('&', '&&'))
            action.triggered.connect(lambda checked=False, key=module.key: table.open_in_requested.emit(self.path, key))
        self.open_in.setMenu(menu)
        layout.addWidget(self.open_in)
        self.resume = QPushButton('Resume')
        self.resume.setObjectName('projectResume')
        self.resume.setFixedHeight(34)
        self.resume.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.resume.setEnabled(available)
        self.resume.setToolTip('Resume the last-used module')
        self.resume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.resume.clicked.connect(lambda: table.open_requested.emit(self.path))
        layout.addWidget(self.resume)
        self.remove = QPushButton()
        self.remove.setObjectName('projectRemove')
        self.remove.setFixedSize(34, 34)
        self.remove.setIcon(action_icon('delete', tint='#9f2334'))
        self.remove.setIconSize(QSize(16, 16))
        self.remove.setToolTip('Delete project and its files')
        self.remove.setAccessibleName('Delete project')
        self.remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove.clicked.connect(lambda: table.remove_requested.emit(self.path))
        layout.addWidget(self.remove)
        layout.addStretch()

    def set_compact(self, compact):
        self.module_group.setVisible(not compact)
        self.open_in.setVisible(compact)

    def required_width(self, compact):
        """Reserve the natural button widths, including inherited font metrics."""
        self.ensurePolished()
        primary = self.open_in if compact else self.module_group
        margins = self.layout().contentsMargins()
        return (primary.sizeHint().width() + self.resume.sizeHint().width()
                + self.remove.width() + margins.left() + margins.right()
                + 2 * self.layout().spacing())


class ProjectTable(QWidget):
    open_requested = Signal(str)
    open_in_requested = Signal(str, str)
    remove_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.entries, self.row_actions, self.name_buttons = [], {}, {}
        self._compact = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        filters = QFrame()
        filters.setObjectName('projectFilters')
        controls = QHBoxLayout(filters)
        controls.setContentsMargins(10, 10, 10, 10)
        self.count = label('All projects  0', 'projectCount')
        controls.addWidget(self.count)
        controls.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName('savedProjectSearch')
        self.search.setPlaceholderText('Search projects...')
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(160)
        self.search.setMaximumWidth(280)
        self.search.addAction(action_icon('search'), QLineEdit.ActionPosition.LeadingPosition)
        controls.addWidget(self.search, 1)
        self.sort = QComboBox()
        self.sort.setObjectName('savedProjectSort')
        self.sort.setFixedWidth(158)
        self.sort.setAccessibleName('Sort projects')
        for title, key in (('Last opened', 'opened'), ('Last saved', 'modified'), ('Name A-Z', 'name')):
            self.sort.addItem(title, key)
        controls.addWidget(self.sort)
        layout.addWidget(filters)
        self.tree = QTreeWidget()
        self.tree.setObjectName('savedProjectTable')
        self.tree.setHeaderLabels(['Project name', 'Location / Site', 'Last opened', 'Actions'])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tree.header().setMinimumSectionSize(80)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            self.tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        self.tree.itemClicked.connect(self._open_item)
        self.tree.itemActivated.connect(self._open_item)
        layout.addWidget(self.tree, 1)
        self.empty = label('No saved projects yet. Import a project or create a new one.', 'projectsSubtitle')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty)
        self.search.textChanged.connect(self.render)
        self.sort.currentIndexChanged.connect(self.render)
        self._wheel_filter = SidebarWheelFilter(self)
        self._arrange()

    def _open_item(self, item, column=0):
        if column != 3 and item.data(0, Qt.ItemDataRole.UserRole + 1):
            self.open_requested.emit(item.data(0, Qt.ItemDataRole.UserRole))

    def refresh(self, entries):
        self.entries = list(entries)
        self.render()

    def render(self, *_):
        self.tree.clear()
        self.row_actions, self.name_buttons = {}, {}
        query = self.search.text().strip().casefold()
        entries = [entry for entry in self.entries if query in ' '.join(str(entry.get(key, '')) for key in ('name', 'path', 'location')).casefold()]
        if self.sort.currentData() == 'name':
            entries.sort(key=lambda entry: entry['name'].casefold())
        else:
            key = 'last_opened' if self.sort.currentData() == 'opened' else 'modified'
            def date_value(entry):
                date = entry_date(entry, key) or entry_date(entry, 'modified')
                return date.timestamp() if date else 0
            entries.sort(key=date_value, reverse=True)
        for entry in entries:
            path = entry['path']
            available = Path(path).is_file()
            item = QTreeWidgetItem(['', entry.get('location') or '\N{EM DASH}', opened_text(entry), ''])
            item.setData(0, Qt.ItemDataRole.UserRole, path)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, available)
            item.setSizeHint(0, QSize(0, 76))
            item.setToolTip(0, path)
            self.tree.addTopLevelItem(item)
            name_cell = QWidget()
            name_cell.setObjectName('projectNameCell')
            names = QVBoxLayout(name_cell)
            names.setContentsMargins(12, 12, 10, 12)
            names.setSpacing(5)
            name = QPushButton(entry['name'].replace('&', '&&'))
            name.setObjectName('savedProjectName')
            name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            name.setToolTip('Resume ' + entry['name'])
            name.setCursor(Qt.CursorShape.PointingHandCursor)
            name.setEnabled(available)
            name.clicked.connect(lambda checked=False, target=path: self.open_requested.emit(target))
            names.addWidget(name)
            names.addWidget(ElidedLabel(str(Path(path).parent) if available else 'File moved or missing', 'savedProjectPath'))
            self.tree.setItemWidget(item, 0, name_cell)
            actions = ProjectActions(entry, self)
            actions.set_compact(self._compact)
            self.tree.setItemWidget(item, 3, actions)
            self.row_actions[path], self.name_buttons[path] = actions, name
        self.count.setText(f'All projects  {len(self.entries)}' if not query else f'{len(entries)} of {len(self.entries)} projects')
        self.empty.setVisible(not entries)
        self.empty.setText('No projects match your search.' if query else 'No saved projects yet. Import a project or create a new one.')
        self._arrange()

    def _arrange(self):
        if not self.row_actions:
            return
        expanded_width = max(actions.required_width(False) for actions in self.row_actions.values())
        # Leave space for a readable project name and the metadata columns.
        # Reserve the scrollbar too, so adding more rows cannot clip actions.
        available_width = self.width() - 2 * self.tree.frameWidth() - self.tree.verticalScrollBar().sizeHint().width()
        compact = available_width < 240 + 125 + 156 + expanded_width
        self._compact = compact
        actions_width = max(actions.required_width(compact) for actions in self.row_actions.values())
        for column, width in ((1, 125), (2, 156), (3, actions_width)):
            if self.tree.columnWidth(column) != width:
                self.tree.setColumnWidth(column, width)
        for actions in self.row_actions.values():
            actions.set_compact(compact)

    def resizeEvent(self, event):
        self._arrange()
        super().resizeEvent(event)


class ProjectsPage(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.setObjectName('projectsPage')
        self.setStyleSheet(PROJECTS_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 24)
        layout.setSpacing(20)
        header = QFrame()
        header.setObjectName('projectsHeader')
        heading = QHBoxLayout(header)
        heading.setContentsMargins(16, 14, 16, 14)
        titles = QVBoxLayout()
        titles.addWidget(label('Projects', 'projectsTitle'))
        titles.addWidget(label('Manage your saved projects and open them in any AquaProv module.', 'projectsSubtitle'))
        heading.addLayout(titles, 1)
        self.import_button = button('Import Project', shell.open_project_dialog, icon='open')
        self.new_button = button('New Project', shell.new_project, True, icon='new')
        heading.addWidget(self.import_button)
        heading.addWidget(self.new_button)
        layout.addWidget(header)
        self.projects = ProjectTable()
        self.projects.open_requested.connect(shell.resume_project)
        self.projects.open_in_requested.connect(shell.resume_project)
        self.projects.remove_requested.connect(shell.delete_project)
        layout.addWidget(self.projects, 1)
