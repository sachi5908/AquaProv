"""Aqueous speciation only: SI is computed by PHREEQC, never from concentrations."""
from copy import deepcopy
import hashlib
from io import StringIO
import re

import numpy as np
import pandas as pd

from ..core.numeric_jobs import run_numeric_job
from ..core.progress import report_progress
from .backend import resolve_database, phase_names
from .data import COMMON_MINERALS, SIResult, classify, finalize, import_si, labels, numeric

# Explicit analytical bases. Equivalent concentrations are accepted only for
# ions with the listed charge; total Fe, DIC and dissolved Si have no fixed charge.
PARAMETERS = {
    'Ca': ('Ca', ('Ca',), 2), 'Mg': ('Mg', ('Mg',), 2),
    'Na': ('Na', ('Na',), 1), 'K': ('K', ('K',), 1),
    'Cl': ('Cl', ('Cl',), 1), 'SO4': ('S(6)', ('SO4', 'S'), 2),
    'NO3': ('N(5)', ('NO3', 'N'), 1), 'F': ('F', ('F',), 1),
    'Alkalinity': ('Alkalinity', ('CaCO3', 'HCO3'), 1),
    'DIC': ('C(4)', ('C', 'HCO3'), None), 'Si': ('Si', ('SiO2', 'Si'), None),
    'Fe': ('Fe', ('Fe',), None), 'Fe(2)': ('Fe(2)', ('Fe',), 2),
    'Fe(3)': ('Fe(3)', ('Fe',), 3), 'Al': ('Al', ('Al',), 3),
    'Mn': ('Mn(2)', ('Mn',), 2), 'Sr': ('Sr', ('Sr',), 2),
    'Ba': ('Ba', ('Ba',), 2), 'B': ('B', ('B',), None),
    'P': ('P', ('P', 'PO4'), None),
}
UNITS = ('mg/L', 'ug/L', 'mmol/L', 'mol/L', 'meq/L')
DEPENDENCIES = {
    'Calcite': ('Ca', 'carbon'), 'Dolomite': ('Ca', 'Mg', 'carbon'),
    'Gypsum': ('Ca', 'SO4'), 'Anhydrite': ('Ca', 'SO4'),
    'Halite': ('Na', 'Cl'), 'Quartz': ('Si',), 'Fluorite': ('Ca', 'F'),
    'Goethite': ('iron',), 'Hematite': ('iron',),
}
ACTIVITIES = ('Ca+2', 'Mg+2', 'CO3-2', 'SO4-2', 'Na+', 'Cl-', 'F-', 'H4SiO4', 'Fe+3', 'H+', 'H2O')


def suggested_parameters(frame):
    """Suggestions require user review; HCO3 is never silently called alkalinity."""
    aliases = {'Alkalinity': ('Alkalinity', 'TA'), 'Si': ('SiO2', 'Si'), 'DIC': ('DIC',),
               'Fe(2)': ('Fe(2)', 'Fe2'), 'Fe(3)': ('Fe(3)', 'Fe3')}
    result = []
    for name, (_, bases, _) in PARAMETERS.items():
        column = next((c for c in aliases.get(name, (name,)) if c in frame), None)
        if column is not None:
            basis = 'Si' if name == 'Si' and column == 'Si' else bases[0]
            result.append(dict(name=name, column=column, unit='mg/L', basis=basis))
    return result


def validate_parameters(frame, parameters):
    if not parameters:
        raise ValueError('Map and review the measured dissolved chemical concentrations first.')
    seen, columns = set(), set()
    for p in parameters:
        name = p.get('name')
        if name not in PARAMETERS or name in seen:
            raise ValueError('Choose each supported chemical parameter only once.')
        seen.add(name)
        if p.get('column') not in frame or p['column'] in columns:
            raise ValueError(f'{name}: choose a distinct source measurement column.')
        columns.add(p['column'])
        if p.get('unit') not in UNITS or p.get('basis') not in PARAMETERS[name][1]:
            raise ValueError(f'{name}: invalid analytical unit or reporting basis.')
        if p['unit'] == 'meq/L' and PARAMETERS[name][2] is None:
            raise ValueError(f'{name}: equivalents require a defined ionic charge; use a mass or molar concentration.')
    if {'Alkalinity', 'DIC'} <= seen:
        raise ValueError('Use measured alkalinity OR total dissolved inorganic carbon; do not double-count carbon.')
    if 'Fe' in seen and seen.intersection({'Fe(2)', 'Fe(3)'}):
        raise ValueError('Use total dissolved Fe OR measured Fe(II)/Fe(III), not both.')
    return seen


