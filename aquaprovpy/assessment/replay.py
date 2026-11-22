"""Save and replay assessments with embedded data, settings and source hashes."""

import json
import platform
from pathlib import Path
import numpy as np
import pandas as pd
import scipy
import sklearn

from ..core.projects import encode_frame, decode_frame, atomic_json
from . import ENGINE_VERSION
from .. import __version__
from .engine import digest, code_fingerprint, plot


def versions():
    return {'aquaprov': __version__, 'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__,
            'scipy': scipy.__version__, 'scikit-learn': sklearn.__version__, 'assessment': ENGINE_VERSION}


def make_manifest(frame, config, result=None):
    payload = encode_frame(frame)
    manifest = {'format': 'aquaprov-assessment', 'version': 1, 'input': payload,
                'input_sha256': digest(payload), 'config': config, 'config_sha256': digest(config),
                'code_sha256': code_fingerprint(), 'versions': versions()}
    if result is not None:
        if result.metadata['input_sha256'] != manifest['input_sha256'] or digest(result.metadata['config']) != manifest['config_sha256']:
            raise ValueError('The displayed result belongs to different data/settings. Regenerate before exporting replay.')
        manifest['table_sha256'] = {name: digest(encode_frame(table)) for name, table in result.tables.items()}
    return manifest


def save_manifest(path, frame, config, result=None):
    atomic_json(path, make_manifest(frame, config, result))


def replay(path, *, allow_version_change=False):
    manifest = json.loads(Path(path).read_text(encoding='utf-8'))
    if manifest.get('format') not in ('aquaprov-assessment', 'aquaprov-assessment') or manifest.get('version') != 1:
        raise ValueError('Unsupported replay document.')
    if digest(manifest['input']) != manifest['input_sha256'] or digest(manifest['config']) != manifest['config_sha256']:
        raise ValueError('Replay input or settings hash does not match. The document may have been edited.')
    changed = manifest['code_sha256'] != code_fingerprint() or manifest['versions'] != versions()
    if changed and not allow_version_change:
        raise ValueError('Code/dependency versions differ. Use --allow-version-change to run an explicitly unverified migration.')
    frame = decode_frame(manifest['input'])
    result = plot(frame, manifest['config'])
    actual = {name: digest(encode_frame(table)) for name, table in result.tables.items()}
    expected = manifest.get('table_sha256')
    result.metadata['replay_table_hashes_match'] = actual == expected if expected else None
    result.metadata['replay_environment_changed'] = changed
    if expected and actual != expected and not allow_version_change:
        import matplotlib.pyplot as plt
        plt.close(result.figure)
        raise ValueError('Replayed numerical tables differ from the saved hashes.')
    if changed:
        result.warnings.append('Replay used different code/dependency versions; numerical agreement must be reviewed.')
    return result
