"""Publication analyses with explicit variable selection and auditable preprocessing.

PCA uses sample-SD standardization and SVD. Loadings are eigenvectors times
sqrt(eigenvalues), NOT eigenvectors alone. Varimax uses Kaiser normalization.
Ward operates on observations with Euclidean distance, never a correlation matrix.
"""

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster import hierarchy

from ._publication import (STYLE, PALETTE, numeric_frame, standardize,
                           sample_labels, scatter_samples, finish, close_on_error)


def _sample_ticks(count, limit=60):
    """Limit text artists, retaining both endpoints and every data observation."""
    return np.unique(np.linspace(0, count - 1, min(count, limit), dtype=int))


def _record_display_labels(tables, meta, warnings, labels, ticks):
    if len(ticks) < len(labels):
        tables['display_labels'] = pd.DataFrame({'display_position_1based': ticks + 1,
                                                 'Sample': np.asarray(labels)[ticks]})
        meta['sample_labels_shown'] = len(ticks)
        warnings.append(f'All {len(labels)} samples are plotted; {len(ticks)} evenly spaced sample labels '
                        'are displayed for readability. Full sample identities remain in the result tables.')


def correlation(df, columns, *, method='pearson', missing='raise', constants='raise'):
    if method not in ('pearson', 'spearman'):
        raise ValueError('Choose pearson or spearman.')
    data, positions, meta, warnings = numeric_frame(df, columns, missing, constants=constants)
    p = len(data.columns)
    r, prob = np.eye(p), np.full((p, p), np.nan)
    function = stats.pearsonr if method == 'pearson' else stats.spearmanr
    pairs = []
    for i in range(p):
        for j in range(i):
            value, pv = function(data.iloc[:, i], data.iloc[:, j])
            if not np.isfinite(value):
                raise ValueError('Correlation is numerically undefined; check near-constant variables.')
            r[i, j] = r[j, i] = value
            prob[i, j] = prob[j, i] = pv
            if np.isfinite(pv):
                pairs.append((i, j, pv))
    # Benjamini-Hochberg over unique off-diagonal tests, not both triangles.
    q = np.full((p, p), np.nan)
    order = np.argsort([v[2] for v in pairs])
    ranked = np.array([pairs[k][2] for k in order])
    adjusted = np.minimum(1, np.minimum.accumulate((ranked * len(pairs) /
                                                  np.arange(1, len(pairs) + 1))[::-1])[::-1])
    for k, value in zip(order, adjusted):
        i, j, _ = pairs[k]
        q[i, j] = q[j, i] = value
    names = data.columns
    tables = {'correlation': pd.DataFrame(r, index=names, columns=names),
              'p_values': pd.DataFrame(prob, index=names, columns=names),
              'q_values_bh': pd.DataFrame(q, index=names, columns=names),
              'n_pairs': pd.DataFrame(len(data), index=names, columns=names),
              'analysis_data': data}
    meta.update(method=method, p_values='two-sided; unadjusted',
                q_values='Benjamini-Hochberg FDR across unique variable pairs')
    if method == 'spearman':
        warnings.append('Spearman p-values use the SciPy asymptotic approximation; small samples require caution.')
    if len(data) == 2:
        warnings.append('Only two observations: correlations are descriptive; significance cannot be established. Undefined p-values remain blank.')
    return tables, meta, warnings


def varimax(loadings, *, tol=1e-8, max_iter=10000):
    """Orthogonal Varimax with Kaiser row normalization; return L@R and R."""
    a = np.asarray(loadings, dtype=float)
    h = np.sqrt(np.sum(a * a, axis=1))
    h = np.where(h > np.finfo(float).eps, h, 1.0)
    normalized = a / h[:, None]
    p, k = a.shape
    rotation = np.eye(k)
    for iteration in range(max_iter):
        b = normalized @ rotation
        u, singular, vt = np.linalg.svd(normalized.T @
            (b ** 3 - b @ np.diag(np.sum(b * b, axis=0)) / p))
        updated = u @ vt
        change = np.linalg.norm(updated - rotation, ord='fro')
        rotation = updated
        # Small change in the SVD surrogate objective can occur well before
        # the rotation stabilizes. Require the orthogonal matrix to converge.
        if iteration and change <= tol:
            return a @ rotation, rotation, iteration + 1
    raise ValueError('Varimax did not converge; no rotated result was accepted.')


