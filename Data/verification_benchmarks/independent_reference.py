"""Independent reference calculations for selected Sukinda wells.

Standalone: uses only the Python standard library and NumPy. No AquaProv code
is imported. The workbook is read directly from its Office Open XML parts.

Outputs (written next to this script):
  selected_wells_input.csv   exact workbook values for the selected wells
  reference_values.csv       CBE, SAR, WQI and DWQI from first principles
  sukinda_verification.pqi   USGS PHREEQC input for the same wells

Usage:  python independent_reference.py [path/to/Sukinda_CGWB_Data_2024.xlsx]
"""
import csv
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
WORKBOOK = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[2] / 'data' / 'Sukinda_CGWB_Data_2024.xlsx'

# Workbook 'Sl. No.' identifiers of the selected wells (see README.md for the selection rationale).
SELECTED = [15, 9, 1, 6, 7, 3, 39, 12]
WELL_TYPES = {'HP', 'TW', 'DW', 'BW'}

# IUPAC standard atomic weights (abridged/conventional values, CIAAW 2021), g/mol.
AW = dict(H=1.008, C=12.011, N=14.007, O=15.999, F=18.998403162, Na=22.98976928,
          Mg=24.305, S=32.06, Cl=35.45, K=39.0983, Ca=40.078)
MOLAR = {
    'Ca': AW['Ca'], 'Mg': AW['Mg'], 'Na': AW['Na'], 'K': AW['K'], 'Cl': AW['Cl'],
    'HCO3': AW['H'] + AW['C'] + 3 * AW['O'],
    'CO3': AW['C'] + 3 * AW['O'],
    'SO4': AW['S'] + 4 * AW['O'],
}
CHARGE = {'Ca': 2, 'Mg': 2, 'Na': 1, 'K': 1, 'HCO3': 1, 'CO3': 2, 'Cl': 1, 'SO4': 2}
CATIONS, ANIONS = ('Ca', 'Mg', 'Na', 'K'), ('HCO3', 'CO3', 'Cl', 'SO4')

# WHO Guidelines for Drinking-water Quality (2026 edition) guideline values, mg/L.
WHO = {'NO3': 50.0, 'F': 1.5}

