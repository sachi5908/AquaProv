"""Geographic graticules and frame ticks on an unchanged projected map."""
import numpy as np
from matplotlib.artist import Artist
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
from matplotlib.ticker import Formatter, Locator, AutoMinorLocator
from pyproj import Transformer
from scipy.optimize import brentq


def coordinate_label(value, longitude=True, style='dms', precision=1):
    limit = 180 if longitude else 90
    if not np.isfinite(value) or abs(value) > limit+1e-8:
        return ''
    direction = ('E' if value >= 0 else 'W') if longitude else ('N' if value >= 0 else 'S')
    absolute = abs(value)
    if style == 'decimal':
        return f'{absolute:.{precision}f}°{direction}'
    if style == 'dm':
        total = round(absolute*60, precision)
        deg, minutes = divmod(total,60)
        return f'{int(deg)}°{minutes:.{precision}f}′{direction}'
    # Round total seconds first, so 59.9999 seconds carries into minutes/degrees.
    total = round(absolute*3600, precision)
    deg, rest = divmod(total,3600)
    minutes, seconds = divmod(rest,60)
    return f'{int(deg)}°{int(minutes):02d}′{seconds:0{3+precision if precision else 2}.{precision}f}″{direction}'


def angular_ticks(low, high, interval=0.):
    if high <= low or not np.isfinite([low,high]).all():
        return np.array([])
    if interval <= 0 or (high-low)/interval > 100:
        steps = np.array([1,2,5,10,15,30,60,120,300,600,900,1800,3600,7200,18000,36000,72000,180000])/3600
        interval = steps[min(np.searchsorted(steps,(high-low)/6),len(steps)-1)]
    return np.arange(np.ceil(low/interval-1e-9),np.floor(high/interval+1e-9)+1)*interval


class GeographicFrame:
    def __init__(self, axis, crs, options):
        if crs in (None,'local'):
            raise ValueError('Longitude/latitude labels need a source coordinate system. Select it in Data first.')
        self.axis, self.options = axis, options
        self.to_geo = Transformer.from_crs(crs,'EPSG:4326',always_xy=True)
        self.to_map = Transformer.from_crs('EPSG:4326',crs,always_xy=True)
        self._cache = {}

    def edge_xy(self, side, positions):
        xlim, ylim = self.axis.get_xlim(), self.axis.get_ylim()
        positions = np.asarray(positions)
        if side in ('bottom','top'):
            return positions, np.full_like(positions,ylim[0 if side == 'bottom' else 1])
        return np.full_like(positions,xlim[0 if side == 'left' else 1]), positions

    def edge_geo(self, side, positions):
        lon, lat = self.to_geo.transform(*self.edge_xy(side,positions))
        return np.asarray(lon if side in ('bottom','top') else lat)

    def intersections(self, side):
        view = (*self.axis.get_xlim(), *self.axis.get_ylim())
        key = (side,view)
        if key in self._cache:
            return self._cache[key]
        if len(self._cache)>16:
            self._cache.clear()
        longitude = side in ('bottom','top')
        limits = self.axis.get_xlim() if longitude else self.axis.get_ylim()
        points = np.linspace(*limits,65)
        values = self.edge_geo(side,points)
        good = values[np.isfinite(values)]
        if len(good)<2 or (longitude and np.ptp(good)>180):
            return []
        step = self.options['longitude_interval'] if longitude else self.options['latitude_interval']
        ticks = angular_ticks(good.min(),good.max(),step)
        result = []
        for tick in ticks:
            for i in range(len(points)-1):
                a,b = values[i]-tick,values[i+1]-tick
                if not np.isfinite([a,b]).all() or a*b > 0 or (a == b == 0):
                    continue
                lo,hi = sorted([points[i],points[i+1]])
                position = brentq(lambda p:float(self.edge_geo(side,p))-tick,lo,hi,xtol=1e-8)
                if not any(abs(position-p)<1e-6 for p,_ in result):
                    result.append((position,tick))
        self._cache[key] = result
        return result

    def extent(self):
        xlim, ylim = self.axis.get_xlim(), self.axis.get_ylim()
        xs = np.linspace(*xlim,32); ys = np.linspace(*ylim,32)
        x = np.r_[xs,xs,np.full_like(ys,xlim[0]),np.full_like(ys,xlim[1])]
        y = np.r_[np.full_like(xs,ylim[0]),np.full_like(xs,ylim[1]),ys,ys]
        lon,lat = np.asarray(self.to_geo.transform(x,y))
        good = np.isfinite(lon)&np.isfinite(lat)
        if not good.any() or np.ptp(lon[good])>180:
            return None
        return (lon[good].min(),lon[good].max(),max(-89.9,lat[good].min()),min(89.9,lat[good].max()))


