"""PHREEQC and imported SI in AquaProv's shared project and plotting interface."""
from copy import deepcopy
from pathlib import Path
import re

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox)

from ..base import ModuleWorkspace
from ..maps.boundary_ui import BoundaryWorkspaceMixin
from .spatial_ui import SISpatialWorkspaceMixin
from ..maps import spatial_controls
from ...ui.loading import plot_loading, run_worker
from ...ui.colour_scale import ColourScaleCombo
from ...saturation.backend import BUILTIN_DATABASES, database_snapshot, resolve_database
from ...saturation.data import COMMON_MINERALS, SPATIAL_VIEWS, VIEWS, infer_si_columns, labels
from ...saturation.automatic import chemistry_mapping, dataset_signature, supported_minerals

SHARED = {'si_mode_combo','si_layout_combo','si_sample_combo','si_group_combo','si_group_value_combo',
          'si_phase_combo','si_value_combo','si_import_database_edit','si_database_combo','si_ph_combo',
          'si_temperature_combo','si_temperature_spin','si_redox_combo','si_redox_column_combo','si_redox_spin',
          'si_density_combo','si_density_spin',
          'si_missing_combo','si_review_check','distance_combo','map_x_combo','map_y_combo','map_crs_combo',
          'map_zone_spin','map_hemisphere_combo','analysis_crs_edit','spatial_source_crs_edit'}


