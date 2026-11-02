"""Derived validation tables that are complex enough to name."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from hspf.core.types import RoutingSource
from hspf.uci.topology import ModelTopology
from hspf.validation.support import as_set, sort_values


def build_subwatershed_precip_dsns(topology: ModelTopology) -> pd.DataFrame:
    """Return direct land-contributor PREC DSN comparisons by receiving reach."""

    precip = topology.precip_assignments()
    columns = (
        "reach_id",
        "reach_dsn",
        "contributor_operation",
        "contributor_id",
        "contributor_dsn",
    )
    if precip.empty:
        return pd.DataFrame(columns=columns)

    reach_precip = precip.loc[precip["TVOL"] == "RCHRES", ["TVOLNO", "SVOLNO"]]
    reach_precip = reach_precip.rename(columns={"TVOLNO": "reach_id", "SVOLNO": "reach_dsn"})
    contributor_precip = precip.rename(
        columns={
            "TVOL": "contributor_operation",
            "TVOLNO": "contributor_id",
            "SVOLNO": "contributor_dsn",
        }
    )
    land_edges = topology.land_to_reach()
    if land_edges.empty:
        return pd.DataFrame(columns=columns)

    land_edges = land_edges[["SVOL", "SVOLNO", "TVOLNO"]].rename(
        columns={
            "SVOL": "contributor_operation",
            "SVOLNO": "contributor_id",
            "TVOLNO": "reach_id",
        }
    )
    result = land_edges.merge(reach_precip, on="reach_id", how="left")
    result = result.merge(
        contributor_precip[
            ["contributor_operation", "contributor_id", "contributor_dsn"]
        ],
        on=["contributor_operation", "contributor_id"],
        how="left",
    )
    return result[list(columns)]


def build_reach_classification(
    topology: ModelTopology,
) -> pd.DataFrame:
    """Classify RCHRES ids for downstream UCI/GIS checks."""

    columns = (
        "reach_id",
        "lake",
        "terminal",
        "area_receiving",
        "routing_only",
        "non_contributing",
        "dummy_terminal_lake",
        "network_area_basis",
        "incoming_land_edge_count",
        "incoming_schematic_area",
    )
    operations = topology.operations
    opn_sequence = operations.loc[operations["in_opn_sequence"]]
    reach_ids = opn_sequence.loc[opn_sequence["OPERATION"] == "RCHRES", "OPNID"].dropna()
    reach_set = set(reach_ids)
    gen_info = operations.loc[operations["OPERATION"] == "RCHRES", ["OPNID", "LKFG"]]
    lkfg_frame = gen_info[["OPNID", "LKFG"]].dropna(subset=["OPNID"])
    lkfg_by_reach = dict(zip(lkfg_frame["OPNID"], lkfg_frame["LKFG"]))

    rchres_edges = topology.reach_edges()
    land_to_reach_edges = topology.land_to_reach()
    outgoing = Counter(rchres_edges["SVOLNO"].dropna())
    incoming_count = Counter(land_to_reach_edges["TVOLNO"].dropna())

    if "AFACTR" in land_to_reach_edges:
        area_frame = land_to_reach_edges.loc[
            land_to_reach_edges["TVOLNO"].notna(),
            ["TVOLNO", "AFACTR"],
        ].copy()
        area_frame["AFACTR"] = pd.to_numeric(
            area_frame["AFACTR"],
            errors="coerce",
        ).fillna(0.0)
        incoming_area = area_frame.groupby("TVOLNO")["AFACTR"].sum().to_dict()
    else:
        incoming_area = {}

    if "routing_source" in land_to_reach_edges:
        network_area_reaches = as_set(
            land_to_reach_edges.loc[
                land_to_reach_edges["routing_source"] == RoutingSource.NETWORK.value,
                "TVOLNO",
            ]
        )
    else:
        network_area_reaches = set()

    schematic_connections = topology.schematic_connections()
    schematic_reach_ids = set(
        schematic_connections.loc[schematic_connections["SVOL"] == "RCHRES", "SVOLNO"].dropna()
    ) | set(
        schematic_connections.loc[schematic_connections["TVOL"] == "RCHRES", "TVOLNO"].dropna()
    )
    routing_graph_reach_ids = set(rchres_edges["SVOLNO"].dropna()) | set(
        rchres_edges["TVOLNO"].dropna()
    )
    schematic_reaches = set(schematic_reach_ids)
    routing_reaches = set(routing_graph_reach_ids) if routing_graph_reach_ids else reach_set
    records: list[dict[str, Any]] = []
    for reach_id in sort_values(reach_set):
        lake = lkfg_by_reach.get(reach_id) == 1
        area_receiving = incoming_count[reach_id] > 0 or incoming_area.get(reach_id, 0.0) > 0
        terminal = outgoing[reach_id] == 0
        routing_only = not area_receiving
        non_contributing = reach_id in schematic_reaches and reach_id not in routing_reaches
        dummy_terminal_lake = terminal and lake and routing_only
        records.append(
            {
                "reach_id": reach_id,
                "lake": lake,
                "terminal": terminal,
                "area_receiving": area_receiving,
                "routing_only": routing_only,
                "non_contributing": non_contributing,
                "dummy_terminal_lake": dummy_terminal_lake,
                "network_area_basis": reach_id in network_area_reaches,
                "incoming_land_edge_count": incoming_count[reach_id],
                "incoming_schematic_area": incoming_area.get(reach_id, 0.0),
            }
        )
    return pd.DataFrame.from_records(records, columns=columns)


def derive_precip_crosswalk(
    topology: ModelTopology,
    operation_metzones: pd.DataFrame,
) -> pd.DataFrame:
    """Derive a metzone-to-dominant-PREC-DSN crosswalk from current tables."""

    precip = topology.precip_assignments().rename(
        columns={"TVOL": "operation", "TVOLNO": "op_id", "SVOLNO": "dsn"}
    )
    merged = precip.merge(
        operation_metzones,
        on=["operation", "op_id"],
        how="inner",
    )
    records: list[dict[str, Any]] = []
    if merged.empty:
        return pd.DataFrame.from_records(
            records, columns=("metzone", "dsn", "operation_count", "dsn_count", "ambiguous")
        )

    for metzone, group in merged.groupby("metzone", dropna=False):
        counts = group["dsn"].value_counts(dropna=False)
        max_count = counts.max()
        dominant = sort_values(counts.loc[counts == max_count].index.tolist())[0]
        records.append(
            {
                "metzone": metzone,
                "dsn": dominant,
                "operation_count": int(len(group)),
                "dsn_count": int(len(counts)),
                "ambiguous": bool((counts == max_count).sum() > 1),
            }
        )
    return pd.DataFrame.from_records(
        records,
        columns=("metzone", "dsn", "operation_count", "dsn_count", "ambiguous"),
    )


__all__ = [
    "build_subwatershed_precip_dsns",
    "build_reach_classification",
    "derive_precip_crosswalk",
]
