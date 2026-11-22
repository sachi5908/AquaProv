"""Explicit measurement units, qualifiers and quality diagnostics.

Concentrations normalize to mg/L of the named species; EC to uS/cm.
Source cells are retained in a long table. No charge balancing or imputation.
"""

from dataclasses import dataclass
import re

import numpy as np
import pandas as pd

from ..ions import ions_WEIGHT, ions_CHARGE

WEIGHTS = dict(ions_WEIGHT, NO3=62.0049, F=18.9984, NH4=18.0385)
CHARGES = {k: abs(v) for k, v in ions_CHARGE.items()} | {'NO3': 1, 'F': 1, 'NH4': 1}
ANALYTES = tuple(WEIGHTS) + ('EC', 'TDS', 'pH', 'Alkalinity', 'Cr_total', 'Cr_VI', 'Ni', 'Fe', 'Mn')
CORE = ('Ca', 'Mg', 'Na', 'K', 'HCO3', 'CO3', 'Cl', 'SO4')


@dataclass
class Measurements:
    values: pd.DataFrame
    observations: pd.DataFrame
    samples: pd.DataFrame
    schema: dict
    warnings: list


def suggest_schema(frame):
    """Suggest field mappings for the user to review, including units and basis."""
    from ..core.data import HEADER_ALIASES
    original = frame.attrs.get('aquaprov', {}).get('original_headers', {})
    fields = {}
    aliases = {'ta': 'Alkalinity', 'alk': 'Alkalinity', 'alkalinity': 'Alkalinity',
               'crtotal': 'Cr_total', 'crvi': 'Cr_VI', 'cr6': 'Cr_VI'}
    for col in frame:
        heading = str(original.get(col, col))
        stem = re.sub(r'\s*\((?:mg/l|ppb|ug/l|µg/l|μg/l|meq/l|mmol/l|.*s/cm)\).*$', '', heading, flags=re.I)
        key = re.sub('[^a-z0-9]', '', stem.lower())
        known = {re.sub('[^a-z0-9]', '', a.lower()): a for a in ANALYTES}
        analyte = aliases.get(key, known.get(key))
        if analyte is None:
            # Existing desktop normalization has already removed ionic charges.
            normalized = HEADER_ALIASES.get(re.sub('[^a-z0-9]', '', heading.lower()), col)
            analyte = normalized if normalized in ANALYTES else None
        if analyte is None or analyte in fields:
            continue
        low = heading.lower()
        unit = ('pH' if analyte == 'pH' else
                ('mS/cm' if 'ms/cm' in low else 'dS/m' if 'ds/m' in low else 'uS/cm') if analyte == 'EC' else
                'ug/L' if any(x in low for x in ('ppb', 'ug/l', 'µg/l', 'μg/l')) else
                'meq/L' if 'meq/l' in low else 'mmol/L' if 'mmol/l' in low else 'mg/L')
        fields[analyte] = {'column': col, 'unit': unit,
                           'basis': 'CaCO3' if analyte == 'Alkalinity' else 'species'}
    metadata = {}
    for key, candidates in {
        'sample': ('Sample', 'Sl. No.', 'Village', 'ShortID', 'Well', 'ID'),
        'well': ('Well', 'ShortID', 'ID'),
        'time': ('Date', 'Sampling date', 'Sampling year', 'SY'),
        'season': ('Sampling season', 'SM'),
        'x': ('Longitude', 'Longitude (°E)', 'Longitude (�E)', 'X'),
        'y': ('Latitude', 'Latitude (°N)', 'Latitude (�N)', 'Y'),
        'depth': ('Depth',), 'aquifer': ('Aquifer',),
    }.items():
        metadata[key] = next((c for c in candidates if c in frame), None)
    return {'version': 1, 'fields': fields, 'metadata': metadata,
            'crs': 'unspecified', 'unit_assumptions_confirmed': False}


