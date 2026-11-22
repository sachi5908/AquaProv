"""Run sukinda_verification.pqi with the standalone USGS PHREEQC batch executable.

Standard library only. Writes sukinda_verification.pqo (full PHREEQC output),
sukinda_verification_selected.tsv (PHREEQC SELECTED_OUTPUT) and phreeqc_si.csv.

Usage:  python run_external_phreeqc.py PHREEQC_HOME [DATABASE TAG]
where PHREEQC_HOME contains bin/Release/phreeqc.exe and database/phreeqc.dat
(USGS phreeqc-3.8.6-17100-x64.msi, extracted or installed). DATABASE defaults to
PHREEQC_HOME/database/phreeqc.dat; TAG (optional) suffixes the output names so a
second run can use another phreeqc.dat release with the same executable.
"""
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOME = Path(sys.argv[1])
EXE = HOME / 'bin' / 'Release' / 'phreeqc.exe'
DB = Path(sys.argv[2]) if len(sys.argv) > 2 else HOME / 'database' / 'phreeqc.dat'
TAG = ('_' + sys.argv[3]) if len(sys.argv) > 3 else ''
MINERALS = ('Calcite', 'Dolomite', 'Gypsum', 'Fluorite')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    pqi, pqo = HERE / 'sukinda_verification.pqi', HERE / f'sukinda_verification{TAG}.pqo'
    selected = HERE / f'sukinda_verification{TAG}_selected.tsv'
    text = pqi.read_text(encoding='ascii').replace('sukinda_verification_selected.tsv', selected.name)
    run_input = HERE / f'_run{TAG}.pqi'
    run_input.write_text(text, encoding='ascii')
    run = subprocess.run([str(EXE), run_input.name, pqo.name, str(DB)], cwd=HERE,
                         capture_output=True, text=True)
    run_input.unlink()
    if run.returncode != 0:
        raise SystemExit(run.stdout + run.stderr)
    out = pqo.read_text(encoding='latin-1')
    version = [l.strip() for l in (HOME / 'phreeqc_version.h').read_text().splitlines()
               if '#define' in l and ('VER' in l or 'REVISION' in l)]
    banner = [l.strip() for l in run.stdout.splitlines() + out.splitlines()[:12] if l.strip()][:12]

    rows = []
    with open(selected, encoding='latin-1') as f:
        reader = csv.DictReader(f, delimiter='\t')
        reader.fieldnames = [h.strip() for h in reader.fieldnames]
        for r in reader:
            r = {k: (v or '').strip() for k, v in r.items()}
            row = {'Sl. No.': int(float(r['soln'])), 'pH': float(r['pH'])}
            for m in MINERALS:
                v = float(r['si_' + m])
                row['SI_' + m] = '' if v <= -999 else repr(v)  # -999.999 = phase not defined
            rows.append(row)
    with open(HERE / f'phreeqc_si{TAG}.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    meta = dict(executable=str(EXE), executable_sha256=sha256(EXE), database=str(DB),
                database_sha256=sha256(DB), version_header=version, console_and_output_header=banner)
    (HERE / f'phreeqc_run_metadata{TAG}.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(json.dumps(meta, indent=2))
    print((HERE / f'phreeqc_si{TAG}.csv').read_text(encoding='utf-8'))


if __name__ == '__main__':
    main()
