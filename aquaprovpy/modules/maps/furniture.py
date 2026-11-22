"""Draggable north symbols and scale bars measured on the ground."""
import numpy as np
from matplotlib.artist import Artist
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch, Polygon, Rectangle
from matplotlib.text import Text
from matplotlib.transforms import Affine2D, Bbox, IdentityTransform
from pyproj import Geod
from scipy.optimize import brentq

from ...boundaries import transform_xy

GEOD = Geod(ellps='WGS84')
UNIT_METRES = {'m': 1., 'km': 1000., 'mi': 1609.344, 'ft': .3048}


class MapFurniture(Artist):
    _aquaprov_draggable = True

    def __init__(self, axis, position, key):
        super().__init__()
        self.position = list(position)
        self.layout_key = key
        self.children = []
        self._bounds = None
        self.set_zorder(19)
        self.set_in_layout(False)
        axis.add_artist(self)

    def get_children(self):
        return self.children

    def contains(self, event):
        return (self.get_visible() and self._bounds is not None and event.x is not None
                and self._bounds.padded(5).contains(event.x, event.y)), {}

    def move_to(self, position):
        self.position = np.clip(position, [.03, .06], [.95, .94]).tolist()
        self.axes.figure._aquaprov_map_layout[self.layout_key] = self.position.copy()
        self.stale = True

    def paint(self, artists, renderer, background=False):
        self.children = artists
        for child in artists:
            child.set_figure(self.figure)
            child.axes = self.axes
        bounds = [child.get_window_extent(renderer) for child in artists]
        self._bounds = Bbox.union(bounds) if bounds else None
        if background and self._bounds is not None:
            box = self._bounds.padded(renderer.points_to_pixels(4))
            panel = Rectangle((box.x0, box.y0), box.width, box.height, facecolor='white',
                              alpha=.88, edgecolor='none', transform=IdentityTransform())
            panel.set_figure(self.figure)
            panel.draw(renderer)
        for child in artists:
            child.draw(renderer)
        self.stale = False


def text_at(x, y, text, size=9, **kwargs):
    return Text(x=x, y=y, text=text, ha='center', va='center', fontsize=size,
                color='#172f40', transform=IdentityTransform(), **kwargs)


class NorthArrow(MapFurniture):
    def __init__(self, axis, crs, reference, *, design='arrow', size=36, position=(.88, .76)):
        from .cartography import north_vector
        north_vector(crs, np.mean(axis.get_xlim()), np.mean(axis.get_ylim()), reference)
        super().__init__(axis, position, 'north_position')
        self.crs, self.reference, self.design, self.size = crs, reference, design, size

    def draw(self, renderer):
        if not self.get_visible():
            return
        from .cartography import north_vector
        axis = self.axes
        anchor = axis.transAxes.transform(self.position)
        source = axis.transData.inverted().transform(anchor)
        try:
            vector = north_vector(self.crs, *source, self.reference)
        except ValueError:
            self._bounds = None
            return
        direction = axis.transData.transform(source+vector)-anchor
        direction /= np.linalg.norm(direction)
        length = min(renderer.points_to_pixels(self.size), axis.bbox.width*.35, axis.bbox.height*.35)
        rotation = np.arctan2(-direction[0], direction[1])
        transform = Affine2D().scale(length).rotate(rotation).translate(*anchor)
        children = []
        if self.design == 'arrow':
            children.append(FancyArrowPatch(anchor-direction*length*.5, anchor+direction*length*.5,
                            arrowstyle='simple', mutation_scale=length*.45, facecolor='#172f40',
                            edgecolor='white', linewidth=1.1, transform=IdentityTransform()))
        elif self.design == 'chevron':
            for points, color in [([(0,.55),(-.22,-.45),(0,-.23)], 'black'),
                                  ([(0,.55),(.22,-.45),(0,-.23)], 'white')]:
                children.append(Polygon(points, facecolor=color, edgecolor='black', lw=.7, transform=transform))
        else:
            count = 4 if self.design == 'compass' else 8
            for i in range(count):
                angle = i*2*np.pi/count
                tip = np.array([np.sin(angle),np.cos(angle)])*(.52 if count == 4 or i % 2 == 0 else .34)
                left = np.array([np.sin(angle-.45),np.cos(angle-.45)])*.11
                right = np.array([np.sin(angle+.45),np.cos(angle+.45)])*.11
                for side, color in [(left,'black'),(right,'white')]:
                    children.append(Polygon([(0,0),tip,side], facecolor=color, edgecolor='black', lw=.55, transform=transform))
        label = ('+Y' if self.crs == 'local' else 'GN') if self.reference == 'grid' else 'N'
        p = anchor+direction*(length*.72)
        children.append(text_at(*p, label, max(9,min(self.size*.28,18)), fontweight='bold',
                                bbox=dict(facecolor='white', alpha=.8, edgecolor='none', pad=1)))
        self.paint(children, renderer)


