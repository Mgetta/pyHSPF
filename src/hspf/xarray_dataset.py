# -*- coding: utf-8 -*-
"""
Construct xarray Datasets from HSPF binary output (HBN) and UCI metadata.

Three public entry points:

* ``hbn_to_xarray(hbn)``  – HBN timeseries → xarray Dataset
* ``uci_to_xarray(uci)``  – UCI structural metadata → xarray Dataset
* ``build_model_dataset(hbn, uci)`` – merged HBN + UCI → single Dataset

Design note
-----------
HSPF operation IDs are only unique within an operation type (PERLND 1 and
RCHRES 1 are different entities).  This module uses a **segment** dimension
whose values are compound strings like ``"PERLND_001"`` / ``"RCHRES_001"``,
with ``operation`` and ``opnid`` carried as coordinate variables on that
dimension.
"""

import numpy as np
import pandas as pd
import xarray as xr

# Sentinel used when an integer metadata field has no value for a segment
_MISSING_INT = -1


# ---------------------------------------------------------------------------
# HBN → xarray
# ---------------------------------------------------------------------------

def hbn_to_xarray(hbn):
    """Convert HBN output into an xarray Dataset.

    Accepts either a single ``hbnClass`` or an ``hbnInterface``
    (which wraps one or more HBN files).  Every
    ``(operation, activity, opnid, tcode)`` group stored in the HBN becomes
    a set of data variables, one per constituent.

    Parameters
    ----------
    hbn : hbnClass or hbnInterface
        Parsed HBN object.  ``map_hbn()`` must have been called (the
        default when constructing with ``Map=True``).

    Returns
    -------
    xr.Dataset
        Dimensions: ``time``, ``segment``.
        Coordinates include ``operation``, ``opnid``, and ``activity``
        (per ``segment``).
        Data variables are the constituent timeseries.

    Notes
    -----
    When the HBN contains multiple temporal resolutions (e.g. daily *and*
    yearly), variable names are suffixed with ``_<tcode>`` (e.g.
    ``ROVOL_3`` for daily, ``ROVOL_5`` for yearly).
    """
    hbn_objects = _resolve_hbn_list(hbn)

    # Collect all data frames across hbn files
    records = []  # (operation, activity, opnid, tcode, DataFrame)
    for hbn_obj in hbn_objects:
        _ensure_mapped(hbn_obj)
        for key, df in hbn_obj.data_frames.items():
            parts = key.split("_")
            operation = parts[0]
            activity = parts[1]
            opnid = int(parts[2])
            tcode = int(parts[3])
            records.append((operation, activity, opnid, tcode, df))

    if not records:
        return xr.Dataset()

    # Group records by tcode
    tcode_groups = {}
    for operation, activity, opnid, tcode, df in records:
        tcode_groups.setdefault(tcode, []).append(
            (operation, activity, opnid, df)
        )

    tcodes_present = sorted(tcode_groups.keys())
    needs_suffix = len(tcodes_present) > 1

    all_data_vars = {}
    # Track per-segment metadata
    segment_operation = {}
    segment_opnid = {}
    segment_activity = {}

    for tcode, group_records in tcode_groups.items():
        constituent_frames = {}  # constituent_name → {segment_label: Series}

        for operation, activity, opnid, df in group_records:
            seg_label = f"{operation}_{opnid:03d}"
            segment_operation[seg_label] = operation
            segment_opnid[seg_label] = opnid
            segment_activity[seg_label] = activity
            for col in df.columns:
                constituent_frames.setdefault(col, {})[seg_label] = df[col]

        # Build one 2-D array (time × segment) per constituent
        for constituent, seg_series in constituent_frames.items():
            wide = pd.DataFrame(seg_series)
            wide.index.name = "time"
            wide.columns.name = "segment"

            var_name = f"{constituent}_{tcode}" if needs_suffix else constituent
            da = xr.DataArray(
                wide.values,
                dims=["time", "segment"],
                coords={
                    "time": wide.index,
                    "segment": list(wide.columns),
                },
            )
            da.attrs["tcode"] = tcode
            all_data_vars[var_name] = da

    if not all_data_vars:
        return xr.Dataset()

    ds = xr.Dataset(all_data_vars)

    # Attach per-segment coordinate arrays
    all_segments = sorted(segment_operation.keys())
    ds.coords["operation"] = (
        "segment",
        [segment_operation.get(s, "") for s in all_segments],
    )
    ds.coords["opnid"] = (
        "segment",
        [segment_opnid.get(s, _MISSING_INT) for s in all_segments],
    )
    ds.coords["activity"] = (
        "segment",
        [segment_activity.get(s, "") for s in all_segments],
    )

    ds.attrs["source"] = "hbn"
    return ds


