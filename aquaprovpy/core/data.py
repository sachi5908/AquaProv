"""Read laboratory tables and normalize their column names."""

import re

import pandas as pd

HEADER_ALIASES = {
    "slno": "Sample", "serialno": "Sample", "sampleno": "Sample",
    "sampleid": "Sample", "samplename": "Sample", "samplenumber": "Sample",
    "typeofwell": "Label", "sampletype": "Label",
    "camgl": "Ca", "ca": "Ca", "ca2mgl": "Ca", "caplusmgl": "Ca",
    "mgmgl": "Mg", "mg": "Mg", "mg2mgl": "Mg", "mgplusmgl": "Mg",
    "namgl": "Na", "na": "Na", "naplusmgl": "Na",
    "kmgl": "K", "k": "K", "kplusmgl": "K",
    "co3mgl": "CO3", "co3": "CO3", "co32mgl": "CO3",
    "hco3mgl": "HCO3", "hco3": "HCO3",
    "clmgl": "Cl", "cl": "Cl", "clmminusmgl": "Cl",
    "so42mgl": "SO4", "so4mgl": "SO4", "so4": "SO4",
    "tdsmgl": "TDS", "tds": "TDS", "ph": "pH",
    "ec": "EC", "ecscm": "EC", "ecuscm": "EC",
    "ecmscm": "EC", "ecdsm": "EC",
    "no3mgl": "NO3", "no3": "NO3", "fmgl": "F", "f": "F",
    "thmgl": "TH", "tamgl": "TA",
}

SERIAL_HEADERS = {"slno", "serialno"}


def _read_preserving_identifiers(reader, source, **kwargs):
    """Preserve textual identifiers while pandas infers measurement types."""
    headers = reader(source, nrows=0, **kwargs).columns
    identifiers = {'sample', 'sampleid', 'samplename', 'sampleno', 'samplenumber',
                   'slno', 'serialno', 'serialnumber', 'id', 'well', 'wellid',
                   'wellno', 'wellname', 'station', 'stationid', 'stationno',
                   'site', 'siteid', 'sitename', 'borehole', 'boreholeid'}

    def as_identifier(value):
        return str(value) if pd.notna(value) and str(value).strip() else pd.NA

    converters = {column: as_identifier for column in headers
                  if re.sub(r'[^a-z0-9]', '', str(column).lower()) in identifiers}
    return reader(source, converters=converters, **kwargs)


def read_csv(path):
    return _read_preserving_identifiers(pd.read_csv, path)


def read_excel(source, *, sheet_name=0):
    return _read_preserving_identifiers(pd.read_excel, source, sheet_name=sheet_name)


def normalize_headers(frame):
    """Map common analytical-lab headings to AquaProv's column names."""
    renamed = {}
    for original in frame.columns:
        key = re.sub(r"[^a-z0-9]", "", str(original).lower())
        if key in HEADER_ALIASES:
            renamed[original] = HEADER_ALIASES[key]
    # A serial-number column is only a fallback sample identifier. Laboratory
    # sheets often contain both "Sl. No." and "Sample ID"; keep the serial
    # column under its own heading instead of rejecting the worksheet.
    serial = [c for c, target in renamed.items() if target == "Sample"
              and re.sub(r"[^a-z0-9]", "", str(c).lower()) in SERIAL_HEADERS]
    others = [c for c in frame.columns if c not in serial and renamed.get(c, c) == "Sample"]
    if others:
        for column in serial:
            del renamed[column]
    elif len(serial) > 1:
        for column in serial[1:]:
            del renamed[column]
    result = frame.rename(columns=renamed)
    if len(set(result.columns)) != len(result.columns):
        sources = {}
        for original in frame.columns:
            sources.setdefault(renamed.get(original, original), []).append(str(original))
        clashes = '; '.join(f"{name}: {', '.join(columns)}" for name, columns in sources.items() if len(columns) > 1)
        raise ValueError("Several source columns map to the same AquaProv name (" + clashes +
                         "). Keep only one version of each column.")
    from copy import deepcopy
    provenance = deepcopy(frame.attrs.get('aquaprov', {}))
    previous = provenance.get('original_headers', {})
    provenance['original_headers'] = {renamed.get(c, c): previous.get(c, c) for c in frame.columns}
    result.attrs['aquaprov'] = provenance
    return result, renamed
