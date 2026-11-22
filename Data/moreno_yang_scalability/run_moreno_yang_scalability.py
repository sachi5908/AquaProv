"""Large-sample check on Moreno Merino et al. (2021) and Yang et al. (2020).

Moreno Merino: contour-filled (density) Piper runtime and charge-balance review
on all source records. Yang: nondetect, duplicate and coordinate-system
diagnostics. All values come from AquaProv APIs; nothing is imputed.
"""
from pathlib import Path
import sys, json, time, hashlib, platform, statistics
from copy import deepcopy
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import aquaprovpy
from aquaprovpy import contour_piper
from aquaprovpy.assessment.measurements import suggest_schema
from aquaprovpy.assessment.engine import plot as assess

OUT = ROOT / 'Manuscript/supporting_materials/evidence/moreno_yang_scalability'
OUT.mkdir(parents=True, exist_ok=True)
summary = dict(aquaprov_version=aquaprovpy.__version__, python=platform.python_version(),
               platform=platform.platform(), processor=platform.processor())

# ---------------- Moreno Merino ----------------
src = ROOT / 'data/data_Moreno_Merino _et_al_2021.csv'
moreno = pd.read_csv(src)
m = dict(source_file=str(src.relative_to(ROOT)), source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
         rows=len(moreno), columns=list(moreno.columns))
ions = ['Ca', 'Mg', 'Na', 'K', 'HCO3', 'CO3', 'Cl', 'SO4']
m['missing_major_ion_values'] = int(moreno[ions].isna().sum().sum())
m['CO3_zero_records'] = int((moreno.CO3 == 0).sum())
m['CO3_nonzero_records'] = int((moreno.CO3 != 0).sum())
m['has_pH'] = 'pH' in moreno.columns
m['has_coordinates'] = any(c.lower() in ('x', 'y', 'lat', 'latitude', 'lon', 'longitude') for c in moreno.columns)

timings = []
for i in range(4):  # run 0 includes first-call overhead; runs 1-3 are repeats
    plt.close('all')
    t0 = time.perf_counter()
    contour_piper.plot(moreno, unit='mg/L', figname=str(OUT / f'moreno_density_piper_run{i}'), figformat='png')
    timings.append(time.perf_counter() - t0)
    plt.close('all')
m['density_piper_seconds_first'] = timings[0]
m['density_piper_seconds_repeats'] = timings[1:]
m['density_piper_seconds_median_repeat'] = statistics.median(timings[1:])
for i in range(1, 4):
    (OUT / f'moreno_density_piper_run{i}.png').unlink()
(OUT / 'moreno_density_piper_run0.png').rename(OUT / 'moreno_density_piper.png')

schema = suggest_schema(moreno)
schema['fields'] = {k: v for k, v in schema['fields'].items() if k in ions}
schema['metadata']['sample'] = 'Sample'
t0 = time.perf_counter()
qa = assess(moreno, dict(schema=schema, view='qa', balance_tolerance=5))
m['qa_seconds'] = time.perf_counter() - t0
qa.export(OUT, 'moreno_quality')
plt.close(qa.figure)
q = qa.tables['quality_by_sample']
cbe = q.major_ion_CBE_percent
m.update(complete_major_balances=int(cbe.notna().sum()),
         cbe_over_5=int((cbe.abs() > 5).sum()), cbe_over_10=int((cbe.abs() > 10).sum()),
         cbe_within_5=int((cbe.abs() <= 5).sum()),
         cbe_min=float(cbe.min()), cbe_median=float(cbe.median()), cbe_max=float(cbe.max()),
         cbe_median_abs=float(cbe.abs().median()),
         duplicate_chemistry=int(q.duplicate_chemistry.sum()),
         measurement_status=qa.tables['measurement_status'].to_dict('records'),
         warnings=qa.warnings)
summary['moreno'] = m

# ---------------- Yang ----------------
src = ROOT / 'data/data_Yang_et_al_2020.csv'
yang = pd.read_csv(src)
y = dict(source_file=str(src.relative_to(ROOT)), source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
         rows=len(yang), wells=int(yang.Well.nunique()))
ys = suggest_schema(yang)
yq = assess(yang, dict(schema=ys, view='qa'))
plt.close(yq.figure)
yq.export(OUT, 'yang_quality')
st = yq.tables['measurement_status']
y['nondetect_unknown_limit'] = st[st.status == 'nondetect_unknown_limit'][['analyte', 'count']].to_dict('records')
y['nondetect_total'] = int(st[st.status == 'nondetect_unknown_limit']['count'].sum())
yqs = yq.tables['quality_by_sample']
rk = yqs[yqs.repeated_record_key]
dc = yqs[yqs.duplicate_chemistry]
y['repeated_record_key_rows'] = int(len(rk))
y['repeated_record_key_groups'] = rk[['well', 'time', 'season']].drop_duplicates().astype(str).to_dict('records')
y['duplicate_chemistry_rows'] = int(len(dc))
y['duplicate_chemistry_records'] = dc[['well', 'time', 'season']].astype(str).to_dict('records')
y['complete_major_balances'] = int(yqs.major_ion_CBE_percent.notna().sum())
y['has_CO3'] = 'CO3' in yang.columns
y['schema_crs'] = ys['crs']
y['x_range'] = [float(yang.X.min()), float(yang.X.max())]
y['y_range'] = [float(yang.Y.min()), float(yang.Y.max())]

# Spatial attempts: geographic interpretation and projected interpretation without a CRS.
attempts = {}
for label, cfg in [('wgs84', dict(coordinates='wgs84')),
                   ('projected_no_crs', dict(coordinates='projected')),
                   ('projected_auto_utm', dict(coordinates='auto_utm'))]:
    try:
        r = assess(yang, dict(schema=deepcopy(ys), view='spatial', column='Cl', folds=5, seed=42,
                              model='spherical', **cfg))
        crs_table = r.tables.get('spatial_coordinate_system')
        attempts[label] = dict(status='ran', analysis_crs=None if crs_table is None else
                               str(crs_table.iloc[0].get('analysis_crs')), warnings=r.warnings)
        plt.close(r.figure)
    except Exception as exc:
        attempts[label] = dict(status='refused', message=str(exc))
y['spatial_attempts'] = attempts
summary['yang'] = y

(OUT / 'summary.json').write_text(json.dumps(summary, indent=2, default=str), encoding='utf-8')
print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ('warnings', 'columns', 'measurement_status')}
                  if isinstance(v, dict) else v for k, v in summary.items()}, indent=1, default=str))
