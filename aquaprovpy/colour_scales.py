"""Shared colour scales for plot rendering and the desktop palette selector."""
import json
from pathlib import Path

from matplotlib import colormaps
from matplotlib.colors import LinearSegmentedColormap


# Keep these identifiers stable: projects and style presets store them verbatim.
COLOUR_SCALES = (
    ('turbo', 'Turbo'),
    ('rainbow_cyclic', 'Rainbow (cyclic)'),
    ('jet', 'Jet'),
    ('parula', 'Parula'),
    ('si_blues', 'Deep Blue-Light Blue (SI)'),
    ('hot', 'Hot'),
    ('bone', 'Bone'),
    ('viridis', 'Viridis'),
    ('plasma', 'Plasma'),
    ('magma', 'Magma'),
    ('cividis', 'Cividis'),
    ('coolwarm', 'Coolwarm'),
    ('hsv', 'HSV (cyclic)'),
    ('seismic', 'Seismic'),
    ('Spectral', 'Spectral'),
    ('RdYlBu', 'Red-Yellow-Blue'),
    ('ocean', 'Ocean'),
    ('terrain', 'Terrain'),
    ('gist_earth', 'Earth'),
    ('twilight', 'Twilight (cyclic)'),
    ('copper', 'Copper'),
    ('YlGnBu', 'Yellow-Green-Blue'),
    ('Greys', 'Grayscale'),
    ('bwr', 'Blue-White-Red'),
    ('PiYG', 'Pink-Yellow-Green'),
    # Additional scales offered by earlier AquaProv versions.
    ('RdBu_r', 'Blue-Red'),
    ('RdYlBu_r', 'Blue-Yellow-Red'),
    ('PuOr_r', 'Purple-Orange'),
    ('BrBG_r', 'Green-Brown'),
    ('YlOrRd', 'Yellow-Orange-Red'),
)
COLOUR_SCALE_LABELS = dict(COLOUR_SCALES)


def colour_scale_label(name):
    return COLOUR_SCALE_LABELS.get(name, name)


def register_colour_scales():
    """Register custom palettes for GUI and headless Matplotlib use."""
    if 'parula' not in colormaps:
        resource = Path(__file__).with_name('assets') / 'colour-scales' / 'parula.json'
        colours = json.loads(resource.read_text(encoding='utf-8'))['colours']
        colormaps.register(LinearSegmentedColormap.from_list('parula', colours, N=256))
    if 'rainbow_cyclic' not in colormaps:
        colormaps.register(LinearSegmentedColormap.from_list('rainbow_cyclic', (
            '#8000ff', '#004cff', '#00d4e8', '#32d12c', '#ffff00', '#ff9100', '#ff2000', '#8000ff',
        ), N=256))
    if 'si_blues' not in colormaps:
        # Blue-side anchors of ColorBrewer RdBu, used by the reference SI maps.
        # Low values are deep blue; high values are light blue in every module.
        colormaps.register(LinearSegmentedColormap.from_list('si_blues', (
            '#053061', '#2166ac', '#4393c3', '#92c5de', '#d1e5f0',
        ), N=256))
    for name in ('parula', 'rainbow_cyclic', 'si_blues'):
        if name + '_r' not in colormaps:
            colormaps.register(colormaps[name].reversed())


def normalize_colourbar_labels(figure, enabled, label=''):
    """Display a continuous scale in its 0–1 colour coordinates, reversibly.

    Matplotlib already maps scalar values to 0–1 through each artist's norm.
    Label that coordinate system without altering samples, contour levels, SI
    zero centres, logarithmic mappings or the mappable linked to the colourbar.
    """
    import numpy as np
    from matplotlib.colors import BoundaryNorm, NoNorm
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

    for axis in figure.axes:
        bar = getattr(axis, '_colorbar', None)
        if bar is None:
            continue
        previous = getattr(bar, '_aquaprov_scale_ticks', None)
        if previous is not None:
            # A replacement norm installs its own tick defaults in Matplotlib.
            if bar.norm is previous['norm']:
                bar.locator = previous['locator']
                bar.formatter = previous['formatter']
                bar.minorlocator = previous['minorlocator']
                bar.update_ticks()
            del bar._aquaprov_scale_ticks
        if (not enabled or isinstance(bar.norm, (BoundaryNorm, NoNorm))
                or getattr(bar.mappable, '_aquaprov_fixed_cmap', False)):
            continue
        norm = bar.norm
        if (norm.vmin is None or norm.vmax is None
                or not np.isfinite([norm.vmin, norm.vmax]).all() or norm.vmin >= norm.vmax):
            continue
        try:
            ticks = np.asarray(norm.inverse(np.linspace(0., 1., 6)), dtype=float)
        except (ValueError, TypeError, NotImplementedError):
            continue
        if not np.isfinite(ticks).all():
            continue
        bar._aquaprov_scale_ticks = dict(norm=norm, locator=bar.locator,
                                         formatter=bar.formatter, minorlocator=bar.minorlocator)
        bar.locator = FixedLocator(ticks)
        bar.formatter = FuncFormatter(
            lambda value, position, mapping=norm:
            f'{float(np.clip(mapping(value), 0., 1.)):.1f}'.rstrip('0').rstrip('.'))
        bar.minorlocator = NullLocator()
        bar.update_ticks()
        # A saved physical-unit label must not describe the new 0–1 ticks as
        # concentrations. Preserve custom wording while identifying the scale.
        normalized = 'Normalized colour scale (0–1)'
        bar.set_label(f'{label}\nNormalized (0–1)' if label else normalized)
