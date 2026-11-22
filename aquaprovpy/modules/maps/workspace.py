"""Map locations, interpolation controls and contour result presentation."""
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox
from ..base import ModuleWorkspace
from ...ui.loading import plot_loading
from ...core.progress import progress_stage
from .boundary_ui import BoundaryWorkspaceMixin
from ...ui.color_button import ColorButton


class MapWorkspace(BoundaryWorkspaceMixin, ModuleWorkspace):
    module_key = "maps"

    def __init__(self):
        self.study_boundary = None
        super().__init__()
        self.chart_card.hide()
        self.analysis_card.hide()
        self.exploration_card.hide()
        self.map_value_combo.parentWidget().findChild(QLabel).setText("Measurement / point color")
        card, layout = self._card("Spatial analysis", "Choose source columns in Data. Boundary coverage is controlled in Study-area boundary.")
        self.spatial_method_combo = QComboBox()
        self.spatial_method_combo.addItems(["Sample locations", "Ordinary kriging · contours", "Ordinary kriging · variance", "IDW · contours"])
        self.distance_combo = QComboBox()
        self.distance_combo.addItem("(choose distance coordinates)", None)
        self.distance_combo.addItem("Projected / local X and Y (same distance units)", "projected")
        self.distance_combo.addItem("WGS84 longitude / latitude → local metres", "wgs84")
        self.distance_combo.addItem('WGS84 → automatic UTM / UPS (metres)', 'auto_utm')
        self.distance_combo.addItem('WGS84 → custom projected CRS (metres)', 'wgs84_projected')
        self.analysis_crs_edit = QLineEdit()
        self.analysis_crs_edit.setPlaceholderText('Projected EPSG code, e.g. EPSG:32645')
        self.analysis_crs_edit.setToolTip('Convert WGS84 longitude/latitude into a regional projected CRS with metre units.')
        self.spatial_source_crs_edit = QLineEdit()
        self.spatial_source_crs_edit.setPlaceholderText('Optional EPSG code for existing X / Y')
        self.spatial_source_crs_edit.setToolTip('For already projected coordinates: override the source CRS selected in Data. Leave blank to use Data settings.')
        self.variogram_combo = QComboBox()
        self.variogram_combo.addItems(["spherical", "exponential"])
        self.range_spin = QDoubleSpinBox()
        self.range_spin.setRange(.000001, 1e9)
        self.range_spin.setDecimals(6)
        self.range_spin.setValue(1000)
        self.sill_spin = QDoubleSpinBox()
        self.sill_spin.setDecimals(6)
        self.sill_spin.setRange(.000001, 1e12)
        self.sill_spin.setValue(1)
        self.nugget_spin = QDoubleSpinBox()
        self.nugget_spin.setDecimals(6)
        self.nugget_spin.setRange(0, 1e12)
        self.power_spin = QDoubleSpinBox()
        self.power_spin.setRange(.1, 10)
        self.power_spin.setValue(2)
        self.neighbors_spin = QSpinBox()
        self.neighbors_spin.setRange(0, 1000)
        self.neighbors_spin.setSpecialValueText('All samples')
        self.neighbors_spin.setToolTip('Zero uses all samples. Otherwise use the nearest available samples up to this count; equal-distance ties are included.')
        self.grid_mode_combo = QComboBox()
        self.grid_mode_combo.addItem('Cells per axis', 'resolution')
        self.grid_mode_combo.addItem('Cell size in analysis units', 'cell_size')
        self.cell_size_spin = QDoubleSpinBox()
        self.cell_size_spin.setDecimals(4)
        self.cell_size_spin.setRange(.0001, 1e9)
        self.cell_size_spin.setValue(20)
        self.cell_size_spin.setToolTip('Square grid spacing: metres after WGS84 conversion, otherwise source distance units. Maximum 1,000,000 grid points.')
        self.grid_spin = QSpinBox()
        self.grid_spin.setRange(20, 1000)
        self.grid_spin.setValue(70)
        self.levels_spin = QSpinBox()
        self.levels_spin.setRange(2, 40)
        self.levels_spin.setValue(12)
        self.classification_combo = QComboBox()
        for title, key in [('Automatic contour intervals', 'automatic'), ('Equal intervals', 'equal_interval'),
                           ('Quantiles', 'quantile'), ('Natural Breaks (Jenks)', 'natural_breaks'),
                           ('Custom class boundaries', 'custom')]:
            self.classification_combo.addItem(title, key)
        self.classification_combo.setToolTip('Classifies predicted grid values. Natural Breaks uses up to 512 histogram bins for large grids; exact displayed boundaries are exported.')
        self.class_breaks_edit = QLineEdit()
        self.class_breaks_edit.setPlaceholderText('e.g. 0, 50, 100, 250, 500')
        self.spatial_surface_combo = QComboBox()
        self.spatial_surface_combo.addItem('Filled contours', 'contours')
        self.spatial_surface_combo.addItem('Classified raster cells', 'raster')
        for text, widget in [("Output", self.spatial_method_combo), ("Distance coordinates", self.distance_combo),
                ('Analysis CRS', self.analysis_crs_edit), ('Source CRS override', self.spatial_source_crs_edit),
                ("Variogram model", self.variogram_combo), ("Range (distance units)", self.range_spin),
                ("Partial sill (measurement units²)", self.sill_spin), ("Nugget (measurement units²)", self.nugget_spin),
                ("IDW power", self.power_spin), ('Nearest neighbours', self.neighbors_spin),
                ('Grid definition', self.grid_mode_combo), ("Grid cells per axis", self.grid_spin),
                ('Cell size (distance units)', self.cell_size_spin), ('Colour classification', self.classification_combo),
                ("Contour levels", self.levels_spin), ('Class boundaries', self.class_breaks_edit),
                ('Surface drawing', self.spatial_surface_combo)]:
            self._add_field(layout, text, widget)
        self.local_idw_preset_button = QPushButton('Apply WGS84 local IDW preset')
        self.local_idw_preset_button.setToolTip('For longitude/latitude columns: automatic UTM/UPS, power 2, nearest 12 samples, 20-metre cells and five Natural Breaks classes.')
        self.local_idw_preset_button.clicked.connect(self._apply_local_idw_preset)
        layout.addWidget(self.local_idw_preset_button)
        self.control_tabs.widget(1).widget().layout().insertWidget(0, card)
        self.contour_card, appearance = self._card("Contour appearance", "These settings affect the figure. Regenerate after changing contours or sample symbols.")
        self.contour_lines_check = QCheckBox("Show contour lines")
        self.contour_lines_check.setChecked(True)
        self.contour_labels_check = QCheckBox("Label contour values")
        self.contour_labels_check.setChecked(True)
        self.contour_samples_check = QCheckBox("Show sample locations")
        self.contour_samples_check.setChecked(True)
        self.contour_width_spin = QDoubleSpinBox()
        self.contour_width_spin.setRange(.1, 4)
        self.contour_width_spin.setSingleStep(.1)
        self.contour_width_spin.setValue(.5)
        self.contour_color_button = ColorButton("#214b60")
        for control in (self.contour_lines_check, self.contour_labels_check, self.contour_samples_check):
            appearance.addWidget(control)
        self._add_field(appearance, "Contour line width (pt)", self.contour_width_spin)
        self._add_field(appearance, "Contour line color", self.contour_color_button)
        self.contour_basemap_check = QCheckBox('Show selected basemap below contours')
        appearance.addWidget(self.contour_basemap_check)
        self.contour_retry_button = QPushButton('Retry basemap')
        self.contour_retry_button.setEnabled(False)
        self.contour_retry_button.setVisible(False)
        self.contour_retry_button.clicked.connect(self._retry_map_background)
        self.contour_basemap_check.toggled.connect(self.contour_retry_button.setVisible)
        appearance.addWidget(self.contour_retry_button)
        self.contour_opacity_spin = QDoubleSpinBox()
        self.contour_opacity_spin.setRange(.05, 1)
        self.contour_opacity_spin.setSingleStep(.05)
        self.contour_opacity_spin.setValue(.8)
        self._add_field(appearance, 'Contour fill opacity', self.contour_opacity_spin)
        self.control_tabs.widget(1).widget().layout().insertWidget(1, self.contour_card)
        self.map_layout_card, map_layout = self._card('Map layout',
            'Colour scale, coordinate grid and north arrow apply to sample maps and contours. Regenerate after changing these options.')
        self.map_colorbar_check = QCheckBox('Show colour scale')
        self.map_colorbar_check.setChecked(True)
        map_layout.addWidget(self.map_colorbar_check)
        self.map_colorbar_orientation_combo = QComboBox()
        self.map_colorbar_orientation_combo.addItem('Right of map', 'vertical')
        self.map_colorbar_orientation_combo.addItem('Below map', 'horizontal')
        self._add_field(map_layout, 'Colour scale position', self.map_colorbar_orientation_combo)
        self.map_colorbar_check.toggled.connect(self.map_colorbar_orientation_combo.setEnabled)
        from .colorbar_controls import build as build_colorbar_controls
        build_colorbar_controls(self, map_layout)
        self.map_grid_check = QCheckBox('Show coordinate grid')
        self.map_grid_check.setChecked(True)
        map_layout.addWidget(self.map_grid_check)
        self.map_grid_spacing_spin = QDoubleSpinBox()
        self.map_grid_spacing_spin.setRange(0, 1e9)
        self.map_grid_spacing_spin.setDecimals(5)
        self.map_grid_spacing_spin.setSpecialValueText('Automatic')
        self.map_grid_spacing_spin.setToolTip('Spacing in displayed axis units: degrees for longitude/latitude, metres for projected maps. Zero selects automatic spacing.')
        self._add_field(map_layout, 'Grid spacing (axis units)', self.map_grid_spacing_spin)
        self.map_grid_check.toggled.connect(self.map_grid_spacing_spin.setEnabled)
        self.map_north_check = QCheckBox('Show north arrow')
        map_layout.addWidget(self.map_north_check)
        self.map_north_reference_combo = QComboBox()
        self.map_north_reference_combo.addItem('True north (requires source CRS)', 'true')
        self.map_north_reference_combo.addItem('Grid north / +Y', 'grid')
        self.map_north_reference_combo.setEnabled(False)
        self._add_field(map_layout, 'Arrow reference', self.map_north_reference_combo)
        self.map_north_check.toggled.connect(self.map_north_reference_combo.setEnabled)
        self.control_tabs.widget(1).widget().layout().insertWidget(2, self.map_layout_card)
        from .layout_ui import build_cartographic_controls
        build_cartographic_controls(self)
        from ...observation_options import build_controls
        build_controls(self)
        self.initialize_boundary_controls()
        self.spatial_method_combo.currentIndexChanged.connect(self._spatial_changed)
        for control in (self.distance_combo, self.grid_mode_combo, self.classification_combo):
            control.currentIndexChanged.connect(self._spatial_changed)
        self.preview_tabs.setCurrentWidget(self.map_page)
        self._spatial_changed()
        self.run_note.setText("Data: set X, Y and value columns. Analysis: choose sample maps, kriging or IDW.")
        self.connect_settings()
        from .colorbar_controls import bind_style
        bind_style(self,self.map_colorbar_check)
        from ..measurement_labels import bind_measurement_labels, bind_scale_label
        bind_measurement_labels(self, self.map_value_combo)
        bind_measurement_labels(self, self.map_x_combo, dimensions=('x',), colorbar=False)
        bind_measurement_labels(self, self.map_y_combo, dimensions=('y',), colorbar=False)
        bind_scale_label(self, self.point_scale_combo)

    def populate_module_columns(self):
        super().populate_module_columns()
        if hasattr(self, 'point_scale_combo'):
            from ...observation_options import populate_controls
            populate_controls(self)
        if hasattr(self, "distance_combo"):
            self.distance_combo.setCurrentIndex(0)
            self.analysis_crs_edit.clear()
            self.spatial_source_crs_edit.clear()

    def _spatial_changed(self, *_):
        index = self.spatial_method_combo.currentIndex()
        for control in (self.distance_combo, self.grid_mode_combo, self.classification_combo, self.spatial_surface_combo):
            control.parentWidget().setVisible(index > 0)
        self.analysis_crs_edit.parentWidget().setVisible(index > 0 and self.distance_combo.currentData() == 'wgs84_projected')
        self.spatial_source_crs_edit.parentWidget().setVisible(index > 0 and self.distance_combo.currentData() == 'projected')
        by_size = self.grid_mode_combo.currentData() == 'cell_size'
        self.grid_spin.parentWidget().setVisible(index > 0 and not by_size)
        self.cell_size_spin.parentWidget().setVisible(index > 0 and by_size)
        custom = self.classification_combo.currentData() == 'custom'
        self.levels_spin.parentWidget().setVisible(index > 0 and not custom)
        self.class_breaks_edit.parentWidget().setVisible(index > 0 and custom)
        self.neighbors_spin.parentWidget().setVisible(index == 3)
        self.local_idw_preset_button.setVisible(index > 0)
        for control in (self.variogram_combo, self.range_spin, self.sill_spin, self.nugget_spin):
            control.parentWidget().setVisible(index in (1, 2))
        self.power_spin.parentWidget().setVisible(index == 3)
        self.contour_card.setVisible(index > 0)
        self.observation_card.setVisible(index == 0)
        # Grouping/numeric color selectors have no role in the spatial renderer.
        self.label_combo.parentWidget().hide()
        self.color_combo.parentWidget().hide()
        self.preview_tabs.setCurrentIndex(2 if index == 0 else 1)
        self._update_generate_button(0)

    def _apply_local_idw_preset(self):
        from PySide6.QtCore import QSignalBlocker
        with QSignalBlocker(self.auto_update_check):
            auto_update = self.auto_update_check.isChecked()
            self.auto_update_check.setChecked(False)
        try:
            self.select_plot('idw')
            self.map_crs_combo.setCurrentIndex(self.map_crs_combo.findData('wgs84'))
            self.distance_combo.setCurrentIndex(self.distance_combo.findData('auto_utm'))
            self.power_spin.setValue(2)
            self.neighbors_spin.setValue(12)
            self.grid_mode_combo.setCurrentIndex(self.grid_mode_combo.findData('cell_size'))
            self.cell_size_spin.setValue(20)
            self.classification_combo.setCurrentIndex(self.classification_combo.findData('natural_breaks'))
            self.levels_spin.setValue(5)
            self.spatial_surface_combo.setCurrentIndex(self.spatial_surface_combo.findData('raster'))
            self.map_frame_sides_combo.setCurrentIndex(self.map_frame_sides_combo.findData('bottom_left'))
            self.map_coordinate_mode_combo.setCurrentIndex(self.map_coordinate_mode_combo.findData('geographic'))
            self.contour_lines_check.setChecked(False)
            self.contour_labels_check.setChecked(False)
        finally:
            with QSignalBlocker(self.auto_update_check):
                self.auto_update_check.setChecked(auto_update)
        self._setting_changed()

    def _restore_current_state(self, state):
        from copy import deepcopy
        state = deepcopy(state)
        controls = state.setdefault('controls', {})
        # Restore legacy settings even when an updated project was open before it.
        for name, default in {'neighbors_spin': 0, 'grid_mode_combo': 'Cells per axis',
                              'cell_size_spin': 20, 'classification_combo': 'Automatic contour intervals',
                              'class_breaks_edit': '', 'spatial_surface_combo': 'Filled contours'}.items():
            controls.setdefault(name, default)
        super()._restore_current_state(state)
        self._spatial_changed()

    def _analysis_controls_changed(self, *_):
        if hasattr(self, "analysis_card"):
            self.analysis_card.hide()
            self.exploration_card.hide()

    def _update_generate_button(self, index):
        if hasattr(self, "generate_button"):
            self.generate_button.setText("Generate spatial view")

    def _map_layout_options(self):
        from .layout_ui import advanced_layout
        from .colorbar_controls import options as colorbar_options
        return dict(show_colorbar=self.map_colorbar_check.isChecked(),
                    colorbar_options=colorbar_options(self),
                    colorbar_orientation=self.map_colorbar_orientation_combo.currentData(),
                    show_grid=self.map_grid_check.isChecked(), grid_spacing=self.map_grid_spacing_spin.value(),
                    north_arrow=self.map_north_check.isChecked(), north_reference=self.map_north_reference_combo.currentData(),
                    map_layout=advanced_layout(self))

    def _sync_view_controls(self):
        super()._sync_view_controls()
        from .layout_ui import sync_cartographic_controls
        sync_cartographic_controls(self)

    @plot_loading
    def generate(self):
        if self.spatial_method_combo.currentIndex() == 0:
            self.preview_tabs.setCurrentWidget(self.map_page)
            self.generate_map()
            return
        self._clear_analysis()
        self.generated_plot = None
        self.save_button.setEnabled(False)
        try:
            from .interpolation import interpolate, contour_result
            columns = (self.map_x_combo.currentText(), self.map_y_combo.currentText(), self.map_value_combo.currentText())
            data = self._prepare_plot_data(self.data, columns)
            options = dict(coordinates=self.distance_combo.currentData(),
                method="idw" if self.spatial_method_combo.currentIndex() == 3 else "kriging",
                resolution=self.grid_spin.value(), model=self.variogram_combo.currentText(),
                range_=self.range_spin.value(), sill=self.sill_spin.value(), nugget=self.nugget_spin.value(), power=self.power_spin.value(),
                neighbors=self.neighbors_spin.value() or None,
                cell_size=self.cell_size_spin.value() if self.grid_mode_combo.currentData() == 'cell_size' else None,
                target_crs=self.analysis_crs_edit.text().strip() or None)
            boundary = self._active_boundary()
            source_override = (self.spatial_source_crs_edit.text().strip()
                               if self.distance_combo.currentData() == 'projected' else '')
            options.update(boundary=boundary,
                source_crs=source_override or (self._declared_source_crs() if self.map_crs_combo.currentData() else None),
                extrapolate=boundary is not None and self.boundary_extrapolate_check.isChecked(),
                samples_inside_boundary=boundary is not None and self.boundary_samples_check.isChecked())
            provider = self._basemap_key() if self.contour_basemap_check.isChecked() else 'plain'
            appearance = dict(show_variance=self.spatial_method_combo.currentIndex() == 2, levels=self.levels_spin.value(),
                classification=self.classification_combo.currentData(), class_breaks=self.class_breaks_edit.text(),
                surface=self.spatial_surface_combo.currentData(),
                lines=self.contour_lines_check.isChecked(), labels=self.contour_labels_check.isChecked(),
                samples=self.contour_samples_check.isChecked(), linewidth=self.contour_width_spin.value(),
                linecolor=self.contour_color_button.text(), marker=self.marker_combo.currentText(),
                sample_size=self.size_spin.value(), sample_color=self.color_button.text(), alpha=self.alpha_spin.value(),
                basemap=provider, surface_alpha=self.contour_opacity_spin.value())
            appearance.update(self._map_layout_options())
            def calculate():
                with progress_stage(0, 70, 'Interpolating spatial grid'):
                    grid = interpolate(data, *columns, **options)
                with progress_stage(70, 100, 'Building contour figure'):
                    return contour_result(grid, **appearance)
            result = self._run_plot_job(calculate)
            self.show_result(result, self.spatial_method_combo.currentText())
            if provider != 'plain':
                from ...map_tiles import TileBasemap
                self.map_basemap = TileBasemap(result.figure.axes[0], self.analysis_canvas, self, provider=provider)
                self.map_basemap.status_changed.connect(self._map_background_status)
                self.map_basemap.refresh()
            self.statusBar().showMessage("Spatial view ready. Grid values and parameters are available in Results & methods.")
        except Exception as exc:
            self.plot_loader.hide()
            self._report_plot_error("Could not generate spatial view", exc)

    def _map_background_status(self, message, busy):
        super()._map_background_status(message, busy)
        self.statusBar().showMessage(message)
        if self.analysis_result is not None:
            self.analysis_result.metadata['basemap_status'] = message
        if hasattr(self, 'contour_retry_button'):
            self.contour_retry_button.setEnabled(not busy and self.map_basemap is not None)

    def _clear_analysis(self):
        super()._clear_analysis()
        if hasattr(self, 'contour_retry_button'):
            self.contour_retry_button.setEnabled(False)
