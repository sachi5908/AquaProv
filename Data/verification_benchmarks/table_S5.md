**Table S5.** Wall-clock runtimes of AquaProv v1.0 workflows (median of three repeats; first call in parentheses).

| Dataset | Records | Workflow | Median time (s) | First call (s) |
|---|---:|---|---:|---:|
| Sukinda | 35 | PHREEQC speciation and SI (IPhreeqc; 4 minerals) | 0.67 | 0.69 |
| Sukinda | 35 | 5-block spatial CV of TDS (ordinary kriging, IDW, training mean) | 0.23 | 0.31 |
| Sukinda | 35 | Monte Carlo SAR uncertainty, 2,000 draws | 0.45 | 0.47 |
| Sukinda | 35 | Monte Carlo SAR uncertainty, 10,000 draws | 1.11 | 1.18 |
| Yang et al. (2020) | 1,184 | CSV ingestion + quality/nondetect review | 0.22 | 0.23 |
| Moreno Merino et al. (2021) | 2,124 | CSV ingestion + 8-ion CBE review | 0.26 | 0.26 |
| Moreno Merino et al. (2021) | 2,124 | Contour-filled (density) Piper, render and save PNG | 6.40 | 6.75 |

Environment: AMD Ryzen 7 7840HS w/ Radeon 780M Graphics (16 logical processors), 15.3 GB RAM, Windows-10-10.0.26300-SP0; Python 3.10.11, AquaProv 1.0, NumPy 2.2.6, pandas 2.3.3, Matplotlib 3.10.9, SciPy 1.15.3, scikit-learn 1.7.2. Times are single-process wall-clock (time.perf_counter) after module import; the first call includes in-process initialization such as database loading. Monte Carlo runs use a 10% relative standard deviation scenario, seed 42, and compute SAR together with the other screening metrics. The Piper time includes the kernel density evaluation, rendering and writing a PNG file.
