"""Cartographic views of a fitted assessment model and its conditional uncertainty."""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, Normalize
from matplotlib.patches import PathPatch
from scipy.stats import norm as gaussian

from ..boundaries import polygon_path, draw_boundary
from ..modules.maps.classification import display_classes, class_table
from ..modules.maps.cartography import aligned_colorbar, decorate_map


def fitted_map(grid, config, unit, tables, metadata):
    output = config.get('map_output', 'both')
    panels = ['prediction', 'uncertainty'] if output == 'both' else [output]
    if any(p not in ('prediction', 'uncertainty') for p in panels):
        raise ValueError('Choose prediction, conditional uncertainty or both.')
    figure, axes = plt.subplots(1, len(panels), figsize=(12 if len(panels)==2 else 9, 6),
                                layout='constrained', squeeze=False)
    figure._aquaprov_boundary_crs = grid.metadata['analysis_crs']
    drawing = config.get('surface_drawing', 'default')
    if drawing == 'default':
        drawing = 'raster'
    metadata['spatial_map'] = dict(grid.metadata, surface_drawing=drawing)
    for ax, panel in zip(axes[0], panels):
        settings = dict(config)
        if panel == 'prediction':
            visible, rendered = grid.values, grid.render_values
            title, label, cmap = 'Fitted ordinary kriging', f"{config['column']} ({unit})", 'viridis'
        else:
            visible, rendered = np.sqrt(grid.variance), np.sqrt(grid.render_variance)
            title, label, cmap = 'Conditional model uncertainty', f'Conditional prediction SD ({unit})', 'magma'
            if config.get('threshold') is not None:
                with np.errstate(divide='ignore', invalid='ignore'):
                    visible = gaussian.sf((config['threshold']-grid.values)/visible)
                    rendered = gaussian.sf((config['threshold']-grid.render_values)/rendered)
                visible = np.where(grid.variance == 0, grid.values > config['threshold'], visible)
                rendered = np.where(grid.render_variance == 0, grid.render_values > config['threshold'], rendered)
                label = 'Conditional P(value > threshold)'
            if len(panels) == 2 and config.get('classification') == 'custom':
                # Concentration thresholds cannot also be uncertainty thresholds.
                settings['classification'] = 'automatic'
        lo, hi = float(np.nanmin(visible)), float(np.nanmax(visible))
        if lo == hi:
            lo, hi = lo-max(abs(lo)*1e-6,1e-9), hi+max(abs(hi)*1e-6,1e-9)
        if panel == 'uncertainty' and config.get('threshold') is not None:
            lo, hi = 0., 1.
        bounds, classes = display_classes(visible, settings, np.linspace(lo,hi,config.get('levels',12)+1))
        tables[panel+'_class_boundaries'] = class_table(classes)
        metadata['spatial_map'][panel+'_classification'] = classes
        norm = Normalize(lo,hi) if classes['method']=='automatic' else BoundaryNorm(bounds,256)
        if drawing == 'contours':
            filled = ax.contourf(grid.x,grid.y,rendered,levels=bounds,cmap=cmap,norm=norm,extend='both',alpha=config.get('opacity',.8))
        elif drawing == 'raster':
            filled = ax.pcolormesh(grid.x,grid.y,rendered,shading='nearest',cmap=cmap,norm=norm,rasterized=True,alpha=config.get('opacity',.8))
        else:
            raise ValueError('Choose filled contours or classified raster cells.')
        patch = PathPatch(polygon_path(grid.clip_geometry),transform=ax.transData)
        filled.set_clip_path(patch)
        from ..plot_legends import scale_legend, contour_legend
        scale_legend(ax,filled,'Kriging prediction' if panel=='prediction' else label)
        if config.get('contour_lines',False) and np.nanmax(visible)>np.nanmin(visible):
            lines = ax.contour(grid.x,grid.y,rendered,levels=bounds,
                colors=config.get('line_color','#214b60'),linewidths=config.get('line_width',.5))
            lines.set_clip_path(patch)
            contour_legend(ax,lines)
            if config.get('contour_labels',False):
                labels = ax.clabel(lines,fontsize=7,inline=True)
                from ..plot_layout import ContourLabelLayout
                ContourLabelLayout(ax,labels)
                for text in labels:
                    text.set_clip_path(patch); text.set_clip_on(True)
        if config.get('show_samples',True):
            ax.scatter(*grid.samples.T,s=config.get('chart_size',18),marker=config.get('chart_marker','o'),
                color=config.get('chart_color','#087f8c'),edgecolors='#193c51',linewidths=.5,label='Sample locations',zorder=5)
        if grid.boundary_geometry is not None:
            draw_boundary(ax,grid.boundary_geometry)
        ax.set(xlabel=grid.metadata['xlabel'],ylabel=grid.metadata['ylabel'],aspect='equal',title=title)
        xpad,ypad=np.ptp(grid.x)*.025,np.ptp(grid.y)*.025
        ax.set_xlim(grid.x.min()-xpad,grid.x.max()+xpad)
        ax.set_ylim(grid.y.min()-ypad,grid.y.max()+ypad)
        ax.set_autoscale_on(False)
        if config.get('show_colorbar',True):
            bar = aligned_colorbar(ax,filled,label,config.get('colorbar_orientation','horizontal'),
                config.get('map_layout'),config.get('colorbar_options'))
            if np.nanmin(visible)==np.nanmax(visible):
                bar.set_ticks([float(np.nanmin(visible))])
        metadata['spatial_map'][panel+'_cartography'] = decorate_map(ax,grid.metadata['analysis_crs'],
            show_grid=config.get('show_grid',False),grid_spacing=config.get('grid_spacing',0),
            north_arrow=config.get('north_arrow',False),north_reference=config.get('north_reference','true'),
            layout=config.get('map_layout'))
    return figure
