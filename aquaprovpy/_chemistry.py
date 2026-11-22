"""Validated major-ion equivalents for normalized geochemical diagrams."""

import numpy as np

from .ions import ions_WEIGHT, ions_CHARGE


MAJOR_IONS = ('Ca', 'Mg', 'Na', 'K', 'HCO3', 'CO3', 'Cl', 'SO4')


def major_ion_meq(frame, unit):
    """Return major ions in meq/L after checking concentrations and ion totals."""
    if unit not in ('mg/L', 'meq/L'):
        raise ValueError('Concentration unit must be mg/L or meq/L.')
    if frame.empty or not frame.columns.is_unique:
        raise ValueError('Provide non-empty chemistry with unique column names.')
    values = frame[list(MAJOR_IONS)].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError('Major-ion concentrations must be finite numeric measurements.')
    if (values < 0).any():
        raise ValueError('Major-ion concentrations must be nonnegative; correct negative measurements before plotting.')
    if unit == 'mg/L':
        values = values * np.array([abs(ions_CHARGE[ion]) / ions_WEIGHT[ion] for ion in MAJOR_IONS])
    with np.errstate(over='ignore'):
        cations, anions = values[:, :4].sum(axis=1), values[:, 4:].sum(axis=1)
    if not np.isfinite(cations).all() or not np.isfinite(anions).all():
        raise ValueError('Ion totals overflow; check the concentration magnitudes.')
    invalid = (cations <= 0) | (anions <= 0)
    if invalid.any():
        rows = ', '.join(str(i + 1) for i in np.flatnonzero(invalid)[:12])
        raise ValueError('Cation and anion totals must both be positive for every sample. '
                         'Undefined composition in plot input row(s): ' + rows + '.')
    return values
