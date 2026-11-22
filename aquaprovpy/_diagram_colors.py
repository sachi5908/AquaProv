"""Numeric sample colors and labels shared by geochemical renderers."""

import numpy as np
import pandas as pd
from matplotlib import colormaps
from matplotlib.colors import Normalize
from matplotlib.collections import PathCollection
from matplotlib.legend_handler import HandlerPathCollection
from .core.progress import report_progress, check_cancelled


def color_label(frame):
    """Read the colour label from provenance; default to 'Color value'."""
    label = frame.attrs.get('color_label')
    if not label or label == '(single color)':
        return 'Color value'
    original = frame.attrs.get('aquaprov', {}).get('original_headers', {})
    return str(original.get(label, label))


def numeric_colors(frame):
    if not pd.api.types.is_numeric_dtype(frame['Color']):
        return None
    values = frame['Color'].to_numpy(dtype=float)
    if not len(values) or not np.isfinite(values).all():
        raise ValueError('Numeric sample colors must be finite and non-empty.')
    return dict(values=values, norm=Normalize(values.min(), values.max()), cmap=colormaps['viridis'])


def scatter_color(frame, position, mapping):
    if mapping is None:
        return {'color': frame['Color'].iloc[position]}
    return {'c': [mapping['values'][position]], 'norm': mapping['norm'], 'cmap': mapping['cmap']}


class _SampleLegendHandler(HandlerPathCollection):
    """A single 2D key represents a batch, including a 3D batch."""
    def create_collection(self, orig_handle, sizes, offsets, offset_transform):
        return PathCollection([orig_handle.get_paths()[0]], sizes=sizes,
                              offsets=offsets, offset_transform=offset_transform)

    def update_prop(self, legend_handle, orig_handle, legend):
        # Copy only the representative style. update_from copies a whole
        # batch's alpha array, which older Matplotlib cannot reset to a scalar.
        legend_handle.set_facecolor(orig_handle.get_facecolor()[:1])
        legend_handle.set_edgecolor(orig_handle.get_edgecolor()[:1])
        legend_handle.set_linewidth(orig_handle.get_linewidth()[:1])
        legend_handle.set_linestyle(orig_handle.get_linestyle()[:1])
        legend_handle.set_cmap(orig_handle.get_cmap())
        legend_handle.set_norm(orig_handle.norm)
        values = orig_handle.get_array()
        legend_handle.set_array(None if values is None else values[:1])
        alpha = orig_handle.get_alpha()
        legend_handle.set_alpha(None if alpha is None else float(np.asarray(alpha).ravel()[0]))
        legend._set_artist_props(legend_handle)
        legend_handle.set_clip_box(None)
        legend_handle.set_clip_path(None)


def sample_legend(axis, *args, **kwargs):
    """Use one representative sample per legend entry, never an entire batch."""
    return axis.legend(*args, handler_map={PathCollection: _SampleLegendHandler()}, **kwargs)


def sample_batches(frame, batch_size=512, *, split_alpha=False):
    """Yield bounded, consecutive runs with one marker and legend label."""
    markers = frame['Marker'].astype(str).to_numpy()
    labels = frame['Label'].fillna('').astype(str).to_numpy()
    alphas = frame['Alpha'].to_numpy() if split_alpha else None
    start = 0
    while start < len(frame):
        check_cancelled()
        stop = start + 1
        while (stop < min(start + batch_size, len(frame)) and
               markers[stop] == markers[start] and labels[stop] == labels[start] and
               (alphas is None or alphas[stop] == alphas[start])):
            stop += 1
        yield start, stop, markers[start], labels[start]
        start = stop


def scatter_panels(axis, frame, panels, *, legend_panel=1, batch_size=512,
                   masks=None, color_mapping=None, **scatter_options):
    """Plot every sample in bounded batches, preserving source draw order.

    A contiguous run shares its marker and legend group; size, alpha and color
    remain per-sample arrays. No averaging, thinning or measurement changes.
    """
    mapping = numeric_colors(frame) if color_mapping is None else color_mapping
    sizes = frame['Size'].to_numpy(dtype=float)
    alphas = frame['Alpha'].to_numpy(dtype=float)
    if not np.isfinite(sizes).all() or (sizes <= 0).any():
        raise ValueError('Marker Size must be finite and positive.')
    if not np.isfinite(alphas).all() or ((alphas < 0) | (alphas > 1)).any():
        raise ValueError('Marker Alpha must be between 0 and 1.')
    colors = frame['Color'].to_numpy()
    panels = [tuple(np.asarray(c) for c in coordinates) for coordinates in panels]
    if masks is None:
        masks = [np.ones(len(frame), dtype=bool) for _ in panels]
    masks = [np.asarray(mask, dtype=bool) & np.isfinite(np.column_stack(coords)).all(axis=1)
             for coords, mask in zip(panels, masks)]
    options = {'edgecolors': 'black', **scatter_options}
    seen, artists = set(), []
    # Matplotlib sorts 3D colors by depth but not array-valued alpha. Runs with
    # scalar alpha preserve each point's opacity through camera changes.
    is_3d = any(len(c) == 3 for c in panels)
    for start, stop, marker, group in sample_batches(frame, batch_size, split_alpha=is_3d):
        group = group or 'Samples'
        for index, coordinates in enumerate(panels):
            positions = np.arange(start, stop)[masks[index][start:stop]]
            if not len(positions):
                continue
            color = ({'c': mapping['values'][positions], 'norm': mapping['norm'], 'cmap': mapping['cmap']}
                     if mapping is not None else {'c': colors[positions]})
            show_label = legend_panel is None or index == legend_panel
            label = group if show_label and group and group not in seen else '_nolegend_'
            artist = axis.scatter(*(c[positions] for c in coordinates), marker=marker,
                s=sizes[positions], alpha=float(alphas[start]) if is_3d else alphas[positions],
                label=label, **options, **color)
            artist._aquaprov_sample_positions = positions
            artist._aquaprov_panel_index = index
            artists.append(artist)
            if show_label:
                seen.add(group)
        report_progress(15 + 65 * stop / len(frame), f'Plotting samples: {stop:,} / {len(frame):,}')
    return artists
