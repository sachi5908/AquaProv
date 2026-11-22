# -*- coding: utf-8 -*-
"""Chadha diagrams for major-ion chemistry.

Created on Thu Sep 16 11:36:50 2021

@author: Jing
"""

import numpy as np
from ._diagram_colors import sample_legend, scatter_panels
import pandas as pd
import matplotlib.pyplot as plt

from ._diagram_colors import color_label
from ._chemistry import major_ion_meq
from ._publication import close_on_error, isolated_style
from .core.diagram_inputs import prepare_python_diagram


@close_on_error
@isolated_style
def plot(df, unit='mg/L', figname='Chadha diagram', figformat='jpg'):
    """Plot and save a Chadha diagram.

    Parameters
    ----------
    df : pandas.DataFrame
        Major-ion chemistry, with one row per sample.
    unit : str
        Ion concentrations in mg/L or meq/L.
    figname : str
        Output path without the file extension, or None for a live figure.
    figformat : str
        Output format, such as 'png', 'pdf' or 'svg'.

    References
    ----------
    .. [1] Chadha, D. K. 1999.
           A proposed new diagram for geochemical classification of natural waters and interpretation of chemical data
           Hydrogeology Journal 7:431–439
           https://doi.org/10.1007/s100400050216
    """
    if not {'Ca', 'Mg', 'Na', 'K', 'HCO3', 'CO3', 'Cl', 'SO4'}.issubset(df.columns):
        raise ValueError("""
        Chadha diagram uses geochemical parameters Ca, Mg, Na, K, HCO3, CO3, Cl, and SO4.
        Confirm that these parameters are provided in the input file.""")

    df = prepare_python_diagram(df, 'chadha')
    ALLOWED_UNITS = ['mg/L', 'meq/L']
    if unit not in ALLOWED_UNITS:
        raise ValueError("""
        The unit used in df. Currently only mg/L and meq/L are supported. 
        Convert the unit manually if needed.""")

    meqL = major_ion_meq(df, unit)

    plt.style.use('default')
    plt.rcParams['font.size'] = 10
    plt.rcParams['axes.labelsize'] = 10
    plt.rcParams['axes.labelweight'] = 'bold'
    plt.rcParams['axes.titlesize'] = 10
    plt.rcParams['xtick.labelsize'] = 10
    plt.rcParams['ytick.labelsize'] = 10
    plt.rcParams['legend.fontsize'] = 10
    plt.rcParams['figure.titlesize'] = 10

    # Plot background
    xmin = -100
    xmax = +100
    ymin = -100
    ymax = +100

    plt.figure(figsize=(8, 8))
    ax = plt.subplot(111, aspect='equal')

    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['top'].set_visible(False)
    ax.xaxis.set_ticks_position('bottom')
    ax.yaxis.set_ticks_position('left')
    ax.spines['left'].set_position(('data', 0))
    ax.spines['bottom'].set_position(('data', 0))

    # Plot the domain
    plt.plot([xmin, xmax, xmax, xmin, xmin], [ymin, ymin, ymax, ymax, ymin],
             linestyle='-', linewidth=1.5, color='k')

    plt.xticks([-80, -60, -40, -20, 20, 40, 60, 80],
               ['-80', '-60', '-40', '-20', '+20', '+40', '+60', '+80'])
    plt.yticks([-80, -60, -40, -20, 20, 40, 60, 80],
               ['-80', '-60', '-40', '-20', '+20', '+40', '+60', '+80'])

    # The axis lines in the center
    ax.plot([xmin, xmax], [0, 0], linestyle='-', linewidth=1.0, color='k')
    ax.plot([0, 0], [ymin, ymax], linestyle='-', linewidth=1.0, color='k')

    # Labels
    # Real axis labels participate in resizing and the shared label controls.
    ax.set_xlabel('(Ca + Mg) − (Na + K) (% meq)')
    ax.set_ylabel('(HCO3 + CO3) − (Cl + SO4) (% meq)')
    ax.xaxis.set_label_coords(.5, -.10)
    ax.yaxis.set_label_coords(-.12, .5)

    # Label the eight hydrochemical fields.
    # Center fields 1-4 on the axes.
    for x, y, label in [(50, 0, '1'), (-50, 0, '2'),
                        (0, 50, '3'), (0, -50, '4')]:
        ax.text(x, y, label, fontsize=26, color="0.6",
                ha='center', va='center')
    plt.text(50, 50, '5', fontsize=26, color="0.6",
             ha='center', va='center')
    plt.text(50, -50, '6', fontsize=26, color="0.6",
             ha='center', va='center')
    plt.text(-50, -50, '7', fontsize=26, color="0.6",
             ha='center', va='center')
    plt.text(-50, 50, '8', fontsize=26, color="0.6",
             ha='center', va='center')

    # Normalize cations and anions separately.
    sumcat = np.sum(meqL[:, 0:4], axis=1)
    suman = np.sum(meqL[:, 4:], axis=1)
    cat = np.zeros((len(meqL), 3))
    an = np.zeros((len(meqL), 3))
    cat[:, 0] = meqL[:, 0] / sumcat                  # Ca
    cat[:, 1] = meqL[:, 1] / sumcat                  # Mg
    cat[:, 2] = (meqL[:, 2] + meqL[:, 3]) / sumcat   # Na+K
    an[:, 0] = (meqL[:, 4] + meqL[:, 5]) / suman     # HCO3 + CO3
    an[:, 2] = meqL[:, 6] / suman                    # Cl
    an[:, 1] = meqL[:, 7] / suman                    # SO4

    # Plot the scatter
    artists = scatter_panels(ax, df, [(100 * (cat[:, 0] + cat[:, 1] - cat[:, 2]),
        100 * (an[:, 0] - an[:, 1] - an[:, 2]))], legend_panel=0)
    cf = artists[0]

    if pd.api.types.is_numeric_dtype(df['Color']):
        cb = plt.colorbar(cf, extend='both', spacing='uniform',
                          orientation='vertical', fraction=0.025, pad=0.05)
        cb.ax.set_ylabel(color_label(df), rotation=90, labelpad=-55, fontsize=14)

    sample_legend(ax, bbox_to_anchor=(0.085, 0.95), markerscale=1, fontsize=12,
              frameon=False,
              labelspacing=0.25, handletextpad=0.25)

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
    df.loc[:, 'Color'] = df.loc[:, 'TDS'].values
    plot(df, unit='mg/L', figname='Chadha diagram', figformat='jpg')
