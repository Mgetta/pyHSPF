# -*- coding: utf-8 -*-
"""
Model-agnostic computation layer for HSPF reports.

This sub-package contains pure analytical functions that operate on generic
pandas DataFrames and Series — no HSPF-specific objects (uci, hbn, etc.).
The goal is to make the core computations reusable by any watershed model
(SWMM, SWAT, HEC-HMS, etc.).

Submodules
----------
timeseries
    Generic temporal filtering and aggregation (filter_years, filter_months, aggregate).
loading
    Load computation analytics (compute_load, compute_loading_rate).
"""
