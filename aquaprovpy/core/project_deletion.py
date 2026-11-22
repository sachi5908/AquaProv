"""Delete project files and folders after checking folder ownership."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import stat

from .projects import PROJECT_FOLDER_MARKER, LEGACY_FOLDER_MARKER, PROJECT_EXTENSIONS, atomic_json


def _is_link(path):
    """Check for symlinks and Windows reparse points, including junctions.

    Use lstat because Path.is_junction is unavailable before Python 3.12.
    """
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _owned_folder(path):
    folder = path.parent
    protected = {Path.home(), *(Path.home() / name for name in ('Desktop', 'Documents', 'Downloads'))}
    if not folder.is_dir() or folder == Path(folder.anchor) or folder in protected:
        return False
    # Save As can put multiple projects into a previously dedicated folder.
    if any(child != path and child.suffix.lower() in PROJECT_EXTENSIONS for child in folder.iterdir()):
        return False
    marker = folder / PROJECT_FOLDER_MARKER
    if not marker.exists():
        marker = folder / LEGACY_FOLDER_MARKER
    if _is_link(marker):
        return False
    if marker.exists():
        try:
            metadata = json.loads(marker.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            return False
        return isinstance(metadata, dict) and metadata.get('project_file') == path.name
    # Projects created before folder markers used this name and export layout.
    # A file saved directly into Documents/Desktop must never own its parent.
    return (folder.name == path.stem and (not any(folder.iterdir()) or (
            all((folder / 'exports' / module).is_dir() and
                not _is_link(folder / 'exports' / module) for module in ('groundwater', 'maps', 'three_d')) and
            not _is_link(folder / 'exports'))))


@dataclass(frozen=True)
class ProjectDeletion:
    path: Path
    directory: Path | None = None

    @classmethod
    def prepare(cls, path):
        # Check for links before resolving the path, so deletion cannot
        # follow one into another project directory.
        path = Path(os.path.abspath(Path(path).expanduser()))
        if path.suffix.lower() not in PROJECT_EXTENSIONS:
            raise ValueError('Choose an AquaProv project file to delete.')
        if any(_is_link(part) for part in (path, *path.parents)):
            raise ValueError('This project path uses a link or junction. Open its actual location to delete it.')
        if path.exists() and not path.is_file():
            raise ValueError('The project path is not a file.')
        path = path.resolve()
        return cls(path, path.parent if _owned_folder(path) else None)

    def includes(self, path):
        path = Path(path).expanduser().resolve()
        return path == self.path or (self.directory is not None and path.is_relative_to(self.directory))

    def delete(self):
        # Recheck immediately after confirmation in case the location changed.
        if self != self.prepare(self.path):
            raise ValueError('The project folder changed. Review the project and try deleting it again.')
        if self.directory is not None:
            target = self.directory.resolve()
            if target != self.path.parent or target == Path(target.anchor):
                raise ValueError('The project folder could not be verified.')
            # Keep the document and ownership marker until the contents are
            # removed, so a locked export does not strand an unrecognized folder.
            marker = target / PROJECT_FOLDER_MARKER
            if not marker.exists():
                atomic_json(marker, {'project_file': self.path.name})
            for child in target.iterdir():
                if child in (marker, self.path):
                    continue
                if child.is_symlink():
                    child.unlink()
                elif _is_link(child):
                    # A top-level Windows junction must be removed directly;
                    # rmtree refuses it. rmdir removes the link, not its target.
                    if child.is_dir():
                        child.rmdir()
                    else:
                        child.unlink()
                elif child.is_dir():
                    # Python 3.8+ removes junctions without traversing targets.
                    shutil.rmtree(child)
                else:
                    child.unlink()
            self.path.unlink(missing_ok=True)
            marker.unlink()
            target.rmdir()
        else:
            self.path.unlink(missing_ok=True)
