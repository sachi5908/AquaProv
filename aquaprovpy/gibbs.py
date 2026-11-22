# -*- coding: utf-8 -*-
"""Gibbs diagrams for dissolved solids and ion ratios.

Created on Tue Sep 14 13:15:59 2021

@author: Jing
"""

import numpy as np
from ._diagram_colors import sample_legend, scatter_panels
import pandas as pd
import matplotlib.pyplot as plt

from .ions import ions_WEIGHT, ions_CHARGE
from ._diagram_colors import color_label, numeric_colors
from ._publication import close_on_error
from .plot_layout import BoundedTextLayout
from .core.diagram_inputs import prepare_python_diagram, panel_mask, annotate_input_coverage


class _GibbsFieldLayout(BoundedTextLayout):
    """Keep process labels parallel to the envelopes as the page resizes."""

    def __init__(self, axis, labels):
        self.slopes = labels
        super().__init__(axis, [text for text, _ in labels])

    def draw(self, renderer):
        for text, slope in self.slopes:
            x, y = text.get_position()
            start, end = self.axis.transData.transform(
                [(x, y), (x + .1, y * 10 ** (.1 * slope))])
            direction = end - start
            text.set_rotation(np.degrees(np.arctan2(direction[1], direction[0])))
        super().draw(renderer)


def _label_processes(axis, *, anion=False):
    labels = [
        (axis.text(.80, 12, 'Precipitation dominance', ha='center', va='center',
                   rotation_mode='anchor', fontsize=10), -1.9 if anion else -3.3),
        (axis.text(.10, 250, 'Rock\ndominance', ha='center', va='center',
                   rotation_mode='anchor', fontsize=10), 0),
        (axis.text(.80, 7000, 'Evaporation–crystallization', ha='center', va='center',
                   rotation_mode='anchor', fontsize=10), 2.3 if anion else 3.3),
    ]
    _GibbsFieldLayout(axis, labels)


