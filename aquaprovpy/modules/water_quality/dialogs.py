"""Editable parameter mappings, standards provenance and classification schemes."""
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ...water_quality.common import validate_parameters, validate_scheme


class ParameterDialog(QDialog):
    HEADERS = ['Use', 'Parameter / species', 'Source column', 'Input unit', 'Standard unit', 'Lower limit', 'Upper limit',
               'Ideal', 'Weight', 'Rating', 'Edition', 'Amendment', 'Publication year', 'Source URL / document', 'Page', 'Verification']

    def __init__(self, frame, profile, standard, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Index parameters, units and standards')
        self.resize(1180,650)
        self.profile, self.original = deepcopy(profile), {}
        layout = QVBoxLayout(self)
        note = QLabel('Select parameters explicitly. Weights start at 1 (equal importance); they are not a transcription of published study weights. '
                      'Weighted arithmetic WQI uses inverse-standard weights. CCME ignores weights and ideals. '
                      'Ratio: 100 C/S; ideal: 100 (C−I)/(S−I); two-sided: separate deviations around the ideal. '
                      'Limits and ideals use standard units. Scroll right to review per-limit provenance.')
        note.setWordWrap(True);layout.addWidget(note)
        self.table = QTableWidget(0,len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        selected = {p['name']:p for p in profile['parameters']}
        names = list(dict.fromkeys([*selected,*standard['parameters']]))
        for name in names:
            definition = standard['parameters'].get(name, {})
            limit = deepcopy(definition.get(profile['limit_kind'], {}))
            base = dict(name=name,column='',unit=definition.get('unit','mg/L'),standard_unit=definition.get('unit','mg/L'),
                        weight=1.,ideal=7. if name=='pH' else 0.,rating='ideal' if profile['method']=='brown' else 'ratio',
                        standard_id=standard['id'],limit_kind=profile['limit_kind'],**limit)
            p = deepcopy(selected.get(name,base))
            self.original[name] = deepcopy(p)
            self.add_row(p,list(frame.columns),name in selected)
        add = QPushButton('Add a custom parameter')
        add.clicked.connect(lambda:self.add_row(dict(name='',column='',unit='mg/L',standard_unit='mg/L',weight=1.,ideal=0.,rating='ratio',
            edition='User-defined',amendment='User-defined',publication_year=2026,verification='unverified'),list(frame.columns),True))
        layout.addWidget(add)
        self.reviewed = QCheckBox('I verified edited limit values, units and provenance against the cited official documents')
        layout.addWidget(self.reviewed)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def add_row(self,p,columns,enabled):
        r = self.table.rowCount();self.table.insertRow(r)
        check = QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable)
        check.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked);self.table.setItem(r,0,check)
        self.table.setItem(r,1,QTableWidgetItem(p['name']))
        combo = QComboBox();combo.addItems(['',*columns]);combo.setCurrentText(p.get('column',''));self.table.setCellWidget(r,2,combo)
        fields = {3:'unit',4:'standard_unit',5:'lower',6:'upper',7:'ideal',8:'weight',10:'edition',11:'amendment',12:'publication_year',13:'source',14:'page'}
        for c,key in fields.items():
            value = p.get(key)
            self.table.setItem(r,c,QTableWidgetItem('' if value is None else str(value)))
        rating = QComboBox();rating.addItems(['ratio','ideal','two_sided']);rating.setCurrentText(p.get('rating','ratio'));self.table.setCellWidget(r,9,rating)
        status = QComboBox();status.addItems(['unverified','verified']);status.setCurrentText(p.get('verification','unverified'));self.table.setCellWidget(r,15,status)

    def accept(self):
        try:
            parameters = []
            for r in range(self.table.rowCount()):
                if self.table.item(r,0).checkState()!=Qt.CheckState.Checked:continue
                read = lambda c:self.table.item(r,c).text().strip()
                name = read(1)
                p = deepcopy(self.original.get(name,{}))
                p.update(name=name,column=self.table.cellWidget(r,2).currentText(),unit=read(3),standard_unit=read(4),
                         lower=float(read(5)) if read(5) else None,upper=float(read(6)) if read(6) else None,
                         ideal=float(read(7) or 0),weight=float(read(8) or 1),rating=self.table.cellWidget(r,9).currentText(),
                         edition=read(10),amendment=read(11),publication_year=int(read(12)),source=read(13),page=read(14),
                         verification=self.table.cellWidget(r,15).currentText())
                old = self.original.get(name,{})
                if any(p.get(k)!=old.get(k) for k in ('lower','upper','standard_unit','edition','amendment','publication_year','source','page')):
                    p['verification'] = 'verified' if self.reviewed.isChecked() else 'unverified'
                    p['notes'] = 'User-edited limit; '+('source reviewed by user.' if self.reviewed.isChecked() else 'source verification required.')
                p.setdefault('standard_id',self.profile['standard_id']);p.setdefault('limit_kind',self.profile['limit_kind'])
                parameters.append(p)
            self.parameters = validate_parameters(parameters)
        except (ValueError,TypeError,KeyError) as exc:
            QMessageBox.warning(self,'Review index parameters',str(exc));return
        super().accept()


class ClassificationDialog(QDialog):
    def __init__(self,scheme,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Classification scheme')
        self.scheme = deepcopy(scheme)
        layout = QVBoxLayout(self);form = QFormLayout();layout.addLayout(form)
        self.name = QLineEdit(scheme['name']);form.addRow('Scheme name',self.name)
        self.cuts = QLineEdit(', '.join(map(str,scheme['cuts'])));form.addRow('Four increasing boundaries',self.cuts)
        self.labels = QLineEdit(', '.join(scheme['labels']));form.addRow('Five labels (ascending score)',self.labels)
        self.colors = QLineEdit(', '.join(scheme['colors']));form.addRow('Five colours (ascending score)',self.colors)
        self.closed = QComboBox();self.closed.addItems(['upper','lower']);self.closed.setCurrentText(scheme['closed']);form.addRow('Boundary belongs to interval',self.closed)
        note = QLabel(f'Score direction: {scheme["direction"]} is better. Upper includes a boundary in the lower-score class; lower includes it in the higher-score class. CCME categories describe objective attainment, not drinking-water safety.')
        note.setWordWrap(True);layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.resize(700,310)

    def accept(self):
        try:
            self.scheme = validate_scheme(dict(self.scheme,name=self.name.text().strip(),cuts=[float(v) for v in self.cuts.text().split(',')],
                labels=[v.strip() for v in self.labels.text().split(',')],colors=[v.strip() for v in self.colors.text().split(',')],closed=self.closed.currentText()))
        except ValueError as exc:
            QMessageBox.warning(self,'Invalid classification',str(exc));return
        super().accept()