def pca(df, columns, *, n_components=3, rotation='none', missing='raise',
        constants='raise', scale=True):
    data, positions, meta, warnings = numeric_frame(df, columns, missing, constants=constants)
    x, preprocessing = standardize(data, scale)
    u, singular, vt = np.linalg.svd(x.to_numpy(), full_matrices=False)
    rank = int(np.linalg.matrix_rank(x.to_numpy()))
    if isinstance(n_components, bool) or not isinstance(n_components, (int, np.integer)) or not 1 <= n_components <= rank:
        raise ValueError(f'n_components must be an integer from 1 to the data rank ({rank}).')
    if rotation not in ('none', 'varimax'):
        raise ValueError('Choose none or varimax rotation.')
    # Deterministic sign convention; component signs are otherwise arbitrary.
    signs = np.sign(vt[np.arange(len(vt)), np.argmax(np.abs(vt), axis=1)])
    vt = vt * signs[:, None]
    eigenvalues = singular ** 2 / (len(x) - 1)
    scores = x.to_numpy() @ vt[:n_components].T
    loadings = vt[:n_components].T * np.sqrt(eigenvalues[:n_components])
    total = eigenvalues.sum()
    names = [f'PC{i + 1}' for i in range(n_components)]
    labels = pd.Index(sample_labels(df.iloc[positions]), name='Sample')
    all_names = [f'PC{i + 1}' for i in range(len(eigenvalues))]
    tables = {
        'scores': pd.DataFrame(scores, index=labels, columns=names),
        'eigenvectors': pd.DataFrame(vt[:n_components].T, index=x.columns, columns=names),
        'loadings': pd.DataFrame(loadings, index=x.columns, columns=names),
        'variance': pd.DataFrame({'eigenvalue': eigenvalues,
            'variance_percent': 100 * eigenvalues / total,
            'cumulative_percent': 100 * np.cumsum(eigenvalues) / total}, index=all_names),
        'preprocessing': preprocessing, 'analysis_data': data,
    }
    if rotation == 'varimax':
        rotated, matrix, iterations = varimax(loadings)
        # Factor-score coordinates with unit sample variance before rotation.
        factor_scores = scores / np.sqrt(eigenvalues[:n_components]) @ matrix
        factors = [f'RC{i + 1}' for i in range(n_components)]
        tables.update({
            'rotated_loadings': pd.DataFrame(rotated, index=x.columns, columns=factors),
            'rotation_matrix': pd.DataFrame(matrix, index=names, columns=factors),
            'rotated_factor_scores': pd.DataFrame(factor_scores, index=labels, columns=factors),
            'rotated_variance': pd.DataFrame({'sum_squared_loadings': (rotated ** 2).sum(axis=0),
                'variance_percent': 100 * (rotated ** 2).sum(axis=0) / total}, index=factors),
        })
        meta.update(varimax_iterations=iterations, kaiser_normalization=True)
    tables['communalities'] = pd.DataFrame({'retained_sum_squared_loadings':
                                            (loadings ** 2).sum(axis=1)}, index=x.columns)
    meta.update(method='PCA via SVD', n_components=int(n_components), rank=rank,
                scale='sample SD (ddof=1)' if scale else 'center only; covariance PCA',
                rotation=rotation, loadings='eigenvectors * sqrt(sample eigenvalues)',
                rotated_scores='unit-variance PC scores @ orthogonal rotation matrix',
                retained_variance_percent=float(100 * eigenvalues[:n_components].sum() / total))
    if len(data) <= len(x.columns):
        warnings.append('Samples do not exceed variables; PCA may be unstable. Review sample adequacy.')
    return tables, meta, warnings, df.iloc[positions]


