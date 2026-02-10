# -*- coding: utf-8 -*-
"""
Reports module for generating HSPF model summaries.

This module provides methods for generating various model summaries that
require information across the various objects (hbn, uci, wdm, and any
static datasources like model_landcover.csv).

Submodules:
-----------
- base: Contains the main Reports class interface
- hydrology: Water budget, runoff, precipitation, and ET reports
- sediment: Sediment budget and scour reports
- loading: Constituent loading reports
- allocations: Allocation and fate analysis
- phosphorous: Phosphorous-specific reports
- utils: Shared utility functions
"""

from .base import Reports
from . import hydrology
from . import sediment
from . import loading
from . import allocations
from . import phosphorous
from . import utils

__all__ = [
    'Reports',
    'hydrology',
    'sediment',
    'loading',
    'allocations',
    'phosphorous',
    'utils',
]