class SaturationWorkspace(SISpatialWorkspaceMixin,BoundaryWorkspaceMixin,ModuleWorkspace):
    module_key = 'saturation'

    def load_data(self):
        path,_ = QFileDialog.getOpenFileName(self,'Import PHREEQC SI or groundwater chemistry','',
            'Data files (*.csv *.xlsx *.xls);;CSV or tab-delimited CSV (*.csv);;Excel workbooks (*.xlsx *.xls)')
        if path:
            self._load_si_source(Path(path))

    def load_selected_sheet(self,sheet):
        if self.source_path and self.excel_sheets and sheet:
            self._load_si_source(self.source_path,sheet)

    def _load_si_source(self,path,sheet=None):
        from ...saturation.io import read_si_dataset
        try:
            with self.plot_loader.busy('Importing SI / groundwater data…',path.name):
                frame,sheets,selected = run_worker(lambda:read_si_dataset(path,sheet))
                self.source_path,self.excel_sheets = path,sheets
                with QSignalBlocker(self.sheet_combo):
                    self.sheet_combo.clear()
                    self.sheet_combo.addItems(sheets)
                    if selected:
                        self.sheet_combo.setCurrentText(selected)
                    self.sheet_combo.setVisible(len(sheets)>1)
                self._accept_frame(frame)
        except Exception as exc:
            QMessageBox.critical(self,'Could not import SI / groundwater data',str(exc))

    def __init__(self):
        self.study_boundary = None
        self.si_parameters = []
        self.si_columns = {}
        self.si_samples = None
        self.si_database_snapshot = None
        self._si_mapping_notes, self._si_mapping_problems = [], []
        self._si_detection_error = None
        self._si_signature = None
        self._si_basemaps = []
        super().__init__()
        self.chart_card.hide()
        self.analysis_card.hide()
        self.exploration_card.hide()
        self.map_background_combo.setCurrentIndex(self.map_background_combo.findData('plain'))
        self.map_value_combo.parentWidget().hide()
        self.map_label_combo.parentWidget().hide()
        for button in self.location_card.findChildren(QPushButton):
            button.hide()
        self.preview_tabs.setTabVisible(self.preview_tabs.indexOf(self.map_page),False)

        def combo(name, choices):
            control = QComboBox()
            for title,value in choices:
                control.addItem(title,value)
            setattr(self,name,control)
            return control

        def spin(name,lo,hi,value,decimals=None):
            control = QDoubleSpinBox() if decimals is not None else QSpinBox()
            if decimals is not None:
                control.setDecimals(decimals)
            control.setRange(lo,hi)
            control.setValue(value)
            setattr(self,name,control)
            return control

        self.si_input_card,layout = self._card('Mineral saturation data',
            'Load CSV / Excel here or in another module. Automatic mode uses existing SI results or calculates them from water chemistry with PHREEQC.')
        self.si_mode_combo = combo('si_mode_combo',[('Automatic: detect SI or water chemistry','auto'),
            ('Import PHREEQC saturation indices','import'),('Calculate with PHREEQC','calculate')])
        self.si_layout_combo = combo('si_layout_combo',[('Wide: one SI column per mineral','wide'),('Long: mineral and SI columns','long')])
        self.si_sample_combo = QComboBox()
        self.si_phase_combo = QComboBox()
        self.si_value_combo = QComboBox()
        self.si_import_database_edit = QLineEdit()
        self.si_import_database_edit.setPlaceholderText('Database / version stated by the source (if known)')
        for title,widget in [('Source',self.si_mode_combo),('Sample / event identifier',self.si_sample_combo),
                             ('Imported table format',self.si_layout_combo),('Mineral-name column',self.si_phase_combo),
                             ('SI value column',self.si_value_combo),('Imported database provenance',self.si_import_database_edit)]:
            self._add_field(layout,title,widget)
        self.si_source_note = QLabel()
        self.si_source_note.setWordWrap(True)
        layout.addWidget(self.si_source_note)
        self.si_mapping_button = QPushButton('Review imported mineral → SI columns…')
        self.si_mapping_button.clicked.connect(self.edit_si_columns)
        layout.addWidget(self.si_mapping_button)
        self.control_tabs.widget(0).widget().layout().insertWidget(1,self.si_input_card)

        self.si_chemistry_card,layout = self._card('PHREEQC solution settings',
            'SI = log10(IAP/K). The selected database controls aqueous speciation, ion activities and phase constants. '
            'No mineral equilibration or automatic charge balancing is applied.')
        self.si_database_combo = combo('si_database_combo',[(name,name) for name in BUILTIN_DATABASES]+[('Custom database (embedded in project)','custom')])
        self.si_database_button = QPushButton('Choose another thermodynamic database (.dat)…')
        self.si_database_button.clicked.connect(self.choose_database)
        self.si_database_note = QLabel('USGS PHREEQC 3.7.3 databases; IPhreeqc 3.7.3 is included for Windows x64.')
        self.si_database_note.setWordWrap(True)
        self._add_field(layout,'Thermodynamic database',self.si_database_combo)
        layout.addWidget(self.si_database_button)
        layout.addWidget(self.si_database_note)
        self.si_ph_combo,self.si_temperature_combo,self.si_redox_column_combo = QComboBox(),QComboBox(),QComboBox()
        self.si_density_combo = QComboBox()
        self.si_redox_combo = combo('si_redox_combo',[('No imposed redox; restrict iron SI','none'),('pe (measured or explicitly assumed)','pe'),('Eh, mV versus SHE','eh_mv')])
        for title,widget in [('Measured pH column',self.si_ph_combo),('Temperature column (°C)',self.si_temperature_combo),
            ('Constant temperature (°C)',spin('si_temperature_spin',0,100,25,2)),
            ('Density column (kg/L)',self.si_density_combo),('Constant density (kg/L)',spin('si_density_spin',.8,1.5,1,4)),
            ('Redox condition',self.si_redox_combo),
            ('Redox measurement column',self.si_redox_column_combo),('Constant pe / Eh (mV)',spin('si_redox_spin',-1500,1500,4,4))]:
            self._add_field(layout,title,widget)
        self.si_missing_combo = combo('si_missing_combo',[('Stop on incomplete mapped chemistry','raise'),('Exclude incomplete samples and report','drop')])
        self._add_field(layout,'Incomplete chemistry',self.si_missing_combo)
        self.si_chemistry_button = QPushButton('Map dissolved chemistry and units…')
        self.si_chemistry_button.setToolTip('Review dissolved concentrations, source columns, units and analytical reporting bases.')
        self.si_chemistry_button.clicked.connect(self.edit_chemistry)
        layout.addWidget(self.si_chemistry_button)
        self.si_chemistry_note = QLabel()
        self.si_chemistry_note.setWordWrap(True)
        layout.addWidget(self.si_chemistry_note)
        self.si_review_check = QCheckBox('I reviewed units, chemical basis\nand solution conditions')
        layout.addWidget(self.si_review_check)
        self.control_tabs.widget(0).widget().layout().insertWidget(2,self.si_chemistry_card)

        self.si_filter_card,layout = self._card('Minerals, samples and groups',
            'Classification uses the exact SI sign. Missing values remain unassessed. All figures and summaries follow these filters.')
        self.si_mineral_list = QListWidget()
        self.si_mineral_list.setMinimumHeight(150)
        layout.addWidget(self.si_mineral_list)
        self.si_add_mineral_edit = QLineEdit()
        self.si_add_mineral_edit.setPlaceholderText('Another PHREEQC phase name')
        layout.addWidget(self.si_add_mineral_edit)
        add = QPushButton('Add mineral')
        add.clicked.connect(self.add_mineral)
        layout.addWidget(add)
        self.si_group_combo,self.si_group_value_combo = QComboBox(),QComboBox()
        self._add_field(layout,'Group / season column',self.si_group_combo)
        self._add_field(layout,'Show group / season',self.si_group_value_combo)
        self.si_samples_button = QPushButton('Compare samples: all selected…')
        self.si_samples_button.clicked.connect(self.choose_samples)
        layout.addWidget(self.si_samples_button)
        self.control_tabs.widget(0).widget().layout().insertWidget(3,self.si_filter_card)

        self.si_plot_card,layout = self._card('SI figure settings')
        self.si_view_combo = combo('si_view_combo',[(title,key) for key,title in VIEWS.items()])
        self.si_mineral_combo,self.si_scatter_mineral_combo,self.si_scatter_column_combo = QComboBox(),QComboBox(),QComboBox()
        self.si_scatter_kind_combo = combo('si_scatter_kind_combo',[('Another mineral SI','mineral'),('Groundwater measurement','measurement')])
        self.si_cmap_combo = ColourScaleCombo(default='RdBu_r', normalization=self.style_controls['normalize_cmap'])
        for title,widget in [('View',self.si_view_combo),('Mapped / Y-axis mineral',self.si_mineral_combo),
                             ('Scatter X axis',self.si_scatter_kind_combo),('X-axis mineral',self.si_scatter_mineral_combo),
                             ('X-axis measurement',self.si_scatter_column_combo),('Colour scale',self.si_cmap_combo)]:
            self._add_field(layout,title,widget)
        self.si_scale_check = QCheckBox('Use a fixed symmetric SI colour scale')
        layout.addWidget(self.si_scale_check)
        self._add_field(layout,'Scale extent (−SI to +SI)',spin('si_limit_spin',.01,1000,5,2))
        self.si_annotate_check = QCheckBox('Annotate heatmap values when there is space')
        self.si_percent_check = QCheckBox('Distribution as percent of assessed observations')
        self.si_points_check = QCheckBox('Show observed samples over interpolation')
        self.si_distribution_points_check = QCheckBox('Show individual points over distributions')
        self.si_distribution_points_check.setChecked(True)
        layout.addWidget(self.si_distribution_points_check)
        self.si_class_colors_check = QCheckBox('Colour points by SI classification')
        self.si_class_colors_check.setChecked(True)
        layout.addWidget(self.si_class_colors_check)
        self.si_labels_check = QCheckBox('Label mapped samples and SI')
        self.si_north_check = QCheckBox('Show grid north arrow (+Y)')
        for control in (self.si_annotate_check,self.si_percent_check,self.si_points_check,self.si_labels_check,self.si_north_check):
            control.setChecked(control in (self.si_annotate_check,self.si_percent_check,self.si_points_check))
            layout.addWidget(control)
        self.control_tabs.widget(1).widget().layout().insertWidget(0,self.si_plot_card)

        self.si_spatial_card,layout = self._card('SI spatial interpolation',
            'Interpolation requires distinct, non-collinear sample locations. An enabled study boundary is filled by default; disable full coverage to restrict predictions to the sampled area.')
        self.distance_combo = combo('distance_combo',[('(choose coordinate distances)',None),('Projected / local X and Y','projected'),('WGS84 longitude / latitude → local metres','wgs84')])
        self.si_interpolation_combo = combo('si_interpolation_combo',[('Inverse distance weighting','idw'),('Ordinary kriging','kriging')])
        self.si_variogram_combo = QComboBox()
        self.si_variogram_combo.addItems(['spherical','exponential'])
        for title,widget in [('Distance coordinates',self.distance_combo),('Method',self.si_interpolation_combo),
            ('Variogram',self.si_variogram_combo),('Range (distance units)',spin('si_range_spin',.000001,1e9,1000,6)),
            ('Partial sill (SI²)',spin('si_sill_spin',.000001,1e6,1,6)),('Nugget (SI²)',spin('si_nugget_spin',0,1e6,0,6)),
            ('IDW power',spin('si_power_spin',.1,10,2,2)),('Grid cells per axis',spin('si_grid_spin',20,160,70))]:
            self._add_field(layout,title,widget)
        self.control_tabs.widget(1).widget().layout().insertWidget(1,self.si_spatial_card)
        self._build_si_map_controls(spin)
        self.initialize_boundary_controls()
        self.si_group_combo.currentIndexChanged.connect(self._populate_groups)
        self.si_mode_combo.currentIndexChanged.connect(self._source_mode_changed)
        self.si_layout_combo.currentIndexChanged.connect(self._refresh_import_minerals)
        self.si_phase_combo.currentIndexChanged.connect(self._refresh_import_minerals)
        self.si_sample_combo.currentIndexChanged.connect(self._sample_column_changed)
        self.si_database_combo.currentIndexChanged.connect(self._database_changed)
        for control in (self.si_layout_combo,self.si_scatter_kind_combo,self.si_interpolation_combo,self.si_redox_combo,
                        self.si_temperature_combo,self.si_redox_column_combo,self.si_density_combo):
            control.currentIndexChanged.connect(self._analysis_controls_changed)
        self.si_scale_check.toggled.connect(self._analysis_controls_changed)
        self._set_minerals(COMMON_MINERALS)
        from ...chart_controls import add_fields, build_reference_controls
        self.si_box_card, box_layout = self._card('Distribution and point appearance')
        add_fields(self, box_layout, [
            ('si_box_width_spin','Box width',.55,(.1,.95)),
            ('si_box_edge_color_edit','Box / whisker colour','#243447'),
            ('si_box_edge_width_spin','Box / whisker width (pt)',.6,(0,5)),
            ('si_median_color_edit','Median colour','#173b4c'),
            ('si_median_width_spin','Median width (pt)',1.,(.1,6)),
            ('si_counts_check','Show mineral sample counts',True),
            ('si_fliers_check','Show outliers when individual points are hidden',True),
            ('si_point_edge_color_edit','Point outline colour','#ffffff'),
            ('si_point_edge_width_spin','Point outline width (pt)',.3,(0,5)),
        ])
        self.control_tabs.widget(1).widget().layout().insertWidget(1,self.si_box_card)
        build_reference_controls(self,x=True)
        self.connect_settings()
        self.si_mineral_list.itemChanged.connect(self._mineral_changed)
        self.populate_module_columns()

    def _set_minerals(self, names, selected=None):
        with QSignalBlocker(self.si_mineral_list):
            self.si_mineral_list.clear()
            for name in dict.fromkeys(names):
                item = QListWidgetItem(name,self.si_mineral_list)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if selected is None or name in selected else Qt.CheckState.Unchecked)
        self._populate_mineral_axes()

    def _selected_minerals(self):
        return [self.si_mineral_list.item(i).text() for i in range(self.si_mineral_list.count())
                if self.si_mineral_list.item(i).checkState() == Qt.CheckState.Checked]

    def _populate_mineral_axes(self):
        names = self._selected_minerals()
        for combo in (self.si_mineral_combo,self.si_scatter_mineral_combo):
            with QSignalBlocker(combo):
                previous = combo.currentText()
                combo.clear()
                combo.addItems(names)
                if previous in names:
                    combo.setCurrentText(previous)
        if len(names)>1 and self.si_mineral_combo.currentText()==self.si_scatter_mineral_combo.currentText():
            self.si_scatter_mineral_combo.setCurrentIndex(1)

    def _mineral_changed(self,*_):
        self._populate_mineral_axes()
        self._clear_plot_cache()
        self._setting_changed()

    def _source_mode_changed(self,*_):
        if self._restoring:
            return
        self._choose_input_minerals()
        if self.si_mode_combo.currentData()=='auto' and self._input_mode()=='calculate':
            self.si_missing_combo.setCurrentIndex(self.si_missing_combo.findData('drop'))
        self._clear_plot_cache()
        self._analysis_controls_changed()

    def _input_mode(self):
        mode = self.si_mode_combo.currentData()
        if mode != 'auto':
            return mode
        long = (self.si_layout_combo.currentData()=='long' and self.si_phase_combo.currentData()
                and self.si_value_combo.currentData())
        return 'import' if self.si_columns or long or self._si_detection_error else 'calculate'

    def _choose_input_minerals(self):
        if self._input_mode()=='import':
            column = self.si_phase_combo.currentData()
            if self.data is not None and self.si_layout_combo.currentData()=='long' and column in self.data:
                values = [str(v).strip() for v in self.data[column].dropna().unique()]
                names = [next((m for m in COMMON_MINERALS if m.casefold()==v.casefold()),v) for v in values]
            else:
                names = self.si_columns or COMMON_MINERALS
            self._set_minerals(names)
        else:
            selected = (supported_minerals(self.si_parameters,self.si_redox_combo.currentData())
                        if self.si_mode_combo.currentData()=='auto' else None)
            self._set_minerals(COMMON_MINERALS,selected)

    def _refresh_import_minerals(self,*_):
        if self._restoring or self.data is None or self._input_mode()!='import':
            return
        column = self.si_phase_combo.currentData()
        if self.si_layout_combo.currentData()=='long' and column in self.data:
            values = [str(v).strip() for v in self.data[column].dropna().unique()]
            names = [next((m for m in COMMON_MINERALS if m.casefold()==v.casefold()),v) for v in values]
        else:
            names = list(self.si_columns) or list(COMMON_MINERALS)
        self._set_minerals(names)
        self._clear_plot_cache()

    def _sample_column_changed(self,*_):
        if not self._restoring:
            self.si_samples = None
            self._refresh_samples_note()

    def _database_changed(self,*_):
        if not self._restoring:
            self.si_review_check.setChecked(False)
        self._clear_plot_cache()

    def _setting_changed(self,*args,update_kind=None):
        if not self._restoring and self.sender() in {getattr(self,name,None) for name in SHARED}:
            self._clear_plot_cache()
        super()._setting_changed(*args,update_kind=update_kind)

    def populate_module_columns(self):
        super().populate_module_columns()
        if not hasattr(self,'si_sample_combo'):
            return
        columns = list(self.data.columns) if self.data is not None else []
        candidates = [(self.si_sample_combo,['Sample','Site','Well','soln']), (self.si_group_combo,['Season','Group','Label']),
            (self.si_phase_combo,['Mineral','mineral','Phase','phase']), (self.si_value_combo,['SI','si','SaturationIndex']),
            (self.si_ph_combo,['pH']), (self.si_temperature_combo,['Temperature','temp','Temperature_C','Temp_C','Water temperature C']),
            (self.si_density_combo,['Density','Density_kg_L','Density_g_cm3']),
            (self.si_redox_column_combo,[]), (self.si_scatter_column_combo,['pH','Ca','EC'])]
        for combo,matches in candidates:
            with QSignalBlocker(combo):
                combo.clear()
                combo.addItem('(none / constant if configured)',None)
                for column in columns:
                    combo.addItem(column,column)
                keys = {re.sub(r'[^a-z0-9]','',m.lower()) for m in matches}
                match = next((c for c in columns if re.sub(r'[^a-z0-9]','',c.lower()) in keys),None)
                if match:
                    combo.setCurrentIndex(combo.findData(match))
        self.si_samples = None
        self.si_review_check.setChecked(False)
        self.distance_combo.setCurrentIndex(0)
        self.analysis_crs_edit.clear()
        self.spatial_source_crs_edit.clear()
        self.boundary_extrapolate_check.setChecked(True)
        self._si_signature = dataset_signature(self.data)
        self.si_parameters,self._si_mapping_notes,self._si_mapping_problems = chemistry_mapping(self.data)
        self._si_detection_error = None
        try:
            self.si_columns = infer_si_columns(self.data) if self.data is not None else {}
        except ValueError as exc:
            self.si_columns = {}
            self._si_detection_error = str(exc)
        with QSignalBlocker(self.si_layout_combo):
            layout = 'long' if not self.si_columns and self.si_phase_combo.currentData() and self.si_value_combo.currentData() else 'wide'
            self.si_layout_combo.setCurrentIndex(self.si_layout_combo.findData(layout))
        if self.si_mode_combo.currentData()=='auto':
            for control,value in ((self.si_temperature_spin,25),(self.si_density_spin,1)):
                with QSignalBlocker(control):
                    control.setValue(value)
            with QSignalBlocker(self.si_redox_combo):
                self.si_redox_combo.setCurrentIndex(self.si_redox_combo.findData('none'))
            with QSignalBlocker(self.si_missing_combo):
                self.si_missing_combo.setCurrentIndex(self.si_missing_combo.findData('drop'))
            longitude = next((c for c in columns if c.lower().startswith('longitude')),None)
            latitude = next((c for c in columns if c.lower().startswith('latitude')),None)
            if longitude and latitude:
                for control,value in ((self.map_x_combo,longitude),(self.map_y_combo,latitude)):
                    with QSignalBlocker(control):
                        control.setCurrentText(value)
                with QSignalBlocker(self.distance_combo):
                    self.distance_combo.setCurrentIndex(self.distance_combo.findData('wgs84'))
                with QSignalBlocker(self.map_crs_combo):
                    self.map_crs_combo.setCurrentIndex(self.map_crs_combo.findData('wgs84'))
        self._choose_input_minerals()
        self._populate_groups()
        self._refresh_chemistry_note()
        self._refresh_samples_note()
        self._analysis_controls_changed()

    def _populate_groups(self,*_):
        if not hasattr(self,'si_group_value_combo'):
            return
        column = self.si_group_combo.currentData()
        values = list(dict.fromkeys(self.data[column].fillna('(missing)').astype(str))) if self.data is not None and column in self.data else []
        with QSignalBlocker(self.si_group_value_combo):
            previous = self.si_group_value_combo.currentData()
            self.si_group_value_combo.clear()
            self.si_group_value_combo.addItem('All groups',None)
            for value in values:
                self.si_group_value_combo.addItem(value,value)
            if previous in values:
                self.si_group_value_combo.setCurrentIndex(self.si_group_value_combo.findData(previous))

    def _refresh_chemistry_note(self):
        if hasattr(self,'si_chemistry_note'):
            self.si_chemistry_note.setText(f'{len(self.si_parameters)} mapped dissolved parameters. '
                'Check alkalinity/DIC and silica reporting basis. Omitted ions can affect ionic strength. '
                'Review density for saline waters; pressure is PHREEQC’s default 1 atm.')

    def edit_chemistry(self):
        if self.data is None:
            QMessageBox.information(self,'Import data','Import groundwater measurements first.')
            return
        from .dialogs import ChemistryDialog
        dialog = ChemistryDialog(self.data,self.si_parameters,self)
        if dialog.exec():
            self.si_parameters = dialog.parameters
            self._si_mapping_notes, self._si_mapping_problems = [], []
            self.si_review_check.setChecked(False)
            self._refresh_chemistry_note()
            self._clear_plot_cache()
            self._setting_changed()

    def edit_si_columns(self):
        if self.data is None:
            QMessageBox.information(self,'Import data','Import PHREEQC output first.')
            return
        from .dialogs import SIColumnDialog
        dialog = SIColumnDialog(self.data,self.si_columns,self)
        if dialog.exec():
            self.si_columns = dialog.mapping
            self._set_minerals(self.si_columns)
            self._clear_plot_cache()
            self._setting_changed()

    def add_mineral(self):
        name = self.si_add_mineral_edit.text().strip()
        if name:
            names = [self.si_mineral_list.item(i).text() for i in range(self.si_mineral_list.count())]
            self._set_minerals([*names,name],[*self._selected_minerals(),name])
            self.si_add_mineral_edit.clear()
            self._mineral_changed()

    def choose_database(self):
        path,_ = QFileDialog.getOpenFileName(self,'Choose PHREEQC thermodynamic database','','PHREEQC databases (*.dat);;All files (*)')
        if not path:
            return
        try:
            self.si_database_snapshot = database_snapshot(path)
            self.si_database_combo.setCurrentIndex(self.si_database_combo.findData('custom'))
            self.si_database_note.setText('Embedded custom database: '+self.si_database_snapshot['name']+'\nSHA256: '+self.si_database_snapshot['sha256'][:16])
            self._database_changed()
            self._setting_changed()
        except (OSError,ValueError,UnicodeError) as exc:
            QMessageBox.warning(self,'Could not load database',str(exc))

    def choose_samples(self):
        if self.data is None:
            return
        from .dialogs import SampleDialog
        try:
            values = labels(self.data,self.si_sample_combo.currentData())
            dialog = SampleDialog(values,self.si_samples,self)
            if dialog.exec():
                self.si_samples = None if len(dialog.samples)==len(set(values)) else dialog.samples
                self._refresh_samples_note()
                self._clear_plot_cache()
                self._setting_changed()
        except ValueError as exc:
            QMessageBox.warning(self,'Sample selection',str(exc))

    def _refresh_samples_note(self):
        self.si_samples_button.setText('Compare samples: '+('all selected…' if self.si_samples is None else f'{len(self.si_samples)} selected…'))

    def _analysis_controls_changed(self,*_):
        if hasattr(self,'analysis_card'):
            self.analysis_card.hide()
            self.exploration_card.hide()
        if not hasattr(self,'si_spatial_card'):
            return
        imported = self._input_mode()=='import'
        automatic = self.si_mode_combo.currentData()=='auto'
        long = self.si_layout_combo.currentData()=='long'
        self.si_chemistry_card.setVisible(not imported)
        self.si_review_check.setVisible(not imported and not automatic)
        if self.data is None:
            note = 'Import data to detect existing SI results or water chemistry.'
        elif imported:
            note = 'Existing SI results detected. Imported values are used without recalculation.' if automatic else 'Using imported SI values.'
        else:
            note = ('Water chemistry detected. PHREEQC calculates SI automatically. ' if automatic else 'Calculate SI from mapped water chemistry. ')
            if not self.si_temperature_combo.currentData():
                note += f'Temperature assumed: {self.si_temperature_spin.value():g} °C. '
            if not self.si_density_combo.currentData():
                note += f'Density assumed: {self.si_density_spin.value():g} kg/L. '
            if self.si_missing_combo.currentData()=='drop':
                note += 'Incomplete mapped samples are excluded and reported. '
            note += 'Input units and reporting bases are shown in Map dissolved chemistry and units and saved with the results.'
        self.si_source_note.setText(note)
        for control in (self.si_layout_combo,self.si_import_database_edit):
            control.parentWidget().setVisible(imported)
        for control in (self.si_phase_combo,self.si_value_combo):
            control.parentWidget().setVisible(imported and long)
        self.si_mapping_button.setVisible(imported and not long)
        view = self.si_view_combo.currentData()
        spatial = view in SPATIAL_VIEWS
        self.location_card.setVisible(spatial)
        self.si_spatial_card.setVisible(spatial)
        self.boundary_card.setVisible(spatial)
        for control in (self.si_range_spin,self.si_sill_spin,self.si_nugget_spin,self.si_variogram_combo):
            control.parentWidget().setVisible(view=='interpolation' and self.si_interpolation_combo.currentData()=='kriging')
        for control in (self.si_interpolation_combo,self.si_grid_spin):
            control.parentWidget().setVisible(view=='interpolation')
        self.si_power_spin.parentWidget().setVisible(view=='interpolation' and self.si_interpolation_combo.currentData()=='idw')
        self.si_mineral_combo.parentWidget().setVisible(spatial or view=='scatter')
        self.si_scatter_kind_combo.parentWidget().setVisible(view=='scatter')
        self.si_scatter_mineral_combo.parentWidget().setVisible(view=='scatter' and self.si_scatter_kind_combo.currentData()=='mineral')
        self.si_scatter_column_combo.parentWidget().setVisible(view=='scatter' and self.si_scatter_kind_combo.currentData()=='measurement')
        self.si_cmap_combo.parentWidget().setVisible(spatial or view=='heatmap')
        self.si_scale_check.setVisible(spatial or view=='heatmap')
        self.si_limit_spin.parentWidget().setVisible((spatial or view=='heatmap') and self.si_scale_check.isChecked())
        self.si_annotate_check.setVisible(view=='heatmap')
        self.si_percent_check.setVisible(view=='distribution')
        self.si_points_check.setVisible(view=='interpolation')
        self.si_distribution_points_check.setVisible(view in ('box', 'violin'))
        self.si_class_colors_check.setVisible(view in ('box', 'violin', 'scatter'))
        if hasattr(self,'si_box_card'):
            self.si_box_card.setVisible(view in ('box','violin','scatter'))
            self.reference_card.setVisible(view in ('box','violin','scatter'))
            self.reference_x_check.setVisible(view=='scatter')
            self.reference_y_check.setVisible(view=='scatter')
            for widget in (self.si_box_width_spin,self.si_box_edge_color_edit,self.si_box_edge_width_spin,self.si_median_color_edit,self.si_median_width_spin):
                widget.parentWidget().setVisible(view=='box')
            self.si_counts_check.setVisible(view in ('box','violin'))
            self.si_fliers_check.setVisible(view=='box')
        self.si_labels_check.setVisible(spatial)
        self.si_north_check.setVisible(spatial)
        self._update_si_map_controls(spatial, view=='interpolation')
        self.si_temperature_spin.parentWidget().setVisible(self.si_temperature_combo.currentData() is None)
        self.si_density_spin.parentWidget().setVisible(self.si_density_combo.currentData() is None)
        self.si_redox_column_combo.parentWidget().setVisible(self.si_redox_combo.currentData()!='none')
        self.si_redox_spin.parentWidget().setVisible(self.si_redox_combo.currentData()!='none' and self.si_redox_column_combo.currentData() is None)
        if hasattr(self,'_active_plot'):
            self.si_view_combo.parentWidget().hide()

    def refresh_contextual_controls(self):
        self.chart_card.hide()
        self.appearance_card.show()
        self.label_combo.parentWidget().hide()
        self.color_combo.parentWidget().hide()
        self._analysis_controls_changed()

    def _capture_current_state(self):
        state = super()._capture_current_state()
        if hasattr(self,'si_mineral_list'):
            state.update(si_parameters=deepcopy(self.si_parameters),si_columns=deepcopy(self.si_columns),
                si_samples=deepcopy(self.si_samples),si_database_snapshot=deepcopy(self.si_database_snapshot),
                si_minerals=[self.si_mineral_list.item(i).text() for i in range(self.si_mineral_list.count())],
                si_selected_minerals=self._selected_minerals(),si_dataset_signature=self._si_signature,
                si_input_mode_version=1,si_mapping_notes=list(self._si_mapping_notes),
                si_mapping_problems=list(self._si_mapping_problems))
        return state

    def _capture_profile(self):
        state = super()._capture_profile()
        for key in list(state):
            if key.startswith('si_'):
                state.pop(key)
        for key in SHARED:
            state['controls'].pop(key,None)
        return state

    def _restore_current_state(self,state):
        state = deepcopy(state)
        spatial_controls.restore_defaults(state, switching=getattr(self,'_switching_plot',False))
        legacy_mode = (not state.get('si_input_mode_version')
                       and state.get('controls',{}).get('si_mode_combo')=='Import PHREEQC saturation indices')
        different_data = (state.get('si_dataset_signature') is not None
                          and state['si_dataset_signature'] != self._si_signature)
        legacy_import = legacy_mode and not self.si_columns and self._input_mode()=='calculate'
        if legacy_mode:
            # Old projects saved Import as the unconditional default. Automatic
            # retains their SI mappings but can detect a later chemistry file.
            state['controls']['si_mode_combo']=self.si_mode_combo.itemText(self.si_mode_combo.findData('auto'))
        if different_data or legacy_import:
            for key in list(state):
                if key.startswith('si_'):
                    state.pop(key)
            for key in list(state.get('controls',{})):
                if key in SHARED:
                    state['controls'].pop(key)
        for key,attribute in (('si_mapping_notes','_si_mapping_notes'),('si_mapping_problems','_si_mapping_problems')):
            if key in state:
                setattr(self,attribute,list(state[key]))
        for key in ('si_parameters','si_columns','si_samples','si_database_snapshot'):
            if key in state:
                setattr(self,key,deepcopy(state[key]))
        if self.si_database_snapshot is not None:
            resolve_database(snapshot=self.si_database_snapshot)
            self.si_database_note.setText('Embedded custom database: '+self.si_database_snapshot['name'])
        if 'si_minerals' in state:
            self._set_minerals(state['si_minerals'],state.get('si_selected_minerals'))
        super()._restore_current_state(state)
        # Group values depend on the restored column. Reapply after populating it.
        saved = state.get('controls',{}).get('si_group_value_combo')
        self._populate_groups()
        if saved:
            with QSignalBlocker(self.si_group_value_combo):
                self.si_group_value_combo.setCurrentText(saved)
        self._refresh_samples_note()
        self._refresh_chemistry_note()

    def analysis_config(self):
        from ...chart_controls import reference_options
        mode = self._input_mode()
        automatic = self.si_mode_combo.currentData()=='auto' and mode=='calculate'
        if mode=='import' and self._si_detection_error and not self.si_columns:
            raise ValueError(self._si_detection_error)
        if automatic and self._si_mapping_problems:
            raise ValueError(' '.join(self._si_mapping_problems))
        if mode=='calculate' and not self._selected_minerals():
            raise ValueError('No selected minerals have mapped chemistry. Map pH and the measured ions/alkalinity in Data, then select the minerals to calculate.')
        custom = self.si_database_combo.currentData()=='custom'
        if mode=='calculate' and custom and self.si_database_snapshot is None:
            raise ValueError('Choose a custom thermodynamic database file first.')
        return dict(mode=mode,source_mode=self.si_mode_combo.currentData(),
            reference=reference_options(self),alpha=self.alpha_spin.value(),
            box_width=self.si_box_width_spin.value(),box_edge_color=self.si_box_edge_color_edit.text(),
            box_edge_width=self.si_box_edge_width_spin.value(),median_color=self.si_median_color_edit.text(),
            median_width=self.si_median_width_spin.value(),show_counts=self.si_counts_check.isChecked(),
            show_fliers=self.si_fliers_check.isChecked(),point_edge_color=self.si_point_edge_color_edit.text(),point_edge_width=self.si_point_edge_width_spin.value(),
            chemistry_setup='automatic' if automatic else 'reviewed',input_assumptions=list(self._si_mapping_notes),
            view=self.si_view_combo.currentData(),layout=self.si_layout_combo.currentData(),
            sample_column=self.si_sample_combo.currentData(),mineral_column=self.si_phase_combo.currentData(),si_column=self.si_value_combo.currentData(),
            si_columns=deepcopy(self.si_columns),import_database=self.si_import_database_edit.text().strip(),
            database=self.si_database_combo.currentData(),database_snapshot=deepcopy(self.si_database_snapshot) if custom else None,
            parameters=deepcopy(self.si_parameters),pH_column=self.si_ph_combo.currentData(),temperature_column=self.si_temperature_combo.currentData(),
            temperature_c=self.si_temperature_spin.value(),redox=self.si_redox_combo.currentData(),redox_column=self.si_redox_column_combo.currentData(),
            density_column=self.si_density_combo.currentData(),density_kg_L=self.si_density_spin.value(),
            redox_value=self.si_redox_spin.value(),chemistry_reviewed=self.si_review_check.isChecked(),missing=self.si_missing_combo.currentData(),
            minerals=self._selected_minerals(),samples=deepcopy(self.si_samples),group_column=self.si_group_combo.currentData(),group_value=self.si_group_value_combo.currentData(),
            mineral=self.si_mineral_combo.currentText(),scatter_kind=self.si_scatter_kind_combo.currentData(),scatter_x_mineral=self.si_scatter_mineral_combo.currentText(),
            scatter_column=self.si_scatter_column_combo.currentData(),cmap=self.si_cmap_combo.currentText(),
            color_limit=self.si_limit_spin.value() if self.si_scale_check.isChecked() else None,annotate=self.si_annotate_check.isChecked(),percent=self.si_percent_check.isChecked(),
            x=self.map_x_combo.currentText(),y=self.map_y_combo.currentText(),coordinates=self.distance_combo.currentData(),
            source_crs=spatial_controls.source_crs(self),boundary=self._active_boundary(), **spatial_controls.display_options(self),
            extrapolate=self._active_boundary() is not None and self.boundary_extrapolate_check.isChecked(),
            samples_inside_boundary=self._active_boundary() is not None and self.boundary_samples_check.isChecked(),
            spatial=dict(method=self.si_interpolation_combo.currentData(),resolution=self.si_grid_spin.value(),model=self.si_variogram_combo.currentText(),
                range_=self.si_range_spin.value(),sill=self.si_sill_spin.value(),nugget=self.si_nugget_spin.value(),power=self.si_power_spin.value(),**spatial_controls.interpolation_options(self)),
            show_samples=self.si_points_check.isChecked(),point_labels=self.si_labels_check.isChecked(),north_arrow=self.si_north_check.isChecked(),
            sample_size=self.size_spin.value(),marker=self.marker_combo.currentText(),color=self.color_button.text(),
            distribution_points=self.si_distribution_points_check.isChecked(),class_colors=self.si_class_colors_check.isChecked(),
            basemap=self._basemap_key() if self.si_view_combo.currentData() in SPATIAL_VIEWS
                and (self.si_view_combo.currentData()!='interpolation' or self.contour_basemap_check.isChecked()) else 'plain',
            **self._si_map_config())

    @plot_loading
    def generate(self):
        self._clear_analysis()
        self.generated_plot = None
        self.save_button.setEnabled(False)
        try:
            if self.data is None:
                raise ValueError('Import PHREEQC SI or groundwater chemistry first.')
            from ...saturation.plots import plot
            config,data = self.analysis_config(),self.data
            result = self._run_plot_job(lambda:plot(data.copy(deep=True),config))
            self.show_result(result,VIEWS[config['view']])
            self._attach_basemaps()
            self.statusBar().showMessage('SI analysis ready. Hover to inspect values; export figures, statistics, interpretations and methods.')
        except Exception as exc:
            self._report_plot_error('Could not generate mineral saturation analysis',exc)

    def _close_basemaps(self):
        for layer in self._si_basemaps:
            layer.close()
            layer.deleteLater()
        self._si_basemaps = []
        if hasattr(self,'si_basemap_retry_button'):
            self.si_basemap_retry_button.setEnabled(False)

    def _attach_basemaps(self):
        if self.analysis_result is None:
            return
        provider = self.analysis_result.metadata.get('config',{}).get('basemap','plain')
        if provider!='plain':
            from ...map_tiles import TileBasemap
            for ax in getattr(self.analysis_result.figure,'_aquaprov_si_map_axes',[]):
                for artist in list(ax.images):
                    artist.remove()
                layer = TileBasemap(ax,self.analysis_canvas,self,provider=provider)
                layer.status_changed.connect(self._si_basemap_status)
                self._si_basemaps.append(layer)
                layer.refresh()

    def _dispose_figure_view(self):
        self._close_basemaps()
        super()._dispose_figure_view()

    def _stash_plot(self):
        self._close_basemaps()
        super()._stash_plot()

    def _restore_cached_plot(self,key):
        restored = super()._restore_cached_plot(key)
        if restored:
            self._attach_basemaps()
        return restored
