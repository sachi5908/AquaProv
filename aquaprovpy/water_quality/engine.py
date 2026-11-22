"""Calculation dispatch and source-row provenance for the water-quality workspace."""
from copy import deepcopy
import hashlib
import json

import numpy as np
import pandas as pd

from .wqi import weighted_arithmetic, groundwater_wqi, ccme_wqi
from .dwqi import drinking_water_index


METHODS = {
    # Retain the historical key so saved projects keep their selected method.
    'WQI': {'brown': 'Weighted arithmetic WQI (inverse-standard weights)',
            'ramakrishnaiah': 'Groundwater WQI (Ramakrishnaiah 2009)', 'ccme': 'CCME WQI 1.0 (2001)'},
    'DWQI': {'ramakrishnaiah': 'Weighted DWQI (Ramakrishnaiah approach)', 'custom': 'Custom weighted DWQI'},
}
VIEWS = {
    'spatial': '2D spatial distribution', 'surface': '3D surface', 'contour': 'Contour map',
    'classification': 'Classification zones', 'samples': 'Sampling points and values',
    'histogram': 'Histogram', 'box': 'Box plot', 'violin': 'Violin plot',
    'seasonal_maps': 'Seasonal comparison maps', 'seasonal_bars': 'Seasonal grouped bars',
    'seasonal_box': 'Seasonal box plots', 'compliance': 'Parameter compliance',
    'comparison': 'WQI and DWQI spatial comparison',
    'index_scatter': 'WQI versus DWQI scatter',
}
SPATIAL_VIEWS = {'spatial', 'surface', 'contour', 'classification', 'samples', 'seasonal_maps', 'comparison'}
SEASONAL_VIEWS = {'seasonal_maps', 'seasonal_bars', 'seasonal_box'}


def figure_title(index, view):
    return VIEWS[view] if view in ('comparison', 'index_scatter') else f'{index} · {VIEWS[view]}'


def calculate(frame, config, index=None):
    index = index or config.get('index', 'WQI')
    if index not in METHODS:
        raise ValueError('Choose WQI or DWQI.')
    profile = deepcopy(config['profiles'][index])
    method = profile['method']
    if method not in METHODS[index]:
        raise ValueError(f'Unsupported {index} methodology.')
    positions = np.arange(len(frame))
    if config.get('filter_season') is not None:
        column = config.get('season_column')
        if column not in frame:
            raise ValueError('Choose a season column before filtering.')
        positions = positions[frame[column].astype(str).eq(str(config['filter_season'])).to_numpy()]
    subset = frame.iloc[positions].copy()
    if subset.empty:
        raise ValueError('No observations match the selected season.')
    parameters = profile['parameters']
    scheme = profile['scheme']
    if index == 'DWQI':
        result = drinking_water_index(subset, parameters, custom=method == 'custom', scheme=scheme)
    elif method == 'ccme':
        result = ccme_wqi(subset, parameters, site_column=config.get('site_column'),
                          time_column=config.get('time_column'), period_column=config.get('season_column'), scheme=scheme)
    elif method == 'brown':
        result = weighted_arithmetic(subset, parameters, scheme=scheme)
    else:
        result = groundwater_wqi(subset, parameters, scheme=scheme)
    # Source rows are always positions in the original dataset, even with duplicate index labels.
    for table in result.tables.values():
        if 'source_row' in table:
            table['source_row'] = positions[table.source_row.to_numpy(dtype=int)-1]+1
    result.samples = result.tables['samples']
    source = frame.iloc[result.samples.source_row.to_numpy(dtype=int)-1]
    sample_column = config.get('site_column')
    result.samples['sample'] = (source[sample_column].astype(str).to_numpy()
                               if sample_column in frame else result.samples.source_row.astype(str))
    season_column = config.get('season_column')
    if season_column in frame:
        result.samples['season'] = source[season_column].to_numpy()
    else:
        result.samples['season'] = 'All observations'
    if method == 'ccme' and index == 'WQI':
        result.samples['sample'] = result.samples.site
        result.samples['season'] = result.samples.period
    result.metadata.update(engine_version='1.0',method_key=method, standard=profile.get('standard_name', 'User-defined'),
                           standard_id=profile.get('standard_id', 'custom'), limit_kind=profile.get('limit_kind', 'custom'),
                           classification_scheme=deepcopy(scheme), filter_season=config.get('filter_season'))
    from ..core.projects import encode_frame
    result.metadata['input_sha256'] = hashlib.sha256(json.dumps(encode_frame(frame), sort_keys=True, allow_nan=False).encode()).hexdigest()
    # Coupled WHO nitrate/nitrite objective is reported separately, not double-weighted.
    selected = {p['name']:p for p in parameters}
    if all(n in selected and selected[n].get('standard_id') == 'WHO-2026' for n in ('NO3','NO2')):
        from .common import unit_factor
        ratio = sum(pd.to_numeric(subset[selected[n]['column']], errors='coerce').to_numpy(dtype=float)
                    * unit_factor(selected[n]['unit'], selected[n]['standard_unit']) / selected[n]['upper'] for n in ('NO3','NO2'))
        result.tables['combined_nitrate_nitrite'] = pd.DataFrame({'source_row':positions+1,
            'sum_of_guideline_ratios':ratio, 'status':np.where(np.isfinite(ratio), np.where(ratio <= 1, 'Meets', 'Exceeds'), 'Unassessed')})
        result.warnings.append('WHO combined nitrate/nitrite attainment is reported separately as the sum of guideline ratios (must be ≤1). It is not an extra weighted index parameter.')
    return result
