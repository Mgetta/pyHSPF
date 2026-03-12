# -*- coding: utf-8 -*-
"""Tests for hspf.xarray_dataset — xarray Dataset construction from HBN and UCI."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from unittest.mock import MagicMock

from hspf.xarray_dataset import hbn_to_xarray, uci_to_xarray, build_model_dataset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hbn_class(data_frames=None):
    """Create a minimal mock hbnClass with data_frames already populated."""
    hbn = MagicMock()
    if data_frames is None:
        idx = pd.date_range("2000-01-01", periods=5, freq="D")
        df1 = pd.DataFrame(
            {"PERO": [1.0, 2.0, 3.0, 4.0, 5.0], "SURO": [0.1, 0.2, 0.3, 0.4, 0.5]},
            index=idx,
        )
        df2 = pd.DataFrame(
            {"PERO": [5.0, 4.0, 3.0, 2.0, 1.0], "SURO": [0.5, 0.4, 0.3, 0.2, 0.1]},
            index=idx,
        )
        data_frames = {
            "PERLND_PWATER_001_3": df1,
            "PERLND_PWATER_002_3": df2,
        }
    hbn.data_frames = data_frames
    hbn.mapn = {}
    # Not an interface
    del hbn.hbns
    return hbn


def _make_hbn_interface(hbn_classes=None):
    """Create a minimal mock hbnInterface wrapping one or more hbnClass."""
    interface = MagicMock()
    interface.hbns = hbn_classes or [_make_hbn_class()]
    return interface


def _make_mixed_hbn():
    """HBN with both PERLND and RCHRES segments (same opnids)."""
    idx = pd.date_range("2000-01-01", periods=5, freq="D")
    return _make_hbn_class(data_frames={
        "PERLND_PWATER_001_3": pd.DataFrame({"PERO": [1.0, 2.0, 3.0, 4.0, 5.0]}, index=idx),
        "RCHRES_HYDR_001_3": pd.DataFrame({"ROVOL": [10.0, 20.0, 30.0, 40.0, 50.0]}, index=idx),
    })


def _make_uci():
    """Create a minimal mock UCI with OPN SEQUENCE and subwatersheds."""
    uci = MagicMock()
    uci.name = "TestModel"

    opnseq = pd.DataFrame({
        "OPERATION": ["PERLND", "PERLND", "RCHRES"],
        "SEGMENT": [1, 2, 1],
    })
    uci.table.return_value = opnseq

    subwatersheds = pd.DataFrame({
        "TVOLNO": [1, 1],
        "SVOLNO": [1, 2],
        "SVOL": ["PERLND", "PERLND"],
        "AFACTR": [10.0, 20.0],
        "LSID": ["Forest", "Cropland"],
        "MLNO": [1, 1],
    })
    uci.network.subwatersheds.return_value = subwatersheds

    uci.valid_opnids = {
        "PERLND": [1, 2],
        "IMPLND": [],
        "RCHRES": [1],
    }

    uci.opnid_dict = {
        "PERLND": pd.DataFrame({"metzone": [1, 1]}, index=[1, 2]),
    }

    uci.network.graph.successors.return_value = iter([])

    return uci


# ---------------------------------------------------------------------------
# hbn_to_xarray
# ---------------------------------------------------------------------------

class TestHbnToXarray:
    def test_basic_dimensions(self):
        ds = hbn_to_xarray(_make_hbn_class())
        assert "time" in ds.dims
        assert "segment" in ds.dims

    def test_constituent_variables(self):
        ds = hbn_to_xarray(_make_hbn_class())
        assert "PERO" in ds.data_vars
        assert "SURO" in ds.data_vars

    def test_segment_labels(self):
        ds = hbn_to_xarray(_make_hbn_class())
        segs = sorted(ds.coords["segment"].values)
        assert segs == ["PERLND_001", "PERLND_002"]

    def test_time_coords(self):
        ds = hbn_to_xarray(_make_hbn_class())
        assert len(ds.coords["time"]) == 5
        assert ds.coords["time"].values[0] == np.datetime64("2000-01-01")

    def test_operation_coord(self):
        ds = hbn_to_xarray(_make_hbn_class())
        assert "operation" in ds.coords
        assert list(ds.coords["operation"].values) == ["PERLND", "PERLND"]

    def test_opnid_coord(self):
        ds = hbn_to_xarray(_make_hbn_class())
        assert "opnid" in ds.coords
        assert sorted(ds.coords["opnid"].values) == [1, 2]

    def test_activity_coord(self):
        ds = hbn_to_xarray(_make_hbn_class())
        assert "activity" in ds.coords
        assert list(ds.coords["activity"].values) == ["PWATER", "PWATER"]

    def test_data_values(self):
        ds = hbn_to_xarray(_make_hbn_class())
        pero_1 = ds["PERO"].sel(segment="PERLND_001").values
        np.testing.assert_array_almost_equal(pero_1, [1.0, 2.0, 3.0, 4.0, 5.0])

    def test_mixed_operations_unique_segments(self):
        """PERLND_001 and RCHRES_001 should be distinct segments."""
        ds = hbn_to_xarray(_make_mixed_hbn())
        segs = sorted(ds.coords["segment"].values)
        assert "PERLND_001" in segs
        assert "RCHRES_001" in segs
        assert len(segs) == 2

    def test_mixed_operation_selection(self):
        """Can select only RCHRES segments using the operation coordinate."""
        ds = hbn_to_xarray(_make_mixed_hbn())
        rchres_mask = ds.coords["operation"] == "RCHRES"
        sub = ds.sel(segment=rchres_mask)
        assert list(sub.coords["segment"].values) == ["RCHRES_001"]

    def test_hbn_interface(self):
        ds = hbn_to_xarray(_make_hbn_interface())
        assert isinstance(ds, xr.Dataset)
        assert "PERO" in ds.data_vars

    def test_empty_hbn(self):
        ds = hbn_to_xarray(_make_hbn_class(data_frames={}))
        assert len(ds.data_vars) == 0

    def test_multiple_tcodes_suffixed(self):
        idx_d = pd.date_range("2000-01-01", periods=3, freq="D")
        idx_y = pd.date_range("2000-01-01", periods=2, freq="YE")
        data_frames = {
            "PERLND_PWATER_001_3": pd.DataFrame({"PERO": [1.0, 2.0, 3.0]}, index=idx_d),
            "PERLND_PWATER_001_5": pd.DataFrame({"PERO": [10.0, 20.0]}, index=idx_y),
        }
        ds = hbn_to_xarray(_make_hbn_class(data_frames=data_frames))
        assert "PERO_3" in ds.data_vars
        assert "PERO_5" in ds.data_vars

    def test_source_attribute(self):
        ds = hbn_to_xarray(_make_hbn_class())
        assert ds.attrs["source"] == "hbn"


# ---------------------------------------------------------------------------
# uci_to_xarray
# ---------------------------------------------------------------------------

class TestUciToXarray:
    def test_basic_structure(self):
        ds = uci_to_xarray(_make_uci())
        assert isinstance(ds, xr.Dataset)
        assert "segment" in ds.coords

    def test_segment_labels(self):
        ds = uci_to_xarray(_make_uci())
        segs = list(ds.coords["segment"].values)
        assert "PERLND_001" in segs
        assert "PERLND_002" in segs
        assert "RCHRES_001" in segs

    def test_operation_variable(self):
        ds = uci_to_xarray(_make_uci())
        assert "operation" in ds.data_vars
        ops = list(ds["operation"].values)
        assert "PERLND" in ops
        assert "RCHRES" in ops

    def test_subwatershed_metadata(self):
        ds = uci_to_xarray(_make_uci())
        assert "area" in ds.data_vars
        assert "landcover" in ds.data_vars
        assert "downstream_rchres" in ds.data_vars

    def test_area_values(self):
        ds = uci_to_xarray(_make_uci())
        area_p1 = float(ds["area"].sel(segment="PERLND_001").values)
        assert area_p1 == 10.0

    def test_source_attribute(self):
        ds = uci_to_xarray(_make_uci())
        assert ds.attrs["source"] == "uci"

    def test_model_name_attribute(self):
        ds = uci_to_xarray(_make_uci())
        assert ds.attrs["model_name"] == "TestModel"


# ---------------------------------------------------------------------------
# build_model_dataset
# ---------------------------------------------------------------------------

class TestBuildModelDataset:
    def test_merged_contains_hbn_vars(self):
        ds = build_model_dataset(_make_hbn_class(), _make_uci())
        assert "PERO" in ds.data_vars
        assert "SURO" in ds.data_vars

    def test_merged_has_metadata_coords(self):
        ds = build_model_dataset(_make_hbn_class(), _make_uci())
        assert "area" in ds.coords or "area" in ds.data_vars

    def test_hbn_only(self):
        ds = build_model_dataset(_make_hbn_class(), uci=None)
        assert "PERO" in ds.data_vars
        assert ds.attrs["source"] == "hbn"

    def test_uci_only(self):
        ds = build_model_dataset(hbn=None, uci=_make_uci())
        assert "operation" in ds.data_vars
        assert ds.attrs["source"] == "uci"

    def test_both_none(self):
        ds = build_model_dataset(hbn=None, uci=None)
        assert len(ds.data_vars) == 0

    def test_source_attribute(self):
        ds = build_model_dataset(_make_hbn_class(), _make_uci())
        assert ds.attrs["source"] == "hbn+uci"

    def test_model_name_attribute(self):
        ds = build_model_dataset(_make_hbn_class(), _make_uci())
        assert ds.attrs["model_name"] == "TestModel"