@close_on_error
def plot(df, unit='mg/L', figname='Gibbs diagram', figformat='jpg'):
    """Plot and save the two Gibbs mass-ratio panels.

    Use ion mass concentrations for the ratios, as in Gibbs (1970), so
    sample coordinates and the reference envelopes share the same basis.
    Convert meq/L inputs to mg/L using each ion's equivalent weight.

    Parameters
    ----------
    df : pandas.DataFrame
        TDS and either Na/Ca or Cl/HCO3 concentrations, one row per sample.
        Each ratio panel uses only its own available measurements.
    unit : str
        Ion concentrations in mg/L or meq/L. TDS is always in mg/L.
    figname : str
        Output path without the file extension, or None for a live figure.
    figformat : str
        Output format, such as 'png', 'pdf' or 'svg'.

    References
    ----------
    .. [1] Gibbs, Ronald J. 1970.
           Mechanisms Controlling World Water Chemistry.
           Science 170, 1088–1090.
           https://doi.org/10.1126/science.170.3962.1088
    """
    df = prepare_python_diagram(df, 'gibbs')
    if unit not in ('mg/L', 'meq/L'):
        raise ValueError('Concentration unit must be mg/L or meq/L.')
    cation_rows = panel_mask(df, ('Na', 'Ca', 'TDS'))
    anion_rows = panel_mask(df, ('Cl', 'HCO3', 'TDS'))
    if (df['TDS'] <= 0).any():
        raise ValueError('TDS must be positive for the logarithmic axis.')
    for rows, ions in ((cation_rows, ('Na', 'Ca')), (anion_rows, ('Cl', 'HCO3'))):
        values = df.loc[rows, list(ions)].to_numpy(dtype=float)
        if (values < 0).any() or (values.sum(axis=1) <= 0).any():
            raise ValueError('Gibbs ratios need nonnegative ions and a positive denominator.')

    # Load the wrapped lines taken from Gibbs (1970)
    Cl_HCO3_plot_wrapped_lines = np.array([
        [0.0056, 0.0251, 0.0446, 0.0771, 0.1096,
         0.1291, 0.1454, 0.1844, 0.2104, 0.2299,
         0.2656, 0.2883, 0.3078, 0.3500, 0.3792,
         0.4052, 0.4507, 0.4799, 0.4994, 0.5351,
         0.5579, 0.5741, 0.5904, 0.6196, 0.6488,
         0.6716, 0.6976, 0.7236, 0.7495, 0.7723,
         0.7983, 0.8242, 0.8535, 0.8827, 0.9119,
         0.9444, 0.9704, 0.9931, 9.9999, 9.9999,
         0.9961, 0.9830, 0.9668, 0.9538, 0.944,
         0.9180, 0.9050, 0.8887, 0.8530, 0.8302,
         0.8074, 0.7814, 0.7554, 0.7294, 0.7132,
         0.6937, 0.6742, 0.6417, 0.6189, 0.5897,
         0.5735, 0.5605, 0.5377, 0.5150, 0.4955,
         0.4760, 0.4565, 0.4402, 0.4175, 0.4013,
         0.3785, 0.3590, 0.3395, 0.3200, 0.3070,
         0.2941, 0.2746, 0.2551, 0.2388, 0.2291,
         0.2128, 0.2063, 0.1998, 0.1997, 0.2062,
         0.2159, 0.2354, 0.2516, 0.2646, 0.2873,
         0.3002, 0.3262, 0.3489, 0.3683, 0.3878,
         0.4105, 0.4267, 0.4527, 0.4754, 0.5175,
         0.5500, 0.5694, 0.5889, 0.6148, 0.6376,
         0.6538, 0.6700, 0.6927, 0.7089, 0.7252,
         0.7479, 0.7771, 0.7965, 0.8160, 0.8322,
         0.8517, 0.8841, 0.9003, 0.9165, 0.9392,
         0.9522, 0.9684, 0.9846, 0.9975, 9.9999,
         9.9999, 0.9935, 0.9870, 0.9708, 0.9579,
         0.9385, 0.9255, 0.9061, 0.8801, 0.8607,
         0.8347, 0.8088, 0.7893, 0.7602, 0.7277,
         0.6855, 0.6531, 0.6044, 0.5623, 0.5298,
         0.4909, 0.4520, 0.4196, 0.3839, 0.3450,
         0.3158, 0.2899, 0.2672, 0.2380, 0.2088,
         0.1861, 0.1634, 0.1408, 0.1148, 0.0889,
         0.0759, 0.0630, 0.0500, 0.0371, 0.0209,
         0.0079],
        [21.4751, 19.1493, 17.0753, 15.2298, 13.0728,
         11.8826, 11.2221, 10.2041, 9.6387, 9.2797,
         8.9368, 8.7709, 8.6076, 8.6146, 8.4558,
         8.2994, 7.8425, 7.6979, 7.4111, 7.0018,
         6.7414, 6.4899, 6.3687, 5.9019, 5.6831,
         5.4718, 5.1686, 4.9767, 4.7919, 4.6137,
         4.5284, 4.4446, 4.3627, 4.2822, 4.2033,
         4.2059, 4.208, 4.1299, 4.1299, 10.1674,
         10.1674, 11.4037, 12.7896, 14.0724, 15.4849,
         17.6996, 19.8518, 21.8417, 24.487, 27.9908,
         30.2081, 33.2299, 35.8599, 38.6981, 40.9758,
         43.3849, 46.8245, 50.5243, 54.5265, 58.8385,
         61.1188, 62.2861, 67.2201, 69.8165, 73.9212,
         76.7813, 81.2954, 84.446, 89.4052, 92.8702,
         96.4574, 102.1283, 104.0659, 110.1841, 114.4615,
         116.6475, 121.1607, 125.8485, 130.7259, 138.4373,
         146.5855, 161.3088, 174.141, 191.656, 219.2029,
         236.7142, 260.6201, 281.4751, 298.2091, 322.1122,
         347.8662, 383.045, 421.755, 455.5326, 482.6745,
         521.3635, 563.0834, 608.2554, 657.0104, 751.9576,
         828.1041, 877.4449, 929.7256, 985.244, 1044.0127,
         1085.1491, 1127.9064, 1195.1847, 1242.2777, 1291.2262,
         1368.2463, 1506.707, 1596.481, 1724.3402, 1826.9677,
         1973.2861, 2258.0322, 2485.9166, 2684.8419, 3013.3769,
         3317.2855, 3582.7378, 3944.3137, 4178.8072, 4178.8072,
         62336.9735, 62336.9735, 56633.1044, 49506.8651, 42458.3638,
         35717.6411, 33073.3075, 28909.8381, 24787.6514, 22513.9619,
         20058.1172, 17870.1583, 16545.0928, 14739.4207, 13643.1016,
         12151.1174, 11247.3165, 9825.9309, 8585.2422, 7795.8054,
         6682.5559, 5839.1344, 5201.5485, 4459.0392, 3822.2836,
         3277.0691, 2919.6032, 2551.907, 2273.401, 1875.816,
         1703.6475, 1460.8193, 1252.6024, 1053.6071, 886.2253,
         805.035, 731.2828, 677.1427, 603.4295, 517.4845,
         452.3967]])

    Na_Ca_plot_wrapped_lines = np.array([
        [0.0083, 0.0277, 0.0505, 0.0668, 0.0830,
         0.1090, 0.1253, 0.1481, 0.1611, 0.1871,
         0.2067, 0.2294, 0.2457, 0.2718, 0.2880,
         0.3174, 0.3500, 0.3956, 0.4379, 0.4802,
         0.5225, 0.5681, 0.6039, 0.6429, 0.6819,
         0.7144, 0.7534, 0.7729, 0.7924, 0.8119,
         0.8314, 0.8509, 0.8737, 0.8997, 0.9225,
         0.9420, 0.9615, 0.9843, 0.9973, 9.9999,
         9.9999, 0.9932, 0.9866, 0.9636, 0.9406,
         0.9209, 0.9045, 0.8881, 0.8716, 0.8519,
         0.8322, 0.8026, 0.7663, 0.7367, 0.7070,
         0.6774, 0.6543, 0.6279, 0.6146, 0.5916,
         0.5783, 0.5617, 0.5419, 0.5383, 0.5513,
         0.5739, 0.6096, 0.6453, 0.6778, 0.6940,
         0.7135, 0.7362, 0.7653, 0.8010, 0.8399,
         0.8724, 0.8983, 0.9340, 0.9469, 0.9696,
         0.9891, 0.9955, 9.9999, 9.9999, 0.9003,
         0.8871, 0.8410, 0.8278, 0.7949, 0.7619,
         0.7290, 0.6830, 0.6369, 0.5942, 0.5516,
         0.5089, 0.4399, 0.4005, 0.3545, 0.3118,
         0.2658, 0.2296, 0.1836, 0.1442, 0.1047,
         0.0718, 0.0454, 0.0092],
        [108.9257, 97.0774, 88.1725, 80.1044, 74.1755,
         66.0907, 61.199, 56.6553, 52.4686, 47.6497,
         44.9668, 40.842, 39.2892, 35.6808, 33.0399,
         30.5792, 28.2983, 24.7192, 21.5954, 18.5101,
         15.5659, 12.5986, 11.0093, 9.0844, 7.3545,
         6.3061, 5.2036, 4.6375, 4.2938, 3.8267,
         3.543, 3.2184, 2.9232, 2.6046, 2.321,
         2.1489, 1.9896, 1.8419, 1.7386, 1.7386,
         7514.32, 7514.32, 7234.9489, 6582.7621, 5989.366,
         5553.6776, 5051.7878, 4683.7185, 4179.9779, 3730.8803,
         3394.141, 2808.0488, 2153.0926, 1714.648, 1365.4861,
         1087.4256, 899.4273, 702.6564, 592.1454, 508.812,
         420.6893, 334.8554, 271.6992, 204.138, 175.1691,
         144.6326, 114.8937, 91.2695, 78.2591, 68.4377,
         59.8414, 50.3607, 39.2599, 30.5983, 22.9525,
         18.2353, 14.4912, 11.7332, 10.262, 8.6362,
         7.5514, 7.267, 7.267, 45278.8769, 45278.8769,
         39640.8983, 28715.7533, 25624.1396, 20408.7169, 15947.8034,
         12461.9512, 9558.8684, 7473.2267, 6069.0146, 5023.5351,
         4238.2048, 3072.823, 2592.1249, 2065.5649, 1614.6797,
         1311.4464, 1044.6506, 816.7192, 650.65, 508.5584,
         412.8464, 341.5145, 261.8588]])

    colors = numeric_colors(df)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5), layout='constrained')
    mass_factor = {ion: 1.0 if unit == 'mg/L' else ions_WEIGHT[ion] / abs(ions_CHARGE[ion])
                   for ion in ('Na', 'Ca', 'Cl', 'HCO3')}

    # Na-Ca panel.
    ax1.semilogy()
    ax1.plot(Na_Ca_plot_wrapped_lines[0], Na_Ca_plot_wrapped_lines[1],
             'k--', lw=1.25, label='Gibbs process boundaries')

    sodium = df['Na'].to_numpy(dtype=float) * mass_factor['Na']
    calcium = df['Ca'].to_numpy(dtype=float) * mass_factor['Ca']
    ratio = np.divide(sodium, sodium + calcium, out=np.full(len(df), np.nan), where=cation_rows)
    artists = scatter_panels(ax1, df, [(ratio, df['TDS'])], masks=[cation_rows], legend_panel=0)

    ax1.set_xlim(0, 1)
    ax1.set_ylim(1, 45000)

    ax1.minorticks_on()
    ax1.tick_params(which='major', direction='in', length=4, width=1.25)
    ax1.tick_params(which='minor', direction='in', length=2.5, width=1.25)

    ax1.spines['top'].set_linewidth(1.25)
    ax1.spines['top'].set_color('k')
    ax1.spines['bottom'].set_linewidth(1.25)
    ax1.spines['bottom'].set_color('k')
    ax1.spines['left'].set_linewidth(1.25)
    ax1.spines['left'].set_color('k')
    ax1.spines['right'].set_linewidth(1.25)
    ax1.spines['right'].set_color('k')

    _label_processes(ax1)

    ax1.set_xlabel('Na$^+$/(Na$^+$+Ca$^{2+}$) (mass ratio)', weight='normal',
               fontsize=12)
    ax1.set_ylabel('TDS (mg/L)', weight='normal',
                   fontsize=12)
    labels = ax1.get_xticklabels() + ax1.get_yticklabels()
    [label.set_fontsize(10) for label in labels]

    sample_legend(ax1, loc='upper left', markerscale=1, frameon=False, fontsize=12,
               labelspacing=0.25, handletextpad=0.25)

    # Cl-HCO3 panel.
    ax2.semilogy()
    ax2.plot(Cl_HCO3_plot_wrapped_lines[0], Cl_HCO3_plot_wrapped_lines[1],
             'k--', lw=1.25, label='Gibbs process boundaries')

    chloride = df['Cl'].to_numpy(dtype=float) * mass_factor['Cl']
    bicarbonate = df['HCO3'].to_numpy(dtype=float) * mass_factor['HCO3']
    ratio = np.divide(chloride, chloride + bicarbonate, out=np.full(len(df), np.nan), where=anion_rows)
    artists += scatter_panels(ax2, df, [(ratio, df['TDS'])], masks=[anion_rows], legend_panel=0)
    cf = artists[-1]

    ax2.set_xlim(0, 1)
    ax2.set_ylim(1, 45000)

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

    _label_processes(ax2, anion=True)

    ax2.set_xlabel('Cl$^-$/(Cl$^-$+HCO$_3^-$) (mass ratio)',
                   weight='normal', fontsize=12)
    ax2.set_ylabel('TDS (mg/L)',
                   fontsize=12, weight='normal')

    labels = ax2.get_xticklabels() + ax2.get_yticklabels()
    [label.set_fontsize(10) for label in labels]

    sample_legend(ax2, loc='upper left', markerscale=1, frameon=False, fontsize=12,
               labelspacing=0.25, handletextpad=0.25)
    if colors is not None:
        fig.colorbar(cf, ax=[ax1, ax2], label=color_label(df), fraction=.035, pad=.03)

    for axis, rows, needed in ((ax1, cation_rows, 'Na, Ca and TDS'), (ax2, anion_rows, 'Cl, HCO3 and TDS')):
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
    plot(df, unit='mg/L', figname='Gibbs diagram', figformat='jpg')
