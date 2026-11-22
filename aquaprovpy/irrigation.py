"""Irrigation calculations and reference-diagram graphical classifications.

SAR and Na% are calculated from meq/L, using existing AquaProv ion constants.
USSL equations: USDA Handbook 60 (1954), p. 79, Fig. 25 on p. 80.
Wilcox: Circular 784 (1948), p. 4 definition and Fig. 1, p. 6 digitization.
EC must be referenced to 25 C for interpretation; no correction is inferred.
See docs/ussl.html and docs/wilcox.html for boundary sources and uncertainty.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

from .ions import ions_WEIGHT, ions_CHARGE
from ._publication import STYLE, finish, scatter_samples, sample_labels, close_on_error


USSL_REFERENCE = 'https://www.ars.usda.gov/ARSUserFiles/20360500/hb60_pdf/hb60complete.pdf'
USSL_CODE_REFERENCE = 'https://rdrr.io/cran/iwaqr/src/R/plot_USSL.R'
WILCOX_REFERENCE = 'https://archive.org/details/explanationinter784wilc/page/n7/mode/1up'
BOUNDARY_NOTES = {
    'ussl': 'Exact empirical equations transcribed from USDA Handbook 60, p. 79; also match iwaqr. '
            'Historical graphical classes are not a site-specific irrigation safety assessment.',
    'wilcox': 'Primary-source Wilcox (1948), Fig. 1: manually digitized curves, not exact analytical boundaries. '
              'Review near-boundary classifications and local irrigation conditions.'}
# Manual readings of printed boundary-circle centres in Circular 784, Fig. 1.
# Values rounded to about 0.5 percentage point; scan/reading uncertainty remains.
# The primary figure's outer line reaches about 92%; the secondary figure uses 84%.
# Monotone cubic interpolation, no overshoot; classification and shading use
# precisely the same curves. Upper/right region wins on an exact boundary.
WILCOX_EC = np.array([0, 85, 240, 490, 750, 1000, 1250, 1500, 1750, 2000.0])
WILCOX_LOWER = np.array([100, 91, 81, 71.5, 65, 60, 56, 53, 50.5, 48.5])
WILCOX_UPPER = np.array([100, 98, 95.5, 91.5, 88.5, 85.5, 83, 80.5, 78.5, 76.5])
WILCOX_OUTER_END = 92.0
WILCOX_NAMES = ('Excellent to good', 'Good to permissible', 'Permissible to doubtful',
                'Doubtful to unsuitable', 'Unsuitable')


def calculate(df, unit='mg/L', *, ec_unit='uS/cm', require_k=True):
    """Return SAR, sodium percentages and EC from complete measurements.

    Wilcox (1948, p. 4) defines Na_percent as 100 * Na / (Ca + Mg + Na + K).
    NaK_percent retains the earlier potassium-inclusive measure for comparison.
    With require_k=False, skip both percentages and return SAR, EC and the
    available cation equivalents. Missing potassium is not treated as zero.
    """
    if unit not in ('mg/L', 'meq/L'):
        raise ValueError('Concentration unit must be mg/L or meq/L.')
    factors = {'uS/cm': 1.0, 'µS/cm': 1.0, 'μS/cm': 1.0, 'mS/cm': 1000.0, 'dS/m': 1000.0}
    if ec_unit not in factors:
        raise ValueError('EC unit must be uS/cm, mS/cm or dS/m.')
    if not isinstance(df, pd.DataFrame) or df.empty or not df.columns.is_unique:
        raise ValueError('Provide a non-empty DataFrame with unique column names.')
    ions = ['Ca', 'Mg', 'Na'] + (['K'] if require_k else [])
    needed = ions + ['EC']
    absent = [c for c in needed if c not in df]
    if absent:
        raise ValueError('Required columns: ' + ', '.join(absent))
    data = df[needed].apply(pd.to_numeric, errors='coerce').astype(float)
    if not np.isfinite(data.to_numpy()).all():
        raise ValueError('Irrigation calculations require finite numeric measurements without blanks.')
    if (data[ions] < 0).any().any() or (data['EC'] <= 0).any():
        raise ValueError('Concentrations must be nonnegative and EC strictly positive.')
    cations = data[ions].copy()
    if unit == 'mg/L':
        for ion in ions:
            cations[ion] *= abs(ions_CHARGE[ion]) / ions_WEIGHT[ion]
    denominator = (cations['Ca'] + cations['Mg']) / 2
    if (denominator <= 0).any():
        raise ValueError('Ca + Mg must be positive for every sample; SAR is otherwise undefined.')
    result = pd.DataFrame({'Sample': sample_labels(df),
        'EC_uS_cm': data['EC'].to_numpy() * factors[ec_unit],
        'SAR': (cations['Na'] / np.sqrt(denominator)).to_numpy()}, index=df.index)
    if require_k:
        result['Na_percent'] = (100 * cations['Na'] / cations.sum(axis=1)).to_numpy()
        result['NaK_percent'] = (100 * (cations['Na'] + cations['K']) / cations.sum(axis=1)).to_numpy()
    for ion in ions:
        result[ion + '_meq_L'] = cations[ion].to_numpy()
    if not np.isfinite(result.drop(columns='Sample').to_numpy()).all():
        raise ValueError('Calculation overflow; check measurement magnitudes.')
    return result


def ussl_boundaries(ec):
    """USDA Handbook 60, p. 79 equations, ordered S1/S2, S2/S3, S3/S4.

    C is EC in micromhos/cm (= uS/cm); log means base 10. Retain the
    original figure's EC extent rather than iwaqr's extension to 12000.
    """
    ec = np.asarray(ec, dtype=float)
    if not np.isfinite(ec).all() or (ec < 100).any() or (ec > 5000).any():
        raise ValueError('USSL graphical boundaries are defined only from 100 to 5000 uS/cm.')
    log_ec = np.log10(ec)
    return np.stack([18.87 - 4.44 * log_ec, 31.31 - 6.66 * log_ec,
                     43.75 - 8.87 * log_ec], axis=-1)


def wilcox_curves(ec):
    ec = np.asarray(ec, dtype=float)
    lower = PchipInterpolator(WILCOX_EC, WILCOX_LOWER, extrapolate=False)(ec)
    upper = PchipInterpolator(WILCOX_EC, WILCOX_UPPER, extrapolate=False)(ec)
    outer = np.where((ec >= 0) & (ec <= 3000),
                     100 - ((100 - WILCOX_OUTER_END) / 3000) * ec, np.nan)
    return lower, upper, outer


def classify_ussl(values):
    ec, sar = values['EC_uS_cm'].to_numpy(), values['SAR'].to_numpy()
    c = np.searchsorted([250, 750, 2250], ec, side='right') + 1
    valid = np.isfinite(ec) & np.isfinite(sar) & (ec >= 100) & (ec <= 5000) & (sar >= 0) & (sar <= 32)
    boundaries = ussl_boundaries(np.clip(np.nan_to_num(ec, nan=100), 100, 5000))
    s = 1 + (sar[:, None] >= boundaries).sum(axis=1)
    result = values.copy()
    result['Salinity_class'] = ['C' + str(v) for v in c]
    result['USSL_graphical_class'] = [f'C{a}-S{b}' if good else 'Outside reference domain'
                                        for a, b, good in zip(c, s, valid)]
    # Review tolerance is explicit, not a physical confidence interval.
    result['Boundary_review'] = valid & ((np.abs(sar[:, None] - boundaries).min(axis=1) <= 0.5) |
        (np.abs(ec[:, None] - np.array([250, 750, 2250])).min(axis=1) <= 25))
    return result


def classify_wilcox(values):
    ec, sodium = values['EC_uS_cm'].to_numpy(), values['Na_percent'].to_numpy()
    low, upper, outer = wilcox_curves(ec)
    codes = np.full(len(ec), 4)
    codes[(ec < 3000) & (sodium < outer)] = 3
    codes[(ec < 2000) & (sodium < upper)] = 2
    codes[(ec < 2000) & (sodium < low)] = 1
    codes[(ec < 750) & (sodium < low)] = 0
    result = values.copy()
    valid = np.isfinite(ec) & np.isfinite(sodium) & (ec > 0) & (ec <= 3500) & (sodium >= 0) & (sodium <= 100)
    result['Wilcox_graphical_class'] = [WILCOX_NAMES[c] if good else 'Outside reference domain'
                                       for c, good in zip(codes, valid)]
    review = ((ec <= 2000) & ((np.abs(sodium - low) <= 1) | (np.abs(sodium - upper) <= 1)))
    review |= (ec <= 3000) & (np.abs(sodium - outer) <= 1)
    review |= ((np.abs(ec - 750) <= 25) & (sodium <= wilcox_curves(750)[0]))
    review |= ((np.abs(ec - 2000) <= 25) & (sodium <= wilcox_curves(2000)[1]))
    review |= ((np.abs(ec - 3000) <= 25) & (sodium <= WILCOX_OUTER_END))
    result['Boundary_review'] = review & valid
    return result


@close_on_error
def plot(df, unit='mg/L', figname='Irrigation diagram', figformat='png', *,
         diagram='ussl', ec_unit='uS/cm', dpi=300, title=None):
    if diagram not in ('ussl', 'wilcox'):
        raise ValueError('Choose ussl or wilcox.')
    values = calculate(df, unit, ec_unit=ec_unit, require_k=diagram == 'wilcox')
    warnings = [BOUNDARY_NOTES[diagram], 'Verify EC is referenced to 25 C before interpreting irrigation classes.']
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(9, 7), layout='constrained')
        if diagram == 'ussl':
            values = classify_ussl(values)
            x = np.geomspace(100, 5000, 300)
            bounds = ussl_boundaries(x)
            limits = [np.zeros(len(x))] + [bounds[:, i] for i in range(3)] + [np.full(len(x), 32)]
            for i, color in enumerate(('#e1f2ea', '#edf3dc', '#fff1d5', '#fae2df')):
                ax.fill_between(x, limits[i], limits[i + 1], color=color, zorder=0)
                ax.text(4800, (limits[i][-1] + limits[i + 1][-1]) / 2, f'S{i + 1}', ha='right', fontsize=10)
            for boundary in bounds.T:
                ax.plot(x, boundary, color='#657889', lw=1)
            for edge in (250, 750, 2250):
                ax.axvline(edge, color='#657889', lw=1)
            for i, center in enumerate(np.sqrt(np.array([100, 250, 750, 2250]) * [250, 750, 2250, 5000])):
                ax.text(center, 31, f'C{i + 1}', ha='center')
            ax.set_xscale('log')
            ax.set_xticks([100, 250, 750, 2250, 5000])
            ax.set_xticklabels(['100', '250', '750', '2250', '5000'])
            y = values['SAR'].to_numpy()
            ax.set(xlim=(min(100, values.EC_uS_cm.min() * 0.9), max(5000, values.EC_uS_cm.max() * 1.1)),
                   ylim=(0, max(32, y.max() * 1.1)), ylabel='Sodium adsorption ratio (SAR)')
            class_column = 'USSL_graphical_class'
            ax.set_title(title or 'USSL · salinity and sodium hazard')
        else:
            values = classify_wilcox(values)
            ax.axvspan(0, 3500, color='#fae2df', zorder=0)
            x3 = np.linspace(0, 3000, 300)
            ax.fill_between(x3, 0, wilcox_curves(x3)[2], color='#fff1d5')
            x2 = np.linspace(0, 2000, 300)
            low, upper, _ = wilcox_curves(x2)
            ax.fill_between(x2, 0, upper, color='#edf3dc')
            ax.fill_between(x2, 0, low, color='#dceef5')
            x1 = np.linspace(0, 750, 150)
            ax.fill_between(x1, 0, wilcox_curves(x1)[0], color='#e1f2ea')
            ax.plot(x2, low, color='#657889', lw=1)
            ax.plot(x2, upper, color='#657889', lw=1)
            ax.plot(x3, wilcox_curves(x3)[2], color='#657889', lw=1)
            for edge, height in ((750, wilcox_curves(750)[0]),
                                 (2000, wilcox_curves(2000)[1]), (3000, WILCOX_OUTER_END)):
                ax.plot([edge, edge], [0, height], color='#657889', lw=1)
            for text, xx, yy, angle in [('Excellent to good', 350, 60, 90),
                    ('Good to permissible', 1400, 32, 90), ('Permissible to doubtful', 1200, 75, 0),
                    ('Doubtful to unsuitable', 2500, 45, 90), ('Unsuitable', 3250, 65, 90)]:
                ax.text(xx, yy, text, rotation=angle, ha='center', va='center', fontsize=9, color='#526479')
            from .plot_layout import BoundedTextLayout
            BoundedTextLayout(ax, ax.texts)
            y = values['Na_percent'].to_numpy()
            ax.set(xlim=(0, max(3500, values.EC_uS_cm.max() * 1.05)), ylim=(0, 100),
                   ylabel='Sodium percentage, 100 Na/(Ca+Mg+Na+K) (%)')
            class_column = 'Wilcox_graphical_class'
            ax.set_title(title or 'Wilcox · irrigation water quality')
        scatter_samples(ax, df, [values['EC_uS_cm'], y])
        ax.set_xlabel('Electrical conductivity at 25 °C (µS/cm)')
        ax.grid(alpha=0.15)
        footer = ('USDA Handbook 60 (1954), p. 79 equations; historical screening classes.' if diagram == 'ussl'
                  else 'Wilcox (1948), Circular 784, Fig. 1; digitized boundaries — review near-boundary samples.')
        fig.supxlabel(footer, fontsize=8, color='#526479', gid='aquaprov-reference-note')
        out = int((values[class_column] == 'Outside reference domain').sum())
        if out:
            warnings.append(f'{out} sample(s) outside the reference domain are shown but not graphically classified.')
        near = int(values['Boundary_review'].sum())
        if near:
            warnings.append(f'{near} sample(s) near graphical boundaries require review.')
        counts = values[class_column].value_counts().to_frame('n')
        counts['percent'] = 100 * counts['n'] / len(values)
        metadata = {'method': diagram, 'concentration_unit': unit, 'ec_input_unit': ec_unit,
            'ec_output_unit': 'uS/cm; must be referenced to 25 C for interpretation',
            'n_used': len(df), 'reference': USSL_REFERENCE if diagram == 'ussl' else WILCOX_REFERENCE,
            'boundary_status': BOUNDARY_NOTES[diagram], 'boundary_tie_rule': 'higher hazard / right-hand region',
            'SAR': 'Na / sqrt((Ca+Mg)/2), all ions in meq/L',
            'Na_percent': '100*Na/(Ca+Mg+Na+K), all ions in meq/L; Wilcox 1948 p. 4',
            'NaK_percent': '100*(Na+K)/(Ca+Mg+Na+K); audit only, not Wilcox ordinate',
            'boundary_version': 'primary-source-review-2026-10-16',
            'ussl_equations_low_to_high': ['18.87-4.44*log10(EC)', '31.31-6.66*log10(EC)', '43.75-8.87*log10(EC)'],
            'ussl_iwaqr_cross_check': USSL_CODE_REFERENCE,
            'wilcox_digitized_EC': WILCOX_EC.tolist(),
            'wilcox_digitized_lower': WILCOX_LOWER.tolist(),
            'wilcox_digitized_upper': WILCOX_UPPER.tolist(),
            'wilcox_outer': 'linear from (0,100) to (3000,92); approximate scan reading',
            'review_tolerance': '25 uS/cm; USSL 0.5 SAR; Wilcox 1 percentage point (heuristic)',
            'ussl_domain': 'EC 100–5000 uS/cm, SAR 0–32',
            'wilcox_domain': 'EC >0–3500 uS/cm, Na% 0–100'}
        return finish(fig, {'samples': values, 'classification_counts': counts}, metadata,
                      warnings, figname, figformat, dpi)
