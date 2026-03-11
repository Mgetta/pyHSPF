# -*- coding: utf-8 -*-
"""
Model-agnostic computation layer for HSPF reports.

This sub-package contains pure analytical functions that operate on generic
pandas DataFrames and Series — no HSPF-specific objects (uci, hbn, etc.).
The goal is to make the core computations reusable by any watershed model
(SWMM, SWAT, HEC-HMS, etc.).

Submodules
----------
yields
    Constituent yield and load analytics (compute_yield, average_annual, etc.).
"""
