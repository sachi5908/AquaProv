"""Cartographic layout controls shared by all Maps views."""
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox


def build_cartographic_controls(w):
    settings = w.control_tabs.widget(1).widget().layout()

    def combo(layout, name, label, items):
        widget = QComboBox()
        for text, value in items:
            widget.addItem(text,value)
        setattr(w,name,widget)
        w._add_field(layout,label,widget)
        return widget

    def number(layout, name, label, value, minimum, maximum, decimals=0, auto=False):
        widget = QDoubleSpinBox()
        widget.setRange(minimum,maximum); widget.setDecimals(decimals); widget.setValue(value)
        if auto:
            widget.setSpecialValueText('Automatic')
        setattr(w,name,widget)
        w._add_field(layout,label,widget)
        return widget

    def check(layout,name,label,value=False):
        widget = QCheckBox(label); widget.setChecked(value)
        setattr(w,name,widget); layout.addWidget(widget)
        return widget

    w.map_grid_card, grid = w._card('Coordinates and grid',
        'Geographic labels and graticules use the source CRS. Angular intervals apply independently to longitude and latitude.')
    combo(grid,'map_coordinate_mode_combo','Frame coordinates', [('Map coordinates','native'),('Longitude / latitude','geographic')])
    combo(grid,'map_coordinate_format_combo','Geographic label format', [('Degrees, minutes, seconds','dms'),('Decimal degrees','decimal'),('Degrees and decimal minutes','dm')])
    number(grid,'map_coordinate_precision_spin','Decimal places',0,0,6)
    combo(grid,'map_frame_sides_combo','Labelled borders', [('All four sides','all'),('Bottom and left','bottom_left')])
    number(grid,'map_coordinate_font_spin','Coordinate label size (pt)',8,5,20,1)
    check(grid,'map_minor_ticks_check','Minor ticks between grid intervals',True)
    grid.addWidget(w.map_grid_check)
    grid.addWidget(w.map_grid_spacing_spin.parentWidget())
    number(grid,'map_grid_y_spacing_spin','Y grid spacing (axis units)',0,0,1e9,5,True)
    combo(grid,'map_angular_unit_combo','Angular interval units',[('Arc seconds','seconds'),('Arc minutes','minutes'),('Degrees','degrees')])
    number(grid,'map_longitude_interval_spin','Longitude interval',0,0,3600*90,4,True)
    number(grid,'map_latitude_interval_spin','Latitude interval',0,0,3600*90,4,True)
    combo(grid,'map_grid_design_combo','Grid design',[('Dashed lines','dashed'),('Solid lines','solid'),('Dotted lines','dotted'),('Intersection crosses','crosses'),('Frame ticks only','frame')])
    number(grid,'map_grid_width_spin','Grid line width (pt)',.55,.1,4,2)
    from ...ui.color_button import ColorButton
    w.map_grid_color_button = ColorButton('#687c8d')
    w._add_field(grid,'Grid colour',w.map_grid_color_button)
    number(grid,'map_grid_alpha_spin','Grid opacity',.5,0,1,2)
    settings.insertWidget(3,w.map_grid_card)

    w.map_north_card, north = w._card('North arrow',
        'Drag the symbol in the preview to place it. Its position is saved with this plot. True north follows the projection at the symbol.')
    north.addWidget(w.map_north_check)
    north.addWidget(w.map_north_reference_combo.parentWidget())
    combo(north,'map_north_design_combo','Arrow design',[('Simple arrow','arrow'),('Split chevron','chevron'),('Four-point compass','compass'),('Eight-point compass','nautical')])
    number(north,'map_north_size_spin','Arrow size (pt)',36,12,120)
    number(north,'map_north_x_spin','Horizontal position (%)',88,3,95,2)
    number(north,'map_north_y_spin','Vertical position (%)',76,6,94,2)
    settings.insertWidget(4,w.map_north_card)

    w.map_scale_card, scale = w._card('Scale bar',
        'Drag the bar to move it. Distances are measured on the ground at the bar location and update when you pan or zoom.')
    check(scale,'map_scale_check','Show scale bar')
    combo(scale,'map_scale_design_combo','Scale design',[('Alternating black / white','alternating'),('Line with ticks','line'),('Dual kilometres / miles','dual')])
    combo(scale,'map_scale_unit_combo','Distance units',[('Kilometres','km'),('Metres','m'),('Miles','mi'),('Feet','ft')])
    length = number(scale,'map_scale_length_spin','Total length (selected units)',0,0,1e9,4,True)
    length.setToolTip('Zero chooses a rounded length. A fixed length is shortened and relabelled if it no longer fits after zooming.')
    number(scale,'map_scale_segments_spin','Divisions',4,2,8)
    number(scale,'map_scale_font_spin','Scale label size (pt)',8,5,20,1)
    check(scale,'map_scale_background_check','White background behind scale',True)
    combo(scale,'map_scale_local_unit_combo','Distance unit for local X/Y',[('(choose if CRS is unknown)',None),('Metres','m'),('Kilometres','km'),('Feet','ft'),('Miles','mi')])
    number(scale,'map_scale_x_spin','Horizontal position (%)',12,3,80,2)
    number(scale,'map_scale_y_spin','Vertical position (%)',10,7,90,2)
    settings.insertWidget(5,w.map_scale_card)

    def refresh(*_):
        geographic = w.map_coordinate_mode_combo.currentData()=='geographic'
        for widget in (w.map_coordinate_format_combo,w.map_coordinate_precision_spin,w.map_angular_unit_combo,
                       w.map_longitude_interval_spin,w.map_latitude_interval_spin):
            widget.parentWidget().setVisible(geographic)
        for widget in (w.map_grid_spacing_spin,w.map_grid_y_spacing_spin):
            widget.parentWidget().setVisible(not geographic)
        for widget in (w.map_north_design_combo,w.map_north_size_spin,w.map_north_x_spin,w.map_north_y_spin):
            widget.setEnabled(w.map_north_check.isChecked())
        for widget in (w.map_scale_design_combo,w.map_scale_unit_combo,w.map_scale_length_spin,w.map_scale_segments_spin,
                       w.map_scale_font_spin,w.map_scale_background_check,w.map_scale_local_unit_combo,w.map_scale_x_spin,w.map_scale_y_spin):
            widget.setEnabled(w.map_scale_check.isChecked())
        if w.map_scale_design_combo.currentData()=='dual':
            w.map_scale_unit_combo.setCurrentIndex(w.map_scale_unit_combo.findData('km'))
            w.map_scale_unit_combo.setEnabled(False)
    for widget in (w.map_coordinate_mode_combo,w.map_scale_design_combo):
        widget.currentIndexChanged.connect(refresh)
    w.map_north_check.toggled.connect(refresh)
    w.map_scale_check.toggled.connect(refresh)
    refresh()


