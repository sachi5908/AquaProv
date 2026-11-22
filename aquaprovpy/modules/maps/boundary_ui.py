"""Study-area state, import/export and manual drawing controls."""
from copy import deepcopy
import numpy as np
import pandas as pd
from shapely.geometry import mapping, shape
from PySide6.QtWidgets import QCheckBox, QFileDialog, QLabel, QMessageBox, QPushButton

from ...boundaries import import_boundaries, merge_boundaries, source_crs, geometry_in_crs, validate_boundary


class BoundaryWorkspaceMixin:
    def initialize_boundary_controls(self):
        self.boundary_card, layout = self._card('Study-area boundary',
            'Draw an area or import KML, KMZ or GeoJSON polygons. Boundaries are embedded in saved projects.')
        self.boundary_summary = QLabel('No study boundary. Interpolation uses the sample convex hull.')
        self.boundary_summary.setWordWrap(True)
        layout.addWidget(self.boundary_summary)
        self.boundary_enabled_check = QCheckBox('Use study boundary')
        self.boundary_extrapolate_check = QCheckBox('Fill entire boundary (extrapolate)')
        self.boundary_extrapolate_check.setChecked(True)
        self.boundary_samples_check = QCheckBox('Use only samples inside boundary')
        self.boundary_extrapolate_check.setToolTip('Fill the complete polygon, including areas beyond the outermost samples. Extrapolated grid cells are flagged in Results. Uncheck to restrict coverage to the sampled area.')
        self.boundary_samples_check.setToolTip('Unchecked: nearby samples outside the boundary may still inform the interpolation.')
        layout.addWidget(self.boundary_enabled_check)
        for name, title, callback in [
            ('boundary_import_button', 'Import KML / KMZ / GeoJSON…', self.import_boundary),
            ('boundary_draw_button', 'Draw / edit study area…', self.draw_study_area),
            ('boundary_export_button', 'Export boundary as GeoJSON…', self.export_boundary),
            ('boundary_clear_button', 'Clear boundary', self.clear_boundary),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            setattr(self, name, button)
            layout.addWidget(button)
        layout.addWidget(self.boundary_extrapolate_check)
        coverage_note = QLabel('Full coverage estimates beyond the outermost samples. Uncheck to show only the sampled area.')
        coverage_note.setWordWrap(True)
        coverage_note.setObjectName('muted')
        layout.addWidget(coverage_note)
        layout.addWidget(self.boundary_samples_check)
        self.control_tabs.widget(0).widget().layout().insertWidget(2, self.boundary_card)
        self.boundary_enabled_check.toggled.connect(self._refresh_boundary_summary)
        self._refresh_boundary_summary()

    def _active_boundary(self):
        if getattr(self, 'study_boundary', None) is not None and self.boundary_enabled_check.isChecked():
            return deepcopy(self.study_boundary)
        return None

    def _refresh_boundary_summary(self, *_):
        if not hasattr(self, 'boundary_summary'):
            return
        has = self.study_boundary is not None
        self.boundary_export_button.setEnabled(has)
        self.boundary_clear_button.setEnabled(has)
        self.boundary_enabled_check.setEnabled(has)
        for control in (self.boundary_extrapolate_check, self.boundary_samples_check):
            control.setEnabled(has and self.boundary_enabled_check.isChecked())
        if has:
            geometry = shape(self.study_boundary['geometry'])
            parts = [geometry] if geometry.geom_type == 'Polygon' else geometry.geoms
            holes = sum(len(p.interiors) for p in parts)
            self.boundary_summary.setText(f"{self.study_boundary['name']} · {len(parts)} part(s), {holes} hole(s) · {self.study_boundary['crs']}")
        else:
            self.boundary_summary.setText('No study boundary. Interpolation uses the sample convex hull.')

    def set_study_boundary(self, boundary):
        candidate = validate_boundary(boundary) if boundary is not None else None
        self._clear_plot_cache()
        self.study_boundary = candidate
        self.boundary_enabled_check.setChecked(candidate is not None)
        self._refresh_boundary_summary()
        self._invalidate_plot()
        self._setting_changed()

    def clear_boundary(self):
        self.set_study_boundary(None)
        self.boundary_extrapolate_check.setChecked(True)
        self.boundary_samples_check.setChecked(False)

    def import_boundary(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import study boundary', '',
                    'Study boundaries (*.kml *.kmz *.geojson *.json);;KML (*.kml);;KMZ (*.kmz);;GeoJSON (*.geojson *.json)')
        if not path:
            return
        try:
            features = import_boundaries(path)
            if len(features) > 1:
                from .boundary_editor import BoundaryPicker
                dialog = BoundaryPicker(features, self)
                if not dialog.exec():
                    return
                features = dialog.selected()
            self.set_study_boundary(merge_boundaries(features))
            self.statusBar().showMessage('Boundary imported. Generate a map or interpolation to apply it.')
        except Exception as exc:
            QMessageBox.warning(self, 'Could not import boundary', str(exc))

    def _declared_source_crs(self):
        return source_crs(self.map_crs_combo.currentData(), self.map_zone_spin.value(), self.map_hemisphere_combo.currentData())

    def draw_study_area(self):
        try:
            if self.data is None:
                raise ValueError('Import sample coordinates before drawing the study area.')
            x, y = self.map_x_combo.currentText(), self.map_y_combo.currentText()
            if x == y or x not in self.data or y not in self.data:
                raise ValueError('Choose separate X and Y coordinate columns in Data.')
            raw = self.data[[x, y]].apply(pd.to_numeric, errors='coerce')
            xy = raw[np.isfinite(raw).all(axis=1)].to_numpy()
            if not len(xy):
                raise ValueError('The chosen columns contain no finite coordinate pairs.')
            crs = self._declared_source_crs()
            declared = crs
            provider = self._basemap_key()
            if provider != 'plain':
                from ...locations import project_coordinates
                mx, my, _, _ = project_coordinates(*xy.T, self.map_crs_combo.currentData(),
                         self.map_zone_spin.value(), self.map_hemisphere_combo.currentData())
                xy, crs = np.column_stack((mx, my)), 'EPSG:3857'
            from .boundary_editor import BoundaryEditor
            dialog = BoundaryEditor(xy, crs, boundary=self.study_boundary, provider=provider,
                                    declared_local_crs=declared, parent=self)
            try:
                if dialog.exec():
                    self.set_study_boundary(dialog.boundary)
            finally:
                dialog.deleteLater()
        except Exception as exc:
            QMessageBox.warning(self, 'Could not draw study area', str(exc))

    def export_boundary(self):
        if self.study_boundary is None:
            return
        try:
            geometry = geometry_in_crs(self.study_boundary, 'EPSG:4326', declared_local_crs=self._declared_source_crs())
            path, _ = QFileDialog.getSaveFileName(self, 'Export study boundary', 'study_boundary.geojson', 'GeoJSON (*.geojson)')
            if not path:
                return
            from ...core.projects import atomic_json
            atomic_json(path, {'type': 'Feature', 'properties': {'name': self.study_boundary['name']}, 'geometry': mapping(geometry)})
            self.statusBar().showMessage('Study boundary exported in WGS84 longitude/latitude.')
        except Exception as exc:
            QMessageBox.warning(self, 'Could not export boundary', str(exc))

    def _capture_current_state(self):
        state = super()._capture_current_state()
        state['study_boundary'] = deepcopy(self.study_boundary)
        return state

    def _capture_profile(self):
        state = super()._capture_profile()
        state.pop('study_boundary', None)
        for name in ('boundary_enabled_check', 'boundary_extrapolate_check', 'boundary_samples_check'):
            state['controls'].pop(name, None)
        return state

    def _restore_current_state(self, state):
        # Boundary coverage belongs to the study area, not an individual plot.
        # Ignore legacy per-plot copies when switching views; top-level project
        # controls remain authoritative when reopening a saved project.
        if getattr(self, '_switching_plot', False) and not getattr(self, '_restoring_boundary_project', False):
            state = deepcopy(state)
            for name in ('boundary_enabled_check', 'boundary_extrapolate_check', 'boundary_samples_check'):
                state.get('controls', {}).pop(name, None)
        if 'study_boundary' in state:
            self.study_boundary = validate_boundary(state['study_boundary']) if state['study_boundary'] else None
        super()._restore_current_state(state)
        self._refresh_boundary_summary()

    def restore_state(self, state):
        self._restoring_boundary_project = True
        try:
            super().restore_state(state)
        finally:
            self._restoring_boundary_project = False

    def populate_module_columns(self):
        super().populate_module_columns()
        if hasattr(self, 'boundary_enabled_check'):
            self.study_boundary = None
            self.boundary_enabled_check.setChecked(False)
            self.boundary_extrapolate_check.setChecked(True)
            self.boundary_samples_check.setChecked(False)
            self._refresh_boundary_summary()
