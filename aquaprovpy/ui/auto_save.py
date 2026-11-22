"""Debounced, atomic project saving without interrupting editing."""
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

from PySide6.QtCore import QObject, QSignalBlocker, QThread, QTimer
from PySide6.QtWidgets import QApplication


class _SaveTask(QThread):
    def __init__(self, project, destination, parent):
        super().__init__(parent)
        self.project, self.destination = project, destination
        self.error = None

    def run(self):
        try:
            self.project.save(self.destination)
        except Exception as exc:
            self.error = exc


class AutoSaveController(QObject):
    def __init__(self, shell):
        super().__init__(shell)
        self.shell = shell
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._scheduled_save)
        self.task = None
        self.revision = 0
        self.error = None

    def changed(self):
        self.revision += 1
        if self.shell.project.auto_save:
            self.timer.start(1000)

    def set_enabled(self, enabled):
        self.shell.project.auto_save = enabled
        self.shell.mark_dirty()
        if not enabled:
            self.timer.stop()

    def reset(self):
        self.stop()
        self.error = None
        with QSignalBlocker(self.shell.module_header.auto_save):
            self.shell.module_header.auto_save.setChecked(self.shell.project.auto_save)
        self.shell.module_header.auto_save.setToolTip(
            'Auto save project (' + ('on' if self.shell.project.auto_save else 'off') + ')')

    def stop(self):
        self.timer.stop()
        if self.task is not None:
            self.task.wait()
            self._finished()
        self.timer.stop()

    def _scheduled_save(self):
        shell = self.shell
        if not shell.dirty or not shell.project.auto_save:
            return
        if (self.task is not None or shell.project_loader.active
                or QApplication.activeModalWidget() is not None
                or any(getattr(w, '_generating_plot', False) or getattr(w, '_updating_data', False)
                       for w in shell.workspaces.values())):
            self.timer.start(200)
            return
        self._start()

    def _start(self):
        shell = self.shell
        self.error = None
        try:
            shell._collect_state()
            owner = shell.project
            snapshot = replace(owner, modules=deepcopy(owner.modules), source=deepcopy(owner.source),
                               dataset=owner.dataset.copy(deep=True) if owner.dataset is not None else None)
            destination = owner.path
            if destination is None:
                destination = shell.recents.path.parent / 'autosaved_projects' / uuid4().hex / 'Untitled.aquaprov'
            self.owner, self.saved_revision = owner, self.revision
            self.task = _SaveTask(snapshot, destination, self)
            self.task.finished.connect(self._finished)
            self.task.start()
        except Exception as exc:
            self._failed(exc)

    def _failed(self, error):
        self.error = error
        message = f'Auto save failed: {error}. Use Save project to retry.'
        self.shell.module_header.auto_save.setToolTip(message)
        self.shell.statusBar().showMessage(message)

    def _finished(self):
        task = self.task
        if task is None or not task.isFinished():
            return
        self.task = None
        task.deleteLater()
        if task.error is not None:
            self._failed(task.error)
            return
        shell = self.shell
        if shell.project is not self.owner:
            return
        first_save = shell.project.path is None
        shell.project.path, shell.project.modified = task.project.path, task.project.modified
        if first_save:
            for key, workspace in shell.workspaces.items():
                workspace.folder_edit.setText(str(shell.project.export_directory(key)))
        if self.revision == self.saved_revision:
            shell.dirty = False
        elif shell.project.auto_save:
            self.timer.start(1000)
        shell._remember()
        shell._update_header()
        state = 'on' if shell.project.auto_save else 'off'
        shell.module_header.auto_save.setToolTip(f'Auto save project ({state})\nSaved to {shell.project.path}')
        shell.statusBar().showMessage(f'Project automatically saved · {shell.project.path}')

    def save_now(self):
        self.stop()
        if self.shell.dirty:
            self._start()
            self.stop()
        return not self.shell.dirty
