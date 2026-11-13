"""Main entry point for AquaProv.

Run this file to start the desktop GUI. Importing it does not open a window.
"""


def main():
    """Launch the AquaProv GUI and return its exit code."""
    import sys
    if sys.argv[1:] == ['--aquaprov-numeric-worker']:
        from aquaprovpy.core.numeric_jobs import worker_main
        return worker_main()
    from aquaprovpy.gui import main as run_gui

    return run_gui()


if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()
    raise SystemExit(main())
