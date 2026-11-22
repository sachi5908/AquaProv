"""One registry for home cards, navigation and project module identifiers."""
from dataclasses import dataclass
import importlib
import sys


@dataclass(frozen=True)
class Module:
    key: str
    title: str
    short_title: str
    description: str
    features: str
    accent: str
    tint: str
    entry: str


MODULES = (
    Module("groundwater", "Groundwater & contamination", "Groundwater",
           "Understand water chemistry and explore contamination patterns.",
           "Piper & geochemical plots\nIrrigation assessment\nContamination diagrams", "#006d75", "#e4f3f3",
           "aquaprovpy.modules.groundwater.workspace.GroundwaterWorkspace"),
    Module("statistics", "Statistics", "Statistics",
           "Explore correlations, multivariate patterns and uncertainty.",
           "Correlation & PCA\nClustering & distributions\nTime series & uncertainty", "#7c3aed", "#f0eaff",
           "aquaprovpy.modules.statistics.workspace.StatisticsWorkspace"),
    Module("maps", "Maps, kriging & contours", "Maps & contours",
           "Connect sample locations to spatial patterns across your study area.",
           "Geographic sample maps\nOrdinary kriging & IDW\nContours & prediction variance", "#006c9a", "#e4f2f9",
           "aquaprovpy.modules.maps.workspace.MapWorkspace"),
    Module("three_d", "3D visualization", "3D visualization",
           "Explore measurements, surfaces and multivariate structure in 3D.",
           "XYZ scatter & surfaces\n3D PCA scores & loadings\nInteractive camera & export", "#00365d", "#e7eef5",
           "aquaprovpy.modules.three_d.workspace.ThreeDWorkspace"),
    Module("assessment", "Assessment & uncertainty", "Assessment",
           "Audit measurements, quantify conditional uncertainty and validate conclusions.",
           "Quality & uncertainty\nAssay priorities & replay\nCompositional & spatial validation", "#99601e", "#fff3df",
           "aquaprovpy.modules.assessment.workspace.AssessmentWorkspace"),
    Module("water_quality", "Water quality indices", "WQI & DWQI",
           "Calculate, classify and map water-quality and drinking-water indices.",
           "Arithmetic, groundwater & CCME WQI\nWeighted & custom DWQI\nSeasonal maps & standards compliance", "#167d6b", "#e4f4ed",
           "aquaprovpy.modules.water_quality.workspace.WaterQualityWorkspace"),
    Module("saturation", "PHREEQC mineral saturation", "Mineral SI",
           "Calculate mineral saturation from ion activities or explore PHREEQC output.",
           "PHREEQC speciation & databases\nSI comparisons & distributions\nSpatial SI maps & exports", "#99601e", "#fff3df",
           "aquaprovpy.modules.saturation.workspace.SaturationWorkspace"),
)


def module_for(key):
    return next(module for module in MODULES if module.key == key)


def load_workspace_class(key):
    """Import dependencies without constructing any Qt widgets (worker-safe)."""
    module = module_for(key)
    package, class_name = module.entry.rsplit(".", 1)
    # Some module dependencies import pyplot. Select the desktop's offscreen
    # renderer before those imports, while respecting an existing pyplot host.
    if 'matplotlib.pyplot' not in sys.modules:
        import matplotlib
        matplotlib.use('Agg')
    return getattr(importlib.import_module(package), class_name)


def create_workspace(key):
    return load_workspace_class(key)()
