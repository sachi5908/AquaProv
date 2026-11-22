"""Run assessment analyses and assemble their tables, metadata and plots."""

import hashlib
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .._publication import PlotResult, STYLE, close_on_error
from ..core.projects import encode_frame
from . import ENGINE_VERSION
from .measurements import prepare, quality_tables
from .uncertainty import propagate, compare_scenarios, WHO_SCREENING
from .robustness import compositional, well_inference
from .spatial import spatial_validation

VIEWS = {
    'qa': 'Measurement quality & charge balance',
    'uncertainty': 'SAR & classification uncertainty',
    'piper': 'Piper composition intervals',
    'screening': 'Chemical threshold probabilities',
    'priorities': 'Follow-up assay priorities',
    'scenarios': 'Sensitivity across analysis choices',
    'coda': 'Compositional PCA',
    'stability': 'Compositional cluster stability',
    'spatial': 'Spatial validation & variogram',
    'spatial_map': 'Fitted kriging & conditional uncertainty',
    'wells': 'Well bootstrap & descriptive trends',
}


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def code_fingerprint():
    if getattr(sys, 'frozen', False):
        # The build embeds source hashes in its Python archive. Frozen apps do
        # not carry loose .py files, but assessment replay still needs provenance.
        from aquaprov_build_info import SOURCE_SHA256
        return dict(SOURCE_SHA256)
    root = Path(__file__).resolve().parents[2]
    files = list((root/'aquaprovpy').rglob('*.py'))
    # A pip installation has package launchers, but no checkout-level main.py.
    # Only fingerprint that launcher when this is an AquaProv source checkout.
    launcher = root / 'main.py'
    if launcher.is_file() and (root / 'pyproject.toml').is_file():
        files.append(launcher)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def select_records(frame, config):
    keep = np.ones(len(frame), dtype=bool)
    reasons = np.full(len(frame), '', dtype=object)
    column = config.get('filter_column')
    if column:
        if column not in frame:
            raise ValueError('Selection column is not in the dataset.')
        text = str(config.get('filter_value', '')).strip()
        match = frame[column].astype(str).str.strip() == text
        try:
            match |= pd.to_numeric(frame[column], errors='coerce') == float(text)
        except ValueError:
            pass
        keep &= match.to_numpy()
        reasons[~keep] = f'Outside selected {column} = {text}'
    if config.get('one_per_well', False):
        col = config['schema'].get('metadata', {}).get('well')
        if not col or col not in frame:
            raise ValueError('Map a well identifier before selecting one record per well.')
        ids = frame[col]
        available = ids.notna() & (ids.astype(str).str.strip() != '')
        reasons[keep & ~available.to_numpy()] = 'Missing well identifier'
        keep &= available.to_numpy()
        positions = np.flatnonzero(keep)
        duplicates = ids.iloc[positions].duplicated(keep='first').to_numpy()
        reasons[positions[duplicates]] = 'One-per-well selection: later source record'
        keep[positions[duplicates]] = False
    if not keep.any():
        raise ValueError('No records match the selected subset.')
    positions = np.flatnonzero(keep)
    excluded = pd.DataFrame({'input_row': np.flatnonzero(~keep)+1, 'source_index': frame.index[~keep].astype(str), 'reason': reasons[~keep]})
    return frame.iloc[positions].copy(), positions+1, excluded


