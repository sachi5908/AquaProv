"""Metre-based analysis projections for local study areas worldwide."""
import numpy as np
from pyproj import CRS, Geod, Transformer
from shapely import get_coordinates


def analysis_coordinates(xy, coordinates, *, boundary=None, source_crs=None, target_crs=None):
    """One coordinate conversion for maps, index panels and validation folds."""
    from ... import boundaries
    from .interpolation import planar_coordinates
    source = boundaries.source_crs(source_crs) if source_crs is not None else 'local'
    geographic = coordinates in ('wgs84', 'auto_utm', 'wgs84_projected')
    if geographic and source not in ('local', 'EPSG:4326'):
        raise ValueError('WGS84 distance coordinates conflict with the declared source CRS.')
    if coordinates in ('auto_utm', 'wgs84_projected'):
        if coordinates == 'wgs84_projected' and not target_crs:
            raise ValueError('Enter the projected analysis CRS, for example EPSG:32645.')
        return project_wgs84(xy, boundary=boundary,
                             target_crs=target_crs if coordinates == 'wgs84_projected' else None)
    converted, xlabel, ylabel, info = planar_coordinates(xy, coordinates)
    if coordinates == 'projected' and source != 'local' and not CRS.from_user_input(source).is_projected:
        raise ValueError('Projected distance coordinates require a projected source CRS; longitude/latitude requires WGS84 distances.')
    crs = boundaries.local_crs(info) if coordinates == 'wgs84' else source
    if coordinates == 'wgs84' and boundary is not None:
        area = boundaries.geometry_in_crs(boundary, 'EPSG:4326', declared_local_crs='EPSG:4326')
        extent = np.vstack((xy, get_coordinates(area)))
        if (np.ptp(extent, axis=0) > 3).any():
            raise ValueError('Study boundary exceeds the local 3-degree approximation. Use a suitable projected CRS.')
    return converted, xlabel, ylabel, dict(info, analysis_crs=crs)


def project_wgs84(xy, *, boundary=None, target_crs=None):
    """Use a supplied metre CRS or choose a local WGS84 UTM/UPS projection.

    Automatic selection is limited to points/boundaries within 500 km of the
    geographic bounding-box centre. Larger or dateline-crossing studies need
    deliberate regional projection and boundary preparation in GIS.
    """
    from ...boundaries import geometry_in_crs
    xy = np.asarray(xy, dtype=float)
    extent = xy
    if boundary is not None:
        polygon = geometry_in_crs(boundary, 'EPSG:4326', declared_local_crs='EPSG:4326')
        extent = np.vstack((xy, get_coordinates(polygon)))
    if (not np.isfinite(extent).all() or (abs(extent[:, 0]) > 180).any()
            or (abs(extent[:, 1]) > 90).any()):
        raise ValueError('Use valid WGS84 longitude/latitude in decimal degrees.')
    automatic = target_crs is None
    lon = float((extent[:, 0].min() + extent[:, 0].max()) / 2)
    lat = float((extent[:, 1].min() + extent[:, 1].max()) / 2)
    if automatic:
        if np.ptp(extent[:, 0]) > 180:
            raise ValueError('Automatic projection cannot span the antimeridian. '
                             'Prepare projected coordinates and a split/projected boundary in GIS.')
        _, _, distances = Geod(ellps='WGS84').inv(
            np.full(len(extent), lon), np.full(len(extent), lat), *extent.T)
        if np.max(distances) > 500000:
            raise ValueError('Automatic UTM/UPS is for local study areas within 500 km of their centre. '
                             'Choose a suitable custom projected CRS for this larger region.')
        if lat > 84 or lat < -80:
            epsg = 32661 if lat >= 0 else 32761
        else:
            zone = min(60, max(1, int(np.floor((lon + 180) / 6)) + 1))
            if 56 <= lat < 64 and 3 <= lon < 12:
                zone = 32
            elif 72 <= lat <= 84 and 0 <= lon < 42:
                zone = 31 if lon < 9 else 33 if lon < 21 else 35 if lon < 33 else 37
            epsg = (32600 if lat >= 0 else 32700) + zone
        crs = CRS.from_epsg(epsg)
    else:
        try:
            crs = CRS.from_user_input(target_crs)
        except Exception as exc:
            raise ValueError('Enter a valid projected analysis CRS, for example EPSG:32645.') from exc
    if (not crs.is_projected or len(crs.axis_info) < 2
            or any(not np.isclose(axis.unit_conversion_factor, 1.) for axis in crs.axis_info[:2])):
        raise ValueError('The analysis CRS must be projected with metre units. '
                         'Choose a metre-based regional CRS or automatic UTM/UPS.')
    try:
        transformer = Transformer.from_crs('EPSG:4326', crs, always_xy=True)
        projected = np.column_stack(transformer.transform(*xy.T, errcheck=True))
    except Exception as exc:
        raise ValueError('Coordinates cannot be transformed into this analysis CRS.') from exc
    if not np.isfinite(projected).all():
        raise ValueError('Projection produced non-finite coordinates. Review the analysis CRS.')
    return projected, 'Easting (m)', 'Northing (m)', {
        'analysis_crs': crs.to_string(), 'analysis_crs_name': crs.name,
        'projection_selection': 'automatic UTM/UPS' if automatic else 'user-selected projected CRS',
        'distance_units': 'metres', 'projection_centre_lon': lon, 'projection_centre_lat': lat,
    }
