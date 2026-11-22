"""Shared interpolation additions for derived-index and assessment maps."""
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QLineEdit, QPushButton, QSpinBox


DEFAULTS = {'neighbors_spin': 0, 'grid_mode_combo': 'Cells per axis',
            'cell_size_spin': 20, 'classification_combo': 'Automatic contour intervals',
            'class_breaks_edit': '', 'spatial_surface_combo': 'Module default',
            'map_legend_combo': 'Module default',
            'analysis_crs_edit': '', 'spatial_source_crs_edit': ''}


def restore_defaults(state, *, switching=False):
    for name, value in DEFAULTS.items():
        if switching and name in ('analysis_crs_edit','spatial_source_crs_edit'):
            continue
        state.setdefault('controls', {}).setdefault(name, value)


def build(w, layout, distance, grid, levels, *, assessment=False):
    w._spatial_controls = (distance, grid, levels)
    distance.addItem('WGS84 → automatic UTM / UPS (metres)', 'auto_utm')
    distance.addItem('WGS84 → custom projected CRS (metres)', 'wgs84_projected')
    w.analysis_crs_edit = QLineEdit()
    w.analysis_crs_edit.setPlaceholderText('Projected EPSG code, e.g. EPSG:32645')
    w.spatial_source_crs_edit = QLineEdit()
    w.spatial_source_crs_edit.setPlaceholderText('Optional EPSG code for existing X / Y')
    w.neighbors_spin = QSpinBox()
    w.neighbors_spin.setRange(0, 1000)
    w.neighbors_spin.setSpecialValueText('All samples')
    w.neighbors_spin.setToolTip('IDW only: nearest available samples, including equal-distance ties. Zero uses all samples.')
    w.grid_mode_combo = QComboBox()
    w.grid_mode_combo.addItem('Cells per axis', 'resolution')
    w.grid_mode_combo.addItem('Cell size in analysis units', 'cell_size')
    grid.setMaximum(1000)
    w.cell_size_spin = QDoubleSpinBox()
    w.cell_size_spin.setDecimals(4)
    w.cell_size_spin.setRange(.0001, 1e9)
    w.cell_size_spin.setValue(20)
    w.cell_size_spin.setToolTip('Metres after WGS84 conversion, otherwise source distance units. Maximum 1,000,000 grid points.')
    w.classification_combo = QComboBox()
    for title, key in [('Automatic contour intervals', 'automatic'), ('Equal intervals', 'equal_interval'),
                       ('Quantiles', 'quantile'), ('Natural Breaks (Jenks)', 'natural_breaks'),
                       ('Custom class boundaries', 'custom')]:
        w.classification_combo.addItem(title, key)
    w.classification_combo.setToolTip('Display classes only. Scientific index thresholds remain unchanged. Natural Breaks uses a bounded histogram approximation on large grids; exact thresholds are exported.')
    levels.setRange(2, 40)
    w.class_breaks_edit = QLineEdit()
    w.class_breaks_edit.setPlaceholderText('e.g. 0, 50, 100, 250, 500')
    w.spatial_surface_combo = QComboBox()
    for title, key in [('Module default', 'default'), ('Filled contours', 'contours'), ('Classified raster cells', 'raster')]:
        w.spatial_surface_combo.addItem(title, key)
    w.map_legend_combo = QComboBox()
    w.map_legend_combo.addItem('Module default','default')
    w.map_legend_combo.addItem('Inside map (position from Style)','inside')
    for title, control in [('Analysis CRS', w.analysis_crs_edit), ('Source CRS override', w.spatial_source_crs_edit),
            ('IDW baseline neighbours' if assessment else 'Nearest neighbours', w.neighbors_spin),
            ('Grid definition', w.grid_mode_combo), ('Cell size (distance units)', w.cell_size_spin),
            ('Colour classification', w.classification_combo), ('Class boundaries', w.class_breaks_edit),
            ('Surface drawing', w.spatial_surface_combo), ('Map legend', w.map_legend_combo)]:
        w._add_field(layout, title, control)
    w.local_idw_preset_button = QPushButton('Apply WGS84 map preset' if assessment else 'Apply WGS84 local IDW preset')
    w.local_idw_preset_button.setToolTip('Automatic UTM/UPS, 20-metre cells, five Natural Breaks classes, raster drawing; IDW power 2 with nearest 12 samples. Assessment keeps its fitted kriging model.')
    w.local_idw_preset_button.clicked.connect(lambda: preset(w, assessment=assessment))
    layout.addWidget(w.local_idw_preset_button)
    for control in (distance, w.grid_mode_combo, w.classification_combo):
        control.currentIndexChanged.connect(w._analysis_controls_changed)


