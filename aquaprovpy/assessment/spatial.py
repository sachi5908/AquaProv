"""Training-only variogram fitting and geographically blocked validation."""
import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.spatial.distance import pdist
from scipy.stats import norm
from sklearn.cluster import KMeans

from ..modules.maps.interpolation import planar_coordinates, validate_geometry, ordinary_kriging, idw, covariance


def fit_variogram(xy, values, model='spherical', bins=10):
    if len(xy) < 2 or np.var(values, ddof=1) <= 0:
        raise ValueError('Variogram fitting needs varying training observations.')
    h = pdist(xy)
    gamma = .5*pdist(np.asarray(values)[:, None])**2
    edges = np.linspace(0, np.max(h)*.8, bins+1)
    rows = []
    for i in range(bins):
        take = (h > edges[i]) & (h <= edges[i+1])
        if take.sum() >= 3:
            rows.append({'distance': h[take].mean(), 'semivariance': gamma[take].mean(), 'pairs': int(take.sum())})
    empirical = pd.DataFrame(rows)
    if len(empirical) < 4:
        raise ValueError('Too few populated distance bins to fit a variogram.')
    variance = np.var(values, ddof=1)
    maxdist = h.max()
    weights = np.sqrt(empirical.pairs.to_numpy()/empirical.pairs.sum())
    def residual(p):
        range_, sill, nugget = p[0]*maxdist, p[1]*variance, p[2]*variance
        fitted = sill+nugget-covariance(empirical.distance.to_numpy(), model, range_, sill)
        return weights*(fitted-empirical.semivariance.to_numpy())/variance
    fit = least_squares(residual, [.4, .8, .2], bounds=([.01, 1e-6, 0], [2, 5, 5]))
    if not fit.success:
        raise ValueError('Variogram optimizer did not converge.')
    params = {'range_': fit.x[0]*maxdist, 'sill': fit.x[1]*variance, 'nugget': fit.x[2]*variance}
    empirical['fitted'] = params['sill']+params['nugget']-covariance(empirical.distance.to_numpy(), model, params['range_'], params['sill'])
    params['at_parameter_bound'] = bool(np.any(fit.active_mask))
    return params, empirical


