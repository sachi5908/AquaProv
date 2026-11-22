"""Versioned, traceable limits. Missing objectives are never inferred or substituted."""
from copy import deepcopy
import csv
import json
from pathlib import Path

import numpy as np

from .common import unit_factor


WHO_URL = 'https://iris.who.int/server/api/core/bitstreams/c60cc28e-defe-45ed-b157-71fdd43902bf/content'
WHO_EDITION = 'WHO GDWQ, fourth edition incorporating first, second and third addenda (2026)'
BIS_URL = 'https://www.bis.gov.in/other/DrinWatIS10500.pdf'
BIS_EDITION = 'BIS IS 10500:2012, second revision; amendments 1–4 (2015, 2018, 2020, 2021); reviewed 2023'


def _limit(value, *, edition, year, source, page, amendment, verification, lower=None, notes=''):
    return dict(lower=lower, upper=value, edition=edition, publication_year=year, source=source,
                page=page, amendment=amendment, verification=verification, notes=notes)


def built_in_standards():
    # Transcribed from WHO 2026, Annex 3, Table A3.3, printed pp. 551–554.
    # These are species concentrations, not concentrations expressed as N or P.
    chemicals = [
        ('Acrylamide', .0005, 551, '10^-5 lifetime cancer-risk basis'),
        ('Alachlor', .02, 551, '10^-5 lifetime cancer-risk basis'),
        ('Aldicarb', .01, 551, 'Including sulfoxide and sulfone metabolites'),
        ('Aldrin_and_dieldrin', .00003, 551, 'Combined aldrin plus dieldrin'),
        ('Sb', .02, 551, ''), ('As', .01, 551, 'Provisional: analytical and treatment limitations (A,T)'),
        ('Atrazine', .1, 551, 'Including chloro-s-triazine metabolites'), ('Ba', 1.3, 551, ''),
        ('Benzene', .01, 551, '10^-5 lifetime cancer-risk basis'),
        ('Benzo_a_pyrene', .0007, 551, '10^-5 lifetime cancer-risk basis'), ('B', 2.4, 551, ''),
        ('Bromate', .01, 551, 'Provisional A,T; 10^-5 lifetime cancer-risk basis'),
        ('Bromodichloromethane', .06, 551, '10^-5 lifetime cancer-risk basis'), ('Bromoform', .1, 551, ''),
        ('Cd', .003, 551, ''), ('Carbofuran', .007, 551, ''), ('Carbon_tetrachloride', .004, 551, ''),
        ('Chlorate', .7, 551, 'Provisional: disinfection (D)'), ('Chlordane', .0002, 551, ''),
        ('Free_chlorine', 5., 551, 'Health-based upper guideline; operational residual minima are context-dependent'),
        ('Chlorite', .7, 551, 'Provisional: disinfection (D)'), ('Chloroform', .3, 551, ''),
        ('Chlorotoluron', .03, 551, ''), ('Chlorpyrifos', .03, 551, ''),
        ('Cr_total', .05, 551, 'Total chromium; not a species-specific Cr(VI) limit'), ('Cu', 2., 551, ''),
        ('Cyanazine', .0006, 551, ''),
        ('Cylindrospermopsins', .0007, 552, 'Provisional; total congeners free plus cell-bound; long-term exposure'),
        ('2_4_D', .03, 552, 'Free acid'), ('2_4_DB', .09, 552, ''), ('DDT', .001, 552, 'Including metabolites'),
        ('Dibromoacetonitrile', .07, 552, ''), ('Dibromochloromethane', .1, 552, ''),
        ('1_2_Dibromo_3_chloropropane', .001, 552, '10^-5 lifetime cancer-risk basis'),
        ('1_2_Dibromoethane', .0004, 552, 'Provisional; 10^-5 lifetime cancer-risk basis'),
        ('Dichloroacetate', .05, 552, 'Provisional D; 10^-5 lifetime cancer-risk basis'),
        ('Dichloroacetonitrile', .02, 552, 'Provisional'), ('1_2_Dichlorobenzene', 1., 552, 'Acceptability effects possible below guideline'),
        ('1_4_Dichlorobenzene', .3, 552, 'Acceptability effects possible below guideline'),
        ('1_2_Dichloroethane', .03, 552, '10^-5 lifetime cancer-risk basis'), ('1_2_Dichloroethene', .05, 552, ''),
        ('Dichloromethane', .02, 552, ''), ('1_2_Dichloropropane', .04, 552, 'Provisional'),
        ('1_3_Dichloropropene', .02, 552, '10^-5 lifetime cancer-risk basis'), ('Dichlorprop', .1, 552, ''),
        ('Di_2_ethylhexyl_phthalate', .008, 552, ''), ('Dimethoate', .006, 552, ''), ('1_4_Dioxane', .05, 552, '10^-5 lifetime cancer-risk basis'),
        ('Edetic_acid', .6, 552, 'Free acid'), ('Endrin', .0006, 552, ''), ('Epichlorohydrin', .0004, 552, 'Provisional'),
        ('Ethylbenzene', .3, 552, 'Acceptability effects possible below guideline'), ('Fenoprop', .009, 552, ''),
        ('F', 1.5, 552, 'Consider water consumption and intake from other sources'),
        ('Hexachlorobutadiene', .0006, 552, ''), ('Hydroxyatrazine', .2, 552, 'Atrazine metabolite'), ('Isoproturon', .009, 552, ''),
        ('Pb', .01, 553, 'Provisional: analytical and treatment limitations (A,T)'), ('Lindane', .002, 553, ''),
        ('Mn_total', .08, 553, 'Provisional; total manganese'), ('Mecoprop', .01, 553, ''),
        ('Hg_inorganic', .006, 553, 'Inorganic mercury'), ('Methoxychlor', .02, 553, ''), ('Metolachlor', .01, 553, ''),
        ('Microcystins', .001, 553, 'Provisional; total congeners free plus cell-bound; long-term exposure'),
        ('Molinate', .006, 553, ''), ('Monochloramine', 3., 553, ''), ('Monochloroacetate', .02, 553, ''),
        ('Ni', .07, 553, ''), ('NO3', 50., 553, 'As NO3; also assess combined nitrate/nitrite guideline ratios'),
        ('Nitrilotriacetic_acid', .2, 553, ''), ('NO2', 3., 553, 'As NO2; also assess combined nitrate/nitrite guideline ratios'),
        ('NDMA', .0001, 553, ''), ('Pendimethalin', .02, 553, ''), ('Pentachlorophenol', .009, 553, 'Provisional; 10^-5 lifetime cancer-risk basis'),
        ('Perchlorate', .07, 553, ''), ('Saxitoxins', .003, 553, 'Total congeners; acute exposure'),
        ('Se', .04, 553, 'Provisional'), ('Simazine', .002, 553, ''),
        ('Sodium_dichloroisocyanurate', 50., 553, 'As sodium dichloroisocyanurate'), ('Cyanuric_acid', 40., 553, 'As cyanuric acid'),
        ('Styrene', .02, 553, 'Acceptability effects possible below guideline'), ('2_4_5_T', .009, 553, ''),
        ('Terbuthylazine', .007, 553, ''), ('Tetrachloroethene', .1, 553, ''), ('Toluene', .7, 553, 'Acceptability effects possible below guideline'),
        ('Trichloroacetate', .2, 553, ''), ('Trichloroethene', .008, 554, ''),
        ('2_4_6_Trichlorophenol', .2, 554, '10^-5 lifetime cancer-risk basis; acceptability effects possible'),
        ('Trifluralin', .02, 554, ''), ('U', .03, 554, 'Provisional; chemical toxicity only, not radiological'),
        ('Vinyl_chloride', .0003, 554, '10^-5 lifetime cancer-risk basis'), ('Xylenes', .5, 554, 'Acceptability effects possible below guideline'),
    ]
    who = dict(id='WHO-2026', name=WHO_EDITION, parameters={}, scope='Selected numeric chemical guidelines from Annex 3; not a complete safety assessment.')
    for name, value, page, note in chemicals:
        who['parameters'][name] = dict(unit='mg/L', guideline=_limit(value, edition=WHO_EDITION,
            year=2026, source=WHO_URL, page=str(page), amendment='first, second and third addenda', verification='verified', notes=note))
    # No health-based WHO guideline is not the same as a zero or a BIS limit.
    for name, unit in [('pH', 'pH'), ('TDS', 'mg/L'), ('TH', 'mg/L'), ('Ca', 'mg/L'), ('Mg', 'mg/L'),
                       ('Na', 'mg/L'), ('Cl', 'mg/L'), ('SO4', 'mg/L'), ('Fe', 'mg/L'), ('Zn', 'mg/L')]:
        who['parameters'][name] = dict(unit=unit, guideline=_limit(None, edition=WHO_EDITION,
            year=2026, source=WHO_URL, page='Annex 3, Table A3.2', amendment='first, second and third addenda',
            verification='verified', notes='No health-based guideline established; not included automatically in index calculations.'))
    bis = dict(id='BIS-10500-2012-A4', name=BIS_EDITION, parameters={},
               scope='Amendment documents unavailable at implementation. Values remain unverified and unset until reviewed official limits are imported.',
               amendments=[dict(number=n, year=y, verification='unverified', source='https://standards.bis.gov.in/')
                           for n,y in enumerate([2015, 2018, 2020, 2021], 1)])
    for name, unit in [('pH', 'pH'), ('Turbidity', 'NTU'), *[(n,'mg/L') for n in
                       ['TDS', 'TH', 'Alkalinity', 'Ca', 'Mg', 'Cl', 'SO4', 'NO3', 'F', 'Fe', 'Mn_total',
                        'Cu', 'Zn', 'Al', 'As', 'Pb', 'Cd', 'Cr_total', 'Hg_inorganic', 'Ni', 'Se', 'B', 'Ba', 'U']]]:
        bis['parameters'][name] = dict(unit=unit, **{kind:_limit(None, edition=BIS_EDITION, year=2012,
            source=BIS_URL, page='', amendment='1–4: unverified', verification='unverified',
            notes='Not verified against the original and all four amendment documents. No inferred value.')
            for kind in ('acceptable', 'permissible')})
    return {who['id']: who, bis['id']: bis}