def factor(analyte, unit, basis='species'):
    if analyte not in ANALYTES:
        raise ValueError(f'Unsupported analyte: {analyte}')
    if analyte == 'pH':
        if unit != 'pH' or basis != 'species':
            raise ValueError('pH requires unit pH and basis species.')
        return 1.0
    if analyte == 'EC':
        if unit not in ('uS/cm', 'mS/cm', 'dS/m') or basis != 'species':
            raise ValueError('EC requires uS/cm, mS/cm or dS/m, basis species.')
        return 1.0 if unit == 'uS/cm' else 1000.0
    if basis == 'N':
        if analyte not in ('NO3', 'NH4') or unit not in ('mg/L', 'ug/L'):
            raise ValueError('As-N conversion requires NO3/NH4 and a mass concentration unit.')
        return WEIGHTS[analyte] / 14.0067 * (0.001 if unit == 'ug/L' else 1)
    if basis == 'CaCO3':
        if analyte != 'Alkalinity' or unit not in ('mg/L', 'ug/L'):
            raise ValueError('CaCO3 basis is supported only for mass-based alkalinity.')
        return .001 if unit == 'ug/L' else 1.0
    if basis != 'species' or analyte == 'Alkalinity':
        raise ValueError('Specify species basis, or CaCO3 for alkalinity; do not treat alkalinity as HCO3.')
    if unit in ('mg/L', 'ug/L'):
        return .001 if unit == 'ug/L' else 1.0
    if analyte not in WEIGHTS:
        raise ValueError(f'{analyte}: use mg/L or ug/L.')
    if unit == 'meq/L':
        return WEIGHTS[analyte] / CHARGES[analyte]
    if unit == 'mmol/L':
        return WEIGHTS[analyte]
    raise ValueError(f'Unsupported unit: {unit}')


def parse_cell(raw, limit=None, qualifier=None):
    """Return the value, measurement status and detection bound.

    A nondetect without a known limit stays unresolved.
    """
    text = '' if pd.isna(raw) else str(raw).strip()
    q = '' if qualifier is None or pd.isna(qualifier) else str(qualifier).strip().lower()
    bound = np.nan
    if limit is not None and not pd.isna(limit) and str(limit).strip():
        try:
            bound = float(limit)
        except (ValueError, TypeError):
            return np.nan, 'invalid_limit', np.nan
        if not np.isfinite(bound) or bound <= 0:
            return np.nan, 'invalid_limit', np.nan
    match = re.fullmatch(r'\s*(<=|<|≤|>=|>|≥)\s*([+\-\d.eE]+)\s*', text)
    if match:
        try:
            value = float(match[2])
        except ValueError:
            return np.nan, 'invalid', bound
        if not np.isfinite(value) or value <= 0:
            return np.nan, 'invalid_limit', bound
        return np.nan, 'left_censored' if match[1] in ('<', '<=', '≤') else 'right_censored', value
    if text.lower() in ('nd', 'n.d.', 'bdl', 'b.d.l.', 'non-detect', '<dl') or q in ('nd', '<', '<=', 'u', 'bdl'):
        return np.nan, 'left_censored' if np.isfinite(bound) else 'nondetect_unknown_limit', bound
    if q in ('>', '>='):
        return np.nan, 'right_censored', bound
    if not text or text.lower() in ('na', 'nan', 'n/a', 'null', '-'):
        return np.nan, 'missing', bound
    if q not in ('', '=', 'detected'):
        return np.nan, 'unsupported_qualifier', bound
    try:
        value = float(text)
    except ValueError:
        return np.nan, 'invalid', bound
    if not np.isfinite(value) or value < 0:
        return np.nan, 'invalid', bound
    return value, 'zero' if value == 0 else 'detected', bound


