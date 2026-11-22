"""Expected value of a follow-up assay for a single upper-threshold decision.

Current log concentration is Normal(mu, sigma^2). The proposed assay returns
log(Y)=log(X)+Normal(0,tau^2), independently conditional on the same stable X.
Loss is one per incorrect binary decision, zero otherwise. No health-cost claim.
"""
import numpy as np
from scipy.special import ndtr
from numpy.polynomial.legendre import leggauss


def posterior_log_parameters(mu, sigma, log_result, assay_log_sd):
    mu, sigma, y, tau = np.broadcast_arrays(mu, sigma, log_result, assay_log_sd)
    if not np.isfinite([mu, sigma, y, tau]).all() or np.any(sigma < 0) or np.any(tau <= 0):
        raise ValueError('Finite values, current SD >= 0 and assay log SD > 0 are required.')
    gain = sigma**2/(sigma**2+tau**2)
    return mu+gain*(y-mu), np.sqrt((1-gain)*sigma**2)


def expected_value(mu, sigma, threshold, assay_log_sd, *, quadrature=96):
    """Return current risk, expected posterior risk and EVSI using split quadrature.

    The standard normal predictive density is integrated on [-10,10], split at
    the decision boundary. Omitted tail mass is below 1.6e-23. Equal assay costs
    and independent additive losses permit sorting EVSI to optimize a batch.
    """
    mu, sigma, threshold, tau = np.broadcast_arrays(mu, sigma, threshold, assay_log_sd)
    if not all(np.isfinite(v).all() for v in (mu,sigma,threshold,tau)) or np.any(sigma < 0) or np.any(threshold <= 0) or np.any(tau <= 0):
        raise ValueError('Finite parameters with sigma >= 0, threshold > 0 and assay SD > 0 are required.')
    if not isinstance(quadrature,int) or not 32 <= quadrature <= 512:
        raise ValueError('Use 32 to 512 quadrature nodes per half interval.')
    shape=mu.shape
    mu,sigma,threshold,tau=[v.ravel() for v in (mu,sigma,threshold,tau)]
    active=sigma>0
    safe=np.where(active,sigma,1.)
    a=(np.log(threshold)-mu)/safe
    prior=np.minimum(ndtr(a),ndtr(-a)); prior[~active]=0
    r=safe/np.sqrt(safe**2+tau**2)
    b=np.clip(a/r,-10,10)
    post_sd=safe*tau/np.sqrt(safe**2+tau**2)
    nodes,weights=leggauss(quadrature)
    risk=np.zeros_like(mu)
    for lo,hi in ((np.full_like(b,-10),b),(b,np.full_like(b,10))):
        z=(hi-lo)[:,None]/2*nodes+(hi+lo)[:,None]/2
        q=(mu[:,None]+(safe*r)[:,None]*z-np.log(threshold)[:,None])/post_sd[:,None]
        loss=ndtr(-np.abs(q))
        risk+=(hi-lo)/2*np.sum(weights*loss*np.exp(-z*z/2)/np.sqrt(2*np.pi),axis=1)
    risk[~active]=0
    if np.any(risk-prior>1e-7):
        raise ValueError('Assay quadrature did not satisfy the information bound; increase nodes.')
    risk=np.minimum(risk,prior)
    return {k:v.reshape(shape) for k,v in {'current_risk':prior,'expected_posterior_risk':risk,'evsi':prior-risk}.items()}
