"""Measured layout for plot keys and labels, without moving observations."""
import math

import numpy as np
from matplotlib.artist import Artist
from matplotlib.text import Text
from matplotlib.transforms import Bbox
from matplotlib.layout_engine import ConstrainedLayoutEngine, LayoutEngine


def fit_figure_legend(figure, renderer):
    legend = (getattr(figure, '_aquaprov_style_outside_legend', None)
              or getattr(figure, '_aquaprov_outside_legend', None))
    if legend is None or not legend.get_visible():
        return
    side = legend._outside_loc in ('right', 'left')
    for text in legend.get_texts():
        text.set_fontsize(getattr(text, '_aquaprov_legend_fontsize', 9))
    for _ in range(12):
        box = legend.get_window_extent(renderer)
        factor = min(1., (figure.bbox.width * .42 if side else figure.bbox.width - figure.dpi * .35) / max(box.width, 1),
                     figure.bbox.height * (.9 if side else .42) / max(box.height, 1))
        if factor >= .999:
            break
        # Handles and packing gaps do not scale with Text. Remeasure so a
        # single proportional adjustment cannot leave the key off the page.
        for text in legend.get_texts():
            text.set_fontsize(text.get_fontsize() * max(.1, factor * .98))


class AxesLegendLayout(Artist):
    """Fit long in-axes keys after layout, including during vector export."""
    def __init__(self, axis):
        super().__init__()
        self.axis = axis
        self.set_zorder(4.9)
        self.set_in_layout(False)
        axis.add_artist(self)

    def draw(self, renderer):
        legend = self.axis.get_legend()
        if legend is None:
            legend = next((key for key in self.axis.figure.legends
                           if getattr(key, '_aquaprov_inside_axis', None) is self.axis and key.get_visible()), None)
        if legend is None or not legend.get_visible():
            return
        anchor = legend.get_bbox_to_anchor()
        bounds = self.axis.bbox
        # Explicit anchors outside the axes remain intentional placements.
        if (anchor.x0 < bounds.x0 - 1 or anchor.y0 < bounds.y0 - 1
                or anchor.x1 > bounds.x1 + 1 or anchor.y1 > bounds.y1 + 1):
            return
        for text in legend.get_texts():
            text.set_fontsize(getattr(text, '_aquaprov_legend_fontsize', legend._fontsize))
        for _ in range(16):
            box = legend.get_window_extent(renderer)
            factor = min(1., bounds.width * .96 / max(box.width, 1),
                         bounds.height * .85 / max(box.height, 1))
            if factor >= .999:
                break
            for text in legend.get_texts():
                text.set_fontsize(text.get_fontsize() * max(.1, factor * .98))
        self.stale = False


class LegendLayoutEngine(ConstrainedLayoutEngine):
    """Measure keys before allocating margins, including during vector export."""
    def execute(self, figure):
        fit_figure_legend(figure, figure._get_renderer())
        return super().execute(figure)


class ManualLegendLayoutEngine(LayoutEngine):
    """Reserve outside space for fixed-layout figures, including Axes3D."""
    _adjust_compatible = True
    _colorbar_gridspec = False

    def __init__(self, figure):
        super().__init__()
        self.previous = figure.get_layout_engine()
        self.positions = {axis: axis.get_position(original=True).frozen() for axis in figure.axes}

    def restore(self, figure):
        for axis, bounds in self.positions.items():
            axis._set_position(bounds)
        figure.set_layout_engine(self.previous or 'none')

    def execute(self, figure):
        renderer = figure._get_renderer()
        fit_figure_legend(figure, renderer)
        legend = figure._aquaprov_style_outside_legend
        bounds = legend.get_window_extent(renderer)
        gap = figure.dpi * .20
        right = 1 - (bounds.width + gap) / figure.bbox.width if legend._outside_loc == 'right' else 1
        bottom = (bounds.height + gap) / figure.bbox.height if legend._outside_loc == 'lower' else 0
        for axis, base in self.positions.items():
            axis._set_position(Bbox.from_bounds(base.x0 * right, bottom + base.y0 * (1-bottom),
                                               base.width * right, base.height * (1-bottom)))


