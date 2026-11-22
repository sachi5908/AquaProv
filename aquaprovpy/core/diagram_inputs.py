"""Shared input requirements for desktop and Python geochemical plots."""
import numpy as np

from .catalog import DIAGRAMS, DIAGRAM_GROUPS, GROUNDWATER_DIAGRAMS
from .plot_data import complete_samples
from .progress import report_progress


def prepare_diagram_data(frame, module_name):
    required = next(columns.split() for engine, columns in DIAGRAMS.values() if engine == module_name)
    return complete_samples(frame, required, numeric_groups=DIAGRAM_GROUPS.get(module_name))


def diagram_availability(frame):
    """Describe input coverage, leaving scientific domain checks to the engine."""
    result = {}
    for index, name in enumerate(GROUNDWATER_DIAGRAMS):
        report_progress(100 * index / len(GROUNDWATER_DIAGRAMS), f'Checking {name} inputs')
        engine = DIAGRAMS[name][0]
        try:
            _, report = prepare_diagram_data(frame, engine)
            result[name] = (True, f'Inputs available for {report["n_available"]} of {len(frame)} samples.')
        except ValueError as error:
            result[name] = (False, str(error))
    return result


def prepare_python_diagram(frame, module_name):
    """Copy, filter and supply optional display fields for a Python plot call."""
    cleaned, report = prepare_diagram_data(frame, module_name)
    cleaned = cleaned.reset_index(drop=True)
    defaults = {'Sample': [f'Sample {i}' for i in report['used_row_positions_1based']],
                'Label': 'All samples', 'Color': '#0072b2', 'Marker': 'o', 'Size': 36, 'Alpha': .8}
    for column, default in defaults.items():
        if column not in cleaned:
            cleaned[column] = default
    cleaned['Sample'] = (cleaned['Sample'].replace(r'^\s*$', np.nan, regex=True)
                         .fillna(dict(enumerate(defaults['Sample']))).astype(str))
    cleaned.attrs['plot_input_filter'] = frame.attrs.get('plot_input_filter', report)
    return cleaned


def panel_mask(frame, columns):
    return np.isfinite(frame[list(columns)].to_numpy(dtype=float)).all(axis=1)


def annotate_input_coverage(figure, frame):
    """Keep partial-panel counts with the exported figure, as well as the UI."""
    report = frame.attrs.get('plot_input_filter', {})
    figure._aquaprov_input_filter = report
    groups = report.get('groups', {})
    if groups and any(group['n_available'] < report['n_input'] for group in groups.values()):
        text = 'Available measurements: ' + '; '.join(f'{name}: n = {group["n_available"]}'
                                                     for name, group in groups.items())
        figure._aquaprov_input_coverage = text
        panels = [axis for axis in figure.axes if axis.get_xlabel() and not hasattr(axis, '_colorbar')]
        if len(panels) == len(groups):
            for axis, group in zip(panels, groups.values()):
                axis.set_xlabel(axis.get_xlabel() + f'\nAvailable samples: n = {group["n_available"]}')
        else:
            # Axis labels participate in the axes layout, separately from the
            # shared figure legend. A figure supxlabel would occupy its margin.
            from textwrap import fill
            figure.axes[0].set_xlabel(fill(text, width=82), fontsize=8)
