"""Isolate long native kernels that hold the desktop interpreter's GIL."""
import os
from pathlib import Path
import pickle
import subprocess
import sys


def _calculate(kind, values):
    if kind == 'phreeqc':
        if not getattr(sys, 'frozen', False):
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from aquaprovpy.saturation.backend import run_native
        return run_native(values)
    if kind == 'ward':
        from scipy.cluster.hierarchy import linkage
        return linkage(values, method='ward', metric='euclidean', optimal_ordering=True)
    if kind == 'density':
        import numpy as np
        model, points = values
        return np.exp(model.score_samples(points))
    raise ValueError('Unknown numerical worker task.')


def _standard_pipe(name):
    stream = getattr(sys, name)
    if stream is not None:
        return stream.buffer
    # PyInstaller's windowed bootloader leaves sys.std* unset even when the
    # parent supplied pipes. Open the inherited Windows handle without a console.
    import ctypes
    from ctypes import wintypes
    import msvcrt
    get_handle = ctypes.windll.kernel32.GetStdHandle
    get_handle.argtypes = [wintypes.DWORD]
    get_handle.restype = wintypes.HANDLE
    reading = name == 'stdin'
    handle = get_handle(wintypes.DWORD(-10 if reading else -11))
    fd = msvcrt.open_osfhandle(handle, (os.O_RDONLY if reading else os.O_WRONLY) | os.O_BINARY)
    return os.fdopen(fd, 'rb' if reading else 'wb')


def worker_main():
    """Private pipe protocol; no files, Qt imports or GUI startup in the child."""
    try:
        kind, values = pickle.load(_standard_pipe('stdin'))
        message = ('result', _calculate(kind, values))
    except Exception as exc:
        message = ('error', str(exc))
    output = _standard_pipe('stdout')
    pickle.dump(message, output, protocol=pickle.HIGHEST_PROTOCOL)
    output.flush()
    return 0


def run_numeric_job(kind, values):
    """Run a cancellable private child, returning only numerical data.

    Unlike multiprocessing spawn, this does not re-import the caller's main
    script. It works from the desktop, a test runner, and the frozen executable.
    """
    from .progress import check_cancelled
    check_cancelled()
    command = ([sys.executable, '--aquaprov-numeric-worker'] if getattr(sys, 'frozen', False)
               else [sys.executable, str(Path(__file__).resolve()), '--worker'])
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        request = pickle.dumps((kind, values), protocol=pickle.HIGHEST_PROTOCOL)
        while True:
            check_cancelled()
            try:
                output, error = process.communicate(request, timeout=.05)
                break
            except subprocess.TimeoutExpired:
                request = None  # communicate retains the partially sent request.
        check_cancelled()
        if process.returncode:
            raise RuntimeError('Numerical worker failed: ' + error.decode('utf-8', errors='replace')[-2000:])
        status, value = pickle.loads(output)
        if status != 'result':
            raise ValueError(value)
        return value
    finally:
        # This process owns only disposable numeric data. Killing it cannot
        # interrupt Qt, shared Matplotlib state, or the user's dataset.
        if process.poll() is None:
            process.kill()
        process.communicate()


if __name__ == '__main__':
    raise SystemExit(worker_main())
