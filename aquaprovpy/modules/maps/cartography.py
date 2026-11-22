"""Map-aligned colour scales, coordinate grids and a geographic north arrow."""
import numpy as np
from matplotlib.artist import Artist
from matplotlib.patches import FancyArrowPatch
from matplotlib.text import Text
from matplotlib.ticker import MaxNLocator, MultipleLocator
from matplotlib.transforms import Bbox
from mpl_toolkits.axes_grid1.axes_size import _Base

from ...boundaries import transform_xy
from .furniture import NorthArrow, ScaleBar


class _ColourbarPadding(_Base):
    """Measure labels without resetting the parent divider's axes position."""
    def __init__(self, axis, location, gap):
        self.axis, self.location, self.gap = axis, location, gap
        self.size = gap

    def get_size(self, renderer):
        # Tight export freezes locators without a renderer after measuring the
        # page. Retain that renderer's physical spacing for the cropped pass.
        if renderer is None:
            return 0, self.size
        axis = self.axis
        boxes = [axis.bbox]
        if axis.axison:
            for component in (axis.xaxis, axis.yaxis):
                bounds = component.get_tightbbox(renderer)
                if bounds is not None:
                    boxes.append(bounds)
        for child in axis.child_axes:
            if child.get_visible() and child.get_in_layout():
                bounds = child.get_tightbbox(renderer)
                if bounds is not None:
                    boxes.append(bounds)
        axis._update_title_position(renderer)
        boxes.extend(text.get_window_extent(renderer) for text in
                     (axis.title, axis._left_title, axis._right_title)
                     if text.get_visible() and text.get_text())
        bounds = Bbox.union(boxes)
        extra = {'right': bounds.x1-axis.bbox.x1, 'left': axis.bbox.x0-bounds.x0,
                 'top': bounds.y1-axis.bbox.y1, 'bottom': axis.bbox.y0-bounds.y0}[self.location]
        self.size = self.gap + max(0, extra)/renderer.points_to_pixels(72)
        return 0, self.size


def aligned_colorbar(axis, mappable, label, orientation='vertical', map_layout=None, colorbar_options=None):
    """Keep the scale attached to the actual map box through resize and export."""
    from mpl_toolkits.axes_grid1 import make_axes_locatable
    if orientation not in ('vertical', 'horizontal', 'left', 'top'):
        raise ValueError('Choose a colour scale beside or above/below the plot.')
    location = {'vertical':'right','horizontal':'bottom'}.get(orientation,orientation)
    orientation = 'vertical' if location in ('left','right') else 'horizontal'
    placement = colorbar_options or {}
    from matplotlib.layout_engine import ConstrainedLayoutEngine
    if isinstance(axis.figure.get_layout_engine(), ConstrainedLayoutEngine):
        # Axes dividers are invisible to constrained layout: a bottom scale
        # can be pushed off the page. Register it with the layout engine,
        # then align its length with the actual equal-aspect map frame.
        perpendicular = axis.get_position().width * axis.figure.get_figwidth() if orientation=='vertical' else axis.get_position().height * axis.figure.get_figheight()
        fraction = min(.3, placement.get('width',6)/72/perpendicular) if placement else .045
        pad = placement.get('gap',6)/72/perpendicular if placement else (.12 if orientation=='horizontal' else .06)
        bar = axis.figure.colorbar(mappable, ax=axis, location=location, fraction=fraction, pad=pad, label=label)
        bar.ax._aquaprov_colorbar_placement = placement
        from ...figure_presentation import align_figure_colorbars
        align_figure_colorbars(axis.figure)
        return bar
    divider = make_axes_locatable(axis)
    # Divider padding is measured from the map border, unlike constrained
    # layout which already reserves its decorations. Include the rendered
    # coordinate labels (also secondary geographic axes), axis labels and
    # title before adding the requested clearance. Remeasure on every draw.
    padding = _ColourbarPadding(axis, location, placement.get('gap', 6)/72)
    cax = divider.append_axes(location, size=placement['width']/72 if placement else '4%',
                             pad=padding)
    cax.set_label('<colorbar>')
    bar = axis.figure.colorbar(mappable, cax=cax, location=location, label=label)
    cax._aquaprov_colorbar_placement = placement
    cax._aquaprov_colorbar_parents = [axis]
    from ...figure_presentation import align_figure_colorbars
    align_figure_colorbars(axis.figure)
    return bar


class GridLocator(MultipleLocator):
    """Retain user spacing unless zooming out would create excessive grid lines."""
    def __init__(self, spacing):
        self.spacing = spacing
        super().__init__(spacing)

    def tick_values(self, vmin, vmax):
        if abs(vmax - vmin) / self.spacing > 200:
            return MaxNLocator(nbins=8).tick_values(vmin, vmax)
        return super().tick_values(vmin, vmax)


def north_vector(crs, x, y, reference='true'):
    if reference == 'grid':
        return np.array([0., 1.])
    if reference != 'true':
        raise ValueError('Choose true north or grid north.')
    if crs in (None, 'local'):
        raise ValueError('True north needs a source coordinate system. Select a CRS in Data, '
                         'or choose Grid north / +Y for local coordinates.')
    from pyproj import Geod
    lon, lat = transform_xy(x, y, crs, 'EPSG:4326')
    if abs(float(lat)) >= 89.9:
        raise ValueError('True north is undefined at the pole.')
    nlon, nlat, _ = Geod(ellps='WGS84').fwd(float(lon), float(lat), 0., 100.)
    nx, ny = transform_xy(nlon, nlat, 'EPSG:4326', crs)
    vector = np.array([float(nx)-x, float(ny)-y])
    if not np.isfinite(vector).all() or np.linalg.norm(vector) == 0:
        raise ValueError('Could not determine north in the selected coordinate system.')
    return vector / np.linalg.norm(vector)


