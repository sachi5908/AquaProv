# -*- coding: utf-8 -*-
"""Durov diagrams with pH and total dissolved solids.

Created on Wed Sep 30 20:51:33 2020

@author: Jing
"""

import math
import numpy as np
from ._diagram_colors import sample_legend, scatter_panels
import pandas as pd
import matplotlib.pyplot as plt

from ._chemistry import major_ion_meq
from ._diagram_colors import color_label, numeric_colors
from ._publication import close_on_error, isolated_style
from .core.diagram_inputs import prepare_python_diagram, annotate_input_coverage


def _tds_step(tds):
    """Tick step for the 8-interval TDS panel: 500 mg/L, or larger if needed."""
    finite = tds[np.isfinite(tds)]
    largest = float(finite.max()) if finite.size else 0.
    if largest <= 4000:
        return 500.
    raw = largest / 8
    magnitude = 10 ** math.floor(math.log10(raw))
    return next(f * magnitude for f in (1, 2, 2.5, 5, 10) if f * magnitude >= raw)


@close_on_error
@isolated_style
def plot(df, unit='mg/L', figname='Durov diagram', figformat='jpg'):
    """Plot and save a Durov diagram.

    Parameters
    ----------
    df : pandas.DataFrame
        Major-ion chemistry, with one row per sample. pH and TDS are optional;
        missing values omit only the corresponding extension-panel points.
    unit : str
        Ion concentrations in mg/L or meq/L. TDS is always in mg/L.
        pH is dimensionless.
    figname : str
        Output path without the file extension, or None for a live figure.
    figformat : str
        Output format, such as 'png', 'pdf' or 'svg'.

    References
    ----------
    .. [1] Durov, S.A. 1948.
           Natural waters and graphic representation of their composition.
           Doklady Akademii Nauk SSSR 59, 87-90.
    """
    df = prepare_python_diagram(df, 'durvo')
    if (df['TDS'].dropna() < 0).any():
        raise ValueError('TDS must be nonnegative.')

    meqL = np.column_stack((major_ion_meq(df, unit),
                           df['pH'].to_numpy(dtype=float), df['TDS'].to_numpy(dtype=float) / 1000.))

    has_ph = df['pH'].notna().any()
    has_tds = df['TDS'].notna().any()

    colors = numeric_colors(df)

    # Triangle vertices.
    h = 0.5 * np.tan(np.pi / 3.0)
    ltriangle_x = np.array([0, -h, 0, 0])
    ltriangle_y = np.array([0, 0.5, 1, 0])
    ttriangle_x = np.array([0, 0.5, 1, 0])
    ttriangle_y = np.array([1, 1 + h, 1, 1])

    # Rectangle vertices.
    crectangle_x = np.array([0, 0, 1, 1, 0])
    crectangle_y = np.array([0, 1, 1, 0, 0])
    rrectangle_x = np.array([1, 2.618, 2.618, 1, 1])
    rrectangle_y = np.array([0, 0, 1, 1, 0])
    brectangle_x = np.array([0, 1, 1, 0, 0])
    brectangle_y = np.array([0, 0, -0.618, -0.618, 0])

    # Draw the triangles and rectangles.
    fig = plt.figure(figsize=(10,10), dpi=100)
    ax = fig.add_subplot(111, aspect='equal',
                         frameon=False, xticks=[], yticks=[])
    ax.plot(ltriangle_x, ltriangle_y, '-k', lw=1.0)
    ax.plot(ttriangle_x, ttriangle_y, '-k', lw=1.0)
    ax.plot(rrectangle_x, rrectangle_y, '-k', lw=1.0)
    ax.plot(brectangle_x, brectangle_y, '-k', lw=1.0)

    # Ticks at 10% intervals, each 0.025 units long.
    linterval = 0.1
    ticklabels = ['0', '10', '20', '30', '40', '50',
                  '60', '70', '80', '90', '100']
    ticklength = 0.02
    # Left triangle.
    for i, x in enumerate(np.linspace(-h, 0, int(1 / linterval + 1))):
        ax.plot([x, x + ticklength * np.sin(np.pi / 3.0)],
                [-x * np.tan(np.pi / 6.0), -x * np.tan(np.pi / 6.0) + ticklength * np.sin(np.pi / 6.0)],
                'k', lw=1.0)
        if i in [2, 4, 6, 8]:
            ax.plot([x, 0], [-x * np.tan(np.pi / 6.0), -x / np.sin(np.pi / 3.0)], 'k:')
            ax.text(x - ticklength * np.sin(np.pi / 3.0), -x * np.tan(np.pi / 6.0) - 4 * ticklength * np.sin(np.pi / 6.0),
                    ticklabels[i], rotation=-30, ha='center', va='center')
    ax.text(-h / 2 - .10, .25 - .16, r'$Na^+ + K^+$ (%)',
            ha='center', va='center', rotation=-30, fontsize=11)
    ax.text(-h - 0.15, 0.5, '  100% Mg' + '$^{2+}$', rotation=90,
            ha='center', va='center', fontsize=12)

    for i, x in enumerate(np.linspace(-h, 0, int(1 / linterval + 1))):
        ax.plot([x, x + ticklength * np.sin(np.pi / 3.0)],
                [0.5 + (h + x) * np.tan(np.pi / 6.0), 0.5 + (h + x) * np.tan(np.pi / 6.0) - ticklength * np.sin(np.pi / 6.0)],
                'k', lw=1.0)
        if i in [2, 4, 6, 8]:
            ax.plot([x, 0], [0.5 + (h + x) * np.tan(np.pi / 6.0), 1 + x / np.sin(np.pi / 3.0)], 'k:')
            ax.text(x - ticklength * np.sin(np.pi / 3.0), 0.5 + (h + x) * np.tan(np.pi / 6.0) +  4 * ticklength * np.sin(np.pi / 6.0),
                    ticklabels[i], rotation=30, ha='center', va='center')
    ax.text(-h / 2 - .10, .75 + .16, r'$Ca^{2+}$ (%)',
            ha='center', va='center', rotation=30, fontsize=11)
    # Top triangle.
    for i, x in enumerate(np.linspace(0, 0.5, int(1 / linterval + 1))):
        ax.plot([x, x + ticklength * np.sin(np.pi / 6.0)],
                [1 + x * np.tan(np.pi / 3.0), 1 + x * np.tan(np.pi / 3.0) - ticklength * np.sin(np.pi / 6.0)],
                'k', lw=1.0)
        if i in [2, 4, 6, 8]:
            ax.plot([x, x / np.sin(np.pi / 6.0)], [1 + x * np.tan(np.pi / 3.0), 1], 'k:')
            ax.text(x - 4 * ticklength * np.sin(np.pi / 6.0), 1 + x * np.tan(np.pi / 3.0) + ticklength * np.sin(np.pi / 6.0),
                    ticklabels[-i - 1], rotation=60, ha='center', va='center')
    ax.text(.25 - .16, 1 + h / 2 + .10, r'$Cl^-$ (%)',
            ha='center', va='center', rotation=60, fontsize=11)
    for i, x in enumerate(np.linspace(0.5, 1, int(1 / linterval + 1))):
        ax.plot([x, x - ticklength * np.sin(np.pi / 6.0)],
                [1 + (1 - x) * np.tan(np.pi / 3.0), 1 + (1 - x) * np.tan(np.pi / 3.0) - ticklength * np.sin(np.pi / 3.0)],
                'k', lw=1.0)
        if i in [2, 4, 6, 8]:
            ax.plot([x, (x - 0.5) / np.sin(np.pi / 6.0)], [1 + (1 - x) * np.tan(np.pi / 3.0), 1], 'k:')
            ax.text(x +  4 * ticklength * np.sin(np.pi / 6.0), 1 + (1 - x) * np.tan(np.pi / 3.0) + ticklength * np.sin(np.pi / 3.0),
                    ticklabels[i], rotation=-60, ha='center', va='center')
    ax.text(.75 + .16, 1 + h / 2 + .10, r'$HCO_3^- + CO_3^{2-}$ (%)',
            ha='center', va='center', rotation=-60, fontsize=11)
    ax.text(0.5, h + 1.23, '  100% SO' + '$_4^{2-}$', rotation=0,
            ha='center', va='center', fontsize=12)
    # Center rectangle
    for x in np.linspace(0, 1, int(1 / linterval + 1)):
        ax.plot([x, x],
                [1, 1 - ticklength],
                'k', lw=1.0)
    for x in np.linspace(0, 1, int(1 / linterval + 1)):
        ax.plot([0, ticklength],
                [x, x],
                'k', lw=1.0)

    # Right rectangle
    # The historical 0-4000 mg/L scale is kept unless a sample exceeds it;
    # the scale then extends so every TDS point stays inside its panel.
    tds_step = _tds_step(df['TDS'].to_numpy(dtype=float))
    tds_max = 8 * tds_step
    for i, x in enumerate(np.linspace(1, 2.618, 9)):
        ax.plot([x, x],
                [0, ticklength],
                'k', lw=1.0)
        if i % 2:
            ax.text(x, -2 * ticklength, f'{i * tds_step:g}', ha='center', va='top')
    ax.text(1 + 1.618 / 2, -0.12, 'TDS (mg/L)', ha='center', va='top', fontsize=12)

    # Water types in the central rectangle.
    ax.text(0.15, 0.1, 'NaCl', ha='center', va='center', fontsize=12)
    ax.text(0.8, 0.9, 'CaHCO$_3$', ha='center', va='center', fontsize=12)

    # Normalize cations and anions separately.
    sumcat = np.sum(meqL[:, 0:4], axis=1)
    suman = np.sum(meqL[:, 4:8], axis=1)
    cat = np.zeros((len(meqL), 3))
    an = np.zeros((len(meqL), 3))
    cat[:, 0] = meqL[:, 0] / sumcat                     # Percentage Ca
    cat[:, 1] = meqL[:, 1] / sumcat                     # Percentage Mg
    cat[:, 2] = (meqL[:, 2] + meqL[:, 3]) / sumcat      # Percentage Na+K
    an[:, 0] = (meqL[:, 4] + meqL[:, 5]) / suman        # Percentage HCO3 + CO3
    an[:, 2] = meqL[:, 6] / suman                       # Percentage Cl
    an[:, 1] = meqL[:, 7] / suman                       # Percentage SO4

    # Convert ion fractions to plot coordinates.
    minpH = math.floor(np.nanmin(meqL[:, 8])) if has_ph else 0
    maxpH = math.ceil(np.nanmax(meqL[:, 8])) if has_ph else 1
    if maxpH == minpH:
        minpH, maxpH = minpH - .5, maxpH + .5

    cat_x = -np.sin(np.pi / 3.0) * (1 -  cat[:, 2] - cat[:, 0])
    cat_y = np.sin(np.pi / 6.0) * (1 -  cat[:, 2] - cat[:, 0]) + cat[:, 0]
    an_x = np.sin(np.pi / 6.0) * (1 - an[:, 2]) + np.sin(np.pi / 6.0) * an[:, 0]
    an_y = 1 + np.sin(np.pi / 3.0) * (1 - an[:, 2] - an[:, 0])
    tds_x = 1 + meqL[:, 9] * 1000 / tds_max * 1.618
    ph_y = -(meqL[:, 8] - minpH) / (maxpH - minpH) * 0.618

    # Plot the scatters
    artists = scatter_panels(ax, df, [(cat_x, cat_y), (an_x, an_y),
        (an_x, cat_y), (an_x, ph_y), (tds_x, cat_y)], legend_panel=2)
    scatter = artists[0]

    if has_ph:
        # Match the bottom panel's ticks to its pH range.
        # Ticks sit exactly at the labelled pH values.
        span = maxpH - minpH
        step = .25 if span <= 2 else .5 if span <= 4 else 1. if span <= 8 else 2.
        values = np.arange(minpH, maxpH + step / 2, step)
        for value in values:
            x = -(value - minpH) / span * 0.618
            ax.plot([0, ticklength],
                    [x, x],
                    'k', lw=1.0)
            if minpH < value < maxpH:
                ax.text(-2 * ticklength, x, f'{value:g}',
                        ha='right', va='center')
        plt.text(-0.38, -0.618 / 2, 'pH', rotation=90,
                 ha='center', va='center', fontsize=12)

    else:
        ax.text(.5, -.3, 'pH unavailable', ha='center', va='center')
    if not has_tds:
        ax.text(1.8, .5, 'TDS unavailable', ha='center', va='center')

    sample_legend(plt.gca(), loc='upper left', markerscale=1, frameon=False, fontsize=12,
               labelspacing=0.25, handletextpad=0.25)

    if colors is not None:
        fig.colorbar(scatter, ax=ax, label=color_label(df), fraction=0.035, pad=0.06)

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
            'pH'     : [7.8, 7.6, 7.5, 7.7, 7.4, 4.8],
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
    plot(df, unit='mg/L', figname='Durov diagram', figformat='jpg')
