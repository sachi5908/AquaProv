"""Complete-sample filtering for desktop plots, with source-row diagnostics."""
import numpy as np
import pandas as pd


def complete_samples(frame, numeric_columns, *, text_columns=(), missing='drop', numeric_groups=None):
    """Keep required measurements and, if supplied, at least one usable panel.

    Groups describe independent panels/series. Missing group columns stay NaN;
    they never become zero or exclude a row usable in another group.
    """
    if frame is None or frame.empty:
        raise ValueError('Import a non-empty dataset first.')
    if not frame.columns.is_unique:
        raise ValueError('Column names must be unique.')
    if missing not in ('drop', 'raise'):
        raise ValueError('Choose whether to exclude incomplete samples or stop on missing data.')
    numeric_columns = list(dict.fromkeys(numeric_columns))
    text_columns = list(dict.fromkeys(text_columns))
    required = list(dict.fromkeys([*numeric_columns, *text_columns]))
    absent = [str(column) for column in required if column not in frame]
    if absent:
        raise ValueError('This plot needs these columns: ' + ', '.join(absent))
    numeric_groups = numeric_groups or {}
    group_columns = list(dict.fromkeys(c for columns in numeric_groups.values() for c in columns))
    checked = list(dict.fromkeys([*required, *group_columns]))
    cleaned = frame.copy(deep=True)
    missing_cells, invalid_cells = {}, {}
    for column in checked:
        raw = (frame[column] if column in frame else pd.Series(np.nan, index=frame.index))
        raw = raw.replace(r'^\s*$', np.nan, regex=True)
        missing_cells[column] = raw.isna().to_numpy()
        if column in numeric_columns or column in group_columns:
            values = pd.to_numeric(raw, errors='coerce').astype(float)
            invalid_cells[column] = ~np.isfinite(values.to_numpy()) & ~missing_cells[column]
            cleaned[column] = values.where(np.isfinite(values), np.nan)
        else:
            invalid_cells[column] = np.zeros(len(frame), dtype=bool)
    keep = np.ones(len(frame), dtype=bool)
    for column in required:
        keep &= ~(missing_cells[column] | invalid_cells[column])
    groups = {}
    for name, columns in numeric_groups.items():
        usable = keep.copy()
        for column in columns:
            usable &= ~(missing_cells[column] | invalid_cells[column])
        groups[name] = usable
    if groups:
        keep &= np.logical_or.reduce(list(groups.values()))
    def describe_row(position, columns):
        sample = frame.iloc[position]['Sample'] if 'Sample' in frame else None
        return {
            'data_row': int(position + 1), 'source_index': str(frame.index[position]),
            'sample': str(sample) if pd.notna(sample) else f'Data row {position + 1}',
            'missing_columns': [str(c) for c in columns if missing_cells[c][position]],
            'invalid_columns': [str(c) for c in columns if invalid_cells[c][position]],
        }
    excluded = [describe_row(position, checked) for position in np.flatnonzero(~keep)]
    if excluded and missing == 'raise':
        raise ValueError('Selected measurements contain missing or non-numeric values. '
                         'Choose "Exclude incomplete rows (reported)" to plot the available samples.')
    if not keep.any():
        needs = (', '.join(map(str, required)) if not groups else
                 'at least one of ' + '; '.join(f'{name} ({", ".join(columns)})'
                                               for name, columns in numeric_groups.items()))
        raise ValueError('No complete samples remain for: ' + needs +
                         f'. All {len(frame)} samples have missing or unusable values in these columns.')
    report = {'n_input': len(frame), 'n_available': int(keep.sum()),
              'required_columns': list(map(str, required)),
              'used_row_positions_1based': (np.flatnonzero(keep) + 1).tolist(),
              'excluded_samples': excluded}
    if groups:
        report['groups'] = {
            name: {'columns': list(numeric_groups[name]), 'n_available': int(usable.sum()),
                   'used_row_positions_1based': (np.flatnonzero(usable) + 1).tolist()}
            for name, usable in groups.items()}
        partial = keep & ~np.logical_and.reduce(list(groups.values()))
        report['partial_samples'] = [describe_row(position, checked) for position in np.flatnonzero(partial)]
    return cleaned.iloc[np.flatnonzero(keep)].copy(), report
