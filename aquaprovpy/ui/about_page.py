"""About page with version information, credits and a license viewer."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QDialog, QDialogButtonBox, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QScrollArea, QTextBrowser, QVBoxLayout, QWidget,
)

from ..core.catalog import APP_TITLE, APP_VERSION
from ..modules.registry import MODULES
from .artwork import BrandLogo, app_icon
from .branding import brand_stylesheet
from .home import button, label
from .icons import module_icon


ABOUT_STYLE = brand_stylesheet("""
QScrollArea#aboutPage, QWidget#aboutBody, QWidget#aboutContent { background: @background@; border: 0; }
QLabel#aboutTitle { color: @ink@; font-size: 22pt; font-weight: 700; }
QLabel#aboutVersion { background: @wash@; color: @teal@; border: 1px solid @border@;
    border-radius: 12px; padding: 5px 12px; font-size: 9pt; font-weight: 600; }
QFrame#aboutHero { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 white, stop:1 @wash@); border: 1px solid @border@; border-radius: 16px; }
QLabel#aboutHeroTitle { color: @ink@; font-size: 24pt; font-weight: 700; }
QLabel#aboutIntro { color: @muted@; font-size: 11pt; }
QLabel#aboutDetail { color: @muted@; font-size: 9pt; }
QLabel#aboutSection { color: @ink@; font-size: 12pt; font-weight: 600; }
QFrame#aboutModule, QFrame#aboutCard { background: white; border: 1px solid @border@; border-radius: 12px; }
QLabel#aboutModuleTitle { color: @ink@; font-size: 10pt; font-weight: 600; }
QLabel#aboutAuthor { color: @ink@; font-size: 11pt; font-weight: 600; }
QLabel#aboutInitials { color: @teal@; background: @wash@; border-radius: 20px; font-size: 11pt; font-weight: 600; }
QLabel#aboutContact { font-size: 9pt; }
QLabel#aboutLicense { color: @teal@; font-size: 10pt; font-weight: 600; }
QPushButton#aboutAction { color: @ink@; background: white; border: 1px solid @border@;
    border-radius: 6px; padding: 7px 12px; font-size: 9pt; font-weight: 600; }
