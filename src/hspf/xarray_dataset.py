# -*- coding: utf-8 -*-
"""
Convert pandas DataFrame outputs from HSPF HBN and UCI methods into
xarray Datasets.

These converter functions define the xarray structure for HSPF data.
They accept the pandas DataFrames already returned by existing methods
(``get_multiple_timeseries``, ``get_time_series``, ``subwatersheds``,
etc.) and return well-structured xarray Datasets that can be joined
together on shared dimensions.

Public API
----------
* ``timeseries_to_xarray``  – wide-format timeseries → xr.Dataset
* ``dataframe_to_xarray``   – metadata DataFrame → xr.Dataset

``operation`` and ``opnid`` are always kept as separate fields.

Examples
--------
>>> # Convert HBN timeseries output to xarray
>>> df = hbn.get_multiple_timeseries('PERLND', 3, 'PERO')
>>> x1 = timeseries_to_xarray(df, operation='PERLND', constituent='PERO')
>>>
>>> # Convert UCI metadata to xarray
>>> df_sw = uci.network.subwatersheds().reset_index()
>>> x2 = dataframe_to_xarray(df_sw, index_col='SVOLNO', index_dim='opnid')
>>>
>>> # Join them on the shared opnid dimension
>>> merged = x1.merge(x2, join='inner')
"""

import numpy as np
import pandas as pd
import xarray as xr


# ---------------------------------------------------------------------------
# Timeseries converter
# ---------------------------------------------------------------------------

def timeseries_to_xarray(df, operation=None, constituent=None, activity=None):
    """Convert a wide-format timeseries DataFrame to an xarray Dataset.

    Designed for the output of ``hbnClass.get_multiple_timeseries`` and
    similar methods that return a DataFrame with a DatetimeIndex and
    integer opnid columns.

    Parameters
    ----------
    df : pd.DataFrame or pd.Series
        Timeseries data.

        * **DataFrame** (wide format): index is DatetimeIndex, each
          column is an opnid (int).  This is the shape returned by
          ``get_multiple_timeseries``.
        * **Series**: index is DatetimeIndex, ``name`` is used as the
          single opnid.  This is the shape returned by
          ``get_time_series``.

    operation : str, optional
        HSPF operation type (``'PERLND'``, ``'IMPLND'``, or
        ``'RCHRES'``).  Stored as a scalar coordinate on ``opnid``.
    constituent : str, optional
        Name for the data variable (e.g. ``'PERO'``, ``'ROVOL'``).
        Defaults to ``'value'``.
    activity : str, optional
        HSPF activity section (e.g. ``'PWATER'``, ``'HYDR'``).
        Stored as a Dataset attribute when provided.

    Returns
    -------
    xr.Dataset
        Dimensions: ``time``, ``opnid``.
        Data variable: *constituent* name.
        Coordinates: ``operation`` (on ``opnid`` dim, if provided).

    Examples
    --------
    >>> df = hbn.get_multiple_timeseries('PERLND', 3, 'PERO')
    >>> ds = timeseries_to_xarray(df, operation='PERLND', constituent='PERO')
    >>> ds
    <xarray.Dataset>
    Dimensions:    (time: ..., opnid: ...)
    Coordinates:
      * time       (time) datetime64[ns] ...
      * opnid      (opnid) int64 1 2 3 ...
        operation  (opnid) <U6 'PERLND' 'PERLND' ...
    Data variables:
        PERO       (time, opnid) float64 ...
    """
    var_name = constituent or "value"

    # Handle Series input (single opnid from get_time_series)
    if isinstance(df, pd.Series):
        opnid_val = df.name if df.name is not None else 0
        df = df.to_frame(name=opnid_val)

    # Ensure integer opnid columns
    opnids = [int(c) for c in df.columns]

    da = xr.DataArray(
        df.values,
        dims=["time", "opnid"],
        coords={
            "time": df.index.values,
            "opnid": opnids,
        },
    )

    ds = xr.Dataset({var_name: da})

    if operation is not None:
        ds.coords["operation"] = ("opnid", [operation] * len(opnids))

    if activity is not None:
        ds.attrs["activity"] = activity

    return ds


# ---------------------------------------------------------------------------
# General DataFrame converter
# ---------------------------------------------------------------------------

def dataframe_to_xarray(df, index_col=None, index_dim=None):
    """Convert a pandas DataFrame to an xarray Dataset.

    A general-purpose converter for metadata DataFrames such as the
    output of ``uci.network.subwatersheds()`` or ``uci.table(...)``.

    Parameters
    ----------
    df : pd.DataFrame
        Any pandas DataFrame.
    index_col : str, optional
        Column to use as the xarray dimension.  If ``None``, the
        existing DataFrame index is used.
    index_dim : str, optional
        Name for the resulting xarray dimension.  Defaults to
        *index_col* if given, otherwise the DataFrame index name, or
        ``'index'``.

    Returns
    -------
    xr.Dataset
        One dimension corresponding to the chosen index.  Each
        remaining column becomes a data variable.

    Examples
    --------
    >>> df_sw = uci.network.subwatersheds().reset_index()
    >>> ds = dataframe_to_xarray(df_sw, index_col='SVOLNO', index_dim='opnid')
    >>> ds
    <xarray.Dataset>
    Dimensions:  (opnid: ...)
    Coordinates:
      * opnid    (opnid) int64 ...
    Data variables:
        TVOLNO   (opnid) int64 ...
        SVOL     (opnid) object ...
        AFACTR   (opnid) float64 ...
        ...
    """
    if index_col is not None:
        df = df.set_index(index_col)

    dim_name = index_dim or df.index.name or "index"

    ds = xr.Dataset.from_dataframe(df)

    # Rename the index dimension if needed
    current_dim = df.index.name or "index"
    if current_dim != dim_name:
        ds = ds.rename({current_dim: dim_name})

    return ds
