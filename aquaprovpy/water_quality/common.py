"""Shared validation, units and classifications; no implicit missing-data weights."""
from dataclasses import dataclass
from copy import deepcopy

import numpy as np
import pandas as pd


QUALITY_LABELS = ['Excellent', 'Good', 'Poor', 'Very Poor', 'Unsuitable']
QUALITY_COLORS = ['#2166ac', '#1a9850', '#fee08b', '#f46d43', '#a50026']
SCHEMES = {
    'arithmetic': dict(name='Weighted arithmetic (five classes)', cuts=[25., 50., 75., 100.],
                       labels=QUALITY_LABELS, colors=QUALITY_COLORS, direction='lower', closed='upper'),
    'relative': dict(name='Ramakrishnaiah-style (five classes)', cuts=[50., 100., 200., 300.],
                     labels=QUALITY_LABELS, colors=QUALITY_COLORS, direction='lower', closed='upper'),
    'ccme': dict(name='CCME guideline attainment (not drinking-water safety)', cuts=[45., 65., 80., 95.],
                 labels=['Poor', 'Marginal', 'Fair', 'Good', 'Excellent'],
                 colors=list(reversed(QUALITY_COLORS)), direction='higher', closed='lower'),
}


@dataclass
class IndexResult:
    samples: pd.DataFrame
    tables: dict
    metadata: dict
    warnings: list


def validate_scheme(scheme):
    scheme = deepcopy(scheme)
    cuts = np.asarray(scheme.get('cuts', []), dtype=float)
    if cuts.shape != (4,) or not np.isfinite(cuts).all() or not (np.diff(cuts) > 0).all():
        raise ValueError('Classification requires four finite, strictly increasing thresholds.')
    if len(scheme.get('labels', [])) != 5 or len(set(scheme['labels'])) != 5:
        raise ValueError('Classification requires five distinct labels.')
    from matplotlib.colors import is_color_like
    if len(scheme.get('colors', [])) != 5 or not all(is_color_like(c) for c in scheme['colors']):
        raise ValueError('Classification requires five valid colours.')
    if scheme.get('closed') not in ('upper', 'lower') or scheme.get('direction') not in ('higher', 'lower'):
        raise ValueError('Specify classification direction and boundary inclusion.')
    if not isinstance(scheme.get('name'), str) or not scheme['name'].strip():
        raise ValueError('Name the classification scheme.')
    scheme['cuts'] = cuts.tolist()
    return scheme


def classify(values, scheme):
    scheme = validate_scheme(scheme)
    values = np.asarray(values, float)
    codes = np.searchsorted(scheme['cuts'], values, side='left' if scheme['closed'] == 'upper' else 'right')
    return np.where(np.isfinite(values), np.asarray(scheme['labels'], object)[codes], 'Unassessed')


def classification_table(scheme):
    scheme = validate_scheme(scheme)
    bounds = [None, *scheme['cuts'], None]
    return pd.DataFrame({'class': scheme['labels'], 'lower': bounds[:-1], 'upper': bounds[1:],
                         'boundary_inclusion': scheme['closed'], 'color': scheme['colors'],
                         'direction': scheme['direction'], 'scheme': scheme['name']})


def unit_factor(unit, standard_unit):
    # Limits and inverse-standard weights always use the declared canonical unit.
    unit = str(unit).replace('µ', 'u').replace('μ', 'u').strip()
    standard_unit = str(standard_unit).replace('µ', 'u').replace('μ', 'u').strip()
    families = ({'mg/L': 1., 'ug/L': .001, 'g/L': 1000.},
                {'uS/cm': 1., 'mS/cm': 1000.}, {'pH': 1.}, {'NTU': 1.},
                {'#/dL':1.}, {'CFU/100 mL':1.}, {'MPN/100 mL':1.})
    for family in families:
        if unit in family and standard_unit in family:
            return family[unit] / family[standard_unit]
    raise ValueError(f'Unsupported conversion {unit!r} to {standard_unit!r}. Use the named chemical species and standard units.')


