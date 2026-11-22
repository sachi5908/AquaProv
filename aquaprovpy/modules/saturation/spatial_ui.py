"""Mineral SI controls using the Maps module's cartographic layout tools."""
from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QPushButton

from ..maps.layout_ui import advanced_layout, build_cartographic_controls, sync_cartographic_controls
from ...ui.colour_scale import ColourScaleCombo
from ..maps import spatial_controls


class SISpatialWorkspaceMixin:
    def _build_si_map_controls(self, spin):
        self.contour_card, layout = self._card('Contour appearance',
            'Style the SI contours or display ordinary-kriging prediction variance in SI squared.')
        self.si_surface_combo = QComboBox()
        self.si_surface_combo.addItem('Saturation index contours', 'si')
        self.si_surface_combo.addItem('Kriging prediction variance (SI²)', 'variance')
        self._add_field(layout, 'Surface', self.si_surface_combo)
        self._add_field(layout, 'Contour levels', spin('si_levels_spin', 3, 30, 12))
        spatial_controls.build(self,self.si_spatial_card.layout(),self.distance_combo,self.si_grid_spin,self.si_levels_spin)
        self.contour_lines_check = QCheckBox('Show contour lines')
        self.contour_labels_check = QCheckBox('Label contour values')
        self.si_zero_check = QCheckBox('Highlight the SI = 0 contour')
        for control in (self.contour_lines_check, self.contour_labels_check, self.si_zero_check):
            control.setChecked(True)
            layout.addWidget(control)
        self._add_field(layout, 'Contour line width (pt)', spin('contour_width_spin', .1, 4, .5, 2))
        from ...ui.color_button import ColorButton
        self.contour_color_button = ColorButton('#214b60')
        self._add_field(layout, 'Contour line colour', self.contour_color_button)
        self._add_field(layout, 'Contour fill opacity', spin('contour_opacity_spin', .05, 1, .8, 2))
        self.contour_basemap_check = QCheckBox('Show selected basemap below contours')
        self.contour_basemap_check.setChecked(True)
        layout.addWidget(self.contour_basemap_check)
        self.control_tabs.widget(1).widget().layout().insertWidget(2, self.contour_card)

        self.map_layout_card, layout = self._card('Map layout')
        self.map_colorbar_check = QCheckBox('Show colour scale')
        self.map_colorbar_check.setChecked(True)
        layout.addWidget(self.map_colorbar_check)
        self.map_colorbar_orientation_combo = QComboBox()
        self.map_colorbar_orientation_combo.addItem('Right of map', 'vertical')
        self.map_colorbar_orientation_combo.addItem('Below map', 'horizontal')
        self._add_field(layout, 'Colour scale position', self.map_colorbar_orientation_combo)
        self.map_colorbar_check.toggled.connect(self.map_colorbar_orientation_combo.setEnabled)
        self.si_point_mode_combo = QComboBox()
        self.si_point_mode_combo.addItem('SI colour scale', 'si')
        self.si_point_mode_combo.addItem('Single fill colour from Style', 'single')
        self._add_field(layout, 'Sample colours', self.si_point_mode_combo)
        self.si_variance_cmap_combo = ColourScaleCombo(default='viridis', normalization=self.style_controls['normalize_cmap'])
        self._add_field(layout, 'Variance colour scale', self.si_variance_cmap_combo)
        self.si_basemap_note = QLabel('Basemap is selected in Data → Locations.')
        self.si_basemap_note.setWordWrap(True)
        layout.addWidget(self.si_basemap_note)
        self.si_basemap_retry_button = QPushButton('Retry basemap')
        self.si_basemap_retry_button.setEnabled(False)
        self.si_basemap_retry_button.clicked.connect(self._retry_si_basemap)
        layout.addWidget(self.si_basemap_retry_button)
        self.control_tabs.widget(1).widget().layout().insertWidget(3, self.map_layout_card)

        self.map_grid_check = QCheckBox('Show coordinate grid')
        self.map_grid_check.setChecked(True)
        self._add_field(layout, 'X grid spacing (axis units)', spin('map_grid_spacing_spin', 0, 1e9, 0, 5))
        self.map_grid_spacing_spin.setSpecialValueText('Automatic')
        # Retain the old SI checkbox name in saved projects.
        self.map_north_check = self.si_north_check
        self.map_north_check.setText('Show north arrow')
        self.map_north_reference_combo = QComboBox()
        self.map_north_reference_combo.addItem('Grid north / +Y', 'grid')
        self.map_north_reference_combo.addItem('True north (requires source CRS)', 'true')
        self._add_field(layout, 'Arrow reference', self.map_north_reference_combo)
        self.map_north_check.toggled.connect(self.map_north_reference_combo.setEnabled)
        self.map_north_reference_combo.setEnabled(self.map_north_check.isChecked())
        build_cartographic_controls(self)
        for control in (self.si_surface_combo, self.si_interpolation_combo):
            control.currentIndexChanged.connect(self._analysis_controls_changed)

    def _update_si_map_controls(self, spatial, interpolated):
        if not hasattr(self, 'si_surface_combo'):
            return
        kriging = self.si_interpolation_combo.currentData() == 'kriging'
        self.si_surface_combo.model().item(1).setEnabled(kriging)
        if not kriging and self.si_surface_combo.currentData() == 'variance':
            self.si_surface_combo.setCurrentIndex(0)
        variance = interpolated and self.si_surface_combo.currentData() == 'variance'
        self.contour_card.setVisible(interpolated)
        for card in (self.map_layout_card, self.map_grid_card, self.map_north_card, self.map_scale_card):
            card.setVisible(spatial)
        self.si_variance_cmap_combo.parentWidget().setVisible(variance)
        self.si_point_mode_combo.parentWidget().setVisible(not variance)
        self.si_zero_check.setVisible(not variance)
        spatial_controls.update(self,spatial=spatial,interpolated=interpolated,idw=interpolated and not kriging)
        if interpolated and self.classification_combo.currentData() != 'automatic':
            self.si_scale_check.hide()
            self.si_limit_spin.parentWidget().hide()
        if variance:
            self.si_cmap_combo.parentWidget().hide()
            self.si_scale_check.hide()
            self.si_limit_spin.parentWidget().hide()

    def _si_map_config(self):
        return dict(surface=self.si_surface_combo.currentData(), levels=self.si_levels_spin.value(),
            contour_lines=self.contour_lines_check.isChecked(), contour_labels=self.contour_labels_check.isChecked(),
            zero_contour=self.si_zero_check.isChecked(), line_width=self.contour_width_spin.value(),
            line_color=self.contour_color_button.text(), surface_alpha=self.contour_opacity_spin.value(),
            variance_cmap=self.si_variance_cmap_combo.currentText(), sample_coloring=self.si_point_mode_combo.currentData(),
            sample_color=self.color_button.text(), sample_alpha=self.alpha_spin.value(),
            show_colorbar=self.map_colorbar_check.isChecked(), colorbar_orientation=self.map_colorbar_orientation_combo.currentData(),
            show_grid=self.map_grid_check.isChecked(), grid_spacing=self.map_grid_spacing_spin.value(),
            north_reference=self.map_north_reference_combo.currentData(), map_layout=advanced_layout(self))

    def _sync_view_controls(self):
        super()._sync_view_controls()
        sync_cartographic_controls(self)

    def _si_basemap_status(self, message, busy):
        self.statusBar().showMessage(message)
        self.si_basemap_note.setText(message)
        self.si_basemap_retry_button.setEnabled(not busy and bool(self._si_basemaps))
        if self.analysis_result is not None:
            self.analysis_result.metadata['basemap_status'] = message

    def _retry_si_basemap(self):
        for layer in self._si_basemaps:
            layer.refresh(force=True)
