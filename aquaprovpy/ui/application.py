"""Create the Qt application and launch the AquaProv window."""

import sys
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from ..core.catalog import APP_NAME, APP_TITLE, APP_VERSION
from .startup import StartupController
from .artwork import app_icon


def create_window():
    from .shell import AquaProvWindow
    return AquaProvWindow()


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    application = QApplication.instance() or QApplication(argv)
    application.setApplicationName(APP_NAME)
    application.setApplicationDisplayName(APP_TITLE)
    application.setApplicationVersion(APP_VERSION)
    application.setOrganizationName("AquaProv")
    application.setFont(QFont("Segoe UI", 10))
    application.setWindowIcon(app_icon())
    from ..core.projects import PROJECT_EXTENSIONS
    project_path = next((arg for arg in argv[1:] if arg.lower().endswith(PROJECT_EXTENSIONS)), None)
    startup = StartupController(application, create_window, project_path=project_path)
    startup.start()
    try:
        return application.exec()
    finally:
        startup.dispose()