def update(w, *, spatial, interpolated, idw=True, classified=False):
    if not hasattr(w, 'grid_mode_combo'):
        return
    mode = w._spatial_controls[0].currentData()
    w.analysis_crs_edit.parentWidget().setVisible(spatial and mode == 'wgs84_projected')
    w.spatial_source_crs_edit.parentWidget().setVisible(spatial and mode == 'projected')
    w.neighbors_spin.parentWidget().setVisible(spatial and idw)
    by_size = w.grid_mode_combo.currentData() == 'cell_size'
    w.grid_mode_combo.parentWidget().setVisible(interpolated)
    w._spatial_controls[1].parentWidget().setVisible(interpolated and not by_size)
    w.cell_size_spin.parentWidget().setVisible(interpolated and by_size)
    colours = interpolated and not classified
    custom = w.classification_combo.currentData() == 'custom'
    w.classification_combo.parentWidget().setVisible(colours)
    w.class_breaks_edit.parentWidget().setVisible(colours and custom)
    w._spatial_controls[2].parentWidget().setVisible(colours and not custom)
    w.spatial_surface_combo.parentWidget().setVisible(colours)
    w.map_legend_combo.parentWidget().setVisible(spatial and not classified)
    w.local_idw_preset_button.setVisible(interpolated)


def interpolation_options(w):
    return dict(neighbors=w.neighbors_spin.value() or None,
                cell_size=w.cell_size_spin.value() if w.grid_mode_combo.currentData() == 'cell_size' else None)


def display_options(w):
    return dict(classification=w.classification_combo.currentData(), class_breaks=w.class_breaks_edit.text(),
                surface_drawing=w.spatial_surface_combo.currentData(), target_crs=w.analysis_crs_edit.text().strip() or None,
                map_legend=w.map_legend_combo.currentData())


def source_crs(w):
    override = w.spatial_source_crs_edit.text().strip() if w._spatial_controls[0].currentData() == 'projected' else ''
    return override or (w._declared_source_crs() if w.map_crs_combo.currentData() else None)


def preset(w, *, assessment=False):
    with QSignalBlocker(w.auto_update_check):
        automatic = w.auto_update_check.isChecked()
        w.auto_update_check.setChecked(False)
    try:
        prefix = 'assessment' if assessment else 'wq' if w.module_key == 'water_quality' else 'si'
        if not assessment:
            control = getattr(w, prefix + '_interpolation_combo')
            control.setCurrentIndex(control.findData('idw'))
        getattr(w, prefix + '_power_spin').setValue(2)
        w._spatial_controls[0].setCurrentIndex(w._spatial_controls[0].findData('auto_utm'))
        w.map_crs_combo.setCurrentIndex(w.map_crs_combo.findData('wgs84'))
        w.neighbors_spin.setValue(12)
        w.grid_mode_combo.setCurrentIndex(w.grid_mode_combo.findData('cell_size'))
        w.cell_size_spin.setValue(20)
        w.classification_combo.setCurrentIndex(w.classification_combo.findData('natural_breaks'))
        w._spatial_controls[2].setValue(5)
        w.spatial_surface_combo.setCurrentIndex(w.spatial_surface_combo.findData('raster'))
        w.map_legend_combo.setCurrentIndex(w.map_legend_combo.findData('inside'))
        w.map_frame_sides_combo.setCurrentIndex(w.map_frame_sides_combo.findData('bottom_left'))
        w.map_coordinate_mode_combo.setCurrentIndex(w.map_coordinate_mode_combo.findData('geographic'))
        w.contour_lines_check.setChecked(False)
        w.contour_labels_check.setChecked(False)
    finally:
        with QSignalBlocker(w.auto_update_check):
            w.auto_update_check.setChecked(automatic)
    w._analysis_controls_changed()
    w._setting_changed()
