"""Portable, versioned project documents and a local recent-project index.

Project data is JSON, never executable Python/pickle. Writes use atomic replace,
so an interrupted save leaves the previous project document intact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import time


FORMAT = "aquaprov-project"
LEGACY_FORMAT = "aquastat-project"
PROJECT_EXTENSIONS = (".aquaprov", ".aquastat")
VERSION = 3
MODULE_IDS = ("groundwater", "statistics", "maps", "three_d", "assessment", "water_quality", "saturation")
PROJECT_FOLDER_MARKER = ".aquaprov-project.json"
LEGACY_FOLDER_MARKER = ".aquastat-project.json"


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows scanners and indexers can briefly open a just-created file.
        # Retry the atomic replacement, preserving the old document on failure.
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError as exc:
                if getattr(exc, 'winerror', None) not in (5, 32, 33) or attempt == 5:
                    raise
                time.sleep(.02 * 2**attempt)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def encode_frame(frame):
    if frame is None:
        return None
    import pandas as pd
    def cell(value):
        if pd.isna(value):
            return None
        if isinstance(value, (pd.Timestamp, datetime)):
            return value.isoformat()
        if hasattr(value, "item"):
            value = value.item()
        if isinstance(value, (str, int, float, bool)):
            return value
        return str(value)
    index = {"values": [cell(value) for value in frame.index],
             "dtype": str(frame.index.dtype), "name": cell(frame.index.name)}
    if isinstance(frame.index, pd.RangeIndex):
        index["range"] = [frame.index.start, frame.index.stop, frame.index.step]
    result = {"columns": list(frame.columns), "dtypes": [str(dtype) for dtype in frame.dtypes], "index": index,
              "data": [[cell(value) for value in row] for row in frame.itertuples(index=False, name=None)]}
    if 'aquaprov' in frame.attrs:
        from copy import deepcopy
        result['aquaprov'] = deepcopy(frame.attrs['aquaprov'])
    return result


def decode_frame(payload):
    if payload is None:
        return None
    import pandas as pd
    if not isinstance(payload, dict) or not isinstance(payload.get("columns"), list):
        raise ValueError("The project dataset is invalid.")
    columns, rows = payload["columns"], payload.get("data")
    if not columns or any(not isinstance(c, str) for c in columns) or len(set(columns)) != len(columns):
        raise ValueError("Project dataset columns must be unique names.")
    if not isinstance(rows, list) or any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
        raise ValueError("The project dataset has inconsistent rows.")
    frame = pd.DataFrame(rows, columns=columns)
    dtypes = payload.get("dtypes", [])
    if len(dtypes) != len(columns):
        raise ValueError("The project dataset has invalid column types.")
    for column, dtype in zip(columns, dtypes):
        if dtype.startswith("datetime64"):
            frame[column] = pd.to_datetime(frame[column]).astype(dtype)
        else:
            frame[column] = frame[column].astype(dtype)
    if "index" in payload:
        index = payload["index"]
        if not isinstance(index, dict) or not isinstance(index.get("values"), list) or len(index["values"]) != len(frame):
            raise ValueError("The project dataset has invalid row identifiers.")
        if "range" in index:
            frame.index = pd.RangeIndex(*index["range"], name=index.get("name"))
        elif str(index.get("dtype", "")).startswith("datetime64"):
            frame.index = pd.DatetimeIndex(pd.to_datetime(index["values"]), name=index.get("name"))
        else:
            frame.index = pd.Index(index["values"], dtype=index.get("dtype"), name=index.get("name"))
    provenance = payload.get('aquaprov', payload.get('aquastat'))
    if provenance is not None:
        if not isinstance(provenance, dict):
            raise ValueError('Invalid measurement provenance.')
        frame.attrs['aquaprov'] = provenance
    return frame


@dataclass
class Project:
    name: str = "Untitled project"
    location: str = ""
    description: str = ""
    path: Path | None = None
    created: str = field(default_factory=timestamp)
    modified: str = field(default_factory=timestamp)
    last_module: str = "groundwater"
    dataset: object = None
    source: dict = field(default_factory=dict)
    modules: dict = field(default_factory=dict)
    auto_save: bool = True

    def export_directory(self, module):
        if module not in MODULE_IDS:
            raise ValueError("Unknown AquaProv module.")
        if self.path is None:
            return Path.home() / "Documents" / "AquaProv Exports" / module
        return self.path.parent / "exports" / module

    def save(self, path=None):
        destination = Path(path or self.path).resolve() if (path or self.path) else None
        if destination is None:
            raise ValueError("Choose a project file first.")
        modified = timestamp()
        payload = {"format": FORMAT, "version": VERSION, "name": self.name,
                   "location": self.location, "description": self.description,
                   "created": self.created, "modified": modified,
                   "last_module": self.last_module, "source": self.source,
                   "dataset": encode_frame(self.dataset), "modules": self.modules,
                   "auto_save": self.auto_save}
        atomic_json(destination, payload)
        self.path, self.modified = destination, modified

    @classmethod
    def create(cls, parent, name, location="", description=""):
        name = name.strip()
        if not name:
            raise ValueError("Enter a project name.")
        slug = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:100]
        if not slug or slug.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
            raise ValueError("Choose a different project name for the folder.")
        folder = Path(parent).expanduser().resolve() / slug
        folder.mkdir(parents=True, exist_ok=False)
        project = cls(name=name, location=location.strip(), description=description.strip())
        try:
            atomic_json(folder / PROJECT_FOLDER_MARKER, {"project_file": slug + ".aquaprov"})
            project.save(folder / (slug + ".aquaprov"))
        except Exception:
            # Only remove the empty directory just created by this operation.
            try:
                (folder / PROJECT_FOLDER_MARKER).unlink(missing_ok=True)
                folder.rmdir()
            except OSError:
                pass
            raise
        for module in MODULE_IDS:
            project.export_directory(module).mkdir(parents=True, exist_ok=True)
        return project

    @classmethod
    def load(cls, path):
        path = Path(path).expanduser().resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("format") not in (FORMAT, LEGACY_FORMAT):
            raise ValueError("This file is not an AquaProv project.")
        if payload.get("version") not in (1, 2, VERSION):
            raise ValueError("This project version is not supported by this AquaProv edition.")
        for key in ("name", "location", "description", "created", "modified"):
            if not isinstance(payload.get(key), str):
                raise ValueError(f"Invalid project field: {key}.")
        modules = payload.get("modules", {})
        if not isinstance(modules, dict) or any(k not in MODULE_IDS or not isinstance(v, dict) for k, v in modules.items()):
            raise ValueError("Invalid project module settings.")
        if payload.get("last_module") not in MODULE_IDS or not isinstance(payload.get("source"), dict):
            raise ValueError("Invalid project workspace metadata.")
        project = cls(path=path, dataset=decode_frame(payload.get("dataset")),
                   **{k: payload[k] for k in ("name", "location", "description", "created", "modified", "last_module", "source")},
                   modules=modules, auto_save=payload.get('auto_save', True) is not False)
        from .project_migrations import separate_statistics
        if payload.get('version') == 2:
            from .editable_project_migration import migrate
            project = migrate(project)
        return separate_statistics(project)


class RecentProjects:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get("AQUAPROV_HOME", os.environ.get("AQUASTAT_HOME", Path.home() / ".aquaprov"))) / "recent_projects.json"
        self.legacy_path = (Path.home() / '.aquastat/recent_projects.json'
                            if path is None and not any(key in os.environ for key in ('AQUAPROV_HOME', 'AQUASTAT_HOME'))
                            else None)

    def load(self):
        try:
            source = self.path if self.path.exists() or self.legacy_path is None else self.legacy_path
            entries = json.loads(source.read_text(encoding="utf-8"))
            return [item for item in entries if isinstance(item, dict) and
                    all(isinstance(item.get(k), str) for k in ("path", "name", "modified"))][:20] if isinstance(entries, list) else []
        except (OSError, ValueError):
            return []

    def remember(self, project, *, opened=True):
        if project.path is None:
            return
        path = str(project.path.resolve())
        entries = self.load()
        previous = next((item for item in entries if os.path.normcase(item['path']) == os.path.normcase(path)), {})
        entries = [item for item in entries if os.path.normcase(item["path"]) != os.path.normcase(path)]
        entries.insert(0, {"name": project.name, "path": path, "modified": project.modified,
                           "location": project.location, "module": project.last_module,
                           "last_opened": timestamp() if opened or not previous else previous.get('last_opened', '')})
        atomic_json(self.path, entries[:20])

    def forget(self, path, *, directory=None):
        """Remove entries for a deleted project (or its entire owned folder)."""
        target = Path(path).expanduser().resolve()
        directory = Path(directory).resolve() if directory is not None else None
        entries = self.load()
        def keep(entry):
            candidate = Path(entry['path']).expanduser().resolve()
            return candidate != target and (directory is None or not candidate.is_relative_to(directory))
        remaining = [entry for entry in entries if keep(entry)]
        if len(remaining) != len(entries):
            atomic_json(self.path, remaining)
