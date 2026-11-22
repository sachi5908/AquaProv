"""Isotropic ordinary kriging and IDW on explicit planar distance coordinates."""
from dataclasses import dataclass
import warnings

import numpy as np
import pandas as pd
from scipy.linalg import LinAlgWarning, lu_factor, lu_solve
from scipy.spatial import Delaunay, distance, cKDTree
from ...core.progress import report_progress


def numeric_samples(frame, columns, minimum=3):
    if frame is None or any(column not in frame for column in columns):
        raise ValueError("Import a dataset and select each required numeric column.")
    if len(set(columns)) != len(columns):
        raise ValueError("Choose different coordinate and measurement columns.")
    values = frame[list(columns)].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError("Selected columns contain missing, non-numeric or infinite values. Clean these rows before interpolation.")
    if len(values) < minimum:
        raise ValueError(f"At least {minimum} complete samples are required.")
    return values.to_numpy(dtype=float)


def planar_coordinates(xy, coordinates):
    xy = np.asarray(xy, dtype=float)
    if coordinates == "projected":
        return xy.copy(), "X (source distance units)", "Y (source distance units)", {}
    if coordinates != "wgs84":
        raise ValueError("Choose a distance coordinate system for interpolation.")
    lon, lat = xy.T
    if (np.abs(lon) > 180).any() or (np.abs(lat) > 85).any():
        raise ValueError("Longitude/latitude must be valid WGS84 decimal degrees (latitude within ±85°).")
    if np.ptp(lon) > 3 or np.ptp(lat) > 3:
        raise ValueError("This area is too wide for the local metre approximation. Import coordinates in a suitable projected CRS.")
    lon0, lat0 = float(lon.mean()), float(lat.mean())
    radius = 6371008.8
    points = np.column_stack((radius * np.radians(lon - lon0) * np.cos(np.radians(lat0)),
                              radius * np.radians(lat - lat0)))
    return points, "Local east (m)", "Local north (m)", {"local_origin_lon": lon0, "local_origin_lat": lat0}


def validate_geometry(xy):
    if len(np.unique(xy, axis=0)) != len(xy):
        raise ValueError("Duplicate sample locations found. Resolve or deliberately aggregate co-located measurements first.")
    centered = xy - xy.mean(axis=0)
    if np.linalg.matrix_rank(centered) < 2:
        raise ValueError("A surface needs at least three non-collinear sample locations.")


def covariance(distances, model, range_, sill):
    ratio = distances / range_
    if model == "spherical":
        return sill * np.where(ratio < 1, 1 - 1.5 * ratio + 0.5 * ratio**3, 0)
    if model == "exponential":
        return sill * np.exp(-3 * ratio)
    raise ValueError("Choose a spherical or exponential variogram.")