def concentration_line(parameter, value):
    name, unit, basis = parameter['name'], parameter['unit'], parameter['basis']
    token, _, charge = PARAMETERS[name]
    if unit == 'ug/L':
        value, unit = value / 1000, 'mg/L'
    if name == 'Alkalinity':
        # PHREEQC alkalinity molar units are equivalents. The explicit half
        # formula avoids PHREEQC's warning/correction of a full CaCO3 formula.
        if unit == 'meq/L':
            unit = 'mmol/L'
        formula = 'Ca0.5(CO3)0.5' if basis == 'CaCO3' else 'HCO3'
    else:
        if unit == 'meq/L':
            value, unit = value / charge, 'mmol/L'
        formula = basis
    return f'    {token} {value:.15g} {unit} as {formula}'


def _values(frame, column, constant, label, minimum, maximum):
    if column:
        if column not in frame:
            raise ValueError(f'{label}: mapped column is absent.')
        values = numeric(frame[column], label).to_numpy()
    else:
        try:
            value = float(constant)
        except (ValueError, TypeError) as exc:
            raise ValueError(f'Specify {label} as a measured column or an explicit constant.') from exc
        if not np.isfinite(value):
            raise ValueError(f'{label} must be finite.')
        values = np.full(len(frame), value)
    if ((values < minimum) | (values > maximum)).any():
        raise ValueError(f'{label} must be between {minimum} and {maximum}.')
    return values


