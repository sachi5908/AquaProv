"""Explicit chemical basis and source-column review."""
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHeaderView,
    QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout)

from ...saturation.data import COMMON_MINERALS
from ...saturation.engine import PARAMETERS, UNITS, validate_parameters


class ChemistryDialog(QDialog):
    def __init__(self, frame, parameters, parent=None):
        super().__init__(parent)
        self.frame = frame
        self.setWindowTitle('Review dissolved chemistry, units and analytical basis')
        self.resize(820,640)
        layout = QVBoxLayout(self)
        note = QLabel('Map dissolved measurements only. Alkalinity is titrated acid-neutralizing capacity; '
                      'HCO3 concentration is not automatically alkalinity or DIC. If using a laboratory bicarbonate '
                      'alkalinity result, select Alkalinity with basis HCO3. Total inorganic carbon belongs in DIC. '
                      'For molar concentrations, the basis does not change the number of moles of the element; '
                      'alkalinity molar units represent equivalents.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(len(PARAMETERS),5)
        self.table.setHorizontalHeaderLabels(['Use','Parameter','Source column','Unit','Reported as'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        previous = {p['name']:p for p in parameters}
        for row,(name,(_,bases,_)) in enumerate(PARAMETERS.items()):
            p = previous.get(name,{})
            check = QCheckBox()
            check.setChecked(bool(p))
            self.table.setCellWidget(row,0,check)
            item = QTableWidgetItem(name)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row,1,item)
            column,unit,basis = QComboBox(),QComboBox(),QComboBox()
            column.addItems(list(frame.columns))
            unit.addItems(UNITS)
            basis.addItems(bases)
            column.setCurrentText(p.get('column',name))
            unit.setCurrentText(p.get('unit','mg/L'))
            basis.setCurrentText(p.get('basis',bases[0]))
            for index,control in enumerate((column,unit,basis),2):
                self.table.setCellWidget(row,index,control)
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        parameters = []
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row,0).isChecked():
                parameters.append(dict(name=self.table.item(row,1).text(),column=self.table.cellWidget(row,2).currentText(),
                                       unit=self.table.cellWidget(row,3).currentText(),basis=self.table.cellWidget(row,4).currentText()))
        try:
            validate_parameters(self.frame,parameters)
        except ValueError as exc:
            QMessageBox.warning(self,'Review chemistry',str(exc))
            return
        self.parameters = parameters
        super().accept()


class SIColumnDialog(QDialog):
    def __init__(self, frame, mapping, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Map imported SI columns')
        self.resize(620,540)
        layout = QVBoxLayout(self)
        note = QLabel('Each selected source column must already contain dimensionless saturation indices. '
                      'Mineral names can be edited; no concentrations are converted by this import.')
        note.setWordWrap(True)
        layout.addWidget(note)
        names = list(dict.fromkeys([*COMMON_MINERALS,*mapping]))
        self.columns = list(frame.columns)
        self.table = QTableWidget(0,3)
        self.table.setHorizontalHeaderLabels(['Use','Mineral','SI column'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for name in names:
            self.add_row(name,mapping.get(name))
        layout.addWidget(self.table)
        add = QPushButton('Add another mineral')
        add.clicked.connect(lambda:self.add_row('',None))
        layout.addWidget(add)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_row(self, name, column):
        row = self.table.rowCount()
        self.table.insertRow(row)
        check = QCheckBox()
        check.setChecked(column is not None)
        self.table.setCellWidget(row,0,check)
        self.table.setItem(row,1,QTableWidgetItem(name))
        choice = QComboBox()
        choice.addItems(self.columns)
        if column:
            choice.setCurrentText(column)
        self.table.setCellWidget(row,2,choice)

    def accept(self):
        mapping = {}
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row,0).isChecked():
                mineral = self.table.item(row,1).text().strip()
                if not mineral or mineral in mapping:
                    QMessageBox.warning(self,'Review SI mapping','Use distinct, non-empty mineral names.')
                    return
                mapping[mineral] = self.table.cellWidget(row,2).currentText()
        if not mapping or len(set(mapping.values())) != len(mapping):
            QMessageBox.warning(self,'Review SI mapping','Select distinct SI columns for at least one mineral.')
            return
        self.mapping = mapping
        super().accept()


class SampleDialog(QDialog):
    def __init__(self, samples, selected=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Select samples for comparison')
        self.resize(420,530)
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        for sample in dict.fromkeys(samples):
            item = QListWidgetItem(sample,self.list)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if selected is None or sample in selected else Qt.CheckState.Unchecked)
        layout.addWidget(self.list)
        for title,state in [('Select all',Qt.CheckState.Checked),('Clear selection',Qt.CheckState.Unchecked)]:
            button = QPushButton(title)
            button.clicked.connect(lambda _,s=state:[self.list.item(i).setCheckState(s) for i in range(self.list.count())])
            layout.addWidget(button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def samples(self):
        return [self.list.item(i).text() for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]