COLUMNS = {
    'id': 'Sl. No.', 'type': 'Type of Well', 'site': 'Village', 'pH': 'pH (–)', 'TDS': 'TDS (mg/L)',
    'TA': 'TA (mg/L)', 'Ca': 'Ca++ (mg/L)', 'Mg': 'Mg++ (mg/L)', 'Na': 'Na+ (mg/L)', 'K': 'K+ (mg/L)',
    'CO3': 'CO3- (mg/L)', 'HCO3': 'HCO3- (mg/L)', 'Cl': 'Cl- (mg/L)', 'SO4': 'SO4(2-) (mg/L)',
    'NO3': 'NO3- (mg/L)', 'F': 'F- (mg/L)', 'Cr_total': 'Cr (Total) (ppb)',
}

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def read_first_sheet(path):
    """Return the first worksheet as a list of row lists (strings or floats)."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS):
                shared.append(''.join(t.text or '' for t in si.iter('{%s}t' % NS['m'])))
        sheets = sorted(n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n))
        root = ET.fromstring(z.read(sheets[0]))
    rows = []
    for row in root.find('m:sheetData', NS).findall('m:row', NS):
        values = {}
        for c in row.findall('m:c', NS):
            col = re.match(r'[A-Z]+', c.get('r')).group()
            index = 0
            for ch in col:
                index = index * 26 + ord(ch) - 64
            v = c.find('m:v', NS)
            if c.get('t') == 's':
                value = shared[int(v.text)]
            elif c.get('t') == 'inlineStr':
                value = ''.join(t.text or '' for t in c.iter('{%s}t' % NS['m']))
            elif v is None:
                value = None
            else:
                try:
                    value = float(v.text)
                except ValueError:
                    value = v.text
            values[index - 1] = value
        rows.append([values.get(i) for i in range(max(values) + 1)] if values else [])
    return rows


def meq(ion, mg_l):
    return mg_l * CHARGE[ion] / MOLAR[ion]


def cbe_percent(w):
    cat = sum(meq(i, w[i]) for i in CATIONS)
    an = sum(meq(i, w[i]) for i in ANIONS)
    return 100.0 * (cat - an) / (cat + an)


def sar(w):
    na, ca, mg = meq('Na', w['Na']), meq('Ca', w['Ca']), meq('Mg', w['Mg'])
    return na / np.sqrt((ca + mg) / 2.0)


def wqi_inverse_standard(w):
    """Weighted arithmetic WQI: w_i proportional to 1/S_i, q_i = 100 c_i / S_i."""
    k = np.array([1.0 / WHO[p] for p in ('NO3', 'F')])
    weights = k / k.sum()
    q = np.array([100.0 * w[p] / WHO[p] for p in ('NO3', 'F')])
    return float(np.sum(weights * q))


def dwqi_equal_importance(w):
    """Relative-weight DWQI with equal importance weights and q_i = 100 c_i / S_i."""
    weights = np.array([0.5, 0.5])
    q = np.array([100.0 * w[p] / WHO[p] for p in ('NO3', 'F')])
    return float(np.sum(weights * q))


def pqi_text(wells):
    lines = [
        'TITLE Independent external verification of AquaProv v1.0 saturation indices (selected Sukinda wells)',
        '# Database: phreeqc.dat (distributed with USGS PHREEQC 3.8.6-17100)',
        '# Conditions: 25 C, density 1 kg/L, pe 4, alkalinity as CaCO3, reported mg/L concentrations',
        'SELECTED_OUTPUT 1',
        '    -file sukinda_verification_selected.tsv',
        '    -reset false',
        '    -high_precision true',
        '    -solution true',
        '    -pH true',
        '    -saturation_indices Calcite Dolomite Gypsum Fluorite',
        '',
    ]
    for w in wells:
        n = int(w['id'])
        lines += [
            f'SOLUTION {n}  Sl. No. {n}, {w["site"]} ({w["type"]})',
            '    units     mg/L',
            '    temp      25',
            f'    pH        {w["pH"]:g}',
            '    pe        4',
            '    density   1',
            f'    Alkalinity {w["TA"]:g} as CaCO3',
            f'    Ca        {w["Ca"]:g}',
            f'    Mg        {w["Mg"]:g}',
            f'    Na        {w["Na"]:g}',
            f'    K         {w["K"]:g}',
            f'    Cl        {w["Cl"]:g}',
            f'    S(6)      {w["SO4"]:g} as SO4',
            f'    N(5)      {w["NO3"]:g} as NO3',
            f'    F         {w["F"]:g}',
            'END',
        ]
    return '\n'.join(lines) + '\n'


def main():
    rows = read_first_sheet(WORKBOOK)
    header = [str(h) for h in rows[0]]
    pos = {k: header.index(v) for k, v in COLUMNS.items()}
    records = []
    for r in rows[1:]:
        if not r or r[pos['type']] not in WELL_TYPES:
            continue
        records.append({k: r[i] for k, i in pos.items()})
    assert len(records) == 35, len(records)
    by_id = {int(w['id']): w for w in records}
    wells = [by_id[i] for i in SELECTED]

    with open(HERE / 'selected_wells_input.csv', 'w', newline='', encoding='utf-8') as f:
        out = csv.DictWriter(f, fieldnames=list(COLUMNS.values()))
        out.writeheader()
        for w in wells:
            out.writerow({COLUMNS[k]: w[k] for k in COLUMNS})

    fields = ['Sl. No.', 'site', 'type', 'TDS_mg_L', 'Cr_total_ug_L', 'CBE_percent', 'SAR', 'WQI', 'DWQI']
    with open(HERE / 'reference_values.csv', 'w', newline='', encoding='utf-8') as f:
        out = csv.writer(f)
        out.writerow(fields)
        for w in wells:
            out.writerow([int(w['id']), w['site'], w['type'], w['TDS'], w['Cr_total'],
                          repr(cbe_percent(w)), repr(float(sar(w))),
                          repr(wqi_inverse_standard(w)), repr(dwqi_equal_importance(w))])
    (HERE / 'sukinda_verification.pqi').write_text(pqi_text(wells), encoding='ascii')
    print('molar masses (g/mol):', {k: round(v, 6) for k, v in MOLAR.items()})
    print((HERE / 'reference_values.csv').read_text(encoding='utf-8'))


if __name__ == '__main__':
    main()
