"""Wilcox (1948): Na-only percent of total cations; primary-figure digitization."""
from .irrigation import plot as _plot


def plot(df, unit='mg/L', figname='Wilcox diagram', figformat='png', **kwargs):
    return _plot(df, unit, figname, figformat, diagram='wilcox', **kwargs)