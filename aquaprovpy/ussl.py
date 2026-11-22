"""USSL irrigation plot; see irrigation.py for equations and boundary provenance."""
from .irrigation import plot as _plot


def plot(df, unit='mg/L', figname='USSL diagram', figformat='png', **kwargs):
    return _plot(df, unit, figname, figformat, diagram='ussl', **kwargs)