"""Fit legacy diagrams to the live figure as well as the exported page."""

import numpy as np
from matplotlib.artist import Artist
from matplotlib.text import Text
from matplotlib.transforms import Affine2D, ScaledTranslation


def _piper_panel_spacing(axis):
    """Separate the component panels without altering their ion coordinates."""
    gap = .18
    shifts = [(-gap, 0), (gap, 0), (0, gap*np.sqrt(3))]
    h = np.sqrt(3)/2
    for artist in [*axis.lines, *axis.patches]:
        points = artist.get_xydata() if hasattr(artist, 'get_xydata') else artist.get_xy()
        if np.max(points[:, 0]) <= 1.00001 and np.max(points[:, 1]) <= h+.00001:
            panel = 0
        elif np.min(points[:, 0]) >= 1.19999 and np.max(points[:, 1]) <= h+.00001:
            panel = 1
        else:
            panel = 2
        artist.set_transform(Affine2D().translate(*shifts[panel]) + axis.transData)
    for artist in axis.collections:
        panel = getattr(artist, '_aquaprov_panel_index', None)
        if panel is not None:
            artist.set_offset_transform(Affine2D().translate(*shifts[panel]) + axis.transData)
    axis.set(xlim=(-.32, 2.52), ylim=(-.16, 2.42))
    return [np.array(shift) for shift in shifts]


class _PiperLabelLayout(Artist):
    """Use physical label padding; data-unit offsets collapse on small pages."""

    def __init__(self, axis):
        super().__init__()
        self.axis = axis
        self.set_zorder(1)
        self.set_in_layout(False)
        shifts = _piper_panel_spacing(axis)
        h = np.sqrt(3) / 2
        self.labels = [text for text in axis.texts if text.get_text().startswith('%')]
        normals = [(0, -1), (h, .5), (-h, .5), (0, -1), (h, .5), (-h, .5),
                   (-h, .5), (h, -.5), (-h, -.5), (h, .5)]
        self.ticks = []
        for index, text in enumerate(t for t in axis.texts if t.get_text().isdigit()):
            normal = np.array(normals[index % 10])
            panel = (0, 0, 0, 1, 1, 1, 2, 2, 2, 2)[index % 10]
            self.ticks.append((text, np.array(text.get_position()) - .03*normal + shifts[panel], normal))
            text._aquaprov_piper_fontsize = text.get_fontsize()
            # The unlabelled lower diamond edges duplicate the upper scales.
            # Their numbers crowd the two triangle labels in the narrow gap.
            if index % 10 in (7, 8):
                text.set_visible(False)
        # Midpoints and outward normals of the six triangle edges and two
        # labelled diamond edges. Scientific sample coordinates stay intact.
        self.edges = [((.5, 0), (0, -1)), ((1.7, 0), (0, -1)),
                      ((.25, h/2), (-h, .5)), ((1.95, h/2), (h, .5)),
                      ((.75, h/2), (h, .5)), ((1.45, h/2), (-h, .5)),
                      ((.85, 1.5*h + .1*np.sqrt(3)), (-h, .5)),
                      ((1.35, 1.5*h + .1*np.sqrt(3)), (h, .5))]
        self.edges = [(np.array(point) + shifts[panel], normal)
                      for (point, normal), panel in zip(self.edges, (0, 1, 0, 1, 0, 1, 2, 2))]
        for label in self.labels:
            label._aquaprov_piper_fontsize = label.get_fontsize()

    def draw(self, renderer):
        ticks = [text for text, _, _ in self.ticks if text.get_visible()]
        edge_length = np.linalg.norm(self.axis.transData.transform((1, 0)) - self.axis.transData.transform((0, 0)))
        for text in ticks:
            text.set_fontsize(text._aquaprov_piper_fontsize)
            width = renderer.get_text_width_height_descent(text.get_text(), text.get_fontproperties(), False)[0]
            text.set_fontsize(text.get_fontsize()*min(1., .18*edge_length/max(width, 1)))
        tick_height = max((renderer.get_text_width_height_descent(
            text.get_text(), text.get_fontproperties(), False)[1] for text in ticks), default=0)
        tick_gap = renderer.points_to_pixels(1.5)
        for text, point, normal in self.ticks:
            text.set_position(point)
            distance = tick_height/2 + tick_gap
            text.set_transform(self.axis.transData + ScaledTranslation(
                normal[0]*distance/self.figure.dpi, normal[1]*distance/self.figure.dpi,
                self.figure.dpi_scale_trans))
        for label, (point, normal) in zip(self.labels, self.edges):
            # Measure the unrotated text: the normal extent of a label parallel
            # to its edge is its height, not its rotated bounding-box width.
            label.set_fontsize(label._aquaprov_piper_fontsize)
            probe = Text(text=label.get_text(), fontproperties=label.get_fontproperties())
            probe.set_figure(self.figure)
            bounds = probe.get_window_extent(renderer)
            factor = min(1., .9*edge_length/max(bounds.width, 1))
            label.set_fontsize(label.get_fontsize()*factor)
            height = bounds.height*factor
            distance = tick_gap + tick_height + height/2 + renderer.points_to_pixels(2)
            label.set_position(point)
            label.set_transform(self.axis.transData + ScaledTranslation(
                normal[0]*distance/self.figure.dpi, normal[1]*distance/self.figure.dpi,
                self.figure.dpi_scale_trans))
        self.stale = False