def spatial_validation(m, column, *, coordinates='wgs84', folds=5, seed=42, model='spherical', threshold=None,
                       source_crs=None, target_crs=None, boundary=None, samples_inside_boundary=False,
                       power=2, neighbors=None):
    if column not in m.values or not all(k in m.samples for k in ('x', 'y')):
        raise ValueError('Map X/Y metadata and select a measurement for spatial validation.')
    if not isinstance(folds, int) or not 3 <= folds <= 10:
        raise ValueError('Use 3 to 10 spatial blocks.')
    if model not in ('spherical', 'exponential'):
        raise ValueError('Choose a spherical or exponential variogram.')
    if threshold is not None and (not np.isfinite(threshold) or threshold <= 0):
        raise ValueError('Exceedance threshold must be positive in normalized measurement units.')
    raw = m.samples[['x', 'y']].apply(pd.to_numeric, errors='coerce')
    raw['value'] = m.values[column]
    keep = np.isfinite(raw).all(axis=1)
    source = raw[keep].to_numpy()
    if len(source) <= folds:
        raise ValueError('Spatial blocks must be fewer than the complete observation count.')
    from ..modules.maps.projections import analysis_coordinates
    xy, _, _, projection = analysis_coordinates(source[:, :2], coordinates,
        boundary=boundary, source_crs=source_crs, target_crs=target_crs)
    if boundary is not None and samples_inside_boundary:
        from ..boundaries import geometry_in_crs, point_mask
        area = geometry_in_crs(boundary, projection['analysis_crs'],
            declared_local_crs='EPSG:4326' if coordinates in ('wgs84','auto_utm','wgs84_projected') else projection['analysis_crs'])
        inside = point_mask(area, xy)
        keep.iloc[np.flatnonzero(keep)[~inside]] = False
        source, xy = source[inside], xy[inside]
        if len(source) <= folds:
            raise ValueError('Spatial blocks must be fewer than the complete observation count inside the boundary.')
    validate_geometry(xy)
    # Blocks depend only on geometry; observations are never used to choose folds.
    labels = KMeans(n_clusters=folds, random_state=seed, n_init=10).fit_predict(xy)
    values, rows = source[:, 2], m.samples.loc[keep, 'row'].to_numpy()
    predictions, parameters = [], []
    from ..core.progress import progress_stage
    for fold in range(folds):
        train, test = labels != fold, labels == fold
        params, _ = fit_variogram(xy[train], values[train], model)
        bound = params.pop('at_parameter_bound')
        with progress_stage(90 * fold / folds, 90 * (fold + .8) / folds, f'Validating spatial fold {fold + 1} of {folds}'):
            pred, var = ordinary_kriging(xy[train], values[train], xy[test], model=model, **params)
        with progress_stage(90 * (fold + .8) / folds, 90 * (fold + 1) / folds, 'Calculating comparison model'):
            baseline = idw(xy[train], values[train], xy[test], power=power, neighbors=neighbors)
        parameters.append({'fold': fold+1, 'n_train': int(train.sum()), 'n_test': int(test.sum()),
                           'at_parameter_bound': bound, **params})
        for pos, p, v, b in zip(np.flatnonzero(test), pred, var, baseline):
            sd = np.sqrt(v)
            record = {'row': rows[pos], 'fold': fold+1, 'observed': values[pos], 'prediction': p,
                      'variance': v, 'lower_95': p-1.96*sd, 'upper_95': p+1.96*sd,
                      'idw_prediction': b, 'training_mean_prediction': values[train].mean(),
                      'residual': values[pos]-p, 'x': xy[pos, 0], 'y': xy[pos, 1]}
            if threshold is not None:
                record['exceedance_probability'] = norm.sf((threshold-p)/sd) if sd > 0 else float(p > threshold)
                record['observed_exceedance'] = int(values[pos] > threshold)
            predictions.append(record)
    pred = pd.DataFrame(predictions).sort_values('row')
    scores = []
    for method, col in [('kriging', 'prediction'), ('IDW', 'idw_prediction'), ('training mean', 'training_mean_prediction')]:
        error = pred[col]-pred.observed
        record = {'method': method, 'RMSE': np.sqrt(np.mean(error**2)), 'MAE': np.mean(abs(error)), 'bias': error.mean()}
        if method == 'kriging':
            record.update(coverage_95=np.mean((pred.observed >= pred.lower_95) & (pred.observed <= pred.upper_95)),
                          mean_interval_width=np.mean(pred.upper_95-pred.lower_95))
            if threshold is not None:
                record['brier_score'] = np.mean((pred.exceedance_probability-pred.observed_exceedance)**2)
        scores.append(record)
    full_params, empirical = fit_variogram(xy, values, model)
    tables = {'spatial_predictions': pred, 'spatial_scores': pd.DataFrame(scores),
              'spatial_coordinate_system': pd.DataFrame([projection]),
              'idw_baseline_settings': pd.DataFrame([{'power': power, 'neighbors': neighbors,
                  'neighborhood': 'all training samples' if neighbors is None else 'nearest training samples, including distance ties'}]),
              'training_variograms': pd.DataFrame(parameters), 'empirical_variogram': empirical,
              'full_data_variogram': pd.DataFrame([full_params]), 'spatial_exclusions': m.samples.loc[~keep],
              'variogram_fit_settings': pd.DataFrame([{
                  'estimator': 'Matheron; 0.5 * mean squared differences', 'distance_bins': 10,
                  'maximum_distance_fraction': .8, 'minimum_pairs_per_bin': 3,
                  'loss': 'least squares with residual weights sqrt(pair count / total pair count)',
                  'range_bounds_fraction_of_max_distance': '[0.01, 2]',
                  'partial_sill_bounds_fraction_of_sample_variance': '[0.000001, 5]',
                  'nugget_bounds_fraction_of_sample_variance': '[0, 5]',
                  'block_method': 'K-means of coordinates, 10 initializations', 'buffer_distance': 0}])}
    notes = ['Geographic K-means blocks use coordinates only; each held-out block uses a variogram fitted only on its training data.',
             'Isotropic ordinary kriging assumes stationarity. Conditional Gaussian intervals and exceedance probabilities omit parameter uncertainty; review measured holdout coverage.',
             'Full-data variogram is an exploratory diagnostic and is never used for holdout predictions.',
             'Duplicate locations are rejected. Select a single campaign or deliberately aggregate replicates before spatial analysis.',
             'K-means blocks have no separation buffer; short-range dependence across block edges may remain.',
             f'Coordinate conversion: {coordinates}; {projection}.']
    if any(p['at_parameter_bound'] for p in parameters) or full_params['at_parameter_bound']:
        notes.append('At least one variogram fit reached parameter bounds. Treat that model as weakly identified.')
    if (pred.lower_95 < 0).any():
        notes.append('Some Gaussian prediction intervals extend below zero. No clipping is applied; assess distributional suitability before concentration or exceedance interpretation.')
    return tables, notes