def finish_legend_position(figure, shared):
    if shared is None:
        return
    from matplotlib.legend import Legend
    for legend in figure.findobj(Legend):
        if legend is not shared:
            legend.set_visible(False)
            legend.set_in_layout(False)
    engine = figure.get_layout_engine()
    if isinstance(engine, ConstrainedLayoutEngine):
        prepare_legend_layout(figure)
    else:
        figure.set_layout_engine(ManualLegendLayoutEngine(figure))


def prepare_legend_layout(figure):
    engine = figure.get_layout_engine()
    if isinstance(engine, ConstrainedLayoutEngine) and not isinstance(engine, LegendLayoutEngine):
        figure.set_layout_engine(LegendLayoutEngine(**engine.get()))


def outside_legend(figure, *, max_columns=None):
    """One shared key in reserved page space, including multi-panel diagrams."""
    from .plot_legends import prepare_figure_legends
    prepare_figure_legends(figure)
    if getattr(figure, '_aquaprov_outside_legend', None) is not None:
        return
    entries = {}
    title = ''
    for axis in figure.axes:
        legend = axis.get_legend()
        if legend is None:
            continue
        title = title or legend.get_title().get_text()
        for label, handle in legend._aquaprov_entries.items():
            entries.setdefault(label, handle)
        legend.remove()
    if not entries:
        return
    width, height = figure.get_size_inches()
    columns = max(1, min(len(entries), int(width * 72 / (40 + max(map(len, entries)) * 5.5))))
    if max_columns is not None:
        columns = min(columns, max_columns)
    rows = math.ceil(len(entries) / columns)
    columns = math.ceil(len(entries) / rows)
    # Preserve a useful plot area even for one legend entry per sample.
    if rows > 3:
        figure.set_size_inches(width, height + (rows - 3) * .22, forward=False)
    legend = figure.legend(list(entries.values()), list(entries), title=title or None,
                           loc='outside lower center', ncols=columns, frameon=False,
                           fontsize=9, handletextpad=.65, columnspacing=1.5, labelspacing=.5)
    figure._aquaprov_outside_legend = legend
    legend._aquaprov_entries = entries
    figure._aquaprov_legend_rows = rows
    prepare_legend_layout(figure)