QPushButton#aboutAction:hover, QPushButton#aboutAction:focus { background: @wash@; border-color: @cyan@; }
QPushButton#primary:focus { border-color: @cyan@; }
""")

MODULE_SUMMARIES = {
    'saturation': ('Mineral saturation', 'PHREEQC speciation, saturation indices and spatial maps.'),
    'groundwater': ('Groundwater', 'Hydrochemistry, contamination and irrigation.'),
    'statistics': ('Statistics', 'Correlations, PCA and data exploration.'),
    'maps': ('Maps & contours', 'Spatial analysis, kriging and interpolation.'),
    'three_d': ('3D visualization', 'XYZ plots, surfaces and interactive PCA.'),
    'assessment': ('Assessment', 'Quality checks, uncertainty and validation.'),
    'water_quality': ('WQI & DWQI', 'Water-quality indices, standards and seasonal maps.'),
}


def info_card(title):
    card = QFrame()
    card.setObjectName('aboutCard')
    layout = QVBoxLayout(card)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(12)
    layout.addWidget(label(title, 'aboutSection'))
    return card, layout


class AboutPage(QScrollArea):
    def __init__(self, shell):
        super().__init__()
        self.setObjectName('aboutPage')
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(ABOUT_STYLE)
        self._columns = None
        body = QWidget()
        body.setObjectName('aboutBody')
        outer = QHBoxLayout(body)
        outer.setContentsMargins(28, 24, 28, 28)
        self.content = QWidget()
        self.content.setObjectName('aboutContent')
        outer.addStretch()
        outer.addWidget(self.content, alignment=Qt.AlignmentFlag.AlignTop)
        outer.addStretch()
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        heading = QHBoxLayout()
        heading.addWidget(label('About AquaProv', 'aboutTitle'), 1)
        self.version = label(f'Version {APP_VERSION}', 'aboutVersion')
        self.version.setWordWrap(False)
        heading.addWidget(self.version)
        layout.addLayout(heading)

        hero = QFrame()
        hero.setObjectName('aboutHero')
        self.hero_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, hero)
        self.hero_layout.setContentsMargins(28, 26, 28, 26)
        self.hero_layout.setSpacing(28)
        self.logo = BrandLogo(280, 112)
        self.hero_layout.addWidget(self.logo, alignment=Qt.AlignmentFlag.AlignCenter)
        introduction = QVBoxLayout()
        introduction.setSpacing(12)
        introduction.addWidget(label('Water analysis suite', 'aboutHeroTitle'))
        introduction.addWidget(label(
            'AquaProv (Aquatic Geochemistry & Provenance) is a desktop workspace '
            'for groundwater chemistry, statistical analysis, '
            'spatial mapping and three-dimensional visualization.', 'aboutIntro'))
        introduction.addWidget(label(
            'Import CSV or Excel data. Save your projects. Export figures, results and methods.',
            'aboutDetail'))
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.support_button = button('Support && Resources', lambda: shell.show_page('guide'), True, 'help')
        self.support_button.setAccessibleName('Support & Resources')
        self.copy_button = button('Copy version', self._copy_version)
        self.copy_button.setObjectName('aboutAction')
        self.copy_button.setMinimumWidth(112)
        self.copy_button.setToolTip('Copy the AquaProv version for a support request or citation')
        actions.addWidget(self.support_button)
        actions.addWidget(self.copy_button)
        actions.addStretch()
        introduction.addLayout(actions)
        self.hero_layout.addLayout(introduction, 1)
        layout.addWidget(hero)
        self.copy_feedback = QTimer(self)
        self.copy_feedback.setSingleShot(True)
        self.copy_feedback.timeout.connect(lambda: self.copy_button.setText('Copy version'))

        suite = QVBoxLayout()
        suite.setSpacing(10)
        suite.addWidget(label('Seven connected analysis modules', 'aboutSection'))
        self.module_grid = QGridLayout()
        self.module_grid.setSpacing(12)
        self.module_cards = []
        for module in MODULES:
            card = QFrame()
            card.setObjectName('aboutModule')
            content = QVBoxLayout(card)
            content.setContentsMargins(16, 16, 16, 16)
            content.setSpacing(8)
            icon = QLabel()
            icon.setPixmap(module_icon(module.key).pixmap(36, 36))
            icon.setFixedSize(36, 36)
            content.addWidget(icon)
            title, summary = MODULE_SUMMARIES[module.key]
            content.addWidget(label(title, 'aboutModuleTitle'))
            content.addWidget(label(summary, 'aboutDetail'))
            content.addStretch()
            self.module_cards.append(card)
        suite.addLayout(self.module_grid)
        layout.addLayout(suite)

        self.details_grid = QGridLayout()
        self.details_grid.setSpacing(16)
        self.authors_card, authors = info_card('Authors & developers')
        for initials, name, email in (
            ('SM', 'Sachida Nanda Mahanta', 'sachida5908@gmail.com'),
            ('BP', 'Bristi Phukan', 'bristi.87.hn.24@gmail.com'),
            ('SK', 'Dr. S. Selvakumar', 'geoselvas@gmail.com'),
        ):
            row = QHBoxLayout()
            row.setSpacing(12)
            avatar = label(initials, 'aboutInitials')
            avatar.setFixedSize(40, 40)
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(avatar)
            details = QVBoxLayout()
            details.setSpacing(3)
            details.addWidget(label(name, 'aboutAuthor'))
            if email:
                contact = QLabel(f'<a href="mailto:{email}" style="color: #006d75; text-decoration: none;">{email}</a>')
                contact.setObjectName('aboutContact')
                contact.setTextFormat(Qt.TextFormat.RichText)
                contact.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                contact.setOpenExternalLinks(True)
                contact.setToolTip('Email ' + name)
                details.addWidget(contact)
            row.addLayout(details, 1)
            authors.addLayout(row)
        authors.addWidget(label(
            'Dr. Harisingh Gour Vishwavidyalaya, Sagar, Madhya Pradesh, India', 'aboutDetail'))
        authors.addStretch()
        authors.addWidget(label('For guides, source code and issue reporting, visit Support & Resources.', 'aboutDetail'))

        self.credits_card, credits = info_card('Open source & acknowledgments')
        credits.addWidget(label('GNU General Public License, version 3', 'aboutLicense'))
        credits.addWidget(label(
            'Original geochemical plotting by Jing Yang and collaborators. '
            'Scientific-module author credits are retained in the source and documentation.', 'aboutDetail'))
        credits.addWidget(label(
            'The startup and project interface draw inspiration from FracSTAT. '
            'Bundled third-party assets retain their original notices.', 'aboutDetail'))
        credits.addStretch()
        self.license_button = button('View license', self._show_license)
        self.license_button.setObjectName('aboutAction')
        credits.addWidget(self.license_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(self.details_grid)

        technology = QVBoxLayout()
        technology.setSpacing(5)
        technology.addWidget(label('Built with open-source tools', 'aboutSection'))
        technology.addWidget(label(
            'Python  \u00b7  PySide6  \u00b7  NumPy  \u00b7  pandas  \u00b7  SciPy  \u00b7  '
            'Matplotlib  \u00b7  scikit-learn  \u00b7  Shapely  \u00b7  pyproj', 'aboutDetail'))
        layout.addLayout(technology)
        self.setWidget(body)
        self._arrange()

    def _arrange(self):
        width = max(280, min(1120, self.viewport().width() - 56))
        self.content.setFixedWidth(width)
        self.hero_layout.setDirection(QBoxLayout.Direction.LeftToRight if width >= 900
                                      else QBoxLayout.Direction.TopToBottom)
        columns = 5 if width >= 1000 else 3 if width >= 650 else 2
        detail_columns = 2 if width >= 700 else 1
        if self._columns == (columns, detail_columns):
            return
        self._columns = columns, detail_columns
        for card in self.module_cards:
            self.module_grid.removeWidget(card)
        for index, card in enumerate(self.module_cards):
            self.module_grid.addWidget(card, index // columns, index % columns)
        for column in range(5):
            self.module_grid.setColumnStretch(column, 1 if column < columns else 0)
        for card in (self.authors_card, self.credits_card):
            self.details_grid.removeWidget(card)
        self.details_grid.addWidget(self.authors_card, 0, 0)
        self.details_grid.addWidget(self.credits_card, 0 if detail_columns == 2 else 1,
                                   1 if detail_columns == 2 else 0)
        self.details_grid.setColumnStretch(0, 1)
        self.details_grid.setColumnStretch(1, 1 if detail_columns == 2 else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange()

    def _copy_version(self):
        QApplication.clipboard().setText(APP_TITLE)
        self.copy_button.setText('Copied!')
        self.copy_feedback.start(2000)

    def _show_license(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('AquaProv license')
        dialog.setWindowIcon(app_icon())
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(label('GNU General Public License, version 3', 'aboutSection'))
        text = QTextBrowser()
        package = Path(__file__).resolve().parents[1]
        license_path = package / 'assets' / 'LICENSE.txt'
        if not license_path.is_file():
            license_path = package.parent / 'LICENSE'
        try:
            text.setPlainText(license_path.read_text(encoding='utf-8'))
        except OSError:
            text.setHtml('AquaProv is distributed under the GNU General Public License, version 3. '
                         'Read the full license at <a href="https://www.gnu.org/licenses/gpl-3.0.html">gnu.org</a>.')
            text.setOpenExternalLinks(True)
        layout.addWidget(text, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()
        dialog.deleteLater()
