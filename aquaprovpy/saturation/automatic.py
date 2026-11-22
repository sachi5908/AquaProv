"""Automatic chemistry mapping with explicit, exportable input assumptions."""
import hashlib
import re

import pandas as pd

from .data import COMMON_MINERALS
from .engine import DEPENDENCIES, PARAMETERS


ALIASES = {
    'ca':'Ca', 'ca2':'Ca', 'calcium':'Ca', 'mg':'Mg', 'mg2':'Mg', 'magnesium':'Mg',
    'na':'Na', 'sodium':'Na', 'k':'K', 'potassium':'K', 'cl':'Cl', 'chloride':'Cl',
    'so4':'SO4', 'so42':'SO4', 'sulfate':'SO4', 'sulphate':'SO4', 'so4s':'SO4',
    'no3':'NO3', 'nitrate':'NO3', 'no3n':'NO3', 'f':'F', 'fluoride':'F',
    'ta':'Alkalinity', 'alkalinity':'Alkalinity', 'totalalkalinity':'Alkalinity',
    'dic':'DIC', 'dissolvedinorganiccarbon':'DIC', 'sio2':'Si', 'silica':'Si', 'si':'Si',
    'fe':'Fe', 'fetotal':'Fe', 'totalfe':'Fe', 'iron':'Fe',
    'fe2':'Fe(2)', 'feii':'Fe(2)', 'fe3':'Fe(3)', 'feiii':'Fe(3)',
    'al':'Al', 'mn':'Mn', 'mn2':'Mn', 'sr':'Sr', 'ba':'Ba', 'b':'B', 'p':'P', 'po4':'P',
}
UNIT_PATTERN = re.compile(r'(?<![a-z])(?:mmol|mol|meq|mg|ug|g)\s*/\s*l\b|\b(?:ppm|ppb)\b', re.I)


def dataset_signature(frame):
    """Do not restore mappings or review flags belonging to a different table."""
    if frame is None:
        return None
    digest = hashlib.sha256(repr(list(frame.columns)).encode('utf-8'))
    digest.update(pd.util.hash_pandas_object(frame, index=False).values.tobytes())
    digest.update(repr(frame.attrs.get('aquaprov', {}).get('original_headers', {})).encode('utf-8'))
    return digest.hexdigest()


def chemistry_mapping(frame):
    parameters, notes, problems = [], [], []
    if frame is None:
        return parameters, notes, problems
    originals = frame.attrs.get('aquaprov', {}).get('original_headers', {})
    for column in frame:
        heading = str(originals.get(column, column)).replace('µ','u').replace('μ','u')
        match = UNIT_PATTERN.search(heading)
        base = UNIT_PATTERN.sub('', heading)
        basis_match = re.search(r'\bas\s+(CaCO3|HCO3|SiO2|SO4|NO3|PO4|Ca|Mg|Na|Cl|Fe|Si|C|S|N|P)\b',base,re.I)
        if basis_match:
            base = base[:basis_match.start()] + base[basis_match.end():]
        key = re.sub(r'[^a-z0-9]', '', base.lower())
        name = ALIASES.get(key)
        if name is None:
            # Recognized chemicals with unsupported labelled units must not
            # silently fall back to mg/L (e.g. Ca (mg/kg)).
            prefix = re.split(r'[\[(]', heading)[0].strip().lower()
            if prefix in ALIASES and '/' in heading and match is None:
                problems.append(f'{column}: unsupported concentration units; map this column and its units explicitly.')
            continue
        unit = re.sub(r'\s+', '', match.group()).lower() if match else 'mg/l'
        unit = {'mg/l':'mg/L','ug/l':'ug/L','mmol/l':'mmol/L','mol/l':'mol/L','meq/l':'meq/L',
                'ppm':'mg/L','ppb':'ug/L'}.get(unit)
        if unit is None:
            problems.append(f'{column}: convert the labelled units to mg/L, ug/L, mmol/L, mol/L or meq/L.')
            continue
        if any(p['name']==name for p in parameters):
            problems.append(f'{name}: more than one chemistry column was recognized; choose the intended measurement.')
            continue
        basis = PARAMETERS[name][1][0]
        if key in ('si','so4s','no3n','po4'):
            basis = {'si':'Si','so4s':'S','no3n':'N','po4':'PO4'}[key]
        if basis_match:
            basis = next((b for b in PARAMETERS[name][1] if b.casefold()==basis_match.group(1).casefold()), None)
            if basis is None:
                problems.append(f'{column}: unsupported reporting basis; review the chemistry mapping.')
                continue
        parameters.append(dict(name=name,column=column,unit=unit,basis=basis))
        if match is None:
            notes.append(f'{column}: units not stated in the header; assumed mg/L.')
        elif match.group().lower() in ('ppm','ppb'):
            notes.append(f'{column}: interpreted {match.group()} as {unit} for aqueous concentration.')
        if name in ('Alkalinity','DIC','Si','SO4','NO3') and basis_match is None:
            notes.append(f'{column}: reporting basis assumed as {basis}; verify the laboratory basis.')
    names = {p['name'] for p in parameters}
    if {'Alkalinity','DIC'} <= names:
        parameters = [p for p in parameters if p['name']!='DIC']
        notes.append('Used alkalinity; DIC was not added a second time.')
    if 'Fe' in names and names.intersection({'Fe(2)','Fe(3)'}):
        parameters = [p for p in parameters if p['name'] not in ('Fe(2)','Fe(3)')]
        notes.append('Used total Fe; separate Fe oxidation-state measurements were not added a second time.')
    return parameters, notes, problems


def supported_minerals(parameters, redox='none'):
    names = {p['name'] for p in parameters}
    if names.intersection({'Alkalinity','DIC'}):
        names.add('carbon')
    if names.intersection({'Fe','Fe(2)','Fe(3)'}):
        names.add('iron')
    return [m for m in COMMON_MINERALS if not (set(DEPENDENCIES[m])-names)
            and (m not in ('Goethite','Hematite') or redox!='none' or 'Fe(3)' in names)]