def ordinary_kriging(xy, values, targets, *, model="spherical", range_=1000, sill=1, nugget=0):
    """Predict a new observation; variance includes the specified nugget.

    Sill is the structured (partial) sill. Exponential range is the practical
    range, where structured covariance is exp(-3) times the partial sill.
    No variogram fitting, anisotropy or trend removal is performed.
    """
    if not np.isfinite([range_, sill, nugget]).all() or range_ <= 0 or sill <= 0 or nugget < 0:
        raise ValueError("Range and partial sill must be positive; nugget must be non-negative.")
    xy, values, targets = np.asarray(xy, float), np.asarray(values, float), np.asarray(targets, float)
    count = len(xy)
    # Scale covariances to keep the Lagrange constraint well conditioned.
    scale = sill + nugget
    matrix = np.empty((count + 1, count + 1))
    matrix[:count, :count] = covariance(distance.cdist(xy, xy), model, range_, sill) / scale
    matrix[np.arange(count), np.arange(count)] += nugget / scale
    matrix[count, :count] = matrix[:count, count] = 1
    matrix[count, count] = 0
    with warnings.catch_warnings():
        warnings.simplefilter("error", LinAlgWarning)
        try:
            factor = lu_factor(matrix)
        except (LinAlgWarning, ValueError) as exc:
            raise ValueError("The kriging system is singular. Check duplicate locations and variogram parameters.") from exc
    predictions, variances = [], []
    batch_size = max(1, min(512, 1_000_000 // count))
    for start in range(0, len(targets), batch_size):
        cross = covariance(distance.cdist(xy, targets[start:start + batch_size]), model, range_, sill) / scale
        solution = lu_solve(factor, np.vstack((cross, np.ones(cross.shape[1]))))
        variance = scale * (1 - np.sum(solution[:count] * cross, axis=0) - solution[count])
        if not np.isfinite(solution).all() or (variance < -1e-7 * scale).any():
            raise ValueError("Numerically unstable kriging system. Review the range, sill and sampling geometry.")
        predictions.append(values @ solution[:count])
        variances.append(np.maximum(variance, 0))
        report_progress(100 * min(start + batch_size, len(targets)) / len(targets), 'Calculating kriging grid')
    return np.concatenate(predictions), np.concatenate(variances)


def idw(xy, values, targets, power=2, *, neighbors=None):
    """IDW with all points or the nearest k; include ties at the kth distance."""
    if not np.isfinite(power) or power <= 0:
        raise ValueError("IDW power must be positive.")
    xy, values, targets = np.asarray(xy, float), np.asarray(values, float), np.asarray(targets, float)
    if neighbors is not None and (isinstance(neighbors, bool)
            or not isinstance(neighbors, (int, np.integer)) or neighbors < 1):
        raise ValueError('IDW neighbours must be a positive integer, or None for all samples.')
    count = min(neighbors, len(xy)) if neighbors is not None else len(xy)
    tree = cKDTree(xy) if count < len(xy) else None
    results = []
    batch_size = max(1, min(512, 1_000_000 // max(count, 1)))
    for start in range(0, len(targets), batch_size):
        batch = targets[start:start + batch_size]
        if tree is not None:
            queried, indices = tree.query(batch, k=count+1)
            distances = queried[:, :count]
            selected = values[indices[:, :count]]
        else:
            distances = distance.cdist(batch, xy)
            selected = np.broadcast_to(values, distances.shape)
        nearest = np.argmin(distances, axis=1)
        exact = distances[np.arange(len(distances)), nearest] == 0
        # Normalize by each row's closest distance to avoid overflow at small units.
        safe = np.maximum(distances, np.finfo(float).tiny)
        weights = (safe.min(axis=1)[:, None] / safe) ** power
        prediction = ((weights * selected).sum(axis=1) if tree is not None else weights @ values) / weights.sum(axis=1)
        prediction[exact] = selected[np.flatnonzero(exact), nearest[exact]]
        if tree is not None:
            # Tied kth distances must not make predictions depend on row order.
            tied = np.flatnonzero((queried[:, count] == queried[:, count-1]) & ~exact)
            for row in tied:
                hits = tree.query_ball_point(batch[row], np.nextafter(queried[row, count-1], np.inf))
                ds = np.linalg.norm(xy[hits] - batch[row], axis=1)
                ws = (ds.min() / ds) ** power
                prediction[row] = ws @ values[hits] / ws.sum()
        results.append(prediction)
        report_progress(100 * min(start + batch_size, len(targets)) / len(targets), 'Calculating IDW grid')
    return np.concatenate(results)


@dataclass
class GridResult:
    x: object
    y: object
    values: object
    variance: object
    samples: object
    measurements: object
    metadata: dict
    boundary_geometry: object = None
    clip_geometry: object = None
    inside_boundary: object = None
    inside_sample_hull: object = None
    render_values: object = None
    render_variance: object = None


def interpolate(frame, x, y, value, *, coordinates, method="kriging", resolution=70,
                model="spherical", range_=1000, sill=1, nugget=0, power=2,
                boundary=None, source_crs=None, extrapolate=False, samples_inside_boundary=False,
                neighbors=None, cell_size=None, target_crs=None):
    source = numeric_samples(frame, [x, y, value])
    from ... import boundaries
    if source_crs is not None:
        source_crs = boundaries.source_crs(source_crs)
    geographic_input = coordinates in ('wgs84', 'auto_utm', 'wgs84_projected')
    if geographic_input and source_crs not in (None, 'local', 'EPSG:4326'):
        raise ValueError('The source coordinate system conflicts with WGS84 distance coordinates. '
                         'Choose longitude/latitude as the source CRS or use projected distance units.')
    if coordinates in ('auto_utm', 'wgs84_projected'):
        from .projections import project_wgs84
        if coordinates == 'wgs84_projected' and not target_crs:
            raise ValueError('Enter the projected analysis CRS, for example EPSG:32645.')
        xy, xlabel, ylabel, projection = project_wgs84(source[:, :2], boundary=boundary,
                            target_crs=target_crs if coordinates == 'wgs84_projected' else None)
        analysis_crs = projection['analysis_crs']
    else:
        xy, xlabel, ylabel, projection = planar_coordinates(source[:, :2], coordinates)
        analysis_crs = boundaries.local_crs(projection) if coordinates == 'wgs84' else (source_crs or 'local')
    if coordinates == 'projected' and source_crs == 'EPSG:4326':
        raise ValueError('Longitude/latitude requires the WGS84 distance option, not projected distance units.')
    if coordinates == 'projected' and source_crs not in (None, 'local'):
        from pyproj import CRS
        if not CRS.from_user_input(source_crs).is_projected:
            raise ValueError('Projected distance coordinates require a projected source CRS. Convert geographic coordinates first.')
    area = None
    n_input = len(source)
    excluded = []
    if boundary is not None:
        area = boundaries.geometry_in_crs(boundary, analysis_crs,
                    declared_local_crs='EPSG:4326' if geographic_input else source_crs)
        if coordinates == 'wgs84':
            geographic = boundaries.geometry_in_crs(boundary, 'EPSG:4326', declared_local_crs='EPSG:4326')
            xmin, ymin, xmax, ymax = geographic.bounds
            if max(xmax, source[:, 0].max())-min(xmin, source[:, 0].min()) > 3 or max(ymax, source[:, 1].max())-min(ymin, source[:, 1].min()) > 3:
                raise ValueError('Study area exceeds the local 3-degree distance approximation. Use an appropriate projected CRS.')
        if samples_inside_boundary:
            keep = boundaries.point_mask(area, xy)
            excluded = (np.flatnonzero(~keep)+1).tolist()
            source, xy = source[keep], xy[keep]
    elif extrapolate or samples_inside_boundary:
        raise ValueError('Select a study boundary before using boundary-specific interpolation options.')
    if len(xy) < 3:
        raise ValueError('At least three complete samples are required inside the selected study area.')
    validate_geometry(xy)
    bounds = area.bounds if area is not None else (xy[:, 0].min(), xy[:, 1].min(), xy[:, 0].max(), xy[:, 1].max())
    if cell_size is None:
        if isinstance(resolution, bool) or not isinstance(resolution, int) or not 20 <= resolution <= 1000:
            raise ValueError('Grid resolution must be between 20 and 1,000 cells per axis.')
        axes = (np.linspace(bounds[0], bounds[2], resolution), np.linspace(bounds[1], bounds[3], resolution))
        grid_spec = {'grid_mode': 'cells per axis', 'cell_size': None}
    else:
        if isinstance(cell_size, bool) or not np.isfinite(cell_size) or cell_size <= 0:
            raise ValueError('Grid cell size must be a positive distance in analysis-coordinate units.')
        dimensions = np.ceil(np.array([bounds[2]-bounds[0], bounds[3]-bounds[1]]) / cell_size) + 2
        if not np.isfinite(dimensions).all() or np.prod(dimensions) > 1000000:
            raise ValueError('This cell size exceeds the 1,000,000 grid-point limit. Increase cell size or reduce the study area.')
        # Cell centres with a one-cell support halo allow exact vector clipping.
        axes = tuple(bounds[i] + (np.arange(int(dimensions[i])) - .5) * cell_size for i in (0, 1))
        grid_spec = {'grid_mode': 'cell size', 'cell_size': float(cell_size),
                     'grid_origin': [float(bounds[0]), float(bounds[1])], 'support_halo_cells': 1}
    gx, gy = np.meshgrid(*axes)
    targets = np.column_stack((gx.ravel(), gy.ravel()))
    inside_hull = Delaunay(xy).find_simplex(targets) >= 0
    inside_area = boundaries.point_mask(area, targets) if area is not None else np.ones(len(targets), dtype=bool)
    mask = inside_area & (np.ones(len(targets), dtype=bool) if extrapolate else inside_hull)
    if not mask.any():
        raise ValueError('No grid cells fall in both the study boundary and sampled area. Check CRS/alignment or increase grid resolution.')
    from shapely.geometry import MultiPoint
    hull = MultiPoint(xy).convex_hull
    clip_geometry = (area if extrapolate else area.intersection(hull)) if area is not None else hull
    if clip_geometry.area <= 0:
        raise ValueError('The study boundary does not overlap the sampled area.')
    # Contours need values on both sides of an edge to reach the exact polygon.
    # Render on a rectangular support grid and clip the artists geometrically;
    # keep all exported values outside the chosen analysis area masked as before.
    if method == "kriging":
        rendered, rendered_variance = ordinary_kriging(xy, source[:, 2], targets,
            model=model, range_=range_, sill=sill, nugget=nugget)
    elif method == "idw":
        rendered = idw(xy, source[:, 2], targets, power, neighbors=neighbors)
        rendered_variance = np.full(len(targets), np.nan)
    else:
        raise ValueError("Choose ordinary kriging or inverse-distance weighting.")
    predictions = np.where(mask, rendered, np.nan)
    variance = np.where(mask, rendered_variance, np.nan)
    metadata = {"method": "ordinary kriging" if method == "kriging" else "inverse-distance weighting",
                "n_used": len(source), "x_column": x, "y_column": y, "value_column": value,
                "coordinates": coordinates, "xlabel": xlabel, "ylabel": ylabel, **projection,
                "resolution": resolution if cell_size is None else None, "mask": "sample convex hull; no extrapolation"}
    metadata.update(analysis_crs=analysis_crs, source_crs=source_crs, n_input=n_input)
    if coordinates in ('auto_utm', 'wgs84_projected'):
        metadata['source_crs'] = 'EPSG:4326'
    metadata.update(grid_spec, grid_shape=list(gx.shape),
                    grid_spacing_x=float(gx[0, 1]-gx[0, 0]), grid_spacing_y=float(gy[1, 0]-gy[0, 0]))
    if area is not None:
        metadata.update(boundary=boundaries.validate_boundary(boundary), extrapolate=bool(extrapolate),
                        samples_inside_boundary=bool(samples_inside_boundary), excluded_sample_rows_1based=excluded,
                        extrapolated_grid_cells=int((mask & ~inside_hull).sum()),
                        mask='study boundary' if extrapolate else 'study boundary intersected with sample convex hull')
    if method == "kriging":
        metadata.update(variogram=model, range=range_, partial_sill=sill, nugget=nugget,
                        parameters="user supplied; no automatic variogram fit", variance="new-observation prediction variance")
    else:
        metadata["power"] = power
        metadata.update(neighbors=None if neighbors is None else int(neighbors),
                        effective_neighbors=len(source) if neighbors is None else min(int(neighbors), len(source)),
                        neighborhood='all samples' if neighbors is None else 'nearest samples; include ties at cutoff distance')
    return GridResult(gx, gy, predictions.reshape(gx.shape), variance.reshape(gx.shape), xy, source[:, 2], metadata,
                      area, clip_geometry, inside_area.reshape(gx.shape), inside_hull.reshape(gx.shape),
                      rendered.reshape(gx.shape), rendered_variance.reshape(gx.shape))


def contour_result(grid, *, show_variance=False, levels=12, lines=True, labels=True,
                   samples=True, linewidth=.5, linecolor='#214b60', marker='o',
                   sample_size=18, sample_color='white', alpha=.8, basemap=None, surface_alpha=1.0,
                   show_colorbar=True, colorbar_orientation='vertical', show_grid=False, grid_spacing=0.,
                   north_arrow=False, north_reference='true', map_layout=None, colorbar_options=None,
                   classification='automatic', class_breaks=None, surface='contours'):
    import matplotlib.pyplot as plt
    from ..._publication import PlotResult
    if show_variance and grid.metadata["method"] != "ordinary kriging":
        raise ValueError("Prediction variance is available for ordinary kriging only.")
    values = grid.variance if show_variance else grid.values
    rendered = grid.render_variance if show_variance else grid.render_values
    if rendered is None:
        rendered = values
    title = "Kriging prediction variance" if show_variance else grid.metadata["value_column"] + " · " + grid.metadata["method"]
    figure, ax = plt.subplots(figsize=(9, 6), layout="tight")
    try:
        from ...boundaries import transform_xy, draw_boundary, polygon_path
        gx, gy, sample_xy = grid.x, grid.y, grid.samples
        outline, clipping = grid.boundary_geometry, grid.clip_geometry
        display_crs = grid.metadata.get('analysis_crs', 'local')
        xlabel, ylabel = grid.metadata['xlabel'], grid.metadata['ylabel']
        if basemap is not None and basemap != 'plain':
            from ...basemaps import add_attribution
            from shapely.ops import transform
            source = display_crs
            gx, gy = transform_xy(grid.x, grid.y, source, 'EPSG:3857')
            sx, sy = transform_xy(*grid.samples.T, source, 'EPSG:3857')
            sample_xy = np.column_stack((sx, sy))
            if outline is not None:
                outline = transform(lambda x,y,z=None: transform_xy(x,y,source,'EPSG:3857'), outline)
            if clipping is not None:
                clipping = transform(lambda x,y,z=None: transform_xy(x,y,source,'EPSG:3857'), clipping)
            display_crs = 'EPSG:3857'
            xlabel, ylabel = 'Web Mercator easting (m)', 'Web Mercator northing (m)'
            add_attribution(ax, basemap)
        if not np.isfinite(surface_alpha) or not 0 < surface_alpha <= 1:
            raise ValueError('Contour opacity must be greater than zero and at most one.')
        from .classification import class_boundaries
        bounds, class_metadata = class_boundaries(values, levels, classification, class_breaks)
        from matplotlib.colors import BoundaryNorm
        norm = BoundaryNorm(bounds, 256) if class_metadata['method'] != 'automatic' else None
        if surface == 'contours':
            filled = ax.contourf(gx, gy, rendered, levels=bounds, cmap='viridis', norm=norm, alpha=surface_alpha, extend='both')
        elif surface == 'raster':
            filled = ax.pcolormesh(gx, gy, rendered, cmap='viridis', norm=BoundaryNorm(bounds, 256),
                                  shading='nearest', alpha=surface_alpha, rasterized=True)
        else:
            raise ValueError('Choose filled contours or classified raster cells.')
        from ...plot_legends import scale_legend, contour_legend
        scale_legend(ax, filled, 'Prediction variance' if show_variance else 'Interpolated values')
        clip_patch = None
        if clipping is not None:
            from matplotlib.patches import PathPatch
            clip_patch = PathPatch(polygon_path(clipping), transform=ax.transData)
            filled.set_clip_path(clip_patch)
        if lines and np.nanmax(values) > np.nanmin(values):
            contours = ax.contour(gx, gy, rendered, levels=bounds, colors=linecolor, linewidths=linewidth, alpha=.8)
            contour_legend(ax, contours)
            if clip_patch is not None:
                contours.set_clip_path(clip_patch)
            if labels:
                texts = ax.clabel(contours, fontsize=7, inline=True)
                from ...plot_layout import ContourLabelLayout
                ContourLabelLayout(ax, texts)
                if clip_patch is not None:
                    for text in texts:
                        text.set_clip_path(clip_patch)
                        text.set_clip_on(True)
        if samples:
            ax.scatter(*sample_xy.T, s=sample_size, marker=marker, facecolors=sample_color, alpha=alpha,
                       edgecolors="#193c51", linewidths=.7, label="Sample locations")
        if outline is not None:
            draw_boundary(ax, outline)
        ax.set(xlabel=xlabel, ylabel=ylabel, title=title, aspect="equal")
        xpad, ypad = np.ptp(gx)*.025, np.ptp(gy)*.025
        ax.set_xlim(np.min(gx)-xpad, np.max(gx)+xpad)
        ax.set_ylim(np.min(gy)-ypad, np.max(gy)+ypad)
        ax.set_autoscale_on(False)
        figure._aquaprov_boundary_crs = display_crs
        from .cartography import aligned_colorbar, decorate_map
        if show_colorbar:
            bar = aligned_colorbar(ax, filled, "Variance (measurement units²)" if show_variance else grid.metadata["value_column"], colorbar_orientation,map_layout,colorbar_options)
            if np.nanmin(values) == np.nanmax(values):
                bar.set_ticks([float(np.nanmin(values))])
        cartography = decorate_map(ax, display_crs, show_grid=show_grid, grid_spacing=grid_spacing,
                     north_arrow=north_arrow, north_reference=north_reference,layout=map_layout)
        if samples:
            # Keep the sample/boundary key clear of the basemap credits below.
            ax.legend(loc="upper left" if north_arrow or basemap not in (None, 'plain') else "best")
        table = pd.DataFrame({"x": grid.x.ravel(), "y": grid.y.ravel(), "prediction": grid.values.ravel()})
        if grid.metadata["method"] == "ordinary kriging":
            table["variance"] = grid.variance.ravel()
        if grid.boundary_geometry is not None:
            table['inside_boundary'] = grid.inside_boundary.ravel()
            table['inside_sample_hull'] = grid.inside_sample_hull.ravel()
            table['extrapolated'] = np.isfinite(table.prediction) & ~table.inside_sample_hull
        if basemap is not None and basemap != 'plain':
            table['display_x_3857'], table['display_y_3857'] = gx.ravel(), gy.ravel()
        notes = ['Grid mask: '+grid.metadata['mask']+'.']
        if grid.metadata.get('extrapolate'):
            notes.append('Full-boundary coverage includes extrapolation beyond the sample convex hull. Those cells are flagged in the grid table.')
        if grid.boundary_geometry is not None:
            notes.append('The boundary clips predictions; it is not a groundwater flow barrier or a kriging boundary condition.')
        if grid.metadata["method"] == "ordinary kriging":
            notes.append("Isotropic ordinary kriging with user-supplied parameters; review the variogram and validate against held-out samples before interpretation.")
        if grid.metadata["coordinates"] == "wgs84":
            notes.append("Distances use a local equirectangular metre approximation. Use a suitable projected CRS for precise regional work.")
        if grid.metadata.get('projection_selection'):
            notes.append('Analysis projection: '+grid.metadata['analysis_crs_name']+' ('+grid.metadata['analysis_crs']+').')
        if grid.metadata['method'] == 'inverse-distance weighting':
            count = grid.metadata.get('neighbors')
            notes.append('IDW neighbourhood: all samples.' if count is None else
                         f'IDW neighbourhood: nearest {grid.metadata["effective_neighbors"]} available samples, including distance ties.')
        if 'approximation' in class_metadata['algorithm']:
            notes.append('Natural Breaks uses a bounded histogram approximation. Exact displayed thresholds are exported in class_boundaries.')
        tables = {"grid": table, "samples": pd.DataFrame({"x": grid.samples[:, 0], "y": grid.samples[:, 1], "value": grid.measurements})}
        if class_metadata['method'] != 'automatic':
            tables['class_boundaries'] = pd.DataFrame({'class': np.arange(1, len(bounds)),
                                                      'lower': bounds[:-1], 'upper': bounds[1:]})
        if grid.boundary_geometry is not None:
            rows = []
            parts = [grid.boundary_geometry] if grid.boundary_geometry.geom_type == 'Polygon' else grid.boundary_geometry.geoms
            for part_id, part in enumerate(parts, 1):
                for ring_id, ring in enumerate([part.exterior, *part.interiors]):
                    rows.extend({'part': part_id, 'ring': ring_id, 'hole': ring_id > 0, 'vertex': i+1, 'x': x, 'y': y}
                                for i,(x,y) in enumerate(ring.coords))
            tables['boundary_vertices'] = pd.DataFrame(rows)
            tables['excluded_samples'] = pd.DataFrame({'source_row': grid.metadata['excluded_sample_rows_1based']})
        return PlotResult(figure, tables,
                          dict(grid.metadata, display="variance" if show_variance else "prediction", display_crs=display_crs,
                               basemap=basemap or 'plain', surface_alpha=surface_alpha,
                               show_colorbar=show_colorbar, colorbar_orientation=colorbar_orientation,
                               show_grid=show_grid, grid_spacing=grid_spacing, north_arrow=north_arrow,
                               north_reference=north_reference,cartography=cartography,
                               classification=dict(class_metadata, boundaries=np.asarray(bounds).tolist()), surface=surface,
                               appearance={'levels': levels, 'lines': lines, 'labels': labels, 'samples': samples,
                                           'linewidth': linewidth, 'linecolor': linecolor, 'marker': marker,
                                           'sample_size': sample_size, 'sample_color': sample_color, 'alpha': alpha}), notes)
    except Exception:
        plt.close(figure)
        raise
