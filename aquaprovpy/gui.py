"""Public desktop entry point; scientific workspaces load only when requested."""
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "aquaprovpy"

from .core.catalog import APP_NAME, DIAGRAMS, STATISTICAL_VIEWS, EXPLORATORY_VIEWS
from .core.data import normalize_headers


def __getattr__(name):
    if name == "AquaProvApp":
        from .ui.workbench import Workbench
        return Workbench
    raise AttributeError(name)


def main():
    from .ui.application import main as run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
