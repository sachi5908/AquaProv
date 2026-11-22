"""Lossless SI imports, explicit exclusions, classifications and summaries."""
from dataclasses import dataclass
import re

import numpy as np
import pandas as pd

COMMON_MINERALS = ('Calcite', 'Dolomite', 'Gypsum', 'Anhydrite', 'Halite', 'Quartz',
                   'Fluorite', 'Goethite', 'Hematite')
CLASSES = ('Undersaturated', 'At equilibrium', 'Supersaturated')
CLASS_COLORS = ('#0072B2', '#808080', '#D55E00')
VIEWS = {'bar': 'SI bar plot', 'heatmap': 'SI heatmap', 'box': 'SI box plot',
         'violin': 'SI violin plot', 'distribution': 'Mineral saturation distribution',
         'scatter': 'SI scatter plot', 'map': 'SI sample map', 'interpolation': 'SI interpolated map'}
SPATIAL_VIEWS = {'map', 'interpolation'}


@dataclass
class SIResult:
    records: pd.DataFrame
    tables: dict
    metadata: dict
    warnings: list


def classify(values):
    """Exact mathematical classes; no rounding or hidden equilibrium tolerance."""
    values = np.asarray(values, dtype=float)
    result = np.full(values.shape, 'Unassessed', dtype=object)
    finite = np.isfinite(values)
    result[finite & (values < 0)] = CLASSES[0]
    result[finite & (values == 0)] = CLASSES[1]
    result[finite & (values > 0)] = CLASSES[2]
    return result


def numeric(series, name):
    values = pd.to_numeric(series, errors='coerce').astype(float)
    bad = series.notna() & series.astype(str).str.strip().ne('') & values.isna()
    if bad.any() or np.isinf(values).any():
        rows = (np.flatnonzero(bad | np.isinf(values)) + 1).tolist()
        raise ValueError(f'{name}: non-numeric, censored or infinite measurements at row(s) {rows[:12]}. '
                         'Resolve qualifiers explicitly; no automatic substitution is applied.')
    return values


def infer_si_columns(frame):
    result = {}
    for column in frame.columns:
        name = str(column).strip()
        match = re.match(r'^si[\s_:\-\[(]+(.+?)[\])]?$|^(.+?)[\s_:\-]+si$', name, re.I)
        mineral = (match.group(1) or match.group(2)).strip() if match else name
        if match and re.match(r'^(?:mg|ug|µg|μg|g|mmol|mol|meq)\s*/\s*L\b|^(?:ppm|ppb)\b',mineral,re.I):
            continue  # Si (mg/L) is dissolved silicon, not an SI result column.
        canonical = next((m for m in COMMON_MINERALS if m.casefold() == mineral.casefold()), None)
        if canonical or match:
            mineral = canonical or mineral
            if mineral in result:
                raise ValueError(f'Multiple SI columns identify {mineral}; map the intended column explicitly.')
            result[mineral] = column
    return result


def labels(frame, column=None):
    if column:
        if column not in frame:
            raise ValueError('The selected sample identifier column is absent.')
        values = frame[column]
        if values.isna().any() or values.astype(str).str.strip().eq('').any():
            raise ValueError('Sample identifiers must not be blank.')
        return values.astype(str).to_numpy()
    return np.array([f'Row {i}' for i in range(1, len(frame) + 1)])


def import_si(frame, config):
    samples = labels(frame, config.get('sample_column'))
    rows = []
    mineral_column, si_column = config.get('mineral_column'), config.get('si_column')
    if config.get('layout', 'wide') == 'long':
        if not mineral_column or not si_column or mineral_column == si_column or any(c not in frame for c in (mineral_column, si_column)):
            raise ValueError('Choose distinct mineral-name and SI columns for long-format output.')
        values = numeric(frame[si_column], si_column)
        for i, (mineral, value) in enumerate(zip(frame[mineral_column], values)):
            if pd.isna(mineral) or not str(mineral).strip():
                raise ValueError(f'Missing mineral name at source row {i + 1}.')
            mineral = str(mineral).strip()
            mineral = next((m for m in COMMON_MINERALS if m.casefold() == mineral.casefold()), mineral)
            rows.append(dict(source_row=i+1, sample=samples[i], mineral=mineral, SI=value))
    else:
        mapping = config.get('si_columns') or infer_si_columns(frame)
        if not mapping:
            raise ValueError('No SI columns found. Use headings such as si_Calcite or select long format.')
        for mineral, column in mapping.items():
            if column not in frame:
                raise ValueError(f'SI column {column} is absent.')
            for i, value in enumerate(numeric(frame[column], column)):
                rows.append(dict(source_row=i+1, sample=samples[i], mineral=mineral, SI=value))
    records = pd.DataFrame(rows)
    # USGS selected-output undefined SI is -999.999. Some tabular exports use -999.
    sentinel = records.SI.isin([-999.999, -999.0])
    records['status'] = np.where(sentinel, 'PHREEQC undefined SI sentinel',
                                 np.where(records.SI.isna(), 'Missing imported SI', 'Imported'))
    records.loc[sentinel, 'SI'] = np.nan
    records['classification'] = classify(records.SI)
    notes = ['Imported SI values are retained without recalculation. Database, temperature, activity model and '
             'original rounding cannot be verified from SI columns alone. A reported zero may reflect source rounding.']
    return SIResult(records, {}, dict(mode='import', database=config.get('import_database') or 'Unspecified by source',
                    calculation='Imported PHREEQC SI; source provenance supplied by user'), notes)