def validate_parameters(parameters):
    if not isinstance(parameters, list) or not parameters:
        raise ValueError('Select at least one parameter and review its standard, units and mapping.')
    names, columns = set(), set()
    for p in parameters:
        if not isinstance(p, dict) or not p.get('name') or not p.get('column'):
            raise ValueError('Each parameter needs a name and source column.')
        if p['name'] in names or p['column'] in columns:
            raise ValueError('Parameter names and measurement columns must be distinct.')
        names.add(p['name']); columns.add(p['column'])
        unit_factor(p.get('unit'), p.get('standard_unit'))
        for field in ('lower', 'upper'):
            value = p.get(field)
            if value is not None and (not np.isfinite(value) or value < 0):
                raise ValueError(f"{p['name']}: {field} must be a finite, nonnegative limit.")
        if p.get('lower') is None and p.get('upper') is None:
            raise ValueError(f"{p['name']}: supply at least one limit.")
        if p.get('lower') is not None and p.get('upper') is not None and p['lower'] >= p['upper']:
            raise ValueError(f"{p['name']}: lower limit must be less than upper limit.")
        for field in ('weight', 'ideal'):
            if not np.isfinite(p.get(field, 0)):
                raise ValueError(f"{p['name']}: {field} must be finite.")
        if p.get('weight', 1) <= 0:
            raise ValueError(f"{p['name']}: weight must be positive; deselect excluded parameters.")
        if p.get('rating', 'ratio') not in ('ratio', 'ideal', 'two_sided'):
            raise ValueError('Choose ratio, ideal or two_sided quality rating.')
        for field in ('edition', 'source', 'verification', 'amendment', 'publication_year'):
            if not p.get(field):
                raise ValueError(f"{p['name']}: record the {field} for this limit.")
        if p['verification'] not in ('verified', 'unverified'):
            raise ValueError('Limit verification must be verified or unverified.')
    return deepcopy(parameters)


def prepare(frame, parameters):
    parameters = validate_parameters(parameters)
    if not isinstance(frame, pd.DataFrame) or frame.empty or not frame.columns.is_unique:
        raise ValueError('Import a non-empty dataset with unique columns.')
    values = pd.DataFrame(index=pd.RangeIndex(len(frame)))
    compliance, long = [], []
    for p in parameters:
        column, name = p['column'], p['name']
        if column not in frame:
            raise ValueError(f'Missing measurement column: {column}. Review parameter mappings.')
        raw = frame[column].reset_index(drop=True).replace(r'^\s*$', np.nan, regex=True)
        numeric = pd.to_numeric(raw, errors='coerce').astype(float)
        invalid = (raw.notna() & numeric.isna()) | np.isinf(numeric) | (numeric < 0)
        if p['standard_unit'] == 'pH':
            invalid |= numeric > 14
        if invalid.any():
            rows = ', '.join(str(i+1) for i in np.flatnonzero(invalid)[:10])
            raise ValueError(f'{column}: invalid or censored measurements in source rows {rows}. Resolve qualifiers explicitly; they are not zeros.')
        c = numeric.to_numpy() * unit_factor(p['unit'], p['standard_unit'])
        values[name] = c
        valid = np.isfinite(c)
        failed = valid & (((c < p['lower']) if p.get('lower') is not None else False)
                          | ((c > p['upper']) if p.get('upper') is not None else False))
        n = int(valid.sum())
        compliance.append(dict(parameter=name, assessed=n, meets=int((valid & ~failed).sum()),
                               exceeds=int(failed.sum()), unassessed=int((~valid).sum()),
                               meets_percent=100*(valid & ~failed).sum()/n if n else np.nan,
                               exceeds_percent=100*failed.sum()/n if n else np.nan,
                               lower=p.get('lower'), upper=p.get('upper'), unit=p['standard_unit'],
                               edition=p['edition'], source=p['source'], verification=p['verification']))
        long.extend(dict(source_row=i+1, parameter=name, concentration=c[i],
                         status='Unassessed' if not valid[i] else 'Exceeds' if failed[i] else 'Meets') for i in range(len(c)))
    return values, pd.DataFrame(compliance), pd.DataFrame(long), parameters


