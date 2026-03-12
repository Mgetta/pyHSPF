# -*- coding: utf-8 -*-
"""Tests for hspf.xarray_dataset — DataFrame-to-xarray converters."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from hspf.xarray_dataset import timeseries_to_xarray, dataframe_to_xarray


# ---------------------------------------------------------------------------
# Helpers — simulate the pandas output of existing HBN / UCI methods
# ---------------------------------------------------------------------------

def _wide_timeseries(n_time=5, opnids=None):
    """Simulate output of hbn.get_multiple_timeseries (wide format).

    Returns a DataFrame: index = DatetimeIndex, columns = opnid (int).
    """
    if opnids is None:
        opnids = [1, 2, 3]
    idx = pd.date_range("2000-01-01", periods=n_time, freq="D")
    rng = np.random.default_rng(42)
    data = {oid: rng.random(n_time) for oid in opnids}
    df = pd.DataFrame(data, index=idx)
    df.index.name = "datetime"
    return df


def _single_timeseries(n_time=5, opnid=1):
    """Simulate output of hbn.get_time_series (Series)."""
    idx = pd.date_range("2000-01-01", periods=n_time, freq="D")
    return pd.Series(np.arange(1.0, n_time + 1), index=idx, name=opnid)


def _subwatersheds_df():
    """Simulate output of uci.network.subwatersheds().reset_index()."""
    return pd.DataFrame({
        "TVOLNO": [1, 1, 2, 2],
        "SVOLNO": [101, 102, 103, 104],
        "SVOL": ["PERLND", "IMPLND", "PERLND", "IMPLND"],
        "AFACTR": [10.0, 5.0, 20.0, 8.0],
        "LSID": ["Forest", "Urban", "Forest", "Urban"],
        "MLNO": [1, 1, 1, 1],
    })


# ---------------------------------------------------------------------------
# timeseries_to_xarray — wide DataFrame
# ---------------------------------------------------------------------------

class TestTimeseriesToXarrayWide:
    def test_dims(self):
        ds = timeseries_to_xarray(_wide_timeseries())
        assert "time" in ds.dims
        assert "opnid" in ds.dims

    def test_default_var_name(self):
        ds = timeseries_to_xarray(_wide_timeseries())
        assert "value" in ds.data_vars

    def test_custom_constituent_name(self):
        ds = timeseries_to_xarray(_wide_timeseries(), constituent="PERO")
        assert "PERO" in ds.data_vars

    def test_opnid_values(self):
        ds = timeseries_to_xarray(_wide_timeseries(opnids=[10, 20]))
        np.testing.assert_array_equal(ds.coords["opnid"].values, [10, 20])

    def test_time_values(self):
        ds = timeseries_to_xarray(_wide_timeseries(n_time=3))
        assert len(ds.coords["time"]) == 3

    def test_operation_coord(self):
        ds = timeseries_to_xarray(_wide_timeseries(), operation="PERLND")
        assert "operation" in ds.coords
        assert all(v == "PERLND" for v in ds.coords["operation"].values)

    def test_no_operation_when_omitted(self):
        ds = timeseries_to_xarray(_wide_timeseries())
        assert "operation" not in ds.coords

    def test_activity_attribute(self):
        ds = timeseries_to_xarray(
            _wide_timeseries(), activity="PWATER"
        )
        assert ds.attrs["activity"] == "PWATER"

    def test_data_values(self):
        df = _wide_timeseries(n_time=3, opnids=[1])
        ds = timeseries_to_xarray(df, constituent="X")
        np.testing.assert_array_almost_equal(
            ds["X"].sel(opnid=1).values, df[1].values
        )


# ---------------------------------------------------------------------------
# timeseries_to_xarray — Series input
# ---------------------------------------------------------------------------

class TestTimeseriesToXarraySeries:
    def test_series_to_dataset(self):
        s = _single_timeseries(opnid=42)
        ds = timeseries_to_xarray(s, constituent="ROVOL")
        assert "ROVOL" in ds.data_vars
        assert "opnid" in ds.dims
        np.testing.assert_array_equal(ds.coords["opnid"].values, [42])

    def test_series_values(self):
        s = _single_timeseries(n_time=4, opnid=1)
        ds = timeseries_to_xarray(s, constituent="Q")
        np.testing.assert_array_almost_equal(
            ds["Q"].sel(opnid=1).values, [1.0, 2.0, 3.0, 4.0]
        )


# ---------------------------------------------------------------------------
# dataframe_to_xarray
# ---------------------------------------------------------------------------

class TestDataframeToXarray:
    def test_basic_conversion(self):
        df = _subwatersheds_df()
        ds = dataframe_to_xarray(df)
        assert isinstance(ds, xr.Dataset)

    def test_index_col(self):
        df = _subwatersheds_df()
        ds = dataframe_to_xarray(df, index_col="SVOLNO", index_dim="opnid")
        assert "opnid" in ds.dims
        np.testing.assert_array_equal(
            ds.coords["opnid"].values, [101, 102, 103, 104]
        )

    def test_data_vars_from_columns(self):
        df = _subwatersheds_df()
        ds = dataframe_to_xarray(df, index_col="SVOLNO", index_dim="opnid")
        assert "AFACTR" in ds.data_vars
        assert "LSID" in ds.data_vars
        assert "TVOLNO" in ds.data_vars

    def test_values_preserved(self):
        df = _subwatersheds_df()
        ds = dataframe_to_xarray(df, index_col="SVOLNO", index_dim="opnid")
        assert float(ds["AFACTR"].sel(opnid=101).values) == 10.0

    def test_uses_existing_index(self):
        df = _subwatersheds_df().set_index("SVOLNO")
        ds = dataframe_to_xarray(df, index_dim="opnid")
        assert "opnid" in ds.dims

    def test_default_dim_name(self):
        df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        ds = dataframe_to_xarray(df)
        assert "index" in ds.dims


# ---------------------------------------------------------------------------
# Joinability — datasets from different sources can merge
# ---------------------------------------------------------------------------

class TestJoinability:
    def test_timeseries_merge_with_metadata(self):
        """Timeseries and metadata datasets join on opnid."""
        ts_df = _wide_timeseries(opnids=[101, 102])
        ds_ts = timeseries_to_xarray(
            ts_df, operation="PERLND", constituent="PERO"
        )

        meta_df = _subwatersheds_df()
        ds_meta = dataframe_to_xarray(
            meta_df, index_col="SVOLNO", index_dim="opnid"
        )

        merged = ds_ts.merge(ds_meta, join="inner")
        assert "PERO" in merged.data_vars
        assert "AFACTR" in merged.data_vars
        # Both opnids 101 and 102 should be present
        np.testing.assert_array_equal(
            sorted(merged.coords["opnid"].values), [101, 102]
        )

    def test_two_timeseries_concat(self):
        """Two timeseries datasets with different opnids can concatenate."""
        ds1 = timeseries_to_xarray(
            _wide_timeseries(opnids=[1, 2]),
            operation="PERLND", constituent="PERO",
        )
        ds2 = timeseries_to_xarray(
            _wide_timeseries(opnids=[3, 4]),
            operation="PERLND", constituent="PERO",
        )
        combined = xr.concat([ds1, ds2], dim="opnid")
        assert len(combined.coords["opnid"]) == 4
