"""UCI routing-graph and routing-overlap checks."""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from hspf.uci.topology import ModelTopology
from hspf.validation.findings import SEVERITY_ERROR, SEVERITY_INFO
from hspf.validation.support import (
    directed_cycle_nodes,
    edge_set,
    make_finding,
    sort_values,
    weak_components,
)


def _reach_ids(topology: ModelTopology) -> set:
    opn_sequence = topology.operations.loc[topology.operations["in_opn_sequence"]]
    return set(opn_sequence.loc[opn_sequence["OPERATION"] == "RCHRES", "OPNID"].dropna())


def check_reach_routing_acyclicity(topology: ModelTopology) -> list:
    """U2-1: RCHRES-to-RCHRES union graph is acyclic."""

    rchres_edges = topology.reach_edges()
    reach_ids = _reach_ids(topology)
    edges = edge_set(rchres_edges, source_col="SVOLNO", target_col="TVOLNO")
    cycle_nodes = directed_cycle_nodes(edges, nodes=reach_ids)
    if not cycle_nodes:
        return []
    return [
        make_finding(
            "U2-1",
            SEVERITY_ERROR,
            "routing_graph",
            "uci",
            "UCI routing graph contains at least one cycle",
            expected="acyclic RCHRES routing graph",
            actual=sort_values(cycle_nodes),
        )
    ]


def check_reach_outlet_count(topology: ModelTopology) -> list:
    """U2-2: report outlet count in the UCI routing graph."""

    rchres_edges = topology.reach_edges()
    reach_ids = _reach_ids(topology)
    edges = edge_set(rchres_edges, source_col="SVOLNO", target_col="TVOLNO")
    sources = {source for source, _ in edges}
    nodes = set(reach_ids) | {node for edge in edges for node in edge}
    outlets = nodes - sources
    return [
        make_finding(
            "U2-2",
            SEVERITY_INFO,
            "routing_graph",
            "uci",
            "UCI outlet count",
            expected="reported for context",
            actual=len(outlets),
            attributes={"outlets": sort_values(outlets)},
        )
    ]


def check_disconnected_reach_networks(topology: ModelTopology) -> list:
    """U2-3: report disconnected weak components in the reach graph."""

    rchres_edges = topology.reach_edges()
    reach_ids = _reach_ids(topology)
    edges = edge_set(rchres_edges, source_col="SVOLNO", target_col="TVOLNO")
    components = weak_components(edges, nodes=reach_ids)
    if len(components) <= 1:
        return []
    return [
        make_finding(
            "U2-3",
            SEVERITY_INFO,
            "routing_component",
            index,
            "UCI routing graph has multiple disconnected sub-networks",
            expected="reported for context",
            actual=sort_values(component),
            attributes={"component_count": len(components)},
        )
        for index, component in enumerate(components, start=1)
    ]


def check_schematic_network_overlap(
    topology: ModelTopology,
    *,
    key_cols: Sequence[str] = (
        "SVOL",
        "SVOLNO",
        "TVOL",
        "TVOLNO",
        "SMEMN",
        "TMEMN",
    ),
) -> list:
    """U8: flag physical transfers defined in both SCHEMATIC and NETWORK."""

    schematic_transfers = topology.schematic_member_transfers()
    network_transfers = topology.network_member_transfers()
    if schematic_transfers.empty or network_transfers.empty:
        return []
    schematic_keys = set(
        schematic_transfers[list(key_cols)].drop_duplicates().itertuples(
            index=False,
            name=None,
        )
    )
    network_keys = set(
        network_transfers[list(key_cols)].drop_duplicates().itertuples(
            index=False,
            name=None,
        )
    )
    overlap = schematic_keys & network_keys
    return [
        make_finding(
            "U8",
            SEVERITY_ERROR,
            "routing_transfer",
            key,
            "Transfer appears in both SCHEMATIC and NETWORK",
            expected="one routing definition per physical transfer",
            actual="duplicate transfer across routing blocks",
        )
        for key in sort_values(overlap)
    ]


__all__ = [
    "check_reach_routing_acyclicity",
    "check_reach_outlet_count",
    "check_disconnected_reach_networks",
    "check_schematic_network_overlap",
]
