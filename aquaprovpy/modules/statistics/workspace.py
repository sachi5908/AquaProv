"""Correlation, PCA, clustering, distributions, time series and uncertainty."""
from ..base import ModuleWorkspace
from ...core.catalog import STATISTICS_DIAGRAMS


class StatisticsWorkspace(ModuleWorkspace):
    module_key = 'statistics'

    def __init__(self):
        super().__init__()
        self.configure_diagrams(STATISTICS_DIAGRAMS)
        self.hide_locations()
        self.connect_settings()
