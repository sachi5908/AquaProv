"""Shared input validation, plot styling and numerical result exports."""

from dataclasses import dataclass, field
from pathlib import Path
from functools import wraps
import platform

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
from . import __version__
from .colour_scales import register_colour_scales

register_colour_scales()


PALETTE = ('#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00', '#56B4E9', '#333333')
GROUP_MARKERS = ('o', 's', '^', 'D', 'v', 'P', 'X', '*')
STYLE = {
    'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.titlesize': 13,
    'axes.titleweight': 'semibold', 'axes.labelsize': 11,
    'axes.labelweight': 'normal', 'axes.edgecolor': '#526479',
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.facecolor': 'white', 'figure.facecolor': 'white',
    'xtick.labelsize': 9, 'ytick.labelsize': 9, 'legend.fontsize': 9,
    'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',
    'savefig.dpi': 300, 'axes.prop_cycle': mpl.cycler(color=PALETTE),
}


@dataclass
class PlotResult:
    """Figure, unrounded result tables and settings. The caller closes the figure."""
    figure: object
    tables: dict
    metadata: dict
    warnings: list = field(default_factory=list)

    def __post_init__(self):
        # Table-only results (for example exported analyses) have no figure.
        if self.figure is not None:
            from .plot_legends import prepare_figure_legends
            prepare_figure_legends(self.figure)

    def methods_record(self):
        """The same analysis provenance accompanies every results format."""
        return dict(self.metadata, warnings=self.warnings, versions={
            'aquaprov': __version__,
            'python': platform.python_version(), 'numpy': np.__version__,
            'pandas': pd.__version__, 'scipy': scipy.__version__,
            'matplotlib': mpl.__version__,
        })

    def export(self, directory, stem='analysis', *, format='csv', title='AquaProv analysis'):
        """Export all tables, methods and warnings; CSV/JSON remains the default."""
        from .core.results_export import export_results
        return export_results(self, directory, stem, format=format, title=title)


def finish(fig, tables, metadata, warnings, figname, figformat, dpi):
    result = PlotResult(fig, tables, metadata, warnings)
    if figname is not None:
        try:
            path = Path(str(figname) + '.' + figformat).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(path, format=figformat, dpi=dpi, bbox_inches='tight')
        except Exception:
            plt.close(fig)
            raise
    return result


def close_on_error(function):
    """Clean only figures created by a failed plot; leave callers' figures alone."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        before = set(plt.get_fignums())
        try:
            return function(*args, **kwargs)
        except Exception:
            for number in set(plt.get_fignums()) - before:
                plt.close(number)
            raise
    return wrapped


def isolated_style(function):
    """Keep a legacy diagram's Matplotlib style changes local to its own call.

    Several historical diagram functions reset the style and set rcParams
    while drawing. Without this guard those settings leak into every later
    figure created by a Python caller.
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        with plt.rc_context():
            return function(*args, **kwargs)
    return wrapped


