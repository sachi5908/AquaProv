"""Dataset preparation jobs; no Qt controls are read or created here."""
import hashlib

import pandas as pd

from .data import normalize_headers, read_csv, read_excel
from .plot_data import complete_samples
from .progress import report_progress


def read_dataset(path, sheet=None):
    sheets = []
    if path.suffix.lower() == '.csv':
        frame = read_csv(path)
    elif path.suffix.lower() in ('.xlsx', '.xls'):
        with pd.ExcelFile(path) as workbook:
            sheets = workbook.sheet_names
            if not sheets:
                raise ValueError('This workbook does not contain any worksheets.')
            if sheet is None:
                sheet = sheets[0]
                for index, name in enumerate(sheets):
                    headers = pd.read_excel(workbook, sheet_name=name, nrows=0)
                    report_progress(40 * (index + 1) / len(sheets), 'Checking workbook sheets')
                    try:
                        _, recognized = normalize_headers(headers)
                    except ValueError:
                        recognized = {}
                    if recognized:
                        sheet = name
                        break
            frame = read_excel(workbook, sheet_name=sheet)
    else:
        raise ValueError('Choose a CSV, XLS, or XLSX file.')
    report_progress(80, 'Recording source information')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    frame.attrs['aquaprov'] = {'source_file': str(path.resolve()),
        'source_sha256': digest.hexdigest(), 'source_sheet': sheet if sheets else None}
    return frame, sheets, sheet


def prepare_dataset(frame):
    frame = frame.copy(deep=True)
    ec_headers = [str(c).lower() for c in frame if str(c).lower().startswith('ec')]
    ec_unit = ('mS/cm' if any('ms/cm' in c for c in ec_headers) else
               'dS/m' if any('ds/m' in c for c in ec_headers) else 'uS/cm')
    frame.columns = [str(c).strip() for c in frame]
    if len(set(frame.columns)) != len(frame.columns):
        raise ValueError('Column names must be unique after trimming spaces.')
    frame = frame.replace(r'^\s*$', pd.NA, regex=True)
    empty = frame.isna().all(axis=1)
    if empty.any():
        frame.attrs.setdefault('aquaprov', {})['excluded_empty_source_indices'] = frame.index[empty].astype(str).tolist()
    frame = frame.dropna(how='all')
    if frame.empty:
        raise ValueError('This worksheet has no non-empty sample rows.')
    frame, renamed = normalize_headers(frame)
    report_progress(35, 'Inspecting measurement columns')
    numeric = {}
    for index, column in enumerate(frame):
        values = pd.to_numeric(frame[column], errors='coerce')
        if values.notna().any():
            numeric[column] = values.dropna().nunique() < 2
        report_progress(35 + 60 * (index + 1) / len(frame.columns))
    return frame, frame.copy(deep=True), renamed, ec_unit, numeric


def styled_plot_frame(data, required, appearance, *, strict=False, text_columns=(), missing='drop', numeric_groups=None):
    if data is None:
        raise ValueError('Import a CSV or Excel file first.')
    numeric = sorted(required - {'Sample'})
    color_column, label_column = appearance['color_column'], appearance['label_column']
    if color_column != '(single color)' and color_column in data:
        numeric.append(color_column)
    frame, report = complete_samples(data, numeric, text_columns=text_columns,
                                     missing=missing, numeric_groups=numeric_groups)
    frame.attrs['plot_input_filter'] = report
    report_progress(65, 'Preparing sample appearance')
    defaults = {'Sample': [f'Sample {i}' for i in report['used_row_positions_1based']],
        'Label': 'All samples', 'Color': appearance['color'], 'Marker': appearance['marker'],
        'Size': appearance['size'], 'Alpha': appearance['alpha']}
    for column, value in defaults.items():
        if column not in frame:
            frame[column] = value
    names = frame['Sample'].replace(r'^\s*$', pd.NA, regex=True)
    frame['Sample'] = names.where(names.notna(), defaults['Sample']).astype(str)
    frame['Label'] = frame[label_column].fillna('').astype(str) if label_column in frame else 'All samples'
    if color_column != '(single color)' and color_column in frame:
        frame['Color'] = pd.to_numeric(frame[color_column], errors='coerce')
        if frame['Color'].isna().any():
            raise ValueError(f'Color column {color_column} must contain numeric values without blanks.')
    else:
        frame['Color'] = appearance['color']
        if label_column in frame:
            from .._publication import PALETTE
            groups = list(dict.fromkeys(frame['Label']))
            frame['Color'] = frame['Label'].map({g: PALETTE[i % len(PALETTE)] for i, g in enumerate(groups)})
    frame.attrs['color_label'] = color_column
    frame['Marker'] = appearance['marker']
    if label_column in frame and color_column == '(single color)':
        from .._publication import PALETTE, GROUP_MARKERS
        groups = list(dict.fromkeys(frame['Label']))
        frame['Marker'] = frame['Label'].map({g: GROUP_MARKERS[(i // len(PALETTE)) % len(GROUP_MARKERS)]
                                            for i, g in enumerate(groups)})
    frame['Size'], frame['Alpha'] = appearance['size'], appearance['alpha']
    return (frame if strict else frame.reset_index(drop=True)), report