# ---------------------------------------------------------------------------
# UCI → xarray
# ---------------------------------------------------------------------------

def uci_to_xarray(uci):
    """Extract UCI structural metadata into an xarray Dataset.

    Parameters
    ----------
    uci : UCI
        Parsed UCI object.

    Returns
    -------
    xr.Dataset
        Dimension: ``segment`` (compound key like ``"PERLND_001"``).
        Data variables include ``area``, ``landcover``, ``downstream_rchres``,
        and ``mass_link``, as available from the subwatershed table.
        Reach topology (``downstream_reach``) is on the ``reach_segment``
        dimension when the network graph can be resolved.
    """
    data_vars = {}
    coords = {}

    # --- OPN SEQUENCE: all segments with their operation type -------------
    try:
        opnseq = uci.table("OPN SEQUENCE")
        seg_ids = opnseq["SEGMENT"].astype(int).values
        seg_ops = opnseq["OPERATION"].values
        segments = [f"{op}_{sid:03d}" for op, sid in zip(seg_ops, seg_ids)]
        coords["segment"] = segments
        data_vars["operation"] = ("segment", list(seg_ops))
        data_vars["opnid"] = ("segment", [int(s) for s in seg_ids])
    except Exception:
        return xr.Dataset()

    # --- Subwatersheds / land-cover metadata -----------------------------
    try:
        subwatersheds = uci.network.subwatersheds()
        sw = (
            subwatersheds.reset_index(drop=True)
            if hasattr(subwatersheds, "reset_index")
            else subwatersheds
        )

        sw_segments = [
            f"{svol}_{svolno:03d}"
            for svol, svolno in zip(sw["SVOL"].values, sw["SVOLNO"].astype(int).values)
        ]

        # Only attach metadata for segments present in OPN SEQUENCE
        seg_set = set(segments)
        mask = [s in seg_set for s in sw_segments]

        if any(mask):
            sw_filtered = sw.iloc[[i for i, m in enumerate(mask) if m]]
            sw_seg_filtered = [s for s, m in zip(sw_segments, mask) if m]

            # Build lookup tables keyed by segment label
            area_map = dict(zip(sw_seg_filtered, sw_filtered["AFACTR"].astype(float).values))
            lsid_map = dict(zip(sw_seg_filtered, sw_filtered["LSID"].astype(str).values))
            tvolno_map = dict(zip(sw_seg_filtered, sw_filtered["TVOLNO"].astype(int).values))

            data_vars["area"] = ("segment", [area_map.get(s, np.nan) for s in segments])
            data_vars["landcover"] = ("segment", [lsid_map.get(s, "") for s in segments])
            data_vars["downstream_rchres"] = (
                "segment",
                [tvolno_map.get(s, _MISSING_INT) for s in segments],
            )

            if "MLNO" in sw.columns:
                mlno_map = dict(zip(sw_seg_filtered, sw_filtered["MLNO"].astype(int).values))
                data_vars["mass_link"] = ("segment", [mlno_map.get(s, _MISSING_INT) for s in segments])
    except Exception:
        pass

    # --- Metzone lookup --------------------------------------------------
    try:
        opnid_dict = uci.opnid_dict
        for op_type in ["PERLND", "IMPLND"]:
            if op_type in opnid_dict:
                meta = opnid_dict[op_type]
                if "metzone" in meta.columns:
                    mz_map = {
                        f"{op_type}_{oid:03d}": int(mz)
                        for oid, mz in zip(meta.index.astype(int), meta["metzone"].values)
                    }
                    data_vars["metzone"] = (
                        "segment",
                        [mz_map.get(s, _MISSING_INT) for s in segments],
                    )
    except Exception:
        pass

    # --- Reach topology --------------------------------------------------
    try:
        reach_ids = uci.valid_opnids.get("RCHRES", [])
        if reach_ids:
            network = uci.network
            downstream = []
            for rid in reach_ids:
                try:
                    successors = list(network.graph.successors(rid))
                    downstream.append(successors[0] if successors else _MISSING_INT)
                except Exception:
                    downstream.append(_MISSING_INT)
            rch_labels = [f"RCHRES_{rid:03d}" for rid in reach_ids]
            data_vars["downstream_reach"] = (
                "reach_segment",
                np.array(downstream, dtype=int),
            )
            coords["reach_segment"] = rch_labels
    except Exception:
        pass

    ds = xr.Dataset(data_vars, coords=coords)
    ds.attrs["source"] = "uci"
    ds.attrs["model_name"] = getattr(uci, "name", "")
    return ds