def calculate_chemistry(frame, config):
    parameters = deepcopy(config.get('parameters', []))
    names = validate_parameters(frame, parameters)
    automatic = config.get('chemistry_setup') == 'automatic'
    if not config.get('chemistry_reviewed', False) and not automatic:
        raise ValueError('Review chemical mappings, dissolved fractions, units, alkalinity/DIC basis and temperature, '
                         'then confirm the chemistry settings before calculating.')
    minerals = config.get('minerals') or list(COMMON_MINERALS)
    if len(minerals) > 80 or len(minerals) != len(set(minerals)):
        raise ValueError('Select at most 80 distinct minerals.')
    if any(not re.fullmatch(r'[A-Za-z0-9_().+\-]+', m) for m in minerals):
        raise ValueError('Use PHREEQC phase names without spaces, quotes or control characters.')
    database = resolve_database(config.get('database', 'phreeqc.dat'), config.get('database_snapshot'))
    known = set(phase_names(database))
    active = [m for m in minerals if m in known]
    if not active:
        raise ValueError('None of the selected minerals occur in the selected database.')
    if not config.get('pH_column'):
        raise ValueError('Map measured pH (hydrogen-ion activity scale) for each sample.')
    ph = _values(frame, config['pH_column'], None, 'pH', 0, 14)
    temperature = _values(frame, config.get('temperature_column'), config.get('temperature_c', 25),
                          'Temperature (degrees C)', 0, 100)
    density = _values(frame, config.get('density_column'), config.get('density_kg_L', 1),
                      'Solution density (kg/L)', .8, 1.5)
    redox = config.get('redox', 'none')
    if redox not in ('none', 'pe', 'eh_mv'):
        raise ValueError('Choose no imposed redox, measured/assumed pe, or Eh in mV.')
    if redox != 'none':
        pe = _values(frame, config.get('redox_column'), config.get('redox_value'),
                     'pe' if redox == 'pe' else 'Eh (mV vs standard hydrogen electrode)',
                     -30 if redox == 'pe' else -1500, 30 if redox == 'pe' else 1500)
        if redox == 'eh_mv':
            pe = (pe / 1000) * 96485.33212 / (np.log(10) * 8.314462618 * (temperature + 273.15))
    else:
        pe = np.full(len(frame), 4.0)
    concentrations = {}
    for p in parameters:
        v = numeric(frame[p['column']], p['column']).to_numpy()
        if (v < 0).any():
            raise ValueError(f'{p["name"]}: concentrations must be non-negative.')
        concentrations[p['name']] = v
    complete = np.isfinite(np.column_stack([ph, temperature, density, pe, *concentrations.values()])).all(axis=1)
    if not complete.all() and config.get('missing', 'raise') == 'raise':
        raise ValueError('Missing mapped chemistry at source row(s) ' + str((np.flatnonzero(~complete)+1).tolist()[:15]) +
                         '. Resolve the data or explicitly exclude incomplete samples.')
    if config.get('missing', 'raise') not in ('raise', 'drop'):
        raise ValueError('Unknown incomplete-chemistry policy.')
    if not complete.any():
        raise ValueError('No samples have complete mapped chemistry.')
    samples = labels(frame, config.get('sample_column'))
    measured = set(names)
    if measured.intersection({'DIC', 'Alkalinity'}):
        measured.add('carbon')
    if measured.intersection({'Fe', 'Fe(2)', 'Fe(3)'}):
        measured.add('iron')
    reasons = {}
    for mineral in minerals:
        if mineral not in known:
            reasons[mineral] = 'Phase absent from selected database'
        elif set(DEPENDENCIES.get(mineral, ())) - measured:
            reasons[mineral] = 'Unmeasured component(s): ' + ', '.join(sorted(set(DEPENDENCIES[mineral]) - measured))
        elif mineral in ('Goethite', 'Hematite') and redox == 'none' and 'Fe(3)' not in names:
            reasons[mineral] = 'Ferric speciation requires measured Fe(III) or an explicit pe/Eh assumption'
    lines = ['TITLE AquaProv aqueous speciation (no equilibration with minerals)',
             'SELECTED_OUTPUT 1', '    -reset false', '    -high_precision true',
             '    -solution true', '    -pH true', '    -pe true', '    -temperature true',
             '    -ionic_strength true', '    -charge_balance true', '    -percent_error true',
             '    -saturation_indices ' + ' '.join(active),
             '    -activities ' + ' '.join(ACTIVITIES),
             'USER_PUNCH 1', '    -headings ' + ' '.join(f'logK_{m}' for m in active),
             '    -start', '10 PUNCH ' + ', '.join(f'LK_PHASE("{m}")' for m in active), '    -end']
    for i in np.flatnonzero(complete):
        lines.extend([f'SOLUTION {i + 1}', '    units mg/L', f'    pH {ph[i]:.15g}',
                      f'    temp {temperature[i]:.15g}', f'    pe {pe[i]:.15g}', f'    density {density[i]:.15g}', '    water 1'])
        lines.extend(concentration_line(p, concentrations[p['name']][i]) for p in parameters)
    lines.append('END')
    input_text = '\n'.join(lines) + '\n'
    report_progress(18, f'PHREEQC: speciating {int(complete.sum())} groundwater samples')
    native = run_numeric_job('phreeqc', dict(database=database['text'], input=input_text))
    table = pd.read_csv(StringIO(native['output']), sep='\t')
    table.columns = table.columns.str.strip()
    table = table.loc[:, ~table.columns.str.startswith('Unnamed')]
    if len(table) != int(complete.sum()) or set(table['soln'].astype(int)) != set(np.flatnonzero(complete)+1):
        raise ValueError('PHREEQC returned unexpected solution identifiers; results were not assigned to samples.')
    by_row = table.set_index('soln')
    rows = []
    for i in range(len(frame)):
        for mineral in minerals:
            status = 'Excluded: incomplete mapped chemistry' if not complete[i] else reasons.get(mineral, 'Calculated')
            si, logk = np.nan, np.nan
            if status == 'Calculated':
                si = float(by_row.loc[i+1, 'si_' + mineral])
                logk = float(by_row.loc[i+1, 'logK_' + mineral])
                if not np.isfinite(si) or si == -999.999:
                    si, status = np.nan, 'Undefined: required activity is absent or zero'
            rows.append(dict(source_row=i+1, sample=samples[i], mineral=mineral, SI=si,
                             log10_K=logk, log10_IAP=si+logk, status=status))
    records = pd.DataFrame(rows)
    records['classification'] = classify(records.SI)
    diagnostics = pd.DataFrame(dict(source_row=np.arange(1,len(frame)+1), sample=samples,
                                    included=complete, input_pH=ph, temperature_C=temperature, density_kg_L=density, input_pe=pe))
    diagnostics = diagnostics.merge(table.rename(columns={'soln':'source_row'}), on='source_row', how='left', validate='one_to_one')
    diagnostics.insert(2, 'Charge balance error (%)', diagnostics.pct_err)
    diagnostics.attrs['full_precision_columns'] = ['Charge balance error (%)']
    diagnostics['charge_balance_review'] = np.where(diagnostics.pct_err.isna(), 'Unassessed',
        np.where(diagnostics.pct_err.abs() > 5, 'Above 5% absolute error', 'Within 5% absolute error'))
    warnings = []
    if native['warnings'].strip():
        warnings.append(native['warnings'].strip())
    if 'pct_err' in table:
        count = int((table.pct_err.abs() > 5).sum())
        if count:
            warnings.append(f'{count} sample(s) exceed 5% absolute PHREEQC charge-balance error. Review chemistry before interpreting SI; no charge adjustment was applied.')
    if redox == 'none':
        warnings.append('No measured/assumed redox specified. PHREEQC pe=4 is recorded as its default; iron-oxide SI is unassessed unless Fe(III) is measured.')
    else:
        warnings.append('Redox-sensitive speciation uses the supplied pe/Eh. Verify Eh is referenced to the standard hydrogen electrode and represents the relevant redox couple.')
    absent_major = sorted({'Ca','Mg','Na','K','Cl','SO4'} - names)
    if absent_major:
        warnings.append('Unmapped major ions: ' + ', '.join(absent_major) + '. Omitted components can affect ionic strength and every calculated SI.')
    if not config.get('temperature_column'):
        warnings.append(f'All solutions use the constant temperature {config.get("temperature_c",25):g} degrees C; no measured temperature column was supplied.')
    if not config.get('density_column'):
        warnings.append(f'Solution density uses the constant {config.get("density_kg_L",1):g} kg/L; review this assumption for saline waters.')
    if automatic:
        warnings.append('Automatic chemistry setup: input mappings and assumptions were applied by AquaProv, not confirmed as laboratory-verified by the user.')
        warnings.extend(config.get('input_assumptions', []))
    warnings.append('Activity models and phase constants are those of the chosen database; assess their suitability for the salinity and temperature of the samples.')
    metadata = dict(mode='calculate', engine='USGS IPhreeqc', engine_version=native['version'],
        engine_sha256=native['library_sha256'], database={k:v for k,v in database.items() if k!='text'},
        input_sha256=hashlib.sha256(input_text.encode('utf-8')).hexdigest(),
        activity_model='As implemented in the selected PHREEQC thermodynamic database',
        chemistry_parameters=parameters, redox=redox, pressure_atm=1.0,
        chemistry_setup='automatic' if automatic else 'reviewed',
        chemistry_reviewed=bool(config.get('chemistry_reviewed',False)),
        input_assumptions=list(config.get('input_assumptions',[])),
        calculation='Initial aqueous SOLUTION speciation only; no EQUILIBRIUM_PHASES, reaction path or charge balancing',
        logIAP='Reconstructed as PHREEQC SI + temperature-dependent LK_PHASE for audit',
        references=['Parkhurst & Appelo (2013), USGS Techniques and Methods 6-A43, https://doi.org/10.3133/tm6A43',
                    'Charlton & Parkhurst (2011), Computers & Geosciences 37, 1653-1663, https://doi.org/10.1016/j.cageo.2011.02.005'])
    return SIResult(records, dict(diagnostics=diagnostics, chemistry_mapping=pd.DataFrame(parameters),
        phreeqc_input=pd.DataFrame({'line':input_text.splitlines()}),
        thermodynamic_database=pd.DataFrame({'line':database['text'].splitlines()})), metadata, warnings)


def calculate(frame, config):
    if frame is None or frame.empty or not frame.columns.is_unique:
        raise ValueError('Import a non-empty dataset with unique column names.')
    mode = config.get('mode', 'import')
    if mode not in ('import', 'calculate'):
        raise ValueError('Choose imported SI or PHREEQC calculation.')
    result = calculate_chemistry(frame, config) if mode == 'calculate' else import_si(frame, config)
    report_progress(78, 'Summarizing mineral saturation and exclusions')
    return finalize(result, frame, config)
