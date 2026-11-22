"""Perpendicular XYZ guides that preserve the data's plotted coordinate range."""
import numpy as np
from matplotlib.colors import to_rgba_array
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d.art3d import Line3DCollection


class CoordinateGuides(Line3DCollection):
    def __init__(self, points, *, colors=None, values=None, cmap=None, norm=None):
        self.points = np.asarray(points, dtype=float).copy()
        line_colors = None if colors is None else np.repeat(to_rgba_array(colors), 3, axis=0)
        super().__init__([], colors=line_colors, linewidths=.6, alpha=.35,
                         linestyles='--', label='_nolegend_')
        self.set_gid('aquaprov-coordinate-guides')
        if values is not None:
            self.set_array(np.repeat(np.asarray(values), 3))
            self.set_cmap(cmap)
            self.set_norm(norm)

    def update_segments(self):
        limits = (self.axes.get_xlim(), self.axes.get_ylim(), self.axes.get_zlim())
        segments = np.broadcast_to(self.points[:, None, None, :], (len(self.points), 3, 2, 3)).copy()
        for dimension, bounds in enumerate(limits):
            segments[:, dimension, 1, dimension] = bounds[0]
        self.set_segments(segments.reshape(-1, 2, 3))

    def do_3d_projection(self):
        # Follow camera-independent axis limits after zooming, resetting or
        # exporting. Adding these lines must never autoscale the observations.
        self.update_segments()
        return super().do_3d_projection()


def add_coordinate_guides(axis, points, **kwargs):
    guides = CoordinateGuides(points, **kwargs)
    axis.add_collection(guides, autolim=False)
    guides.update_segments()
    axis.legend(handles=[Line2D([], [], color='#66788a', linestyle='--', linewidth=.8,
                               label='Coordinate guides')], loc='upper left', frameon=False)
    return guides
