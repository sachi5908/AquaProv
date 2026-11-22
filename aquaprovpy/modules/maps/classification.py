"""Reproducible map class thresholds, independent of scientific predictions."""
import numpy as np


def display_classes(values, config, default_bounds):
    """Preserve each module's legacy scale unless display classes are selected."""
    method = config.get('classification', 'automatic')
    if method == 'automatic':
        edges = np.asarray(default_bounds)
        metadata = {'method': method, 'algorithm': 'module automatic scale', 'class_count': len(edges)-1}
    else:
        edges, metadata = class_boundaries(values, config.get('levels', 12), method, config.get('class_breaks'))
    return edges, dict(metadata, boundaries=edges.tolist())


def class_table(metadata):
    import pandas as pd
    edges = np.asarray(metadata['boundaries'])
    return pd.DataFrame({'class': np.arange(1, len(edges)), 'lower': edges[:-1], 'upper': edges[1:]})


def _jenks(values, classes, max_bins=512):
    unique, counts = np.unique(values, return_counts=True)
    if len(unique) <= max_bins:
        centers, upper = unique, unique
        algorithm = 'Jenks optimal partition of unique values'
    else:
        hist, edges = np.histogram(values, bins=max_bins)
        keep = hist > 0
        centers = ((edges[:-1] + edges[1:]) / 2)[keep]
        upper, counts = edges[1:][keep], hist[keep]
        algorithm = f'Jenks optimal partition of a {max_bins}-bin histogram (approximation)'
    classes = min(classes, len(centers))
    # Translation/scaling avoids cancellation for large offsets or tiny units.
    centers = (centers - values.min()) / np.ptp(values)
    w = np.r_[0., np.cumsum(counts)]
    s = np.r_[0., np.cumsum(counts * centers)]
    q = np.r_[0., np.cumsum(counts * centers**2)]
    n = len(counts)
    cost = np.full((classes + 1, n + 1), np.inf)
    starts = np.zeros((classes + 1, n + 1), dtype=int)
    cost[0, 0] = 0
    for k in range(1, classes + 1):
        for end in range(k, n + 1):
            candidate = np.arange(k - 1, end)
            error = q[end] - q[candidate] - (s[end] - s[candidate])**2 / (w[end] - w[candidate])
            options = cost[k - 1, candidate] + np.maximum(error, 0)
            best = int(np.argmin(options))
            cost[k, end] = options[best]
            starts[k, end] = candidate[best]
    breaks, end = [], n
    for k in range(classes, 1, -1):
        end = starts[k, end]
        # Midpoints avoid an empty first class when its only value is the minimum.
        breaks.append(float((upper[end - 1] + unique[np.searchsorted(unique, upper[end - 1], side='right')]) / 2)
                      if algorithm.startswith('Jenks optimal partition of unique') else float(upper[end - 1]))
    return np.r_[values.min(), sorted(breaks), values.max()], algorithm


def class_boundaries(values, levels=12, method='automatic', explicit=None):
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        raise ValueError('No finite predictions are available for classification.')
    if not np.isscalar(levels):
        explicit, method = levels, 'custom'
    if method == 'custom':
        try:
            edges = np.asarray([float(v.strip()) for v in explicit.split(',')]
                               if isinstance(explicit, str) else explicit, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError('Enter at least two increasing class boundaries separated by commas.') from exc
        if edges.ndim != 1 or len(edges) < 2 or not np.isfinite(edges).all() or (np.diff(edges) <= 0).any():
            raise ValueError('Class boundaries must be finite, strictly increasing numbers (at least two).')
        return edges, {'method': method, 'algorithm': 'user-specified boundaries', 'class_count': len(edges)-1}
    if isinstance(levels, bool) or not isinstance(levels, (int, np.integer)) or not 2 <= levels <= 40:
        raise ValueError('Choose between 2 and 40 colour classes.')
    low, high = float(finite.min()), float(finite.max())
    if method not in ('automatic', 'equal_interval', 'quantile', 'natural_breaks'):
        raise ValueError('Choose automatic contours, equal intervals, quantiles, natural breaks or custom boundaries.')
    if low == high:
        pad = max(abs(low) * 1e-6, 1e-9)
        edges, algorithm = np.array([low-pad, high+pad]), 'constant field; one display band'
    elif method == 'automatic':
        from matplotlib.ticker import MaxNLocator
        edges, algorithm = MaxNLocator(nbins=levels).tick_values(low, high), 'Matplotlib MaxNLocator'
    elif method == 'equal_interval':
        edges, algorithm = np.linspace(low, high, levels+1), 'equal width'
    elif method == 'quantile':
        edges = np.unique(np.quantile(finite, np.linspace(0, 1, levels+1)))
        algorithm = 'quantiles; repeated boundaries merged'
    else:
        edges, algorithm = _jenks(finite, levels)
    return edges, {'method': method, 'algorithm': algorithm, 'class_count': len(edges)-1,
                   'requested_class_count': int(levels)}
