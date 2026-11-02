"""Internal helpers shared by validation checks."""

from __future__ import annotations

from typing import Any, Hashable, Iterable, Mapping

import networkx as nx
import pandas as pd

from hspf.validation.findings import Finding


DEFAULT_OUTLET_SENTINELS = frozenset({999, -999})
LAND_OPERATIONS = frozenset({"PERLND", "IMPLND"})
METEOROLOGICAL_MEMBERS = frozenset(
    {"PREC", "PEVT", "PET", "ATEM", "CLOU", "DEWP", "SOLR", "WIND"}
)


def is_missing(value: Any) -> bool:
    """Return True for scalar missing values."""

    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def as_set(values: Iterable[Any]) -> set[Any]:
    """Return non-missing values as a set."""

    return {value for value in values if not is_missing(value)}


def sort_values(values: Iterable[Any]) -> list[Any]:
    """Sort mixed-type identifiers deterministically."""

    return sorted(values, key=lambda value: (str(type(value)), str(value)))


def make_finding(
    check_id: str,
    severity: str,
    subject_type: str,
    subject_id: Any,
    message: str,
    *,
    expected: Any | None = None,
    actual: Any | None = None,
    attributes: Mapping[str, Any] | None = None,
) -> Finding:
    """Build a finding while keeping check code compact."""

    return Finding(
        check_id=check_id,
        severity=severity,
        subject_type=subject_type,
        subject_id=subject_id,
        message=message,
        expected=expected,
        actual=actual,
        attributes={} if attributes is None else dict(attributes),
    )


def edge_set(
    edges: pd.DataFrame,
    *,
    source_col: str,
    target_col: str,
) -> set[tuple[Any, Any]]:
    """Return non-missing directed edges from a two-column frame."""

    if edges.empty:
        return set()
    subset = edges[[source_col, target_col]].dropna()
    return set(subset.itertuples(index=False, name=None))


def filtered_gis_edges(
    reach_layer: pd.DataFrame,
    *,
    outlet_sentinels: Iterable[Any] = DEFAULT_OUTLET_SENTINELS,
) -> set[tuple[Any, Any]]:
    """Return GIS reach edges after removing outlet sentinel references."""

    if reach_layer.empty:
        return set()
    sentinels = set(outlet_sentinels)
    valid = reach_layer.loc[
        reach_layer["ReachID"].notna()
        & reach_layer["DS_ReachID"].notna()
        & ~reach_layer["DS_ReachID"].isin(sentinels),
        ["ReachID", "DS_ReachID"],
    ]
    return set(valid.itertuples(index=False, name=None))


def directed_cycle_nodes(
    edges: Iterable[tuple[Hashable, Hashable]],
    *,
    nodes: Iterable[Hashable] = (),
) -> set[Hashable]:
    """Return nodes in one directed cycle, if any."""

    graph = nx.DiGraph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from(edges)
    try:
        cycle = nx.find_cycle(graph, orientation="original")
    except nx.NetworkXNoCycle:
        return set()
    return {source for source, _, _ in cycle} | {target for _, target, _ in cycle}


def weak_components(
    edges: Iterable[tuple[Hashable, Hashable]],
    *,
    nodes: Iterable[Hashable] = (),
) -> list[set[Hashable]]:
    """Return weakly connected components for a directed graph."""

    graph = nx.DiGraph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from(edges)
    return [set(component) for component in nx.weakly_connected_components(graph)]


__all__ = [
    "DEFAULT_OUTLET_SENTINELS",
    "LAND_OPERATIONS",
    "METEOROLOGICAL_MEMBERS",
    "is_missing",
    "as_set",
    "sort_values",
    "make_finding",
    "edge_set",
    "filtered_gis_edges",
    "directed_cycle_nodes",
    "weak_components",
]
