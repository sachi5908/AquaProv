"""Explicit WGS84 coordinate conversion and bounded Web Mercator tile geometry.

No datum or coordinate system is guessed from the magnitude of an X/Y value.
UTM inversion uses the standard ellipsoidal transverse Mercator series (Snyder,
USGS Professional Paper 1395). It is restricted to the selected WGS84 UTM zone.
"""
import math

import numpy as np


EARTH_RADIUS = 6378137.0
WORLD_HALF = math.pi * EARTH_RADIUS
MAX_LATITUDE = math.degrees(math.atan(math.sinh(math.pi)))
TILE_SIZE = 256
MAX_TILES = 36
CRS_CHOICES = {
    'WGS84 longitude / latitude (EPSG:4326)': 'wgs84',
    'Web Mercator X / Y in metres (EPSG:3857)': 'mercator',
    'WGS84 UTM easting / northing in metres': 'utm',
}


def _coordinate_arrays(x, y):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if x.ndim != 1 or x.shape != y.shape or not x.size:
        raise ValueError('Supply equally sized, non-empty X and Y coordinate columns.')
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Coordinates must be finite numbers.')
    return x, y


def utm_to_lonlat(easting, northing, zone, hemisphere):
    """Invert WGS84 UTM; X=easting, Y=northing, both in metres."""
    x, y = _coordinate_arrays(easting, northing)
    if isinstance(zone, bool) or not isinstance(zone, (int, np.integer)) or not 1 <= zone <= 60:
        raise ValueError('Choose the UTM zone (1–60) supplied with your coordinates.')
    if hemisphere not in ('N', 'S'):
        raise ValueError('Choose UTM hemisphere N or S.')
    if ((x < 100000) | (x > 900000) | (y < 0) | (y > 10000000)).any():
        raise ValueError('UTM requires eastings 100,000–900,000 and northings 0–10,000,000 metres. Check the zone and units.')
    flattening = 1 / 298.257223563
    e2 = flattening * (2 - flattening)
    ep2 = e2 / (1 - e2)
    e1 = (1 - np.sqrt(1 - e2)) / (1 + np.sqrt(1 - e2))
    meridian = (y - (10000000 if hemisphere == 'S' else 0)) / 0.9996
    mu = meridian / (EARTH_RADIUS * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    phi = (mu + (3 * e1 / 2 - 27 * e1**3 / 32) * np.sin(2 * mu)
           + (21 * e1**2 / 16 - 55 * e1**4 / 32) * np.sin(4 * mu)
           + 151 * e1**3 / 96 * np.sin(6 * mu)
           + 1097 * e1**4 / 512 * np.sin(8 * mu))
    sin, cos, tan = np.sin(phi), np.cos(phi), np.tan(phi)
    n = EARTH_RADIUS / np.sqrt(1 - e2 * sin**2)
    r = EARTH_RADIUS * (1 - e2) / (1 - e2 * sin**2)**1.5
    t, c = tan**2, ep2 * cos**2
    d = (x - 500000) / (n * 0.9996)
    latitude = phi - (n * tan / r) * (
        d**2 / 2 - (5 + 3 * t + 10 * c - 4 * c**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t + 298 * c + 45 * t**2 - 252 * ep2 - 3 * c**2) * d**6 / 720)
    longitude = np.radians(zone * 6 - 183) + (
        d - (1 + 2 * t + c) * d**3 / 6
        + (5 - 2 * c + 28 * t - 3 * c**2 + 8 * ep2 + 24 * t**2) * d**5 / 120) / cos
    lon, lat = np.degrees(longitude), np.degrees(latitude)
    # Widen to six degrees for the officially widened Norway/Svalbard zones.
    if (np.abs(lon - (zone * 6 - 183)) > 6.1).any() or (lat < -80).any() or (lat > 84).any():
        raise ValueError('Coordinates fall outside the supported WGS84 UTM zone/latitude range. Check your CRS.')
    if (hemisphere == 'N' and (lat < -1e-8).any()) or (hemisphere == 'S' and (lat > 1e-8).any()):
        raise ValueError('UTM northings do not match the selected hemisphere.')
    return (lon + 180) % 360 - 180, lat


def project_coordinates(x, y, crs, zone=None, hemisphere='N'):
    """Return EPSG:3857 X/Y and WGS84 longitude/latitude without altering inputs."""
    x, y = _coordinate_arrays(x, y)
    if crs == 'mercator':
        if (np.abs(x) > WORLD_HALF).any() or (np.abs(y) > WORLD_HALF).any():
            raise ValueError('EPSG:3857 coordinates exceed the map world bounds. Check the CRS and metre units.')
        lon = np.degrees(x / EARTH_RADIUS)
        lat = np.degrees(np.arctan(np.sinh(y / EARTH_RADIUS)))
        return x.copy(), y.copy(), lon, lat
    if crs == 'utm':
        lon, lat = utm_to_lonlat(x, y, zone, hemisphere)
    elif crs == 'wgs84':
        lon, lat = x, y
    else:
        raise ValueError('Select the coordinate system for the real map. Local X/Y alone cannot identify a real location.')
    if (np.abs(lon) > 180).any() or (np.abs(lat) > 90).any():
        raise ValueError('WGS84 needs X = longitude (−180 to 180) and Y = latitude (−90 to 90), in decimal degrees. Check for swapped columns or projected coordinates.')
    if (np.abs(lat) > MAX_LATITUDE).any():
        raise ValueError('The OpenStreetMap background supports latitudes only between −85.0511 and 85.0511 degrees. Use the plain coordinate view near the poles.')
    mx = EARTH_RADIUS * np.radians(lon)
    my = EARTH_RADIUS * np.arcsinh(np.tan(np.radians(lat)))
    return mx, my, lon.copy(), lat.copy()


def map_limits(x, y):
    """Fit samples with context; give a single sample a useful 1 km view."""
    x, y = _coordinate_arrays(x, y)
    limits = []
    for values in (x, y):
        low, high = float(values.min()), float(values.max())
        pad = max((high - low) * 0.12, 500)
        limits.append((max(-WORLD_HALF, low - pad), min(WORLD_HALF, high + pad)))
    return limits


def tile_extent(tile):
    zoom, column, row = tile
    width = 2 * WORLD_HALF / 2**zoom
    left = -WORLD_HALF + column * width
    top = WORLD_HALF - row * width
    return left, left + width, top - width, top


def visible_tiles(xlim, ylim, pixel_width=1024, *, max_zoom=19):
    """Plan only visible tiles, lowering zoom to enforce a strict request bound."""
    xmin, xmax = sorted(xlim)
    ymin, ymax = sorted(ylim)
    if not np.isfinite([xmin, xmax, ymin, ymax, pixel_width]).all():
        return []
    if xmax <= -WORLD_HALF or xmin >= WORLD_HALF or ymax <= -WORLD_HALF or ymin >= WORLD_HALF:
        return []
    xmin, xmax = max(xmin, -WORLD_HALF), min(xmax, WORLD_HALF)
    ymin, ymax = max(ymin, -WORLD_HALF), min(ymax, WORLD_HALF)
    if xmax <= xmin or ymax <= ymin:
        return []
    zoom = max(0, min(max_zoom, int(math.floor(math.log2(
        2 * WORLD_HALF * max(pixel_width, 1) / ((xmax - xmin) * TILE_SIZE))))))
    while True:
        count = 2**zoom
        width = 2 * WORLD_HALF / count
        x0 = max(0, min(count - 1, int((xmin + WORLD_HALF) / width)))
        x1 = max(0, min(count - 1, math.ceil((xmax + WORLD_HALF) / width) - 1))
        y0 = max(0, min(count - 1, int((WORLD_HALF - ymax) / width)))
        y1 = max(0, min(count - 1, math.ceil((WORLD_HALF - ymin) / width) - 1))
        if (x1 - x0 + 1) * (y1 - y0 + 1) <= MAX_TILES or zoom == 0:
            return [(zoom, x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
        zoom -= 1