# ---------------------------------------------------------------------------
# Combined builder
# ---------------------------------------------------------------------------

def build_model_dataset(hbn, uci):
    """Merge HBN output and UCI metadata into a single xarray Dataset.

    This is the recommended entry point for integrated analysis.  The
    HBN timeseries Dataset is enriched with UCI structural metadata
    (areas, land covers, reach topology) by aligning on the shared
    ``segment`` dimension.

    Parameters
    ----------
    hbn : hbnClass, hbnInterface, or None
        Parsed HBN object(s).  Pass ``None`` to get only UCI metadata.
    uci : UCI or None
        Parsed UCI object.  Pass ``None`` to get only HBN output.

    Returns
    -------
    xr.Dataset
        Merged Dataset.
    """
    ds_hbn = hbn_to_xarray(hbn) if hbn is not None else xr.Dataset()
    ds_uci = uci_to_xarray(uci) if uci is not None else xr.Dataset()

    if not ds_hbn.data_vars and not ds_uci.data_vars:
        return xr.Dataset()

    if not ds_hbn.data_vars:
        return ds_uci

    if not ds_uci.data_vars:
        return ds_hbn

    # Start from HBN dataset, merge in UCI metadata
    ds = ds_hbn.copy()

    hbn_segments = set(ds.coords["segment"].values)

    # Attach per-segment metadata from UCI (area, landcover, etc.)
    if "segment" in ds_uci.dims:
        for var_name in ["area", "landcover", "downstream_rchres", "mass_link", "metzone"]:
            if var_name not in ds_uci:
                continue
            uci_segs = ds_uci.coords["segment"].values
            lookup = dict(zip(uci_segs, ds_uci[var_name].values))
            aligned = [lookup.get(s, None) for s in ds.coords["segment"].values]
            if any(v is not None for v in aligned):
                dtype = ds_uci[var_name].dtype
                if np.issubdtype(dtype, np.str_) or dtype == object:
                    fill = ""
                elif np.issubdtype(dtype, np.floating):
                    fill = np.nan
                else:
                    fill = _MISSING_INT
                aligned = [v if v is not None else fill for v in aligned]
                ds.coords[var_name] = ("segment", aligned)

    # Attach reach topology on its own dimension
    if "reach_segment" in ds_uci.dims and "downstream_reach" in ds_uci:
        ds_reach = ds_uci[["downstream_reach"]]
        ds = ds.merge(ds_reach, join="outer")

    ds.attrs["source"] = "hbn+uci"
    ds.attrs["model_name"] = ds_uci.attrs.get("model_name", "")
    return ds


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _resolve_hbn_list(hbn):
    """Return a list of hbnClass objects from either an hbnClass or hbnInterface."""
    if hasattr(hbn, "hbns"):
        return hbn.hbns
    return [hbn]


def _ensure_mapped(hbn_obj):
    """Ensure the hbnClass has been mapped (data_frames populated)."""
    if not hasattr(hbn_obj, "data_frames") or not hbn_obj.data_frames:
        if hasattr(hbn_obj, "map_hbn"):
            hbn_obj.map_hbn()
