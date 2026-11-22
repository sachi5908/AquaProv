"""Reusable, saved controls for measured points and threshold highlighting."""
import numpy as np
import pandas as pd
from matplotlib import colors, ticker


def numbers(text, count=None):
    values = [float(part.strip()) for part in text.split(',') if part.strip()]
    if not all(np.isfinite(values)) or (count is not None and len(values) != count):
        raise ValueError('Enter ' + (str(count) if count else 'finite') + ' comma-separated numbers.')
    return values


def build_controls(workspace):
    from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit
    from .ui.color_button import ColorButton
    card, layout = workspace._card('Point colours, zeros & thresholds',
        'Colour and threshold columns are independent. Thresholds use the units of the selected source column. Blanks remain missing.')
    definitions = [
        ('point_scale_combo', 'Colour scale', ['Linear', 'Logarithmic']),
        ('point_limits_edit', 'Colour limits (min, max; blank = automatic)', ''),
        ('point_ticks_edit', 'Colour ticks (comma-separated; blank = automatic)', ''),
        ('point_edge_color_edit', 'Point outline colour', '#ffffff'),
        ('point_edge_width_spin', 'Point outline width (pt)', .35),
        ('point_zero_check', 'Show reported zeros separately', False),
        ('point_zero_marker_combo', 'Zero marker', ['x', 'o', '^', 's', '+']),
        ('point_zero_color_edit', 'Zero colour', '#929aa0'),
        ('point_zero_size_spin', 'Zero marker area (pt²)', 13.),
        ('point_zero_width_spin', 'Zero marker line width (pt)', .7),
        ('point_zero_note_check', 'Show reported-zero count', False),
        ('point_zero_text_edit', 'Zero note (blank = automatic; {n} = zero count)', ''),
        ('point_zero_note_size_spin', 'Zero-note font size (pt)', 6.3),
        ('point_zero_note_color_edit', 'Zero-note text colour', '#243447'),
        ('point_zero_note_x_spin', 'Zero-note horizontal position (%)', 98.),
        ('point_zero_note_y_spin', 'Zero-note vertical position (%)', 98.),
        ('point_threshold_column_combo', 'Highlight using column', ['(none)']),
        ('point_threshold_operator_combo', 'Highlight comparison', ['>', '>=', '<', '<=']),
        ('point_threshold_spin', 'Threshold (source column units)', 50.),
        ('point_threshold_color_edit', 'Highlight colour', '#b52f3b'),
        ('point_threshold_size_spin', 'Highlight ring area (pt²)', 64.),
        ('point_threshold_marker_combo', 'Highlight marker', ['o', 's', 'D', '^']),
        ('point_threshold_width_spin', 'Highlight outline width (pt)', 1.),
        ('point_labels_combo', 'Point labels', ['All', 'Highlighted only', 'None']),
        ('point_label_size_spin', 'Point label size (pt)', 6.5),
        ('point_label_color_edit', 'Point label colour (blank = point/highlight colour)', ''),
        ('point_label_offsets_edit', 'Label offsets (ID:dx,dy; ID:dx,dy; in points)', ''),
        ('point_geographic_check', 'Longitude / latitude aspect (plain coordinates)', False),
        ('point_bounds_check', 'Show coordinate bounds rectangle', True),
    ]
    for name, label, default in definitions:
        if isinstance(default, list):
            widget = QComboBox(); widget.addItems(default)
        elif isinstance(default, bool):
            widget = QCheckBox(label); widget.setChecked(default)
        elif isinstance(default, float):
            widget = QDoubleSpinBox(); widget.setDecimals(4)
            widget.setRange(-1e12, 1e12) if name == 'point_threshold_spin' else widget.setRange(.1, 10000)
            widget.setValue(default)
            if name.endswith('_width_spin'):
                widget.setRange(0,8)
            elif name.endswith(('_note_x_spin','_note_y_spin')):
                widget.setRange(0,100)
            elif name.endswith(('_label_size_spin','_note_size_spin')):
                widget.setRange(4,48)
        elif name.endswith('_color_edit'):
            widget = ColorButton(default, allow_auto=not default)
        else:
            widget = QLineEdit(default)
        setattr(workspace, name, widget)
        if isinstance(widget, QCheckBox):
            layout.addWidget(widget)
        else:
            workspace._add_field(layout, label, widget)
    workspace.control_tabs.widget(1).widget().layout().insertWidget(1, card)
    workspace.observation_card = card


def populate_controls(workspace):
    combo = workspace.point_threshold_column_combo
    current = combo.currentText()
    combo.clear(); combo.addItem('(none)')
    combo.addItems([str(c) for c in getattr(workspace, '_numeric_columns', [])])
    if combo.findText(current) >= 0:
        combo.setCurrentText(current)


def options(workspace):
    from .ui.color_button import ColorButton
    result = {}
    for name, widget in vars(workspace).items():
        if not name.startswith('point_'):
            continue
        key = name[len('point_'):].rsplit('_', 1)[0]
        if isinstance(widget, ColorButton):
            result[key] = widget.text()
        elif hasattr(widget, 'isChecked'):
            result[key] = widget.isChecked()
        elif hasattr(widget, 'currentText'):
            result[key] = widget.currentText()
        elif hasattr(widget, 'value'):
            result[key] = widget.value()
        elif hasattr(widget, 'text'):
            result[key] = widget.text()
    return result


