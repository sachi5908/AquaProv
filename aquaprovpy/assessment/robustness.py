"""Compositional geometry and inference with wells as the sampling units."""
import numpy as np
import pandas as pd
from scipy.linalg import helmert
from scipy.cluster.hierarchy import linkage, cut_tree
from scipy.spatial.distance import cdist
from scipy.stats import theilslopes, kendalltau
from sklearn.metrics import adjusted_rand_score


def compositional(m, columns, *, clusters=3, resamples=0, seed=42):
    if len(columns) < 3 or len(set(columns)) != len(columns) or any(c not in m.values for c in columns):
        raise ValueError('Select at least three distinct, mapped concentration components.')
    if any(c in ('pH', 'EC', 'TDS', 'Alkalinity') for c in columns):
        raise ValueError('Select non-overlapping concentration components; pH, EC, TDS and alkalinity are not parts.')
    if ('Cr_total' in columns and 'Cr_VI' in columns):
        raise ValueError('Total Cr and Cr(VI) overlap and cannot both be compositional parts.')
    raw = m.values[columns]
    keep = np.isfinite(raw).all(axis=1) & (raw > 0).all(axis=1)
    data = raw[keep].to_numpy()
    if len(data) < 2:
        raise ValueError('At least two rows with strictly positive measured parts are needed for PCA. No pseudocount is added.')
    if isinstance(clusters, bool) or not isinstance(clusters, int) or not 1 <= clusters <= len(data):
        raise ValueError('Cluster count must be between 1 and the complete sample count.')
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples < 0:
        raise ValueError('Stability resamples must be a non-negative integer.')
    if resamples and 'well' in m.samples and m.samples.loc[keep, 'well'].dropna().duplicated().any():
        raise ValueError('Row-bootstrap stability requires independent rows. Select one campaign/record per well, or use the well-bootstrap view for repeated sampling.')
    # Helmert rows form an orthonormal basis of the zero-sum CLR subspace.
    basis = helmert(len(columns), full=False).T
    log = np.log(data)
    clr = log - log.mean(axis=1, keepdims=True)
    ilr = clr @ basis
    center = ilr.mean(axis=0)
    u, s, vt = np.linalg.svd(ilr-center, full_matrices=False)
    if np.sum(s*s) <= np.finfo(float).eps:
        raise ValueError('All samples have the same composition; PCA is undefined.')
    # Fix sign conventions for deterministic exports.
    for j in range(len(vt)):
        pivot = np.argmax(abs(vt[j]))
        if vt[j, pivot] < 0:
            vt[j] *= -1
            u[:, j] *= -1
    names = [f'PC{i+1}' for i in range(len(s))]
    scores = pd.DataFrame(u*s, columns=names)
    scores.insert(0, 'row', m.samples.loc[keep, 'row'].to_numpy())
    scores.insert(1, 'sample', m.samples.loc[keep, 'sample'].astype(str).to_numpy())
    labels = cut_tree(linkage(ilr, method='ward'), n_clusters=clusters).ravel()
    scores['cluster'] = labels+1
    tables = {
        'coda_scores': scores,
        'clr_loadings': pd.DataFrame(basis @ vt.T, index=columns, columns=names),
        'ilr_basis': pd.DataFrame(basis, index=columns, columns=[f'ILR{i+1}' for i in range(basis.shape[1])]),
        'ilr_center': pd.DataFrame({'mean': center}),
        'coda_variance': pd.DataFrame({'component': names, 'eigenvalue': s*s/(len(data)-1), 'fraction': s*s/sum(s*s)}),
        'coda_exclusions': m.samples.loc[~keep].assign(reason='Missing, censored, zero or negative selected component'),
    }
    notes = ['ILR PCA uses an exported orthonormal Helmert basis and Euclidean Aitchison geometry; balances are centered, not standardized.',
             f'{int((~keep).sum())} rows excluded explicitly; no non-detect substitution or zero pseudocount.',
             'Loadings describe log-ratio contrasts, not effects on absolute concentrations. Selected components determine the subcomposition.']
    if resamples:
        rng = np.random.default_rng(seed)
        consensus = np.zeros((len(data), len(data)))
        stability = []
        from ..core.progress import report_progress
        for repeat in range(resamples):
            indices = rng.integers(0, len(data), len(data))
            train = ilr[indices]
            bootlabels = cut_tree(linkage(train, method='ward'), n_clusters=clusters).ravel()
            centroids = np.array([train[bootlabels == k].mean(axis=0) for k in np.unique(bootlabels)])
            predicted = np.argmin(cdist(ilr, centroids), axis=1)
            consensus += predicted[:, None] == predicted[None, :]
            stability.append({'resample': repeat+1, 'adjusted_rand_index': adjusted_rand_score(labels, predicted)})
            report_progress(95 * (repeat + 1) / resamples, f'Cluster resamples: {repeat + 1} / {resamples}')
        tables['cluster_stability'] = pd.DataFrame(stability)
        rows = scores.row.astype(str).tolist()
        tables['cluster_coassignment'] = pd.DataFrame(consensus/resamples, index=rows, columns=rows)
        notes.append('Stability bootstraps rows, fits Ward clusters, then assigns all rows to the nearest training centroid. It assumes independent rows; repeated wells require an independent subset.')
    return tables, notes


