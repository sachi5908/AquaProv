"""WQI methods: weighted arithmetic, relative-weight groundwater and CCME 1.0."""
import numpy as np
import pandas as pd

from .common import (IndexResult, SCHEMES, aggregate_arithmetic, prepare, classify,
                     validate_scheme, classification_table)


def weighted_arithmetic(frame, parameters, *, scheme=None):
    parameters = [{**p, 'rating':p.get('rating','ideal')} for p in parameters]
    result = aggregate_arithmetic(frame, parameters, index='WQI', inverse=True, scheme=scheme,
        method='Weighted arithmetic WQI (inverse-standard weights; configurable ideal-value ratings)')
    return result


def groundwater_wqi(frame, parameters, *, scheme=None):
    result = aggregate_arithmetic(frame, parameters, index='WQI', scheme=scheme,
        method='Relative-weight groundwater WQI — Ramakrishnaiah et al. (2009), DOI 10.1155/2009/757424')
    result.warnings.append('This implements the published relative-weight formulation with the configured parameter set and weights; it does not reproduce the Tumkur study dataset or its historical standards.')
    return result


def ccme_wqi(frame, parameters, *, site_column, time_column, period_column=None, scheme=None):
    """One score per site/period with at least four variables and four occasions.

    Missing tests are not passes. A failed zero observation against a positive
    minimum has an infinite excursion and the limiting amplitude F3 = 100.
    """
    values, compliance, tests, parameters = prepare(frame, parameters)
    scheme = validate_scheme(scheme or SCHEMES['ccme'])
    if scheme['direction'] != 'higher' or scheme['cuts'][0] < 0 or scheme['cuts'][-1] > 100:
        raise ValueError('CCME classifications must use the higher-is-better 0–100 scale.')
    if len(parameters) < 4:
        raise ValueError('CCME requires at least four selected variables.')
    keys = [site_column, time_column] + ([period_column] if period_column else [])
    if any(not key or key not in frame for key in keys) or len(set(keys)) != len(keys):
        raise ValueError('CCME requires distinct site and sampling-occasion columns, and an optional period column.')
    if frame[keys].isna().any().any() or frame[keys].astype(str).apply(lambda s: s.str.strip().eq('')).any().any():
        raise ValueError('CCME site, occasion and period identifiers cannot be missing.')
    groups = pd.DataFrame({'site': frame[site_column].astype(str).to_numpy(),
                           'period': frame[period_column].astype(str).to_numpy() if period_column else 'All observations',
                           'occasion': frame[time_column].astype(str).to_numpy()})
    if groups.duplicated(['site', 'period', 'occasion']).any():
        raise ValueError('CCME has duplicate site/period/occasion records. Resolve replicate tests explicitly.')
    result, membership, excursions = [], [], []
    notes = ['CCME WQI assesses attainment of the selected objectives over repeated sampling. Its categories are not drinking-water safety classes.',
             'At least four variables and four measured occasions per variable are required for each site/period. Missing tests are excluded from test counts, never treated as passes.']
    for (site, period), positions in groups.groupby(['site', 'period'], sort=False).indices.items():
        c = values.iloc[positions].to_numpy()
        valid = np.isfinite(c)
        failed = np.zeros_like(valid)
        excursion = np.zeros_like(c)
        for j,p in enumerate(parameters):
            upper, lower = p.get('upper'), p.get('lower')
            if upper is not None:
                f = valid[:,j] & (c[:,j] > upper)
                if upper == 0 and f.any():
                    raise ValueError('CCME upper objectives must be positive when exceeded (zero-tolerance tests cannot be ratio-normalized).')
                if upper:
                    excursion[f,j] = c[f,j]/upper-1
                failed[:,j] |= f
            if lower is not None:
                f = valid[:,j] & (c[:,j] < lower)
                with np.errstate(divide='ignore'):
                    excursion[f,j] = lower/c[f,j]-1
                failed[:,j] |= f
        adequate = bool((valid.sum(axis=0) >= 4).all())
        ntests = int(valid.sum())
        f1 = 100*failed.any(axis=0).sum()/len(parameters) if adequate else np.nan
        f2 = 100*failed.sum()/ntests if adequate else np.nan
        nse = excursion.sum()/ntests if ntests else np.nan
        f3 = (100. if np.isinf(nse) else 100*nse/(nse+1)) if adequate else np.nan
        score = float(np.clip(100-np.sqrt((f1*f1+f2*f2+f3*f3)/3), 0, 100)) if adequate else np.nan
        record = len(result)+1
        result.append(dict(source_row=int(positions[0])+1, record=record, site=site, period=period,
                           WQI=score, classification=classify([score], scheme)[0], F1=f1, F2=f2, F3=f3,
                           normalized_sum_excursions=nse, variables=len(parameters), tests=ntests,
                           failed_tests=int(failed.sum()), occasions=len(positions), status='Assessed' if adequate else 'Insufficient tests'))
        membership.extend(dict(record=record, source_row=int(i)+1) for i in positions)
        excursions.extend(dict(record=record, source_row=int(i)+1, parameter=p['name'],
                               failed=bool(failed[k,j]), excursion=excursion[k,j] if valid[k,j] else np.nan)
                          for k,i in enumerate(positions) for j,p in enumerate(parameters))
    samples = pd.DataFrame(result)
    if samples.WQI.isna().any():
        notes.append(f'{int(samples.WQI.isna().sum())} site/period groups lack four measured tests per variable and are unassessed.')
    if any(p['verification'] != 'verified' for p in parameters):
        notes.append('One or more objective limits are unverified. Consult the exported standards provenance.')
    metadata = dict(index='WQI', methodology='CCME Water Quality Index 1.0 (CCME, 2001)',
                    formula='100 - sqrt((F1^2 + F2^2 + F3^2)/3); F3 = 100*nse/(nse+1)',
                    classification_scheme=scheme, parameters=parameters, n_input=len(frame),
                    n_assessed=int(samples.WQI.notna().sum()), site_column=site_column,
                    time_column=time_column, period_column=period_column,
                    weighting='unweighted scope, frequency and amplitude; arithmetic weights and ideal values are not used')
    return IndexResult(samples, {'samples': samples, 'ccme_membership': pd.DataFrame(membership),
        'ccme_excursions': pd.DataFrame(excursions), 'compliance': compliance, 'parameter_tests': tests,
        'standards': pd.DataFrame(parameters), 'classification_scheme': classification_table(scheme)}, metadata, notes)