LAYOUT_DEFAULTS = dict(north_design='arrow',north_size=36.,north_position=[.88,.76],
    scale_bar=False,scale_design='alternating',scale_unit='km',scale_length=0.,scale_segments=4,
    scale_position=[.12,.10],scale_background=True,scale_font_size=8.,local_unit=None,
    coordinate_mode='native',coordinate_format='dms',coordinate_precision=0,coordinate_font_size=8.,
    frame_sides='bottom_left',longitude_interval=0.,latitude_interval=0.,minor_ticks=False,
    grid_spacing_y=0.,grid_design='dashed',grid_width=.55,grid_color='#687c8d',grid_alpha=.5)


def layout_options(layout):
    from copy import deepcopy
    from matplotlib.colors import is_color_like
    options = deepcopy(LAYOUT_DEFAULTS)
    if layout:
        if set(layout)-set(options):
            raise ValueError('Unknown map layout options: '+', '.join(sorted(set(layout)-set(options))))
        options.update(deepcopy(layout))
    for key, choices in {'north_design':('arrow','chevron','compass','nautical'),
            'scale_design':('alternating','line','dual'),'scale_unit':('m','km','mi','ft'),
            'coordinate_mode':('native','geographic'),'coordinate_format':('decimal','dm','dms'),
            'frame_sides':('bottom_left','all'),'grid_design':('solid','dashed','dotted','crosses','frame'),
            'local_unit':(None,'m','km','mi','ft')}.items():
        if options[key] not in choices:
            raise ValueError('Invalid map option: '+key)
    for key in ('north_position','scale_position'):
        point = np.asarray(options[key],float)
        if point.shape != (2,) or not np.isfinite(point).all() or (point<0).any() or (point>1).any():
            raise ValueError('Map element positions must lie within the map frame.')
        options[key] = point.tolist()
    for key,low,high in [('north_size',12,120),('scale_length',0,1e9),('scale_segments',2,8),
            ('coordinate_precision',0,6),('coordinate_font_size',5,20),('scale_font_size',5,20),
            ('grid_width',.1,4),('grid_alpha',0,1),('grid_spacing_y',0,1e9),
            ('longitude_interval',0,180),('latitude_interval',0,90)]:
        if not np.isfinite(options[key]) or not low<=options[key]<=high:
            raise ValueError('Map option out of range: '+key)
    if not is_color_like(options['grid_color']):
        raise ValueError('Choose a valid grid colour.')
    return options


class NativeCrossGrid(Artist):
    def __init__(self, axis, show, options):
        super().__init__()
        self.show, self.options = show, options
        self.set_zorder(2.4); self.set_in_layout(False)
        axis.add_artist(self)

    def draw(self, renderer):
        if not self.show:
            return
        from matplotlib.lines import Line2D
        x,y = np.meshgrid(self.axes.get_xticks(),self.axes.get_yticks())
        o = self.options
        points = Line2D(x.ravel(),y.ravel(),linestyle='none',marker='+',markersize=4,
                        markeredgewidth=o['grid_width'],color=o['grid_color'],alpha=o['grid_alpha'],
                        transform=self.axes.transData)
        points.set_figure(self.figure); points.axes = self.axes
        points.set_clip_path(self.axes.patch); points.draw(renderer)


def decorate_map(axis, crs, *, show_grid=False, grid_spacing=0., north_arrow=False, north_reference='true', layout=None):
    if not np.isfinite(grid_spacing) or grid_spacing < 0:
        raise ValueError('Grid spacing must be non-negative; zero selects automatic spacing.')
    from matplotlib.ticker import AutoMinorLocator
    options = layout_options(layout)
    axis.figure._aquaprov_map_layout = options
    axis._aquaprov_display_crs = crs
    if options['coordinate_mode']=='geographic':
        from .graticule import geographic_frame
        geographic_frame(axis,crs,options,show_grid)
    else:
        for component,spacing in [(axis.xaxis,grid_spacing),(axis.yaxis,options['grid_spacing_y'] or grid_spacing)]:
            component.set_major_locator(GridLocator(spacing) if spacing else MaxNLocator(nbins=7))
            component.set_tick_params(labelsize=options['coordinate_font_size'])
            if options['minor_ticks']:
                component.set_minor_locator(AutoMinorLocator(2))
        all_sides = options['frame_sides']=='all'
        axis.tick_params(top=all_sides,right=all_sides,labeltop=all_sides,labelright=all_sides)
        if show_grid and options['grid_design'] not in ('crosses','frame'):
            axis.grid(True,color=options['grid_color'],linestyle=options['grid_design'],
                      linewidth=options['grid_width'],alpha=options['grid_alpha'])
        else:
            axis.grid(False)
            if options['grid_design']=='crosses':
                axis._aquaprov_custom_grid = NativeCrossGrid(axis,show_grid,options)
    axis.set_axisbelow(False)
    if north_arrow:
        NorthArrow(axis, crs, north_reference, design=options['north_design'],size=options['north_size'],position=options['north_position'])
    if options['scale_bar']:
        ScaleBar(axis,crs,design=options['scale_design'],unit=options['scale_unit'],length=options['scale_length'],
                 segments=int(options['scale_segments']),position=options['scale_position'],local_unit=options['local_unit'],
                 background=options['scale_background'],font_size=options['scale_font_size'])
    return options
