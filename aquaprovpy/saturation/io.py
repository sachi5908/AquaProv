"""CSV (including PHREEQC tab-separated output) and Excel source ingestion."""
import csv
import hashlib
from pathlib import Path

import pandas as pd

from ..core.data import _read_preserving_identifiers
from ..core.data_jobs import read_dataset


def read_si_dataset(path, sheet=None):
    path = Path(path)
    if path.suffix.lower()!='.csv':
        return read_dataset(path,sheet)
    with path.open(encoding='utf-8-sig') as stream:
        preview = stream.read(8192)
    try:
        separator = csv.Sniffer().sniff(preview,delimiters=',;\t').delimiter
    except csv.Error:
        separator = ','
    frame = _read_preserving_identifiers(pd.read_csv,path,sep=separator,encoding='utf-8-sig')
    # IPhreeqc selected output appends a trailing tab to every line.
    frame = frame.loc[:,~(frame.columns.astype(str).str.startswith('Unnamed:') & frame.isna().all().to_numpy())]
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    frame.attrs['aquaprov'] = dict(source_file=str(path.resolve()),source_sha256=digest.hexdigest(),source_sheet=None)
    return frame,[],None
