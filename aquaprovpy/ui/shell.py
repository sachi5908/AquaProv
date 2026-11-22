"""Single-window application shell, navigation and project lifecycle."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget)

from ..core.projects import Project, RecentProjects
from ..core.catalog import APP_TITLE
from ..core.project_deletion import ProjectDeletion
from ..modules.registry import MODULES, load_workspace_class, module_for
from .artwork import BrandLogo, app_icon
from .about_page import AboutPage
from .branding import brand_stylesheet
from .home import button, label
from .projects_page import ProjectsPage
from .resources_page import ResourcesPage
from .home_dashboard import HomePage
from .project_dialog import NewProjectDialog
from .module_header import ModuleHeader
from .loading import BusyOverlay, loading_checkpoint, run_worker
from ..core.progress import progress_stage, report_progress
from .auto_save import AutoSaveController


# Native Qt controls read pointSize(); pixel-sized fonts return -1 there.
SHELL_STYLE = brand_stylesheet("""
QWidget { font-family: 'Segoe UI'; font-size: 9pt; color: @ink@; }
QMainWindow, QWidget#shellBody, QWidget#homeContent { background: @background@; }
QFrame#navigation { background: @navigation@; border: 0; }
QLabel#navCaption { color: @muted@; font-size: 10px; font-weight: 700; }
QLabel#navNote { color: @muted@; font-size: 11px; }
QPushButton#navButton { color: @ink@; background: transparent; text-align: left; border: 0; padding: 12px; border-radius: 7px; }
QPushButton#navButton:hover { background: @hover@; color: @navy@; }
QPushButton#navButton:checked { background: @selected@; color: @navy@; font-weight: 700; }
QFrame#topbar { background: white; border-bottom: 1px solid @border@; }
QFrame#moduleHeader { background: white; border-bottom: 1px solid @border@; }
QLabel#projectName { font-weight: 700; font-size: 13px; }
QLabel#pageTitle { font-size: 27px; font-weight: 700; }
QLabel#sectionTitle { font-size: 18px; font-weight: 700; }
QLabel#moduleTitle { font-size: 16px; font-weight: 700; }
QLabel#features { color: @ink@; line-height: 1.5; font-size: 11px; }
QLabel#muted { color: @muted@; font-size: 11px; }
QFrame#moduleCard { background: white; border: 1px solid @border@; border-radius: 12px; }
QPushButton { padding: 9px 14px; border: 1px solid @border@; border-radius: 7px; background: white; font-weight: 600; }
QPushButton:hover { background: @wash@; border-color: @cyan@; }
QPushButton#primary { background: @teal@; border-color: @teal@; color: white; }
QPushButton#primary:hover { background: @teal_hover@; }
QPushButton#secondary { background: @wash@; color: @ink@; border: 1px solid @border@; }
QPushButton:disabled { color: @disabled@; background: @wash@; }
QLineEdit, QComboBox, QTextEdit { background: white; padding: 8px; border: 1px solid @border@; border-radius: 6px; selection-background-color: @teal@; }
QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border-color: @teal@; }
QTreeWidget { background: white; border: 1px solid @border@; border-radius: 8px; outline: 0; }
QTreeWidget::item { padding: 12px 8px; border-bottom: 1px solid @wash@; }
QTreeWidget::item:selected { background: @selected@; color: @navy@; }
QHeaderView::section { background: @soft@; border: 0; padding: 10px; color: @muted@; font-size: 10px; font-weight: 700; }
QScrollArea { border: 0; background: @background@; }
QScrollBar:vertical { background: transparent; width: 9px; }
QScrollBar::handle:vertical { background: @border@; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QStatusBar { background: @wash@; color: @muted@; border-top: 1px solid @border@; }
QMenuBar, QMenu { background: white; color: @ink@; }
QMenu::item:selected { background: @selected@; }
""")


class AquaProvWindow(QMainWindow):
    def __init__(self, recents=None):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(app_icon())
        self.resize(1440, 940)
        self.setMinimumSize(1024, 700)
        self.recents = recents or RecentProjects()
        self.project = Project()
        self.workspaces = {}
        self.dirty = False
        self._syncing = False
        self._page = "home"
        self._module_mode = False
        self._opening_module = False
        self._home_window_state = Qt.WindowState.WindowNoState
        self._home_geometry = None
        self.setStyleSheet(SHELL_STYLE)
        self._build()
        self.project_loader = BusyOverlay(self.centralWidget(), 'projectLoader')
        self.auto_saver = AutoSaveController(self)
        self._build_shortcuts()
        self.refresh_projects()
        self.show_page("home")

    def _build(self):
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        self.home_navigation = sidebar
        sidebar.setObjectName("navigation")
        sidebar.setFixedWidth(214)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(18, 24, 18, 18)
        nav.setSpacing(6)
        self.logo = BrandLogo(178, 72)
        nav.addWidget(self.logo)
        nav.addWidget(label("WATER ANALYSIS SUITE", "navCaption"))
        nav.addSpacing(26)
        self.nav_buttons = {}
        def nav_button(key, text, callback):
            control = QPushButton(text)
            control.setObjectName("navButton")
            control.setCheckable(True)
            control.setCursor(Qt.CursorShape.PointingHandCursor)
            control.clicked.connect(callback)
            nav.addWidget(control)
            self.nav_buttons[key] = control
        nav_button("home", "Home", lambda: self.show_page("home"))
        nav_button("projects", "Projects", lambda: self.show_page("projects"))
        nav.addSpacing(22)
        nav.addWidget(label("ANALYSIS MODULES", "navCaption"))
        for module in MODULES:
            nav_button(module.key, module.short_title.replace("&", "&&"), lambda checked=False, key=module.key: self.open_module(key))
        nav.addStretch()
        nav.addWidget(label("One project. Connected analyses.", "navNote"))
        nav.addSpacing(14)
        nav_button("guide", "Support && Resources", lambda: self.show_page("guide"))
        nav_button("about", "About AquaProv", lambda: self.show_page("about"))
        layout.addWidget(sidebar)
        body = QWidget()
        body.setObjectName("shellBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        header = QFrame()
        self.home_header = header
        header.setObjectName("topbar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(28, 13, 24, 13)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        self.project_title = label("Start a project", "projectName")
        self.project_subtitle = label("Create, open or explore a module", "muted")
        titles.addWidget(self.project_title)
        titles.addWidget(self.project_subtitle)
        header_layout.addLayout(titles, 1)
        header_layout.addWidget(button("Import data…", self.import_data, icon='import'))
        self.save_project_button = button("Save project", self.save_project, True, icon='save')
        header_layout.addWidget(self.save_project_button)
        body_layout.addWidget(header)
        self.module_header = ModuleHeader(self)
        self.module_header.hide()
        body_layout.addWidget(self.module_header)
        self.stack = QStackedWidget()
        body_layout.addWidget(self.stack, 1)
        layout.addWidget(body, 1)
        self.setCentralWidget(central)
        self.home = HomePage(self)
        self.projects_page = ProjectsPage(self)
        self.resources_page = ResourcesPage(self)
        self.pages = {"home": self.home, "projects": self.projects_page,
                      "guide": self.resources_page, "about": self._about_page()}
        for page in self.pages.values():
            self.stack.addWidget(page)

    def _about_page(self):
        return AboutPage(self)

    def _build_shortcuts(self):
        for title, shortcut, callback in [("New project", "Ctrl+N", self.new_project), ("Open project", "Ctrl+O", self.open_project_dialog),
                ("Save project", "Ctrl+S", self.save_project), ("Save project as…", "Ctrl+Shift+S", lambda: self.save_project(save_as=True)),
                ("Import data", "Ctrl+I", self.import_data)]:
            action = QAction(title, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            self.addAction(action)
        for title, shortcut, callback in [("Home", "Alt+Home", lambda: self.show_page("home")), ("Generate", "F5", self.generate)]:
            action = QAction(title, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            self.addAction(action)
        self.fullscreen_action = QAction("Full screen", self)
        self.fullscreen_action.setShortcut("F11")
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(self.fullscreen_action)
        exit_fullscreen = QAction("Exit full screen", self)
        exit_fullscreen.setShortcut("Esc")
        exit_fullscreen.triggered.connect(self.exit_fullscreen)
        self.addAction(exit_fullscreen)

    def refresh_projects(self):
        entries = self.recents.load()
        self.home.projects.refresh(entries)
        self.projects_page.projects.refresh(entries)
        self._update_header()

    def _update_header(self):
        self.project_title.setText(self.project.name + ("  •  Unsaved changes" if self.dirty else ""))
        self.project_subtitle.setText(str(self.project.path) if self.project.path else "Explore a module, then save your project to keep the dataset and settings.")
        self.setWindowTitle(APP_TITLE if not self.project.path else f"{self.project.name} — {APP_TITLE}")
        self.module_header.set_project(self.project.name, self.dirty)

    def _select_nav(self, key):
        self._page = key
        for name, control in self.nav_buttons.items():
            control.setChecked(name == key)

    def show_page(self, key):
        self._set_module_mode(False)
        self.home_header.hide()
        self.statusBar().hide()
        if key == 'guide':
            self.resources_page.refresh()
        self.stack.setCurrentWidget(self.pages[key])
        self._select_nav(key)
        self.refresh_projects()
        self.statusBar().showMessage("Ready · Create or open a project, or choose an analysis module.")

    def _set_module_mode(self, enabled):
        if enabled == self._module_mode:
            return
        self._module_mode = enabled
        self.home_navigation.setVisible(not enabled)
        self.home_header.setVisible(not enabled)
        self.module_header.setVisible(enabled)
        self.statusBar().setVisible(not enabled)
        if enabled:
            self._home_window_state = self.windowState()
            self._home_geometry = self.saveGeometry()
            self._home_size = self.size()
            if not self.isFullScreen():
                self.setWindowState(Qt.WindowState.WindowMaximized)
        else:
            self.setWindowState(self._home_window_state)
            if self._home_geometry is not None:
                self.restoreGeometry(self._home_geometry)
                if self._home_window_state == Qt.WindowState.WindowNoState:
                    self.resize(self._home_size)
            self.module_header.set_fullscreen(False)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self._before_fullscreen = self.windowState()
            self.showFullScreen()
            self.module_header.set_fullscreen(True)

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.setWindowState(getattr(self, '_before_fullscreen', Qt.WindowState.WindowMaximized))
            self.module_header.set_fullscreen(False)

    def mark_dirty(self):
        if not self._syncing:
            self.dirty = True
            self._update_header()
            self.auto_saver.changed()

    def set_auto_save_enabled(self, enabled):
        self.auto_saver.set_enabled(enabled)
        self.module_header.auto_save.setToolTip('Auto save project (' + ('on' if enabled else 'off') + ')')

    def open_module(self, key):
        if self._opening_module:
            return None
        self._opening_module = True
        try:
            with self.project_loader.busy('Opening module\u2026', module_for(key).short_title):
                return self._open_module(key)
        finally:
            self._opening_module = False

    def _open_module(self, key):
        if key not in self.workspaces:
            self.statusBar().showMessage(f"Opening {module_for(key).title}…")
            workspace = None
            try:
                with progress_stage(0, 22, 'Loading module resources'):
                    workspace_class = run_worker(lambda: load_workspace_class(key))
                # QWidget construction belongs on the GUI thread; its shared
                # builders yield at loading checkpoints to animate the overlay.
                with progress_stage(22, 58, 'Building workspace controls'):
                    workspace = workspace_class()
                loading_checkpoint()
                if self.project.dataset is not None:
                    with progress_stage(58, 82, 'Preparing project data'):
                        workspace.accept_project_data(self.project.dataset, self.project.source)
                    loading_checkpoint()
                with progress_stage(82, 94, 'Restoring module settings'):
                    workspace.restore_state(self.project.modules.get(key, {}))
                loading_checkpoint()
                workspace.folder_edit.setText(str(self.project.export_directory(key)))
                workspace.data_changed.connect(lambda frame, source, module=key: self._dataset_changed(module, frame, source))
                workspace.settings_changed.connect(self.mark_dirty)
                self.stack.addWidget(workspace)
                self.workspaces[key] = workspace
            except Exception as exc:
                if workspace is not None:
                    workspace.close()
                    workspace.deleteLater()
                self.project_loader.fail()
                QMessageBox.critical(self, "Module could not open", str(exc))
                return None
        report_progress(96, 'Displaying workspace')
        self._set_module_mode(True)
        self.module_header.set_module(key)
        self.module_header.set_workspace(self.workspaces[key])
        self.stack.setCurrentWidget(self.workspaces[key])
        self._select_nav(key)
        if self.project.last_module != key:
            self.project.last_module = key
            if self.project.path or self.project.dataset is not None:
                self.mark_dirty()
        self.statusBar().showMessage(f"{module_for(key).title} · Dataset shared across modules; settings saved per module.")
        if self.project.path:
            self._remember(opened=True)
        return self.workspaces[key]

    def _dataset_changed(self, key, frame, source):
        self._syncing = True
        try:
            self.project.dataset = run_worker(lambda: frame.copy(deep=True))
            self.project.source = source.copy()
            from ..modules.plot_profiles import clear_dataset_assumptions
            for state in self.project.modules.values():
                clear_dataset_assumptions(state)
            for other_key, workspace in self.workspaces.items():
                if other_key == key:
                    continue
                state = workspace.capture_state()
                clear_dataset_assumptions(state)
                workspace.accept_project_data(frame, source)
                workspace.restore_state(state)
        finally:
            self._syncing = False
        self.mark_dirty()

    def import_data(self):
        workspace = self.open_module(self._page if self._page in self.workspaces else self.project.last_module)
        if workspace:
            workspace.load_data()

    def generate(self):
        if self._page in self.workspaces:
            self.workspaces[self._page].generate()

    def _collect_state(self):
        for key, workspace in self.workspaces.items():
            self.project.modules[key] = workspace.capture_state()

    def _remember(self, *, opened=False):
        try:
            self.recents.remember(self.project, opened=opened)
        except OSError as exc:
            self.statusBar().showMessage(f"The recent-project list could not be updated: {exc}")
        self.refresh_projects()

    def save_project(self, checked=False, *, save_as=False, path=None):
        self.auto_saver.stop()
        destination = Path(path) if path else self.project.path
        if save_as or destination is None:
            filename, _ = QFileDialog.getSaveFileName(self, "Save AquaProv project", str(destination or Path.home() / "Documents" / "Untitled.aquaprov"), "AquaProv project (*.aquaprov)")
            if not filename:
                if self.dirty and self.project.auto_save:
                    self.auto_saver.changed()
                return False
            destination = Path(filename)
        if destination.suffix.lower() not in (".aquaprov", ".aquaprov"):
            destination = destination.with_suffix(".aquaprov")
        try:
            self._collect_state()
            if self.project.name == "Untitled project":
                self.project.name = destination.stem
            project = self.project
            with self.project_loader.busy('Saving project…', 'Writing dataset and settings'):
                with progress_stage(0, 95, 'Writing dataset and settings'):
                    run_worker(lambda: project.save(destination))
            for key, workspace in self.workspaces.items():
                workspace.folder_edit.setText(str(self.project.export_directory(key)))
            self.dirty = False
            self.auto_saver.error = None
            self.module_header.auto_save.setToolTip(
                'Auto save project (' + ('on' if self.project.auto_save else 'off') + ')')
            self._remember()
            self.statusBar().showMessage(f"Project saved · {destination}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Project could not be saved", str(exc))
            return False

    def _can_replace_project(self):
        if not self.dirty:
            return True
        if self.project.auto_save and self.auto_saver.save_now():
            return True
        choice = QMessageBox.question(self, "Save project changes?", f"Save changes to {self.project.name} before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        return self.save_project() if choice == QMessageBox.StandardButton.Save else True

    def _clear_workspaces(self):
        self.auto_saver.stop()
        self.module_header.clear_workspace()
        for workspace in self.workspaces.values():
            workspace.blockSignals(True)
            self.stack.removeWidget(workspace)
            workspace.close()
            workspace.deleteLater()
        self.workspaces.clear()

    def delete_project(self, path):
        try:
            deletion = ProjectDeletion.prepare(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Project could not be deleted', str(exc))
            return False
        name = next((entry['name'] for entry in self.recents.load()
                     if Path(entry['path']).resolve() == deletion.path), deletion.path.stem)
        active = self.project.path is not None and deletion.includes(self.project.path)
        warning = QMessageBox(self)
        warning.setWindowTitle('Delete project?')
        warning.setIcon(QMessageBox.Icon.Warning)
        warning.setTextFormat(Qt.TextFormat.PlainText)
        warning.setText(f'Permanently delete "{name}"?')
        if deletion.directory is not None:
            detail = ('The entire project folder will be deleted, including its saved data, '
                      'settings, exported figures and all other files inside it.\n\n'
                      f'{deletion.directory}')
        elif deletion.path.exists():
            detail = (f'This project file and its saved data and settings will be deleted:\n\n{deletion.path}'
                      '\n\nThis is a shared or unrecognized folder. Other files and shared exports will be kept.')
        else:
            detail = (f'The project file is missing:\n\n{deletion.path}'
                      '\n\nIts recent-project entry will be removed. Other files will be kept.')
        detail += '\n\nOriginal input files and exports outside the project folder will be kept.'
        if active:
            detail += '\nThe open project will close and its unsaved changes will be discarded.'
        warning.setInformativeText(detail + '\n\nThis cannot be undone.')
        delete = warning.addButton('Delete project', QMessageBox.ButtonRole.DestructiveRole)
        cancel = warning.addButton(QMessageBox.StandardButton.Cancel)
        warning.setDefaultButton(cancel)
        warning.setEscapeButton(cancel)
        warning.exec()
        confirmed = warning.clickedButton() == delete
        warning.deleteLater()
        if not confirmed:
            return False
        if active:
            # Finish an in-flight write before deleting its destination.
            self.auto_saver.stop()
        try:
            deletion.delete()
        except (OSError, ValueError) as exc:
            if active and not self.project.path.exists():
                self._reset_deleted_project()
            self.refresh_projects()
            QMessageBox.warning(self, 'Project could not be fully deleted',
                f'{exc}\n\nSome files may remain. Close any files in use and try again. '
                'The project remains in the list so you can retry.')
            return False
        if active:
            self._reset_deleted_project()
        try:
            self.recents.forget(deletion.path, directory=deletion.directory)
        except OSError as exc:
            QMessageBox.warning(self, 'Project list could not be updated',
                f'The project files were deleted, but the recent-project entry could not be removed:\n{exc}')
        self.refresh_projects()
        return True

    def _reset_deleted_project(self):
        self._clear_workspaces()
        self.project = Project()
        self.dirty = False
        self.auto_saver.reset()
        self.show_page('projects')

    def set_project(self, project, *, module=None):
        with self.project_loader.busy('Opening project\u2026', project.name):
            self._set_project(project, module=module)

    def _set_project(self, project, *, module=None):
        from ..core.project_migrations import separate_statistics
        project = separate_statistics(project)
        self._clear_workspaces()
        self.project = project
        self.dirty = False
        self.auto_saver.reset()
        self.open_module(module or project.last_module)
        self._update_header()

    def new_project(self, checked=False, *, module=None):
        if not self._can_replace_project():
            return
        dialog = NewProjectDialog(self, module=module)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_project(dialog.project)

    def open_project_dialog(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open AquaProv project", str(Path.home() / "Documents"), "AquaProv project (*.aquaprov *.aquastat)")
        if filename:
            self.open_project(filename)

    def resume_project(self, path, module=None):
        """Resume a recent project without replacing its live, possibly unsaved workspace."""
        if self.project_loader.active:
            return False
        target = Path(path).expanduser().resolve()
        if self.project.path and self.project.path.resolve() == target:
            with self.project_loader.busy('Opening project\u2026', self.project.name):
                return self.open_module(module or self.project.last_module) is not None
        if module is None:
            known_modules = {item.key for item in MODULES}
            for entry in self.recents.load():
                if Path(entry['path']).expanduser().resolve() == target:
                    remembered = entry.get('module')
                    if remembered in known_modules:
                        module = remembered
                    break
        return self.open_project(path, module=module)

    def open_project(self, path, module=None):
        if self.project_loader.active:
            return False
        with self.project_loader.busy('Opening project\u2026', Path(path).stem):
            return self._open_project(path, module=module)

    def _open_project(self, path, module=None):
        try:
            if module is not None:
                module_for(module)
            with progress_stage(0, 15, 'Reading saved project'):
                project = run_worker(lambda: Project.load(path))
        except Exception as exc:
            self.project_loader.fail()
            QMessageBox.critical(self, "Project could not be opened", str(exc))
            return False
        if not self._can_replace_project():
            self.project_loader.fail()
            return False
        with progress_stage(15, 100, 'Restoring project'):
            self.set_project(project, module=module)
        return True

    def closeEvent(self, event):
        if not self._can_replace_project():
            event.ignore()
            return
        self.auto_saver.stop()
        self.module_header.clear_workspace()
        for workspace in self.workspaces.values():
            workspace.close()
        event.accept()
