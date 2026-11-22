"""Compare AquaProv v1.0 exports with the independent reference and external PHREEQC.

Inputs: aquaprov_exports/*.csv, reference_values.csv, phreeqc_si.csv, phreeqc_si_db373.csv
Outputs: comparison_by_well.csv, comparison_summary.csv, table_S4.md
"""
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
A = HERE / 'aquaprov_exports'
MINERALS = ['Calcite', 'Dolomite', 'Gypsum', 'Fluorite']

ref = pd.read_csv(HERE / 'reference_values.csv')
order = ref['Sl. No.'].tolist()
q = pd.read_csv(A / 'aquaprov_quality_by_sample.csv').set_index('Sl. No.')
s = pd.read_csv(A / 'aquaprov_sar.csv').set_index('Sl. No.')
w = pd.read_csv(A / 'aquaprov_wqi_dwqi.csv').set_index('Sl. No.')
si = pd.read_csv(A / 'aquaprov_saturation_indices.csv')
si = si.assign(**{'Sl. No.': si['sample'].astype(int)}).pivot(index='Sl. No.', columns='mineral', values='SI')
ext = pd.read_csv(HERE / 'phreeqc_si.csv').set_index('Sl. No.')
ext373 = pd.read_csv(HERE / 'phreeqc_si_db373.csv').set_index('Sl. No.')

rows = []
for _, r in ref.iterrows():
    n = r['Sl. No.']
    row = {'Sl. No.': n, 'site': r.site, 'type': r.type, 'TDS_mg_L': r.TDS_mg_L, 'Cr_total_ug_L': r.Cr_total_ug_L}
    for metric, aq, rv in [('CBE_percent', q.loc[n, 'major_ion_CBE_percent'], r.CBE_percent),
                           ('SAR', s.loc[n, 'SAR'], r.SAR), ('WQI', w.loc[n, 'WQI'], r.WQI),
                           ('DWQI', w.loc[n, 'DWQI'], r.DWQI)]:
        row[f'{metric}_AquaProv'], row[f'{metric}_reference'], row[f'{metric}_delta'] = aq, rv, aq - rv
    for m in MINERALS:
        aq = si.loc[n, m] if m in si.columns else float('nan')
        e, e373 = ext.loc[n, 'SI_' + m], ext373.loc[n, 'SI_' + m]
        row[f'SI_{m}_AquaProv'], row[f'SI_{m}_PHREEQC386'], row[f'SI_{m}_delta'] = aq, e, aq - e
        row[f'SI_{m}_PHREEQC386_db373'], row[f'SI_{m}_delta_db373'] = e373, aq - e373
    rows.append(row)
by_well = pd.DataFrame(rows)
by_well.to_csv(HERE / 'comparison_by_well.csv', index=False)

summary = []
for metric in ['CBE_percent', 'SAR', 'WQI', 'DWQI']:
    d = by_well[f'{metric}_delta'].abs()
    summary.append(dict(metric=metric, comparison='AquaProv vs independent Python reference',
                        n=int(d.notna().sum()), max_abs_delta=d.max()))
for m in MINERALS:
    for tag, label in [('', 'AquaProv vs USGS PHREEQC 3.8.6 + phreeqc.dat 3.8.6'),
                       ('_db373', 'AquaProv vs USGS PHREEQC 3.8.6 + phreeqc.dat 3.7.3 (AquaProv bundle)')]:
        d = by_well[f'SI_{m}_delta{tag}'].abs()
        both_undefined = int((by_well[f'SI_{m}_AquaProv'].isna() & by_well[f'SI_{m}_PHREEQC386{tag}'].isna()).sum())
        summary.append(dict(metric=f'SI_{m}', comparison=label, n=int(d.notna().sum()),
                            max_abs_delta=d.max(), undefined_in_both=both_undefined))
summary = pd.DataFrame(summary)
summary.to_csv(HERE / 'comparison_summary.csv', index=False)