def hca(df, columns, *, n_clusters=3, missing='raise', constants='raise', scale=True):
    data, positions, meta, warnings = numeric_frame(df, columns, missing, constants=constants)
    if isinstance(n_clusters, bool) or not isinstance(n_clusters, (int, np.integer)) or not 1 <= n_clusters <= len(data):
        raise ValueError('n_clusters must be an integer between 1 and the sample count.')
    x, preprocessing = standardize(data, scale)
    from .core.progress import progress_listener, report_progress
    report_progress(10, 'Ordering Ward clusters')
    if len(data) >= 256 and progress_listener.get() is not None:
        from .core.numeric_jobs import run_numeric_job
        z = run_numeric_job('ward', x.to_numpy())
    else:
        z = hierarchy.linkage(x.to_numpy(), method='ward', metric='euclidean', optimal_ordering=True)
    report_progress(70, 'Preparing cluster membership')
    clusters = hierarchy.cut_tree(z, n_clusters=[n_clusters]).ravel() + 1
    labels = sample_labels(df.iloc[positions])
    members = data.copy()
    members.index = pd.Index(labels, name='Sample')
    grouped = members.groupby(clusters)
    tables = {'linkage': pd.DataFrame(z, columns=['left_node', 'right_node', 'ward_distance', 'n_members']),
              'membership': pd.DataFrame({'Cluster': clusters, 'input_row_position': positions + 1}, index=members.index),
              'cluster_means': grouped.mean(), 'cluster_counts': grouped.size().to_frame('n'),
              'preprocessing': preprocessing, 'analysis_data': members}
    meta.update(method='Ward minimum variance', distance='Euclidean on observations; SciPy Ward heights',
                scale='sample SD (ddof=1)' if scale else 'center only', n_clusters=int(n_clusters),
                optimal_leaf_ordering=True, cut='exact merge-count cut; ties resolved by linkage order')
    if np.any(np.diff(z[:, 2]) == 0):
        warnings.append('Tied merge heights: exact cluster-count cut uses linkage order, not a unique height threshold.')
    return tables, meta, warnings


VIEWS = ('pearson', 'spearman', 'pca_scores', 'pca_scores_3d', 'pca_loadings',
         'pca_loadings_3d', 'pca_scree', 'pca_correlation_circle',
         'hca', 'heatmap', 'scatter_matrix', 'boxplot')


