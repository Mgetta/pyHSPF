"""GIS-internal validation checks."""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from hspf.validation.findings import SEVERITY_ERROR, SEVERITY_INFO
from hspf.validation.support import (
    DEFAULT_OUTLET_SENTINELS,
    as_set,
    directed_cycle_nodes,
    filtered_gis_edges,
    is_missing,
    make_finding,
    sort_values,
)


def check_reach_keys(reach_layer: pd.DataFrame) -> list:
    """G0-1: GIS reach ids are present and unique."""

    findings = []
    missing_rows = reach_layer.index[reach_layer["ReachID"].map(is_missing)].tolist()
    for row_index in missing_rows:
        findings.append(
            make_finding(
                "G0-1",
                SEVERITY_ERROR,
                "reach_row",
                row_index,
                "ReachID is missing",
                expected="non-null reach id",
                actual=None,
            )
        )

    duplicated = reach_layer.loc[
        reach_layer["ReachID"].notna()
        & reach_layer.duplicated(subset="ReachID", keep=False),
        "ReachID",
    ]
    for reach_id, count in duplicated.value_counts().items():
        findings.append(
            make_finding(
                "G0-1",
                SEVERITY_ERROR,
                "reach",
                reach_id,
                "ReachID is duplicated",
                expected="unique reach id",
                actual=int(count),
            )
        )
    return findings


def check_downstream_references(
    reach_layer: pd.DataFrame,
    *,
    outlet_sentinels: Iterable[Any] = DEFAULT_OUTLET_SENTINELS,
) -> list:
    """G0-2: downstream GIS references are valid reach ids or outlet sentinels."""

    reach_ids = as_set(reach_layer["ReachID"])
    sentinels = set(outlet_sentinels)
    findings = []

    missing = reach_layer.loc[reach_layer["DS_ReachID"].map(is_missing)]
    for row in missing.itertuples():
        findings.append(
            make_finding(
                "G0-2",
                SEVERITY_ERROR,
                "reach",
                row.ReachID,
                "DS_ReachID is missing",
                expected="downstream reach id or outlet sentinel",
                actual=None,
                attributes={"row": row.Index},
            )
        )

    invalid = reach_layer.loc[
        reach_layer["DS_ReachID"].notna()
        & ~reach_layer["DS_ReachID"].isin(sentinels)
        & ~reach_layer["DS_ReachID"].isin(reach_ids)
    ]
    for row in invalid.itertuples():
        findings.append(
            make_finding(
                "G0-2",
                SEVERITY_ERROR,
                "reach",
                row.ReachID,
                "DS_ReachID references a missing GIS reach",
                expected="ReachID in GIS layer or outlet sentinel",
                actual=row.DS_ReachID,
                attributes={"row": row.Index},
            )
        )
    return findings


def check_gis_reach_graph(
    reach_layer: pd.DataFrame,
    *,
    outlet_sentinels: Iterable[Any] = DEFAULT_OUTLET_SENTINELS,
) -> list:
    """G0-3: GIS reach graph has no cycles and reports outlet count."""

    reach_ids = as_set(reach_layer["ReachID"])
    edges = filtered_gis_edges(reach_layer, outlet_sentinels=outlet_sentinels)
    findings = []
    cycle_nodes = directed_cycle_nodes(edges, nodes=reach_ids)
    if cycle_nodes:
        findings.append(
            make_finding(
                "G0-3",
                SEVERITY_ERROR,
                "reach_graph",
                "gis",
                "GIS reach graph contains at least one cycle",
                expected="acyclic GIS reach graph",
                actual=sort_values(cycle_nodes),
            )
        )

    outlet_rows = reach_layer.loc[reach_layer["DS_ReachID"].isin(set(outlet_sentinels))]
    findings.append(
        make_finding(
            "G0-3",
            SEVERITY_INFO,
            "reach_graph",
            "gis",
            "GIS outlet count",
            expected="reported for context",
            actual=len(outlet_rows),
            attributes={"outlets": sort_values(outlet_rows["ReachID"].dropna().tolist())},
        )
    )
    return findings


def check_catchment_attributes(catchments: pd.DataFrame) -> list:
    """G0-4: GIS catchments have reach and metzone attributes."""

    findings = []
    missing_mask = catchments["ReachID"].map(is_missing) | catchments["metzone"].map(is_missing)
    for row in catchments.loc[missing_mask].itertuples():
        missing: list[str] = []
        if is_missing(row.ReachID):
            missing.append("ReachID")
        if is_missing(row.metzone):
            missing.append("metzone")
        if missing:
            findings.append(
                make_finding(
                    "G0-4",
                    SEVERITY_ERROR,
                    "catchment",
                    row.Index,
                    "Catchment is missing required GIS attributes",
                    expected="non-null ReachID and metzone",
                    actual={"missing": missing},
                )
            )
    return findings


__all__ = [
    "check_reach_keys",
    "check_downstream_references",
    "check_gis_reach_graph",
    "check_catchment_attributes",
]
