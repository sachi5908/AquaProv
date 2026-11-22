"""Descriptive time-series and iid bootstrap tools for AquaProv.

These are exploratory summaries, not hydrological forecasts or propagation of
laboratory measurement errors. No censoring, imputation or unit conversion is
performed. Row exclusions are opt-in and exported with their original positions.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ._publication import STYLE, close_on_error, finish
from .core.progress import report_progress


def _measurement(df, column, missing):
    if missing not in ('raise', 'drop'):
        raise ValueError('Missing policy must be raise or drop.')
    if column not in df or df.empty:
        raise ValueError('Choose a measurement column from a non-empty dataset.')
    values = pd.to_numeric(df[column], errors='coerce')
    invalid = df[column].notna() & values.isna()
    if invalid.any():
        raise ValueError('Non-numeric or censored measurements must be resolved explicitly.')
    if np.isinf(values.to_numpy(dtype=float)).any():
        raise ValueError('Infinite measurements are not supported.')
    return values


def bootstrap(df, column, *, statistic='mean', confidence=95, resamples=2000,
              seed=42, missing='raise'):
    """Percentile bootstrap of a mean or median; independent rows assumed."""
    if statistic not in ('mean', 'median'):
        raise ValueError('Choose mean or median.')
    if not np.isfinite(confidence) or not 50 <= confidence < 100:
        raise ValueError('Confidence must be at least 50 and less than 100 percent.')
    if isinstance(resamples, bool) or not isinstance(resamples, (int, np.integer)) or resamples < 2:
        raise ValueError('Use at least 2 bootstrap resamples to estimate a standard error.')
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or not 0 <= seed <= 2147483647:
        raise ValueError('Seed must be an integer from 0 to 2147483647.')
    values = _measurement(df, column, missing)
    excluded = np.flatnonzero(values.isna()).tolist()
    if excluded and missing == 'raise':
        raise ValueError('Missing measurements: choose explicit row exclusion or resolve the data.')
    values = values.dropna().to_numpy(dtype=float)
    if not len(values):
        raise ValueError('At least one complete measurement is required.')
    rng = np.random.default_rng(seed)
    reducer = np.mean if statistic == 'mean' else np.median
    draws = np.empty(resamples)
    batch_size = max(1, min(100, 1_000_000 // len(values)))
    for start in range(0, resamples, batch_size):
        count = min(batch_size, resamples - start)
        draws[start:start + count] = reducer(rng.choice(values, (count, len(values))), axis=1)
        report_progress(75 * (start + count) / resamples, f'Bootstrap samples: {start + count:,} / {resamples:,}')
    tail = (100 - confidence) / 200
    low, high = np.quantile(draws, [tail, 1 - tail])
    estimate = float(reducer(values))
    summary = pd.DataFrame([dict(variable=column, statistic=statistic, n=len(values),
        estimate=estimate, ci_low=low, ci_high=high, confidence_percent=confidence,
        bootstrap_se=draws.std(ddof=1))])
    metadata = dict(method='iid percentile bootstrap', variable=column, statistic=statistic,
        confidence_percent=confidence, resamples=int(resamples), seed=int(seed),
        n_input=len(df), n_used=len(values), missing=missing,
        excluded_row_positions_1based=[i + 1 for i in excluded],
        unit_note='Original measurement units; no conversion',
        quantile_method='NumPy linear', sampling='Independent rows, with replacement')
    warnings = ['Assumes independent, representative observations. Repeated-site, temporal or spatial dependence requires a different resampling design.',
                'This interval estimates sampling uncertainty of the statistic, not measurement-error uncertainty or a prediction interval.']
    if len(values) < 30:
        warnings.append('Small sample: percentile intervals may have poor coverage; review before publication.')
    if resamples < 2000:
        warnings.append('Fewer than 2000 resamples: use more for final interval stability checks.')
    if np.ptp(values) == 0:
        warnings.append('All measurements are equal: the bootstrap interval is degenerate.')
    if excluded:
        warnings.append(f'Excluded {len(excluded)} missing rows by explicit request.')
    used = np.flatnonzero(pd.to_numeric(df[column], errors='coerce').notna()) + 1
    return {'summary': summary, 'bootstrap_distribution': pd.DataFrame({'estimate': draws}),
            'analysis_data': pd.DataFrame({column: values}, index=pd.Index(used, name='source_row_position'))}, metadata, warnings


def time_series(df, column, time_column, *, date_format='%Y-%m-%d', missing='raise',
                group_column=None):
    """Sort observed dates within explicit sites/groups; never interpolate."""
    values = _measurement(df, column, missing)
    if time_column not in df or time_column == column:
        raise ValueError('Choose a separate date/time column.')
    raw = df[time_column]
    if pd.api.types.is_numeric_dtype(raw):
        raise ValueError('Numeric date codes are ambiguous. Import actual dates or explicitly formatted date strings.')
    times = pd.to_datetime(raw, format=date_format, errors='coerce')
    if (raw.notna() & times.isna()).any():
        raise ValueError('Dates do not match the selected format. No ambiguous date parsing is performed.')
    keep = values.notna() & times.notna()
    if (~keep).any() and missing == 'raise':
        raise ValueError('Missing measurements or dates: resolve them or choose explicit row exclusion.')
    if group_column is not None and group_column not in df:
        raise ValueError('Choose an existing site/group column.')
    groups = df[group_column].fillna('Unlabelled').astype(str) if group_column else pd.Series('All observations', index=df.index)
    table = pd.DataFrame({'source_row_position': np.arange(1, len(df) + 1),
                          'time': times, 'value': values, 'group': groups})
    table = table.loc[keep].sort_values(['group', 'time'], kind='stable').reset_index(drop=True)
    if table.empty:
        raise ValueError('At least one complete dated measurement is required.')
    warnings = ['Descriptive observations only. Connecting lines are visual guides, not interpolation, forecasts or significance tests.',
                'Select a site/group column when rows contain different sampling locations.']
    if table.duplicated(['group', 'time']).any():
        warnings.append('Duplicate dates within a group are shown individually, without aggregation.')
    excluded = (np.flatnonzero(~keep) + 1).tolist()
    if excluded:
        warnings.append(f'Excluded {len(excluded)} incomplete rows by explicit request.')
    metadata = dict(method='observed time series', variable=column, time_column=time_column,
        date_format=date_format, group_column=group_column, missing=missing,
        n_input=len(df), n_used=len(table), excluded_row_positions_1based=excluded,
        unit_note='Original measurement units; no conversion', aggregation='none', interpolation='none')
    return {'observations': table}, metadata, warnings


@close_on_error
def plot(df, unit='mg/L', figname=None, figformat='png', *, view='bootstrap',
         column=None, dpi=300, **options):
    if view == 'bootstrap':
        tables, metadata, warnings = bootstrap(df, column, **options)
    elif view == 'time_series':
        tables, metadata, warnings = time_series(df, column, **options)
    else:
        raise ValueError('Unknown exploratory view.')
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(9, 6))
        if view == 'bootstrap':
            row = tables['summary'].iloc[0]
            ax.hist(tables['bootstrap_distribution']['estimate'], bins='auto',
                    color='#0072B2', edgecolor='white', alpha=0.85, label='Bootstrap estimates')
            ax.axvline(row.estimate, color='#172b4d', label='Observed estimate')
            for limit, label in [(row.ci_low, f'{row.confidence_percent:g}% percentile interval'), (row.ci_high, None)]:
                ax.axvline(limit, color='#D55E00', linestyle='--', label=label)
            ax.set(xlabel=f'{column} · bootstrap {row.statistic} (original units)',
                   ylabel='Resamples', title='Sampling uncertainty · iid bootstrap')
            ax.legend()
        else:
            for label, series in tables['observations'].groupby('group', sort=False):
                ax.plot(series.time, series.value, marker='o', markersize=4, label=label)
            ax.set(xlabel=metadata['time_column'], ylabel=f'{column} (original units)',
                   title='Observed water-quality time series')
            ax.legend()
            fig.autofmt_xdate()
        ax.set_title(f'{ax.get_title()} · n = {metadata["n_used"]}')
        from .plot_layout import outside_legend
        outside_legend(fig)
        fig.set_layout_engine('constrained', w_pad=.12, h_pad=.12)
    return finish(fig, tables, metadata, warnings, figname, figformat, dpi)