@close_on_error
def plot(df, unit='mg/L', figname='Multivariate analysis', figformat='png', *,
         columns=None, view='pearson', missing='raise', constants='raise',
         scale=True, n_components=3, rotation='none', n_clusters=3,
         significance='raw', dpi=300, title=None, show_origin_lines=True, projection='persp', annotate=True,
         scatter_pair=False):
    """Plot one analysis, returning a PlotResult with full-precision result tables.

    ``unit`` is accepted for GUI/API compatibility, not used to convert statistics.
    Input columns may have different units; standardized PCA/HCA are recommended.
    No log transform, imputation or outlier removal is performed implicitly.
    """
    if view not in VIEWS:
        raise ValueError('Unknown statistical view: ' + str(view))
    if significance not in ('raw', 'fdr'):
        raise ValueError('significance must be raw or fdr.')
    if not isinstance(scatter_pair, (bool, np.bool_)):
        raise ValueError('scatter_pair must be true or false.')
    if view == 'scatter_matrix' and scatter_pair:
        if isinstance(columns, str) or columns is None:
            raise ValueError('Select exactly two distinct measurement columns for a single scatter plot.')
        columns = list(columns)
        if len(columns) != 2 or len(set(columns)) != 2:
            raise ValueError('Select exactly two distinct measurement columns for a single scatter plot.')
    if view.endswith('_3d') and projection not in ('persp', 'ortho'):
        raise ValueError('Choose perspective or orthographic projection.')
    with plt.rc_context(STYLE):
        if view in ('pearson', 'spearman'):
            tables, meta, warnings = correlation(df, columns, method=view, missing=missing, constants=constants)
            r = tables['correlation']
            count = len(r)
            fig, ax = plt.subplots(layout='constrained', figsize=(max(6, count * 0.55), max(5, count * 0.5)))
            values = np.ma.array(r.to_numpy(), mask=np.triu(np.ones((count, count), dtype=bool), 1))
            image = ax.imshow(values, cmap='RdBu_r', vmin=-1, vmax=1)
            probabilities = tables['p_values' if significance == 'raw' else 'q_values_bh'].to_numpy()
            for i in range(count if annotate else 0):
                for j in range(i + 1):
                    pv = probabilities[i, j]
                    star = '**' if pv < 0.01 else '*' if pv < 0.05 else ''
                    ax.text(j, i, f'{r.iloc[i, j]:.2f}{star}', ha='center', va='center',
                            fontsize=max(5, min(9, 110 / count)),
                            color='white' if abs(r.iloc[i, j]) > 0.65 else '#243447')
            ax.set_xticks(range(count)); ax.set_xticklabels(r.columns, rotation=45, ha='right')
            ax.set_yticks(range(count)); ax.set_yticklabels(r.index)
            fig.colorbar(image, ax=ax, shrink=0.75, label='Correlation coefficient')
            from .plot_legends import add_legend_entries, scale_legend
            scale_legend(ax, image, 'Correlation coefficient')
            if annotate:
                level = 'p' if significance == 'raw' else 'BH-adjusted q'
                add_legend_entries(ax, [Line2D([], [], linestyle='none', marker='$*$', label=f'{level} < 0.05'),
                                        Line2D([], [], linestyle='none', marker='$**$', label=f'{level} < 0.01')])
            label = 'p' if significance == 'raw' else 'BH-adjusted q'
            ax.set_title(title or f'{view.title()} correlation')
            ax.set_xlabel(f'* {label} < 0.05; ** {label} < 0.01 (two-sided)' if annotate else '')
            from .plot_layout import CellTextLayout
            CellTextLayout(ax, count, count)
            meta['display_significance'] = significance
        elif view.startswith('pca'):
            tables, meta, warnings, selected = pca(df, columns, n_components=n_components,
                rotation=rotation, missing=missing, constants=constants, scale=scale)
            loadkey = 'rotated_loadings' if rotation == 'varimax' else 'loadings'
            load = tables[loadkey]
            dimensions = 3 if view.endswith('3d') else 2
            if view not in ('pca_loadings', 'pca_scree') and n_components < dimensions:
                raise ValueError(f'This view requires at least {dimensions} retained components.')
            if view == 'pca_scree':
                fig, ax = plt.subplots(layout='constrained', figsize=(8, 5))
                variance = tables['variance']
                ticks = np.arange(1, len(variance) + 1)
                ax.plot(ticks, variance['eigenvalue'], 'o-', color=PALETTE[0], label='Eigenvalue')
                if scale:
                    ax.axhline(1, color='#718096', ls='--', label='Eigenvalue = 1 (heuristic)')
                    ax.legend(frameon=False)
                ax.set(xlabel='Principal component', ylabel='Eigenvalue', xticks=ticks)
                other = ax.twinx()
                other.plot(ticks, variance['cumulative_percent'], 's--', color=PALETTE[1], label='Cumulative variance')
                other.set(ylabel='Cumulative variance (%)', ylim=(0, 105))
            elif view == 'pca_loadings':
                fig, ax = plt.subplots(layout='constrained', figsize=(max(6, n_components * 1.2), max(5, len(load) * 0.38)))
                limit = max(1.0, np.abs(load.to_numpy()).max())
                image = ax.imshow(load, cmap='RdBu_r', vmin=-limit, vmax=limit, aspect='auto')
                for i in range(len(load)):
                    for j in range(n_components):
                        value = load.iloc[i, j]
                        ax.text(j, i, f'{value:.3f}', ha='center', va='center',
                                color='white' if abs(value) > limit * 0.65 else '#243447')
                ax.set_xticks(range(n_components)); ax.set_xticklabels(load.columns)
                ax.set_yticks(range(len(load))); ax.set_yticklabels(load.index)
                fig.colorbar(image, ax=ax, label='Loading')
                from .plot_legends import scale_legend
                scale_legend(ax, image, 'Component loading')
                from .plot_layout import CellTextLayout
                CellTextLayout(ax, len(load), n_components)
            else:
                is_load = view in ('pca_loadings_3d', 'pca_correlation_circle')
                if view == 'pca_correlation_circle' and not scale:
                    raise ValueError('Correlation circle requires standardized PCA.')
                fig = plt.figure(figsize=(8, 7), layout=None if dimensions == 3 else 'constrained')
                ax = fig.add_subplot(111, projection='3d' if dimensions == 3 else None)
                if is_load:
                    coords = load.iloc[:, :dimensions]
                    variable_key = []
                    for number, (label, row) in enumerate(coords.iterrows(), 1):
                        color = PALETTE[int(np.argmax(np.abs(row))) % len(PALETTE)]
                        if dimensions == 3:
                            if show_origin_lines:
                                arrow = ax.quiver(0, 0, 0, *row, color=color, arrow_length_ratio=0.06, linewidth=1)
                                arrow.set_gid('aquaprov-origin-lines')
                                from .plot_legends import add_legend_entries
                                add_legend_entries(ax, [Line2D([], [], color='#66788a', label='Origin vectors')])
                            ax.scatter(*row, marker='o', s=20, color=color, depthshade=False)
                            variable_key.append(Line2D([], [], color=color, marker=f'${number}$',
                                                       markersize=9, lw=0, label=str(label)))
                        else:
                            ax.annotate('', xy=row, xytext=(0, 0), arrowprops={'arrowstyle': '->', 'color': color})
                            variable_key.append(Line2D([], [], color=color, label=str(label)))
                    from .plot_layout import point_labels
                    point_labels(ax, coords.to_numpy(),
                                 list(range(1, len(coords)+1)) if dimensions == 3 else coords.index,
                                 colors=[PALETTE[int(np.argmax(np.abs(row))) % len(PALETTE)]
                                         for row in coords.to_numpy()], fontsize=9)
                    limit = max(1.15, float(np.abs(coords.to_numpy()).max()) * 1.18)
                    ax.set(xlim=(-limit, limit), ylim=(-limit, limit))
                    if dimensions == 3:
                        ax.set_zlim(-limit, limit)
                        ax.legend(handles=variable_key, title='Variables', loc='upper left',
                                  bbox_to_anchor=(1.17, 1), frameon=False, labelspacing=0.9)
                    else:
                        ax.add_patch(Circle((0, 0), 1, fill=False, color='#718096', ls='--'))
                        from .plot_legends import add_legend_entries
                        add_legend_entries(ax, [*variable_key, Line2D([], [], color='#718096', ls='--', label='Unit correlation circle')])
                        ax.set_aspect('equal')
                    names = coords.columns
                else:
                    coords = tables['rotated_factor_scores' if rotation == 'varimax' else 'scores']
                    scatter_samples(ax, selected, [coords.iloc[:, i] for i in range(dimensions)],
                                    show_origin_lines=dimensions == 3 and show_origin_lines)
                    names = coords.columns
                for i, setter in enumerate([ax.set_xlabel, ax.set_ylabel] + ([ax.set_zlabel] if dimensions == 3 else [])):
                    var = tables['rotated_variance' if rotation == 'varimax' else 'variance']['variance_percent'].iloc[i]
                    setter(f'{names[i]} ({var:.1f}%)')
                if dimensions == 3:
                    # Equal coordinate units preserve relative score distances;
                    # a cube with independently autoscaled axes distorts them.
                    ax.set_box_aspect([np.ptp(ax.get_xlim()), np.ptp(ax.get_ylim()), np.ptp(ax.get_zlim())])
                    ax.set_proj_type(projection)
                    for component in (ax.xaxis, ax.yaxis, ax.zaxis):
                        component.set_major_locator(MaxNLocator(nbins=5))
                    ax.view_init(elev=22, azim=-55)
                    meta['displayed_components'] = list(names[:3])
                    meta['displayed_variance_percent'] = float(
                        tables['rotated_variance' if rotation == 'varimax' else 'variance']['variance_percent'].iloc[:3].sum())
                    if not is_load and rotation == 'varimax':
                        warnings.append('Rotated factor-score coordinates have unit sample variance. Axis percentages describe variance attributed by the rotated loadings.')
                    if not is_load and ax.get_legend() is not None:
                        ax.get_legend().set_bbox_to_anchor((1.17, 1))
                ax.grid(True, alpha=0.25)
            label = 'Varimax-rotated' if rotation == 'varimax' and view != 'pca_scree' else 'PCA'
            ax.set_title(title or (label + ' · ' + view.replace('pca_', '').replace('_', ' ')))
        elif view == 'hca':
            tables, meta, warnings = hca(df, columns, n_clusters=n_clusters,
                                         missing=missing, constants=constants, scale=scale)
            n = meta['n_used']
            fig, ax = plt.subplots(layout='constrained', figsize=(10, min(16, max(5, n * 0.19))))
            z = tables['linkage'].to_numpy()
            membership = tables['membership']['Cluster'].to_numpy()
            node_clusters = {i: {int(c)} for i, c in enumerate(membership)}
            for i, row in enumerate(z):
                node_clusters[n + i] = node_clusters[int(row[0])] | node_clusters[int(row[1])]
            def color_node(node):
                members = node_clusters[int(node)]
                return PALETTE[(next(iter(members)) - 1) % len(PALETTE)] if len(members) == 1 else '#526479'
            labels = tables['membership'].index.tolist()
            tree = hierarchy.dendrogram(z, labels=labels, orientation='right', no_labels=n > 60,
                                        ax=ax, leaf_font_size=8, link_color_func=color_node)
            if n > 60:
                ticks = _sample_ticks(n)
                ordered = np.asarray(labels)[tree['leaves']]
                ax.set_yticks(5 + 10 * ticks, labels=ordered[ticks], fontsize=8)
                tables['leaf_order'] = pd.DataFrame({'Sample': ordered,
                    'input_position_1based': tables['membership']['input_row_position'].to_numpy()[tree['leaves']]})
                _record_display_labels(tables, meta, warnings, ordered, ticks)
            ax.legend(handles=[Line2D([], [], color=PALETTE[(i - 1) % len(PALETTE)],
                                      label=f'Cluster {i} (n={int((membership == i).sum())})')
                               for i in range(1, n_clusters + 1)],
                      loc='lower right', frameon=False)
            ax.set(xlabel='Ward linkage distance (Euclidean)', ylabel='Sample',
                   title=title or f'Ward hierarchical clustering · {n_clusters} clusters')
            ax.grid(axis='x', alpha=0.2)
        else:
            raw_scatter = view == 'scatter_matrix'
            data, positions, meta, warnings = numeric_frame(df, columns, missing,
                min_rows=1 if raw_scatter else 2, constants='keep' if raw_scatter else constants,
                min_columns=2 if raw_scatter else 1)
            tables = {'analysis_data': data}
            meta.update(method=view, scale='raw measurements, original units' if raw_scatter else 'sample SD (ddof=1)')
            if not raw_scatter:
                x, preprocessing = standardize(data)
                tables.update(standardized_data=x, preprocessing=preprocessing)
            if view == 'scatter_matrix':
                if scatter_pair:
                    x_variable, y_variable = data.columns
                    fig, ax = plt.subplots(layout='constrained', figsize=(7, 5.5))
                    ax.scatter(data[x_variable], data[y_variable], color=PALETTE[0], alpha=0.7, s=24,
                               label='Paired measurements')
                    ax.set(xlabel=x_variable, ylabel=y_variable,
                           title=title or f'{y_variable} versus {x_variable} scatter plot')
                    ax.grid(True, alpha=0.2)
                    meta.update(scale='raw measurements, original units', scatter_mode='single variable pair',
                                x_variable=x_variable, y_variable=y_variable)
                else:
                    from pandas.plotting import scatter_matrix
                    axes = scatter_matrix(data, figsize=(max(7, len(data.columns) * 1.8),) * 2,
                                          diagonal='hist', color=PALETTE[0], alpha=0.7, s=18)
                    fig = axes[0, 0].figure
                    axes[0, 1].collections[0].set_label('Paired measurements')
                    if axes[0, 0].patches:
                        axes[0, 0].patches[0].set_label('Measurement frequency')
                    fig.suptitle(title or 'Measurement scatter matrix')
                    meta.update(scale='raw measurements, original units', scatter_mode='matrix')
            elif view == 'boxplot':
                fig, ax = plt.subplots(layout='constrained', figsize=(max(7, len(x.columns) * 0.6), 5))
                boxes = ax.boxplot(x.to_numpy(), patch_artist=True,
                           boxprops={'facecolor': '#c9e7f0', 'edgecolor': PALETTE[0]},
                           medianprops={'color': PALETTE[1]})
                from .plot_legends import box_legend
                box_legend(ax, boxes)
                ax.set_xticks(range(1, len(x.columns) + 1)); ax.set_xticklabels(x.columns, rotation=45, ha='right')
                ax.set(ylabel='Standardized value (sample z-score)', title=title or 'Standardized distributions')
                ax.grid(axis='y', alpha=0.2)
            else:
                fig, ax = plt.subplots(layout='constrained', figsize=(max(7, len(x.columns) * 0.6), min(16, max(5, len(x) * 0.16))))
                limit = max(1, np.abs(x.to_numpy()).max())
                image = ax.imshow(x, cmap='RdBu_r', vmin=-limit, vmax=limit, aspect='auto')
                ax.set_xticks(range(len(x.columns))); ax.set_xticklabels(x.columns, rotation=45, ha='right')
                ticks = _sample_ticks(len(x))
                labels = sample_labels(df.iloc[positions])
                ax.set_yticks(ticks, labels=np.asarray(labels)[ticks], fontsize=7)
                _record_display_labels(tables, meta, warnings, labels, ticks)
                ax.set_title(title or 'Standardized sample profiles')
                fig.colorbar(image, ax=ax, label='Sample z-score')
                from .plot_legends import scale_legend
                scale_legend(ax, image, 'Standardized sample value')
        if not title:
            # Report the sample count after exclusions in every statistical view.
            heading = fig._suptitle if view == 'scatter_matrix' and not scatter_pair else ax.title
            heading.set_text(f'{heading.get_text()} · n = {meta["n_used"]}')
        if view in ('pca_loadings_3d', 'pca_scores_3d'):
            meta['appearance'] = {'show_origin_lines': show_origin_lines, 'projection': projection,
                                  'axis_scaling': 'equal coordinate units'}
            # Matplotlib's tight_layout can crop 3D axis labels on export.
            fig.subplots_adjust(left=0.04, bottom=0.12, right=0.76, top=0.9)
            if ax.get_legend() is not None:
                from .plot_layout import outside_legend
                outside_legend(fig)
                fig._aquaprov_3d_legend = True
                fig.subplots_adjust(left=.08, right=.90, bottom=.22, top=.88)
        else:
            from .plot_layout import outside_legend
            outside_legend(fig)
            fig.set_layout_engine('constrained', w_pad=.12, h_pad=.12, wspace=.10)
        meta.update(view=view, unit_note='Statistics use supplied units; no chemical conversion',
                    transformations='No log transform, imputation or outlier removal')
        return finish(fig, tables, meta, warnings, figname, figformat, dpi)
