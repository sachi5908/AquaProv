"""Data-driven SI figures with zero-centred scales and auditable spatial grids."""
from copy import deepcopy
from textwrap import fill

import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, TwoSlopeNorm
from matplotlib.cm import ScalarMappable
from matplotlib.patches import Patch, PathPatch
import numpy as np
import pandas as pd

from .._publication import PlotResult, STYLE, close_on_error
from ..plot_layout import CellTextLayout, ContourLabelLayout, TickLabelLayout, outside_legend, point_labels
from .. import boundaries
from ..modules.maps.cartography import aligned_colorbar, decorate_map
from ..modules.maps.interpolation import interpolate, planar_coordinates
from ..modules.maps.projections import analysis_coordinates
from ..modules.maps.classification import display_classes, class_table
from .data import CLASSES, CLASS_COLORS, SPATIAL_VIEWS, VIEWS, classify, numeric
from .engine import calculate


class SIInspector:
    """Hover labels survive the shared Agg-to-Qt canvas handoff."""
    def __init__(self, figure, layers=(), heatmap=None):
        self.figure, self.layers, self.heatmap = figure, layers, heatmap
        self.annotations = {}
        axes = {artist.axes for artist, _ in layers}
        if heatmap is not None:
            axes.add(heatmap[0])
        for ax in axes:
            note = ax.annotate('', (0, 0), xytext=(10, 10), textcoords='offset points', fontsize=8,
                               bbox=dict(boxstyle='round', fc='white', alpha=.96), zorder=30)
            note.set_visible(False)
            note.set_in_layout(False)
            self.annotations[ax] = note
        self.cid = figure.canvas.mpl_connect('motion_notify_event', self.move)

    def move(self, event):
        changed = False
        for ax, note in self.annotations.items():
            label = None
            if event.inaxes is ax:
                if self.heatmap is not None and ax is self.heatmap[0] and event.xdata is not None and event.ydata is not None:
                    text = self.heatmap[1]
                    x, y = int(np.floor(event.xdata+.5)), int(np.floor(event.ydata+.5))
                    if 0 <= y < text.shape[0] and 0 <= x < text.shape[1]:
                        label = text[y, x]
                for artist, labels in self.layers:
                    if artist.axes is ax:
                        hit, info = artist.contains(event)
                        if hit:
                            indices = info.get('ind', [0])
                            if len(indices):
                                label = labels[indices[0]]
                                break
            visible = label is not None
            changed |= visible or note.get_visible() != visible
            if visible:
                note.xy = (event.xdata, event.ydata)
                note.set_text('\n'.join(fill(line,48) for line in label.splitlines()))
                note.set_visible(True)
                note.set_position((10,10))
                renderer = self.figure.canvas.get_renderer()
                box = note.get_window_extent(renderer)
                bounds = self.figure.bbox.padded(-12)
                dx = max(0,bounds.x0-box.x0) - max(0,box.x1-bounds.x1)
                dy = max(0,bounds.y0-box.y0) - max(0,box.y1-bounds.y1)
                scale = renderer.points_to_pixels(1)
                note.set_position((10+dx/scale,10+dy/scale))
            note.set_visible(visible)
        if changed:
            self.figure.canvas.draw_idle()


def _norm(values, config):
    limit = config.get('color_limit')
    if limit is None:
        finite = np.asarray(values, float)
        finite = finite[np.isfinite(finite)]
        limit = max(float(np.abs(finite).max()), .1) if len(finite) else 1.
    if not np.isfinite(limit) or limit <= 0:
        raise ValueError('SI colour limit must be positive; the diverging scale is symmetric around zero.')
    return TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit)


def _label(row):
    value = f'{row.SI:.6g}' if np.isfinite(row.SI) else 'unassessed'
    return f'{row.sample} | {row.mineral}\nSI: {value}\n{row.classification}\nSource row {row.source_row}'


