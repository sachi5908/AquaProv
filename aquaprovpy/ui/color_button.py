"""Clickable colour swatches with text values for saved plot settings."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen
from PySide6.QtWidgets import QColorDialog, QHBoxLayout, QPushButton, QToolButton, QWidget


def _qcolor(value):
    color = QColor(value)
    if not color.isValid() and value:
        from matplotlib.colors import to_rgba
        try:
            color = QColor.fromRgbF(*to_rgba(value))
        except ValueError:
            pass
    return color


class ColorButton(QPushButton):
    """Display only the colour; retain text()/setText() for project compatibility."""
    colorChanged = Signal(str)

    def __init__(self, value, parent=None, *, allow_auto=False):
        super().__init__(parent)
        self.allow_auto = allow_auto
        self._value = value
        self.setFixedSize(36, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName('Choose colour')
        self.clicked.connect(self.choose_color)
        if allow_auto:
            automatic = QAction('Use automatic colour', self)
            automatic.triggered.connect(self.clear)
            self.addAction(automatic)
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self._update_description()

    def text(self):
        return self._value

    def setText(self, value):
        if value == self._value:
            return
        self._value = value
        self._update_description()
        self.update()
        self.colorChanged.emit(value)

    def clear(self):
        if self.allow_auto:
            self.setText('')

    def _update_description(self):
        value = self._value or 'Automatic'
        self.setAccessibleDescription(value)
        self.setToolTip('Click to choose colour · ' + value)

    def choose_color(self):
        current = _qcolor(self._value)
        if not current.isValid():
            current = QColor('#2878a5')
        color = QColorDialog.getColor(current, self.window(), self.accessibleName())
        if color.isValid():
            self.setText(color.name())

    def paintEvent(self, event):
        # Paint directly so inherited button styles never expose the stored hex
        # value or replace the fill with the application's generic button tint.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        color = _qcolor(self._value)
        painter.setOpacity(1 if self.isEnabled() else .4)
        painter.setBrush(color if color.isValid() else QColor('#f3f6f8'))
        border = '#0095bf' if self.hasFocus() or self.underMouse() else '#b9cbd6'
        painter.setPen(QPen(QColor(border), 2 if self.hasFocus() else 1))
        painter.drawRoundedRect(rect, 5, 5)
        if not self._value:
            painter.setPen(QPen(QColor('#8294a2'), 1.5))
            painter.drawLine(rect.left() + 6, rect.bottom() - 5,
                             rect.right() - 6, rect.top() + 5)


class ColorPalette(QWidget):
    """A row of editable swatches stored as the existing comma-separated value."""
    colorChanged = Signal(str)

    def __init__(self, value, parent=None):
        super().__init__(parent)
        self._value = ''
        self._swatches = []
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(6)
        self._add = QToolButton()
        self._add.setText('+')
        self._add.setFixedSize(24, 24)
        self._add.setToolTip('Add a series colour')
        self._add.setAccessibleName('Add a series colour')
        self._add.clicked.connect(self._add_color)
        self._row.addWidget(self._add)
        self._row.addStretch()
        self.setText(value)

    def text(self):
        return self._value

    def setText(self, value):
        if value == self._value:
            return
        self._value = value
        for swatch in self._swatches:
            self._row.removeWidget(swatch)
            swatch.hide()
            swatch.setParent(None)
            swatch.deleteLater()
        self._swatches = []
        for index, color in enumerate(part.strip() for part in value.split(',') if part.strip()):
            swatch = ColorButton(color)
            swatch.setAccessibleName(f'Choose series {index + 1} colour')
            swatch.colorChanged.connect(self._colors_changed)
            remove = QAction('Remove this series colour', swatch)
            remove.triggered.connect(lambda checked=False, button=swatch: self._remove_color(button))
            swatch.addAction(remove)
            swatch.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
            self._swatches.append(swatch)
            self._row.insertWidget(index, swatch)
        self.colorChanged.emit(value)

    def _colors_changed(self):
        self._value = ', '.join(swatch.text() for swatch in self._swatches)
        self.colorChanged.emit(self._value)

    def _add_color(self):
        color = QColorDialog.getColor(QColor('#2878a5'), self.window(), 'Add a series colour')
        if color.isValid():
            self.setText(', '.join(filter(None, (self._value, color.name()))))

    def _remove_color(self, button):
        if len(self._swatches) > 1:
            self.setText(', '.join(swatch.text() for swatch in self._swatches if swatch is not button))
