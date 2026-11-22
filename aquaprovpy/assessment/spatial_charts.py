"""Spatial diagnostics drawn from AquaProv's training-only validation tables.

Display choices never refit a model, regroup the wells or alter predictions.
"""
import numpy as np
import matplotlib.pyplot as plt

from .._publication import STYLE, PALETTE, GROUP_MARKERS


METHODS = (
    ('Kriging', 'prediction', '#087f8c', 'o'),
    ('IDW', 'idw_prediction', '#d55e00', '^'),
    ('Training mean', 'training_mean_prediction', '#6b7280', 's'),
)


def _measurement_label(tables, config):
    column = config['column']
    observations = tables.get('observations')
    if observations is not None and {'analyte', 'canonical_unit'} <= set(observations):
        units = observations.loc[observations.analyte.eq(column), 'canonical_unit'].dropna().unique()
        if len(units) == 1:
            return f'{column} ({units[0]})'
    return column


def spatial_chart(tables, config):
    name = config['chart']
    if name not in ('Validation blocks', 'Prediction comparison', 'Kriging intervals'):
        raise ValueError('Choose a supported spatial diagnostic chart.')
    data = tables['spatial_predictions'].sort_values('row', kind='stable')
    required = ['row', 'fold', 'observed', 'prediction', 'idw_prediction',
                'training_mean_prediction', 'lower_95', 'upper_95', 'x', 'y']
    if data.empty or data.row.duplicated().any() or not np.isfinite(data[required].to_numpy()).all():
        raise ValueError('Spatial diagnostics require one finite held-out prediction per source row.')
    if (data.lower_95 > data.prediction).any() or (data.prediction > data.upper_95).any():
        raise ValueError('Prediction interval bounds must enclose their predictions.')
    appearance = config.get('chart_appearance', {})
    size = config.get('chart_size', 24)
    label = _measurement_label(tables, config)
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(6.4, 4.8), layout='constrained')
        try:
            if name == 'Validation blocks':
                crs = tables['spatial_coordinate_system'].iloc[0].get('analysis_crs', 'local')
                from ..boundaries import geometry_in_crs, draw_boundary
                from ..modules.maps.cartography import decorate_map
                extent = [data.x.min(), data.y.min(), data.x.max(), data.y.max()]
                boundary = config.get('boundary')
                if boundary is not None:
                    area = geometry_in_crs(boundary, crs)
                    draw_boundary(ax, area)
                    xmin, ymin, xmax, ymax = area.bounds
                    extent = [min(extent[0], xmin), min(extent[1], ymin),
                              max(extent[2], xmax), max(extent[3], ymax)]
                for number, (fold, group) in enumerate(data.groupby('fold', sort=True)):
                    points = ax.scatter(group.x, group.y, s=size,
                                        color=PALETTE[number % len(PALETTE)],
                                        marker=GROUP_MARKERS[number % len(GROUP_MARKERS)],
                                        edgecolors='#243447', linewidths=.5,
                                        label=f'Block {int(fold)} (n = {len(group)})',
                                        alpha=appearance.get('alpha', 1), zorder=4)
                    points.set_gid(f'aquaprov-validation-block-{int(fold)}')
                dx, dy = max(extent[2]-extent[0], 1), max(extent[3]-extent[1], 1)
                ax.set(xlim=(extent[0]-.04*dx, extent[2]+.04*dx),
                       ylim=(extent[1]-.06*dy, extent[3]+.06*dy), aspect='equal',
                       xlabel='Analysis x', ylabel='Analysis y')
                ax.set_autoscale_on(False)
                decorate_map(ax, crs, north_arrow=config.get('north_arrow', False),
                             north_reference=config.get('north_reference', 'true'),
                             layout=config.get('map_layout'))
                ax.legend(loc='upper center', bbox_to_anchor=(.5, -.20), ncol=3,
                          frameon=False, fontsize=8)
            elif name == 'Prediction comparison':
                for method, column, color, marker in METHODS:
                    points = ax.scatter(data.observed, data[column], s=size, marker=marker,
                                        color=color, edgecolors='white', linewidths=.35,
                                        alpha=appearance.get('alpha', .85), label=method)
                    points.set_gid('aquaprov-predictions-'+column)
                values = data[['observed', *[m[1] for m in METHODS]]].to_numpy()
                low, high = float(values.min()), float(values.max())
                pad = max((high-low)*.05, 1.)
                limits = [min(0., low-pad), high+pad]
                ax.plot(limits, limits, ':', color='#334155', lw=1, label='1:1 line')
                ax.set(xlim=limits, ylim=limits, xlabel='Observed '+label,
                       ylabel='Held-out predicted '+label, aspect='equal')
                ax.legend(loc='upper left', frameon=False, fontsize=8)
            else:
                # Row order is explicit; negative Gaussian bounds stay visible.
                positions = np.arange(len(data))
                intervals = ax.errorbar(positions, data.prediction,
                                       yerr=[data.prediction-data.lower_95, data.upper_95-data.prediction],
                                       fmt='o', color='#087f8c', ecolor='#7bb4bc', markersize=np.sqrt(size),
                                       alpha=appearance.get('alpha', 1),
                                       linewidth=1, capsize=2, label='Kriging prediction and conditional 95% interval')
                intervals.lines[0].set_gid('aquaprov-interval-predictions')
                points = ax.scatter(positions, data.observed, s=size, marker='x',
                                    color='#b44722', alpha=appearance.get('alpha', 1),
                                    zorder=4, label='Held-out observation')
                points.set_gid('aquaprov-interval-observations')
                ax.axhline(0, color='#64748b', lw=.8, ls=':')
                ax.set(xlabel='Source data row', ylabel=label, xlim=(-1, len(data)))
                tick_positions = np.unique(np.linspace(0, len(data)-1, min(15, len(data)), dtype=int))
                ax.set_xticks(tick_positions, data.row.iloc[tick_positions].astype(str))
                ax.margins(y=.1)
                ax.legend(loc='upper center', bbox_to_anchor=(.5, 1.17), frameon=False, fontsize=8)
            ax.set_title(name)
            ax._aquaprov_source_rows = data.row.tolist()
            return fig
        except Exception:
            plt.close(fig)
            raise
