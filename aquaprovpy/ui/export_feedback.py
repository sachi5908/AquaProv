"""Export notifications, overwrite confirmation and error messages."""

import errno
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from ..core.export_files import ExportWriteError
from .icons import action_icon


def dismiss_export_success(parent):
    for dialog in parent.findChildren(QMessageBox, 'exportSuccess'):
        dialog.setObjectName('previousExportSuccess')
        dialog.close()


def _file_summary(paths, limit=4):
    names = [path.name for path in paths[:limit]]
    if len(paths) > limit:
        names.append(f'... and {len(paths) - limit} more files')
    return '\n'.join(names)


def confirm_export_overwrite(parent, paths, title):
    existing = [path for path in paths if path.exists()]
    for path in existing:
        if not path.is_file():
            raise ValueError(f'A folder already uses the export name "{path.name}". Choose another file name.')
    if not existing:
        return True
    text = ('These files already exist:\n\n' + _file_summary(existing) +
            f'\n\nLocation:\n{existing[0].parent}\n\nReplace them?')
    return QMessageBox.question(parent, title, text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes


def show_export_success(parent, paths, description):
    dismiss_export_success(parent)
    paths = [Path(path).resolve() for path in paths]
    directory = paths[0].parent
    dialog = QMessageBox(parent)
    dialog.setObjectName('exportSuccess')
    dialog.setWindowTitle('Export complete')
    dialog.setIcon(QMessageBox.Icon.Information)
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    dialog.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse |
                                   Qt.TextInteractionFlag.TextSelectableByKeyboard)
    dialog.setText(f'{description} saved successfully.')
    dialog.setInformativeText(f'{len(paths)} file' + ('s' if len(paths) != 1 else '') +
                             ' saved:\n' + _file_summary(paths) + f'\n\nLocation:\n{directory}')
    dialog.setDetailedText('Saved files:\n' + '\n'.join(str(path) for path in paths))
    ok = dialog.addButton(QMessageBox.StandardButton.Ok)
    open_folder = dialog.addButton('Open folder', QMessageBox.ButtonRole.ActionRole)
    open_folder.setObjectName('openExportFolder')
    open_folder.setIcon(action_icon('open'))
    def open_location():
        if not directory.is_dir() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))):
            QMessageBox.warning(parent, 'Folder could not be opened',
                f'The files were saved, but the folder could not be opened automatically.\n\nLocation:\n{directory}')
    open_folder.clicked.connect(open_location)
    dialog.setDefaultButton(ok)
    dialog.setEscapeButton(ok)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    # Non-blocking Qt API: the save operation has already completed. The user
    # can dismiss this window-modal notice or open the destination folder.
    dialog.open()
    return dialog


def show_export_error(parent, title, error, directory=None):
    cause = error.cause if isinstance(error, ExportWriteError) else error
    message = cause.strerror if isinstance(cause, OSError) and cause.strerror else str(cause)
    if isinstance(cause, PermissionError):
        message = 'The file or folder cannot be written. Close the output file if it is open, or choose a folder you can write to.\n\n' + message
    elif isinstance(cause, OSError) and (cause.errno == errno.ENOSPC or getattr(cause, 'winerror', None) == 112):
        message = 'There is not enough free disk space. Free some space or choose another drive.\n\n' + message
    if isinstance(error, ExportWriteError):
        directory = error.targets[0].parent
        if error.completed:
            message += '\n\nOnly these files were saved before the export stopped:\n' + _file_summary(list(error.completed))
        else:
            message += '\n\nNo new files were saved; existing exports were kept.'
    if directory is not None:
        message += f'\n\nLocation:\n{directory}'
    if isinstance(cause, ValueError):
        QMessageBox.warning(parent, 'Check export settings', message)
    else:
        QMessageBox.critical(parent, title, message)
