"""Per-plot legend checklist; hiding a key never hides its data artist."""
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QListWidget, QListWidgetItem, QPushButton)


class LegendItemsControl(QWidget):
    selectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hidden = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.note = QLabel('Generate this plot to see its legend items.')
        self.note.setWordWrap(True)
        self.note.setObjectName('muted')
        layout.addWidget(self.note)
        self.items = QListWidget()
        self.items.setMinimumHeight(100)
        self.items.setMaximumHeight(220)
        self.items.setWordWrap(True)
        self.items.itemChanged.connect(self._item_changed)
        layout.addWidget(self.items)
        row = QHBoxLayout()
        self.show_all = QPushButton('Show all items')
        self.hide_all = QPushButton('Hide all items')
        self.show_all.clicked.connect(lambda: self._select_all(True))
        self.hide_all.clicked.connect(lambda: self._select_all(False))
        row.addWidget(self.show_all)
        row.addWidget(self.hide_all)
        layout.addLayout(row)
        self.set_entries([])

    def value(self):
        return list(self._hidden)

    def setValue(self, hidden):
        self._hidden = list(hidden)
        self.set_entries([self.items.item(i).text() for i in range(self.items.count())])

    def set_entries(self, labels):
        self.items.setFixedHeight(max(100, min(220, len(labels) * 24 + 12)))
        with QSignalBlocker(self.items):
            self.items.clear()
            for label in labels:
                item = QListWidgetItem(label)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked if label in self._hidden else Qt.CheckState.Checked)
                self.items.addItem(item)
        self.note.setText('Check the items to include in this plot’s legend.' if labels else
                          'Generate this plot to see its legend items.')
        for widget in (self.items, self.show_all, self.hide_all):
            widget.setEnabled(bool(labels))

    def _item_changed(self, item):
        label = item.text()
        if item.checkState() == Qt.CheckState.Checked:
            self._hidden = [value for value in self._hidden if value != label]
        elif label not in self._hidden:
            self._hidden.append(label)
        self.selectionChanged.emit()

    def _select_all(self, checked):
        labels = [self.items.item(i).text() for i in range(self.items.count())]
        self._hidden = [] if checked else list(dict.fromkeys([*self._hidden, *labels]))
        self.set_entries(labels)
        self.selectionChanged.emit()
