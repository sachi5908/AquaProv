"""Editable source mappings without changing imported measurements."""
from copy import deepcopy

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QTableWidget, QComboBox,
    QDialogButtonBox, QLabel, QCheckBox, QLineEdit, QMessageBox, QTabWidget, QWidget)

from ...assessment.measurements import ANALYTES, prepare


class SchemaDialog(QDialog):
    def __init__(self, frame, schema, parent=None):
        super().__init__(parent)
        self.frame, self.schema = frame, deepcopy(schema)
        self.setWindowTitle('Measurement mappings, units & laboratory metadata')
        self.resize(1120, 690)
        layout = QVBoxLayout(self)
        note = QLabel('Review the suggested mappings. SD must be a laboratory standard deviation in the source unit. '
                      'A detection limit is required for non-detect modelling. Alkalinity is kept separate from bicarbonate.')
        note.setWordWrap(True)
        layout.addWidget(note)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        self.table = QTableWidget(len(ANALYTES), 9)
        self.table.setHorizontalHeaderLabels(['Analyte', 'Source column', 'Unit', 'Basis', 'SD column', 'Limit column', 'Fixed limit', 'Qualifier column', 'Fixed SD'])
        self.rows = []
        for row, analyte in enumerate(ANALYTES):
            field = schema['fields'].get(analyte, {})
            label = QLabel(analyte)
            self.table.setCellWidget(row, 0, label)
            widgets = {}
            for col, key, choices in [
                (1, 'column', ['(unmapped)', *frame.columns]),
                (2, 'unit', ['mg/L', 'ug/L', 'meq/L', 'mmol/L', 'uS/cm', 'mS/cm', 'dS/m', 'pH']),
                (3, 'basis', ['species', 'N', 'CaCO3']),
                (4, 'sd_column', ['(none)', *frame.columns]),
                (5, 'limit_column', ['(none)', *frame.columns]),
                (7, 'qualifier_column', ['(none)', *frame.columns]),
            ]:
                combo = QComboBox()
                combo.addItems([str(x) for x in choices])
                default = 'pH' if analyte == 'pH' and key == 'unit' else 'uS/cm' if analyte == 'EC' and key == 'unit' else 'CaCO3' if analyte == 'Alkalinity' and key == 'basis' else choices[0]
                combo.setCurrentText(str(field.get(key, default)))
                self.table.setCellWidget(row, col, combo)
                widgets[key] = combo
            for col, key in [(6, 'limit'), (8, 'sd')]:
                edit = QLineEdit(str(field[key]) if field.get(key) is not None else '')
                self.table.setCellWidget(row, col, edit)
                widgets[key] = edit
            self.rows.append((analyte, widgets))
        self.table.setColumnWidth(1, 190)
        tabs.addTab(self.table, 'Measurements')
        page = QWidget()
        form = QFormLayout(page)
        self.metadata_controls = {}
        for key in ('sample', 'well', 'time', 'season', 'x', 'y', 'depth', 'aquifer'):
            combo = QComboBox()
            combo.addItems(['(none)', *[str(c) for c in frame.columns]])
            combo.setCurrentText(schema.get('metadata', {}).get(key) or '(none)')
            form.addRow(key.title(), combo)
            self.metadata_controls[key] = combo
            if key == 'time':
                combo.setToolTip('Use numeric years/time values or ISO 8601 dates. Ambiguous day/month strings are not inferred.')
        self.crs_edit = QLineEdit(schema.get('crs', 'unspecified'))
        form.addRow('Source CRS identifier', self.crs_edit)
        tabs.addTab(page, 'Sample & location metadata')
        self.confirm = QCheckBox('I have checked the source units and chemical bases')
        self.confirm.setChecked(schema.get('unit_assumptions_confirmed', False))
        layout.addWidget(self.confirm)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        fields = {}
        try:
            for analyte, widgets in self.rows:
                if widgets['column'].currentIndex() == 0:
                    continue
                field = {k: widgets[k].currentText() for k in ('column', 'unit', 'basis')}
                for key in ('sd_column', 'limit_column', 'qualifier_column'):
                    if widgets[key].currentIndex() > 0:
                        field[key] = widgets[key].currentText()
                for key in ('sd', 'limit'):
                    if widgets[key].text().strip():
                        field[key] = float(widgets[key].text())
                fields[analyte] = field
            schema = {'version': 1, 'fields': fields,
                      'metadata': {k: w.currentText() if w.currentIndex() > 0 else None for k,w in self.metadata_controls.items()},
                      'crs': self.crs_edit.text().strip() or 'unspecified',
                      'unit_assumptions_confirmed': self.confirm.isChecked()}
            prepare(self.frame, schema)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, 'Check measurement mappings', str(exc))
            return
        self.schema = schema
        super().accept()
