"""Individual assessment charts using the same recalculated assessment tables."""
import numpy as np
import matplotlib.pyplot as plt

CHARTS = {'qa': ['Dashboard', 'Charge balance'],
          'uncertainty': ['Dashboard', 'SAR intervals', 'Na percent intervals'],
          'spatial': ['Dashboard', 'Held-out predictions', 'RMSE comparison']}


def chart(tables, config):
    name = config.get('chart', 'Dashboard')
    if name not in CHARTS.get(config['view'], ['Dashboard']):
        raise ValueError('Choose a chart available for the selected assessment.')
    fig, ax = plt.subplots(figsize=(6.4, 4), layout='constrained')
    color = config.get('chart_color', '#087f8c')
    size = config.get('chart_size', 14)
    marker = config.get('chart_marker', 'o')
    appearance = config.get('chart_appearance', {})
    reference = appearance.get('reference', {})
    from ..chart_annotations import reference_line, plot_note
    if name == 'Charge balance':
        data = tables['quality_by_sample']
        tol = config.get('balance_tolerance', 5)
        values = data.major_ion_CBE_percent
        if appearance.get('band', True):
            ax.axhspan(-tol,tol,color=appearance.get('band_color','#dcece5'),alpha=appearance.get('band_alpha',1),gid='aquaprov-tolerance-band',label=f'Tolerance band (±{tol:g}%)')
        reference_line(ax, reference)
        ax.scatter(data.row, values, s=size, marker=marker,
                   c=np.where(values.abs() > tol, appearance.get('review_color','#ce6b32'), color),
                   edgecolors=appearance.get('edgecolor','white'),linewidths=appearance.get('edgewidth',.25),alpha=appearance.get('alpha',1))
        from ..plot_legends import add_legend_entries
        from matplotlib.lines import Line2D
        add_legend_entries(ax, [Line2D([], [], marker=marker, lw=0, color=color, label='Within tolerance'),
                                Line2D([], [], marker=marker, lw=0, color=appearance.get('review_color','#ce6b32'), label='Exceeds tolerance')])
        ax.set(xlabel='Source data row', ylabel='Major-ion CBE (%)')
        plot_note(ax,reference.get('note',{}),'{count} of {n} exceed ±{tolerance}%',
                  count=int(values.abs().gt(tol).sum()),n=int(values.notna().sum()),tolerance=tol)
    elif name in ('SAR intervals', 'Na percent intervals'):
        metric = 'SAR' if name == 'SAR intervals' else 'Na_percent'
        data = tables['metric_intervals'].loc[lambda t: t.metric.eq(metric)]
        intervals = ax.errorbar(data.row, data['median'], yerr=[data['median'] - data.lower, data.upper - data['median']],
                    fmt=marker,ms=np.sqrt(size),lw=appearance.get('interval_width',.75),capsize=appearance.get('capsize',1.3),
                    capthick=appearance.get('capwidth',.75),color=color,ecolor=appearance.get('interval_color') or color,
                    markeredgecolor=appearance.get('edgecolor',color),markeredgewidth=appearance.get('edgewidth',0),alpha=appearance.get('alpha',1),label='Median and 95% interval')
        for cap in intervals.lines[1]:
            cap.set_markeredgewidth(appearance.get('capwidth',.75))
        reference_line(ax,reference)
        plot_note(ax,reference.get('note',{'show':False}),'n = {n}',n=len(data))
        ax.set(xlabel='Source data row', ylabel=metric.replace('_', ' ') + ': median and 95% interval')
    elif name == 'Held-out predictions':
        data = tables['spatial_predictions']
        for fold, group in data.groupby('fold'):
            ax.scatter(group.observed, group.prediction, s=size, marker=marker, label=str(fold),
                       color=plt.get_cmap('tab10')(int(fold) - 1), edgecolors='white', linewidths=.3,
                       alpha=appearance.get('alpha', 1))
        lo = min(data.observed.min(), data.prediction.min())
        hi = max(data.observed.max(), data.prediction.max())
        ax.plot([lo, hi], [lo, hi], ':', color='#64748b', lw=.8,label='Identity line (y = x)')
        ax.set(xlabel='Observed ' + config['column'], ylabel='Predicted ' + config['column'])
        ax.legend(title='Held-out block', ncol=min(5, data.fold.nunique()), loc='upper left', frameon=False,
                  handletextpad=.1, columnspacing=.4, handlelength=.7, borderpad=.2, labelspacing=.3)
    elif name == 'RMSE comparison':
        data = tables['spatial_scores']
        names = {'kriging': 'Kriging', 'idw': 'IDW', 'mean': 'Training mean', 'training mean': 'Training mean'}
        bar_colors = [value.strip() for value in appearance.get('bar_colors', '').split(',') if value.strip()]
        if bar_colors and len(bar_colors) not in (1, len(data)):
            raise ValueError('Provide one bar colour or one colour per RMSE method, in table order.')
        bars = ax.barh([names.get(n, n) for n in data.method], data.RMSE, color=bar_colors or color, height=.55,
                       alpha=appearance.get('alpha', 1))
        for bar, method in zip(bars, data.method):
            bar.set_label(names.get(method, method))
        ax.invert_yaxis(); ax.set_xlabel('RMSE')
        ax.margins(x=.2)
        for bar, value in zip(bars, data.RMSE):
            ax.annotate(f'{value:.2f}', (value, bar.get_y() + bar.get_height()/2),
                        xytext=(3, 0), textcoords='offset points', va='center')
    ax.set_title(name)
    from ..plot_layout import outside_legend
    outside_legend(fig)
    return fig
