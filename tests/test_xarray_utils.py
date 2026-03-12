# -*- coding: utf-8 -*-
"""
Tests for :mod:`hspf.xarray_utils`.
"""
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from hspf.xarray_utils import (
    HspfDatasetCollection,
    MAX_OPNID,
    OPERATIONS,
    PANDAS_FREQ,
    TIMESTEP_LABELS,
    UNITS_BY_VARIABLE,
    TimeStep,
    create_timestep_dataset,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

MODELS = ["baseline", "scenario1"]
OPS = ["PERLND", "IMPLND", "RCHRES"]
OPNIDS = [101, 202, 303]
VARIABLES = ["PERO", "SURO", "Q", "TP"]
DAILY_INDEX = pd.date_range("2000-01-01", periods=365, freq="D")
MONTHLY_INDEX = pd.date_range("2000-01-01", periods=12, freq="ME")


def _daily_ds():
    return create_timestep_dataset(
        timestep=TimeStep.DAILY,
        time_index=DAILY_INDEX,
        models=MODELS,
        operations=OPS,
        opnids=OPNIDS,
        variables=VARIABLES,
    )


def _monthly_ds():
    return create_timestep_dataset(
        timestep=TimeStep.MONTHLY,
        time_index=MONTHLY_INDEX,
        models=MODELS,
        operations=OPS,
        opnids=OPNIDS,
        variables=VARIABLES,
    )


# ---------------------------------------------------------------------------
# TimeStep enum
# ---------------------------------------------------------------------------


def test_timestep_values():
    assert TimeStep.HOURLY == 2
    assert TimeStep.DAILY == 3
    assert TimeStep.MONTHLY == 4
    assert TimeStep.YEARLY == 5


def test_timestep_is_int():
    assert isinstance(TimeStep.DAILY, int)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_timestep_labels_keys():
    assert set(TIMESTEP_LABELS.keys()) == {
        TimeStep.HOURLY,
        TimeStep.DAILY,
        TimeStep.MONTHLY,
        TimeStep.YEARLY,
    }


def test_timestep_labels_values():
    assert TIMESTEP_LABELS[TimeStep.HOURLY] == "hourly"
    assert TIMESTEP_LABELS[TimeStep.DAILY] == "daily"
    assert TIMESTEP_LABELS[TimeStep.MONTHLY] == "monthly"
    assert TIMESTEP_LABELS[TimeStep.YEARLY] == "yearly"


def test_pandas_freq_values():
    assert PANDAS_FREQ[TimeStep.HOURLY] == "h"
    assert PANDAS_FREQ[TimeStep.DAILY] == "D"
    assert PANDAS_FREQ[TimeStep.MONTHLY] == "ME"
    assert PANDAS_FREQ[TimeStep.YEARLY] == "YE"


def test_operations_tuple():
    assert OPERATIONS == ("PERLND", "IMPLND", "RCHRES")


def test_max_opnid():
    assert MAX_OPNID == 999


def test_units_by_variable_known_entries():
    assert UNITS_BY_VARIABLE["Q"] == "cfs"
    assert UNITS_BY_VARIABLE["TSS"] == "mg/l"
    assert UNITS_BY_VARIABLE["PERO"] == "inches"
    assert UNITS_BY_VARIABLE["SURO"] == "inches"
    assert UNITS_BY_VARIABLE["ROVOL"] == "acre-ft"


# ---------------------------------------------------------------------------
# create_timestep_dataset – dimensions and shape
# ---------------------------------------------------------------------------


def test_create_dimensions_present():
    ds = _daily_ds()
    for dim in ("model", "time", "operation", "opnid", "variable"):
        assert dim in ds.dims


def test_create_shape():
    ds = _daily_ds()
    assert ds["value"].shape == (
        len(MODELS),
        len(DAILY_INDEX),
        len(OPS),
        len(OPNIDS),
        len(VARIABLES),
    )


def test_create_time_length_daily():
    ds = _daily_ds()
    assert ds.sizes["time"] == 365


def test_create_time_length_monthly():
    ds = _monthly_ds()
    assert ds.sizes["time"] == 12


def test_create_coords_model():
    ds = _daily_ds()
    assert list(ds.coords["model"].values) == MODELS


def test_create_coords_operation():
    ds = _daily_ds()
    assert list(ds.coords["operation"].values) == OPS


def test_create_coords_opnid():
    ds = _daily_ds()
    assert list(ds.coords["opnid"].values) == OPNIDS


def test_create_coords_variable():
    ds = _daily_ds()
    assert list(ds.coords["variable"].values) == VARIABLES


# ---------------------------------------------------------------------------
# create_timestep_dataset – initial values
# ---------------------------------------------------------------------------


def test_create_value_all_nan():
    ds = _daily_ds()
    assert np.all(np.isnan(ds["value"].values))


# ---------------------------------------------------------------------------
# create_timestep_dataset – units coordinate
# ---------------------------------------------------------------------------


def test_units_coord_present():
    ds = _daily_ds()
    assert "units" in ds.coords


def test_units_coord_not_dimension():
    ds = _daily_ds()
    assert "units" not in ds.dims


def test_units_coord_on_variable_dim():
    ds = _daily_ds()
    assert ds.coords["units"].dims == ("variable",)


def test_units_coord_known_variable():
    ds = _daily_ds()
    units = dict(zip(ds.coords["variable"].values, ds.coords["units"].values))
    assert units["PERO"] == "inches"
    assert units["Q"] == "cfs"
    assert units["TP"] == "mg/l"


def test_units_coord_unknown_variable():
    ds = create_timestep_dataset(
        timestep=TimeStep.DAILY,
        time_index=DAILY_INDEX,
        models=MODELS,
        operations=OPS,
        opnids=OPNIDS,
        variables=["UNKNOWN_VAR"],
    )
    assert ds.coords["units"].values[0] == "unknown"


# ---------------------------------------------------------------------------
# create_timestep_dataset – attrs
# ---------------------------------------------------------------------------


def test_attrs_timestep_label():
    ds = _daily_ds()
    assert ds.attrs["timestep"] == "daily"


def test_attrs_timestep_code():
    ds = _daily_ds()
    assert ds.attrs["timestep_code"] == 3


def test_attrs_conventions():
    ds = _daily_ds()
    assert ds.attrs["Conventions"] == "CF-1.8"


def test_attrs_source():
    ds = _daily_ds()
    assert ds.attrs["source"] == "pyHSPF"


def test_attrs_hourly():
    ds = create_timestep_dataset(
        timestep=TimeStep.HOURLY,
        time_index=pd.date_range("2000-01-01", periods=24, freq="h"),
        models=["m"],
        operations=["PERLND"],
        opnids=[1],
        variables=["SURO"],
    )
    assert ds.attrs["timestep"] == "hourly"
    assert ds.attrs["timestep_code"] == 2


# ---------------------------------------------------------------------------
# create_timestep_dataset – opnid validation
# ---------------------------------------------------------------------------


def test_opnid_zero_raises():
    with pytest.raises(ValueError, match="1–999"):
        create_timestep_dataset(
            timestep=TimeStep.DAILY,
            time_index=DAILY_INDEX,
            models=MODELS,
            operations=OPS,
            opnids=[0, 101],
            variables=VARIABLES,
        )


def test_opnid_1000_raises():
    with pytest.raises(ValueError, match="1–999"):
        create_timestep_dataset(
            timestep=TimeStep.DAILY,
            time_index=DAILY_INDEX,
            models=MODELS,
            operations=OPS,
            opnids=[1000],
            variables=VARIABLES,
        )


def test_opnid_negative_raises():
    with pytest.raises(ValueError, match="1–999"):
        create_timestep_dataset(
            timestep=TimeStep.DAILY,
            time_index=DAILY_INDEX,
            models=MODELS,
            operations=OPS,
            opnids=[-1],
            variables=VARIABLES,
        )


def test_opnid_boundary_values_ok():
    ds = create_timestep_dataset(
        timestep=TimeStep.DAILY,
        time_index=DAILY_INDEX,
        models=["m"],
        operations=["PERLND"],
        opnids=[1, 999],
        variables=["SURO"],
    )
    assert list(ds.coords["opnid"].values) == [1, 999]


# ---------------------------------------------------------------------------
# HspfDatasetCollection – add / __getitem__ / __contains__
# ---------------------------------------------------------------------------


def test_collection_add_and_getitem():
    col = HspfDatasetCollection()
    ds = _daily_ds()
    col.add(ds)
    assert col["daily"] is ds


def test_collection_contains_true():
    col = HspfDatasetCollection()
    col.add(_daily_ds())
    assert "daily" in col


def test_collection_contains_false():
    col = HspfDatasetCollection()
    col.add(_daily_ds())
    assert "monthly" not in col


def test_collection_add_multiple():
    col = HspfDatasetCollection()
    col.add(_daily_ds())
    col.add(_monthly_ds())
    assert "daily" in col
    assert "monthly" in col


# ---------------------------------------------------------------------------
# HspfDatasetCollection – keys / items
# ---------------------------------------------------------------------------


def test_collection_keys():
    col = HspfDatasetCollection()
    col.add(_daily_ds())
    col.add(_monthly_ds())
    assert set(col.keys()) == {"daily", "monthly"}


def test_collection_items():
    col = HspfDatasetCollection()
    daily = _daily_ds()
    monthly = _monthly_ds()
    col.add(daily)
    col.add(monthly)
    d = dict(col.items())
    assert d["daily"] is daily
    assert d["monthly"] is monthly


# ---------------------------------------------------------------------------
# HspfDatasetCollection – variables_at
# ---------------------------------------------------------------------------


def test_variables_at_returns_list():
    col = HspfDatasetCollection()
    col.add(_daily_ds())
    assert col.variables_at("daily") == VARIABLES


def test_variables_at_different_resolutions():
    variables_daily = ["PERO", "SURO"]
    variables_monthly = ["Q", "TP"]
    daily = create_timestep_dataset(
        timestep=TimeStep.DAILY,
        time_index=DAILY_INDEX,
        models=MODELS,
        operations=OPS,
        opnids=OPNIDS,
        variables=variables_daily,
    )
    monthly = create_timestep_dataset(
        timestep=TimeStep.MONTHLY,
        time_index=MONTHLY_INDEX,
        models=MODELS,
        operations=OPS,
        opnids=OPNIDS,
        variables=variables_monthly,
    )
    col = HspfDatasetCollection()
    col.add(daily)
    col.add(monthly)
    assert col.variables_at("daily") == variables_daily
    assert col.variables_at("monthly") == variables_monthly


# ---------------------------------------------------------------------------
# HspfDatasetCollection – select
# ---------------------------------------------------------------------------


def test_select_returns_present_resolutions_only():
    variables_daily = ["PERO", "SURO"]
    variables_monthly = ["Q", "TP"]
    daily = create_timestep_dataset(
        timestep=TimeStep.DAILY,
        time_index=DAILY_INDEX,
        models=MODELS,
        operations=OPS,
        opnids=OPNIDS,
        variables=variables_daily,
    )
    monthly = create_timestep_dataset(
        timestep=TimeStep.MONTHLY,
        time_index=MONTHLY_INDEX,
        models=MODELS,
        operations=OPS,
        opnids=OPNIDS,
        variables=variables_monthly,
    )
    col = HspfDatasetCollection()
    col.add(daily)
    col.add(monthly)

    result = col.select("baseline", "PERLND", 101, "PERO")
    assert "daily" in result
    assert "monthly" not in result


def test_select_returns_correct_shape():
    col = HspfDatasetCollection()
    col.add(_daily_ds())
    result = col.select("baseline", "PERLND", 101, "PERO")
    da = result["daily"]
    # After selecting model, operation, opnid, variable the remaining dim is time
    assert da.dims == ("time",)
    assert da.sizes["time"] == 365


def test_select_variable_absent_returns_empty():
    col = HspfDatasetCollection()
    col.add(_daily_ds())
    result = col.select("baseline", "PERLND", 101, "NONEXISTENT")
    assert result == {}


def test_select_across_multiple_resolutions():
    daily = create_timestep_dataset(
        timestep=TimeStep.DAILY,
        time_index=DAILY_INDEX,
        models=MODELS,
        operations=OPS,
        opnids=OPNIDS,
        variables=["Q"],
    )
    monthly = create_timestep_dataset(
        timestep=TimeStep.MONTHLY,
        time_index=MONTHLY_INDEX,
        models=MODELS,
        operations=OPS,
        opnids=OPNIDS,
        variables=["Q"],
    )
    col = HspfDatasetCollection()
    col.add(daily)
    col.add(monthly)
    result = col.select("baseline", "RCHRES", 303, "Q")
    assert set(result.keys()) == {"daily", "monthly"}
    assert result["daily"].sizes["time"] == 365
    assert result["monthly"].sizes["time"] == 12


# ---------------------------------------------------------------------------
# HspfDatasetCollection – to_dict
# ---------------------------------------------------------------------------


def test_to_dict_returns_dict():
    col = HspfDatasetCollection()
    col.add(_daily_ds())
    d = col.to_dict()
    assert isinstance(d, dict)
    assert "daily" in d


def test_to_dict_is_copy():
    col = HspfDatasetCollection()
    col.add(_daily_ds())
    d = col.to_dict()
    d["extra"] = None
    # The original collection should not be affected
    assert "extra" not in col
