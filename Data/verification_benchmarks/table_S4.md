**Table S4.** External numerical verification of AquaProv v1.0 for eight Sukinda wells. CBE, SAR, WQI and DWQI: AquaProv versus an independent standard-library/NumPy implementation. SI: AquaProv (IPhreeqc 3.7.3, bundled phreeqc.dat 3.7.3) versus the standalone USGS PHREEQC 3.8.6-17100 batch executable with its distributed phreeqc.dat.

(a) Charge balance, SAR and indices (AquaProv / reference)

| Sl. No. | Site (type) | TDS (mg/L) | Total Cr (µg/L) | CBE (%) | SAR | WQI | DWQI |
|---:|---|---:|---:|---|---|---|---|
| 15 | Guakata (HP) | 34.93 | 0 | 13.315 / 13.314 | 0.3436 / 0.3436 | 0.4252 / 0.4252 | 7.3000 / 7.3000 |
| 9 | Kaliapani Township (HP) | 333.3 | 6.3 | 1.051 / 1.050 | 0.2032 / 0.2032 | 12.9450 / 12.9450 | 6.6667 / 6.6667 |
| 1 | Kamarda TW (TW) | 315.6 | 159.2 | 0.257 / 0.256 | 0.0808 / 0.0808 | 13.0091 / 13.0091 | 7.7667 / 7.7667 |
| 6 | Patna HP 2 (HP) | 292.1 | 427.3 | -0.269 / -0.271 | 0.4098 / 0.4098 | 6.4725 / 6.4725 | 3.3333 / 3.3333 |
| 7 | Gurujang (HP) | 156.5 | 51.7 | 4.558 / 4.555 | 1.4527 / 1.4527 | 7.6026 / 7.6026 | 22.7333 / 22.7333 |
| 3 | Talangi HP (HP) | 182.3 | 24.8 | 12.300 / 12.297 | 0.4798 / 0.4798 | 8.6919 / 8.6919 | 41.4333 / 41.4333 |
| 39 | Ragada HP (HP) | 114.1 | 0 | -7.504 / -7.505 | 0.3053 / 0.3053 | 6.4783 / 6.4783 | 3.4333 / 3.4333 |
| 12 | Chingudipal (HP) | 256.5 | 0 | 7.135 / 7.134 | 0.5249 / 0.5249 | 20.1165 / 20.1165 | 22.0000 / 22.0000 |
| **max \|Δ\|** | | | | **3.3e-03** | **1.9e-06** | **0.0e+00** | **0.0e+00** |

(b) Mineral saturation indices (AquaProv / external PHREEQC 3.8.6)

| Sl. No. | Calcite | Dolomite | Gypsum | Fluorite |
|---:|---|---|---|---|
| 15 | -2.950 / -2.949 | -6.140 / -6.138 | -4.441 / -4.441 | – / – |
| 9 | 0.351 / 0.369 | 0.231 / 0.252 | -2.160 / -2.153 | -2.264 / -2.252 |
| 1 | -0.038 / -0.021 | 0.326 / 0.345 | -3.331 / -3.326 | -2.654 / -2.640 |
| 6 | -0.210 / -0.198 | -0.145 / -0.132 | -2.215 / -2.214 | -3.257 / -3.248 |
| 7 | -1.905 / -1.902 | -3.699 / -3.697 | -3.013 / -3.018 | -3.596 / -3.595 |
| 3 | -1.689 / -1.685 | -3.592 / -3.586 | -2.970 / -2.973 | -3.220 / -3.218 |
| 39 | -0.954 / -0.946 | -1.828 / -1.818 | -4.978 / -4.975 | -3.455 / -3.448 |
| 12 | 0.568 / 0.581 | 0.491 / 0.507 | -2.428 / -2.424 | -2.011 / -2.002 |
| **max \|ΔSI\|**, phreeqc.dat 3.8.6 | **0.018** | **0.022** | **0.006** | **0.014** |
| **max \|ΔSI\|**, same phreeqc.dat 3.7.3 | **0.0e+00** | **0.0e+00** | **0.0e+00** | **0.0e+00** |

Notes: Well identifiers are the workbook "Sl. No." values. CBE uses Ca, Mg, Na, K, HCO3, CO3, Cl and SO4; the reference uses IUPAC (CIAAW 2021) standard atomic weights. WQI uses inverse-standard weights and DWQI equal importance weights, with WHO (2026) objectives of 50 mg/L NO3 and 1.5 mg/L F. PHREEQC conditions: 25 °C, density 1 kg/L, pe 4, alkalinity as CaCO3, reported mg/L concentrations. Fluorite SI is undefined (–) for Sl. No. 15, which reports F = 0, in both AquaProv and PHREEQC.
