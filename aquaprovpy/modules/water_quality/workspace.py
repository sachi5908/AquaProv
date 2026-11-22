"""Integrated WQI/DWQI controls, portable profiles, GIS, preview and exports."""
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDoubleSpinBox,QFileDialog,QLabel,QMessageBox,QPushButton,QSpinBox)

from ..base import ModuleWorkspace
from ..maps import spatial_controls
from ..maps.boundary_ui import BoundaryWorkspaceMixin
from ..three_d.workspace_tools import ThreeDWorkspaceToolsMixin
from ...ui.loading import plot_loading
from ...ui.colour_scale import ColourScaleCombo
from ...ui.color_button import ColorButton
from ...water_quality.common import SCHEMES,validate_parameters,validate_scheme
from ...water_quality.engine import METHODS,VIEWS,SPATIAL_VIEWS,SEASONAL_VIEWS,figure_title
from ...water_quality.standards import built_in_standards,import_standard,mapped_parameters,validate_standard


SHARED_CONTROLS = {'wq_method_combo','wq_standard_combo','wq_limit_combo','wq_site_combo','wq_time_combo','wq_season_combo',
                   'wq_pre_combo','wq_post_combo','wq_filter_combo','distance_combo','map_x_combo','map_y_combo','map_crs_combo',
                   'map_zone_spin','map_hemisphere_combo','analysis_crs_edit','spatial_source_crs_edit'}


