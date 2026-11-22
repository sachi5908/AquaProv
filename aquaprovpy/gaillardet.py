# -*- coding: utf-8 -*-
"""Gaillardet diagrams for cation and bicarbonate ratios.

Created on Thu Sep 16 10:22:05 2021

@author: Jing
"""

import numpy as np
from ._diagram_colors import sample_legend, scatter_panels
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from .ions import ions_WEIGHT, ions_CHARGE
from ._diagram_colors import color_label, numeric_colors
from ._publication import close_on_error
from .core.diagram_inputs import prepare_python_diagram, panel_mask, annotate_input_coverage


def _field_ellipse(axis, centre, width, height, angle, limits, **style):
    """Add a published field outline that stays attached to the data axes.

    The fields were digitized as ellipses in the panel's axes fraction at the
    default limits. Converting them to log-data vertices keeps them at the same
    ratios when a user changes the axis limits or the figure is restyled.
    """
    t = np.linspace(0, 2 * np.pi, 241)
    theta = np.radians(angle)
    fx = centre[0] + width / 2 * np.cos(t) * np.cos(theta) - height / 2 * np.sin(t) * np.sin(theta)
    fy = centre[1] + width / 2 * np.cos(t) * np.sin(theta) + height / 2 * np.sin(t) * np.cos(theta)
    (x0, x1), (y0, y1) = np.log10(limits[0]), np.log10(limits[1])
    vertices = np.column_stack((10 ** (x0 + fx * (x1 - x0)), 10 ** (y0 + fy * (y1 - y0))))
    return axis.add_patch(mpatches.Polygon(vertices, closed=True, zorder=0.9, **style))