def advanced_layout(w):
    factor = {'degrees':1.,'minutes':60.,'seconds':3600.}[w.map_angular_unit_combo.currentData()]
    return dict(north_design=w.map_north_design_combo.currentData(),north_size=w.map_north_size_spin.value(),
        north_position=[w.map_north_x_spin.value()/100,w.map_north_y_spin.value()/100],
        scale_bar=w.map_scale_check.isChecked(),scale_design=w.map_scale_design_combo.currentData(),
        scale_unit=w.map_scale_unit_combo.currentData(),scale_length=w.map_scale_length_spin.value(),
        scale_segments=int(w.map_scale_segments_spin.value()),scale_position=[w.map_scale_x_spin.value()/100,w.map_scale_y_spin.value()/100],
        scale_background=w.map_scale_background_check.isChecked(),scale_font_size=w.map_scale_font_spin.value(),
        local_unit=w.map_scale_local_unit_combo.currentData(),coordinate_mode=w.map_coordinate_mode_combo.currentData(),
        coordinate_format=w.map_coordinate_format_combo.currentData(),coordinate_precision=int(w.map_coordinate_precision_spin.value()),
        coordinate_font_size=w.map_coordinate_font_spin.value(),frame_sides=w.map_frame_sides_combo.currentData(),
        longitude_interval=w.map_longitude_interval_spin.value()/factor,latitude_interval=w.map_latitude_interval_spin.value()/factor,
        minor_ticks=w.map_minor_ticks_check.isChecked(),grid_spacing_y=w.map_grid_y_spacing_spin.value(),
        grid_design=w.map_grid_design_combo.currentData(),grid_width=w.map_grid_width_spin.value(),
        grid_color=w.map_grid_color_button.text(),grid_alpha=w.map_grid_alpha_spin.value())


def sync_cartographic_controls(w):
    if w.analysis_canvas is None or not hasattr(w,'map_north_x_spin'):
        return
    figure = w.analysis_canvas.figure
    if not getattr(figure,'_aquaprov_layout_moved',False):
        return
    figure._aquaprov_layout_moved = False
    from PySide6.QtCore import QSignalBlocker
    layout = getattr(figure,'_aquaprov_map_layout',{})
    changed = False
    for key, widgets in [('north_position',(w.map_north_x_spin,w.map_north_y_spin)),
                         ('scale_position',(w.map_scale_x_spin,w.map_scale_y_spin))]:
        for value,widget in zip(layout.get(key,[]),widgets):
            value = round(value*100,2)
            if widget.value()!=value:
                with QSignalBlocker(widget):
                    widget.setValue(value)
                changed = True
    if changed:
        # Dragging furniture already updates the live figure and its layout.
        w.settings_changed.emit()