def validate_standard(profile):
    if not isinstance(profile, dict) or not all(isinstance(profile.get(k), str) and profile[k].strip() for k in ('id', 'name')):
        raise ValueError('A standards profile requires id and name.')
    if not isinstance(profile.get('parameters'), dict) or not profile['parameters']:
        raise ValueError('A standards profile requires named parameters.')
    for name, p in profile['parameters'].items():
        unit_factor(p.get('unit'), p.get('unit'))
        kinds = [k for k in ('acceptable', 'permissible', 'guideline') if k in p]
        if not kinds:
            raise ValueError(f'{name}: specify acceptable/permissible limits or a guideline.')
        for kind in kinds:
            limit = p[kind]
            for key in ('edition', 'publication_year', 'source', 'amendment', 'verification'):
                if limit.get(key) in (None, ''):
                    raise ValueError(f'{name}/{kind}: missing {key} provenance.')
            if limit['verification'] not in ('verified', 'unverified'):
                raise ValueError('Verification must be verified or unverified.')
            for key in ('lower', 'upper'):
                v = limit.get(key)
                if v is not None and (not isinstance(v,(int,float)) or isinstance(v,bool) or not np.isfinite(v) or v < 0):
                    raise ValueError(f'{name}/{kind}: invalid {key} limit.')
            if limit.get('lower') is not None and limit.get('upper') is not None and limit['lower'] >= limit['upper']:
                raise ValueError(f'{name}/{kind}: limits must be ordered.')
        a, pmax = p.get('acceptable', {}), p.get('permissible', {})
        if a.get('upper') is not None and pmax.get('upper') is not None and a['upper'] > pmax['upper']:
            raise ValueError(f'{name}: permissible upper limit cannot be below acceptable.')
    return deepcopy(profile)