def ratings(values, parameters):
    result = pd.DataFrame(index=values.index)
    for p in parameters:
        c = values[p['name']].to_numpy()
        ideal, upper, lower = p.get('ideal', 0.), p.get('upper'), p.get('lower')
        rule = p.get('rating', 'ratio')
        if rule == 'ratio':
            if upper is None or upper <= 0:
                raise ValueError(f"{p['name']}: a ratio rating requires a positive upper standard.")
            q = 100*c/upper
        elif rule == 'two_sided':
            if lower is None or upper is None or not lower < ideal < upper:
                raise ValueError(f"{p['name']}: a two-sided rating requires lower < ideal < upper.")
            q = np.where(c >= ideal, 100*(c-ideal)/(upper-ideal), 100*(ideal-c)/(ideal-lower))
        else:
            standard = upper if upper is not None else lower
            if standard == ideal:
                raise ValueError(f"{p['name']}: the ideal cannot equal the rating standard.")
            if (upper is not None and ideal > upper) or (upper is None and ideal < lower):
                raise ValueError(f"{p['name']}: the ideal must be on the compliant side of the rating standard.")
            q = 100*(c-ideal)/(standard-ideal)
        result[p['name']] = q
    return result


def aggregate_arithmetic(frame, parameters, *, index, method, inverse=False, scheme=None):
    values, compliance, tests, parameters = prepare(frame, parameters)
    scheme = validate_scheme(scheme or SCHEMES['arithmetic' if inverse else 'relative'])
    if scheme['direction'] != 'lower':
        raise ValueError('Arithmetic indices use a lower-is-better classification direction.')
    q = ratings(values, parameters)
    if inverse:
        standards = np.array([p.get('upper') if p.get('upper') is not None else p['lower'] for p in parameters])
        if (standards <= 0).any():
            raise ValueError('Inverse-standard weights require positive rating standards.')
        weights = 1/standards
    else:
        weights = np.array([p.get('weight', 1.) for p in parameters], dtype=float)
    weights /= weights.sum()
    contributions = q.to_numpy()*weights
    complete = values.notna().all(axis=1).to_numpy()
    scores = contributions.sum(axis=1)  # NaNs propagate: never renormalize a partial sample.
    if not np.isfinite(scores[complete]).all():
        raise ValueError('The rating or index overflowed; check the measurement and limit magnitudes.')
    sample = pd.DataFrame({'source_row': np.arange(1, len(frame)+1), index: scores,
                           'classification': classify(scores, scheme), 'parameters_assessed': values.notna().sum(axis=1),
                           'parameters_required': len(parameters)})
    detail = tests.copy()
    # prepare() orders the audit rows by parameter, then by source row.
    detail['rating'] = q.to_numpy().T.ravel()
    detail['relative_weight'] = np.repeat(weights,len(frame))
    detail['contribution'] = detail.rating*detail.relative_weight
    standards = pd.DataFrame(parameters)
    standards['relative_weight'] = weights
    notes = ['Index values summarize selected parameters; they do not establish drinking-water safety or assess omitted hazards.',
             'Compliance percentages use the measured count for each parameter; missing counts are reported separately.']
    if (~complete).any():
        notes.append(f'{int((~complete).sum())} samples are unassessed because selected measurements are missing; weights were not renormalized.')
    if (q.to_numpy() < 0).any():
        notes.append('Signed ideal-value ratings produced negative subindices (for example pH below its ideal). This is the selected arithmetic convention; review the individual compliance results or explicitly select a two-sided rating.')
    unverified = [p['name'] for p in parameters if p['verification'] != 'verified']
    if unverified:
        notes.append('Unverified standard limits used: '+', '.join(unverified)+'. See parameter provenance before interpretation.')
    metadata = dict(index=index, methodology=method, formula='sum(relative_weight_i * quality_rating_i)',
                    rating_definitions={'ratio':'100*C/S', 'ideal':'100*(C-I)/(S-I)',
                        'two_sided':'100*(C-I)/(upper-I) above ideal; 100*(I-C)/(I-lower) below ideal'},
                    weighting='(1/S_i) / sum(1/S_i)' if inverse else 'w_i / sum(w_i)',
                    missing='complete selected parameter set; no partial-score renormalization',
                    parameters=parameters, classification_scheme=scheme, n_input=len(frame), n_assessed=int(complete.sum()))
    return IndexResult(sample, {'samples': sample, 'parameter_contributions': detail, 'compliance': compliance,
                                'standards': standards, 'classification_scheme': classification_table(scheme)}, metadata, notes)
