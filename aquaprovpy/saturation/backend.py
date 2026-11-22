"""Small IPhreeqc C-API adapter. Native execution belongs in a disposable worker."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys

RESOURCES = Path(__file__).resolve().parent / 'resources'
BUILTIN_DATABASES = ('phreeqc.dat', 'wateq4f.dat')


def database_snapshot(path):
    path = Path(path)
    raw = path.read_bytes()
    if len(raw) > 20_000_000:
        raise ValueError('The thermodynamic database exceeds 20 MB.')
    text = raw.decode('utf-8-sig')
    if 'SOLUTION_MASTER_SPECIES' not in text or 'PHASES' not in text:
        raise ValueError('Choose a PHREEQC thermodynamic .dat database.')
    return dict(name=path.name, text=text, sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
                source=str(path.resolve()))


def resolve_database(selection='phreeqc.dat', snapshot=None):
    if snapshot is not None:
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get('text'), str):
            raise ValueError('Invalid saved thermodynamic database.')
        digest = hashlib.sha256(snapshot['text'].encode('utf-8')).hexdigest()
        if digest != snapshot.get('sha256'):
            raise ValueError('Saved thermodynamic database checksum does not match.')
        return dict(snapshot)
    if selection not in BUILTIN_DATABASES:
        return database_snapshot(selection)
    result = database_snapshot(RESOURCES / selection)
    manifest = json.loads((RESOURCES / 'manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256((RESOURCES / selection).read_bytes()).hexdigest() != manifest['files'][selection]['sha256']:
        raise ValueError('Bundled thermodynamic database checksum does not match.')
    result['source'] = manifest['files'][selection]['source']
    return result


def phase_names(database):
    """Read named PHASES, each followed by a reaction, without executing BASIC."""
    lines = [line.split('#', 1)[0].strip() for line in database['text'].splitlines()]
    lines = [line for line in lines if line]
    names = []
    active = False
    sections = {'EXCHANGE_MASTER_SPECIES', 'EXCHANGE_SPECIES', 'SURFACE_MASTER_SPECIES',
                'SURFACE_SPECIES', 'RATES', 'END', 'PITZER', 'SIT', 'NAMED_EXPRESSIONS'}
    for i, line in enumerate(lines[:-1]):
        if line == 'PHASES':
            active = True
        elif line in sections:
            active = False
        elif active and '=' not in line and not line.startswith('-') and '=' in lines[i + 1]:
            # WATEQ4F appends legacy phase numbers after the actual name.
            names.append(line.split()[0])
    return names


def _library_path():
    override = os.environ.get('AQUAPROV_IPHREEQC_LIBRARY')
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == 'win32' and ctypes.sizeof(ctypes.c_void_p) == 8:
        path = RESOURCES / 'IPhreeqc-3.7.3.dll'
        manifest = json.loads((RESOURCES / 'manifest.json').read_text(encoding='utf-8'))
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['files'][path.name]['sha256']:
            raise ValueError('Bundled IPhreeqc library checksum does not match.')
        return path
    raise ValueError('Set AQUAPROV_IPHREEQC_LIBRARY to a compatible IPhreeqc shared library on this platform. '
                     'The Windows x64 edition includes IPhreeqc. Imported SI analysis needs no engine.')


def run_native(request):
    """Return selected output, native warnings and version; never modify input chemistry."""
    path = _library_path()
    try:
        library = ctypes.CDLL(str(path))
    except OSError as exc:
        raise ValueError(f'Could not load IPhreeqc ({path.name}): {exc}') from exc
    signatures = {
        'CreateIPhreeqc': ([], ctypes.c_int),
        'DestroyIPhreeqc': ([ctypes.c_int], ctypes.c_int),
        'LoadDatabaseString': ([ctypes.c_int, ctypes.c_char_p], ctypes.c_int),
        'RunString': ([ctypes.c_int, ctypes.c_char_p], ctypes.c_int),
        'GetVersionString': ([], ctypes.c_char_p),
        'GetSelectedOutputString': ([ctypes.c_int], ctypes.c_char_p),
        'GetErrorString': ([ctypes.c_int], ctypes.c_char_p),
        'GetWarningString': ([ctypes.c_int], ctypes.c_char_p),
        'SetSelectedOutputStringOn': ([ctypes.c_int, ctypes.c_int], ctypes.c_int),
        'SetSelectedOutputFileOn': ([ctypes.c_int, ctypes.c_int], ctypes.c_int),
        'SetOutputFileOn': ([ctypes.c_int, ctypes.c_int], ctypes.c_int),
        'SetLogFileOn': ([ctypes.c_int, ctypes.c_int], ctypes.c_int),
        'SetErrorFileOn': ([ctypes.c_int, ctypes.c_int], ctypes.c_int),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(library, name)
        function.argtypes, function.restype = arguments, result
    identifier = library.CreateIPhreeqc()
    if identifier < 0:
        raise RuntimeError('IPhreeqc could not create a calculation instance.')
    def read(name):
        return (getattr(library, name)(identifier) or b'').decode('utf-8', errors='replace')
    try:
        for name in ('SetSelectedOutputFileOn', 'SetOutputFileOn', 'SetLogFileOn', 'SetErrorFileOn'):
            getattr(library, name)(identifier, 0)
        if library.LoadDatabaseString(identifier, request['database'].encode('utf-8')):
            raise ValueError('PHREEQC database error:\n' + read('GetErrorString'))
        library.SetSelectedOutputStringOn(identifier, 1)
        if library.RunString(identifier, request['input'].encode('utf-8')):
            raise ValueError('PHREEQC calculation error:\n' + read('GetErrorString'))
        return dict(output=read('GetSelectedOutputString'), warnings=read('GetWarningString'),
                    version=library.GetVersionString().decode('ascii'),
                    library_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    finally:
        library.DestroyIPhreeqc(identifier)
