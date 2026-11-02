"""Checks that compare UCI topology against GIS layers."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

import pandas as pd

from hspf.uci.topology import ModelTopology
from hspf.validation.findings import SEVERITY_ERROR, SEVERITY_INFO, SEVERITY_WARNING
from hspf.validation.support import (
    DEFAULT_OUTLET_SENTINELS,
    as_set,
    edge_set,
    filtered_gis_edges,
    make_finding,
    sort_values,
)


def check_reach_set_reconciliation(
    topology: ModelTopology,
    reach_layer: pd.DataFrame,
) -> list:
    """G1-1/G1-2: UCI and GIS reach id sets reconcile."""

    opn_sequence = topology.operations.loc[topology.operations["in_opn_sequence"]]
    uci_reach_ids = opn_sequence.loc[opn_sequence["OPERATION"] == "RCHRES", "OPNID"].dropna()
    uci_ids = set(uci_reach_ids)
    gis_ids = as_set(reach_layer["ReachID"])
    findings = []
    for reach_id in sort_values(uci_ids - gis_ids):
        findings.append(
            make_finding(
                "G1-1",
                SEVERITY_ERROR,
                "reach",
                reach_id,
                "UCI reach is missing from GIS reach layer",
                expected="ReachID present in GIS",
                actual=None,
            )
        )
    for reach_id in sort_values(gis_ids - uci_ids):
        findings.append(
            make_finding(
                "G1-2",
                SEVERITY_WARNING,
                "reach",
                reach_id,
                "GIS reach is absent from UCI RCHRES set",
                expected="RCHRES in UCI or documented extra GIS feature",
                actual="GIS-only reach",
            )
        )
    return findings


def check_routing_edge_concordance(
    topology: ModelTopology,
    reach_layer: pd.DataFrame,
    *,
    outlet_sentinels: Iterable[Any] = DEFAULT_OUTLET_SENTINELS,
) -> list:
    """G2-1/G2-2: GIS edges match the UCI union routing graph."""

    uci_rchres_edges = topology.reach_edges()
    gis_edges = filtered_gis_edges(reach_layer, outlet_sentinels=outlet_sentinels)
    uci_edges = edge_set(uci_rchres_edges, source_col="SVOLNO", target_col="TVOLNO")

    uci_by_source: dict[Any, set[Any]] = defaultdict(set)
    gis_by_source: dict[Any, set[Any]] = defaultdict(set)
    for source, target in uci_edges:
        uci_by_source[source].add(target)
    for source, target in gis_edges:
        gis_by_source[source].add(target)

    findings = []
    for edge in sort_values(gis_edges - uci_edges):
        findings.append(
            make_finding(
                "G2-1",
                SEVERITY_ERROR,
                "reach_edge",
                edge,
                "GIS downstream edge is absent from UCI routing graph",
                expected="edge present in UCI union graph",
                actual="GIS-only edge",
            )
        )

    for edge in sort_values(uci_edges - gis_edges):
        source, target = edge
        if len(uci_by_source[source]) > 1:
            findings.append(
                make_finding(
                    "G2-2",
                    SEVERITY_INFO,
                    "reach_edge",
                    edge,
                    "UCI has an extra downstream edge for a multi-exit reach",
                    expected="visible multi-exit/diversion context",
                    actual={"uci_targets": sort_values(uci_by_source[source])},
                )
            )
        elif source in gis_by_source:
            findings.append(
                make_finding(
                    "G2-1",
                    SEVERITY_ERROR,
                    "reach_edge",
                    edge,
                    "UCI downstream edge differs from GIS downstream edge",
                    expected=sort_values(gis_by_source[source]),
                    actual=target,
                )
            )
    return findings


def check_terminal_reach_concordance(
    topology: ModelTopology,
    reach_layer: pd.DataFrame,
    *,
    outlet_sentinels: Iterable[Any] = DEFAULT_OUTLET_SENTINELS,
) -> list:
    """G2-3: UCI and GIS agree on terminal reaches."""

    uci_rchres_edges = topology.reach_edges()
    sentinels = set(outlet_sentinels)
    gis_outlets = set(reach_layer.loc[reach_layer["DS_ReachID"].isin(sentinels), "ReachID"])
    uci_edges = edge_set(uci_rchres_edges, source_col="SVOLNO", target_col="TVOLNO")
    uci_nodes = as_set(reach_layer["ReachID"]) | {node for edge in uci_edges for node in edge}
    uci_sources = {source for source, _ in uci_edges}
    uci_outlets = uci_nodes - uci_sources

    findings = []
    for reach_id in sort_values(uci_outlets - gis_outlets):
        findings.append(
            make_finding(
                "G2-3",
                SEVERITY_ERROR,
                "reach",
                reach_id,
                "UCI outlet is not a GIS outlet",
                expected="GIS downstream sentinel",
                actual="non-terminal GIS reach",
            )
        )
    for reach_id in sort_values(gis_outlets - uci_outlets):
        findings.append(
            make_finding(
                "G2-3",
                SEVERITY_ERROR,
                "reach",
                reach_id,
                "GIS outlet is not a UCI outlet",
                expected="no outgoing UCI routing edge",
                actual="outgoing UCI edge present",
            )
        )
    return findings


def check_lake_concordance(
    classification: pd.DataFrame,
    reach_layer: pd.DataFrame,
) -> list:
    """G3: LKFG-derived lake class agrees with GIS lake flag."""

    if "lake" not in reach_layer:
        return []
    merged = classification[["reach_id", "lake"]].merge(
        reach_layer[["ReachID", "lake"]].dropna(subset=["ReachID"]),
        left_on="reach_id",
        right_on="ReachID",
        how="inner",
        suffixes=("_uci", "_gis"),
    )
    mismatches = merged.loc[merged["lake_uci"].astype(bool) != merged["lake_gis"].astype(bool)]

    findings = []
    for row in mismatches.itertuples(index=False):
        findings.append(
            make_finding(
                "G3",
                SEVERITY_WARNING,
                "reach",
                row.reach_id,
                "UCI LKFG lake class differs from GIS lake flag",
                expected=bool(row.lake_uci),
                actual=bool(row.lake_gis),
            )
        )
    return findings


def check_catchment_coverage(
    classification: pd.DataFrame,
    catchments: pd.DataFrame,
    topology: ModelTopology,
) -> list:
    """G4-1/G4-2/G4-3: catchment coverage and reach assignments."""

    catchment_counts = catchments["ReachID"].value_counts(dropna=True)
    opn_sequence = topology.operations.loc[topology.operations["in_opn_sequence"]]
    uci_reach_ids = opn_sequence.loc[opn_sequence["OPERATION"] == "RCHRES", "OPNID"].dropna()
    uci_reaches = set(uci_reach_ids)
    findings = []

    area_receiving = classification.loc[classification["area_receiving"], "reach_id"]
    for reach_id in sort_values(set(area_receiving) - set(catchment_counts.index)):
        findings.append(
            make_finding(
                "G4-1",
                SEVERITY_ERROR,
                "reach",
                reach_id,
                "Area-receiving reach has no catchment polygon",
                expected="one or more catchment polygons",
                actual=0,
            )
        )

    invalid_catchments = catchments.loc[
        catchments["ReachID"].notna() & ~catchments["ReachID"].isin(uci_reaches)
    ]
    for row in invalid_catchments.itertuples():
        findings.append(
            make_finding(
                "G4-2",
                SEVERITY_ERROR,
                "catchment",
                row.Index,
                "Catchment references a reach absent from the UCI",
                expected="catchment ReachID in UCI RCHRES set",
                actual=row.ReachID,
            )
        )

    routing_only_reaches = set(classification.loc[classification["routing_only"], "reach_id"])
    routing_only_counts = catchment_counts.loc[
        catchment_counts.index.isin(routing_only_reaches)
    ]
    for reach_id, count in routing_only_counts.items():
        findings.append(
            make_finding(
                "G4-3",
                SEVERITY_WARNING,
                "reach",
                reach_id,
                "Catchments are assigned to a routing-only reach",
                expected="no catchments on routing-only reach",
                actual=int(count),
            )
        )
    return findings


def check_precip_metzones(
    topology: ModelTopology,
    operation_metzones: pd.DataFrame,
) -> list:
    """G5-3: operation PREC DSNs are coherent within spatial metzones."""

    precip = topology.precip_assignments().rename(
        columns={"TVOL": "operation", "TVOLNO": "op_id", "SVOLNO": "dsn"}
    )
    merged = precip.merge(
        operation_metzones,
        on=["operation", "op_id"],
        how="outer",
        indicator=True,
    ).rename(columns={"_merge": "merge_state"})
    findings = []
    for row in merged.loc[merged["merge_state"] != "both"].itertuples(index=False):
        findings.append(
            make_finding(
                "G5-3",
                SEVERITY_WARNING,
                row.operation,
                row.op_id,
                "Operation is missing one side of the PREC DSN / spatial metzone comparison",
                expected="PREC DSN and spatial metzone",
                actual=row.merge_state,
            )
        )

    comparable = merged.loc[merged["merge_state"] == "both"].copy()
    for metzone, group in comparable.groupby("metzone", dropna=False):
        counts = group["dsn"].value_counts(dropna=False)
        if len(counts) <= 1:
            continue
        max_count = counts.max()
        dominant_dsns = set(counts.loc[counts == max_count].index.tolist())
        if len(dominant_dsns) > 1:
            for row in group.itertuples(index=False):
                findings.append(
                    make_finding(
                        "G5-3",
                        SEVERITY_WARNING,
                        row.operation,
                        row.op_id,
                        "Spatial metzone has no dominant PREC DSN",
                        expected="one dominant PREC DSN per spatial metzone",
                        actual={"metzone": metzone, "dsn_counts": counts.to_dict()},
                    )
                )
            continue
        dominant = next(iter(dominant_dsns))
        for row in group.loc[group["dsn"] != dominant].itertuples(index=False):
            findings.append(
                make_finding(
                    "G5-3",
                    SEVERITY_WARNING,
                    row.operation,
                    row.op_id,
                    "Operation PREC DSN differs from the dominant DSN for its spatial metzone",
                    expected=dominant,
                    actual=row.dsn,
                    attributes={"metzone": metzone},
                )
            )
    return findings


def check_precip_crosswalk(
    topology: ModelTopology,
    operation_metzones: pd.DataFrame,
    crosswalk: Mapping[Any, Any] | pd.DataFrame,
) -> list:
    """G5-4: operation DSNs conform to a committed metzone-to-DSN crosswalk."""

    if isinstance(crosswalk, pd.DataFrame):
        crosswalk_map = dict(zip(crosswalk["metzone"], crosswalk["dsn"]))
    else:
        crosswalk_map = dict(crosswalk)

    precip = topology.precip_assignments().rename(
        columns={"TVOL": "operation", "TVOLNO": "op_id", "SVOLNO": "dsn"}
    )
    merged = precip.merge(
        operation_metzones,
        on=["operation", "op_id"],
        how="outer",
        indicator=True,
    ).rename(columns={"_merge": "merge_state"})
    findings = []
    for row in merged.itertuples(index=False):
        if row.merge_state != "both":
            findings.append(
                make_finding(
                    "G5-4",
                    SEVERITY_ERROR,
                    row.operation,
                    row.op_id,
                    "Operation is missing one side of committed-crosswalk validation",
                    expected="PREC DSN and spatial metzone",
                    actual=row.merge_state,
                )
            )
            continue
        metzone = row.metzone
        if metzone not in crosswalk_map:
            findings.append(
                make_finding(
                    "G5-4",
                    SEVERITY_ERROR,
                    row.operation,
                    row.op_id,
                    "Spatial metzone is absent from committed PREC crosswalk",
                    expected="metzone present in crosswalk",
                    actual=metzone,
                )
            )
            continue
        expected_dsn = crosswalk_map[metzone]
        if row.dsn != expected_dsn:
            findings.append(
                make_finding(
                    "G5-4",
                    SEVERITY_ERROR,
                    row.operation,
                    row.op_id,
                    "Operation PREC DSN differs from committed metzone crosswalk",
                    expected=expected_dsn,
                    actual=row.dsn,
                    attributes={"metzone": metzone},
                )
            )
    return findings


def check_area_comparison_deferred() -> list:
    """G6: explicit placeholder because area comparison is deferred."""

    return [
        make_finding(
            "G6",
            SEVERITY_INFO,
            "area_check",
            "deferred",
            "Area comparison is deferred until lake-surface conventions are decided",
            expected="future direct-drainage area check",
            actual="deferred",
        )
    ]


__all__ = [
    "check_reach_set_reconciliation",
    "check_routing_edge_concordance",
    "check_terminal_reach_concordance",
    "check_lake_concordance",
    "check_catchment_coverage",
    "check_precip_metzones",
    "check_precip_crosswalk",
    "check_area_comparison_deferred",
]
