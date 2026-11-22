"""Diagram names, module assignments and application metadata."""

from .. import __version__

APP_NAME = "AquaProv"
APP_VERSION = __version__
APP_TITLE = f"{APP_NAME} V. {APP_VERSION}"


DIAGRAMS = {
    "Triangle Piper": ("triangle_piper", "Ca Mg Na K HCO3 CO3 Cl SO4"),
    "Rectangle Piper": ("rectangle_piper", "Ca Mg Na K HCO3 CO3 Cl SO4"),
    "Color-coded Piper": ("color_piper", "Ca Mg Na K HCO3 CO3 Cl SO4"),
    "Contour-filled Piper": ("contour_piper", "Ca Mg Na K HCO3 CO3 Cl SO4"),
    "Durov": ("durvo", "Ca Mg Na K HCO3 CO3 Cl SO4"),
    "Stiff": ("stiff", "Ca Mg Na K HCO3 Cl SO4"),
    "Chernoff face": ("chernoff", "Ca Mg Na K HCO3 Cl SO4"),
    "Schoeller": ("schoeller", ""),
    "Gibbs": ("gibbs", "TDS"),
    "Chadha": ("chadha", "Ca Mg Na K HCO3 CO3 Cl SO4"),
    "Gaillardet": ("gaillardet", "Ca Na"),
    "HFE-D": ("hfed", "Ca Mg Na K HCO3 CO3 Cl SO4"),
    "USSL irrigation": ("ussl", "Ca Mg Na EC"),
    "Wilcox irrigation": ("wilcox", "Ca Mg Na K EC"),
}
# Independent panels/series: each uses only its own measured inputs.
DIAGRAM_GROUPS = {
    'schoeller': {ion: (ion,) for ion in ('Ca', 'Mg', 'Na', 'K', 'Cl', 'SO4', 'HCO3')},
    'gibbs': {'Na-Ca panel': ('Na', 'Ca', 'TDS'), 'Cl-HCO3 panel': ('Cl', 'HCO3', 'TDS')},
    'gaillardet': {'HCO3/Na panel': ('Ca', 'Na', 'HCO3'), 'Mg/Na panel': ('Ca', 'Na', 'Mg')},
    'durvo': {'Composition': tuple('Ca Mg Na K HCO3 CO3 Cl SO4'.split()),
              'pH panel': ('pH',), 'TDS panel': ('TDS',)},
}
DIAGRAM_INPUT_NOTES = {
    'schoeller': 'Uses available Ca, Mg, Na, K, Cl, SO4 and HCO3 measurements. Missing values leave gaps; zero cannot be shown on the log axis.',
    'gibbs': 'Needs TDS and either Na + Ca or Cl + HCO3. Each panel uses its own complete samples.',
    'gaillardet': 'Needs Ca + Na and either HCO3 or Mg. Each panel uses its own complete samples; ratios must be positive for log axes.',
    'durvo': 'Needs Ca, Mg, Na, K, HCO3, CO3, Cl and SO4. pH and TDS are optional extra panels.',
}
STATISTICAL_VIEWS = {
    "Pearson correlation": "pearson", "Spearman correlation": "spearman",
    "PCA · 2D sample scores": "pca_scores", "PCA · 3D sample scores": "pca_scores_3d",
    "PCA · loading heatmap": "pca_loadings", "PCA · 3D component loadings": "pca_loadings_3d",
    "PCA · scree & variance": "pca_scree", "PCA · correlation circle": "pca_correlation_circle",
    "HCA · Ward dendrogram": "hca", "Standardized sample heatmap": "heatmap",
    "Scatter matrix": "scatter_matrix", "Standardized boxplots": "boxplot",
}
DIAGRAMS.update({name: ("multivariate", "") for name in STATISTICAL_VIEWS})
EXPLORATORY_VIEWS = {'Measured series · source rows': 'measured_series',
                     'Time series · observed measurements': 'time_series',
                     'Uncertainty · bootstrap interval': 'bootstrap'}
DIAGRAMS.update({name: ('exploration', '') for name in EXPLORATORY_VIEWS})
GROUNDWATER_DIAGRAMS = tuple(name for name, (engine, _) in DIAGRAMS.items()
                            if engine not in ('multivariate', 'exploration'))
STATISTICS_DIAGRAMS = tuple(name for name, (engine, _) in DIAGRAMS.items()
                           if engine in ('multivariate', 'exploration') and '3D' not in name)
NUMERIC_COLUMNS = {"Ca", "Mg", "Na", "K", "HCO3", "CO3", "Cl", "SO4", "pH", "TDS"}
MARKERS = ("o", "s", "^", "D", "v", "P", "X", "*")