def _matrix(records, config):
    data = records.copy()
    if config.get('layout', 'wide') == 'long' and config.get('mode', 'import') == 'import':
        data['observation'] = data['sample']
        if data.duplicated(['observation','mineral']).any():
            raise ValueError('Repeated sample/mineral pairs cannot be paired unambiguously. Filter a group or '
                             'use unique sample-event identifiers for comparisons, heatmaps and mineral scatter plots.')
    else:
        data['observation'] = data['sample']
        # Keep repeated sample names as separate measured rows in wide tables.
        repeat = data[['source_row','sample']].drop_duplicates()['sample'].duplicated(keep=False)
        duplicate_names = data[['source_row','sample']].drop_duplicates().loc[repeat, 'sample']
        mask = data['sample'].isin(duplicate_names)
        data.loc[mask,'observation'] = data.loc[mask,'sample'] + ' [row ' + data.loc[mask,'source_row'].astype(str) + ']'
    order = list(dict.fromkeys(data.observation))
    minerals = list(dict.fromkeys(data.mineral))
    matrix = data.pivot(index='observation',columns='mineral',values='SI').reindex(index=order, columns=minerals)
    return matrix, data


def _spatial(ax, frame, result, config, layers):
    mineral = config.get('mineral') or result.records.mineral.iloc[0]
    records = result.records[result.records.mineral == mineral].copy()
    if records.empty:
        raise ValueError('Select a mapped mineral included in the current mineral filter.')
    x, y = config.get('x'), config.get('y')
    if x not in frame or y not in frame or x == y:
        raise ValueError('Choose distinct X and Y coordinate columns.')
    source = frame[[x,y]].apply(pd.to_numeric, errors='coerce').to_numpy(dtype=float)
    records['source_x'], records['source_y'] = source[records.source_row.to_numpy()-1].T
    good_xy = np.isfinite(records[['source_x','source_y']]).all(axis=1)
    records['spatial_status'] = np.where(records.SI.isna(), 'Unassessed SI',
                                          np.where(good_xy, 'Included', 'Missing/invalid coordinates'))
    usable = records[records.spatial_status == 'Included'].copy()
    if usable.empty:
        raise ValueError('No assessed SI values have valid coordinates.')
    xy, xlabel, ylabel, projection = analysis_coordinates(usable[['source_x','source_y']].to_numpy(), config.get('coordinates'),
        boundary=config.get('boundary'),source_crs=config.get('source_crs'),target_crs=config.get('target_crs'))
    crs = projection['analysis_crs']
    if config.get('coordinates') == 'wgs84':
        if config.get('source_crs') not in (None,'local','EPSG:4326'):
            raise ValueError('WGS84 distance coordinates conflict with the declared source CRS.')
        crs = boundaries.local_crs(projection)
        if config.get('boundary'):
            geographic = boundaries.geometry_in_crs(config['boundary'],'EPSG:4326',declared_local_crs='EPSG:4326')
            west,south,east,north = geographic.bounds
            if (max(east,usable.source_x.max())-min(west,usable.source_x.min())>3 or
                    max(north,usable.source_y.max())-min(south,usable.source_y.min())>3):
                raise ValueError('Study boundary exceeds the local 3-degree distance approximation. Use a suitable projected CRS.')
    elif crs == 'EPSG:4326':
        raise ValueError('Longitude/latitude require WGS84 distance coordinates, not projected units.')
    usable['map_x'], usable['map_y'] = xy.T
    records.loc[usable.index, ['analysis_x','analysis_y']] = xy
    area = boundaries.geometry_in_crs(config['boundary'], crs,
        declared_local_crs='EPSG:4326' if config.get('coordinates') in ('wgs84','auto_utm','wgs84_projected') else crs) if config.get('boundary') else None
    if area is not None:
        config['boundary'] = boundaries.make_boundary(area,crs,name=config['boundary'].get('name','Study area'))
    if area is not None:
        vertices = []
        parts = [area] if area.geom_type == 'Polygon' else area.geoms
        for part_id, part in enumerate(parts, 1):
            for ring_id, ring in enumerate([part.exterior, *part.interiors]):
                vertices.extend(dict(part=part_id, ring=ring_id, hole=ring_id>0, vertex=i+1, x=x, y=y)
                                for i,(x,y) in enumerate(ring.coords))
        result.tables['boundary_vertices'] = pd.DataFrame(vertices)
    if area is not None and config.get('samples_inside_boundary', False):
        inside = boundaries.point_mask(area, xy)
        records.loc[usable.index[~inside],'spatial_status'] = 'Outside study boundary'
        usable = usable[inside].copy()
        xy = xy[inside]
        if usable.empty:
            raise ValueError('No assessed samples fall inside the study boundary.')
    result.tables['spatial_records'] = records
    excluded = int((records.spatial_status != 'Included').sum())
    if excluded:
        result.warnings.append(f'{excluded} selected observation(s) omitted from this map; see spatial_records.')
    grid = None
    variance = config['view']=='interpolation' and config.get('surface','si')=='variance'
    if config['view'] == 'interpolation':
        options = {key:value for key,value in config.get('spatial',{}).items()
                   if key in ('method','resolution','model','range_','sill','nugget','power','neighbors','cell_size')}
        grid = interpolate(usable,'map_x','map_y','SI',coordinates='projected',source_crs=crs,
                           boundary=config.get('boundary'), extrapolate=config.get('extrapolate',False), **options)
        if variance and grid.metadata['method'] != 'ordinary kriging':
            raise ValueError('Prediction variance is available for ordinary kriging only.')
        table = pd.DataFrame(dict(x=grid.x.ravel(), y=grid.y.ravel(), SI=grid.values.ravel(),
                                 inside_sample_hull=grid.inside_sample_hull.ravel(), inside_boundary=grid.inside_boundary.ravel()))
        table['classification'] = classify(table.SI)
        table['extrapolated'] = table.SI.notna() & ~table.inside_sample_hull
        if grid.metadata['method'] == 'ordinary kriging':
            table['variance_SI_squared'] = grid.variance.ravel()
            result.warnings.append('Kriging uses user-supplied variogram parameters; its variance is conditional on those parameters and excludes PHREEQC/input uncertainty.')
        result.tables['interpolation_grid'] = table
        grid.metadata.update(input_coordinates=config.get('coordinates'),coordinate_conversion=projection)
        result.metadata['interpolation'] = grid.metadata
        result.warnings.append('The interpolated field is SI in log10 units, not interpolated ion activities or a PHREEQC calculation at unsampled locations. Assess sampling support before interpretation.')
        if config.get('extrapolate',False):
            result.warnings.append('Full-boundary coverage includes extrapolation beyond the sample convex hull; exported cells identify this region. Disable Fill entire boundary to restrict predictions to the sampled area.')
        if area is not None:
            result.warnings.append('The study boundary clips predictions; it is not a groundwater flow barrier or a kriging boundary condition.')
    sx, sy = xy.T
    gx, gy = (grid.x,grid.y) if grid is not None else (None,None)
    clip = grid.clip_geometry if grid is not None else None
    display_crs = crs
    provider = config.get('basemap','plain')
    if provider != 'plain':
        if crs == 'local':
            raise ValueError('A geographic basemap requires a declared source CRS.')
        from shapely.ops import transform
        def mercator(x,y,z=None):
            return boundaries.transform_xy(x,y,crs,'EPSG:3857')
        sx,sy = mercator(sx,sy)
        if grid is not None:
            gx,gy = mercator(gx,gy)
            clip = transform(mercator,clip)
        if area is not None:
            area = transform(mercator,area)
        display_crs = 'EPSG:3857'
        xlabel,ylabel = 'Web Mercator easting (m)','Web Mercator northing (m)'
        from ..basemaps import add_attribution
        add_attribution(ax,provider)
        ax.figure._aquaprov_si_map_axes = [ax]
    records.loc[usable.index, ['display_x','display_y']] = np.column_stack((sx,sy))
    if grid is not None and display_crs != crs:
        result.tables['interpolation_grid']['display_x'] = gx.ravel()
        result.tables['interpolation_grid']['display_y'] = gy.ravel()
    values = usable.SI.to_numpy() if grid is None else np.r_[usable.SI,grid.values.ravel()]
    si_norm = _norm(values,config)
    si_cmap = config.get('cmap','RdBu_r')
    norm, cmap = si_norm, si_cmap
    if variance:
        norm = Normalize(vmin=0., vmax=max(float(np.nanmax(grid.variance)), 1e-12))
        cmap = config.get('variance_cmap','viridis')
    filled = None
    if grid is not None:
        levels = config.get('levels',12)
        if not isinstance(levels,int) or not 2 <= levels <= 40:
            raise ValueError('Use 2 to 40 contour levels.')
        opacity = config.get('surface_alpha',.8)
        if not np.isfinite(opacity) or not 0 < opacity <= 1:
            raise ValueError('Contour opacity must be greater than zero and at most one.')
        rendered = grid.render_variance if variance else grid.render_values
        visible = grid.variance if variance else grid.values
        bounds = np.linspace(norm.vmin,norm.vmax,levels+1)
        if not variance:
            bounds = np.unique(np.r_[bounds,0.])
        bounds, classes = display_classes(visible, config, bounds)
        if (not variance and classes['method'] not in ('automatic','custom')
                and np.nanmin(visible) < 0 < np.nanmax(visible) and not np.any(bounds == 0)):
            # A colour band must not merge under- and supersaturation.
            bounds = np.sort(np.r_[bounds,0.])
            classes.update(boundaries=bounds.tolist(),class_count=len(bounds)-1,zero_boundary_added=True)
            result.warnings.append('SI = 0 was added as a display boundary to separate under- and supersaturation; the displayed class count may exceed the requested count by one.')
        result.metadata['display_classification'] = classes
        result.tables['class_boundaries'] = class_table(classes)
        if classes['method'] != 'automatic':
            from matplotlib.colors import BoundaryNorm, ListedColormap
            # Colour each band through the zero-centred SI scale, even with uneven breaks.
            cmap = ListedColormap(plt.get_cmap(cmap)(norm((bounds[:-1]+bounds[1:])/2)))
            norm = BoundaryNorm(bounds, cmap.N)
        patch = PathPatch(boundaries.polygon_path(clip),transform=ax.transData)
        drawing = config.get('surface_drawing', 'default')
        if drawing in ('default','contours'):
            filled = ax.contourf(gx,gy,rendered,levels=bounds,cmap=cmap,norm=norm,alpha=opacity,extend='max' if variance else 'both')
        elif drawing == 'raster':
            filled = ax.pcolormesh(gx,gy,rendered,shading='nearest',cmap=cmap,norm=norm,alpha=opacity,rasterized=True)
        else:
            raise ValueError('Choose filled contours or classified raster cells.')
        if classes['method'] != 'automatic':
            filled._aquaprov_fixed_cmap = True
        result.metadata['surface_drawing'] = 'contours' if drawing == 'default' else drawing
        from ..plot_legends import scale_legend
        scale_legend(ax, filled, 'Prediction variance' if variance else 'Interpolated SI')
        filled.set_gid('aquaprov-si-surface')
        filled.set_clip_path(patch)
        low, high = np.nanmin(visible), np.nanmax(visible)
        zero = not variance and config.get('zero_contour',True) and low < 0 < high
        contour_texts = []

        def contour_lines(levels, width, fmt=None):
            if not len(levels):
                return
            lines = ax.contour(gx,gy,rendered,levels=levels,colors=config.get('line_color','#214b60'),linewidths=width)
            from ..plot_legends import contour_legend
            contour_legend(ax, lines, 'SI = 0 contour' if len(levels) == 1 and levels[0] == 0 else 'SI contour lines')
            lines.set_clip_path(patch)
            if config.get('contour_labels',True):
                texts = ax.clabel(lines,fmt=fmt,fontsize=8,inline=True)
                contour_texts.extend(texts)
                for text in texts:
                    text.set_clip_path(patch)
                    text.set_clip_on(True)

        width = config.get('line_width',.5)
        if config.get('contour_lines',True) and high > low:
            ordinary = bounds[(bounds>low)&(bounds<high)]
            if zero:
                ordinary = ordinary[ordinary!=0]
            contour_lines(ordinary,width)
        if zero:
            contour_lines([0.],max(width,1.),{0.:'SI = 0'})
        if contour_texts:
            ContourLabelLayout(ax,contour_texts,prefer_points=True)
    if grid is None or config.get('show_samples',True):
        point_colors = (dict(c=usable.SI,cmap=si_cmap,norm=si_norm)
                        if not variance and config.get('sample_coloring','si')=='si'
                        else dict(color=config.get('sample_color','white')))
        points = ax.scatter(sx,sy,**point_colors,s=config.get('sample_size',40),
                            marker=config.get('marker','o'),alpha=config.get('sample_alpha',1.),
                            edgecolors='#26384a',linewidths=.6,zorder=5,label='Sample locations')
        points.set_gid('aquaprov-si-samples')
        layers.append((points,[_label(row) for row in usable.itertuples()]))
        if filled is None:
            filled = ScalarMappable(norm=si_norm,cmap=si_cmap)
    if config.get('point_labels',False):
        names = [fill(str(row.sample),18) + f'\nSI: {row.SI:.2f}' for row in usable.itertuples()]
        point_labels(ax,np.column_stack((sx,sy)),names,fontsize=8,fit=True)
    if area is not None:
        boundaries.draw_boundary(ax,area)
    if config.get('show_colorbar',True):
        bar = aligned_colorbar(ax,filled,'Kriging prediction variance (SI²)' if variance else 'Saturation index (SI)',
                         config.get('colorbar_orientation','vertical'),config.get('map_layout'))
        if grid is not None and np.nanmin(visible) == np.nanmax(visible):
            bar.set_ticks([float(np.nanmin(visible))])
    title = 'Kriging prediction variance (SI²)' if variance else VIEWS[config['view']]
    ax.set(xlabel=xlabel,ylabel=ylabel,aspect='equal',title=f'{mineral} · {title}')
    if grid is not None:
        padding = .07 if config.get('point_labels',False) else .025
        xpad,ypad = np.ptp(gx)*padding,np.ptp(gy)*padding
        ax.set_xlim(np.min(gx)-xpad,np.max(gx)+xpad)
        ax.set_ylim(np.min(gy)-ypad,np.max(gy)+ypad)
    else:
        ax.margins(.07)
        ax.autoscale_view()
    ax.set_autoscale_on(False)
    ax.figure._aquaprov_boundary_crs = display_crs
    cartography = decorate_map(ax,display_crs,show_grid=config.get('show_grid',True),grid_spacing=config.get('grid_spacing',0.),
                 north_arrow=config.get('north_arrow',False),north_reference=config.get('north_reference','grid'),
                 layout=config.get('map_layout'))
    result.metadata['map'] = dict(projection,mineral=mineral,analysis_crs=crs,display_crs=display_crs,
                                 surface='variance' if variance else 'si',cartography=cartography)


