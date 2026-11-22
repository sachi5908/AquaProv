# -*- coding: utf-8 -*-
"""Schoeller diagrams for comparing major-ion concentrations.

Created on Thu Sep 16 13:11:29 2021

@author: Jing
"""

import numpy as np
from .core.progress import report_progress
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

from .ions import ions_WEIGHT, ions_CHARGE
from ._diagram_colors import sample_legend, color_label, numeric_colors, sample_batches, scatter_panels
from ._publication import close_on_error
from .core.diagram_inputs import prepare_python_diagram, annotate_input_coverage


@close_on_error
def plot(df, unit='mg/L', figname='Schoeller diagram', figformat='jpg'):
    """Plot and save a Schoeller diagram.

    Parameters
    ----------
    df : pandas.DataFrame
        Available Ca, Mg, Na, K, Cl, SO4 and HCO3 concentrations, one row per
        sample. Missing measurements and zeros leave gaps on the log axis.
    unit : str
        Ion concentrations in mg/L or meq/L.
    figname : str
        Output path without the file extension, or None for a live figure.
    figformat : str
        Output format, such as 'png', 'pdf' or 'svg'.

    References
    ----------
    .. [1] Güler, et al. 2002.
           Evaluation of graphical and multivariate statistical methods for classification of water chemistry data
           Hydrogeology Journal 10(4):455-474
           https://doi.org/10.1007/s10040-002-0196-6
    """
    df = prepare_python_diagram(df, 'schoeller')
    if unit not in ('mg/L', 'meq/L'):
        raise ValueError('Concentration unit must be mg/L or meq/L.')
    ions = ('Ca', 'Mg', 'Na', 'K', 'Cl', 'SO4', 'HCO3')
    meqL = df[list(ions)].to_numpy(dtype=float)
    if (meqL < 0).any():
        raise ValueError('Ion concentrations must be nonnegative.')
    if unit == 'mg/L':
        meqL = meqL * np.array([abs(ions_CHARGE[ion]) / ions_WEIGHT[ion] for ion in ions])
    # A gap prevents a line from implying an unmeasured concentration. Zero is
    # also unplottable on a log axis; preserve it in the source table.
    meqL = np.where(meqL > 0, meqL, np.nan)

    # A logarithmic axis needs finite, strictly positive limits, even when
    # individual measured concentrations are zero.
    positive_meq = meqL[np.isfinite(meqL) & (meqL > 0)]
    if positive_meq.size == 0:
        raise ValueError('Schoeller diagram requires at least one positive, finite ion concentration.')

    colors = numeric_colors(df)

    fig = plt.figure(figsize=(6, 3))
    ax = fig.add_subplot(111)
    ax.semilogy()
    # Set valid limits before adding samples so an all-zero first sample does
    # not trigger logarithmic autoscaling warnings in numeric-color mode.
    ax.set_ylim([np.min(positive_meq) * 0.5, np.max(positive_meq) * 1.5])

    # Each path retains all seven positions, including NaN gaps. Batching
    # paths avoids thousands of artists without connecting different samples.
    segments = np.stack((np.broadcast_to(np.arange(1, 8), meqL.shape), meqL), axis=2)
    for start, stop, _, _ in sample_batches(df):
        curve = LineCollection(segments[start:stop], alpha=df['Alpha'].to_numpy()[start:stop])
        curve._aquaprov_sample_positions = np.arange(start, stop)
        if colors is not None:
            curve.set_array(colors['values'][start:stop])
            curve.set_cmap(colors['cmap'])
            curve.set_norm(colors['norm'])
        else:
            curve.set_color(df['Color'].to_numpy()[start:stop])
        ax.add_collection(curve)
        report_progress(10 + 30 * stop / len(df), 'Drawing concentration profiles')
    marker_frame = df.copy()
    # Schoeller historically uses the line-marker size, independent of Size.
    marker_frame['Size'] = plt.rcParams['lines.markersize'] ** 2
    scatter_panels(ax, marker_frame,
        [(np.full(len(df), i + 1), meqL[:, i]) for i in range(7)],
        legend_panel=None if colors is not None else -1, edgecolors='face')
    # Explicit handles keep a group legend even when its first ion is missing.
    from matplotlib.lines import Line2D
    handles, seen = [], set()
    for i, label in enumerate(df['Label'].fillna('').astype(str) if colors is None else []):
        label = label or 'Samples'
        if label in seen:
            continue
        seen.add(label)
        color = df['Color'].iloc[i] if colors is None else colors['cmap'](colors['norm'](colors['values'][i]))
        handles.append(Line2D([], [], color=color, marker=df['Marker'].iloc[i],
            alpha=float(df['Alpha'].iloc[i]), label=label,
            linestyle='-' if colors is None else 'None'))

    if colors is not None:
        fig.colorbar(curve, ax=ax, label=color_label(df))

    # Background settings
    ax.set_xticks([1, 2, 3, 4, 5, 6, 7])
    ax.set_xticklabels(['Ca$^{2+}$', 'Mg$^{2+}$', 'Na$^+$', 'K$^+$',
                        'Cl$^-$', 'SO$_4^{2-}$', 'HCO$_3^-$'])
    ax.set_ylabel('meq/L', fontsize=12, weight='normal')

    # Set the limits
    ax.set_xlim([1, 7])

    # Plot the vertical lines
    for xtick in [1, 2, 3, 4, 5, 6, 7]:
        plt.axvline(xtick, linewidth=1, color='grey', linestyle='dashed')

    sample_legend(ax, **({'handles': handles} if colors is None else {}),
              loc='best', markerscale=1, frameon=False, fontsize=10,
              labelspacing=0.25, handletextpad=0.25)

    annotate_input_coverage(fig, df)
    if figname is not None:
        plt.savefig(figname + '.' + figformat, format=figformat,
                    bbox_inches='tight', dpi=plt.rcParams['savefig.dpi'])

    return

if __name__ == '__main__':
    # Example data
    data = {'Sample' : ['sample1', 'sample2', 'sample3', 'sample4', 'sample5', 'sample6'],
            'Label'  : ['C1', 'C2', 'C2', 'C3', 'C3', 'C1'],
            'Color'  : ['red', 'green', 'green', 'blue', 'blue', 'red'],
            'Marker' : ['o', 'o', 'o', 'o', 'o', 'o'],
            'Size'   : [30, 30, 30, 30, 30, 30],
            'Alpha'  : [0.6, 0.6, 0.6, 0.6, 0.6, 0.6],
            'pH'     : [7.8, 7.6, 7.5, 7.7, 7.4, 7.1],
            'Ca'     : [32, 46, 54, 50, 50, 134],
            'Mg'     : [6, 11, 11, 11, 22, 21],
            'Na'     : [28, 17, 16, 25, 25, 39],
            'K'      : [2.8, 0.7, 2.4, 2.8, 0.5, 6.4],
            'HCO3'   : [73, 201, 207, 244, 305, 275],
            'CO3'    : [0, 0, 0, 0, 0, 0],
            'Cl'     : [43, 14, 18, 18, 11, 96],
            'SO4'    : [48, 9, 10, 9, 9, 100],
            'TDS'    : [233, 299, 377, 360, 424, 673],
            }
    df = pd.DataFrame(data)
    plot(df, unit='mg/L', figname='Scholler diagram', figformat='jpg')
