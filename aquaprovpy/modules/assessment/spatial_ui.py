"""Assessment map controls; fitted models and held-out validation stay distinct."""
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox
from ..maps import spatial_controls
from ..maps.layout_ui import build_cartographic_controls, advanced_layout, sync_cartographic_controls
from ...ui.color_button import ColorButton


class AssessmentSpatialMixin:
    def _build_assessment_maps(self):
        self.assessment_map_card, layout = self._card('Fitted spatial map',
            'The map uses the full-data fitted variogram. Geographic holdout validation refits each training block. IDW settings control the validation comparison.')
        def spin(name, low, high, default, decimals=None):
            widget = QSpinBox() if decimals is None else QDoubleSpinBox()
            if decimals is not None:
                widget.setDecimals(decimals)
            widget.setRange(low, high); widget.setValue(default)
            setattr(self, name, widget)
            return widget
        self.assessment_map_output_combo = QComboBox()
        for label, value in [('Prediction and uncertainty', 'both'), ('Fitted prediction', 'prediction'), ('Conditional uncertainty', 'uncertainty')]:
            self.assessment_map_output_combo.addItem(label, value)
        for title, widget in [('Map output', self.assessment_map_output_combo),
                ('IDW baseline power', spin('assessment_power_spin', .1, 10, 2, 2)),
                ('Grid cells per axis', spin('assessment_grid_spin', 20, 1000, 70)),
                ('Colour classes', spin('assessment_levels_spin', 2, 40, 12))]:
            self._add_field(layout, title, widget)
        spatial_controls.build(self, layout, self.assessment_coordinates_combo,
            self.assessment_grid_spin, self.assessment_levels_spin, assessment=True)
        self.contour_lines_check = QCheckBox('Show contour lines')
        self.contour_labels_check = QCheckBox('Label contour values')
        self.contour_samples_check = QCheckBox('Show sample locations'); self.contour_samples_check.setChecked(True)
        for widget in (self.contour_lines_check, self.contour_labels_check, self.contour_samples_check):
            layout.addWidget(widget)
        self.contour_color_button = ColorButton('#214b60')
        self._add_field(layout, 'Contour line colour', self.contour_color_button)
        self._add_field(layout, 'Contour line width', spin('contour_width_spin', .1, 4, .5, 2))
        self._add_field(layout, 'Fill opacity', spin('contour_opacity_spin', .05, 1, .8, 2))
        self.map_colorbar_check = QCheckBox('Show colour scale'); self.map_colorbar_check.setChecked(True)
        layout.addWidget(self.map_colorbar_check)
        self.map_colorbar_orientation_combo = QComboBox()
        self.map_colorbar_orientation_combo.addItem('Below map', 'horizontal')
        self.map_colorbar_orientation_combo.addItem('Right of map', 'vertical')
        self._add_field(layout, 'Colour scale position', self.map_colorbar_orientation_combo)
        from ..maps.colorbar_controls import build
        build(self, layout)
        self.map_grid_check = QCheckBox('Show coordinate grid')
        self._add_field(layout, 'Grid spacing', spin('map_grid_spacing_spin', 0, 1e9, 0, 5))
        self.map_north_check = QCheckBox('Show north arrow')
        self.map_north_reference_combo = QComboBox()
        self.map_north_reference_combo.addItem('True north (requires source CRS)', 'true')
        self.map_north_reference_combo.addItem('Grid north / +Y', 'grid')
        self._add_field(layout, 'North reference', self.map_north_reference_combo)
        self.control_tabs.widget(1).widget().layout().insertWidget(2, self.assessment_map_card)
        build_cartographic_controls(self)
        self.initialize_boundary_controls()
        self.boundary_extrapolate_check.setChecked(False)

    def _update_assessment_maps(self):
        if not hasattr(self, 'assessment_map_card'):
            return
        view = self.view_key()
        spatial, mapped = view in ('spatial', 'spatial_map'), view == 'spatial_map'
        self.assessment_map_card.setVisible(spatial)
        self.boundary_card.setVisible(spatial)
        for card in (self.map_grid_card, self.map_north_card, self.map_scale_card):
            card.setVisible(mapped)
        spatial_controls.update(self, spatial=spatial, interpolated=mapped)
        for name in ('assessment_map_output_combo', 'contour_width_spin', 'contour_color_button',
                     'contour_opacity_spin', 'map_colorbar_orientation_combo'):
            getattr(self, name).parentWidget().setVisible(mapped)
        for control in (self.contour_lines_check, self.contour_labels_check, self.contour_samples_check, self.map_colorbar_check):
            control.setVisible(mapped)
        if mapped:
            self.appearance_card.show()

    def _assessment_spatial_config(self):
        from ..maps.colorbar_controls import options
        return dict(source_crs=spatial_controls.source_crs(self), **spatial_controls.display_options(self),
            **spatial_controls.interpolation_options(self), power=self.assessment_power_spin.value(),
            resolution=self.assessment_grid_spin.value(), levels=self.assessment_levels_spin.value(),
            boundary=self._active_boundary(), extrapolate=self._active_boundary() is not None and self.boundary_extrapolate_check.isChecked(),
            samples_inside_boundary=self._active_boundary() is not None and self.boundary_samples_check.isChecked(),
            map_output=self.assessment_map_output_combo.currentData(), map_layout=advanced_layout(self),
            show_samples=self.contour_samples_check.isChecked(), show_colorbar=self.map_colorbar_check.isChecked(),
            colorbar_orientation=self.map_colorbar_orientation_combo.currentData(), colorbar_options=options(self),
            show_grid=self.map_grid_check.isChecked(), grid_spacing=self.map_grid_spacing_spin.value(),
            north_arrow=self.map_north_check.isChecked(), north_reference=self.map_north_reference_combo.currentData(),
            contour_lines=self.contour_lines_check.isChecked(), contour_labels=self.contour_labels_check.isChecked(),
            line_width=self.contour_width_spin.value(), line_color=self.contour_color_button.text(),
            opacity=self.contour_opacity_spin.value())

    def _sync_view_controls(self):
        super()._sync_view_controls()
        if hasattr(self, 'map_scale_check'):
            sync_cartographic_controls(self)
