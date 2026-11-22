"""Publication figures using AquaProv's numerical, GIS and figure infrastructure."""
from copy import deepcopy

import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap, Normalize
from matplotlib.patches import Patch, PathPatch
import numpy as np
import pandas as pd

from .._publication import PlotResult, STYLE, close_on_error
from ..modules.maps.interpolation import interpolate, planar_coordinates
from ..modules.maps.projections import analysis_coordinates
from ..modules.maps.classification import display_classes, class_table
from ..modules.maps.cartography import aligned_colorbar, decorate_map
from ..boundaries import polygon_path, draw_boundary, local_crs, geometry_in_crs, point_mask, transform_xy, make_boundary
from .common import classify
from .engine import calculate, VIEWS, SPATIAL_VIEWS, SEASONAL_VIEWS, figure_title
from .appearance import label_samples, label_options, sample_appearance, uses_scale_colors
from ..plot_layout import outside_legend
from ..figure_presentation import prepare_figure_title


class PointInspector:
    """A canvas-independent hover inspector (Qt reuses the figure callbacks)."""
    def __init__(self, figure, layers):
        self.figure, self.layers = figure, layers
        self.annotations = {}
        for artist, labels in layers:
            ax = artist.axes
            if ax not in self.annotations:
                text = ax.annotate('', (0,0), xytext=(9,9), textcoords='offset points', fontsize=8,
                                   bbox=dict(boxstyle='round', fc='white', alpha=.95), zorder=30)
                text.set_visible(False)
                text.set_in_layout(False)
                self.annotations[ax] = text
        self.cid = figure.canvas.mpl_connect('motion_notify_event', self.move)

    def move(self, event):
        changed = False
        for ax, annotation in self.annotations.items():
            visible = False
            if event.inaxes is ax:
                for artist, labels in self.layers:
                    if artist.axes is not ax:
                        continue
                    hit, info = artist.contains(event)
                    if hit and len(info.get('ind', [])):
                        i = info['ind'][0]
                        annotation.xy = (event.xdata, event.ydata)
                        annotation.set_text(labels[i])
                        visible = True
                        break
            changed |= annotation.get_visible() != visible or visible
            annotation.set_visible(visible)
        if changed:
            self.figure.canvas.draw_idle()


def _coordinates(frame, result, config):
    x, y = config.get('x'), config.get('y')
    if x not in frame or y not in frame or x == y:
        raise ValueError('Choose distinct X and Y source coordinate columns.')
    coordinates = frame[[x,y]].apply(pd.to_numeric, errors='coerce').to_numpy(dtype=float)
    records = result.samples.copy()
    row = records.source_row.to_numpy(dtype=int)-1
    records['x'], records['y'] = coordinates[row].T
    threshold_column = config.get('point_settings', {}).get('threshold_column', '(none)')
    if threshold_column != '(none)':
        if threshold_column not in frame:
            raise ValueError('Highlight column is no longer present in the dataset.')
        records[threshold_column] = frame[threshold_column].to_numpy()[row]
    if 'ccme_membership' in result.tables:
        # A site cannot be assigned the coordinate of its first visit if it moved.
        for record, members in result.tables['ccme_membership'].groupby('record', sort=False):
            xy = coordinates[members.source_row.to_numpy(dtype=int)-1]
            if not np.isfinite(xy).all() or not np.allclose(xy, xy[0], rtol=0, atol=1e-8):
                raise ValueError(f'CCME site/period record {record} has missing or changing coordinates. Use stable monitoring-site identifiers.')
    records['spatial_status'] = np.where(~np.isfinite(records[result.metadata['index']]), 'Unassessed index',
                               np.where(np.isfinite(records[['x','y']]).all(axis=1), 'Included', 'Missing coordinates'))
    return records


def _grid(data, index, spatial, projection, config):
    options = {k:spatial[k] for k in ('method','resolution','model','range_','sill','nugget','power','neighbors','cell_size') if k in spatial}
    return interpolate(data, 'map_x', 'map_y', index, coordinates='projected',
                       source_crs=projection, boundary=config.get('boundary'),
                       extrapolate=config.get('extrapolate', False),
                       samples_inside_boundary=config.get('samples_inside_boundary', False), **options)