def well_inference(m, column, *, resamples=2000, seed=42):
    if column not in m.values or 'well' not in m.samples:
        raise ValueError('Map a well identifier and choose a measurement before well-level inference.')
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples < 2:
        raise ValueError('Use at least 2 bootstrap resamples.')
    data = m.samples.copy()
    data['value'] = m.values[column]
    keep = data.value.notna() & data.well.notna() & (data.well.astype(str).str.strip() != '')
    used = data[keep].copy()
    wells = used.groupby('well', sort=False).value.agg(['mean', 'median', 'count']).reset_index()
    if wells.empty:
        raise ValueError('At least one well with measured values is required.')
    rng = np.random.default_rng(seed)
    means = wells['mean'].to_numpy()
    draws = np.array([rng.choice(means, len(means), replace=True).mean() for _ in range(resamples)])
    lo, hi = np.quantile(draws, [.025, .975])
    tables = {'well_summaries': wells,
              'well_bootstrap': pd.DataFrame([{'analyte': column, 'n_wells': len(wells), 'n_measurements': len(used),
                    'equal_well_mean': means.mean(), 'pooled_measurement_mean': used.value.mean(),
                    'lower_95': lo, 'upper_95': hi, 'resamples': resamples}]),
              'well_exclusions': data[~keep]}
    notes = ['Bootstrap resamples whole well summaries, weighting wells equally. Intervals address between-well sampling variation, not laboratory error.',
             'Independent, representative wells are required. Resampling wells alone does not resolve spatial dependence.']
    if len(wells) < 3:
        notes.append('Fewer than three wells: bootstrap intervals have limited information; a single-well interval is degenerate.')
    if 'time' in used:
        numeric = pd.to_numeric(used.time, errors='coerce')
        is_datetime = pd.api.types.is_datetime64_any_dtype(used.time)
        if not is_datetime and numeric.notna().sum() == used.time.notna().sum():
            used['t'] = numeric
            time_unit = 'source numeric time unit'
        else:
            dates = pd.to_datetime(used.time, errors='coerce', format='ISO8601', utc=True)
            used['t'] = (dates - pd.Timestamp('1970-01-01', tz='UTC')).dt.total_seconds() / (365.25*86400)
            time_unit = 'year (365.25 days); ISO YYYY-MM-DD dates'
        trends = []
        for well, g in used.groupby('well', sort=False):
            # Equal-time replicates/seasons are aggregated explicitly, not counted as independent times.
            times = g.dropna(subset=['t']).groupby('t').value.mean()
            if len(times) < 2:
                trends.append({'well': well, 'status': 'fewer than 2 distinct times', 'n_times': len(times)})
                continue
            slope = theilslopes(times.values, times.index.to_numpy()).slope
            trends.append({'well': well, 'status': 'descriptive', 'n_times': len(times),
                           'sen_slope': slope, 'kendall_tau': kendalltau(times.index, times.values).statistic})
        tables['within_well_trends'] = pd.DataFrame(trends)
        tables['trend_time_exclusions'] = used[used.t.isna()].assign(reason='Missing or non-ISO time value')
        notes.append('Descriptive Theil-Sen slopes use means at each distinct time; no serial-independence p-values or trend forecasts. Slope denominator: '+time_unit+'.')
    return tables, notes
