# -*- coding: utf-8 -*-
"""Rectangular Piper diagrams for major-ion chemistry.

Created on Wed Sep 15 14:54:43 2021

@author: Jing
"""

import pandas as pd
import matplotlib.pyplot as plt
from pylab import *

from ._chemistry import major_ion_meq
from ._publication import close_on_error, isolated_style


from ._diagram_colors import sample_legend, scatter_panels


@close_on_error
@isolated_style
def plot(df, unit='mg/L', figname='rectangle Piper diagram', figformat='jpg'):
    """Plot and save a rectangular Piper diagram.

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
    .. [1] Ray, R. K. and Mukherjee R. 2008.
           Reproducing the Piper Trilinear Diagram in Rectangular Coordinates.
           Groundwater 46(6), 893–896.
           https://doi.org/10.1111/j.1745-6584.2008.00471.x
    """
    if not {'Ca', 'Mg', 'Na', 'K',
            'HCO3', 'CO3', 'Cl', 'SO4'}.issubset(df.columns):
        raise RuntimeError("""
        Trilinear Piper diagram requires geochemical parameters:
        Ca, Mg, Na, K, HCO3, CO3, Cl, and SO4.
        Confirm that these parameters are provided in the input file.""")

    ALLOWED_UNITS = ['mg/L', 'meq/L']
    if unit not in ALLOWED_UNITS:
        raise RuntimeError("""
        Currently only mg/L and meq/L are supported.
        Convert the unit manually if needed.""")

    meqL = major_ion_meq(df, unit)

    # Global plot settings
    rc('xtick', labelsize=12)
    rc('ytick', labelsize=12)
    rc('font', size=12)
    rc('legend', fontsize=14)
    rc('figure', figsize=(15.0, 5.0)) # define size of Figure window
    markersize=4
    linewidth=2
    xtickpositions = linspace(0, 100, 6) # desired xtickpositions for graphs

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

    fig = plt.figure()

    # Cation panel.
    ax1 = fig.add_subplot(131)
    ax1b = ax1.twinx()

    ax1.fill([100, 0, 100, 100], [0, 100, 100, 0], color = (0.8, 0.8, 0.8))
    ax1.plot([100, 0], [0, 100], 'k')
    ax1.plot([50, 0, 50, 50], [0, 50, 50, 0], 'k--')
    ax1.text(25, 15, 'Na type', fontsize=14)
    ax1.text(75, 15, 'Ca type', fontsize=14)
    ax1.text(25, 65, 'Mg type', fontsize=14)

    # Plot the scatters
    scatter_panels(ax1b, df, [(100 * cat[:, 0], 100 * cat[:, 1])], legend_panel=0)

    lgnd = sample_legend(plt.gca(), loc='upper left', markerscale=1, frameon=False, fontsize=12,
                  handletextpad=-0.5, facecolor=(0.8, 0.8, 0.8))

    # Axis limits and labels.
    ax1.set_xlim(0,100)
    ax1.set_ylim(0,100)
    ax1b.set_ylim(0,100)
    ax1.set_xlabel(r'$\longleftarrow$' + 'Ca$^{2+}$ (% meq)',
                   fontsize=12, weight='normal')
    ax1b.set_ylabel('Mg$^{2+}$ (% meq)' + r'$\longrightarrow$',
                    fontsize=12, weight='normal')
    setp(ax1, yticklabels=[])

    # Reverse x axis:
    ax1.set_xlim(ax1.get_xlim()[::-1])

    # Anion panel.
    ax3 = fig.add_subplot(133)
    ax3.fill([100, 100, 0, 100], [0, 100, 100, 0], color = (0.8, 0.8, 0.8))
    ax3.plot([0, 100], [100, 0], 'k')
    ax3.plot([50, 50, 0, 50], [0, 50, 50, 0],'k--')
    ax3.text(55, 15, 'Cl type', fontsize=14)
    ax3. text(5, 15, 'HCO$_3$ type', fontsize=14)
    ax3.text(5, 65, 'SO$_4$ type', fontsize=14)

    # Plot the scatters
    scatter_panels(ax3, df, [(100 * an[:, 2], 100 * an[:, 1])], legend_panel=-1)

    # Axis limits and labels.
    ax3.set_xlim(0, 100)
    ax3.set_ylim(0, 100)
    ax3.set_xlabel('Cl$^-$ (% meq)' + r'$\longrightarrow$',
                   size=12, weight='normal')
    ax3.set_ylabel('SO$_4^{2-}$ (% meq)' + r'$\longrightarrow$',
                   size=12, weight='normal')

    # Combined cation-anion panel.
    ax2 = fig.add_subplot(132)
    ax2b = ax2.twinx()

    ax2.plot([0, 100], [10, 10], 'k--')
    ax2.plot([0, 100], [50, 50], 'k--')
    ax2.plot([0, 100], [90, 90], 'k--')
    ax2.plot([10, 10], [0, 100], 'k--')
    ax2.plot([50, 50], [0, 100], 'k--')
    ax2.plot([90, 90], [0, 100], 'k--')

    # Plot the scatters
    scatter_panels(ax2, df, [(100 * cat[:, 2], 100 * (an[:, 1] + an[:, 2]))], legend_panel=-1)

    # Axis limits and labels.
    ax2.set_xlim(0,100)
    ax2.set_ylim(0,100)
    ax2.set_xlabel('Na$^+$+K$^+$ (% meq)' + r'$\longrightarrow$',
                   size=12, weight='normal')
    ax2.set_ylabel('SO$_4^{2-}$+Cl$^-$ (% meq)' + r'$\longrightarrow$',
                   size=12, weight='normal')
    ax2.set_title(r'$\longleftarrow$' + 'Ca$^{2+}$+Mg$^{2+}$ (% meq)',
                  size=12, weight='normal')
    ax2b.set_ylabel(r'$\longleftarrow$' + 'CO$_3^{2-}$+HCO$_3^-$ (% meq)',
                    size=12, weight='normal')

    # Reverse 2nd y axis:
    ax2b.set_ylim(100, 0)

    # adjust position of subplots
    plt.subplots_adjust(left=0.05, bottom=0.2, right=0.95, top=0.90,
                    wspace=0.4, hspace=0.0)

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
    plot(df, unit='mg/L', figname='rectangle Piper diagram', figformat='jpg')