def compute(frame, config, *, artifacts=None):
    allowed = {'chart_appearance', 'chart', 'chart_color', 'chart_size', 'chart_marker', 'schema', 'view', 'draws', 'seed', 'relative_sd', 'uncertainty', 'censoring', 'profile',
               'budget', 'assay_cost', 'balance_tolerance', 'columns', 'clusters', 'resamples', 'column',
               'coordinates', 'folds', 'model', 'threshold', 'error_correlation',
               'filter_column', 'filter_value', 'one_per_well', 'censor_models', 'priority_method', 'followup_relative_sd',
               'source_crs','target_crs','boundary','samples_inside_boundary','extrapolate','power','neighbors',
               'resolution','cell_size','levels','classification','class_breaks','surface_drawing','map_output','map_legend',
               'map_layout','show_samples','show_colorbar','colorbar_orientation','colorbar_options','show_grid',
               'grid_spacing','north_arrow','north_reference','contour_lines','contour_labels','line_width','line_color','opacity'}
    if not isinstance(config, dict) or set(config)-allowed:
        raise ValueError('Unknown assessment settings: '+', '.join(sorted(set(config)-allowed)))
    view = config.get('view', 'qa')
    if view not in VIEWS:
        raise ValueError('Unknown assessment view.')
    selected, input_rows, exclusions = select_records(frame, config)
    m = prepare(selected, config['schema'])
    row_map = dict(enumerate(input_rows, 1))
    m.observations['row'] = m.observations.row.map(row_map)
    m.samples['row'] = input_rows
    tables = quality_tables(m, balance_tolerance=config.get('balance_tolerance', 5))
    tables['selection_exclusions'] = exclusions
    warnings = list(m.warnings)
    if view in ('uncertainty', 'piper', 'screening', 'priorities'):
        opts = {k: config[k] for k in ('draws', 'seed', 'relative_sd', 'uncertainty', 'censoring', 'profile', 'budget', 'assay_cost', 'error_correlation', 'censor_models', 'priority_method', 'followup_relative_sd') if k in config}
        extra, warnings = propagate(m, **opts)
        tables.update(extra)
    elif view == 'scenarios':
        opts = {k: config[k] for k in ('draws', 'seed', 'relative_sd', 'profile', 'error_correlation') if k in config}
        extra, notes = compare_scenarios(m, **opts)
        tables.update(extra)
        warnings += notes
    elif view in ('coda', 'stability'):
        extra, notes = compositional(m, config.get('columns', []), clusters=config.get('clusters', 3),
                                    resamples=config.get('resamples', 100) if view == 'stability' else 0,
                                    seed=config.get('seed', 42))
        tables.update(extra)
        warnings += notes
    elif view in ('spatial', 'spatial_map'):
        opts = {k: config[k] for k in ('coordinates', 'folds', 'seed', 'model', 'threshold', 'source_crs', 'target_crs', 'boundary', 'samples_inside_boundary', 'power', 'neighbors') if k in config}
        extra, notes = spatial_validation(m, config.get('column'), **opts)
        tables.update(extra)
        warnings += notes
        if view == 'spatial_map':
            from ..modules.maps.interpolation import interpolate
            from scipy.stats import norm
            source = tables['spatial_predictions'][['x','y','observed']].rename(columns={'observed':'value'})
            parameters = tables['full_data_variogram'].iloc[0]
            projection = tables['spatial_coordinate_system'].iloc[0].to_dict()
            map_boundary = config.get('boundary')
            if map_boundary is not None:
                from ..boundaries import make_boundary, geometry_in_crs
                declared = 'EPSG:4326' if config.get('coordinates','wgs84') in ('wgs84','auto_utm','wgs84_projected') else projection['analysis_crs']
                map_boundary = make_boundary(geometry_in_crs(map_boundary,projection['analysis_crs'],declared_local_crs=declared),
                    projection['analysis_crs'],name=map_boundary.get('name','Study area'))
            grid = interpolate(source, 'x', 'y', 'value', coordinates='projected',
                               source_crs=projection['analysis_crs'], boundary=map_boundary,
                               extrapolate=config.get('extrapolate',False),
                               model=config.get('model', 'spherical'), range_=parameters['range_'],
                               sill=parameters.sill, nugget=parameters.nugget,
                               resolution=config.get('resolution',70),cell_size=config.get('cell_size'))
            grid.metadata.update(input_coordinates=config.get('coordinates','wgs84'),coordinate_conversion=projection,
                parameters='full-data fitted variogram; separate training-only fits for holdouts')
            if artifacts is not None:
                artifacts['fitted_grid'] = grid
            table = pd.DataFrame({'x': grid.x.ravel(), 'y': grid.y.ravel(),
                                  'prediction': grid.values.ravel(), 'conditional_variance': grid.variance.ravel(),
                                  'inside_boundary': grid.inside_boundary.ravel(),
                                  'inside_sample_hull': grid.inside_sample_hull.ravel()})
            table['extrapolated'] = table.prediction.notna() & ~table.inside_sample_hull
            tables['fitted_grid_settings'] = pd.DataFrame([dict(analysis_crs=projection['analysis_crs'],
                rows=grid.x.shape[0],columns=grid.x.shape[1],cell_size=grid.metadata['cell_size'],mask=grid.metadata['mask'])])
            if config.get('threshold') is not None:
                sd = np.sqrt(table.conditional_variance.to_numpy())
                with np.errstate(divide='ignore', invalid='ignore'):
                    probability = norm.sf((config['threshold']-table.prediction)/sd)
                deterministic = (sd == 0) & np.isfinite(table.prediction)
                probability[deterministic] = (table.prediction[deterministic] > config['threshold']).astype(float)
                table['conditional_exceedance_probability'] = probability
            tables['fitted_grid'] = table
            warnings.append('Map uses the full-data fitted variogram and the grid/mask settings exported in fitted_grid_settings. Holdout scores use separate training-only fits. Probabilities are conditional Gaussian calculations, not validated regulatory boundaries.')
            if config.get('extrapolate'):
                warnings.append('Full-boundary coverage includes extrapolation beyond the sample convex hull; these cells are flagged in fitted_grid.')
    elif view == 'wells':
        extra, notes = well_inference(m, config.get('column'), resamples=config.get('resamples', 2000), seed=config.get('seed', 42))
        tables.update(extra)
        warnings += notes
    warnings += ['Charge balance is a diagnostic, not an automatic acceptance filter; missing ions prevent a complete major-ion balance.',
                 'Duplicate chemistry or record keys are review flags, not proof of laboratory replicates.']
    metadata = {'analysis': VIEWS[view], 'engine_version': ENGINE_VERSION, 'n_input': len(frame), 'n_selected': len(selected),
                'config': config, 'input_sha256': digest(encode_frame(frame)), 'code_sha256': code_fingerprint(),
                'source_provenance': frame.attrs.get('aquaprov', {}),
                'threshold_profile': config.get('profile', WHO_SCREENING) if view in ('uncertainty', 'piper', 'screening', 'priorities') else None}
    return tables, metadata, warnings