def numeric_frame(df, columns, missing='raise', min_rows=2, constants='raise', min_columns=2):
    """Validate selected variables and record any requested complete-case filtering."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        raise ValueError('Provide a non-empty pandas DataFrame.')
    if not df.columns.is_unique:
        raise ValueError('Column names must be unique.')
    if isinstance(columns, str) or columns is None:
        raise ValueError('Select an explicit list of measurement columns.')
    columns = list(columns)
    if len(columns) < min_columns or len(set(columns)) != len(columns):
        raise ValueError(f'Select at least {min_columns} distinct measurement column(s).')
    absent = [c for c in columns if c not in df]
    if absent:
        raise ValueError('Missing columns: ' + ', '.join(map(str, absent)))
    if missing not in ('raise', 'drop'):
        raise ValueError("missing must be 'raise' or 'drop' (complete cases).")
    if constants not in ('raise', 'drop', 'keep'):
        raise ValueError("constants must be 'raise', 'drop' or 'keep'.")
    raw = df[columns].replace(r'^\s*$', np.nan, regex=True)
    data = raw.apply(pd.to_numeric, errors='coerce').astype(float)
    invalid = (data.isna() & raw.notna()) | np.isinf(data)
    if invalid.any().any():
        bad = [str(c) for c in columns if invalid[c].any()]
        raise ValueError('Non-numeric or infinite measurements in: ' + ', '.join(bad) +
                         '. Resolve text/nondetect qualifiers explicitly; they are not zeros.')
    keep = ~data.isna().any(axis=1)
    excluded = np.flatnonzero(~keep.to_numpy()).tolist()
    warnings = []
    if excluded and missing == 'raise':
        raise ValueError('Missing measurements in data row(s): ' +
                         ', '.join(str(i + 1) for i in excluded[:12]) +
                         '. Correct them or explicitly choose complete-case deletion.')
    if excluded:
        warnings.append(f'Excluded {len(excluded)} rows by complete-case deletion.')
    positions = np.flatnonzero(keep.to_numpy())
    data = data.iloc[positions].copy()
    if len(data) < min_rows:
        raise ValueError(f'At least {min_rows} complete samples are required.')
    constant = [c for c in data if data[c].nunique() <= 1]
    if constant and constants == 'raise':
        raise ValueError('Constant variables have undefined correlations: ' + ', '.join(map(str, constant)))
    if constant and constants == 'drop':
        data = data.drop(columns=constant)
        warnings.append('Excluded constant variables: ' + ', '.join(map(str, constant)))
    if len(data.columns) < min_columns:
        raise ValueError(f'At least {min_columns} varying measurement column(s) are required.')
    metadata = {'selected_columns': columns, 'used_columns': list(data.columns),
                'n_input': len(df), 'n_used': len(data), 'missing': missing,
                'excluded_row_positions_1based': [i + 1 for i in excluded],
                'constant_policy': constants, 'excluded_constant_columns': constant if constants == 'drop' else []}
    return data, positions, metadata, warnings


def standardize(data, enabled=True):
    mean = data.mean()
    scale = data.std(ddof=1) if enabled else pd.Series(1.0, index=data.columns)
    values = (data - mean) / scale
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError('Scaling produced non-finite values; check measurement magnitudes.')
    return values, pd.DataFrame({'mean': mean, 'scale_sample_sd': scale})


def sample_labels(df):
    return df['Sample'].astype(str).tolist() if 'Sample' in df else [str(i) for i in df.index]


def add_origin_lines(ax, coordinates, *, colors=None, values=None, cmap=None, norm=None):
    """Connect 3D observations to (0, 0, 0), including the origin in the view."""
    from mpl_toolkits.mplot3d.art3d import Line3DCollection

    points = np.asarray(coordinates, dtype=float)
    lines = Line3DCollection(np.stack((np.zeros_like(points), points), axis=1),
                             colors=colors, linewidths=.8, alpha=.65, label='_nolegend_')
    lines.set_gid('aquaprov-origin-lines')
    from .plot_legends import add_legend_entries
    from matplotlib.lines import Line2D
    add_legend_entries(ax, [Line2D([], [], color='#66788a', linewidth=.8, alpha=.65, label='Origin guides')])
    if values is not None:
        lines.set_array(np.asarray(values))
        lines.set_cmap(cmap)
        lines.set_norm(norm)
    ax.add_collection(lines, autolim=False)
    # Extend the view, never translate or normalize the observed coordinates.
    points_with_origin = np.vstack((points, np.zeros(3)))
    ax.auto_scale_xyz(*points_with_origin.T, had_data=True)
    return lines


def scatter_samples(ax, df, coordinates, *, show_origin_lines=False):
    """Honor optional legacy styling; use categorical colors when Color is absent."""
    from ._diagram_colors import scatter_panels, numeric_colors, sample_legend
    labels = df['Label'].fillna('Unlabelled').astype(str) if 'Label' in df else pd.Series(['Samples'] * len(df))
    groups = list(dict.fromkeys(labels))
    styles = pd.DataFrame(index=df.index)
    styles['Label'] = labels.to_numpy()
    group_colors = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(groups)}
    group_markers = {g: GROUP_MARKERS[(i // len(PALETTE)) % len(GROUP_MARKERS)] for i, g in enumerate(groups)}
    styles['Color'] = df['Color'] if 'Color' in df else labels.map(group_colors).to_numpy()
    styles['Marker'] = df['Marker'] if 'Marker' in df else labels.map(group_markers).to_numpy()
    styles['Size'] = df['Size'] if 'Size' in df else 45.
    styles['Alpha'] = df['Alpha'] if 'Alpha' in df else .85
    mapping = numeric_colors(styles)
    sample_artists = scatter_panels(ax, styles, [coordinates], legend_panel=0,
        linewidths=.5, edgecolors='#243447', zorder=4, color_mapping=mapping,
        **({'depthshade': False} if len(coordinates) == 3 else {}))
    if show_origin_lines and len(coordinates) == 3:
        add_origin_lines(ax, np.asarray(coordinates).T, **(
            dict(values=mapping['values'], cmap=mapping['cmap'], norm=mapping['norm'])
            if mapping is not None else dict(colors=styles['Color'].to_numpy())))
    if mapping is not None:
        ax.figure.colorbar(sample_artists[0], ax=ax,
                           shrink=0.7, pad=0.04, label=df.attrs.get('color_label', 'Color value'))
    else:
        sample_legend(ax, loc='upper left', bbox_to_anchor=(1.01, 1), frameon=False,
                  ncol=max(1, (len(groups) + 19) // 20))