class PointLabelLayout(Artist):
    """Position labels in display space before drawing, including 3D rotation.

    The leader endpoints remain at the true measurements. Label rectangles are
    kept inside the plot and avoid earlier labels and the other measured points.
    """
    def __init__(self, axis, coordinates, labels, *, colors=None, fontsize=8, fit=False):
        super().__init__()
        self.axis = axis
        self.coordinates = np.asarray(coordinates, dtype=float)
        self.labels = []
        self.fit = fit
        self.set_zorder(2.5)
        self.set_in_layout(False)
        for i, label in enumerate(labels):
            color = colors[i] if colors is not None else '#26394d'
            annotation = axis.annotate(str(label), (0, 0), xytext=(6, 6),
                                       textcoords='offset points', ha='center', va='center',
                                       fontsize=fontsize, color=color, annotation_clip=True,
                                       arrowprops=dict(arrowstyle='-', color=color, lw=.55),
                                       zorder=5)
            annotation.set_in_layout(False)
            if fit:
                annotation._aquaprov_point_fontsize = fontsize
            self.labels.append(annotation)
        axis.add_artist(self)

    def draw(self, renderer):
        if not self.fit:
            self._place(renderer)
            return
        # Long labels in a small map may need smaller type as well as new
        # positions. Re-evaluate at every preview/export size; retain the
        # requested font so enlarging the page restores it.
        for factor in (1., .88, .76, .64, .52, .40):
            for text in self.labels:
                text.set_fontsize(max(4., text._aquaprov_point_fontsize * factor))
            self._place(renderer)
            boxes = [Text.get_window_extent(t, renderer).padded(1)
                     for t in self.labels if t.get_visible()]
            bounds = self.axis.bbox
            if (all(bounds.contains(b.x0,b.y0) and bounds.contains(b.x1,b.y1) for b in boxes)
                    and not any(a.overlaps(b) for i,a in enumerate(boxes) for b in boxes[i+1:])):
                break

    def _place(self, renderer):
        coordinates = self.coordinates
        if coordinates.shape[1] == 3:
            from mpl_toolkits.mplot3d import proj3d
            x, y, _ = proj3d.proj_transform(*coordinates.T, self.axis.get_proj())
            coordinates = np.column_stack((x, y))
        points = self.axis.transData.transform(coordinates[:, :2])
        bounds = self.axis.bbox.padded(-4)
        placed = []
        for artist in self.axis.artists:
            if not artist.get_visible():
                continue
            if getattr(artist, '_aquaprov_draggable', False) and getattr(artist, '_bounds', None) is not None:
                placed.append(artist._bounds.padded(5))
            if isinstance(artist, ContourLabelLayout) and not artist.prefer_points:
                placed.extend(text.get_window_extent(renderer).padded(3)
                              for text in artist.labels if text.get_visible())
        scale = renderer.points_to_pixels(1)
        for annotation, xy, anchor in zip(self.labels, coordinates, points):
            visible = bool(annotation.get_text()) and np.isfinite(anchor).all() and self.axis.bbox.contains(*anchor)
            annotation.set_visible(visible)
            if not visible:
                continue
            annotation.xy = tuple(xy[:2])
            annotation.set_position((0, 0))
            size = Text.get_window_extent(annotation, renderer)
            width, height = size.width + 5, size.height + 4
            best = None
            def candidate(offset, distance):
                center = anchor + offset * scale
                box = Bbox.from_bounds(center[0]-width/2, center[1]-height/2, width, height)
                outside = max(0, bounds.x0-box.x0) + max(0, box.x1-bounds.x1) + max(0, bounds.y0-box.y0) + max(0, box.y1-bounds.y1)
                collisions = sum(box.overlaps(other) for other in placed)
                on_points = np.sum((points[:, 0] > box.x0) & (points[:, 0] < box.x1) &
                                   (points[:, 1] > box.y0) & (points[:, 1] < box.y1))
                return outside * 10000 + collisions * 1000 + on_points * 1000 + distance, offset, box
            for radius in (10, 17, 26, 38, 54, 74, 100, 135):
                for angle in (45, 135, -45, -135, 90, -90, 0, 180):
                    offset = radius * np.array([np.cos(np.deg2rad(angle)), np.sin(np.deg2rad(angle))])
                    option = candidate(offset, radius)
                    if best is None or option[0] < best[0]:
                        best = option
                if best[0] <= radius:
                    break
            if best[0] >= 1000 and width < bounds.width and height < bounds.height:
                # Edge samples with long labels may need more than a radial
                # offset. Search free page space while retaining the true
                # sample as the leader endpoint, including after 3D rotation.
                for x in np.linspace(bounds.x0+width/2, bounds.x1-width/2, 9):
                    for y in np.linspace(bounds.y0+height/2, bounds.y1-height/2, 9):
                        offset = (np.array([x,y])-anchor)/scale
                        option = candidate(offset, np.linalg.norm(offset))
                        if option[0] < best[0]:
                            best = option
            annotation.set_position(tuple(best[1]))
            placed.append(best[2])
        self.stale = False


def point_labels(axis, coordinates, labels, **options):
    return PointLabelLayout(axis, coordinates, labels, **options)


class ContourLabelLayout(Artist):
    """Thin colliding contour labels; retained labels stay on their contours."""
    def __init__(self, axis, labels, *, prefer_points=False):
        super().__init__()
        self.axis, self.labels = axis, list(labels)
        self.prefer_points = prefer_points
        self.set_zorder(2.6 if prefer_points else 2.5)
        self.set_in_layout(False)
        for text in self.labels:
            text.set_in_layout(False)
        axis.add_artist(self)

    def draw(self, renderer):
        occupied = []
        if self.prefer_points:
            # Place observed-sample labels first, then thin contour labels.
            # Dense contours must not force measured sample IDs to overlap.
            for artist in self.axis.artists:
                if isinstance(artist, PointLabelLayout):
                    for text in artist.labels:
                        if text.get_visible():
                            text.update_positions(renderer)
                            occupied.append(Text.get_window_extent(text,renderer).padded(3))
        bounds = self.axis.bbox.padded(-3)
        for text in self.labels:
            text.set_visible(True)
            box = text.get_window_extent(renderer).padded(3)
            visible = (bounds.contains(box.x0, box.y0) and bounds.contains(box.x1, box.y1)
                       and not any(box.overlaps(other) for other in occupied))
            clip = text.get_clip_path()
            if visible and clip is not None:
                corners = [(box.x0, box.y0), (box.x0, box.y1), (box.x1, box.y0), (box.x1, box.y1)]
                visible = clip.get_fully_transformed_path().contains_points(corners).all()
            text.set_visible(visible)
            if visible:
                occupied.append(box)
        self.stale = False


