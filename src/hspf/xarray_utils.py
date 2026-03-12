# -*- coding: utf-8 -*-
"""
xarray-based dataset schema for storing HSPF model outputs across multiple
time-step resolutions.

HSPF writes binary outputs (HBN files) at different time-step codes:
  2 = hourly, 3 = daily, 4 = monthly, 5 = yearly.

Because different variables may be stored at different resolutions their time
axes have different lengths and cannot share a single ``time`` dimension in a
rectangular xarray Dataset without massive NaN padding.  This module provides
a *dict-of-Datasets* approach: one ``xr.Dataset`` per time-step resolution,
wrapped in the lightweight :class:`HspfDatasetCollection` container class.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Dict, List

import numpy as np
import pandas as pd
import xarray as xr

# ---------------------------------------------------------------------------
# TimeStep enum
# ---------------------------------------------------------------------------


class TimeStep(IntEnum):
    """HBN time-step codes.

    Values match the integer codes written into HSPF binary output files.
    """

    HOURLY = 2
    DAILY = 3
    MONTHLY = 4
    YEARLY = 5


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Human-readable label for each :class:`TimeStep`.
TIMESTEP_LABELS: Dict[TimeStep, str] = {
    TimeStep.HOURLY: "hourly",
    TimeStep.DAILY: "daily",
    TimeStep.MONTHLY: "monthly",
    TimeStep.YEARLY: "yearly",
}

#: pandas frequency string for each :class:`TimeStep`.
PANDAS_FREQ: Dict[TimeStep, str] = {
    TimeStep.HOURLY: "h",
    TimeStep.DAILY: "D",
    TimeStep.MONTHLY: "ME",
    TimeStep.YEARLY: "YE",
}

#: HSPF operation types.
OPERATIONS = ("PERLND", "IMPLND", "RCHRES")

#: Maximum valid operation ID (HSPF three-digit integer limitation).
MAX_OPNID = 999

#: Units for each HSPF output variable and water-quality constituent.
#:
#: HSPF direct outputs (hydrology, sediment, routing volumes) and
#: water-quality constituents (Q, TSS, TP, …) are treated uniformly as
#: entries in the ``variable`` dimension.
UNITS_BY_VARIABLE: Dict[str, str] = {
    # --- Water-quality constituents (native HBN / UNIT_DEFAULTS units) ---
    "Q": "cfs",
    "TSS": "mg/l",
    "TP": "mg/l",
    "OP": "mg/l",
    "TKN": "mg/l",
    "N": "mg/l",
    "WT": "degF",
    "WL": "ft",
    # --- PERLND / IMPLND hydrologic outputs ---
    "PERO": "inches",
    "SURO": "inches",
    "IFWO": "inches",
    "AGWO": "inches",
    "TAET": "inches",
    "IMPEV": "inches",
    "PRECIP": "inches",
    "PETINF": "inches",
    "CEPE": "inches",
    "UZET": "inches",
    "LZET": "inches",
    "AGWET": "inches",
    "BASET": "inches",
    "SURET": "inches",
    "SURI": "inches",
    "IFWI": "inches",
    "AGWI": "inches",
    "LZIRR": "inches",
    "LZSN": "inches",
    "UZSN": "inches",
    "INTFW": "dimensionless",
    "IRC": "dimensionless",
    # --- RCHRES volumetric / routing outputs ---
    "ROVOL": "acre-ft",
    "IVOL": "acre-ft",
    "VOLEV": "acre-ft",
    # --- Sediment ---
    "SOSED": "tons/acre",
    "SOSLD": "tons/acre",
    "DEPSCOUR": "tons",
}

# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def create_timestep_dataset(
    timestep: TimeStep,
    time_index: pd.DatetimeIndex,
    models: List[str],
    operations: List[str],
    opnids: List[int],
    variables: List[str],
) -> xr.Dataset:
    """Create an empty :class:`xr.Dataset` for one HSPF time-step resolution.

    Parameters
    ----------
    timestep:
        The HBN time-step resolution for this dataset.
    time_index:
        Temporal axis (e.g. ``pd.date_range(..., freq="D")``).
    models:
        Model identifiers, e.g. ``["baseline", "scenario1"]``.
    operations:
        HSPF operation types to include (subset of ``OPERATIONS``).
    opnids:
        Operation IDs.  Must all be in the range 1–:data:`MAX_OPNID`.
    variables:
        Variable / constituent names (e.g. ``["PERO", "SURO", "Q", "TP"]``).

    Returns
    -------
    xr.Dataset
        A dataset with a single ``"value"`` data variable spanning all five
        dimensions and a ``"units"`` non-dimension coordinate on the
        ``variable`` dimension.

    Raises
    ------
    ValueError
        If any *opnid* is outside the range 1–999.
    """
    bad = [oid for oid in opnids if not (1 <= oid <= MAX_OPNID)]
    if bad:
        raise ValueError(
            f"opnids must be in the range 1–{MAX_OPNID}; "
            f"invalid values: {bad}"
        )

    label = TIMESTEP_LABELS[timestep]
    units = [UNITS_BY_VARIABLE.get(v, "unknown") for v in variables]

    shape = (
        len(models),
        len(time_index),
        len(operations),
        len(opnids),
        len(variables),
    )
    data = np.full(shape, np.nan, dtype=np.float64)

    ds = xr.Dataset(
        data_vars={
            "value": xr.DataArray(
                data=data,
                dims=["model", "time", "operation", "opnid", "variable"],
            ),
        },
        coords={
            "model": ("model", list(models)),
            "time": ("time", time_index),
            "operation": ("operation", list(operations)),
            "opnid": ("opnid", list(opnids)),
            "variable": ("variable", list(variables)),
            "units": ("variable", units),
        },
        attrs={
            "timestep": label,
            "timestep_code": int(timestep),
            "Conventions": "CF-1.8",
            "source": "pyHSPF",
        },
    )
    return ds


# ---------------------------------------------------------------------------
# Collection class
# ---------------------------------------------------------------------------


class HspfDatasetCollection:
    """A dict-of-Datasets keyed by timestep label.

    Each entry is one :class:`xr.Dataset` produced by
    :func:`create_timestep_dataset` for a single time-step resolution.

    Examples
    --------
    >>> col = HspfDatasetCollection()
    >>> col.add(daily_ds)
    >>> col.add(monthly_ds)
    >>> col["daily"]
    <xarray.Dataset ...>
    """

    def __init__(self) -> None:
        self._store: Dict[str, xr.Dataset] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, ds: xr.Dataset) -> None:
        """Add *ds* to the collection.

        The key is taken from ``ds.attrs["timestep"]``.

        Parameters
        ----------
        ds:
            A dataset created by :func:`create_timestep_dataset`.

        Raises
        ------
        KeyError
            If ``ds.attrs["timestep"]`` is missing.
        """
        key = ds.attrs["timestep"]
        self._store[key] = ds

    # ------------------------------------------------------------------
    # Dict-like access
    # ------------------------------------------------------------------

    def __getitem__(self, label: str) -> xr.Dataset:
        return self._store[label]

    def __contains__(self, label: object) -> bool:
        return label in self._store

    def keys(self):
        """Return the timestep labels present in the collection."""
        return self._store.keys()

    def items(self):
        """Return ``(label, dataset)`` pairs."""
        return self._store.items()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def variables_at(self, label: str) -> List[str]:
        """Return the list of variable names stored at *label*.

        Parameters
        ----------
        label:
            Timestep label, e.g. ``"daily"``.
        """
        return list(self._store[label].coords["variable"].values)

    def select(
        self,
        model: str,
        operation: str,
        opnid: int,
        variable: str,
    ) -> Dict[str, xr.DataArray]:
        """Slice across all resolutions that contain *variable*.

        Parameters
        ----------
        model:
            Model identifier.
        operation:
            HSPF operation type (``"PERLND"``, ``"IMPLND"``, or ``"RCHRES"``).
        opnid:
            Operation ID (1–999).
        variable:
            Variable / constituent name.

        Returns
        -------
        dict[str, xr.DataArray]
            Mapping from timestep label to the selected 1-D time series.
            Only resolutions that contain *variable* are included.
        """
        result: Dict[str, xr.DataArray] = {}
        for label, ds in self._store.items():
            if variable in ds.coords["variable"].values:
                result[label] = ds["value"].sel(
                    model=model,
                    operation=operation,
                    opnid=opnid,
                    variable=variable,
                )
        return result

    def to_dict(self) -> Dict[str, xr.Dataset]:
        """Return the underlying ``dict[label, Dataset]``."""
        return dict(self._store)