def prepare_diagram_layout(figure, module_name):
    """Reserve room for annotations without changing the plotted measurements.

    Legacy renderers rely on savefig's tight crop to include labels outside the
    page. The interactive canvas needs those labels inside the figure itself.
    Keep these presentation changes separate from the legacy calculations.
    """
    if getattr(figure, '_aquaprov_diagram_layout', None) == module_name:
        return
    figure._aquaprov_diagram_layout = module_name
    figure._aquaprov_overall_heading = module_name in (
        'triangle_piper', 'color_piper', 'contour_piper', 'durvo', 'chadha', 'hfed')
    if module_name == 'triangle_piper':
        figure.axes[0].add_artist(_PiperLabelLayout(figure.axes[0]))
    if module_name == 'gibbs':
        panels = [axis for axis in figure.axes if not hasattr(axis, '_colorbar')]
        if len(panels) == 2:
            # Both panels use the same TDS scale. Keep one set of y labels.
            panels[1].set_ylabel('')
            panels[1].tick_params(axis='y', labelleft=False)
    if module_name == 'gaillardet':
        panels = [axis for axis in figure.axes if axis.get_xlabel()]
        colorbars = [axis._colorbar for axis in figure.axes if hasattr(axis, '_colorbar')]
        # Recreate the optional colorbar under the new layout so it participates
        # in the same margin calculation as the two logarithmic panels.
        colorbar = colorbars[0] if colorbars else None
        if colorbar is not None:
            mappable, label = colorbar.mappable, colorbar.ax.get_ylabel()
            colorbar.remove()
        figure.set_size_inches(12, 6, forward=False)
        grid = figure.add_gridspec(1, 2)
        for column, axis in enumerate(panels):
            axis.set_subplotspec(grid[0, column])
        figure.set_layout_engine('constrained', w_pad=0.12, h_pad=0.12, wspace=0.08)
        if colorbar is not None:
            colorbar = figure.colorbar(mappable, ax=panels[1], extend='both',
                                      fraction=0.05, pad=0.04, label=label)
            colorbar.ax.tick_params(labelsize=10)
    elif module_name == 'stiff':
        figure.set_size_inches(5, 4, forward=False)
        # The six ion labels extend beyond the symmetric concentration axis.
        # Constrained layout measures them again on resize and style changes.
        figure.set_layout_engine('constrained', w_pad=0.12, h_pad=0.12)
    elif module_name == 'chernoff':
        face = figure.axes[0]
        figure.set_size_inches(6, 5, forward=False)
        # A pure Ca or Mg sample has a half-width of 1.25 in the legacy mapping.
        face.set(xlim=(-1.35, 1.35), ylim=(-1.35, 1.35))
        figure.set_layout_engine('constrained', w_pad=0.12, h_pad=0.12, wspace=0.06)
    elif module_name == 'hfed':
        axis = figure.axes[0]
        colorbars = [item._colorbar for item in figure.axes if hasattr(item, '_colorbar')]
        colorbar = colorbars[0] if colorbars else None
        if colorbar is not None:
            mappable, label = colorbar.mappable, colorbar.ax.get_xlabel()
            colorbar.remove()
        figure.set_size_inches(13, 8, forward=False)
        grid = figure.add_gridspec(1, 2, width_ratios=(1.8, 1))
        axis.set_subplotspec(grid[0, 0])
        facies = figure.add_subplot(grid[0, 1], label='Hydrochemical facies key')
        facies.set_axis_off()
        facies.set_navigate(False)
        # Keep the reference key on the page instead of outside the plot box.
        key = [text for text in axis.texts if text.get_position()[0] == 149]
        for index, annotation in enumerate(key):
            annotation.remove()
            annotation.set_transform(facies.transAxes)
            annotation.set_position((0, 0.9 - index * 0.048))
            facies.add_artist(annotation)
        figure.set_layout_engine('constrained', w_pad=0.12, h_pad=0.12, wspace=0.06)
        if colorbar is not None:
            figure.colorbar(mappable, ax=axis, orientation='horizontal',
                            extend='both', fraction=0.05, pad=0.04, label=label)
    else:
        # Old colorbars use nested grids meant for tight_layout. Recreate them
        # with the live layout engine so titles, scales and twin axes cooperate.
        scales = []
        for axis in list(figure.axes):
            cb = getattr(axis, '_colorbar', None)
            if cb is not None:
                scales.append((cb.mappable, cb.ax.get_ylabel() or cb.ax.get_xlabel(), cb.orientation, cb.extend))
                cb.remove()
        sizes = {'triangle_piper': (10, 8), 'color_piper': (10, 8), 'contour_piper': (10, 8),
                 'rectangle_piper': (15, 6), 'durvo': (12, 8), 'chadha': (9, 8), 'schoeller': (9, 6)}
        if module_name in sizes:
            figure.set_size_inches(*sizes[module_name], forward=False)
        figure.set_layout_engine('constrained', w_pad=.14, h_pad=.14,
                                 wspace=.035 if module_name == 'gibbs' else .12)
        parents = [axis for axis in figure.axes if axis.get_label() != '<colorbar>']
        for mappable, label, orientation, extend in scales:
            cb = figure.colorbar(mappable, ax=parents, orientation=orientation,
                                 label=label, extend=extend, fraction=.035, pad=.055)
            cb.ax.yaxis.labelpad = 8
            cb.ax.xaxis.labelpad = 8
    if module_name == 'contour_piper':
        from ..plot_legends import scale_legend
        axis = figure.axes[0]
        scale_legend(axis, axis.collections[0], 'Sample density')
    from ..plot_layout import outside_legend
    outside_legend(figure)
