"""Editable measured-series charts; rows are observations, not invented dates."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import is_color_like
from matplotlib.markers import MarkerStyle
from ._publication import PlotResult, close_on_error


def build_controls(workspace, layout):
    from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QLineEdit
    from .ui.color_button import ColorButton, ColorPalette
    workspace.series_fields = []
    for name, label, default in [
        ('series_order_edit', 'Series column order (semicolon-separated; blank = selected order)', ''),
        ('series_colors_edit', 'Series colours', '#087f8c, #d17a32'),
        ('series_markers_edit', 'Series markers (comma-separated)', 'o, ^'),
        ('series_names_edit', 'Series legend names (comma-separated; blank = columns)', ''),
        ('series_sizes_edit', 'Individual marker areas (comma-separated; blank = Style size)', ''),
        ('series_edge_color_edit', 'Point outline colour', '#ffffff'),
        ('series_edge_width_spin', 'Point outline width (pt)', .25),
        ('series_zero_check', 'Draw reported zeros as open markers', True),
        ('series_zero_size_spin', 'Zero marker area (pt²)', 12.),
        ('series_zero_width_spin', 'Zero outline width (pt)', .6),
        ('series_offset_spin', 'Horizontal separation between series (rows)', .36),
        ('series_threshold_check', 'Show horizontal threshold', False),
        ('series_threshold_spin', 'Threshold (measurement units)', 50.),
        ('series_threshold_label_edit', 'Threshold legend label', 'Threshold'),
        ('series_threshold_color_edit', 'Threshold colour', '#b52f3b'),
        ('series_threshold_width_spin', 'Threshold line width (pt)', .85),
        ('series_threshold_style_edit', 'Threshold line style (-, --, :, -.)', '--'),
    ]:
        if isinstance(default, bool):
            widget = QCheckBox(label); widget.setChecked(default)
        elif isinstance(default, float):
            widget = QDoubleSpinBox(); widget.setRange(-1e12, 1e12); widget.setDecimals(4); widget.setValue(default)
            if name == 'series_zero_size_spin':
                widget.setRange(.1, 10000)
            if name.endswith('_width_spin'):
                widget.setRange(0,8)
        elif name == 'series_colors_edit':
            widget = ColorPalette(default)
        elif name.endswith('_color_edit'):
            widget = ColorButton(default)
        else:
            widget = QLineEdit(default)
        setattr(workspace, name, widget)
        if isinstance(widget, QCheckBox):
            layout.addWidget(widget); workspace.series_fields.append(widget)
        else:
            workspace.series_fields.append(workspace._add_field(layout, label, widget))


def options(workspace):
    return dict(colors=workspace.series_colors_edit.text(), markers=workspace.series_markers_edit.text(),
                names=workspace.series_names_edit.text(), open_zeros=workspace.series_zero_check.isChecked(),
                zero_size=workspace.series_zero_size_spin.value(),
                sizes=workspace.series_sizes_edit.text(),edge_color=workspace.series_edge_color_edit.text(),edge_width=workspace.series_edge_width_spin.value(),
                zero_width=workspace.series_zero_width_spin.value(),threshold_width=workspace.series_threshold_width_spin.value(),threshold_style=workspace.series_threshold_style_edit.text(),
                offset=workspace.series_offset_spin.value(),
                threshold=workspace.series_threshold_spin.value() if workspace.series_threshold_check.isChecked() else None,
                threshold_label=workspace.series_threshold_label_edit.text(), threshold_color=workspace.series_threshold_color_edit.text(),
                size=workspace.size_spin.value(), alpha=workspace.alpha_spin.value())


@close_on_error
def plot(df, unit='mg/L', figname=None, *, columns, colors='#087f8c, #d17a32', markers='o, ^', names='',
         open_zeros=True, offset=.36, threshold=None, threshold_label='Threshold', threshold_color='#b52f3b',
         size=14, alpha=1, zero_size=12, sizes='', edge_color='white', edge_width=.25, zero_width=.6, threshold_width=.85, threshold_style='--'):
    if not columns:
        raise ValueError('Select at least one measurement variable.')
    if not np.isfinite([size, zero_size, offset, alpha]).all() or size <= 0 or zero_size <= 0 or not 0 <= alpha <= 1:
        raise ValueError('Marker sizes must be positive and opacity must be between zero and one.')
    palette = [c.strip() for c in colors.split(',') if c.strip()]
    symbols = [m.strip() for m in markers.split(',') if m.strip()]
    legends = [n.strip() for n in names.split(',')] if names.strip() else columns
    if not palette or not all(is_color_like(c) for c in palette):
        raise ValueError('Enter valid series colours, separated by commas.')
    if not symbols:
        raise ValueError('Enter at least one marker symbol.')
    for symbol in symbols:
        MarkerStyle(symbol)
    if len(legends) != len(columns):
        raise ValueError('Provide one legend name per selected measurement, or leave names blank.')
    from .observation_options import numbers
    areas = numbers(sizes,len(columns)) if sizes.strip() else [size]*len(columns)
    if any(value <= 0 for value in areas):
        raise ValueError('Individual marker areas must be positive.')
    if threshold_style not in ('-','--',':','-.'):
        raise ValueError('Choose a threshold line style: -, --, : or -.')
    fig, ax = plt.subplots(figsize=(6.4, 4), layout='constrained')
    tables, handles = [], []
    for i, column in enumerate(columns):
        values = pd.to_numeric(df[column], errors='coerce').to_numpy(float)
        invalid = df[column].notna().to_numpy() & ~np.isfinite(values)
        if invalid.any():
            raise ValueError(f'{column}: resolve non-numeric or infinite measurements before plotting.')
        row = np.arange(1, len(df)+1)
        x = row + (i - (len(columns)-1)/2) * offset
        zero = np.isfinite(values) & (values == 0) if open_zeros else np.zeros(len(df), bool)
        finite = np.isfinite(values) & ~zero
        color, marker = palette[i % len(palette)], symbols[i % len(symbols)]
        ax.scatter(x[finite], values[finite], s=areas[i], marker=marker, color=color, edgecolors=edge_color, linewidths=edge_width, alpha=alpha)
        ax.scatter(x[zero], values[zero], s=zero_size, marker=marker, facecolors='none', edgecolors=color, linewidths=zero_width, alpha=alpha)
        handles.append(Line2D([], [], marker=marker, color=color, lw=0, markersize=np.sqrt(areas[i]), label=legends[i]))
        if zero.any():
            handles.append(Line2D([], [], marker=marker, color=color, lw=0, markerfacecolor='none',
                                  markersize=np.sqrt(zero_size), label=legends[i] + ' (reported zero)'))
        tables.append(pd.DataFrame(dict(row=row, sample=df['Sample'].astype(str).to_numpy() if 'Sample' in df else row,
                                        variable=column, value=values, reported_zero=values == 0, plotted=np.isfinite(values))))
    if threshold is not None:
        ax.axhline(threshold, color=threshold_color, ls=threshold_style, lw=threshold_width,gid='aquaprov-series-threshold')
        handles.append(Line2D([], [], color=threshold_color, ls=threshold_style,lw=threshold_width, label=threshold_label))
    ax.legend(handles=handles, loc='upper right', frameon=False)
    ax.set(xlabel='Source data row', ylabel='Reported measurement (source units)', title='Measured concentrations', xlim=(0, len(df)+1))
    from .plot_layout import outside_legend
    outside_legend(fig)
    return PlotResult(fig, {'series_observations': pd.concat(tables, ignore_index=True)},
                      {'analysis': 'Measured series', 'columns': columns, 'zero_policy': 'Reported zeros retained; missing measurements omitted per series'}, [])