def _grid_table(grid, scheme):
    table = pd.DataFrame({'x':grid.x.ravel(), 'y':grid.y.ravel(), 'prediction':grid.values.ravel(),
                          'classification':classify(grid.values.ravel(), scheme),
                          'inside_sample_hull':grid.inside_sample_hull.ravel(), 'inside_boundary':grid.inside_boundary.ravel()})
    table['extrapolated'] = table.prediction.notna() & ~table.inside_sample_hull
    if grid.metadata['method'] == 'ordinary kriging':
        table['variance'] = grid.variance.ravel()
    return table


def _map_axis(ax, data, index, scheme, config, grid, norm, crs, *, classification=False, title=None, layers=None):
    spatial = config.get('spatial', {})
    gx, gy = (grid.x, grid.y) if grid is not None else (None, None)
    sx, sy = data.map_x.to_numpy(), data.map_y.to_numpy()
    area = geometry_in_crs(config['boundary'], crs, declared_local_crs=crs) if config.get('boundary') else None
    clip = grid.clip_geometry if grid is not None else None
    display_crs = crs
    if config.get('basemap', 'plain') != 'plain':
        from shapely.ops import transform
        if crs == 'local':
            raise ValueError('A geographic basemap requires a declared source CRS.')
        if grid is not None:
            gx, gy = transform_xy(gx, gy, crs, 'EPSG:3857')
        sx, sy = transform_xy(sx, sy, crs, 'EPSG:3857')
        if clip is not None:
            clip = transform(lambda x,y,z=None: transform_xy(x,y,crs,'EPSG:3857'), clip)
        if area is not None:
            area = transform(lambda x,y,z=None: transform_xy(x,y,crs,'EPSG:3857'), area)
        display_crs = 'EPSG:3857'
        from ..basemaps import add_attribution
        add_attribution(ax, config['basemap'])
    cmap = config.get('cmap', 'viridis')
    if classification:
        cmap = ListedColormap(scheme['colors'])
        norm = BoundaryNorm(np.arange(-.5,5), 5)
    filled = None
    if grid is not None:
        z = grid.render_values
        patch = PathPatch(polygon_path(clip), transform=ax.transData) if clip is not None else None
        if classification:
            z = np.searchsorted(scheme['cuts'], z, side='left' if scheme['closed']=='upper' else 'right')
            # Never interpolate category codes between grid nodes.
            filled = ax.pcolormesh(gx,gy,z,shading='nearest',cmap=cmap,norm=norm)
            filled._aquaprov_fixed_cmap = True
        else:
            levels, classes = display_classes(config.get('_class_values', grid.values), config,
                np.linspace(norm.vmin, norm.vmax, config.get('levels', 12)+1))
            grid.metadata['display_classification'] = classes
            drawing = config.get('surface_drawing', 'default')
            if drawing == 'default':
                drawing = 'contours' if config['view'] == 'contour' else 'raster'
            grid.metadata['surface_drawing'] = drawing
            if classes['method'] != 'automatic':
                norm = BoundaryNorm(levels, 256)
            if drawing == 'contours':
                filled = ax.contourf(gx,gy,z,levels=levels,cmap=cmap,norm=norm,extend='both',alpha=config.get('opacity', .9))
            elif drawing == 'raster':
                filled = ax.pcolormesh(gx,gy,z,shading='nearest',cmap=cmap,norm=norm,alpha=config.get('opacity', .9),rasterized=True)
            else:
                raise ValueError('Choose filled contours or classified raster cells.')
            if (config.get('contour_lines', True) and
                    (config['view']=='contour' or config.get('surface_drawing','default')!='default') and
                    np.nanmax(grid.values) > np.nanmin(grid.values)):
                lines = ax.contour(gx,gy,z,levels=levels,colors=config.get('line_color', '#284453'),linewidths=config.get('line_width', .5))
                from ..plot_legends import contour_legend
                contour_legend(ax, lines)
                if patch:
                    lines.set_clip_path(patch)
                if config.get('contour_labels', True):
                    labels = ax.clabel(lines,fontsize=8,inline=True)
                    from ..plot_layout import ContourLabelLayout
                    ContourLabelLayout(ax, labels)
                    if patch:
                        for label in labels:
                            label.set_clip_path(patch); label.set_clip_on(True)
        if patch:
            filled.set_clip_path(patch)
    if config.get('show_samples', True):
        colors = np.searchsorted(scheme['cuts'], data[index], side='left' if scheme['closed']=='upper' else 'right') if classification else data[index]
        if config['view'] == 'samples' and config.get('point_settings'):
            from ..observation_options import draw_points
            point_settings = dict(config['point_settings'])
            point_settings['geographic'] = display_crs == 'EPSG:4326'
            if config.get('color_min') is not None and not point_settings.get('limits'):
                point_settings['limits'] = f'{config["color_min"]}, {config["color_max"]}'
            points = draw_points(ax, data, sx, sy, data[index] if uses_scale_colors(config) else None,
                settings=point_settings, size=config.get('sample_size', 23), marker=config.get('marker', 'o'),
                color=config.get('color', '#087f8c'), alpha=config.get('sample_alpha',1), cmap=cmap)
        else:
            points = ax.scatter(sx,sy,zorder=5,**sample_appearance(config,colors,cmap,norm))
        points.set_gid('aquaprov-index-samples')
        points.set_label('Samples')
        if classification:
            points._aquaprov_fixed_cmap = True
        if layers is not None:
            layers.append((points, [f'{r.sample}\n{index}: {getattr(r,index):.4g}\n{r.classification}' for r in data.itertuples()]))
        if config.get('point_labels', config['view']=='samples'):
            label_samples(ax, np.column_stack((sx, sy)), data,index,config)
        if filled is None and uses_scale_colors(config):
            filled = points
    if filled is not None and grid is not None and not classification:
        from ..plot_legends import scale_legend
        scale_legend(ax, filled, index + ' interpolated values')
    if area is not None:
        draw_boundary(ax,area)
    if classification:
        ax.legend(handles=[Patch(facecolor=c,label=l) for c,l in zip(scheme['colors'],scheme['labels'])],
                  loc='upper center',bbox_to_anchor=(.5,-.14),ncols=3,fontsize=8)
    elif config.get('show_colorbar', True) and filled is not None:
        cb = aligned_colorbar(ax,filled,index,config.get('colorbar_orientation','vertical'),config.get('map_layout'),config.get('colorbar_options'))
        if config['view'] == 'samples':
            from ..observation_options import configure_colorbar
            configure_colorbar(cb, config.get('point_settings', {}))
    ax.set(title=title or f'{index} · {VIEWS[config["view"]]}',xlabel='Easting / X (distance units)',ylabel='Northing / Y (distance units)',aspect='equal')
    if display_crs == 'EPSG:3857':
        ax.set(xlabel='Web Mercator easting (m)',ylabel='Web Mercator northing (m)')
    elif display_crs == 'EPSG:4326':
        ax.set(xlabel='Longitude (°E)', ylabel='Latitude (°N)', aspect=1/np.cos(np.deg2rad(np.mean(sy))))
    if grid is not None:
        xpad,ypad=np.ptp(gx)*.025,np.ptp(gy)*.025
        ax.set_xlim(np.nanmin(gx)-xpad,np.nanmax(gx)+xpad);ax.set_ylim(np.nanmin(gy)-ypad,np.nanmax(gy)+ypad)
    else:
        xpad,ypad=max(np.ptp(sx)*.08,1e-6),max(np.ptp(sy)*.08,1e-6)
        ax.set_xlim(np.min(sx)-xpad,np.max(sx)+xpad);ax.set_ylim(np.min(sy)-ypad,np.max(sy)+ypad)
    ax.set_autoscale_on(False)
    decorate_map(ax,display_crs,show_grid=config.get('show_grid',True),grid_spacing=config.get('grid_spacing',0.),
                 north_arrow=config.get('north_arrow',False),north_reference=config.get('north_reference','grid'),
                 layout=config.get('map_layout'))
    for artist in ax.artists:
        if getattr(artist,'_aquaprov_draggable',False):
            # Measure cartographic symbols before positioning sample labels.
            artist.set_zorder(2.4)
    return ax