def empty(ax, message):
    ax.text(.5, .5, message, ha='center', va='center', wrap=True, transform=ax.transAxes)
    ax.set_axis_off()


def intervals_plot(ax, table, title, ylabel):
    if table.empty:
        empty(ax, 'No assessable observations. Review mappings, missing ions, censoring and SD requirements.')
        return
    shown = table.head(60)
    x = np.arange(len(shown))
    ax.errorbar(x, shown['median'], yerr=[shown['median']-shown.lower, shown.upper-shown['median']],
                fmt='.', capsize=2, color='#007c83', ecolor='#72a9ac', label='Median and 95% interval')
    ax.set(title=title+(' (first 60 rows)' if len(table) > 60 else ''), xlabel='Source data row', ylabel=ylabel)
    if len(shown) <= 25:
        ax.set_xticks(x, shown.row.astype(str), rotation=70)
    else:
        pick = np.linspace(0, len(shown)-1, 12).astype(int)
        ax.set_xticks(pick, shown.row.iloc[pick].astype(str), rotation=70)
    ax.grid(axis='y', alpha=.15)


@close_on_error
def plot(frame, config):
    from ..core.progress import progress_stage, report_progress
    with progress_stage(0, 75, 'Computing assessment'):
        artifacts = {}
        tables, metadata, warnings = compute(frame, config, artifacts=artifacts)
    report_progress(78, 'Building assessment figure')
    view = config.get('view', 'qa')
    units = tables['observations'].drop_duplicates('analyte').set_index('analyte').canonical_unit
    if config.get('chart', 'Dashboard') != 'Dashboard':
        from .charts import chart
        return PlotResult(chart(tables, config), tables, metadata, warnings)
    value_unit = units.get(config.get('column'), 'measurement units')
    if view == 'spatial_map':
        from .maps import fitted_map
        with plt.rc_context(STYLE):
            fig = fitted_map(artifacts['fitted_grid'],config,value_unit,tables,metadata)
        return PlotResult(fig,tables,metadata,warnings)
    with plt.rc_context(STYLE):
        if view == 'piper':
            fig, axes = plt.subplots(1, 3, figsize=(13, 5), layout='constrained')
        else:
            fig, axes = plt.subplots(1, 2, figsize=(12, 5.7), layout='constrained')
        left, right = axes[:2]
        if view == 'qa':
            q = tables['quality_by_sample']
            valid = q.major_ion_CBE_percent.notna()
            if valid.any():
                left.scatter(q.loc[valid, 'row'], q.loc[valid, 'major_ion_CBE_percent'], s=12,
                             c=np.where(q.loc[valid, 'balance_review'], '#c44d36', '#007c83'))
                from ..plot_legends import add_legend_entries
                from matplotlib.lines import Line2D
                add_legend_entries(left, [Line2D([], [], marker='o', lw=0, color=color, label=label)
                                          for color, label in [('#007c83', 'Within tolerance'), ('#c44d36', 'Exceeds tolerance')]])
                tol = config.get('balance_tolerance', 5)
                left.axhspan(-tol, tol, alpha=.1, color='green', label=f'Tolerance band (±{tol:g}%)')
                left.axhline(0, color='grey', lw=.8, label='Zero charge balance')
                left.set(xlabel='Source data row', ylabel='Major-ion CBE (%)', title='Charge-balance review')
            else:
                empty(left, 'No complete eight-ion balances. Review the missing-ion and qualifier tables.')
            counts = tables['measurement_status'].groupby('status')['count'].sum().sort_values()
            right.barh(counts.index, counts.values, color='#007c83', label='Measurement status counts')
            right.set(xlabel='Observation count', title='Measurement status')
        elif view == 'uncertainty':
            t = tables['metric_intervals']
            for ax, metric, ylabel in [(left, 'SAR', 'SAR'), (right, 'Na_percent', 'Na (%)')]:
                subset = t[t.metric == metric] if 'metric' in t else pd.DataFrame()
                intervals_plot(ax, subset, metric+' · conditional 95% intervals', ylabel)
        elif view == 'piper':
            t = tables['metric_intervals']
            for ax, part, title in zip(axes, ['cation', 'anion', 'diamond'], ['Cations: Ca / Mg / Na+K', 'Anions: HCO3+CO3 / SO4 / Cl', 'Piper diamond']):
                if 'metric' not in t:
                    empty(ax, 'No complete Piper observations.')
                    continue
                x = t[t.metric == f'Piper_{part}_x'].set_index('row')
                y = t[t.metric == f'Piper_{part}_y'].set_index('row')
                if x.empty:
                    empty(ax, 'Piper requires eight measured major ions.')
                    continue
                x, y = x.head(150), y.loc[x.head(150).index]
                ax.errorbar(x['median'], y['median'], xerr=[x['median']-x.lower, x.upper-x['median']],
                            yerr=[y['median']-y.lower, y.upper-y['median']], fmt='.', alpha=.45, ms=4, label='Median and marginal 95% intervals')
                outline = np.array([[0, 0], [1, 0], [.5, np.sqrt(3)/2], [0, 0]]) if part != 'diamond' else np.array([[0, np.sqrt(3)/2], [.5, 0], [1, np.sqrt(3)/2], [.5, np.sqrt(3)], [0, np.sqrt(3)/2]])
                ax.plot(*outline.T, color='#45616a', lw=1, label='Piper domain')
                ax.set(title=title, aspect='equal', xlabel='Normalized Piper x', ylabel='Normalized Piper y')
            warnings.append('Piper plot shows the first 150 assessable rows; error bars are marginal 95% intervals, not joint confidence regions. Tables include every row.')
        elif view in ('screening', 'priorities'):
            t = tables['threshold_probabilities'] if view == 'screening' else tables['assay_priorities']
            if 'probability' not in t or t.empty:
                empty(left, 'No threshold probabilities can be assessed.')
                empty(right, 'Review unassessed chemicals and uncertainty settings.')
            else:
                shown = t.dropna(subset=['probability']).head(30).iloc[::-1]
                labels = shown.row.astype(str)+' / '+shown.analyte
                left.barh(labels, shown.probability, color='#007c83', label='Exceedance probability')
                left.axvline(.5, color='grey', lw=.8, ls='--', label='Probability = 0.5')
                left.set(xlim=(0, 1), xlabel='Conditional P(value > threshold)', title='Threshold screening (up to 30 assays)')
                left.tick_params(axis='y', labelsize=7)
                if view == 'priorities':
                    right.barh(labels, shown.priority_score, color=np.where(shown.selected_for_review, '#c37b27', '#aac0c3'))
                    from ..plot_legends import add_legend_entries
                    from matplotlib.patches import Patch
                    add_legend_entries(right, [Patch(facecolor='#c37b27', label='Within assay budget'),
                                               Patch(facecolor='#aac0c3', label='Outside assay budget')])
                    evsi = config.get('priority_method') == 'evsi'
                    right.set(xlabel='Expected error reduction / assay cost' if evsi else 'min(P, 1 − P) / assay cost',
                              title=('Expected assay value' if evsi else 'Ambiguity priority')+' · gold = within budget')
                    right.tick_params(axis='y', labelsize=7)
                else:
                    assessable = tables['threshold_probabilities'].dropna(subset=['probability'])
                    right.hist(assessable.probability, bins=np.linspace(0, 1, 11), color='#66a6aa', label='Assay frequency')
                    right.set(xlabel='Conditional exceedance probability', ylabel='Assay count', title='Decision ambiguity')
        elif view == 'scenarios':
            t = tables['scenario_conclusions']
            counts = t.conclusion.value_counts()
            left.barh(counts.index, counts.values, color='#007c83', label='Scenario conclusion counts')
            left.set(xlabel='Assay count', title='Robustness across four scenarios')
            shown = t.dropna(subset=['minimum_probability']).head(40)
            if len(shown):
                x = np.arange(len(shown))
                right.vlines(x, shown.minimum_probability, shown.maximum_probability, color='#c37b27', lw=2, label='Probability range across scenarios')
                right.scatter(x, shown.minimum_probability, s=12, color='#007c83', label='Minimum scenario probability')
                right.set(ylim=(-.05, 1.05), xlabel='Assessable assay index (first 40)', ylabel='Probability range across scenarios', title='Assumption sensitivity')
            else:
                empty(right, 'No assessable threshold scenarios.')
        elif view in ('coda', 'stability'):
            t = tables['coda_scores']
            cluster_points = left.scatter(t.PC1, t.PC2, c=t.cluster, cmap='tab10', s=18, alpha=.7)
            cluster_points._aquaprov_fixed_cmap = True
            from ..plot_legends import add_legend_entries
            from matplotlib.lines import Line2D
            add_legend_entries(left, [Line2D([], [], marker='o', lw=0,
                                            color=cluster_points.get_cmap()(cluster_points.norm(cluster)),
                                            label=f'Cluster {cluster}') for cluster in sorted(t.cluster.unique())])
            v = tables['coda_variance'].fraction
            left.set(xlabel=f'PC1 ({v.iloc[0]:.1%})', ylabel=f'PC2 ({v.iloc[1]:.1%})', title='ILR PCA · Ward clusters')
            if view == 'stability':
                matrix = tables['cluster_coassignment'].to_numpy()
                order = np.argsort(t.cluster.to_numpy(), kind='stable')
                im = right.imshow(matrix[order][:, order], vmin=0, vmax=1, cmap='viridis', aspect='auto')
                right.set(title='Bootstrap cluster co-assignment', xlabel='Rows ordered by original cluster', ylabel='Rows ordered by original cluster')
                fig.colorbar(im, ax=right, label='Co-assignment frequency')
                from ..plot_legends import scale_legend
                scale_legend(right, im, 'Co-assignment frequency')
            else:
                right.bar(np.arange(1, len(v)+1), v*100, color='#007c83', label='Explained compositional variance')
                right.set(xlabel='Principal component', ylabel='Variance (%)', title='Compositional variance')
        elif view == 'spatial':
            t = tables['spatial_predictions']
            fold_points = left.scatter(t.observed, t.prediction, c=t.fold, cmap='tab10', s=22)
            fold_points._aquaprov_fixed_cmap = True
            from ..plot_legends import add_legend_entries
            from matplotlib.lines import Line2D
            add_legend_entries(left, [Line2D([], [], marker='o', lw=0,
                                            color=fold_points.get_cmap()(fold_points.norm(fold)),
                                            label=f'Held-out block {fold}') for fold in sorted(t.fold.unique())])
            limits = [min(t.observed.min(), t.prediction.min()), max(t.observed.max(), t.prediction.max())]
            left.plot(limits, limits, color='grey', ls='--', label='Identity line (y = x)')
            left.set(xlabel=f'Held-out observation ({value_unit})', ylabel=f'Training-only prediction ({value_unit})', title='Spatial block validation')
            v = tables['empirical_variogram']
            right.scatter(v.distance, v.semivariance, s=np.sqrt(v.pairs)*8, label='Empirical semivariance')
            right.plot(v.distance, v.fitted, color='#c37b27', label='Fitted variogram')
            right.set(xlabel='Distance (m)' if config.get('coordinates') in ('wgs84','auto_utm','wgs84_projected') else 'Source distance units',
                      ylabel=f'Semivariance ({value_unit})²', title='Full-data variogram · diagnostic only')
        elif view == 'wells':
            t = tables['well_summaries']
            left.hist(t['mean'], bins=min(25, max(3, len(t)//3)), color='#007c83', label='Well mean frequency')
            b = tables['well_bootstrap'].iloc[0]
            left.axvline(b.equal_well_mean, color='#c37b27', label='Equal-well mean')
            left.axvspan(b.lower_95, b.upper_95, color='#c37b27', alpha=.15, label='95% bootstrap interval')
            left.set(xlabel=f"{config.get('column')} ({value_unit})", ylabel='Well count', title='Well means & 95% bootstrap interval')
            trends = tables.get('within_well_trends', pd.DataFrame())
            if 'sen_slope' in trends:
                right.hist(trends.sen_slope.dropna(), bins=15, color='#66a6aa', label='Within-well slope frequency')
                right.set(xlabel='Descriptive within-well slope', ylabel='Well count', title='Theil–Sen trends')
            else:
                right.bar(np.arange(len(t)), t['count'], color='#66a6aa', label='Measurements per well')
                right.set(xlabel='Well index', ylabel='Measurement count', title='Unequal sampling intensity')
        title = VIEWS[view]
        if view in ('uncertainty', 'piper', 'screening', 'priorities'):
            title += ' · ' + {'fixed': 'fixed values', 'scenario': 'sensitivity scenario', 'laboratory': 'supplied laboratory SD'}[config.get('uncertainty', 'fixed')]
        fig.suptitle(title, fontsize=13)
        from ..plot_layout import outside_legend
        outside_legend(fig)
    # Put the analysis tables first in the desktop's result selector.
    qa_names = {'quality_by_sample', 'measurement_status', 'observations', 'normalized_measurements', 'flagged_observations', 'selection_exclusions'}
    tables = {**{k:v for k,v in tables.items() if k not in qa_names}, **{k:v for k,v in tables.items() if k in qa_names}}
    return PlotResult(fig, tables, metadata, warnings)
