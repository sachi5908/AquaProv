"""User-facing plot library and routes into each module's existing controls."""
from dataclasses import dataclass
from ..core.catalog import (DIAGRAMS, DIAGRAM_INPUT_NOTES, STATISTICAL_VIEWS, EXPLORATORY_VIEWS,
                            GROUNDWATER_DIAGRAMS, STATISTICS_DIAGRAMS)


@dataclass(frozen=True)
class PlotChoice:
    key: str
    title: str
    group: str
    description: str
    routes: tuple


def plot_choices(module):
    if module == 'saturation':
        from ..saturation.data import VIEWS, SPATIAL_VIEWS
        return tuple(PlotChoice(key,title,'Spatial SI' if key in SPATIAL_VIEWS else 'Mineral saturation',
            'Explore measured or PHREEQC-calculated SI; review database provenance, exclusions and scientific interpretations in Results & methods.',
            (('si_view_combo',title),)) for key,title in VIEWS.items())
    if module == 'water_quality':
        from ..water_quality.engine import VIEWS, SPATIAL_VIEWS
        choices = []
        for index in ('WQI', 'DWQI'):
            for key, title in VIEWS.items():
                if key in ('comparison', 'index_scatter'):
                    continue
                group = index + (' · spatial maps' if key in SPATIAL_VIEWS else ' · distributions & compliance')
                description = ('Choose site coordinates and IDW or ordinary kriging; review the calculation method and standards.'
                               if key in SPATIAL_VIEWS else 'Calculate the selected index; review weights, limits, sample counts and classification in Results & methods.')
                choices.append(PlotChoice(index.lower()+'_'+key, index+' · '+title, group, description,
                    (('wq_index_combo',index),('wq_view_combo',title))))
        choices.append(PlotChoice('comparison',VIEWS['comparison'],'Compare indices',
            'Side-by-side maps retain separate WQI and DWQI calculations, scales and classifications.',
            (('wq_index_combo','WQI'),('wq_view_combo',VIEWS['comparison']))))
        choices.append(PlotChoice('index_scatter', VIEWS['index_scatter'], 'Compare indices',
            'Compare recalculated WQI and DWQI for paired source observations; optional independent threshold highlighting.',
            (('wq_index_combo','WQI'), ('wq_view_combo', VIEWS['index_scatter']))))
        return tuple(choices)
    if module == 'assessment':
        from ..assessment.engine import VIEWS
        descriptions = {
            'qa': 'Inspect units, qualifiers, missing ions and charge balance before drawing conclusions.',
            'uncertainty': 'Propagate supplied SDs or explicit sensitivity scenarios to SAR and graphical class probabilities.',
            'piper': 'Marginal intervals for measured major-ion compositions and dominant-ion facies probabilities.',
            'screening': 'Compare named chemical species with a versioned screening profile; review unassessed chemicals.',
            'priorities': 'Rank follow-up assays by threshold ambiguity under an equal-cost budget.',
            'scenarios': 'Compare fixed values, relative SD, uniform censoring and half-limit substitution without averaging assumptions.',
            'coda': 'ILR PCA with an exported orthonormal basis; positive non-overlapping concentration components only.',
            'stability': 'Bootstrap Ward clusters and inspect co-assignment stability. Use independent sample rows.',
            'spatial': 'Fit variograms on training observations and compare held-out geographic blocks with IDW and mean baselines.',
            'spatial_map': 'Map a fitted variogram after blocked validation; conditional uncertainty is masked outside the sample convex hull.',
            'wells': 'Bootstrap whole wells and inspect descriptive within-well trends, respecting repeated sampling.',
        }
        return tuple(PlotChoice(key, title, 'Quality & decisions' if key in ('qa', 'uncertainty', 'piper', 'screening', 'priorities', 'scenarios') else 'Robustness & validation',
                                descriptions[key], (('assessment_view_combo', title),)) for key, title in VIEWS.items())
    if module in ("groundwater", "statistics"):
        choices = []
        for name in GROUNDWATER_DIAGRAMS if module == 'groundwater' else STATISTICS_DIAGRAMS:
            engine, required = DIAGRAMS[name]
            if engine in ("ussl", "wilcox"):
                group, description = "Irrigation assessment", "Set concentration and measured EC units; review classifications in Results & methods."
            elif name in EXPLORATORY_VIEWS:
                group, description = "Time series & uncertainty", "Select the measurement and sampling options for this plot."
            elif name in STATISTICAL_VIEWS:
                group = "Multivariate statistics"
                description = "Select measurement variables and the method settings below. IDs and coordinates are not chemical measurements."
            else:
                group = "Geochemical diagrams"
                description = DIAGRAM_INPUT_NOTES.get(engine) or (
                    "Required columns: " + ", ".join(required.split()) + ". Set units and sample appearance before generating.")
            choices.append(PlotChoice(name, name, group, description, (("diagram_combo", name),)))
        return tuple(choices)
    if module == "maps":
        return tuple(PlotChoice(key, title, group, description, (("spatial_method_combo", route),)) for key, title, group, description, route in (
            ("locations", "Sample locations", "Sample maps", "Choose coordinate columns, a background and the source CRS in Data.", "Sample locations"),
            ("kriging", "Kriging contours", "Spatial interpolation", "Set distance coordinates, variogram, range, partial sill and nugget. Style the contour lines and sample markers below.", "Ordinary kriging · contours"),
            ("variance", "Kriging prediction variance", "Spatial interpolation", "Prediction variance in squared measurement units, conditional on your variogram settings.", "Ordinary kriging · variance"),
            ("idw", "IDW contours", "Spatial interpolation", "Set distance coordinates, inverse-distance power and grid size. No prediction variance is inferred.", "IDW · contours"),
        ))
    return (
        PlotChoice("xyz_scatter", "XYZ sample scatter", "Measurements in 3D", "Choose X, Y and Z measurements. Set marker appearance and the camera for this plot.", (("three_d_mode_combo", "XYZ scatter"),)),
        PlotChoice("xyz_surface", "XYZ interpolated surface", "Measurements in 3D", "Choose X, Y and Z. Control surface resolution, opacity, mesh edges and sample visibility.", (("three_d_mode_combo", "XYZ surface (linear)"),)),
        PlotChoice("pca_scores", "PCA · 3D sample scores", "Multivariate statistics", "Select chemical variables, retained components, scaling and rotation for a 3D score view.", (("three_d_mode_combo", "PCA 3D"), ("diagram_combo", "PCA · 3D sample scores"))),
        PlotChoice("pca_loadings", "PCA · 3D component loadings", "Multivariate statistics", "Explore how the selected variables load on three components; configure the PCA model below.", (("three_d_mode_combo", "PCA 3D"), ("diagram_combo", "PCA · 3D component loadings"))),
    )