def f(v, p):
    return '–' if pd.isna(v) else f'{v:.{p}f}'


def e(v):
    return '–' if pd.isna(v) else f'{v:.1e}'


lines = ['**Table S4.** External numerical verification of AquaProv v1.0 for eight Sukinda wells. '
         'CBE, SAR, WQI and DWQI: AquaProv versus an independent standard-library/NumPy implementation. '
         'SI: AquaProv (IPhreeqc 3.7.3, bundled phreeqc.dat 3.7.3) versus the standalone USGS PHREEQC 3.8.6-17100 '
         'batch executable with its distributed phreeqc.dat.', '',
         '(a) Charge balance, SAR and indices (AquaProv / reference)', '',
         '| Sl. No. | Site (type) | TDS (mg/L) | Total Cr (µg/L) | CBE (%) | SAR | WQI | DWQI |',
         '|---:|---|---:|---:|---|---|---|---|']
for _, r in by_well.iterrows():
    lines.append(f"| {r['Sl. No.']} | {r.site} ({r.type}) | {r.TDS_mg_L:g} | {r.Cr_total_ug_L:g} | "
                 f"{f(r.CBE_percent_AquaProv, 3)} / {f(r.CBE_percent_reference, 3)} | "
                 f"{f(r.SAR_AquaProv, 4)} / {f(r.SAR_reference, 4)} | "
                 f"{f(r.WQI_AquaProv, 4)} / {f(r.WQI_reference, 4)} | {f(r.DWQI_AquaProv, 4)} / {f(r.DWQI_reference, 4)} |")
mx = summary.set_index(['metric', 'comparison']).max_abs_delta
ref_label = 'AquaProv vs independent Python reference'
lines.append(f"| **max \\|Δ\\|** | | | | **{e(mx[('CBE_percent', ref_label)])}** | **{e(mx[('SAR', ref_label)])}** | "
             f"**{e(mx[('WQI', ref_label)])}** | **{e(mx[('DWQI', ref_label)])}** |")
lines += ['', '(b) Mineral saturation indices (AquaProv / external PHREEQC 3.8.6)', '',
          '| Sl. No. | Calcite | Dolomite | Gypsum | Fluorite |', '|---:|---|---|---|---|']
for _, r in by_well.iterrows():
    lines.append(f"| {r['Sl. No.']} | " + ' | '.join(
        f"{f(r[f'SI_{m}_AquaProv'], 3)} / {f(r[f'SI_{m}_PHREEQC386'], 3)}" for m in MINERALS) + ' |')
l386 = 'AquaProv vs USGS PHREEQC 3.8.6 + phreeqc.dat 3.8.6'
l373 = 'AquaProv vs USGS PHREEQC 3.8.6 + phreeqc.dat 3.7.3 (AquaProv bundle)'
lines.append('| **max \\|ΔSI\\|**, phreeqc.dat 3.8.6 | ' + ' | '.join(f"**{f(mx[(f'SI_{m}', l386)], 3)}**" for m in MINERALS) + ' |')
lines.append('| **max \\|ΔSI\\|**, same phreeqc.dat 3.7.3 | ' + ' | '.join(f"**{e(mx[(f'SI_{m}', l373)])}**" for m in MINERALS) + ' |')
lines += ['', 'Notes: Well identifiers are the workbook "Sl. No." values. CBE uses Ca, Mg, Na, K, HCO3, CO3, Cl and SO4; '
          'the reference uses IUPAC (CIAAW 2021) standard atomic weights. WQI uses inverse-standard weights and DWQI '
          'equal importance weights, with WHO (2026) objectives of 50 mg/L NO3 and 1.5 mg/L F. PHREEQC conditions: '
          '25 °C, density 1 kg/L, pe 4, alkalinity as CaCO3, reported mg/L concentrations. Fluorite SI is undefined '
          '(–) for Sl. No. 15, which reports F = 0, in both AquaProv and PHREEQC.']
(HERE / 'table_S4.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(summary.to_string())
print('\n'.join(lines))