def summarize(records):
    rows = []
    for mineral, group in records.groupby('mineral', sort=False):
        values = group.SI.dropna()
        row = dict(mineral=mineral, n_total=len(group), n_assessed=len(values), n_missing=int(group.SI.isna().sum()),
                   mean=values.mean(), median=values.median(), sd=values.std(ddof=1), minimum=values.min(),
                   q25=values.quantile(.25), q75=values.quantile(.75), maximum=values.max())
        for label in CLASSES:
            count = int((group.classification == label).sum())
            row[label] = count
            row[label + ' (%)'] = 100 * count / len(values) if len(values) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def interpretations(summary):
    rows = []
    for _, s in summary.iterrows():
        n = int(s.n_assessed)
        if not n:
            text = 'No assessed SI values; no saturation conclusion is supported.'
        else:
            text = (f'{n} assessed observation(s); median SI {s["median"]:.3g}, range {s.minimum:.3g} to {s.maximum:.3g}. '
                    f'{int(s[CLASSES[0]])} undersaturated, {int(s[CLASSES[1]])} at equilibrium, '
                    f'{int(s[CLASSES[2]])} supersaturated. ')
            if s[CLASSES[2]]:
                text += 'Positive SI indicates thermodynamic precipitation potential, not proof of precipitation; kinetics and nucleation can inhibit it. '
            if s[CLASSES[0]]:
                text += 'Negative SI permits dissolution if the mineral is present and accessible; it does not establish mineral occurrence. '
            if s[CLASSES[1]]:
                text += 'Zero SI is equilibrium at the precision of the supplied result. '
            if s.mineral in ('Goethite', 'Hematite'):
                text += 'Iron-oxide SI is especially sensitive to Fe speciation, pe/Eh and the selected phase thermodynamics.'
        rows.append(dict(mineral=s.mineral, interpretation=text.strip()))
    return pd.DataFrame(rows)


def finalize(result, frame, config):
    result.records['source_index'] = frame.index.astype(str).to_numpy()[result.records.source_row.to_numpy()-1]
    records = result.records.copy()
    selected = config.get('minerals')
    if selected is not None:
        if not selected:
            raise ValueError('Select at least one mineral.')
        records = records[records.mineral.isin(selected)]
    group_column = config.get('group_column')
    if group_column:
        if group_column not in frame:
            raise ValueError('The selected group column is absent.')
        records['group'] = frame[group_column].fillna('(missing)').astype(str).to_numpy()[records.source_row.to_numpy()-1]
        if config.get('group_value') is not None:
            records = records[records.group == str(config['group_value'])]
    else:
        records['group'] = 'All samples'
    samples = config.get('samples')
    if samples is not None:
        records = records[records['sample'].isin(samples)]
    if records.empty:
        raise ValueError('No SI observations match the selected minerals, samples and group.')
    result.metadata.update(n_input_rows=len(frame), n_selected_observations=len(records),
                           source_row_definition='One-based position in the imported AquaProv dataset; source_index preserves the dataframe index',
                           classification='SI < 0: undersaturated; SI = 0: equilibrium; SI > 0: supersaturated',
                           definition='SI = log10(IAP / K(T)); dimensionless',
                           statistics='Sample SD (ddof=1); linear quartiles; class percentages exclude missing SI.')
    result.tables['all_saturation_indices'] = result.records.copy()
    result.records = records.reset_index(drop=True)
    result.tables['saturation_indices'] = result.records
    result.tables['mineral_statistics'] = summarize(result.records)
    if group_column:
        result.tables['group_statistics'] = pd.concat([summarize(g).assign(group=key)
            for key, g in result.records.groupby('group', sort=False)], ignore_index=True)
    result.tables['interpretations'] = interpretations(result.tables['mineral_statistics'])
    result.warnings += ['SI describes thermodynamic saturation for the selected database and conditions, not reaction rate or mineral abundance.',
                        'Statistics describe the selected observations; repeated samples and spatial dependence are not independent replication.']
    missing = result.records.SI.isna().sum()
    if missing:
        result.warnings.append(f'{missing} selected mineral observation(s) are unassessed; see status and n_missing in Results & methods.')
    return result
