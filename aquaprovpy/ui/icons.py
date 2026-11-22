"""Small, locally bundled action icons shared across the desktop interface."""
from pathlib import Path
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap


ICON_ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'icons'
ICONS = {
    'home': 'home.png', 'open': 'folder.png', 'import': 'file-import.png',
    'save': 'save.png', 'export': 'export.png', 'generate': 'graph.png',
    'settings': 'settings.png', 'fullscreen': 'full_screen.png', 'reset': 'reset.png',
    'color': 'color-wheel.png', 'search': 'search.png', 'new': 'plus.png',
    'help': 'question.png', 'library': 'canvas.png', 'three_d': 'cube.png',
    'maps': 'internet.png', 'tabs': 'tab.png', 'delete': 'bin.png',
    'github': 'github-sign.png', 'manual': 'pdf-file.png', 'issue': 'bug.png',
    'auto_update': 'auto_update.png',
    'auto_save': 'auto_save.png',
}


def module_icon(key):
    return QIcon(str(ICON_ROOT / f'module_{key}.svg'))


def action_icon(name, tint=None):
    path = str(ICON_ROOT / ICONS[name])
    if tint is None:
        return QIcon(path)
    pixmap = QPixmap(path)
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(tint))
    painter.end()
    return QIcon(pixmap)


def decorate_button(button, name, size=18, tint=None):
    button.setIcon(action_icon(name, tint))
    button.setIconSize(QSize(size, size))
    return button
