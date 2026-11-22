"""Export AquaProv v1.0 results for the 35 Sukinda wells through its public APIs.

Same settings as the manuscript figures (scripts/make_plot_composites.py and
scripts/run_worked_applications.py). Writes aquaprov_exports/*.csv.
Run with the AquaProv environment:  .venv-build-min/Scripts/python.exe aquaprov_exports.py
"""
from pathlib import Path
from copy import deepcopy
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
import aquaprovpy
from aquaprovpy.core.data import normalize_headers
from aquaprovpy.assessment.measurements import suggest_schema
from aquaprovpy.assessment.engine import plot as assess
from aquaprovpy import ussl
from aquaprovpy.water_quality.standards import built_in_standards, mapped_parameters
from aquaprovpy.water_quality.common import SCHEMES
from aquaprovpy.water_quality.plots import plot as wq_plot
from aquaprovpy.saturation.automatic import chemistry_mapping
from aquaprovpy.saturation.engine import calculate as si_calculate

SOURCE = ROOT / 'data/Sukinda_CGWB_Data_2024.xlsx'


def load():
    raw = pd.read_excel(SOURCE)
    selected = raw.loc[raw['Type of Well'].isin(['HP', 'TW', 'DW', 'BW'])].copy()
    assert len(selected) == 35
    frame, renamed = normalize_headers(selected.copy())
    return raw, selected, frame, renamed


def charge_balance(frame, renamed):
    schema = suggest_schema(frame)
    schema['fields'] = {k: v for k, v in schema['fields'].items()
                        if k in ('Ca', 'Mg', 'Na', 'K', 'HCO3', 'CO3', 'Cl', 'SO4', 'NO3', 'F', 'pH', 'TDS', 'EC')}
    schema['metadata'].update(sample=renamed.get('Sl. No.', 'Sl. No.'))
    schema['unit_assumptions_confirmed'] = True
    result = assess(frame, dict(schema=schema, view='qa', balance_tolerance=5))
    plt.close(result.figure)
    return result.tables['quality_by_sample']


def sar(frame):
    result = ussl.plot(frame.copy(), figname=None, unit='mg/L', ec_unit='uS/cm')
    plt.close(result.figure)
    return result.tables['samples']


def indices(frame, renamed, raw):
    x = renamed.get(raw.columns[3], raw.columns[3])
    y = renamed.get(raw.columns[4], raw.columns[4])
    index_frame = frame[['Sample', x, y, 'NO3', 'F']].copy()
    index_frame['Sample'] = index_frame['Sample'].astype(str)
    standard = built_in_standards()['WHO-2026']
    profiles = {
        name: dict(method=method, parameters=mapped_parameters(index_frame, standard, method=method),
                   scheme=deepcopy(SCHEMES[scheme]), standard_id=standard['id'],
                   standard_name=standard['name'], limit_kind='guideline')
        for name, method, scheme in [('WQI', 'brown', 'arithmetic'), ('DWQI', 'ramakrishnaiah', 'relative')]
    }
    config = dict(index='WQI', profiles=profiles, site_column='Sample', x=x, y=y,
                  coordinates='wgs84', source_crs='EPSG:4326', basemap='plain',
                  point_labels=False, show_grid=False, sample_size=14,
                  spatial=dict(method='idw', resolution=60, power=2), extrapolate=False, view='comparison')
    result = wq_plot(index_frame, config)
    plt.close(result.figure)
    a = result.tables['WQI_samples'][['source_row', 'WQI']]
    b = result.tables['DWQI_samples'][['source_row', 'DWQI']]
    return a.merge(b, on='source_row', how='outer')


def si_config(raw, selected):
    parameters, assumptions, problems = chemistry_mapping(selected)
    assert not problems, problems
    keep = {'Ca', 'Mg', 'Na', 'K', 'Cl', 'SO4', 'Alkalinity', 'NO3', 'F'}
    parameters = [p for p in parameters if p['name'] in keep]
    return dict(mode='calculate', chemistry_setup='automatic', chemistry_reviewed=False,
                parameters=parameters, minerals=['Calcite', 'Dolomite', 'Gypsum', 'Fluorite'],
                sample_column='Sl. No.', pH_column=raw.columns[7], database='phreeqc.dat',
                temperature_c=25., density_kg_L=1., redox='none', missing='drop',
                mineral='Calcite', scatter_x_mineral='Dolomite', annotate=False, sample_size=14)


def saturation(raw, selected):
    calculated = si_calculate(selected, si_config(raw, selected))
    table = calculated.tables['saturation_indices'] if hasattr(calculated, 'tables') else calculated['saturation_indices']
    return table


def main():
    raw, selected, frame, renamed = load()
    out = HERE / 'aquaprov_exports'
    out.mkdir(exist_ok=True)
    ids = selected['Sl. No.'].astype(int).to_numpy()
    q = charge_balance(frame, renamed)
    q.insert(0, 'Sl. No.', ids)
    q.to_csv(out / 'aquaprov_quality_by_sample.csv', index=False)
    s = sar(frame)
    s.insert(0, 'Sl. No.', ids)
    s.to_csv(out / 'aquaprov_sar.csv', index=False)
    w = indices(frame, renamed, raw).sort_values('source_row')
    w.insert(0, 'Sl. No.', ids[w.source_row.to_numpy() - 1])
    w.to_csv(out / 'aquaprov_wqi_dwqi.csv', index=False)
    si = saturation(raw, selected)
    si.to_csv(out / 'aquaprov_saturation_indices.csv', index=False)
    (out / 'aquaprov_version.txt').write_text(f'AquaProv {aquaprovpy.__version__}\n', encoding='utf-8')
    print('exported', [p.name for p in out.iterdir()])


if __name__ == '__main__':
    main()
