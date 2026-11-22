"""Startup banner shown before the launcher or scientific libraries load."""
from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout
from ..core.catalog import APP_TITLE, APP_VERSION
from .artwork import BrandLogo, WaterBanner, app_icon
from .branding import brand_stylesheet


class StartupSplash(WaterBanner):
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(app_icon())
        self.setStyleSheet(brand_stylesheet("QWidget { font-family: 'Segoe UI'; font-size: 9pt; color: @ink@; }"))
        self.setFixedSize(760, 400)
        self._dismissed = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(42, 24, 42, 28)
        eyebrow = QLabel("WATER ANALYSIS SUITE")
        eyebrow.setStyleSheet(brand_stylesheet("color: @teal@; font-size: 8pt; font-weight: 600; letter-spacing: 3px;"))
        layout.addWidget(eyebrow, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.logo = BrandLogo(475, 188)
        layout.addWidget(self.logo, alignment=Qt.AlignmentFlag.AlignHCenter)
        subtitle = QLabel("Groundwater. Spatial insight. A new dimension.")
        subtitle.setStyleSheet(brand_stylesheet("color: @navy@; font-size: 11pt;"))
        layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignHCenter)
        version = QLabel(f"V. {APP_VERSION}")
        version.setStyleSheet(brand_stylesheet("color: @muted@; font-size: 9pt;"))
        layout.addWidget(version, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        self.status = QLabel("Preparing your workspace…")
        self.status.setStyleSheet(brand_stylesheet("color: @muted@; font-size: 9pt;"))
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet(brand_stylesheet("QProgressBar { background: @border@; border: 0; } QProgressBar::chunk { background: @cyan@; }"))
        layout.addWidget(self.progress)

    def dismiss(self):
        self._dismissed = True
        self.close()

    def closeEvent(self, event):
        if not self._dismissed:
            self.cancelled.emit()
        event.accept()


class StartupController(QObject):
    def __init__(self, application, create_window, *, minimum_ms=1100, project_path=None):
        super().__init__(application)
        self.application = application
        self.create_window = create_window
        self.project_path = project_path
        self.splash = StartupSplash()
        self.window = None
        self.cancelled = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(max(0, minimum_ms))
        self.timer.timeout.connect(self.finish)
        self.build_timer = QTimer(self)
        self.build_timer.setSingleShot(True)
        self.build_timer.timeout.connect(self.build)
        self.splash.cancelled.connect(self.cancel)

    def start(self):
        screen = self.application.primaryScreen()
        if screen:
            self.splash.move(screen.availableGeometry().center() - self.splash.rect().center())
        self.splash.show()
        self.build_timer.start(30)

    def build(self):
        if self.cancelled:
            return
        try:
            self.splash.status.setText("Preparing Home & recent projects…")
            self.window = self.create_window()
            self.timer.start()
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self.splash, "AquaProv could not start", str(exc))
            self.splash.dismiss()
            self.application.exit(1)

    def finish(self):
        if self.cancelled or self.window is None:
            return
        self.window.show()
        self.splash.dismiss()
        if self.project_path:
            self.window.open_project(self.project_path)

    def cancel(self):
        self.cancelled = True
        self.timer.stop()
        self.build_timer.stop()
        self.application.quit()

    def dispose(self):
        self.timer.stop()
        self.build_timer.stop()
        self.splash.dismiss()
