"""Run: python -m aquaprovpy.assessment manifest.json --output results_dir"""
import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description='Replay an AquaProv groundwater assessment.')
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-version-change', action='store_true')
    args = parser.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    from .replay import replay
    try:
        result = replay(args.manifest, allow_version_change=args.allow_version_change)
        args.output.mkdir(parents=True, exist_ok=True)
        result.export(args.output, 'assessment')
        result.figure.savefig(args.output/'assessment.png', dpi=180)
        import matplotlib.pyplot as plt
        plt.close(result.figure)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'Assessment failed: {exc}', file=sys.stderr)
        return 1
    print(f'Assessment exported to {args.output.resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