@close_on_error
def plot(df, unit='mg/L', figname='Gaillardet diagram', figformat='jpg'):
    """Plot and save the two Gaillardet ratio panels.

    Parameters
    ----------
    df : pandas.DataFrame
        Ca, Na and either Mg or HCO3 concentrations, one row per sample.
        Each ratio panel uses only its own available measurements.
    unit : str
        Ion concentrations in mg/L or meq/L.
    figname : str
        Output path without the file extension, or None for a live figure.
    figformat : str
        Output format, such as 'png', 'pdf' or 'svg'.

    References
    ----------
    .. [1] Gaillardet, J. et al. 1999.
           Global silicate weathering and CO2 consumption rates deduced
           from the chemistry of large rivers
           Chemical Geology 159, 3-30.
           https://doi.org/10.1016/S0009-2541(99)00031-5
    """
    df = prepare_python_diagram(df, 'gaillardet')
    if unit not in ('mg/L', 'meq/L'):
        raise ValueError('Concentration unit must be mg/L or meq/L.')
    bicarbonate_rows = panel_mask(df, ('Ca', 'Na', 'HCO3'))
    magnesium_rows = panel_mask(df, ('Ca', 'Na', 'Mg'))
    for rows, ions in ((bicarbonate_rows, ('Ca', 'Na', 'HCO3')), (magnesium_rows, ('Ca', 'Na', 'Mg'))):
        if (df.loc[rows, list(ions)].to_numpy(dtype=float) <= 0).any():
            raise ValueError('Gaillardet ratios require positive concentrations for logarithmic axes.')
    ions = ('Ca', 'Mg', 'Na', 'HCO3')
    divisor = [ions_WEIGHT[ion] if unit == 'mg/L' else abs(ions_CHARGE[ion]) for ion in ions]
    molL = df[list(ions)].to_numpy(dtype=float) / np.array(divisor)
    colors = numeric_colors(df)

    fig = plt.figure(figsize=(12, 10))

    # Plot the scatters
    ax1 = fig.add_subplot(221, aspect='equal')
    ax1.loglog()

    with np.errstate(divide='ignore', invalid='ignore'):
        ratios = molL / molL[:, 2, None]
    artists = scatter_panels(ax1, df, [(ratios[:, 0], ratios[:, 3])],
                             masks=[bicarbonate_rows], legend_panel=0)

    sample_legend(ax1, loc='lower right', markerscale=1, frameon=False, fontsize=12,
               labelspacing=0.25, handletextpad=0.25)

    # Show horizontal line at 100
    ax1.axhline(y=100, linestyle=':', linewidth=1, color='k')

    # Add a rectangle for Evaporites
    rect = mpatches.Rectangle([0.12, 0.15], 0.15, 0.20,
                              fc="w", ec='k', alpha=0.2, hatch='///', label='Evaporites')
    ax1.add_patch(rect)
    ax1.text(0.3, 0.2, 'Evaporites', fontsize=12)

    # Add an ellipse for Silicates
    limits1 = ((0.1, 100), (0.1, 250))
    _field_ellipse(ax1, (0.2, 0.35), 0.20, 0.13, 45, limits1,
                   fc="w", ec='k', alpha=0.2, hatch='\\\\\\')
    ax1.text(0.15, 4, 'Silicates', fontsize=12)

    # Add an ellipse for Carbonates
    _field_ellipse(ax1, (0.85, 0.90), 0.25, 0.1, 30, limits1,
                   fc="w", ec='k', alpha=0.2, hatch='++')
    ax1.text(3, 70, 'Carbonates', fontsize=12)

    # Axis labels and ticks.
    ax1.set_xlabel('Ca$^{2+}$/Na$^+$', fontsize=12, weight='normal')
    ax1.set_ylabel('HCO$_3^-$/Na$^+$', fontsize=12, weight='normal')

    ax1.minorticks_off()
    ax1.tick_params(which='major', direction='in', length=4, width=1.25)
    ax1.tick_params(which='minor', direction='in', length=2.5, width=1.25)

    labels = ax1.get_xticklabels() + ax1.get_yticklabels()
    [label.set_fontsize(10) for label in labels]

    ax1.spines['top'].set_linewidth(1.25)
    ax1.spines['top'].set_color('k')
    ax1.spines['bottom'].set_linewidth(1.25)
    ax1.spines['bottom'].set_color('k')
    ax1.spines['left'].set_linewidth(1.25)
    ax1.spines['left'].set_color('k')
    ax1.spines['right'].set_linewidth(1.25)
    ax1.spines['right'].set_color('k')

    ax1.set_xlim(0.1, 100)
    ax1.set_ylim(0.1, 250)

    ax2 = fig.add_subplot(222, aspect='equal')
    ax2.loglog()
    # Plot the scatters
    artists += scatter_panels(ax2, df, [(ratios[:, 0], ratios[:, 1])],
                              masks=[magnesium_rows], legend_panel=0)
    cf = artists[-1]

    if colors is not None:
        cb = plt.colorbar(cf, extend='both', spacing='uniform',
                          orientation='vertical', fraction=0.05, pad=0.125,
                          )
        cb.ax.tick_params(labelsize=10)
        cb.ax.set_ylabel(color_label(df), rotation=90, labelpad=-65, fontsize=12)

    # Show horizontal line at 10
    ax2.axhline(y=10, linestyle=':', linewidth=1, color='k')

    # Add a rectangle for Evaporites
    rect = mpatches.Rectangle([0.12, 0.015], 0.15, 0.020,
                              fc="w", ec='k', alpha=0.2, hatch='///')
    ax2.add_patch(rect)
    ax2.text(0.3, 0.02, 'Evaporites', fontsize=12)

    # Add an ellipse for Silicates
    limits2 = ((0.1, 100), (0.01, 25))
    _field_ellipse(ax2, (0.20, 0.40), 0.20, 0.13, 45, limits2,
                   fc="w", ec='k', alpha=0.2, hatch='\\\\\\')
    ax2.text(0.15, 0.6, 'Silicates', fontsize=12)

    # Add an ellipse for Carbonates
    _field_ellipse(ax2, (0.87, 0.90), 0.20, 0.17, 45, limits2,
                   fc="w", ec='k', alpha=0.2, hatch='++')
    ax2.text(4, 7, 'Carbonates', fontsize=12)

    # Axis labels and ticks.
    ax2.set_xlabel('Ca$^{2+}$/Na$^+$', fontsize=12, weight='normal')
    ax2.set_ylabel('Mg$^{2+}$/Na$^+$', fontsize=12, weight='normal')

    labels = ax2.get_xticklabels() + ax2.get_yticklabels()
    [label.set_fontsize(10) for label in labels]

    ax2.set_xlim(0.1, 100)
    ax2.set_ylim(0.01, 25)

    ax2.minorticks_on()
    ax2.tick_params(which='major', direction='in', length=4, width=1.25)
    ax2.tick_params(which='minor', direction='in', length=2.5, width=1.25)

    ax2.spines['top'].set_linewidth(1.25)
    ax2.spines['top'].set_color('k')
    ax2.spines['bottom'].set_linewidth(1.25)
    ax2.spines['bottom'].set_color('k')
    ax2.spines['left'].set_linewidth(1.25)
    ax2.spines['left'].set_color('k')
    ax2.spines['right'].set_linewidth(1.25)
    ax2.spines['right'].set_color('k')

    plt.subplots_adjust(wspace=0.001)

    for axis, rows, needed in ((ax1, bicarbonate_rows, 'Ca, Na and HCO3'), (ax2, magnesium_rows, 'Ca, Na and Mg')):
        if not rows.any():
            axis.text(.5, .5, 'No complete samples\nNeeds ' + needed,
                      transform=axis.transAxes, ha='center', va='center',
                      bbox=dict(facecolor='white', alpha=.9, edgecolor='none'))
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
    df.loc[df['Label']=='C1', 'Marker'] = 'o'
    df.loc[df['Label']=='C2', 'Marker'] = 's'
    df.loc[df['Label']=='C3', 'Marker'] = '^'
    plot(df, unit='mg/L', figname='Gaillardet diagram', figformat='jpg')
