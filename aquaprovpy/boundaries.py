"""Polygon boundaries, bounded KML/KMZ/GeoJSON imports and explicit CRS conversion."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import zipfile

from defusedxml import ElementTree as XML
import numpy as np
from pyproj import CRS, Transformer
from shapely import intersects_xy
from shapely.geometry import Polygon, MultiPolygon, shape, mapping
from shapely.geometry.polygon import orient
from shapely.ops import transform, unary_union
from shapely.validation import explain_validity

MAX_XML_BYTES = 12 * 1024 * 1024
MAX_VERTICES = 100000


def source_crs(code, zone=None, hemisphere=None):
    if code in ('wgs84', 'mercator'):
        return 'EPSG:4326' if code == 'wgs84' else 'EPSG:3857'
    if code == 'utm':
        if not isinstance(zone, int) or not 1 <= zone <= 60 or hemisphere not in ('N', 'S'):
            raise ValueError('Select the WGS84 UTM zone and hemisphere.')
        return f'EPSG:{(32600 if hemisphere == "N" else 32700) + zone}'
    if code is None or code == 'local':
        return 'local'
    return CRS.from_user_input(code).to_string()


def local_crs(projection):
    """The same local equirectangular metres used by the interpolation engine."""
    lat, lon = projection['local_origin_lat'], projection['local_origin_lon']
    return (f'+proj=eqc +lat_ts={lat:.15g} +lat_0={lat:.15g} +lon_0={lon:.15g} '
            '+R=6371008.8 +units=m +no_defs +type=crs')


def validate_geometry(geometry):
    if geometry.geom_type not in ('Polygon', 'MultiPolygon') or geometry.is_empty:
        raise ValueError('A boundary must contain a non-empty Polygon or MultiPolygon.')
    parts = [geometry] if geometry.geom_type == 'Polygon' else list(geometry.geoms)
    count = 0
    for polygon in parts:
        for ring in [polygon.exterior, *polygon.interiors]:
            xy = np.asarray(ring.coords)
            count += len(xy)
            if xy.shape[1] != 2 or not np.isfinite(xy).all():
                raise ValueError('Boundary vertices must be finite 2D coordinates.')
    if count > MAX_VERTICES:
        raise ValueError(f'Boundary exceeds {MAX_VERTICES:,} vertices; simplify it in GIS first.')
    if not geometry.is_valid or not np.isfinite(geometry.area) or geometry.area <= 0:
        raise ValueError('Invalid boundary: '+explain_validity(geometry)+'. Correct crossing edges or holes.')
    return geometry


def make_boundary(geometry, crs, *, name='Study area', provenance=None):
    geometry = validate_geometry(geometry)
    crs = 'local' if crs == 'local' else CRS.from_user_input(crs).to_string()
    if crs == 'EPSG:4326':
        xmin, ymin, xmax, ymax = geometry.bounds
        if xmin < -180 or xmax > 180 or ymin < -90 or ymax > 90:
            raise ValueError('Boundary longitude/latitude is outside WGS84 bounds.')
        if xmax-xmin > 180:
            raise ValueError('Antimeridian-crossing boundaries need splitting in GIS before import.')
    # JSON lists, not tuples, make saved state and restored state identical.
    return {'version': 1, 'name': str(name), 'crs': crs,
            'geometry': json.loads(json.dumps(mapping(geometry))), 'provenance': deepcopy(provenance or {})}


def validate_boundary(boundary):
    if not isinstance(boundary, dict) or boundary.get('version') != 1:
        raise ValueError('Unsupported study-area boundary document.')
    return make_boundary(shape(boundary['geometry']), boundary['crs'], name=boundary.get('name', 'Study area'),
                         provenance=boundary.get('provenance'))


def transform_xy(x, y, source, target):
    if source == target:
        return np.asarray(x), np.asarray(y)
    if 'local' in (source, target):
        raise ValueError('Select the source coordinate system to align a geographic boundary or basemap with local X/Y.')
    transformer = Transformer.from_crs(source, target, always_xy=True)
    tx, ty = transformer.transform(x, y, errcheck=True)
    if not np.isfinite(tx).all() or not np.isfinite(ty).all():
        raise ValueError('Coordinate transformation produced invalid boundary coordinates.')
    return np.asarray(tx), np.asarray(ty)


def geometry_in_crs(boundary, target, *, declared_local_crs=None):
    b = validate_boundary(boundary)
    origin = (declared_local_crs or 'local') if b['crs'] == 'local' else b['crs']
    g = shape(b['geometry'])
    if origin != target:
        g = transform(lambda x,y,z=None: transform_xy(x, y, origin, target), g)
    return validate_geometry(g)


def point_mask(geometry, xy):
    xy = np.asarray(xy, dtype=float)
    return np.asarray(intersects_xy(geometry, xy[:, 0], xy[:, 1]), dtype=bool)


def polygon_path(geometry):
    """Compound nonzero-winding path; clockwise holes remain transparent."""
    from matplotlib.path import Path as MplPath
    vertices, codes = [], []
    def polygons(g):
        if g.geom_type == 'Polygon':
            yield g
        elif g.geom_type in ('MultiPolygon', 'GeometryCollection'):
            for part in g.geoms:
                yield from polygons(part)
    parts = polygons(geometry)
    for part in parts:
        part = orient(part, sign=1)
        for ring in [part.exterior, *part.interiors]:
            xy = np.asarray(ring.coords)
            vertices.extend(xy)
            codes.extend([MplPath.MOVETO] + [MplPath.LINETO]*(len(xy)-2) + [MplPath.CLOSEPOLY])
    return MplPath(vertices, codes)


def draw_boundary(axis, geometry, *, color='#d97706', width=1.7):
    from matplotlib.patches import PathPatch
    patch = PathPatch(polygon_path(geometry), facecolor='none', edgecolor=color,
                      linewidth=width, zorder=6, label='Study boundary')
    axis.add_patch(patch)
    return patch


def _coordinates(element):
    if element is None or not element.text:
        raise ValueError('KML polygon has no coordinates.')
    vertices = []
    for token in element.text.split():
        values = token.split(',')
        if len(values) not in (2, 3):
            raise ValueError('KML coordinates must be longitude,latitude[,altitude].')
        vertices.append((float(values[0]), float(values[1])))
    if len(vertices) < 4 or vertices[0] != vertices[-1]:
        raise ValueError('KML polygon rings must have at least three vertices and close at the first vertex.')
    return vertices


def _kml_features(payload, document):
    root = XML.fromstring(payload)
    if root.tag.split('}')[-1] not in ('kml', 'Document', 'Placemark', 'Folder'):
        raise ValueError('This file is not a KML document.')
    # Strip namespaces locally so KML 2.1/2.2 and unqualified exports work.
    for element in root.iter():
        element.tag = element.tag.split('}')[-1]
    marks = list(root.iter('Placemark'))
    if not marks:
        marks = [root]
    features = []
    for index, mark in enumerate(marks, 1):
        polygons = []
        for node in mark.iter('Polygon'):
            outer = _coordinates(node.find('./outerBoundaryIs/LinearRing/coordinates'))
            holes = [_coordinates(inner.find('./LinearRing/coordinates')) for inner in node.findall('./innerBoundaryIs')]
            polygons.append(validate_geometry(Polygon(outer, holes)))
        if polygons:
            name = mark.findtext('name') or f'{document} · area {index}'
            features.append(make_boundary(unary_union(polygons), 'EPSG:4326', name=name,
                                           provenance={'document': document, 'format': 'KML', 'altitude': 'ignored'}))
    return features


def import_boundaries(path):
    """Read polygon features only. Never extract archives or follow network links."""
    path = Path(path)
    if path.stat().st_size > 64*1024*1024:
        raise ValueError('Boundary file exceeds 64 MB.')
    raw = path.read_bytes()
    if path.suffix.lower() == '.kmz':
        with zipfile.ZipFile(path) as archive:
            entries = [i for i in archive.infolist() if i.filename.lower().endswith('.kml') and not i.is_dir()]
            if not entries or len(entries) > 32 or sum(i.file_size for i in entries) > MAX_XML_BYTES:
                raise ValueError('KMZ needs 1–32 KML documents totalling at most 12 MB.')
            features = []
            for entry in entries:
                with archive.open(entry) as stream:
                    payload = stream.read(MAX_XML_BYTES+1)
                if len(payload) > MAX_XML_BYTES:
                    raise ValueError('KML document exceeds the import size limit.')
                features.extend(_kml_features(payload, entry.filename))
    elif path.suffix.lower() == '.kml':
        if len(raw) > MAX_XML_BYTES:
            raise ValueError('KML document exceeds 12 MB.')
        features = _kml_features(raw, path.name)
    elif path.suffix.lower() in ('.json', '.geojson'):
        if len(raw) > MAX_XML_BYTES:
            raise ValueError('GeoJSON document exceeds 12 MB.')
        document = json.loads(raw)
        if document.get('crs'):
            raise ValueError('GeoJSON must use WGS84 longitude/latitude (RFC 7946); reproject legacy GeoJSON in GIS first.')
        nodes = document.get('features', []) if document.get('type') == 'FeatureCollection' else [document]
        features = []
        for index, node in enumerate(nodes, 1):
            geometry = node.get('geometry') if node.get('type') == 'Feature' else node
            if geometry and geometry.get('type') in ('Polygon', 'MultiPolygon'):
                features.append(make_boundary(shape(geometry), 'EPSG:4326',
                    name=(node.get('properties') or {}).get('name', f'Area {index}'), provenance={'format': 'GeoJSON'}))
    else:
        raise ValueError('Choose a KML, KMZ or GeoJSON polygon boundary.')
    if not features:
        raise ValueError('No polygon boundaries found. Points, paths and external NetworkLinks are not study-area polygons.')
    for b in features:
        b['provenance'].update(source_file=path.name, source_sha256=hashlib.sha256(raw).hexdigest())
    return features


def merge_boundaries(features):
    if not features:
        raise ValueError('Select at least one boundary area.')
    crs = features[0]['crs']
    geometry = unary_union([geometry_in_crs(b, crs) for b in features])
    return make_boundary(geometry, crs, name=features[0]['name'] if len(features) == 1 else f'Study area ({len(features)} features)',
                         provenance={'features': [{'name':b['name'], **b.get('provenance', {})} for b in features]})
