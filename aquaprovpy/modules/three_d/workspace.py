"""Workspace for XYZ plots and 3D PCA scores and loadings."""

import pandas as pd
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QMessageBox, QSpinBox
from ..base import ModuleWorkspace
from .workspace_tools import ThreeDWorkspaceToolsMixin
from ...core.catalog import DIAGRAMS, STATISTICAL_VIEWS
from ...ui.loading import plot_loading


class ThreeDWorkspace(ThreeDWorkspaceToolsMixin, ModuleWorkspace):
    module_key = "three_d"

    def __init__(self):
        super().__init__()
        self.configure_diagrams([name for name in DIAGRAMS if "3D" in name])
        self.hide_locations()
        self.xyz_card, layout = self._card("3D view", "Choose three numeric axes. Surface views interpolate Z within the sampled X/Y boundary.")
        self.three_d_mode_combo = QComboBox()
        self.three_d_mode_combo.addItems(["XYZ scatter", "XYZ surface (linear)", "PCA 3D"])
        self.x_axis_combo, self.y_axis_combo, self.z_axis_combo = QComboBox(), QComboBox(), QComboBox()
        for label, widget in [("View", self.three_d_mode_combo), ("X axis", self.x_axis_combo),
                              ("Y axis", self.y_axis_combo), ("Z axis", self.z_axis_combo)]:
            self._add_field(layout, label, widget)
        self.control_tabs.widget(1).widget().layout().insertWidget(0, self.xyz_card)
        self.surface_card, surface = self._card("Surface settings")
        self.surface_grid_spin = QSpinBox()
        self.surface_grid_spin.setRange(20, 160)
        self.surface_grid_spin.setValue(65)
        self.surface_alpha_spin = QDoubleSpinBox()
        self.surface_alpha_spin.setRange(.05, 1)
        self.surface_alpha_spin.setSingleStep(.05)
        self.surface_alpha_spin.setValue(1.)
        self.surface_alpha_spin.setToolTip('Use 1 for an opaque publication surface without transparency seams; lower values reveal objects behind it.')
        self.surface_samples_check = QCheckBox("Show measured sample points")
        self.surface_samples_check.setChecked(True)
        self.surface_edges_check = QCheckBox("Show surface mesh edges")
        self.projection_combo = QComboBox()
        self.projection_combo.addItems(["Perspective", "Orthographic"])
        self._add_field(surface, "Grid cells per axis", self.surface_grid_spin)
        self._add_field(surface, "Surface opacity", self.surface_alpha_spin)
        surface.addWidget(self.surface_samples_check)
        surface.addWidget(self.surface_edges_check)
        self._add_field(layout, "Camera projection", self.projection_combo)
        self.origin_lines_check = QCheckBox("Show lines from origin to points")
        self.origin_lines_check.setChecked(True)
        layout.addWidget(self.origin_lines_check)
        self.control_tabs.widget(1).widget().layout().insertWidget(1, self.surface_card)
        self.three_d_mode_combo.currentIndexChanged.connect(self._mode_changed)
        self.surface_samples_check.toggled.connect(self._mode_changed)
        self.color_combo.currentIndexChanged.connect(self._mode_changed)
        self._axis_column_names = {}
        for dimension, combo in zip('xyz', (self.x_axis_combo, self.y_axis_combo, self.z_axis_combo)):
            combo.currentTextChanged.connect(lambda column, d=dimension: self._axis_column_changed(d, column))
            combo.setToolTip('Changing the measurement resets its axis label, limits and ticks to the new data.')
        self.color_combo.setToolTip(
            'Choose a measurement to colour PCA scores and show its numeric colour scale. '
            'Single colour uses the sample/group colours without a numeric scale.')
        self._mode_changed()
        self.preview_tabs.setCurrentIndex(1)
        self.run_note.setText("Choose XYZ axes or a PCA view, then Generate. Drag the figure to rotate; use the camera controls for exact angles.")
        self.connect_settings()
        # Connect camera controls after the general settings handlers so
        # changing the view does not queue a new calculation.
        self.initialize_three_d_tools()

    def populate_module_columns(self):
        if not hasattr(self, "x_axis_combo"):
            return
        numeric = list(self._numeric_columns)
        for index, combo in enumerate((self.x_axis_combo, self.y_axis_combo, self.z_axis_combo)):
            combo.clear()
            combo.addItems(numeric)
            combo.setCurrentIndex(min(index, len(numeric) - 1))

    def _mode_changed(self, *_):
        pca = self.three_d_mode_combo.currentIndex() == 2
        self.chart_card.setVisible(pca)
        self.analysis_card.setVisible(pca)
        self.surface_card.setVisible(self.three_d_mode_combo.currentIndex() == 1)
        self.origin_lines_check.setText('Show lines from origin to points' if pca else 'Show coordinate guides')
        self.origin_lines_check.setToolTip(
            'Connect (0, 0, 0) to PCA scores or loading endpoints, including in exported images.' if pca else
            'Draw dashed perpendicular guides from each visible sample to the X/Y/Z coordinate planes. '
            'Guides help read a saved image while keeping the data scale unchanged.')
        self.origin_lines_check.setEnabled(self.three_d_mode_combo.currentIndex() != 1 or self.surface_samples_check.isChecked())
        self.projection_combo.parentWidget().show()
        self.label_combo.parentWidget().setVisible(pca)
        self.color_combo.parentWidget().setVisible(pca)
        scores = STATISTICAL_VIEWS.get(self.diagram_combo.currentText()) == 'pca_scores_3d'
        self.colour_scale_note.setText(
            'For a numbered colourbar, choose a measurement under Settings > Sample appearance > Color by numeric column.'
            if scores else 'PCA loadings use variable colours and do not have a numeric colourbar.')
        self.colour_scale_note.setVisible(pca and (not scores or self.color_combo.currentIndex() <= 0))
        for combo in (self.x_axis_combo, self.y_axis_combo, self.z_axis_combo):
            combo.parentWidget().setVisible(not pca)

    def _analysis_controls_changed(self, *_):
        super()._analysis_controls_changed()
        if hasattr(self, "three_d_mode_combo"):
            self._mode_changed()

    def _axis_column_changed(self, dimension, column):
        previous = self._axis_column_names.get(dimension)
        self._axis_column_names[dimension] = column
        if (not previous or not column or previous == column or self._restoring
                or getattr(self, '_switching_plot', False) or getattr(self, '_updating_data', False)):
            return
        # Imported publication profiles may contain concentration/geographic
        # labels and fixed ticks. They cannot describe a different measurement.
        for suffix in ('label', 'limits', 'ticks', 'tick_format', 'tick_divisor'):
            control = self.style_controls.get(dimension + '_' + suffix)
            if control is not None:
                control.clear()
        if dimension == 'z':
            self.style_controls['colorbar_label'].clear()
        import re
        title = self.style_controls['title']
        if re.search(r'(?<!\w)' + re.escape(previous) + r'(?!\w)', title.text()):
            title.clear()

    def _restore_current_state(self, state):
        self._stop_rotation()
        # Older plot profiles have no origin-line preference; use the new default.
        state = dict(state, controls={'origin_lines_check': True, **state.get('controls', {})})
        super()._restore_current_state(state)

    @plot_loading
    def generate(self):
        self._stop_rotation()
        camera = self._camera_for_generation()
        if self.three_d_mode_combo.currentIndex() == 2:
            self.generate_analysis()
            self._apply_generated_camera(camera)
            return
        self._clear_analysis()
        self.generated_plot = None
        self.save_button.setEnabled(False)
        try:
            from .plots import plot_xyz
            columns = (self.x_axis_combo.currentText(), self.y_axis_combo.currentText(), self.z_axis_combo.currentText())
            data = self._prepare_plot_data(self.data, columns)
            options = dict(surface=self.three_d_mode_combo.currentIndex() == 1,
                resolution=self.surface_grid_spin.value(), surface_alpha=self.surface_alpha_spin.value(),
                show_samples=self.surface_samples_check.isChecked(), mesh_edges=self.surface_edges_check.isChecked(),
                marker=self.marker_combo.currentText(), sample_size=self.size_spin.value(), sample_alpha=self.alpha_spin.value(),
                sample_color=self.color_button.text(), projection='ortho' if self.projection_combo.currentIndex() else 'persp',
                show_origin_lines=self.origin_lines_check.isChecked())
            result = self._run_plot_job(lambda: plot_xyz(data, *columns, **options))
            self.show_result(result, self.three_d_mode_combo.currentText())
            self._apply_generated_camera(camera)
            self.statusBar().showMessage("3D view ready. Drag to rotate, or set elevation and azimuth above the figure.")
        except Exception as exc:
            self.plot_loader.hide()
            self._report_plot_error("Could not generate 3D view", exc)