@close_on_error
def plot(frame, config, *, calculated=None):
    config = deepcopy(config)
    view = config.setdefault('view','bar')
    if view not in VIEWS:
        raise ValueError('Choose a supported mineral saturation view.')
    result = deepcopy(calculated) if calculated is not None else calculate(frame,config)
    records = result.records
    minerals = list(dict.fromkeys(records.mineral))
    layers, heatmap = [], None
    with plt.rc_context(STYLE):
        fig,ax = plt.subplots(figsize=(max(8,min(18, len(minerals)*.9)),6.2),layout='constrained')
        if view in SPATIAL_VIEWS:
            _spatial(ax,frame,result,config,layers)
        elif view in ('bar','heatmap'):
            matrix,data = _matrix(records,config)
            count = len(matrix)
            if count > (60 if view=='bar' else 200):
                raise ValueError('Select fewer sample events for a readable figure (bar: 60; heatmap: 200). All data remain available in the source table.')
            result.tables['sample_comparison'] = matrix.reset_index()
            if view == 'bar':
                if count * len(minerals) > 300:
                    raise ValueError('Filter the bar comparison to at most 300 sample/mineral observations.')
                width = .8 / len(minerals)
                fig.set_figwidth(max(fig.get_figwidth(),min(24,3+count*.4)))
                mineral_keys = []
                for j,mineral in enumerate(minerals):
                    values = matrix[mineral].to_numpy()
                    colors = [CLASS_COLORS[CLASSES.index(c)] if c in CLASSES else '#dddddd' for c in classify(values)]
                    bars = ax.bar(np.arange(count)-.4+width*(j+.5),values,width*.92,color=colors,
                                  hatch=('', '//', '..', 'xx', '\\', 'oo', '--', '++', '**')[j%9],
                                  edgecolor='#26384a',linewidth=.35,label=mineral)
                    mineral_keys.append(Patch(facecolor='white',edgecolor='#26384a',
                                              hatch=bars[0].get_hatch(),label=mineral))
                    for i,bar in enumerate(bars):
                        layers.append((bar,[f'{matrix.index[i]} | {mineral}\nSI: {values[i]:.6g}\n{classify([values[i]])[0]}']))
                rotation = 90 if count > 12 else 60
                ax.set_xticks(np.arange(count),matrix.index,rotation=rotation,
                              ha='right',rotation_mode='anchor')
                if rotation == 90:
                    TickLabelLayout(ax,'x')
                ax.legend(handles=mineral_keys)
                # Exact zeros remain visible on the reference line.
                for j,mineral in enumerate(minerals):
                    values = matrix[mineral].to_numpy()
                    at_zero = np.flatnonzero(values == 0)
                    ax.scatter(at_zero-.4+width*(j+.5),np.zeros(len(at_zero)),marker='_',color=CLASS_COLORS[1],zorder=5)
                ax.set(ylabel='Saturation index (SI)',xlabel='Sample / sampling event')
            else:
                fig.set_size_inches(max(8,min(18,len(minerals)*.95)),max(5,min(24,count*.28+2)))
                cmap = plt.get_cmap(config.get('cmap','RdBu_r')).copy()
                cmap.set_bad('#e5e7eb')
                values = matrix.to_numpy()
                artist = ax.imshow(np.ma.masked_invalid(values),aspect='auto',cmap=cmap,norm=_norm(values,config))
                fig.colorbar(artist,ax=ax,label='Saturation index (SI)',extend='both')
                from ..plot_legends import scale_legend, add_legend_entries
                scale_legend(ax, artist, 'Saturation index (SI)')
                if not np.isfinite(values).all():
                    add_legend_entries(ax, [Patch(facecolor='#e5e7eb', label='Unassessed (missing SI)')])
                ax.set_xticks(range(len(minerals)),minerals,rotation=45,ha='right')
                ax.set_yticks(range(count),matrix.index)
                notes = np.empty(values.shape,dtype=object)
                for y in range(count):
                    for x,mineral in enumerate(minerals):
                        si = values[y,x]
                        text = f'{si:.2f}' if np.isfinite(si) else 'NA'
                        notes[y,x] = f'{matrix.index[y]} | {mineral}\nSI: {si:.6g}\n{classify([si])[0]}'
                        if config.get('annotate',True) and values.size <= 300:
                            ax.text(x,y,text,ha='center',va='center',fontsize=8,
                                    color='white' if np.isfinite(si) and abs(si) > artist.norm.vmax*.65 else '#202a35')
                heatmap = (ax,notes)
                CellTextLayout(ax,count,len(minerals))
                ax.set(ylabel='Sample / sampling event',xlabel='Mineral')
                result.warnings.append('Grey heatmap cells are unassessed, not SI = 0.')
        elif view in ('box','violin'):
            for i,mineral in enumerate(minerals,1):
                group = records[(records.mineral == mineral) & records.SI.notna()]
                values = group.SI.to_numpy()
                if len(values):
                    if view=='box':
                        edge = dict(color=config.get('box_edge_color','#243447'),linewidth=config.get('box_edge_width',.6))
                        artist = ax.boxplot([values],positions=[i],widths=config.get('box_width',.55),patch_artist=True,
                            showfliers=config.get('show_fliers',True) and not config.get('distribution_points',True),
                            boxprops=edge.copy(),whiskerprops=edge.copy(),capprops=edge.copy(),
                            flierprops=dict(marker='.',markersize=3,markeredgecolor=config.get('box_edge_color','#243447')),
                            medianprops=dict(color=config.get('median_color','#1f2937'),linewidth=config.get('median_width',1.5)))
                        artist['boxes'][0].set(facecolor=config.get('color', '#8ecae6'),alpha=config.get('alpha',.7),gid='aquaprov-si-box')
                        for median in artist['medians']:
                            median.set_gid('aquaprov-si-median')
                        from ..plot_legends import box_legend
                        box_legend(ax, artist)
                    elif len(values)>=3 and np.ptp(values)>0:
                        artist = ax.violinplot([values],positions=[i],widths=.8,showmedians=True,showextrema=True)
                        for body in artist['bodies']:
                            body.set(facecolor='#168aad',alpha=.4)
                        from ..plot_legends import violin_legend
                        violin_legend(ax, artist)
                    else:
                        result.warnings.append(f'{mineral}: violin density requires at least three nonconstant values; displaying observed points only.')
                    # Deterministic display jitter; numerical values are unaltered.
                    if config.get('distribution_points', True):
                        jitter = np.random.default_rng(1729+i).uniform(-.16,.16,len(values))
                        artist = ax.scatter(i+jitter,values,s=config.get('sample_size',19),alpha=config.get('alpha',.75),marker=config.get('marker','o'),
                            edgecolors=config.get('point_edge_color','white'),linewidths=config.get('point_edge_width',.3),
                            c=[CLASS_COLORS[CLASSES.index(c)] for c in group.classification] if config.get('class_colors', True) else config.get('color', '#087f8c'),zorder=4,label='Observed SI values')
                        layers.append((artist,[_label(r) for r in group.itertuples()]))
            ax.set_xticks(range(1,len(minerals)+1),[f'{m}\n(n = {records.loc[records.mineral==m,"SI"].count()})' if config.get('show_counts',True) else m for m in minerals],rotation=0,ha='center')
            ax.set(xlim=(.4,len(minerals)+.6),ylabel='Saturation index (SI)',xlabel='Mineral')
        elif view == 'distribution':
            summary = result.tables['mineral_statistics'].set_index('mineral').reindex(minerals)
            percent = config.get('percent',True)
            bottom = np.zeros(len(minerals))
            for label,color in zip(CLASSES,CLASS_COLORS):
                values = summary[label + ' (%)'].fillna(0).to_numpy() if percent else summary[label].to_numpy()
                bars = ax.bar(minerals,values,bottom=bottom,color=color,label=label,edgecolor='white')
                for i,bar in enumerate(bars):
                    layers.append((bar,[f'{minerals[i]} | {label}\n{int(summary.iloc[i][label])} of {int(summary.iloc[i].n_assessed)} assessed observations']))
                bottom += values
            ax.legend()
            ax.tick_params(axis='x',labelrotation=35)
            ax.set(ylabel='Assessed observations (%)' if percent else 'Number of assessed observations',xlabel='Mineral')
            if percent:
                ax.set_ylim(0,105)
            else:
                from matplotlib.ticker import MaxNLocator
                ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        elif view == 'scatter':
            yname = config.get('mineral') or minerals[0]
            if config.get('scatter_kind','mineral') == 'mineral':
                matrix,_ = _matrix(records,config)
                xname = config.get('scatter_x_mineral')
                if xname not in matrix or yname not in matrix or xname==yname:
                    raise ValueError('Choose two distinct minerals included in the mineral selection.')
                table = matrix[[xname,yname]].reset_index().rename(columns={xname:'x',yname:'y','observation':'sample'})
                xlabel = xname + ' SI'
                from ..chart_annotations import reference_line
                reference_line(ax,config.get('reference',{}),direction='vertical')
            else:
                xname = config.get('scatter_column')
                if xname not in frame:
                    raise ValueError('Choose a numeric groundwater measurement for the scatter X axis.')
                subset = records[records.mineral==yname]
                measurement = numeric(frame[xname],xname).to_numpy()
                table = pd.DataFrame(dict(sample=subset['sample'].to_numpy(), source_row=subset.source_row.to_numpy(),
                    x=measurement[subset.source_row.to_numpy()-1], y=subset.SI.to_numpy()))
                xlabel = xname + ' (source units)'
            table['plotted'] = np.isfinite(table[['x','y']]).all(axis=1)
            result.tables['scatter_observations'] = table
            usable = table[table.plotted]
            if usable.empty:
                raise ValueError('No paired finite values for the selected scatter variables.')
            artist = ax.scatter(usable.x,usable.y,c=[CLASS_COLORS[CLASSES.index(c)] for c in classify(usable.y)] if config.get('class_colors',True) else config.get('color','#087f8c'),
                                s=config.get('sample_size',40),marker=config.get('marker','o'),alpha=config.get('alpha',1),
                                edgecolors=config.get('point_edge_color','white'),linewidths=config.get('point_edge_width',.5),label='Paired SI observations')
            layers.append((artist,[f'{r.sample}\n{xlabel}: {r.x:.6g}\n{yname} SI: {r.y:.6g}' for r in usable.itertuples()]))
            result.metadata['scatter'] = dict(x=xlabel,y=yname+' SI',n_pairs=len(usable),n_excluded=int((~table.plotted).sum()))
            if len(usable)>=3 and usable.x.nunique()>1 and usable.y.nunique()>1:
                result.metadata['scatter']['pearson_r_descriptive'] = float(usable[['x','y']].corr().iloc[0,1])
            ax.set(xlabel=xlabel,ylabel=yname+' SI')
        if view not in SPATIAL_VIEWS:
            if view not in ('heatmap','distribution'):
                from ..chart_annotations import reference_line
                reference_line(ax,config.get('reference',dict(color='#515e6b',width=.9,linestyle='--')))
                ax.grid(axis='y',alpha=.2)
            ax.set_title(VIEWS[view])
            if view in ('heatmap','box','violin','distribution'):
                TickLabelLayout(ax,'x')
            if view in ('bar','box','violin','scatter') and config.get('class_colors',True):
                class_keys = [Patch(facecolor=color,label=label) for color,label in
                              zip(CLASS_COLORS,('SI < 0','SI = 0','SI > 0'))]
                ax.legend(handles=(mineral_keys if view=='bar' else [])+class_keys)
        if view in SPATIAL_VIEWS and config.get('map_legend') == 'inside':
            from ..plot_legends import prepare_figure_legends
            prepare_figure_legends(fig)
        else:
            outside_legend(fig,max_columns=3)
        fig._aquaprov_si_inspector = SIInspector(fig,layers,heatmap)
    # Database text is already an exported table; do not duplicate it in JSON config.
    recorded = {k:v for k,v in config.items() if k!='database_snapshot'}
    if config.get('database_snapshot'):
        recorded['database_snapshot'] = {k:v for k,v in config['database_snapshot'].items() if k!='text'}
    result.metadata.update(config=recorded,view=view,source_provenance=deepcopy(frame.attrs.get('aquaprov',{})))
    return PlotResult(fig,result.tables,result.metadata,result.warnings)
