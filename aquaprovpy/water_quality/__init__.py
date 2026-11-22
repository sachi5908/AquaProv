"""Water-quality indices with separate WQI and drinking-water calculations."""

from .wqi import weighted_arithmetic, groundwater_wqi, ccme_wqi
from .dwqi import drinking_water_index

__all__ = ['weighted_arithmetic', 'groundwater_wqi', 'ccme_wqi', 'drinking_water_index']
