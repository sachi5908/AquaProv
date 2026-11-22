"""Keep wheel gestures in settings panels from editing field values."""
from PySide6.QtCore import QEvent, QObject, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QApplication, QAbstractSpinBox, QComboBox, QLineEdit, QScrollArea, QWidget,
)


class SidebarWheelFilter(QObject):
    """Route field wheel events to the enclosing scroll area.

    Watch application events so controls added or reparented after the sidebar
    is built are covered too. The filter is owned by, and limited to, its panel.
    Popup lists keep their native scrolling, as do plots outside the sidebar.
    """

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        if (event.type() == QEvent.Type.Wheel
                and isinstance(watched, QWidget)
                and self.panel.isAncestorOf(watched)):
            control = watched.parentWidget() if isinstance(watched, QLineEdit) else watched
            if not isinstance(control, (QComboBox, QAbstractSpinBox)):
                return False
            if isinstance(control, QComboBox) and control.view().isVisible():
                return False
            parent = control.parentWidget()
            while parent is not None:
                if isinstance(parent, QScrollArea):
                    viewport = parent.viewport()
                    forwarded = QWheelEvent(
                        QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint())),
                        event.globalPosition(), event.pixelDelta(), event.angleDelta(),
                        event.buttons(), event.modifiers(), event.phase(), event.inverted(),
                        event.source(), event.pointingDevice(),
                    )
                    forwarded.setTimestamp(event.timestamp())
                    forwarded.ignore()
                    QApplication.sendEvent(viewport, forwarded)
                    if forwarded.isAccepted():
                        break
                if parent is self.panel:
                    break
                parent = parent.parentWidget()
            # Consume the original even at the scroll boundary: a field must
            # never start editing values just because the panel cannot move.
            event.accept()
            return True
        return super().eventFilter(watched, event)
