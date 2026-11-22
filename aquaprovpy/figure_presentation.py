"""Shared plot headings and colour scales for previews and exports."""
import re
from itertools import product

import numpy as np

from matplotlib.artist import Artist
from matplotlib.transforms import Bbox


def _visible_plot_box(axis):
    """Figure coordinates of a 2D plot or the projected 3D coordinate box."""
    if not hasattr(axis, 'get_proj'):
        return axis.get_position()
    from mpl_toolkits.mplot3d import proj3d
    corners = np.array(list(product(axis.get_xlim(), axis.get_ylim(), axis.get_zlim())))
    x, y, _ = proj3d.proj_transform(*corners.T, axis.get_proj())
    display = axis.transData.transform(np.column_stack((x, y)))
    points = axis.figure.transFigure.inverted().transform(display)
    if not np.isfinite(points).all():
        return axis.get_position()
    return Bbox.from_extents(*points.min(axis=0), *points.max(axis=0))


def prepare_figure_title(figure, default_title='', *, sample=None):
    """Choose one main heading, retaining panel titles and sample provenance."""
    if hasattr(figure, '_aquaprov_heading'):
        return
    panels = [axis for axis in figure.axes
              if axis.get_label() != '<colorbar>' and not hasattr(axis, '_colorbar')
              and (axis.axison or getattr(axis, '_axis3don', False))]
    # Twin axes are one plot; a multi-panel plot needs an overall heading.
    boxes = {tuple(axis.get_position(original=True).bounds) for axis in panels}
    if figure._suptitle is not None and figure._suptitle.get_text():
        heading = figure._suptitle
    elif getattr(figure, '_aquaprov_overall_heading', False):
        heading = figure.suptitle(default_title)
    elif panels and len(boxes) == 1:
        axis = next((axis for axis in panels if axis.get_title()), panels[0])
        heading = axis.title
        if sample is not None:
            heading.set_text(f'{default_title} · {sample}')
        elif not heading.get_text():
            heading.set_text(default_title)
    else:
        heading = figure.suptitle(default_title)
    figure._aquaprov_heading = heading
    figure._aquaprov_title_font = heading.get_fontproperties().copy()
    figure._aquaprov_title_position = (heading.get_position()[0], heading.get_horizontalalignment())
    figure._aquaprov_default_title = heading.get_text()
    count = re.search(r' · n = \d+$', heading.get_text())
    figure._aquaprov_title_suffix = f' · {sample}' if sample is not None else count.group() if count else ''


def apply_figure_title(figure, style):
    prepare_figure_title(figure)
    heading = figure._aquaprov_heading
    text = style.title.strip()
    if text:
        suffix = figure._aquaprov_title_suffix
        if suffix and not text.endswith(suffix):
            text += suffix
    else:
        text = figure._aquaprov_default_title
    heading.set_text(text)
    heading.set_fontsize(style.title_size)
    heading.set_color(style.text_color)
    if style.font_family != 'Original':
        heading.set_fontfamily(style.font_family)
    original_font = figure._aquaprov_title_font
    weight = style.font_weight if style.font_family != 'Original' else original_font.get_weight()
    font_style = style.font_style if style.font_family != 'Original' else original_font.get_style()
    heading.set_fontweight(weight if style.title_weight == 'Original' else style.title_weight)
    heading.set_fontstyle(font_style if style.title_style == 'Original' else style.title_style)
    if style.title_position == 'Original':
        x, alignment = figure._aquaprov_title_position
    else:
        alignment = style.title_position.lower()
        # Axes headings align with the plot edges; overall headings keep a
        # small page margin. Keep y unchanged so automatic layout still works.
        margin = .02 if heading is figure._suptitle else 0.
        x = {'left': margin, 'center': .5, 'right': 1. - margin}[alignment]
    heading.set_x(x)
    heading.set_horizontalalignment(alignment)


def _three_d_decoration_box(axis, renderer):
    """Include projected ticks and labels, which Axes3D's tight box omits."""
    boxes = [_visible_plot_box(axis).transformed(axis.figure.transFigure)]
    for component in (axis.xaxis, axis.yaxis, axis.zaxis):
        bounds = component.get_tightbbox(renderer)
        if bounds is not None:
            boxes.append(bounds)
        if component.label.get_visible() and component.label.get_text():
            boxes.append(component.label.get_window_extent(renderer))
    return Bbox.union(boxes)