def _box(ax, groups, labels, index, color):
    artists = ax.boxplot(groups,tick_labels=labels,patch_artist=True,showfliers=True,
                         medianprops={'color':'#1f2937','linewidth':1.4})
    for box in artists['boxes']:
        box.set(facecolor=color,alpha=.7)
    from ..plot_legends import box_legend
    box_legend(ax, artists)
    ax.set(ylabel=index)
    ax.grid(axis='y',alpha=.2)


@close_on_error
def plot(frame, config):
    config = deepcopy(config)
    view, index = config.get('view','histogram'), config.get('index','WQI')
    if view not in VIEWS:
        raise ValueError('Choose a supported water-quality view.')
    label_options(config)
    uses_scale_colors(config)
    results = {name:calculate(frame,config,name) for name in (('WQI','DWQI') if view in ('comparison','index_scatter') else (index,))}
    primary = results[index]
    tables, notes, metadata = {}, [], {}
    for name,result in results.items():
        tables.update({f'{name}_{k}':v.copy() for k,v in result.tables.items()})
        notes.extend(result.warnings)
        metadata[name] = result.metadata
    records = primary.samples
    valid = records[np.isfinite(records[index])].copy()
    if valid.empty and view != 'compliance':
        raise ValueError('No complete index values are available. Review selected parameters, missing measurements and CCME sampling requirements.')
    seasons = config.get('seasons', [])
    if view in SEASONAL_VIEWS:
        if len(seasons) != 2 or len(set(seasons)) != 2 or not config.get('season_column'):
            raise ValueError('Select two distinct seasons (for example pre-monsoon and post-monsoon).')
        if config.get('filter_season') is not None:
            raise ValueError('Choose all seasons before generating a seasonal comparison.')
        if any(not valid.season.astype(str).eq(str(s)).any() for s in seasons):
            raise ValueError('Both selected seasons must contain assessable index values.')
    with plt.rc_context(STYLE):
        if view in SPATIAL_VIEWS:
            panels, all_xy, crs = [], [], config.get('source_crs') or 'local'
            for name,result in results.items():
                spatial_records = _coordinates(frame,result,config)
                tables[name+'_spatial_records'] = spatial_records
                usable = spatial_records[spatial_records.spatial_status=='Included'].copy()
                if usable.empty:
                    raise ValueError(f'{name}: no assessable indices with coordinates.')
                if view == 'seasonal_maps':
                    usable = usable[usable.season.astype(str).isin([str(s) for s in seasons])]
                all_xy.append(usable[['x','y']].to_numpy())
                if view == 'seasonal_maps':
                    panels.extend((name,str(s),usable[usable.season.astype(str)==str(s)].copy(),result) for s in seasons)
                else:
                    panels.append((name,name,usable,result))
            merged = np.vstack(all_xy)
            geographic_samples = (view == 'samples' and config.get('point_settings',{}).get('geographic')
                                  and config.get('basemap','plain') == 'plain')
            if geographic_samples:
                if config.get('coordinates') != 'wgs84':
                    raise ValueError('Longitude / latitude display requires WGS84 coordinates.')
                from ..locations import project_coordinates
                project_coordinates(merged[:,0], merged[:,1], 'wgs84', 0, 'N')
                converted, xlabel, ylabel, origin = merged, 'Longitude (°E)', 'Latitude (°N)', None
                crs = 'EPSG:4326'
            else:
                converted,xlabel,ylabel,projection_info = analysis_coordinates(merged,config.get('coordinates'),
                    boundary=config.get('boundary'),source_crs=config.get('source_crs'),target_crs=config.get('target_crs'))
                crs = projection_info['analysis_crs']
                origin = projection_info if config.get('coordinates') == 'wgs84' else None
                metadata['coordinate_conversion'] = projection_info
            if config.get('coordinates') == 'wgs84' and not geographic_samples:
                if config.get('source_crs') not in (None,'local','EPSG:4326'):
                    raise ValueError('WGS84 distances conflict with the declared source CRS.')
                crs = local_crs(origin)
                notes.append('Distances use a common local equirectangular metre approximation for all panels; use an appropriate projected CRS for precise regional mapping.')
            elif crs == 'EPSG:4326' and not geographic_samples:
                raise ValueError('Longitude/latitude requires the WGS84 distance setting.')
            if config.get('boundary'):
                original_boundary=deepcopy(config['boundary'])
                if origin:
                    geographic=geometry_in_crs(original_boundary,'EPSG:4326',declared_local_crs='EPSG:4326')
                    xmin,ymin,xmax,ymax=geographic.bounds
                    if (max(xmax,merged[:,0].max())-min(xmin,merged[:,0].min()) > 3 or
                            max(ymax,merged[:,1].max())-min(ymin,merged[:,1].min()) > 3):
                        raise ValueError('Study boundary exceeds the local 3-degree approximation. Use a suitable projected CRS.')
                area=geometry_in_crs(original_boundary,crs,declared_local_crs='EPSG:4326' if config.get('coordinates') in ('wgs84','auto_utm','wgs84_projected') else crs)
                config['boundary']=make_boundary(area,crs,name=original_boundary.get('name','Study area'))
                metadata['source_boundary']=original_boundary
            grids, map_data = [], []
            for name,title,data,result in panels:
                # Convert with one origin for all seasons/indices, not one projection per panel.
                if config.get('coordinates') in ('wgs84', 'auto_utm', 'wgs84_projected') and not geographic_samples:
                    from ..boundaries import transform_xy
                    data['map_x'],data['map_y'] = transform_xy(data.x.to_numpy(),data.y.to_numpy(),'EPSG:4326',crs)
                else:
                    data['map_x'],data['map_y'] = data.x,data.y
                if config.get('boundary') and config.get('samples_inside_boundary'):
                    area = geometry_in_crs(config['boundary'],crs,declared_local_crs='EPSG:4326' if origin else crs)
                    keep = point_mask(area,data[['map_x','map_y']].to_numpy())
                    tables[f'{name}_{len(map_data)+1}_excluded_boundary_samples'] = data.loc[~keep].copy()
                    data = data.loc[keep].copy()
                if data.empty:
                    raise ValueError('No samples remain inside the selected boundary.')
                grid = None if view=='samples' else _grid(data,name,config.get('spatial',{}),crs,config)
                if grid is not None:
                    tables[f'{name}_{len(grids)+1}_grid'] = _grid_table(grid,result.metadata['classification_scheme'])
                    grid.metadata.update(input_coordinates=config.get('coordinates'), coordinate_conversion=metadata.get('coordinate_conversion', {}))
                    metadata[f'{name}_{len(grids)+1}_spatial'] = grid.metadata
                grids.append(grid); map_data.append(data)
            metadata['coordinate_origin'] = origin
            metadata['analysis_crs'] = crs
            if view == 'surface':
                # A rotating Axes3D cannot use constrained layout reliably.
                # Match the dedicated 3D module's stable publication margins.
                figure = plt.figure(figsize=(9,7))
                figure.subplots_adjust(left=.10, right=.88, bottom=.12, top=.90)
                ax = figure.add_subplot(111,projection='3d')
                grid,data = grids[0],map_data[0]
                z = grid.values
                extent = np.r_[z[np.isfinite(z)], data[index].to_numpy()]
                norm = Normalize(float(extent.min()), float(extent.max()))
                if config.get('color_min') is not None:
                    if config['color_min'] >= config['color_max']:raise ValueError('Colour minimum must be less than maximum.')
                    norm = Normalize(config['color_min'],config['color_max'])
                artist = ax.plot_surface(grid.x,grid.y,z,cmap=config.get('cmap','viridis'),
                                         norm=norm,
                                         alpha=config.get('opacity',1.),linewidth=.2 if config.get('mesh_edges') else 0,
                                         antialiased=bool(config.get('mesh_edges')),
                                         edgecolor='#506070' if config.get('mesh_edges') else 'none',rcount=z.shape[0],ccount=z.shape[1])
                from ..plot_legends import scale_legend
                scale_legend(ax, artist, index + ' interpolated surface')
                if config.get('show_samples',True):
                    points=ax.scatter(data.map_x,data.map_y,data[index],depthshade=False,
                                      **sample_appearance(config,data[index],artist.get_cmap(),artist.norm))
                    points.set_gid('aquaprov-index-samples')
                    points.set_label('Samples')
                    if config.get('coordinate_guides',True):
                        from ..modules.three_d.guides import add_coordinate_guides
                        add_coordinate_guides(ax, data[['map_x','map_y',index]].to_numpy(),
                                              values=data[index].to_numpy(),cmap=artist.get_cmap(),norm=artist.norm)
                    if config.get('point_labels',False):
                        label_samples(ax, data[['map_x','map_y',index]].to_numpy(),data,index,config)
                ax.grid(config.get('show_grid',True))
                ax.set(xlabel=xlabel,ylabel=ylabel,zlabel=index,title=figure_title(index,view))
                ax.view_init(elev=config.get('elevation',30),azim=config.get('azimuth',-60),roll=config.get('roll',0))
                ax.set_proj_type(config.get('projection','persp'))
                ax.set_box_aspect((1,1,.65))
                from matplotlib.ticker import MaxNLocator
                for component in (ax.xaxis,ax.yaxis,ax.zaxis):
                    component.set_major_locator(MaxNLocator(nbins=5))
                if config.get('show_colorbar',True):
                    figure.colorbar(artist,ax=ax,shrink=.6,pad=.12,label=index)
            else:
                figure,axes = plt.subplots(1,len(panels),figsize=(8 if len(panels)==1 else 14,6),layout='constrained',squeeze=False)
                layers, map_axes = [], []
                norms = []
                for data,grid,(name,_,_,_) in zip(map_data,grids,panels):
                    values = grid.values if grid is not None else data[name].to_numpy()
                    lo,hi = float(np.nanmin(values)),float(np.nanmax(values))
                    if lo == hi: lo,hi = lo-max(abs(lo)*.01,.5),hi+max(abs(hi)*.01,.5)
                    norms.append(Normalize(lo,hi))
                if view == 'seasonal_maps':
                    norms = [Normalize(min(n.vmin for n in norms),max(n.vmax for n in norms))]*2
                if view == 'seasonal_maps':
                    config['_class_values'] = np.concatenate([g.values.ravel() for g in grids])
                for panel_number, (ax,(name,title,_,result),data,grid,norm) in enumerate(zip(axes[0],panels,map_data,grids,norms), 1):
                    if config.get('color_min') is not None:
                        norm = Normalize(config['color_min'],config['color_max'])
                        if norm.vmin >= norm.vmax:raise ValueError('Colour minimum must be less than maximum.')
                    map_axes.append(_map_axis(ax,data,name,result.metadata['classification_scheme'],config,grid,norm,crs,
                        classification=view=='classification',title=title if len(panels)>1 else None,layers=layers))
                    if grid is not None and 'display_classification' in grid.metadata:
                        tables[f'{name}_{panel_number}_class_boundaries'] = class_table(grid.metadata['display_classification'])
                if len(map_axes)>1:
                    figure.suptitle(figure_title(index,view),fontweight='semibold')
                    xlim = (min(a.get_xlim()[0] for a in map_axes),max(a.get_xlim()[1] for a in map_axes))
                    ylim = (min(a.get_ylim()[0] for a in map_axes),max(a.get_ylim()[1] for a in map_axes))
                    for ax in map_axes:ax.set_xlim(xlim);ax.set_ylim(ylim)
                figure._aquaprov_point_inspector = PointInspector(figure,layers)
                figure._aquaprov_index_map_axes = map_axes
            if view != 'samples':
                notes.append('Interpolation masks the sample convex hull unless explicit boundary extrapolation is enabled. Classes are assigned after interpolating continuous index values.')
                if config.get('spatial',{}).get('method','kriging')=='kriging':
                    notes.append('Ordinary kriging uses user-specified isotropic variogram parameters; validate them against held-out observations. Kriging may overshoot the observed index range; predictions are not clipped.')
                if config.get('extrapolate'):
                    notes.append('Boundary extrapolation is enabled. Exported grids flag cells outside the sample convex hull.')
            if len(panels)>1 and view=='comparison':
                notes.append('WQI and DWQI use independent numerical colour scales and classification schemes. Compare their reported methods before interpreting numerical differences.')
        else:
            figure,ax = plt.subplots(figsize=(9,6),layout='constrained')
            color = config.get('color','#007c83')
            scores = valid[index].to_numpy()
            if view == 'index_scatter':
                from ..observation_options import draw_points, threshold_mask
                a, b = results['WQI'].samples, results['DWQI'].samples
                paired = a[['source_row', 'sample', 'WQI']].merge(b[['source_row','DWQI']], on='source_row', validate='one_to_one')
                paired = paired.replace([np.inf, -np.inf], np.nan).dropna(subset=['WQI','DWQI'])
                if paired.empty:
                    raise ValueError('No paired WQI and DWQI observations are available.')
                source = frame.iloc[paired.source_row.to_numpy(int)-1].copy()
                points = draw_points(ax, source, paired.WQI, paired.DWQI,
                    settings={**config.get('point_settings', {}), 'geographic':False},
                    size=config.get('sample_size', 17), marker=config.get('marker','o'), color=color,
                    alpha=config.get('sample_alpha',1))
                paired['highlighted'] = threshold_mask(source, config.get('point_settings', {}))
                tables['index_comparison'] = paired
                lo = min(paired.WQI.min(), paired.DWQI.min()); hi = max(paired.WQI.max(), paired.DWQI.max())
                from ..chart_annotations import reference_line, plot_note
                reference = config.get('reference',dict(color='#85929d',width=.8,linestyle=':'))
                reference_line(ax,reference,direction='identity',limits=[lo,hi])
                ax.set(xlabel='WQI', ylabel='DWQI')
                plot_note(ax,reference.get('note',dict(x=.97,y=.06,ha='right',va='bottom')),'n = {n}',n=len(paired))
            elif view=='histogram':
                bins = config.get('bins', 'auto')
                count,edges,_ = ax.hist(scores,bins=bins,color=color,edgecolor='white',alpha=.85)
                ax.patches[0].set_label(index + ' frequency')
                tables['histogram'] = pd.DataFrame({'lower':edges[:-1],'upper':edges[1:],'count':count.astype(int)})
                ax.set(xlabel=index,ylabel='Number of samples / site-periods')
                from matplotlib.ticker import MaxNLocator
                ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            elif view=='box':
                _box(ax,[scores],[index],index,color)
            elif view=='violin':
                if len(scores)>1 and np.ptp(scores)>0:
                    parts = ax.violinplot([scores],showmedians=True,showextrema=True)
                    for body in parts['bodies']:body.set_facecolor(color);body.set_alpha(.65)
                    from ..plot_legends import violin_legend
                    violin_legend(ax, parts)
                else:
                    ax.scatter(np.ones(len(scores)),scores,color=color,label='Observed values')
                    notes.append('A density cannot be estimated for a singleton or constant sample; the violin view shows the observed value instead.')
                ax.set(xticks=[1],xticklabels=[index],ylabel=index)
            elif view in ('seasonal_box','seasonal_bars'):
                groups = [valid[valid.season.astype(str)==str(s)][index].to_numpy() for s in seasons]
                if view=='seasonal_box':
                    _box(ax,groups,seasons,index,color)
                else:
                    if not config.get('site_column'):
                        raise ValueError('Grouped seasonal bars require a sampling-site column.')
                    table = valid[valid.season.astype(str).isin([str(s) for s in seasons])].groupby(['sample','season'],sort=False)[index].agg(['mean','count','std']).reset_index()
                    tables['seasonal_site_statistics'] = table
                    sites = list(dict.fromkeys(table['sample']))
                    if len(sites)>100:
                        raise ValueError('Grouped bars support up to 100 sites; use a reviewed subset or seasonal box plots.')
                    x = np.arange(len(sites))
                    for j,season in enumerate(seasons):
                        values = table[table.season.astype(str)==str(season)].set_index('sample')['mean'].reindex(sites)
                        ax.bar(x+(j-.5)*.38,values.to_numpy(),.38,label=str(season),color=(color,'#e69f00')[j])
                    ax.set(xticks=x,xticklabels=sites,ylabel=f'Mean {index} per site and season')
                    ax.tick_params(axis='x',rotation=60);ax.legend()
                    for label in ax.get_xticklabels():
                        label.set_ha('right');label.set_rotation_mode('anchor')
                    figure.set_figwidth(max(9,min(24,3+.32*len(sites))))
                    notes.append('Seasonal bars show arithmetic means of available index records per site/season; missing combinations are gaps. Counts and SDs are exported; bars are descriptive, not paired significance tests.')
                tables['seasonal_summary'] = pd.DataFrame([dict(season=s,n=len(g),mean=np.mean(g),median=np.median(g),sd=np.std(g,ddof=1) if len(g)>1 else np.nan) for s,g in zip(seasons,groups)])
            elif view=='compliance':
                table = primary.tables['compliance']
                y = np.arange(len(table))
                ax.barh(y,table.meets_percent,color='#1a9850',label='Meets selected limits')
                ax.barh(y,table.exceeds_percent,left=table.meets_percent,color='#d73027',label='Outside selected limits')
                labels = [f'{r.parameter} (n={r.assessed}; missing={r.unassessed})' for r in table.itertuples()]
                ax.set(yticks=y,yticklabels=labels,xlim=(0,100),xlabel='Percentage of measured samples')
                ax.invert_yaxis();ax.legend(loc='upper center',bbox_to_anchor=(.5,-.12),ncols=2)
                figure.set_figheight(max(5,min(20,2+.32*len(table))))
            ax.set_title(figure_title(index,view))
            if view in ('box','violin'):
                # The heading and Y axis already identify this single index.
                ax.set_xticks([])
                q1,q3 = np.quantile(scores,[.25,.75]);iqr=q3-q1
                tables['distribution_summary'] = pd.DataFrame([dict(n=len(scores),minimum=scores.min(),q1=q1,median=np.median(scores),q3=q3,maximum=scores.max(),iqr=iqr)])
                tables['box_outliers'] = valid[(valid[index]<q1-1.5*iqr)|(valid[index]>q3+1.5*iqr)]
        if view != 'surface':
            # Reserve page space for keys instead of anchoring them below axes.
            if view in SPATIAL_VIEWS-{'classification'} and config.get('map_legend') == 'inside':
                from ..plot_legends import prepare_figure_legends
                prepare_figure_legends(figure)
            else:
                outside_legend(figure)
        prepare_figure_title(figure,figure_title(index,view))
        # The full method/edition/classification records accompany every result export.
        config.pop('_class_values', None)
        metadata.update(analysis=VIEWS[view],index=index,config=config)
        tables['calculation_report'] = pd.DataFrame([dict(index=n,methodology=r.metadata['methodology'],
            standard=r.metadata['standard'],limit_kind=r.metadata['limit_kind'],
            parameter_editions='; '.join(dict.fromkeys(p['edition'] for p in r.metadata['parameters'])),
            unverified_parameters=', '.join(p['name'] for p in r.metadata['parameters'] if p['verification']!='verified'),
            classification=r.metadata['classification_scheme']['name'],
            thresholds=str(r.metadata['classification_scheme']['cuts']),direction=r.metadata['classification_scheme']['direction']) for n,r in results.items()])
        return PlotResult(figure,tables,metadata,list(dict.fromkeys(notes)))
