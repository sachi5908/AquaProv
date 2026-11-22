"""Installed desktop launcher; help and version do not import Qt."""
import argparse

from . import __version__


def main():
    """Launch the desktop, optionally opening a saved AquaProv project."""
    parser = argparse.ArgumentParser(
        prog="aquaprov", description="AquaProv water-chemistry desktop application.",
    )
    parser.add_argument("project", nargs="?", help="saved .aquaprov project to open")
    parser.add_argument("-V", "--version", action="version", version=f"AquaProv V. {__version__}")
    parser.parse_args()
    from .gui import main as run_gui

    return run_gui()
