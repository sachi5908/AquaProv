# AquaProv v1.0 external verification and runtime benchmarks

Supports Section 4.1 and Tables S4–S5 of Mahanta et al. Every number in the tables was produced by running the scripts below; nothing is estimated.

## Selected Sukinda wells (workbook `Sl. No.`)

Eight of the 35 HP/TW/DW/BW wells in `data/Sukinda_CGWB_Data_2024.xlsx`:

| Sl. No. | Site | Reason for inclusion |
|---:|---|---|
| 15 | Guakata (HP) | Lowest TDS (34.93 mg/L); \|CBE\| > 10%; reports F = 0, so Fluorite SI is undefined (an agreement check) |
| 9 | Kaliapani Township (HP) | Highest TDS (333.3 mg/L); calcite and dolomite supersaturated |
| 1 | Kamarda TW (TW) | Total Cr 159.2 µg/L (> 50 µg/L) |
| 6 | Patna HP 2 (HP) | Total Cr 427.3 µg/L (> 50 µg/L) |
| 7 | Gurujang (HP) | Total Cr 51.7 µg/L (> 50 µg/L) |
| 3 | Talangi HP (HP) | \|CBE\| > 10%; highest DWQI of the set |
| 39 | Ragada HP (HP) | Most negative CBE (−7.5%) |
| 12 | Chingudipal (HP) | \|CBE\| > 5%; highest calcite SI |

Seven wells have finite Calcite, Dolomite, Gypsum and Fluorite SI. Bhimtangar TW 3 (Sl. No. 17, total Cr 105.4 µg/L) was not selected, because it also reports F = 0.

## Files

| File | Purpose | Dependencies |
|---|---|---|
| `independent_reference.py` | First-principles CBE (8 ions, CIAAW 2021 atomic weights), SAR, WQI (inverse-standard weights) and DWQI (equal importance), with WHO 2026 objectives (NO3 50 mg/L, F 1.5 mg/L). Reads the workbook XML directly and writes `selected_wells_input.csv`, `reference_values.csv` and `sukinda_verification.pqi`. | Python stdlib + NumPy (no AquaProv) |
| `run_external_phreeqc.py` | Runs `sukinda_verification.pqi` with the standalone USGS PHREEQC batch executable and parses SI into `phreeqc_si*.csv`. | Python stdlib |
| `sukinda_verification.pqi` | PHREEQC input file: phreeqc.dat, 25 °C, density 1 kg/L, pe 4, alkalinity as CaCO3, reported mg/L concentrations. | – |
| `sukinda_verification.pqo`, `sukinda_verification_selected.tsv` | PHREEQC 3.8.6-17100 output with its distributed `phreeqc.dat` (3.8.6). | – |
| `sukinda_verification_db373.pqo`, `*_db373_selected.tsv` | Same executable with the `phreeqc.dat` 3.7.3 file bundled in AquaProv, to separate engine effects from database-release effects. | – |
| `phreeqc_run_metadata*.json` | Executable and database paths, SHA-256 hashes and version header. | – |
| `aquaprov_exports.py`, `aquaprov_exports/` | Fresh AquaProv v1.0 exports (CBE, SAR, WQI/DWQI, SI) for all 35 wells, using the manuscript settings. | AquaProv environment |
| `compare.py` | Per-well differences and max \|Δ\|: `comparison_by_well.csv`, `comparison_summary.csv`, `table_S4.md`. | pandas |
| `benchmark_runtime.py` | Wall-clock benchmarks: `runtime_benchmarks.csv`, `runtime_environment.json`, `table_S5.md`. | AquaProv environment |

## Reproduce (Windows, from this folder)

```
python -I independent_reference.py
python -I run_external_phreeqc.py <PHREEQC_HOME>
python -I run_external_phreeqc.py <PHREEQC_HOME> <AquaProv>/aquaprovpy/saturation/resources/phreeqc.dat db373
<AquaProv>/.venv-build-min/Scripts/python.exe aquaprov_exports.py
<AquaProv>/.venv-build-min/Scripts/python.exe compare.py
<AquaProv>/.venv-build-min/Scripts/python.exe benchmark_runtime.py
```

`<PHREEQC_HOME>` is the folder containing `bin/Release/phreeqc.exe` and `database/phreeqc.dat` from the official USGS installer `phreeqc-3.8.6-17100-x64.msi` (https://water.usgs.gov/water-resources/software/PHREEQC/index.html; SHA-256 6e5f6697fa727f919eb4e7c1c2bc20e8c2717378aaf77731efd831ef66578243). Here the installer was unpacked without a system installation (`msiexec /a phreeqc-3.8.6-17100-x64.msi /qn TARGETDIR=...`). This is the USGS batch program, not AquaProv's internal IPhreeqc library.

## Results summary (22 November 2026)

- CBE, SAR, WQI and DWQI (8 wells, AquaProv vs independent reference): max |Δ| = 0.0033 percentage points, 1.9 × 10⁻⁶, 0 and 0. The CBE difference comes from molar masses: AquaProv uses WQChartPy values (e.g. Cl 35.4527, SO4 96.0636 g/mol); the reference uses CIAAW 2021 values (Cl 35.45, SO4 96.056 g/mol).
- SI (AquaProv/IPhreeqc 3.7.3 vs USGS PHREEQC 3.8.6-17100 batch): max |ΔSI| = 0.018 (Calcite), 0.022 (Dolomite), 0.006 (Gypsum) and 0.014 (Fluorite, 7 wells) with phreeqc.dat 3.8.6; 0 for all four minerals when the external executable uses the phreeqc.dat 3.7.3 file bundled with AquaProv. The residual differences therefore come from the database release, not from the engine or the input translation.
- Runtimes: see `table_S5.md`.

### Runtime variability note

Section 4.4 currently reports 9.2 s for the Moreno Merino density Piper (median of 3; 10.2 s first call) and 0.5 s for the CBE review, measured about an hour before this benchmark in a separate process (`evidence/moreno_yang_scalability/summary.json`). This benchmark measured 6.40 s and 0.26 s. A fresh-process re-run of the original Piper timing, immediately afterwards and with identical code, gave 6.39 s (runs: 7.55, 6.39, 6.38, 6.50 s), so the difference reflects machine state on the laptop (background load or thermal/power conditions), not the method. The earlier 0.48 s CBE time was the first assessment call in its process, which includes lazy initialization; here, earlier workflows had already initialized the engine.

## Location in the submission package

In this package, the input datasets are in `../Data/`, and the Section 4.4 large-sample outputs (Moreno Merino and Yang) are in `../Data/moreno_yang_scalability/`. The scripts were run from the AquaProv project tree (`Manuscript/supporting_materials/verification_benchmarks/`). To re-run them, place this folder there, or pass the workbook path explicitly, e.g. `python -I independent_reference.py ../Data/Sukinda_CGWB_Data_2024.xlsx`. `numerical_verification_py31011/` holds the Python 3.10.11 re-run of the Table 3 verification cases (170 passed). Section 4.4 and Table S5 report the runtimes from `runtime_benchmarks.csv`. The earlier timings in `../Data/moreno_yang_scalability/summary.json` are kept as a record; see the runtime variability note above.
