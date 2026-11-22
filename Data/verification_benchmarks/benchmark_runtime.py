"""Wall-clock runtime benchmark for AquaProv v1.0 workflows.

Each workflow runs four times in one process after module imports: the first call
(cold within the process: file reads, caches, IPhreeqc/database load) and three
repeats. The table reports the median of the three repeats and the first call.
Writes runtime_benchmarks.csv, runtime_environment.json and table_S5.md.
Run:  .venv-build-min/Scripts/python.exe benchmark_runtime.py
"""
from pathlib import Path
from copy import deepcopy
import ctypes
import json
import os
import platform
import statistics
import sys
import tempfile
import time
import winreg

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import aquaprovpy
from aquaprovpy import contour_piper
from aquaprovpy.core.data import normalize_headers
from aquaprovpy.assessment.measurements import suggest_schema
from aquaprovpy.assessment.engine import plot as assess
from aquaprovpy.saturation.engine import calculate as si_calculate
from aquaprov_exports import si_config

SUKINDA = ROOT / 'data/Sukinda_CGWB_Data_2024.xlsx'
YANG = ROOT / 'data/data_Yang_et_al_2020.csv'
MORENO = ROOT / 'data/data_Moreno_Merino _et_al_2021.csv'
REPEATS = 3


def environment():
    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0')
    cpu = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()

    class MEM(ctypes.Structure):
        _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
    m = MEM(); m.dwLength = ctypes.sizeof(MEM)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    import matplotlib as mpl, scipy, sklearn
    return dict(cpu=cpu, logical_processors=os.cpu_count(), ram_GB=round(m.ullTotalPhys / 1024**3, 1),
                os=platform.platform(), python=platform.python_version(), aquaprov=aquaprovpy.__version__,
                numpy=np.__version__, pandas=pd.__version__, matplotlib=mpl.__version__,
                scipy=scipy.__version__, scikit_learn=sklearn.__version__,
                date=time.strftime('%Y-%m-%d %H:%M:%S'))


def sukinda_inputs():
    raw = pd.read_excel(SUKINDA)
    selected = raw.loc[raw['Type of Well'].isin(['HP', 'TW', 'DW', 'BW'])].copy()
    frame, renamed = normalize_headers(selected.copy())
    schema = suggest_schema(frame)
    schema['fields'] = {k: v for k, v in schema['fields'].items()
                        if k in ('Ca', 'Mg', 'Na', 'K', 'HCO3', 'CO3', 'Cl', 'SO4', 'NO3', 'F', 'pH', 'TDS', 'EC')}
    schema['metadata'].update(sample=renamed.get('Sl. No.', 'Sl. No.'),
                              x=renamed.get('Longitude (°E)', 'Longitude (°E)'),
                              y=renamed.get('Latitude (°N)', 'Latitude (°N)'))
    schema['unit_assumptions_confirmed'] = True
    return raw, selected, frame, schema