class BoundedTextLayout(Artist):
    """Fit reference text around fixed anchors inside a compact plot box."""
    def __init__(self, axis, labels):
        super().__init__()
        self.axis, self.labels = axis, list(labels)
        for text in self.labels:
            text._aquaprov_bounded_fontsize = text.get_fontsize()
        self.set_zorder(2.5)
        self.set_in_layout(False)
        axis.add_artist(self)

    def draw(self, renderer):
        box = self.axis.bbox.padded(-renderer.points_to_pixels(2))
        for text in self.labels:
            text.set_fontsize(text._aquaprov_bounded_fontsize)
            anchor = text.get_transform().transform(text.get_position())
            width = 2*max(1, min(anchor[0]-box.x0, box.x1-anchor[0]))
            height = 2*max(1, min(anchor[1]-box.y0, box.y1-anchor[1]))
            for _ in range(4):
                bounds = text.get_window_extent(renderer)
                factor = min(1., width/max(bounds.width, 1), height/max(bounds.height, 1))
                if factor >= .999:
                    break
                text.set_fontsize(text.get_fontsize()*factor*.98)
        self.stale = False


class CellTextLayout(Artist):
    """Keep every heatmap number inside its own cell after font/size changes."""
    def __init__(self, axis, rows, columns):
        super().__init__()
        self.axis, self.rows, self.columns = axis, rows, columns
        self.labels = list(axis.texts)
        for text in self.labels:
            text._aquaprov_cell_fontsize = text.get_fontsize()
        self.set_zorder(2.5)
        self.set_in_layout(False)
        axis.add_artist(self)

    def draw(self, renderer):
        width = self.axis.bbox.width / self.columns * .88
        height = self.axis.bbox.height / self.rows * .80
        for text in self.labels:
            requested = text._aquaprov_cell_fontsize
            text.set_fontsize(requested)
            box = text.get_window_extent(renderer)
            factor = min(1., width / max(box.width, 1), height / max(box.height, 1))
            text.set_fontsize(requested * factor)
        self.stale = False


class TickLabelLayout(Artist):
    """Fit dense category IDs without omitting, abbreviating or moving any ID."""
    def __init__(self, axis, dimension='y'):
        super().__init__()
        self.axis = axis
        self.dimension = dimension
        for text in getattr(axis, 'get_' + dimension + 'ticklabels')():
            text._aquaprov_tick_fontsize = text.get_fontsize()
        self.set_zorder(.5)  # Update before the axis draws its ticks.
        self.set_in_layout(False)
        axis.add_artist(self)

    def draw(self, renderer):
        labels = getattr(self.axis, 'get_' + self.dimension + 'ticklabels')()
        locations = getattr(self.axis, 'get_' + self.dimension + 'ticks')()
        if len(locations) < 2:
            return
        coordinates = np.column_stack((np.zeros(len(locations)), locations))
        if self.dimension == 'x':
            coordinates = coordinates[:, ::-1]
        display = self.axis.transData.transform(coordinates)[:, 0 if self.dimension=='x' else 1]
        spacing = np.min(np.abs(np.diff(display))) * .88
        for text in labels:
            requested = getattr(text, '_aquaprov_tick_fontsize', text.get_fontsize())
            text.set_fontsize(requested)
            # Raster font hinting is not linear at very small sizes; measure
            # again instead of assuming a single scale factor is sufficient.
            for _ in range(6):
                box = text.get_window_extent(renderer)
                extent = box.width if self.dimension=='x' else box.height
                if extent <= spacing or text.get_fontsize() <= 1:
                    break
                text.set_fontsize(text.get_fontsize() * spacing / extent * .97)
        self.stale = False
