"""Public raster basemaps and the attribution retained in exported figures."""

BASEMAPS = {
    'osm': {'title': 'OpenStreetMap (online)', 'name': 'OpenStreetMap',
            'url': 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', 'max_zoom': 19,
            'attribution': '© OpenStreetMap contributors · openstreetmap.org/copyright',
            'credit_url': 'https://www.openstreetmap.org/copyright'},
    'plain': {'title': 'Plain coordinates (no background)', 'name': 'Plain coordinates'},
    'esri_light': {'title': 'Esri light gray (online)', 'name': 'Esri Light Gray Canvas',
            'url': 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', 'max_zoom': 16,
            'attribution': 'Tiles © Esri · Sources: Esri, HERE, Garmin, OpenStreetMap contributors, and the GIS User Community',
            'credit_url': 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer'},
    'esri_dark': {'title': 'Esri dark gray (online)', 'name': 'Esri Dark Gray Canvas',
            'url': 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', 'max_zoom': 16,
            'attribution': 'Tiles © Esri · Sources: Esri, HERE, Garmin, OpenStreetMap contributors, and the GIS User Community',
            'credit_url': 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer'},
}


def basemap(key):
    if key not in BASEMAPS:
        raise ValueError('Unknown basemap provider.')
    return BASEMAPS[key]


def add_attribution(axis, key):
    provider = basemap(key)
    if key == 'plain':
        return None
    from textwrap import fill
    text = axis.text(.99, .01, fill(provider['attribution'], 85), transform=axis.transAxes,
                     ha='right', va='bottom', fontsize=7, color='#243447', zorder=20,
                     bbox={'facecolor': 'white', 'alpha': .95, 'edgecolor': 'none'})
    text.set_url(provider['credit_url'])
    text.set_in_layout(False)
    return text
