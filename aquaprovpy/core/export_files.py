"""Stage complete exports before replacing files, and track partial write failures."""
import os
from pathlib import Path
import tempfile


class ExportWriteError(OSError):
    def __init__(self, cause, targets, completed):
        super().__init__(str(cause))
        self.cause = cause
        self.targets = tuple(targets)
        self.completed = tuple(completed)


def write_export_files(targets, writer):
    targets = [Path(path).absolute() for path in targets]
    if not targets or len({path.parent for path in targets}) != 1:
        raise ValueError('Export files must share one output folder.')
    if len({str(path).casefold() for path in targets}) != len(targets):
        raise ValueError('Export file names must be unique.')
    for path in targets:
        if path.exists() and not path.is_file():
            raise ValueError(f'A folder already uses this export name: {path.name}. Choose another file name.')
    completed = []
    try:
        targets[0].parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.aquaprov-export-', dir=targets[0].parent) as folder:
            staged = [Path(folder) / path.name for path in targets]
            writer(staged)
            if any(not path.is_file() or path.stat().st_size == 0 for path in staged):
                raise OSError('The exporter did not produce all expected files.')
            for source, target in zip(staged, targets):
                os.replace(source, target)
                completed.append(target)
    except OSError as exc:
        raise ExportWriteError(exc, targets, completed) from exc
    return targets