def threshold_mask(frame, settings):
    column = settings.get('threshold_column', '(none)')
    if column == '(none)':
        return np.zeros(len(frame), dtype=bool)
    if column not in frame:
        raise ValueError(f'Highlight column is not available: {column}')
    values = pd.to_numeric(frame[column], errors='coerce').to_numpy(float)
    compare = {'>': np.greater, '>=': np.greater_equal, '<': np.less, '<=': np.less_equal}
    return np.isfinite(values) & compare[settings.get('threshold_operator', '>')](values, settings.get('threshold', 50))


def draw_points(ax, frame, x, y, value=None, *, settings=None, size=23, marker='o',
                alpha=1., color='#087f8c', cmap='viridis', labels=None):
    settings = settings or {}
    x, y = np.asarray(x), np.asarray(y)
    valid = np.isfinite(x) & np.isfinite(y)
    high = threshold_mask(frame, settings) & valid
    zero = np.zeros(len(frame), dtype=bool)
    norm = None
    values = None if value is None else pd.to_numeric(value, errors='coerce').to_numpy(float)
    if values is not None:
        valid &= np.isfinite(values)
        high &= valid
        log = settings.get('scale') == 'Logarithmic'
        if log and np.any(values[valid] < 0):
            raise ValueError('Logarithmic colour scales require non-negative measurements; choose Linear for negative values.')
        if settings.get('zero') or log:
            zero = valid & (values == 0)
            valid &= ~zero
        limits = numbers(settings['limits'], 2) if settings.get('limits', '').strip() else None
        if limits and (limits[0] >= limits[1] or (log and limits[0] <= 0)):
            raise ValueError('Colour minimum must be less than maximum; logarithmic limits must be positive.')
        if log and not valid.any() and limits is None:
            raise ValueError('No positive measurements for a logarithmic colour scale. Set explicit positive limits or choose Linear.')
        norm = (colors.LogNorm if log else colors.Normalize)(*(limits or (None, None)))
    if zero.any() and settings.get('zero', settings.get('scale')=='Logarithmic'):
        ax.scatter(x[zero], y[zero], s=settings.get('zero_size', 13),
                   marker=settings.get('zero_marker', 'x'), color=settings.get('zero_color', '#929aa0'),
                   linewidths=settings.get('zero_width',.7), alpha=alpha, zorder=2, label='Reported zero')
    points = ax.scatter(x[valid], y[valid], c=values[valid] if values is not None else color,
                        norm=norm, cmap=cmap if values is not None else None,
                        s=size, marker=marker, alpha=alpha, edgecolors=settings.get('edge_color','white'), linewidths=settings.get('edge_width',.35), zorder=3, label='Samples')
    if high.any():
        ax.scatter(x[high], y[high], s=settings.get('threshold_size', 64), facecolors='none',
                   edgecolors=settings.get('threshold_color', '#b52f3b'), linewidths=settings.get('threshold_width',1),
                   marker=settings.get('threshold_marker','o'), zorder=4, label='Threshold highlight')
    offsets = {}
    for entry in settings.get('label_offsets', '').split(';'):
        if entry.strip():
            key, pair = entry.rsplit(':', 1)
            offsets[key.strip()] = numbers(pair, 2)
    mode = settings.get('labels', 'All')
    if labels is not None and mode != 'None':
        selected = high if mode == 'Highlighted only' else valid | zero
        for i in np.flatnonzero(selected):
            label = str(labels.iloc[i] if hasattr(labels, 'iloc') else labels[i])
            label_color = settings.get('label_color') or (settings.get('threshold_color','#b52f3b') if high[i] else '#243447')
            annotation = ax.annotate(label, (x[i], y[i]), xytext=offsets.get(label, (5, -9)), textcoords='offset points',
                        fontsize=settings.get('label_size',7), color=label_color)
            annotation._aquaprov_annotation_style = dict(color=label_color,fontsize=settings.get('label_size',7))
    if settings.get('zero_note') and values is not None:
        from .chart_annotations import plot_note
        count = int(np.sum(np.isfinite(values) & (values==0)))
        plot_note(ax, dict(text=settings.get('zero_text',''),x=settings.get('zero_note_x',98)/100,
            y=settings.get('zero_note_y',98)/100,ha='right',va='top',color=settings.get('zero_note_color','#243447'),
            size=settings.get('zero_note_size',6.3)), ('× ' if settings.get('zero_marker','x')=='x' else '')+'reported zero (n = {n})',n=count)
    if settings.get('geographic'):
        ax.set_aspect(1 / np.cos(np.deg2rad(np.mean(y[np.isfinite(y)]))), adjustable='box')
    return points


def configure_colorbar(colorbar, settings):
    if settings.get('ticks', '').strip():
        ticks = numbers(settings['ticks'])
        if settings.get('scale') == 'Logarithmic' and any(t <= 0 for t in ticks):
            raise ValueError('Logarithmic colour ticks must be positive.')
        colorbar.set_ticks(ticks)
        colorbar.formatter = ticker.FormatStrFormatter('%g')
        colorbar.update_ticks()
        colorbar.minorticks_off()
