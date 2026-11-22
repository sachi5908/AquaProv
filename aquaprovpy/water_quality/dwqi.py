"""Drinking-water index entry points, separate from the WQI calculations."""
from .common import aggregate_arithmetic


def drinking_water_index(frame, parameters, *, custom=False, scheme=None):
    method = ('Custom weighted DWQI (user-specified weights, ratings and drinking-water limits)' if custom else
              'Weighted DWQI adapted from Ramakrishnaiah et al. (2009), DOI 10.1155/2009/757424')
    result = aggregate_arithmetic(frame, parameters, index='DWQI', method=method, scheme=scheme)
    result.warnings.append('DWQI has no universally standardized formula. The exported weights, quality ratings, standard edition and classification scheme define this run.')
    return result
