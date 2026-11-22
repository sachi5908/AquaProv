"""Shared labels and action buttons for launcher pages."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton
from .icons import decorate_button


def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, primary=False, icon=None):
    widget = QPushButton(text)
    widget.setObjectName("primary" if primary else "secondary")
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(callback)
    if icon:
        decorate_button(widget, icon, tint='#ffffff' if primary else None)
    return widget