class WaterQualityWorkspace(ThreeDWorkspaceToolsMixin,BoundaryWorkspaceMixin,ModuleWorkspace):
    module_key = 'water_quality'
    three_d_projection_name = 'wq_projection_combo'

    def __init__(self):
        self.study_boundary = None
        self.standards = built_in_standards()
        self.index_profiles = {name:dict(method='brown' if name=='WQI' else 'ramakrishnaiah',standard_id='WHO-2026',
            standard_name=self.standards['WHO-2026']['name'],limit_kind='guideline',parameters=[],
            scheme=deepcopy(SCHEMES['arithmetic' if name=='WQI' else 'relative'])) for name in METHODS}
        self._syncing_index = False
        self._index_basemaps = []
        super().__init__()
        self.chart_card.hide();self.analysis_card.hide();self.exploration_card.hide()
        self.map_background_combo.setCurrentIndex(self.map_background_combo.findData('plain'))
        self.map_value_combo.parentWidget().hide();self.map_label_combo.parentWidget().hide()
        for button in self.location_card.findChildren(QPushButton):button.hide()
        self.preview_tabs.setTabVisible(self.preview_tabs.indexOf(self.map_page),False)
        self.method_card,layout = self._card('Index calculation','WQI and DWQI retain independent methods, standards, parameters and classes across all views.')
        self.wq_index_combo = QComboBox();self.wq_index_combo.addItems(METHODS)
        self.wq_view_combo = QComboBox()
        for key,title in VIEWS.items():self.wq_view_combo.addItem(title,key)
        self.wq_method_combo = QComboBox()
        self.wq_standard_combo = QComboBox()
        self.wq_limit_combo = QComboBox()
        for label,widget in [('Index',self.wq_index_combo),('View',self.wq_view_combo),('Methodology',self.wq_method_combo),
                             ('Standards database',self.wq_standard_combo),('Limit category',self.wq_limit_combo)]:self._add_field(layout,label,widget)
        self.method_note = QLabel();self.method_note.setWordWrap(True);layout.addWidget(self.method_note)
        self.parameters_button = QPushButton('Review parameters, weights, units and limits…');self.parameters_button.clicked.connect(self.edit_parameters);layout.addWidget(self.parameters_button)
        self.classification_button = QPushButton('Edit classification thresholds and colours…');self.classification_button.clicked.connect(self.edit_classification);layout.addWidget(self.classification_button)
        self.standards_import_button = QPushButton('Import reviewed standards (JSON / CSV)…');self.standards_import_button.clicked.connect(self.import_standards);layout.addWidget(self.standards_import_button)
        self.standards_export_button = QPushButton('Export selected standards / update template…');self.standards_export_button.clicked.connect(self.export_standards);layout.addWidget(self.standards_export_button)
        self.control_tabs.widget(1).widget().layout().insertWidget(0,self.method_card)
        self.season_card,layout = self._card('Sampling sites and seasons','Use site identifiers to compare repeated measurements. CCME additionally requires distinct sampling occasions.')
        self.wq_site_combo = QComboBox();self.wq_time_combo = QComboBox();self.wq_season_combo = QComboBox()
        self.wq_filter_combo = QComboBox();self.wq_pre_combo = QComboBox();self.wq_post_combo = QComboBox()
        for label,widget in [('Sample / site column',self.wq_site_combo),('Sampling occasion (CCME)',self.wq_time_combo),
            ('Season / assessment-period column',self.wq_season_combo),('Show season',self.wq_filter_combo),
            ('First season',self.wq_pre_combo),('Second season',self.wq_post_combo)]:self._add_field(layout,label,widget)
        self.control_tabs.widget(0).widget().layout().insertWidget(1,self.season_card)
        self.spatial_card,layout = self._card('Index interpolation','Interpolate calculated indices. Kriging range is in distance units; partial sill and nugget are in squared index units.')
        self.distance_combo = QComboBox()
        for title,value in [('(choose distance coordinates)',None),('Projected / local X and Y','projected'),('WGS84 longitude / latitude → local metres','wgs84')]:self.distance_combo.addItem(title,value)
        self.wq_interpolation_combo = QComboBox();self.wq_interpolation_combo.addItem('Inverse distance weighting','idw');self.wq_interpolation_combo.addItem('Ordinary kriging','kriging')
        self.wq_variogram_combo = QComboBox();self.wq_variogram_combo.addItems(['spherical','exponential'])
        def spin(name,minimum,maximum,value,decimals=None):
            control = QDoubleSpinBox() if decimals is not None else QSpinBox()
            if decimals is not None:control.setDecimals(decimals)
            control.setRange(minimum,maximum);control.setValue(value);setattr(self,name,control);return control
        fields = [('Distance coordinates',self.distance_combo),('Interpolation',self.wq_interpolation_combo),('Variogram',self.wq_variogram_combo),
            ('Range',spin('wq_range_spin',.000001,1e9,1000,6)),('Partial sill',spin('wq_sill_spin',.000001,1e12,100,6)),
            ('Nugget',spin('wq_nugget_spin',0,1e12,0,6)),('IDW power',spin('wq_power_spin',.1,10,2,2)),
            ('Grid cells per axis',spin('wq_grid_spin',20,160,70)),('Contour levels',spin('wq_levels_spin',3,40,12))]
        for label,widget in fields:self._add_field(layout,label,widget)
        spatial_controls.build(self,layout,self.distance_combo,self.wq_grid_spin,self.wq_levels_spin)
        self.control_tabs.widget(1).widget().layout().insertWidget(1,self.spatial_card)
        self.wq_display_card,layout = self._card('Index figure appearance')
        self.wq_samples_check = QCheckBox('Show sampling points');self.wq_samples_check.setChecked(True)
        self.wq_labels_check = QCheckBox('Show point labels');self.wq_labels_check.setChecked(True)
        self.wq_colorbar_check = QCheckBox('Show colour scale');self.wq_colorbar_check.setChecked(True)
        self.wq_grid_check = QCheckBox('Show coordinate grid');self.wq_grid_check.setChecked(True)
        self.wq_north_check = QCheckBox('Show grid north arrow (+Y)')
        self.wq_mesh_check = QCheckBox('Show 3D mesh edges')
        self.wq_guides_check = QCheckBox('Show 3D coordinate guides');self.wq_guides_check.setChecked(True)
        self.wq_scale_check = QCheckBox('Use custom colour limits')
        for control in (self.wq_samples_check,self.wq_labels_check,self.wq_colorbar_check,self.wq_grid_check,self.wq_north_check,self.wq_mesh_check,self.wq_guides_check,self.wq_scale_check):layout.addWidget(control)
        self.wq_cmap_combo = ColourScaleCombo(default='viridis', normalization=self.style_controls['normalize_cmap'])
        self.wq_projection_combo = QComboBox();self.wq_projection_combo.addItem('Perspective','persp');self.wq_projection_combo.addItem('Orthographic','ortho')
        for label,widget in [('Colour scale',self.wq_cmap_combo),('Fill opacity',spin('wq_opacity_spin',.05,1,1.,2)),
            ('Colour minimum',spin('wq_min_spin',-1e9,1e9,0,2)),('Colour maximum',spin('wq_max_spin',-1e9,1e9,100,2)),
            ('Histogram bins',spin('wq_bins_spin',1,100,12)),('3D projection',self.wq_projection_combo)]:self._add_field(layout,label,widget)
        self.control_tabs.widget(1).widget().layout().insertWidget(2,self.wq_display_card)
        self._build_map_controls(spin)
        self._build_point_controls(spin)
        self.initialize_boundary_controls();self.boundary_extrapolate_check.setChecked(False)
        self.wq_index_combo.currentTextChanged.connect(self._load_index_controls)
        self.wq_method_combo.currentIndexChanged.connect(self._method_changed)
        self.wq_standard_combo.currentIndexChanged.connect(self._standard_changed)
        self.wq_limit_combo.currentIndexChanged.connect(self._limit_changed)
        self.wq_season_combo.currentIndexChanged.connect(self._populate_seasons)
        self.wq_interpolation_combo.currentIndexChanged.connect(self._analysis_controls_changed)
        self._load_index_controls()
        from ...observation_options import build_controls
        build_controls(self)
        from ...chart_controls import build_reference_controls
        build_reference_controls(self,note=True)
        from ...chart_controls import add_fields
        add_fields(self,self.reference_card.layout(),[('reference_limits_edit','Identity line limits (min, max; blank = data range)','')])
        self.wq_cmap_combo.currentTextChanged.connect(self.style_controls['cmap'].setCurrentText)
        self.style_controls['cmap'].currentTextChanged.connect(lambda value: self.wq_cmap_combo.setCurrentText(value) if value!='Original' else None)
        self.connect_settings()
        from ..maps.colorbar_controls import bind_style
        bind_style(self,self.wq_colorbar_check)
        settings=self.control_tabs.widget(1).widget().layout()
        settings.removeWidget(self.appearance_card)
        settings.insertWidget(settings.indexOf(self.wq_label_card),self.appearance_card)
        self.initialize_three_d_tools()
        self._analysis_controls_changed()
        self.populate_module_columns()

    def _build_point_controls(self, spin):
        appearance=self.appearance_card.layout()
        self.appearance_card.findChild(QLabel,'cardTitle').setText('Point and plot appearance')
        self.appearance_card.findChild(QLabel,'muted').setText('Set point fills, outlines, symbols and opacity. For distribution plots, the fill colour applies to the plotted distribution.')
        self.single_color_label.setText('Fill colour')
        self.wq_point_mode_combo=QComboBox()
        for title,value in [('Automatic','auto'),('Single colour','single'),('Map colour scale','scale')]:
            self.wq_point_mode_combo.addItem(title,value)
        self.wq_point_mode_combo.setToolTip('Automatic uses the map colour scale on sample-only maps and the chosen fill colour on contour, classification and surface overlays.')
        appearance.insertWidget(2,self.wq_samples_check)
        self._add_field(appearance,'Point colours',self.wq_point_mode_combo)
        appearance.removeWidget(self.wq_point_mode_combo.parentWidget())
        appearance.insertWidget(3,self.wq_point_mode_combo.parentWidget())
        self.wq_edge_color_button=ColorButton('#26384a')
        self._add_field(appearance,'Point outline colour',self.wq_edge_color_button)
        self._add_field(appearance,'Point outline width (pt)',spin('wq_edge_width_spin',0,5,.5,2))
        self.wq_label_card,layout=self._card('Point labels','Choose label content and appearance. Labels reposition when the map is resized or the 3D camera rotates.')
        layout.addWidget(self.wq_labels_check)
        self.wq_label_content_combo=QComboBox()
        for title,value in [('Site and index value','both'),('Site name','site'),('Index value','value'),('Site and classification','class')]:
            self.wq_label_content_combo.addItem(title,value)
        self.wq_label_font_combo=QComboBox()
        for title,value in [('Use figure font',None),('DejaVu Sans','DejaVu Sans'),('Arial','Arial'),('Segoe UI','Segoe UI'),('Times New Roman','Times New Roman')]:
            self.wq_label_font_combo.addItem(title,value)
        self.wq_label_color_button=ColorButton('#26394d')
        for title,widget in [('Label content',self.wq_label_content_combo),('Font family',self.wq_label_font_combo),
            ('Text colour',self.wq_label_color_button),('Text size (pt)',spin('wq_label_size_spin',4,32,7,1)),
            ('Index decimal places',spin('wq_label_decimals_spin',0,6,2)),('Wrap site names at characters',spin('wq_label_wrap_spin',8,60,22))]:
            self._add_field(layout,title,widget)
        self.wq_label_bold_check=QCheckBox('Bold');self.wq_label_italic_check=QCheckBox('Italic')
        self.wq_label_leaders_check=QCheckBox('Show leader lines to points');self.wq_label_leaders_check.setChecked(True)
        self.wq_label_halo_check=QCheckBox('White text halo for contrast');self.wq_label_halo_check.setChecked(True)
        for control in (self.wq_label_bold_check,self.wq_label_italic_check,self.wq_label_leaders_check,self.wq_label_halo_check):layout.addWidget(control)
        self.control_tabs.widget(1).widget().layout().insertWidget(3,self.wq_label_card)
        for widget in (self.wq_samples_check,self.wq_labels_check):widget.toggled.connect(self._analysis_controls_changed)
        self.wq_point_mode_combo.currentIndexChanged.connect(self._analysis_controls_changed)
        self.wq_label_content_combo.currentIndexChanged.connect(self._analysis_controls_changed)

    def _build_map_controls(self, spin):
        self.contour_card,layout = self._card('Contour appearance')
        self.contour_lines_check = QCheckBox('Show contour lines');self.contour_lines_check.setChecked(True)
        self.contour_labels_check = QCheckBox('Label contour values');self.contour_labels_check.setChecked(True)
        layout.addWidget(self.contour_lines_check);layout.addWidget(self.contour_labels_check)
        self._add_field(layout,'Contour line width (pt)',spin('contour_width_spin',.1,4,.5,2))
        self.contour_color_button = ColorButton('#284453')
        self._add_field(layout,'Contour line colour',self.contour_color_button)
        self.control_tabs.widget(1).widget().layout().insertWidget(3,self.contour_card)
        self.map_colorbar_orientation_combo = QComboBox()
        self.map_colorbar_orientation_combo.addItem('Right of map','vertical')
        self.map_colorbar_orientation_combo.addItem('Below map','horizontal')
        self._add_field(self.wq_display_card.layout(),'Colour scale position',self.map_colorbar_orientation_combo)
        from ..maps.colorbar_controls import build as build_colorbar_controls
        build_colorbar_controls(self, self.wq_display_card.layout())
        self.map_grid_check = QCheckBox('Show coordinate grid');self.map_grid_check.setChecked(True)
        self.wq_north_check.setText('Show north arrow')
        self.map_north_check = self.wq_north_check
        self.map_north_reference_combo = QComboBox()
        self.map_north_reference_combo.addItem('Grid north / +Y','grid')
        self.map_north_reference_combo.addItem('True north (requires source CRS)','true')
        self._add_field(layout,'Arrow reference',self.map_north_reference_combo)
        self._add_field(layout,'X grid spacing (axis units)',spin('map_grid_spacing_spin',0,1e9,0,5))
        self.map_grid_spacing_spin.setSpecialValueText('Automatic')
        from ..maps.layout_ui import build_cartographic_controls
        build_cartographic_controls(self)
        self.map_frame_sides_combo.setCurrentIndex(self.map_frame_sides_combo.findData('bottom_left'))
        self.map_north_check.toggled.connect(self.map_north_reference_combo.setEnabled)
        self.map_north_reference_combo.setEnabled(self.map_north_check.isChecked())

    def _load_index_controls(self,*_):
        if not hasattr(self,'wq_method_combo'):return
        self._syncing_index = True
        try:
            profile = self.index_profiles[self.wq_index_combo.currentText()]
            for combo in (self.wq_method_combo,self.wq_standard_combo,self.wq_limit_combo):combo.blockSignals(True);combo.clear()
            for key,title in METHODS[self.wq_index_combo.currentText()].items():self.wq_method_combo.addItem(title,key)
            self.wq_method_combo.setCurrentIndex(self.wq_method_combo.findData(profile['method']))
            for key,s in self.standards.items():self.wq_standard_combo.addItem(s['name'],key)
            self.wq_standard_combo.setCurrentIndex(self.wq_standard_combo.findData(profile['standard_id']))
            standard = self.standards[profile['standard_id']]
            for kind in ('acceptable','permissible','guideline'):
                if any(kind in p for p in standard['parameters'].values()):self.wq_limit_combo.addItem(kind.title(),kind)
            self.wq_limit_combo.setCurrentIndex(self.wq_limit_combo.findData(profile['limit_kind']))
            for combo in (self.wq_method_combo,self.wq_standard_combo,self.wq_limit_combo):combo.blockSignals(False)
            self._refresh_method_note();self._analysis_controls_changed()
        finally:self._syncing_index=False

    def _refresh_method_note(self):
        p = self.index_profiles[self.wq_index_combo.currentText()]
        extra = ('CCME: one value per site/period; at least four variables and four measured occasions per variable.' if p['method']=='ccme' else
                 'Use Results & methods to inspect every quality rating, normalized weight and contribution.')
        self.method_note.setText(f'{len(p["parameters"])} selected parameters · {p["scheme"]["name"]}\n{extra}\n'+self.standards[p['standard_id']].get('scope',''))

    def _profile_changed(self):
        self._clear_plot_cache();self._refresh_method_note();self._invalidate_plot();self._setting_changed()

    def _method_changed(self,*_):
        if self._syncing_index or self._restoring:return
        p = self.index_profiles[self.wq_index_combo.currentText()]
        p['method']=self.wq_method_combo.currentData()
        p['scheme']=deepcopy(SCHEMES['ccme' if p['method']=='ccme' else 'arithmetic' if p['method']=='brown' else 'relative'])
        for parameter in p['parameters']:parameter['rating']='ideal' if p['method']=='brown' else 'ratio'
        self._analysis_controls_changed();self._profile_changed()

    def _standard_changed(self,*_):
        if self._syncing_index or self._restoring:return
        p = self.index_profiles[self.wq_index_combo.currentText()]
        p['standard_id']=self.wq_standard_combo.currentData();s=self.standards[p['standard_id']];p['standard_name']=s['name']
        p['limit_kind']='guideline' if any('guideline' in d for d in s['parameters'].values()) else 'acceptable'
        p['parameters']=mapped_parameters(self.data,s,p['limit_kind'],p['method']) if self.data is not None else []
        self._load_index_controls();self._profile_changed()

    def _limit_changed(self,*_):
        if self._syncing_index or self._restoring:return
        p=self.index_profiles[self.wq_index_combo.currentText()];p['limit_kind']=self.wq_limit_combo.currentData()
        p['parameters']=mapped_parameters(self.data,self.standards[p['standard_id']],p['limit_kind'],p['method']) if self.data is not None else []
        self._profile_changed()

    def edit_parameters(self):
        if self.data is None:
            QMessageBox.information(self,'Import data','Import measurements before selecting index parameters.');return
        from .dialogs import ParameterDialog
        p=self.index_profiles[self.wq_index_combo.currentText()]
        dialog=ParameterDialog(self.data,p,self.standards[p['standard_id']],self)
        if dialog.exec():p['parameters']=dialog.parameters;self._profile_changed()

    def edit_classification(self):
        from .dialogs import ClassificationDialog
        p=self.index_profiles[self.wq_index_combo.currentText()];dialog=ClassificationDialog(p['scheme'],self)
        if dialog.exec():p['scheme']=dialog.scheme;self._profile_changed()

    def import_standards(self):
        path,_=QFileDialog.getOpenFileName(self,'Import reviewed official limits','','Standards (*.json *.csv)')
        if not path:return
        try:
            s=import_standard(path)
            # Keep earlier project snapshots addressable, including repeated imports.
            if s['id'] in self.standards:
                base=s['id']+'-reviewed-import';candidate=base;number=2
                while candidate in self.standards:
                    candidate=f'{base}-{number}';number+=1
                s['id']=candidate
            self.standards[s['id']]=s
            self._load_index_controls()
            self.wq_standard_combo.setCurrentIndex(self.wq_standard_combo.findData(s['id']))
        except (OSError,ValueError,KeyError,TypeError) as exc:QMessageBox.warning(self,'Invalid standards import',str(exc))

    def export_standards(self):
        s=self.standards[self.wq_standard_combo.currentData()]
        path,_=QFileDialog.getSaveFileName(self,'Export standards template',s['id']+'.json','JSON (*.json)')
        if not path:return
        from ...core.projects import atomic_json
        try:atomic_json(path,s)
        except OSError as exc:QMessageBox.warning(self,'Could not export standards',str(exc))

    def populate_module_columns(self):
        super().populate_module_columns()
        if hasattr(self, 'point_scale_combo'):
            from ...observation_options import populate_controls
            populate_controls(self)
        if not hasattr(self,'wq_site_combo'):return
        columns=list(self.data.columns) if self.data is not None else []
        for combo,candidates in [(self.wq_site_combo,['Site','Well','Sample']), (self.wq_time_combo,['Date','Time','SamplingDate']), (self.wq_season_combo,['Season','season','Period'])]:
            with QSignalBlocker(combo):
                combo.clear();combo.addItem('(none)',None)
                for c in columns:combo.addItem(c,c)
                match=next((c for c in candidates if c in columns),None)
                if match:combo.setCurrentIndex(combo.findData(match))
        self._populate_seasons()
        self.distance_combo.setCurrentIndex(0)
        self.analysis_crs_edit.clear()
        self.spatial_source_crs_edit.clear()
        if self.data is not None:
            for p in self.index_profiles.values():p['parameters']=mapped_parameters(self.data,self.standards[p['standard_id']],p['limit_kind'],p['method'])
        self._refresh_method_note()

    def _populate_seasons(self,*_):
        column=self.wq_season_combo.currentData()
        values=list(dict.fromkeys(self.data[column].dropna().astype(str))) if self.data is not None and column in self.data else []
        for combo in (self.wq_filter_combo,self.wq_pre_combo,self.wq_post_combo):
            with QSignalBlocker(combo):
                previous=combo.currentData();combo.clear()
                if combo is self.wq_filter_combo:combo.addItem('All seasons',None)
                for value in values:combo.addItem(value,value)
                if previous in values:combo.setCurrentIndex(combo.findData(previous))
        if len(values)>1 and self.wq_pre_combo.currentIndex()==self.wq_post_combo.currentIndex():self.wq_post_combo.setCurrentIndex(1)

    def _analysis_controls_changed(self,*_):
        if hasattr(self,'analysis_card'):self.analysis_card.hide();self.exploration_card.hide()
        if not hasattr(self,'wq_display_card'):return
        view=self.wq_view_combo.currentData();spatial=view in SPATIAL_VIEWS
        if hasattr(self, 'observation_card'):
            self.observation_card.setVisible(view in ('samples', 'index_scatter'))
            # WQI/DWQI already has richer label controls in its map appearance
            # card. Do not offer duplicate label/bounds settings with no effect.
            self.point_labels_combo.parentWidget().hide()
            self.point_label_offsets_edit.parentWidget().hide()
            self.point_label_size_spin.parentWidget().hide()
            self.point_label_color_edit.parentWidget().hide()
            self.point_edge_color_edit.parentWidget().hide()
            self.point_edge_width_spin.parentWidget().hide()
            self.point_bounds_check.hide()
            for widget in (self.point_scale_combo, self.point_limits_edit, self.point_ticks_edit,
                           self.point_zero_marker_combo, self.point_zero_color_edit, self.point_zero_size_spin):
                widget.parentWidget().setVisible(view == 'samples')
            for widget in (self.point_zero_check, self.point_zero_note_check, self.point_geographic_check):
                widget.setVisible(view == 'samples')
            self.point_limits_edit.parentWidget().hide()  # Uses the existing custom-colour-limits controls.
            for widget in (self.point_zero_width_spin,self.point_zero_text_edit,self.point_zero_note_size_spin,self.point_zero_note_color_edit,
                           self.point_zero_note_x_spin,self.point_zero_note_y_spin):
                widget.parentWidget().setVisible(view=='samples')
        if hasattr(self,'reference_card'):
            self.reference_card.setVisible(view=='index_scatter')
        maps=spatial and view!='surface'
        self.spatial_card.setVisible(spatial);self.location_card.setVisible(spatial)
        if hasattr(self,'boundary_card'):self.boundary_card.setVisible(spatial)
        self.wq_time_combo.parentWidget().setVisible(self.index_profiles[self.wq_index_combo.currentText()]['method']=='ccme')
        for combo in (self.wq_pre_combo,self.wq_post_combo):combo.parentWidget().setVisible(view in SEASONAL_VIEWS)
        for control in (self.wq_variogram_combo,self.wq_range_spin,self.wq_sill_spin,self.wq_nugget_spin):control.parentWidget().setVisible(spatial and view!='samples' and self.wq_interpolation_combo.currentData()=='kriging')
        for control in (self.wq_interpolation_combo,self.wq_grid_spin):control.parentWidget().setVisible(view!='samples')
        self.wq_power_spin.parentWidget().setVisible(spatial and view!='samples' and self.wq_interpolation_combo.currentData()=='idw')
        self.wq_levels_spin.parentWidget().setVisible(view=='contour')
        for control in (self.wq_samples_check,self.wq_labels_check,self.wq_colorbar_check,self.wq_scale_check):control.setVisible(spatial)
        self.wq_grid_check.setVisible(view=='surface')
        if hasattr(self,'map_grid_card'):
            for card in (self.map_grid_card,self.map_north_card,self.map_scale_card):card.setVisible(maps)
            self.contour_card.setVisible(view=='contour')
            self.map_colorbar_orientation_combo.parentWidget().setVisible(maps and view!='classification')
            for field in self._colorbar_fields:
                field.setVisible(maps and view!='classification')
        for control in (self.wq_cmap_combo,self.wq_opacity_spin,self.wq_min_spin,self.wq_max_spin):control.parentWidget().setVisible(spatial)
        self.wq_bins_spin.parentWidget().setVisible(view=='histogram')
        self.wq_mesh_check.setVisible(view=='surface');self.wq_projection_combo.parentWidget().setVisible(view=='surface')
        self.wq_guides_check.setVisible(view=='surface')
        if hasattr(self,'three_d_tools'):self.three_d_tools.setVisible(view=='surface')
        if hasattr(self,'view_tools'):self.view_tools.camera_menu.menuAction().setVisible(view=='surface')
        self.style_controls['z_label'].parentWidget().setVisible(view=='surface')
        if hasattr(self,'_active_plot'):
            self.wq_view_combo.parentWidget().hide();self.wq_index_combo.parentWidget().hide()
        if hasattr(self,'wq_label_card'):
            self.wq_label_card.setVisible(spatial)
            points=spatial and self.wq_samples_check.isChecked()
            self.wq_labels_check.setEnabled(points)
            labels=points and self.wq_labels_check.isChecked()
            for name,widget in vars(self).items():
                if name.startswith('wq_label_') and name.endswith(('_combo','_button','_spin','_check')):
                    widget.setEnabled(labels)
            self.wq_label_decimals_spin.setEnabled(labels and self.wq_label_content_combo.currentData() in ('both','value'))
            self.wq_label_wrap_spin.setEnabled(labels and self.wq_label_content_combo.currentData()!='value')
            self.wq_point_mode_combo.parentWidget().setVisible(spatial)
            self.wq_point_mode_combo.setEnabled(points)
            for widget in (self.wq_edge_color_button,self.wq_edge_width_spin):
                widget.parentWidget().setVisible(spatial or view=='index_scatter');widget.setEnabled(points or view=='index_scatter')
            scaled=self.wq_point_mode_combo.currentData()=='scale' or (self.wq_point_mode_combo.currentData()=='auto' and view=='samples')
            self.color_button.setEnabled(not spatial or (points and not scaled))
            self.color_button.setToolTip('Choose Single colour above to set the point fill.' if spatial and scaled else 'Choose the plotted fill colour.')
            for widget in (self.marker_combo,self.size_spin,self.alpha_spin):
                widget.parentWidget().setVisible(spatial or view=='index_scatter')
                widget.setEnabled(points or view=='index_scatter')
            self.appearance_card.setVisible(view!='compliance')
            self.wq_colorbar_check.setVisible(spatial and view!='classification')
            self.wq_colorbar_check.setEnabled(view!='samples' or (points and scaled))
        self._update_shared_spatial_controls()

    def refresh_contextual_controls(self):
        self.chart_card.hide();self.appearance_card.show()
        self.label_combo.parentWidget().hide();self.color_combo.parentWidget().hide()
        self._analysis_controls_changed()

    def _capture_current_state(self):
        state=super()._capture_current_state()
        state['index_profiles']=deepcopy(self.index_profiles);state['water_quality_standards']=deepcopy(self.standards)
        for name in ('wq_edge_color_button','wq_label_color_button'):
            if hasattr(self,name):state['controls'][name]=getattr(self,name).text()
        return state

    def _capture_profile(self):
        state=super()._capture_profile();state.pop('index_profiles',None);state.pop('water_quality_standards',None)
        for key in SHARED_CONTROLS:state['controls'].pop(key,None)
        return state

    def _update_shared_spatial_controls(self):
        view = self.wq_view_combo.currentData()
        spatial_controls.update(self, spatial=view in SPATIAL_VIEWS,
            interpolated=view in SPATIAL_VIEWS-{'samples'},
            idw=view != 'samples' and self.wq_interpolation_combo.currentData() == 'idw',
            classified=view in ('classification','surface'))
        if view in SPATIAL_VIEWS-{'samples','classification','surface'} and self.classification_combo.currentData() != 'automatic':
            self.wq_scale_check.hide()
            self.wq_min_spin.parentWidget().hide()
            self.wq_max_spin.parentWidget().hide()

    def _restore_current_state(self,state):
        self._stop_rotation()
        state=deepcopy(state)
        spatial_controls.restore_defaults(state, switching=getattr(self,'_switching_plot',False))
        controls=state.setdefault('controls',{})
        # Older index plots used one grid checkbox for maps and surfaces.
        controls.setdefault('map_grid_check',controls.get('wq_grid_check',True))
        if 'water_quality_standards' in state:self.standards={k:validate_standard(s) for k,s in state['water_quality_standards'].items()}
        if 'index_profiles' in state:
            profiles=deepcopy(state['index_profiles'])
            for name in METHODS:
                p=profiles[name]
                if p['method'] not in METHODS[name] or p['standard_id'] not in self.standards:raise ValueError('Invalid saved index profile.')
                p['scheme']=validate_scheme(p['scheme'])
                if p['parameters']:validate_parameters(p['parameters'])
            self.index_profiles=profiles
        super()._restore_current_state(state)
        from PySide6.QtGui import QColor
        for name in ('wq_edge_color_button','wq_label_color_button'):
            value=controls.get(name)
            if isinstance(value,str) and QColor(value).isValid():getattr(self,name).setText(value)
        self._load_index_controls()

    def analysis_config(self):
        from ..maps.layout_ui import advanced_layout
        from ..maps.colorbar_controls import options as colorbar_options
        from ...observation_options import options
        from ...chart_controls import reference_options
        point_settings = options(self)
        point_settings.update(limits='',edge_color=self.wq_edge_color_button.text(),edge_width=self.wq_edge_width_spin.value())
        reference = reference_options(self)
        reference['limits'] = self.reference_limits_edit.text()
        return dict(index=self.wq_index_combo.currentText(),view=self.wq_view_combo.currentData(),profiles=deepcopy(self.index_profiles),
            point_settings=point_settings,colorbar_options=colorbar_options(self),reference=reference,
            site_column=self.wq_site_combo.currentData(),time_column=self.wq_time_combo.currentData(),season_column=self.wq_season_combo.currentData(),
            seasons=[self.wq_pre_combo.currentData(),self.wq_post_combo.currentData()],filter_season=self.wq_filter_combo.currentData(),
            x=self.map_x_combo.currentText(),y=self.map_y_combo.currentText(),coordinates=self.distance_combo.currentData(),
            source_crs=spatial_controls.source_crs(self), **spatial_controls.display_options(self),
            boundary=self._active_boundary(),extrapolate=self._active_boundary() is not None and self.boundary_extrapolate_check.isChecked(),
            samples_inside_boundary=self._active_boundary() is not None and self.boundary_samples_check.isChecked(),
            spatial=dict(method=self.wq_interpolation_combo.currentData(),resolution=self.wq_grid_spin.value(),model=self.wq_variogram_combo.currentText(),
                         range_=self.wq_range_spin.value(),sill=self.wq_sill_spin.value(),nugget=self.wq_nugget_spin.value(),power=self.wq_power_spin.value(),**spatial_controls.interpolation_options(self)),
            cmap=self.wq_cmap_combo.currentText(),color=self.color_button.text(),marker=self.marker_combo.currentText(),sample_size=self.size_spin.value(),
            point_color_mode=self.wq_point_mode_combo.currentData(),sample_alpha=self.alpha_spin.value(),
            sample_edgecolor=self.wq_edge_color_button.text(),sample_linewidth=self.wq_edge_width_spin.value(),
            point_label_style=dict(content=self.wq_label_content_combo.currentData(),color=self.wq_label_color_button.text(),
                size=self.wq_label_size_spin.value(),font_family=self.wq_label_font_combo.currentData(),
                bold=self.wq_label_bold_check.isChecked(),italic=self.wq_label_italic_check.isChecked(),
                decimals=self.wq_label_decimals_spin.value(),wrap=self.wq_label_wrap_spin.value(),
                leaders=self.wq_label_leaders_check.isChecked(),halo=self.wq_label_halo_check.isChecked()),
            levels=self.wq_levels_spin.value(),show_samples=self.wq_samples_check.isChecked(),point_labels=self.wq_labels_check.isChecked(),
            show_colorbar=self.wq_colorbar_check.isChecked(),
            show_grid=(self.wq_grid_check if self.wq_view_combo.currentData()=='surface' else self.map_grid_check).isChecked(),
            north_arrow=self.wq_north_check.isChecked(),north_reference=self.map_north_reference_combo.currentData(),
            colorbar_orientation=self.map_colorbar_orientation_combo.currentData(),grid_spacing=self.map_grid_spacing_spin.value(),
            map_layout=advanced_layout(self),contour_lines=self.contour_lines_check.isChecked(),
            contour_labels=self.contour_labels_check.isChecked(),line_width=self.contour_width_spin.value(),line_color=self.contour_color_button.text(),
            coordinate_guides=self.wq_guides_check.isChecked(),
            opacity=self.wq_opacity_spin.value(),mesh_edges=self.wq_mesh_check.isChecked(),projection=self.wq_projection_combo.currentData(),
            elevation=self.elevation_spin.value(),azimuth=self.azimuth_spin.value(),bins=self.wq_bins_spin.value(),
            color_min=self.wq_min_spin.value() if self.wq_scale_check.isChecked() else None,
            color_max=self.wq_max_spin.value() if self.wq_scale_check.isChecked() else None,
            basemap=self._basemap_key() if self.wq_view_combo.currentData() in SPATIAL_VIEWS-{'surface'} else 'plain')

    @plot_loading
    def generate(self):
        self._stop_rotation()
        camera=self._camera_for_generation() if self.wq_view_combo.currentData()=='surface' else None
        self._clear_analysis();self.generated_plot=None;self.save_button.setEnabled(False)
        try:
            if self.data is None:raise ValueError('Import water-quality measurements first.')
            from ...water_quality.plots import plot
            config=self.analysis_config();data=self.data
            if camera is not None:config.update(zip(('elevation','azimuth','roll'),camera))
            result=self._run_plot_job(lambda:plot(data.copy(deep=True),config))
            self.show_result(result,figure_title(config['index'],config['view']))
            self._sync_view_controls()
            if config['basemap']!='plain':
                from ...map_tiles import TileBasemap
                for ax in getattr(result.figure,'_aquaprov_index_map_axes',[]):
                    layer=TileBasemap(ax,self.analysis_canvas,self,provider=config['basemap'])
                    layer.status_changed.connect(lambda message,busy:self.statusBar().showMessage(message))
                    self._index_basemaps.append(layer);layer.refresh()
            self.statusBar().showMessage('Index ready. Export figures and Results & methods; hover over mapped samples to inspect values.')
        except Exception as exc:self._report_plot_error('Could not generate water-quality analysis',exc)

    def _sync_view_controls(self):
        super()._sync_view_controls()
        from ..maps.layout_ui import sync_cartographic_controls
        sync_cartographic_controls(self)

    def _dispose_figure_view(self):
        self._close_index_basemaps()
        super()._dispose_figure_view()

    def _close_index_basemaps(self):
        for layer in getattr(self,'_index_basemaps',[]):layer.close();layer.deleteLater()
        self._index_basemaps=[]

    def _stash_plot(self):
        # Stop network activity while a canvas is retained off screen.
        self._close_index_basemaps()
        super()._stash_plot()

    def _restore_cached_plot(self,key):
        restored=super()._restore_cached_plot(key)
        if restored and self.analysis_result is not None:
            provider=self.analysis_result.metadata.get('config',{}).get('basemap','plain')
            if provider!='plain':
                from ...map_tiles import TileBasemap
                for ax in getattr(self.analysis_result.figure,'_aquaprov_index_map_axes',[]):
                    # Retained raster tiles belong to the closed provider instance.
                    for artist in list(ax.images):artist.remove()
                    layer=TileBasemap(ax,self.analysis_canvas,self,provider=provider)
                    layer.status_changed.connect(lambda message,busy:self.statusBar().showMessage(message))
                    self._index_basemaps.append(layer);layer.refresh()
        return restored
