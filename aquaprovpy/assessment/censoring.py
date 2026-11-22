"""Explicit left-censored lognormal models, fitted on a declared reference set.

The likelihood treats detection as X < L, with exact detected concentrations.
It is not a model of noisy detection, informative missingness or correlated ions.
"""
import numpy as np
from scipy.optimize import minimize
from scipy.special import log_ndtr, ndtri_exp


def validate_censor_model(model):
    if not isinstance(model, dict) or not model.get('source'):
        raise ValueError('A censored-distribution model requires a source description.')
    mu, sigma = model.get('log_mean'), model.get('log_sd')
    if mu is None or sigma is None or not np.isfinite([mu, sigma]).all() or sigma <= 0:
        raise ValueError('Censored lognormal parameters must be finite, with log_sd > 0.')
    return float(mu), float(sigma)


def draw_left_censored(limit, model, rng, count):
    """Stable inverse CDF sampling conditional on 0 < X < limit."""
    mu, sigma = validate_censor_model(model)
    if not np.isfinite(limit) or limit <= 0:
        raise ValueError('A positive finite censoring limit is required.')
    log_mass = log_ndtr((np.log(limit)-mu)/sigma)
    u = np.maximum(rng.random(count), np.finfo(float).tiny)
    log_x = mu + sigma*ndtri_exp(np.log(u)+log_mass)
    # Floating-point safeguards only; this is not a pseudocount for source data.
    return np.minimum(np.exp(log_x), limit)


def fit_censored_lognormal(values, limits, *, source):
    """Censored MLE; NaN value means left-censored at its positive limit.

    Use only training/reference data. Parameters are returned with fit diagnostics;
    parameter uncertainty is not silently included in subsequent conditional draws.
    """
    x, lod = np.asarray(values, float), np.asarray(limits, float)
    if x.ndim != 1 or x.shape != lod.shape or not source:
        raise ValueError('Aligned one-dimensional values/limits and a source are required.')
    detected = np.isfinite(x)
    if np.isinf(x).any() or np.any(x[detected] <= 0):
        raise ValueError('Detected concentrations must be positive and finite.')
    if detected.sum() < 8 or np.any(~np.isfinite(lod[~detected])) or np.any(lod[~detected] <= 0):
        raise ValueError('At least eight detects and positive limits for every non-detect are required.')
    logx, logl = np.log(x[detected]), np.log(lod[~detected])
    start_sd = max(float(logx.std()), .1)
    def objective(par):
        mu, logs = par; sigma = np.exp(logs)
        z = (logx-mu)/sigma
        return float(np.sum(logs + .5*z*z) - np.sum(log_ndtr((logl-mu)/sigma)))
    fit = minimize(objective, [logx.mean(), np.log(start_sd)], method='BFGS',
                   options={'gtol':1e-6, 'maxiter':1000})
    if not np.isfinite(fit.fun) or (not fit.success and np.linalg.norm(fit.jac) > 1e-3):
        raise ValueError('Censored lognormal fit failed: '+str(fit.message))
    model = {'log_mean':float(fit.x[0]), 'log_sd':float(np.exp(fit.x[1])), 'source':source,
             'method':'left-censored lognormal maximum likelihood; fixed fitted parameters',
             'detected_n':int(detected.sum()), 'censored_n':int((~detected).sum()),
             'optimizer_success':bool(fit.success), 'gradient_norm':float(np.linalg.norm(fit.jac)),
             'censoring_fraction':float((~detected).mean())}
    validate_censor_model(model)
    return model