class FrameLocator(Locator):
    def __init__(self, frame, side):
        self.frame, self.side = frame, side

    def __call__(self):
        return np.array([p for p,_ in self.frame.intersections(self.side)])


class FrameFormatter(Formatter):
    def __init__(self, frame, side):
        self.frame, self.side = frame, side
        self._label_key = None
        self._label_positions = []

    def __call__(self, value, pos=None):
        o = self.frame.options
        # Keep the requested grid/tick intervals while omitting labels that
        # would overlap at the current canvas size.
        axis = self.frame.axis
        key = (*axis.get_xlim(),*axis.get_ylim(),axis.bbox.width,axis.bbox.height)
        if key != self._label_key:
            self._label_key = key
            font = FontProperties(size=o['coordinate_font_size'])
            previous_end = -float('inf')
            self._label_positions = []
            rows = []
            for p,angle in self.frame.intersections(self.side):
                xy = self.frame.edge_xy(self.side,p)
                pixel = axis.transData.transform(xy)[0 if self.side in ('bottom','top') else 1]
                label = coordinate_label(angle,self.side in ('bottom','top'),o['coordinate_format'],o['coordinate_precision'])
                width = TextPath((0,0),label,prop=font).get_extents().width*axis.figure.dpi/72 + 3
                rows.append((pixel,p,width))
            for pixel,p,width in sorted(rows):
                low,high = (axis.bbox.x0,axis.bbox.x1) if self.side in ('bottom','top') else (axis.bbox.y0,axis.bbox.y1)
                if pixel-width/2<low+3 or pixel+width/2>high-3:
                    continue
                if pixel-width/2 > previous_end+5:
                    self._label_positions.append(p)
                    previous_end = pixel+width/2
        if not any(abs(value-p)<1e-6 for p in self._label_positions):
            return ''
        return coordinate_label(float(self.frame.edge_geo(self.side,value)), self.side in ('bottom','top'),
                                o['coordinate_format'],o['coordinate_precision'])


class Graticule(Artist):
    def __init__(self, axis, frame, show, options):
        super().__init__()
        self.frame, self.show, self.options = frame, show, options
        self.set_zorder(2.4)
        self.set_in_layout(False)
        axis.add_artist(self)

    def draw(self, renderer):
        o, axis = self.options,self.axes
        if not self.show or o['grid_design']=='frame':
            return
        extent = self.frame.extent()
        if extent is None:
            return
        lo,hi,bot,top = extent
        lons = angular_ticks(lo,hi,o['longitude_interval'])
        lats = angular_ticks(bot,top,o['latitude_interval'])
        if o['grid_design']=='crosses':
            lon,lat = np.meshgrid(lons,lats)
            x,y = self.frame.to_map.transform(lon.ravel(),lat.ravel())
            collection = Line2D(x,y,linestyle='none',marker='+',markersize=4,
                         markeredgewidth=o['grid_width'],color=o['grid_color'],alpha=o['grid_alpha'],transform=axis.transData)
        else:
            paths = []
            lat = np.linspace(bot,top,129)
            lon = np.linspace(lo,hi,129)
            for value in lons:
                paths.append(np.column_stack(self.frame.to_map.transform(np.full_like(lat,value),lat)))
            for value in lats:
                paths.append(np.column_stack(self.frame.to_map.transform(lon,np.full_like(lon,value))))
            collection = LineCollection(paths, colors=o['grid_color'],linewidths=o['grid_width'],
                         linestyles=o['grid_design'],alpha=o['grid_alpha'],transform=axis.transData)
        collection.set_figure(axis.figure)
        collection.axes = axis
        collection.set_clip_path(axis.patch)
        collection.draw(renderer)
        self.stale = False


def geographic_frame(axis, crs, options, show_grid):
    frame = GeographicFrame(axis,crs,options)
    axis.grid(False)
    sides = [(axis.xaxis,'bottom'),(axis.yaxis,'left')]
    if options['frame_sides']=='all':
        top = axis.secondary_xaxis('top')
        right = axis.secondary_yaxis('right')
        top.set_navigate(False); right.set_navigate(False)
        sides.extend([(top.xaxis,'top'),(right.yaxis,'right')])
    for component,side in sides:
        component.set_major_locator(FrameLocator(frame,side))
        component.set_major_formatter(FrameFormatter(frame,side))
        if options['minor_ticks']:
            component.set_minor_locator(AutoMinorLocator(2))
        component.set_tick_params(which='major',labelsize=options['coordinate_font_size'],direction='out',pad=3,
                                  labelrotation=90 if side in ('left','right') else 0)
    axis.set_xlabel('Longitude')
    axis.set_ylabel('Latitude')
    axis._aquaprov_geographic_frame = frame
    axis._aquaprov_custom_grid = Graticule(axis,frame,show_grid,options)
    return frame
