"""Explicit orchestration for the UCI/GIS validation campaign."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import pandas as pd

from hspf.uci.topology import ModelTopology
from hspf.validation.classification import (
    build_reach_classification,
    build_subwatershed_precip_dsns,
)
from hspf.validation.checks.gis_layer import (
    check_catchment_attributes,
    check_downstream_references,
    check_gis_reach_graph,
    check_reach_keys,
)
from hspf.validation.checks.uci_forcing import (
    check_copy_met_distribution,
    check_duplicate_precip_targets,
    check_ftable_coverage,
    check_lake_forcing_completeness,
    check_land_forcing_completeness,
    check_orphan_ftables,
    check_precip_factors,
    check_reach_classification_flags,
    check_subwatershed_dsn_coherence,
)
from hspf.validation.checks.uci_gis import (
    check_area_comparison_deferred,
    check_catchment_coverage,
    check_lake_concordance,
    check_precip_crosswalk,
    check_precip_metzones,
    check_reach_set_reconciliation,
    check_routing_edge_concordance,
    check_terminal_reach_concordance,
)
from hspf.validation.checks.uci_membership import (
    check_connection_membership,
    check_dangling_land_segments,
    check_external_input_targets,
    check_geninfo_reconciliation,
    check_unmatched_masslink_transfers,
)
from hspf.validation.checks.uci_routing import (
    check_disconnected_reach_networks,
    check_reach_outlet_count,
    check_reach_routing_acyclicity,
    check_schematic_network_overlap,
)
from hspf.validation.findings import Finding
from hspf.validation.support import DEFAULT_OUTLET_SENTINELS


def validate_gis(
    reach_layer: pd.DataFrame,
    catchments: pd.DataFrame,
    *,
    outlet_sentinels: Iterable[Any] = DEFAULT_OUTLET_SENTINELS,
) -> list[Finding]:
    """Run GIS-internal validation checks."""

    findings: list[Finding] = []
    findings.extend(check_reach_keys(reach_layer))
    findings.extend(
        check_downstream_references(
            reach_layer,
            outlet_sentinels=outlet_sentinels,
        )
    )
    findings.extend(
        check_gis_reach_graph(
            reach_layer,
            outlet_sentinels=outlet_sentinels,
        )
    )
    findings.extend(check_catchment_attributes(catchments))
    return findings


def validate_uci(topology: ModelTopology) -> list[Finding]:
    """Run UCI-internal validation checks against a prepared topology."""

    classification = build_reach_classification(topology)

    findings: list[Finding] = []
    findings.extend(check_connection_membership(topology))
    findings.extend(check_external_input_targets(topology))
    findings.extend(check_geninfo_reconciliation(topology))
    findings.extend(check_unmatched_masslink_transfers(topology))
    findings.extend(check_dangling_land_segments(topology))
    findings.extend(check_reach_routing_acyclicity(topology))
    findings.extend(check_reach_outlet_count(topology))
    findings.extend(check_disconnected_reach_networks(topology))
    findings.extend(check_reach_classification_flags(classification))
    findings.extend(check_ftable_coverage(classification, topology.ftable_ids))
    findings.extend(check_orphan_ftables(topology))
    findings.extend(check_land_forcing_completeness(topology))
    findings.extend(check_lake_forcing_completeness(classification, topology))
    findings.extend(check_duplicate_precip_targets(topology))
    findings.extend(check_precip_factors(topology))
    findings.extend(check_subwatershed_dsn_coherence(build_subwatershed_precip_dsns(topology)))
    findings.extend(check_schematic_network_overlap(topology))
    findings.extend(check_copy_met_distribution(topology))
    return findings


def validate_uci_gis(
    topology: ModelTopology,
    reach_layer: pd.DataFrame,
    catchments: pd.DataFrame,
    *,
    spatial_metzones: pd.DataFrame | None = None,
    precip_crosswalk: Mapping[Any, Any] | pd.DataFrame | None = None,
    outlet_sentinels: Iterable[Any] = DEFAULT_OUTLET_SENTINELS,
) -> list[Finding]:
    """Run validation checks that compare UCI topology against GIS tables."""

    classification = build_reach_classification(topology)

    findings: list[Finding] = []
    findings.extend(check_reach_set_reconciliation(topology, reach_layer))
    findings.extend(
        check_routing_edge_concordance(
            topology,
            reach_layer,
            outlet_sentinels=outlet_sentinels,
        )
    )
    findings.extend(
        check_terminal_reach_concordance(
            topology,
            reach_layer,
            outlet_sentinels=outlet_sentinels,
        )
    )
    findings.extend(check_lake_concordance(classification, reach_layer))
    findings.extend(check_catchment_coverage(classification, catchments, topology))

    if spatial_metzones is not None:
        operation_metzones = spatial_metzones[["operation", "op_id", "metzone"]].drop_duplicates()
        findings.extend(check_precip_metzones(topology, operation_metzones))
        if precip_crosswalk is not None:
            findings.extend(
                check_precip_crosswalk(
                    topology,
                    operation_metzones,
                    precip_crosswalk,
                )
            )

    findings.extend(check_area_comparison_deferred())
    return findings


def validate_all(
    topology: ModelTopology,
    reach_layer: pd.DataFrame,
    catchments: pd.DataFrame,
    *,
    spatial_metzones: pd.DataFrame | None = None,
    precip_crosswalk: Mapping[Any, Any] | pd.DataFrame | None = None,
    outlet_sentinels: Iterable[Any] = DEFAULT_OUTLET_SENTINELS,
) -> list[Finding]:
    """Run the full planned validation campaign."""

    findings: list[Finding] = []
    findings.extend(
        validate_gis(
            reach_layer,
            catchments,
            outlet_sentinels=outlet_sentinels,
        )
    )
    findings.extend(validate_uci(topology))
    findings.extend(
        validate_uci_gis(
            topology,
            reach_layer,
            catchments,
            spatial_metzones=spatial_metzones,
            precip_crosswalk=precip_crosswalk,
            outlet_sentinels=outlet_sentinels,
        )
    )
    return findings


__all__ = [
    "validate_gis",
    "validate_uci",
    "validate_uci_gis",
    "validate_all",
]