def prepare(frame, schema):
    if frame is None or frame.empty or not frame.columns.is_unique:
        raise ValueError('Import a non-empty dataset with unique column names.')
    if schema.get('version') != 1 or not isinstance(schema.get('fields'), dict) or not schema['fields']:
        raise ValueError('Define at least one measurement mapping (schema version 1).')
    columns = [v.get('column') for v in schema['fields'].values()]
    if len(set(columns)) != len(columns):
        raise ValueError('A source measurement column cannot map to multiple analytes.')
    records, warnings = [], []
    samples = pd.DataFrame({'row': np.arange(1, len(frame) + 1), 'source_index': frame.index.astype(str)})
    for key, col in schema.get('metadata', {}).items():
        if col:
            if col not in frame:
                raise ValueError(f'Metadata column not found: {col}')
            samples[key] = frame[col].to_numpy()
    if 'sample' not in samples:
        samples['sample'] = samples['row'].astype(str)
    values = pd.DataFrame(index=pd.RangeIndex(len(frame)))
    for analyte, field in schema['fields'].items():
        col = field['column']
        for name in ('column', 'sd_column', 'limit_column', 'qualifier_column', 'followup_relative_sd_column'):
            if field.get(name) and field[name] not in frame:
                raise ValueError(f'Column not found: {field[name]}')
        conversion = factor(analyte, field['unit'], field.get('basis', 'species'))
        nums = []
        for i, raw in enumerate(frame[col]):
            def get(name, default=None):
                return frame[field[name]].iloc[i] if field.get(name) else field.get(name.replace('_column', ''), default)
            num, status, limit = parse_cell(raw, get('limit_column'), get('qualifier_column'))
            sd_raw = get('sd_column')
            sd = np.nan
            if sd_raw is not None and not pd.isna(sd_raw) and str(sd_raw).strip():
                try:
                    sd = float(sd_raw) * conversion
                except (ValueError, TypeError):
                    raise ValueError(f'{analyte} row {i + 1}: SD must be numeric.')
                if not np.isfinite(sd) or sd < 0:
                    raise ValueError(f'{analyte} row {i + 1}: SD must be finite and nonnegative.')
            followup = get('followup_relative_sd_column', np.nan)
            followup = np.nan if followup is None or pd.isna(followup) else float(followup)
            if not np.isnan(followup) and (not np.isfinite(followup) or followup <= 0):
                raise ValueError('Follow-up relative SD must be positive and finite.')
            nums.append(num * conversion)
            records.append({'row': i + 1, 'analyte': analyte, 'source_column': col,
                            'raw_value': None if pd.isna(raw) else str(raw), 'status': status,
                            'raw_limit': str(get('limit_column')) if get('limit_column') is not None else None,
                            'raw_qualifier': str(get('qualifier_column')) if get('qualifier_column') is not None else None,
                            'raw_sd': str(sd_raw) if sd_raw is not None else None,
                            'followup_relative_sd': followup,
                            'source_unit': field['unit'], 'source_basis': field.get('basis', 'species'),
                            'conversion_factor': conversion, 'value': num * conversion,
                            'limit': limit * conversion, 'sd': sd,
                            'canonical_unit': 'pH' if analyte == 'pH' else 'uS/cm' if analyte == 'EC' else 'mg/L',
                            'canonical_basis': 'CaCO3' if analyte == 'Alkalinity' else 'species'})
        values[analyte] = nums
    if not schema.get('unit_assumptions_confirmed', False):
        warnings.append('Units/bases are suggested mappings, not verified laboratory metadata. Confirm before interpretation.')
    if any('ppb' in str(c).lower() for c in frame):
        warnings.append('Aqueous ppb headings are suggested as ug/L; confirm the source uses this concentration convention.')
    warnings.append('Reported zeros remain zeros; verify whether laboratory zeros actually represent non-detects.')
    return Measurements(values, pd.DataFrame(records), samples, schema, warnings)


def quality_tables(m, *, balance_tolerance=5.0):
    if not np.isfinite(balance_tolerance) or not 0 < balance_tolerance <= 100:
        raise ValueError('Charge-balance tolerance must be in (0,100].')
    v = m.values
    summary = m.observations.groupby(['analyte', 'status']).size().rename('count').reset_index()
    qa = m.samples.copy()
    qa['available_major_ions'] = v.reindex(columns=CORE).notna().sum(axis=1).to_numpy()
    qa['complete_major_ions'] = qa['available_major_ions'] == len(CORE)
    eq = v.reindex(columns=CORE).copy()
    for ion in CORE:
        eq[ion] *= CHARGES[ion] / WEIGHTS[ion]
    c = eq[['Ca', 'Mg', 'Na', 'K']].sum(axis=1, min_count=4)
    a = eq[['HCO3', 'CO3', 'Cl', 'SO4']].sum(axis=1, min_count=4)
    qa['cation_meq_L'], qa['anion_meq_L'] = c.to_numpy(), a.to_numpy()
    qa['major_ion_CBE_percent'] = (100 * (c - a) / (c + a).where(c + a > 0)).to_numpy()
    qa['balance_review'] = qa['major_ion_CBE_percent'].abs() > balance_tolerance
    # Nitrate and fluoride can matter in contaminated waters; export a second,
    # explicitly separate diagnostic when both have been measured.
    extra = v.reindex(columns=['NO3', 'F']).copy()
    for ion in extra:
        extra[ion] *= CHARGES[ion] / WEIGHTS[ion]
    extended_a = a + extra.sum(axis=1, min_count=2)
    qa['CBE_with_NO3_F_percent'] = (100 * (c - extended_a) / (c + extended_a).where(c + extended_a > 0)).to_numpy()
    qa['duplicate_chemistry'] = v.duplicated(keep=False).to_numpy()
    keys = [k for k in ('well', 'time', 'season', 'depth') if k in qa]
    qa['repeated_record_key'] = qa.duplicated(keys, keep=False) if keys else False
    qa['pH_outside_0_14'] = ((v.get('pH', pd.Series(np.nan, index=v.index)) > 14)).to_numpy()
    issues = m.observations[~m.observations.status.isin(['detected', 'zero'])].copy()
    return {'quality_by_sample': qa, 'measurement_status': summary, 'observations': m.observations,
            'normalized_measurements': pd.concat([m.samples[['row', 'sample']], v], axis=1), 'flagged_observations': issues}