class _ThreeDColorbarLayout(Artist):
    """Reserve room for a right-hand scale before painting the 3D axes."""
    def __init__(self, colorbar, parent):
        super().__init__()
        self.colorbar, self.parent = colorbar, parent
        self.set_zorder(-1000)
        self.set_in_layout(False)

    def draw(self, renderer):
        axis = self.parent
        # Tight export freezes each axes with a locator after measuring it.
        # Keep that allocation during the cropped render.
        if axis.get_axes_locator() is not None:
            return
        base = axis.get_subplotspec().get_position(self.figure)
        # Start from the requested margins on every draw: repeated styling,
        # rotation, export and hiding the scale must not progressively shrink it.
        axis._set_position(base)
        if not self.colorbar.ax.get_visible():
            return
        # transFigure retains the full page during a tight-cropped export.
        page = Bbox.unit().transformed(self.figure.transFigure)
        for _ in range(6):
            # 3D text positions are known only after projection. Measure without
            # painting so translucent surfaces are still rendered just once.
            with renderer._draw_disabled():
                axis.draw(renderer)
                self.colorbar.ax.draw(renderer)
            bounds = self.colorbar.ax.get_tightbbox(renderer)
            overflow = (bounds.x1 + renderer.points_to_pixels(3) - page.x1) / page.width
            if overflow <= .0001:
                break
            current = axis.get_position(original=True)
            width = max(base.width * .25, current.width - overflow)
            if width >= current.width:
                break
            axis._set_position(Bbox.from_bounds(base.x0, base.y0, width, base.height))
        self.stale = False


class _AlignedColorbarLocator:
    """Measure the parent plot at draw time, including resize and camera changes."""
    def __init__(self, colorbar, parents):
        self.colorbar = colorbar
        self.parents = parents
        self.original = colorbar.ax.get_axes_locator()

    def __call__(self, axis, renderer):
        if renderer is None and hasattr(axis, '_aquaprov_3d_colorbar_layout'):
            return axis.get_position()
        placement = getattr(axis, '_aquaprov_colorbar_placement', {})
        info = getattr(axis, '_colorbar_info', {})
        if placement and info:
            # Matplotlib stores pad/fraction relative to the parent allocation.
            # Recompute them from points after resizing or changing export size.
            parent_box = Bbox.union([p.get_position(original=True) for p in self.parents])
            vertical = self.colorbar.orientation == 'vertical'
            inches = parent_box.width * axis.figure.get_figwidth() if vertical else parent_box.height * axis.figure.get_figheight()
            if inches > 0:
                info['pad'] = placement.get('gap', 6) / 72 / inches
                info['fraction'] = placement.get('width', 6) / 72 / inches
        allocated = (self.original(axis, renderer) if self.original is not None
                     else axis.get_position(original=True))
        boxes = []
        for parent in self.parents:
            locator = parent.get_axes_locator()
            parent.apply_aspect(locator(parent, renderer) if locator is not None else None)
            boxes.append(_visible_plot_box(parent))
        plot = Bbox.union(boxes)
        # Include extension triangles in the total length, so even scales with
        # extend='both' end at the plot edges instead of protruding beyond them.
        outline = self.colorbar.outline.get_path().get_extents()
        width, height = axis.figure.get_size_inches()
        aspect = getattr(axis, '_colorbar_info', {}).get('aspect', 20)
        axis.set_box_aspect(None)
        fraction, anchor = placement.get('length',1.), placement.get('anchor',.5)
        if self.colorbar.orientation == 'vertical':
            length = plot.height * fraction / outline.height
            thickness = placement['width']/72/width if placement else min(allocated.width, plot.height * height / width / aspect)
            left = allocated.x0
            if hasattr(axis, '_aquaprov_3d_colorbar_layout'):
                decorations = _three_d_decoration_box(self.parents[0], renderer)
                left = axis.figure.transFigure.inverted().transform(
                    (decorations.x1 + renderer.points_to_pixels(6), 0))[0]
            return Bbox.from_bounds(left, plot.y0 + plot.height*(1-fraction)*anchor - outline.y0 * length, thickness, length)
        length = plot.width * fraction / outline.width
        thickness = placement['width']/72/height if placement else min(allocated.height, plot.width * width / height / aspect)
        return Bbox.from_bounds(plot.x0 + plot.width*(1-fraction)*anchor - outline.x0 * length, allocated.y0, length, thickness)

    def get_subplotspec(self):
        if hasattr(self.original, 'get_subplotspec'):
            return self.original.get_subplotspec()
        return self.colorbar.ax.get_subplotspec()


def align_figure_colorbars(figure):
    for axis in figure.axes:
        colorbar = getattr(axis, '_colorbar', None)
        parents = getattr(axis, '_colorbar_info', {}).get('parents', []) or getattr(axis, '_aquaprov_colorbar_parents', [])
        # Explicit dividers need the same extension-triangle correction.
        if colorbar is None or not parents or isinstance(axis.get_axes_locator(), _AlignedColorbarLocator):
            continue
        axis.set_axes_locator(_AlignedColorbarLocator(colorbar, parents))
        if (len(parents) == 1 and hasattr(parents[0], 'get_proj')
                and parents[0].get_subplotspec() is not None
                and getattr(axis, '_colorbar_info', {}).get('location') == 'right'
                and not hasattr(axis, '_aquaprov_colorbar_placement')
                and figure.get_layout_engine() is None):
            layout = _ThreeDColorbarLayout(colorbar, parents[0])
            axis._aquaprov_3d_colorbar_layout = layout
            figure.add_artist(layout)
