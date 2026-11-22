"""Read-only table that formats only visible cells, even for large datasets."""
import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import QTableView


class _FrameModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame = None
        self.results = False

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() or self.frame is None else len(self.frame)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() or self.frame is None else len(self.frame.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        value = self.frame.iat[index.row(), index.column()]
        if pd.isna(value):
            return ''
        if self.frame.columns[index.column()] in self.frame.attrs.get('full_precision_columns', ()):
            return str(value)
        return f'{value:.6g}' if self.results and isinstance(value, (float, np.floating)) else str(value)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if self.frame is None or role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self.frame.columns[section])
        return str(self.frame.index[section]) if self.results else str(section + 1)


class DataFrameTable(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModel(_FrameModel(self))
        self.horizontalHeader().setResizeContentsPrecision(50)
        self.setWordWrap(False)

    def set_frame(self, frame, *, results=False):
        model = self.model()
        model.beginResetModel()
        model.frame, model.results = frame, results
        model.endResetModel()
        self.resizeColumnsToContents()

    def clear(self):
        self.set_frame(None)

    def rowCount(self):
        return self.model().rowCount()

    def columnCount(self):
        return self.model().columnCount()
