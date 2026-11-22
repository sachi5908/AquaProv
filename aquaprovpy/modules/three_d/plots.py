"""XYZ scatter and piecewise-linear surfaces; no implicit coordinate conversion."""

import numpy as np
import pandas as pd
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import Delaunay, QhullError

from ..maps.interpolation import numeric_samples, validate_geometry
from .guides import add_coordinate_guides


def plot_xyz(frame, x, y, z, *, surface=False, resolution=65, surface_alpha=1.,
             show_samples=True, mesh_edges=False, marker='o', sample_size=40,
             sample_alpha=.8, sample_color='#203e54', projection='persp', show_origin_lines=True):
    """Plot XYZ measurements, with optional coordinate guides.

    The show_origin_lines argument retains its earlier name for compatibility.
    """
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from matplotlib.ticker import MaxNLocator
    from matplotlib.tri import Triangulation, LinearTriInterpolator, UniformTriRefiner
    from ..._publication import PlotResult
    values = numeric_samples(frame, [x, y, z], minimum=3 if surface else 1)
    if surface:
        validate_geometry(values[:, :2])
    if not isinstance(resolution, int) or not 20 <= resolution <= 160:
        raise ValueError('Surface resolution must be between 20 and 160 cells per axis.')
    if projection not in ('persp', 'ortho'):
        raise ValueError('Choose perspective or orthographic projection.')
    if not np.isfinite([surface_alpha, sample_alpha, sample_size]).all() or not (
            0 <= surface_alpha <= 1 and 0 <= sample_alpha <= 1 and sample_size > 0):
        raise ValueError('Opacity must be between 0 and 1, and sample size must be positive.')
    # Axes3D bounding boxes change with the camera. Explicit margins avoid
    # constrained-layout collapse as the desktop viewport resizes.
    figure = plt.figure(figsize=(9, 6))
    figure.subplots_adjust(left=.02, right=.89, bottom=.10, top=.90)
    try:
        ax = figure.add_subplot(111, projection="3d")
        ax.set_proj_type(projection)
        samples = pd.DataFrame(values, columns=[x, y, z], index=frame.index.copy())
        if 'Sample' in frame and 'Sample' not in samples:
            samples.insert(0, 'Sample', frame['Sample'].to_numpy())
        tables = {"samples": samples}
        norm = Normalize(vmin=values[:, 2].min(), vmax=values[:, 2].max())
        if surface:
            try:
                triangulation = Delaunay(values[:, :2])
            except QhullError as exc:
                raise ValueError('The X/Y locations cannot form a stable surface. Check nearly collinear coordinates.') from exc
            gx, gy = np.meshgrid(np.linspace(values[:, 0].min(), values[:, 0].max(), resolution),
                                 np.linspace(values[:, 1].min(), values[:, 1].max(), resolution))
            gz = LinearNDInterpolator(triangulation, values[:, 2])(gx, gy)
            # A rectangular display grid can miss measured peaks and shrink the
            # hull. Refine the actual interpolation triangles linearly instead:
            # every observed vertex and every original triangle edge is retained.
            mesh = Triangulation(values[:, 0], values[:, 1], triangulation.simplices)
            subdivisions = max(0, int(np.log(max(1, resolution ** 2 / len(mesh.triangles))) / np.log(4)))
            mesh, mesh_z = UniformTriRefiner(mesh).refine_field(
                values[:, 2], triinterpolator=LinearTriInterpolator(mesh, values[:, 2]), subdiv=subdivisions)
            colored = ax.plot_trisurf(mesh, mesh_z, cmap="viridis", norm=norm,
                                      linewidth=.35 if mesh_edges else 0,
                                      edgecolor='#42576c' if mesh_edges else 'none', alpha=surface_alpha,
                                      antialiased=mesh_edges)
            from ...plot_legends import scale_legend
            scale_legend(ax, colored, 'Interpolated surface')
            if show_samples:
                ax.scatter(*values.T, color=sample_color, s=sample_size, marker=marker, alpha=sample_alpha, depthshade=False, label='Samples')
                if show_origin_lines:
                    add_coordinate_guides(ax, values, colors=sample_color)
            tables["surface_grid"] = pd.DataFrame({"x": gx.ravel(), "y": gy.ravel(), "z": gz.ravel()})
        else:
            colored = ax.scatter(*values.T, c=values[:, 2], cmap="viridis", s=sample_size, marker=marker,
                                 norm=norm, alpha=sample_alpha, edgecolor="white", linewidth=.5, depthshade=False, label='Samples')
            if show_origin_lines:
                add_coordinate_guides(ax, values, values=values[:, 2], cmap=colored.get_cmap(), norm=colored.norm)
        ax.set(xlabel=x, ylabel=y, zlabel=z, title="3D surface" if surface else "3D sample scatter")
        for component in (ax.xaxis, ax.yaxis, ax.zaxis):
            component.set_major_locator(MaxNLocator(nbins=5))
        figure.colorbar(colored, ax=ax, shrink=.65, pad=.1, label=z)
        return PlotResult(figure, tables, {"method": "piecewise-linear surface" if surface else "XYZ sample scatter",
            "n_used": len(values), "x_column": x, "y_column": y, "z_column": z,
            "coordinates": "source columns; no CRS conversion", "grid_resolution": resolution if surface else None,
            "color_scale": "Z measurement range", "color_limits": [float(norm.vmin), float(norm.vmax)],
            "surface_rendering": "linear refinement of sample Delaunay triangles" if surface else None,
            "appearance": {'surface_alpha': surface_alpha, 'show_samples': show_samples, 'mesh_edges': mesh_edges,
                           'marker': marker, 'sample_size': sample_size, 'sample_alpha': sample_alpha,
                           'sample_color': sample_color, 'projection': projection, 'show_origin_lines': show_origin_lines,
                           'guide_type': 'perpendicular to coordinate planes',
                           'guide_planes': 'first X, Y and Z view limits',
                           'guides_visible': bool(show_origin_lines and (not surface or show_samples))}},
            ["Piecewise-linear interpolation within the sample convex hull; no extrapolation. X and Y remain in source units."] if surface else [])
    except Exception:
        plt.close(figure)
        raise