def import_standard(path):
    """Read reviewed transcriptions with per-limit provenance, not automatic PDF guesses."""
    path = Path(path)
    if path.suffix.lower() == '.json':
        return validate_standard(json.loads(path.read_text(encoding='utf-8-sig')))
    if path.suffix.lower() != '.csv':
        raise ValueError('Import a reviewed JSON or CSV transcription. Record the official document URL and page for each limit.')
    rows = list(csv.DictReader(path.open(encoding='utf-8-sig', newline='')))
    if not rows:
        raise ValueError('The standards CSV is empty.')
    profile = dict(id=rows[0].get('standard_id', ''), name=rows[0].get('standard_name', ''), parameters={})
    for row in rows:
        if row.get('standard_id') != profile['id'] or row.get('standard_name') != profile['name']:
            raise ValueError('One CSV must describe one standards profile.')
        name, kind = row['parameter'], row['limit_kind']
        if kind not in ('acceptable', 'permissible', 'guideline'):
            raise ValueError('Unknown limit_kind.')
        p = profile['parameters'].setdefault(name, dict(unit=row['unit']))
        if p['unit'] != row['unit'] or kind in p:
            raise ValueError('Duplicate limit or inconsistent units in standards CSV.')
        p[kind] = {k:row.get(k, '') for k in ('edition', 'publication_year', 'source', 'page', 'amendment', 'verification', 'notes')}
        p[kind].update({k:float(row[k]) if row.get(k, '').strip() else None for k in ('lower', 'upper')})
    return validate_standard(profile)


def mapped_parameters(frame, standard, kind='guideline', method='brown'):
    """Conservative exact-name suggestions; never silently equate different species."""
    result = []
    for name, definition in standard['parameters'].items():
        limit = definition.get(kind)
        if name not in frame or not limit or (limit.get('lower') is None and limit.get('upper') is None):
            continue
        result.append(dict(name=name, column=name, unit=definition['unit'], standard_unit=definition['unit'],
                           weight=1., ideal=7. if name == 'pH' else 0., rating='ideal' if method == 'brown' else 'ratio',
                           standard_id=standard['id'], limit_kind=kind, **deepcopy(limit)))
    return result