def ground_distance(axis, crs, first, last, local_unit=None):
    """Distance between two positions in axes fractions, in metres."""
    xy = axis.transData.inverted().transform(axis.transAxes.transform([first, last]))
    if crs in (None, 'local'):
        if local_unit not in UNIT_METRES:
            raise ValueError('A scale bar on local X/Y needs a declared distance unit in Scale bar settings.')
        return float(np.linalg.norm(xy[1]-xy[0])*UNIT_METRES[local_unit])
    lon, lat = transform_xy(*xy.T, crs, 'EPSG:4326')
    return float(GEOD.inv(lon[0], lat[0], lon[1], lat[1])[2])


def scale_geometry(axis, crs, position, *, length=0., unit='km', local_unit=None):
    """Solve the displayed horizontal span for a ground distance at the bar."""
    x, y = position
    available = max(.005, .98-x)
    width = min(.28, available)
    distance = ground_distance(axis, crs, (x,y), (x+width,y), local_unit)
    requested = length*UNIT_METRES[unit]
    maximum = ground_distance(axis, crs, (x,y), (x+available,y), local_unit)
    if not np.isfinite(distance) or distance <= 0:
        raise ValueError('The current map extent cannot support a distance scale.')
    if requested <= 0 or requested > maximum:
        power = 10**np.floor(np.log10(distance))
        requested = max(v*power for v in (1,2,5,10) if v*power <= distance*(1+1e-12))
    end = brentq(lambda delta: ground_distance(axis,crs,(x,y),(x+delta,y),local_unit)-requested,
                 0., available, xtol=1e-12)
    return requested, end


class ScaleBar(MapFurniture):
    def __init__(self, axis, crs, *, design='alternating', unit='km', length=0., segments=4,
                 position=(.12,.10), local_unit=None, background=True, font_size=8):
        scale_geometry(axis, crs, position, length=length, unit=unit, local_unit=local_unit)
        super().__init__(axis, position, 'scale_position')
        self.crs, self.design, self.unit = crs, design, unit
        self.length, self.segments, self.local_unit = length, segments, local_unit
        self.background, self.font_size = background, font_size
        self.last_distance_metres = None
        self.last_endpoints = None

    def move_to(self, position):
        super().move_to(np.clip(position, [.03,.07],[.80,.90]))

    def draw(self, renderer):
        if not self.get_visible():
            return
        try:
            metres, span = scale_geometry(self.axes, self.crs, self.position,
                          length=self.length, unit=self.unit, local_unit=self.local_unit)
        except (ValueError, RuntimeError):
            self._bounds = None
            return
        start = self.axes.transAxes.transform(self.position)
        end = self.axes.transAxes.transform([self.position[0]+span,self.position[1]])
        self.last_distance_metres = metres
        self.last_endpoints = [self.position.copy(), [self.position[0]+span,self.position[1]]]
        unit = 'km' if self.design == 'dual' else self.unit
        pt = renderer.points_to_pixels(1)
        height = pt*5
        xs = np.linspace(start[0],end[0],self.segments+1)
        children = []
        if self.design == 'alternating':
            for i in range(self.segments):
                children.append(Rectangle((xs[i],start[1]),xs[i+1]-xs[i],height,
                                facecolor='black' if i % 2 == 0 else 'white', edgecolor='black', lw=.8,
                                transform=IdentityTransform()))
        else:
            children.append(Line2D([start[0],end[0]],[start[1],start[1]],color='black',lw=1,transform=IdentityTransform()))
        for i,x in enumerate(xs):
            children.append(Line2D([x,x],[start[1]-height*.5,start[1]+height],color='black',lw=.7,transform=IdentityTransform()))
        rows = [(unit,start[1]-pt*9)]
        if self.design == 'dual':
            rows.append(('mi',start[1]+pt*14))
        font = FontProperties(size=self.font_size)
        for row_unit,y in rows:
            labels = [f'{metres*i/self.segments/UNIT_METRES[row_unit]:.3g}' for i in range(len(xs))]
            widths = [renderer.get_text_width_height_descent(label,font,False)[0] for label in labels]
            previous = -float('inf')
            for i,(x,label,width) in enumerate(zip(xs,labels,widths)):
                if i not in (0,self.segments) and (x-width/2<previous+pt*4 or x+width/2>xs[-1]-widths[-1]/2-pt*4):
                    continue
                children.append(text_at(x,y,label,self.font_size))
                previous = x+width/2
            children.append(text_at(end[0]+widths[-1]/2+pt*5,y,row_unit,self.font_size))
            children[-1].set_ha('left')
        self.paint(children, renderer, self.background)
