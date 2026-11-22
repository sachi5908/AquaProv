"""Support cards for online documentation and project links."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)
from ..core.resources import RESOURCE_LINKS_PATH, load_resource_links
from .branding import brand_stylesheet
from .home import label
from .icons import action_icon

DOCS_ROOT = Path(__file__).resolve().parents[2] / 'docs'

RESOURCE_STYLE = brand_stylesheet("""
QWidget#resourcesPage, QWidget#resourceBody { background: @background@; }
QFrame#resourceHeader { background: white; border: 0; border-bottom: 1px solid @border@; }
QLabel#resourceTitle { font-size: 20pt; font-weight: 700; color: @ink@; }
QLabel#resourceSubtitle { font-size: 9pt; color: @muted@; }
QFrame#resourceCard { background: white; border: 1px solid @border@; border-radius: 12px; }
QLabel#resourceCardTitle { font-size: 12pt; font-weight: 700; color: @ink@; }
QLabel#resourceDescription { font-size: 9pt; color: @muted@; }
QPushButton#resourceAction { color: white; border: 0; border-radius: 6px; padding: 10px 16px; font-size: 9pt; font-weight: 600; }
QPushButton#resourceAction:disabled { background: @wash@; color: @disabled@; }
QScrollArea#resourceScroll { background: transparent; border: 0; }
""")


class ResourceCard(QFrame):
    def __init__(self, title, description, icon, accent, tint):
        super().__init__()
        self.setObjectName('resourceCard')
        self.setMinimumHeight(218)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        line = QFrame()
        line.setFixedHeight(3)
        line.setStyleSheet(f'background: {accent}; border: 0;')
        layout.addWidget(line)
        content = QVBoxLayout()
        content.setContentsMargins(22, 20, 22, 20)
        content.setSpacing(14)
        heading = QHBoxLayout()
        heading.setSpacing(14)
        badge = QLabel()
        badge.setFixedSize(46, 46)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(action_icon(icon, accent).pixmap(24, 24))
        badge.setStyleSheet(f'background: {tint}; border-radius: 12px;')
        heading.addWidget(badge)
        heading.addWidget(label(title, 'resourceCardTitle'), 1)
        content.addLayout(heading)
        content.addWidget(label(description, 'resourceDescription'))
        content.addStretch()
        self.action = QPushButton()
        self.action.setObjectName('resourceAction')
        self.action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action.setStyleSheet(f'QPushButton#resourceAction:enabled {{ background: {accent}; }}'
                                 f'QPushButton#resourceAction:hover {{ background: {QColor(accent).darker(112).name()}; }}')
        content.addWidget(self.action, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(content, 1)


class ResourcesPage(QWidget):
    def __init__(self, shell, config_path=RESOURCE_LINKS_PATH, docs_root=DOCS_ROOT):
        super().__init__()
        self.config_path, self.docs_root = Path(config_path), Path(docs_root)
        self.setObjectName('resourcesPage')
        self.setStyleSheet(RESOURCE_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName('resourceHeader')
        heading = QVBoxLayout(header)
        heading.setContentsMargins(28, 24, 28, 24)
        heading.addWidget(label('Support & Resources', 'resourceTitle'))
        heading.addWidget(label('Documentation, user guides and project support.', 'resourceSubtitle'))
        layout.addWidget(header)
        scroll = QScrollArea()
        scroll.setObjectName('resourceScroll')
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName('resourceBody')
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 24, 24, 24)
        self.grid = QGridLayout()
        self.grid.setSpacing(20)
        body_layout.addLayout(self.grid)
        body_layout.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        self.cards = {
            'documentation_url': ResourceCard('Documentation', 'Browse guides and references for AquaProv.', 'maps', '#2563eb', '#e5efff'),
            'manual_url': ResourceCard('User Guide', 'Read about projects, plots and exporting your results.', 'manual', '#006d75', '#e1f1f2'),
            'issues_url': ResourceCard('Report an Issue', 'Report a bug or suggest an improvement on GitHub.', 'issue', '#7540ce', '#eee7fa'),
            'github_url': ResourceCard('GitHub Repository', 'Browse the source code, releases and project updates.', 'github', '#203449', '#e7edf3'),
        }
        for key, card in self.cards.items():
            card.action.clicked.connect(lambda checked=False, name=key: self._open(name))
        self._columns = None
        self._arrange()
        self.refresh()

    def _arrange(self):
        columns = 2 if self.width() >= 800 else 1
        if columns == self._columns:
            return
        self._columns = columns
        for card in self.cards.values():
            self.grid.removeWidget(card)
        for index, card in enumerate(self.cards.values()):
            self.grid.addWidget(card, index // columns, index % columns)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if columns == 2 else 0)

    def resizeEvent(self, event):
        self._arrange()
        super().resizeEvent(event)

    def refresh(self):
        self.links = load_resource_links(self.config_path)
        for key, filenames in (('documentation_url', ('index.html',)),
                               ('manual_url', ('manual.html', 'index.html'))):
            if not self.links[key]:
                local_html = next((self.docs_root / name for name in filenames
                                   if (self.docs_root / name).is_file()), None)
                if local_html is not None:
                    self.links[key] = QUrl.fromLocalFile(str(local_html.resolve())).toString()
        for key, caption in (('documentation_url', 'Open Documentation'), ('manual_url', 'Open Manual'),
                              ('issues_url', 'Report an Issue'), ('github_url', 'Open GitHub')):
            action = self.cards[key].action
            available = bool(self.links[key])
            action.setEnabled(available)
            action.setText(caption if available else 'Coming soon')
            action.setToolTip(self.links[key] or 'This resource is not available yet.')

    def _open(self, key):
        target = self.links.get(key, '')
        if target:
            QDesktopServices.openUrl(QUrl(target))
