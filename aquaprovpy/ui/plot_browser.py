"""Searchable plot navigation, grouped by scientific purpose."""
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import QFrame, QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout
from .icons import action_icon


class PlotBrowser(QFrame):
    plot_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("plotLibrary")
        self.setMinimumWidth(180)
        self.setMaximumWidth(320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 14)
        title = QLabel("PLOT LIBRARY")
        title.setObjectName("libraryHeading")
        layout.addWidget(title)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a plot…")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(action_icon('search'), QLineEdit.ActionPosition.LeadingPosition)
        layout.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setObjectName("plotTree")
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(10)
        self.tree.setUniformRowHeights(True)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.currentItemChanged.connect(self._selected)
        self.tree.setAccessibleName("Available plots in this module")
        layout.addWidget(self.tree, 1)
        self.count = QLabel()
        self.count.setObjectName("muted")
        layout.addWidget(self.count)
        self.items = {}
        self.search.textChanged.connect(self._filter)

    def populate(self, choices):
        self.choices = choices
        with QSignalBlocker(self.tree):
            self.tree.clear()
            self.items = {}
            groups = {}
            for choice in choices:
                if choice.group not in groups:
                    group = QTreeWidgetItem([choice.group])
                    group.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    font = group.font(0)
                    font.setBold(True)
                    group.setFont(0, font)
                    self.tree.addTopLevelItem(group)
                    groups[choice.group] = group
                item = QTreeWidgetItem(groups[choice.group], [choice.title])
                item.setData(0, Qt.ItemDataRole.UserRole, choice.key)
                item.setToolTip(0, choice.title + "\n" + choice.description)
                self.items[choice.key] = item
            self.tree.expandAll()
        self._filter()

    def select(self, key):
        if key in self.items:
            with QSignalBlocker(self.tree):
                self.tree.setCurrentItem(self.items[key])

    def _selected(self, item, _previous):
        if item and item.data(0, Qt.ItemDataRole.UserRole):
            self.plot_selected.emit(item.data(0, Qt.ItemDataRole.UserRole))

    def _filter(self, *_):
        query = self.search.text().casefold()
        visible = 0
        for choice in self.choices:
            match = query in (choice.title + " " + choice.group).casefold()
            self.items[choice.key].setHidden(not match)
            visible += int(match)
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            group.setHidden(all(group.child(i).isHidden() for i in range(group.childCount())))
        self.tree.expandAll()
        self.count.setText(f"{visible} of {len(self.choices)} plots")