def main():
    raw, selected, frame, schema = sukinda_inputs()
    cfg_si = si_config(raw, selected)
    spatial_schema = deepcopy(schema)
    spatial_schema['crs'] = 'EPSG:4326 (assumed from longitude/latitude headings)'
    tmp = Path(tempfile.mkdtemp(prefix='aquaprov_bench_'))

    def phreeqc():
        r = si_calculate(selected, cfg_si)
        assert len(r.tables['saturation_indices']) == 140

    def spatial():
        r = assess(frame, dict(schema=spatial_schema, view='spatial', column='TDS', coordinates='wgs84',
                               folds=5, seed=42, model='spherical'))
        assert set(r.tables['spatial_scores'].method) >= {'kriging', 'IDW'}
        plt.close(r.figure)

    def screening(draws):
        def run():
            r = assess(frame, dict(schema=schema, view='screening', draws=draws, seed=42, uncertainty='scenario',
                                   relative_sd=.1, censoring='exclude', error_correlation=0.0))
            sar = r.tables['metric_intervals'].query("metric == 'SAR'")
            assert len(sar) == 35
            plt.close(r.figure)
        return run

    def yang():
        y = pd.read_csv(YANG)
        r = assess(y, dict(schema=suggest_schema(y), view='qa'))
        st = r.tables['measurement_status']
        assert int(st.loc[st.status == 'nondetect_unknown_limit', 'count'].sum()) == 392
        plt.close(r.figure)

    def moreno_cbe():
        m = pd.read_csv(MORENO)
        s = suggest_schema(m)
        s['fields'] = {k: v for k, v in s['fields'].items() if k in ('Ca', 'Mg', 'Na', 'K', 'HCO3', 'CO3', 'Cl', 'SO4')}
        s['metadata']['sample'] = 'Sample'
        r = assess(m, dict(schema=s, view='qa', balance_tolerance=5))
        cbe = r.tables['quality_by_sample'].major_ion_CBE_percent
        assert len(cbe) == 2124 and int((cbe.abs() > 5).sum()) == 672
        plt.close(r.figure)

    moreno_frame = pd.read_csv(MORENO)

    def moreno_piper():
        plt.close('all')
        contour_piper.plot(moreno_frame, unit='mg/L', figname=str(tmp / 'moreno_density'), figformat='png')
        plt.close('all')

    workflows = [
        ('Sukinda', 35, 'PHREEQC speciation and SI (IPhreeqc; 4 minerals)', phreeqc),
        ('Sukinda', 35, '5-block spatial CV of TDS (ordinary kriging, IDW, training mean)', spatial),
        ('Sukinda', 35, 'Monte Carlo SAR uncertainty, 2,000 draws', screening(2000)),
        ('Sukinda', 35, 'Monte Carlo SAR uncertainty, 10,000 draws', screening(10000)),
        ('Yang et al. (2020)', 1184, 'CSV ingestion + quality/nondetect review', yang),
        ('Moreno Merino et al. (2021)', 2124, 'CSV ingestion + 8-ion CBE review', moreno_cbe),
        ('Moreno Merino et al. (2021)', 2124, 'Contour-filled (density) Piper, render and save PNG', moreno_piper),
    ]
    rows = []
    for dataset, n, name, fn in workflows:
        times = []
        for _ in range(REPEATS + 1):
            t0 = time.perf_counter()
            fn()
            times.append(time.perf_counter() - t0)
        rows.append(dict(dataset=dataset, records=n, workflow=name, first_call_s=times[0],
                         repeat_1_s=times[1], repeat_2_s=times[2], repeat_3_s=times[3],
                         median_repeat_s=statistics.median(times[1:])))
        print(f'{dataset:28s} {name:70s} first {times[0]:8.3f}  median {rows[-1]["median_repeat_s"]:8.3f}', flush=True)
    table = pd.DataFrame(rows)
    table.to_csv(HERE / 'runtime_benchmarks.csv', index=False)
    env = environment()
    (HERE / 'runtime_environment.json').write_text(json.dumps(env, indent=2), encoding='utf-8')

    fmt = lambda v: f'{v:.2f}' if v >= 0.1 else f'{v:.3f}'
    lines = ['**Table S5.** Wall-clock runtimes of AquaProv v1.0 workflows (median of three repeats; first call in parentheses).', '',
             '| Dataset | Records | Workflow | Median time (s) | First call (s) |', '|---|---:|---|---:|---:|']
    for r in rows:
        lines.append(f"| {r['dataset']} | {r['records']:,} | {r['workflow']} | {fmt(r['median_repeat_s'])} | {fmt(r['first_call_s'])} |")
    lines += ['', f"Environment: {env['cpu']} ({env['logical_processors']} logical processors), {env['ram_GB']} GB RAM, "
              f"{env['os']}; Python {env['python']}, AquaProv {env['aquaprov']}, NumPy {env['numpy']}, pandas {env['pandas']}, "
              f"Matplotlib {env['matplotlib']}, SciPy {env['scipy']}, scikit-learn {env['scikit_learn']}. "
              'Times are single-process wall-clock (time.perf_counter) after module import; the first call includes '
              'in-process initialization such as database loading. Monte Carlo runs use a 10% relative standard deviation '
              'scenario, seed 42, and compute SAR together with the other screening metrics. The Piper time includes the '
              'kernel density evaluation, rendering and writing a PNG file.']
    (HERE / 'table_S5.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(env, indent=2))


if __name__ == '__main__':
    main()
