"""UCI referential-integrity checks."""

from __future__ import annotations

import pandas as pd

from hspf.core.types import RoutingSource
from hspf.uci.topology import ModelTopology
from hspf.validation.findings import SEVERITY_ERROR, SEVERITY_WARNING
from hspf.validation.support import LAND_OPERATIONS, make_finding, sort_values


GENINFO_OPERATIONS = frozenset({"PERLND", "IMPLND", "RCHRES"})


def _opn_sequence(topology: ModelTopology) -> pd.DataFrame:
    return topology.operations.loc[topology.operations["in_opn_sequence"]].copy()


def _operation_keys(topology: ModelTopology) -> set[tuple]:
    opn_sequence = _opn_sequence(topology)
    subset = opn_sequence[["OPERATION", "OPNID"]].dropna()
    return set(subset.itertuples(index=False, name=None))


def _routing_source_context(routing_source: object) -> tuple[str, str]:
    if routing_source == RoutingSource.SCHEMATIC_MASS_LINK.value:
        return "U1-1", "SCHEMATIC"
    if routing_source == RoutingSource.NETWORK.value:
        return "U1-2", "NETWORK"
    return "U1-2", "CONNECTION"


def check_connection_membership(topology: ModelTopology) -> list:
    """U1-1/U1-2: routing connection endpoints exist in OPN SEQUENCE."""

    connections = topology.connections
    if connections.empty:
        return []

    opn_keys = _operation_keys(topology)
    findings = []

    source_candidates = connections.loc[
        connections["SVOL"].notna() & connections["SVOLNO"].notna()
    ]
    source_keys = pd.MultiIndex.from_frame(source_candidates[["SVOL", "SVOLNO"]])
    bad_sources = source_candidates.loc[~source_keys.isin(list(opn_keys))]
    for row in bad_sources.itertuples():
        check_id, block_name = _routing_source_context(row.routing_source)
        key = (row.SVOL, row.SVOLNO)
        findings.append(
            make_finding(
                check_id,
                SEVERITY_ERROR,
                f"{block_name.lower()}_source",
                {"row": row.Index, "operation": row.SVOL, "id": row.SVOLNO},
                f"{block_name} source operation is absent from OPN SEQUENCE",
                expected="operation/id present in OPN SEQUENCE",
                actual=key,
            )
        )

    target_candidates = connections.loc[
        connections["TVOL"].notna() & connections["TVOLNO"].notna()
    ]
    target_keys = pd.MultiIndex.from_frame(target_candidates[["TVOL", "TVOLNO"]])
    bad_targets = target_candidates.loc[~target_keys.isin(list(opn_keys))]
    for row in bad_targets.itertuples():
        check_id, block_name = _routing_source_context(row.routing_source)
        key = (row.TVOL, row.TVOLNO)
        findings.append(
            make_finding(
                check_id,
                SEVERITY_ERROR,
                f"{block_name.lower()}_target",
                {"row": row.Index, "operation": row.TVOL, "id": row.TVOLNO},
                f"{block_name} target operation is absent from OPN SEQUENCE",
                expected="operation/id present in OPN SEQUENCE",
                actual=key,
            )
        )

    return findings


def check_external_input_targets(topology: ModelTopology) -> list:
    """U1-3: EXT SOURCES targets exist in OPN SEQUENCE."""

    external_inputs = topology.external_inputs
    if external_inputs.empty:
        return []

    opn_keys = _operation_keys(topology)
    target_candidates = external_inputs.loc[
        external_inputs["TVOL"].notna() & external_inputs["TVOLNO"].notna()
    ]
    target_keys = pd.MultiIndex.from_frame(target_candidates[["TVOL", "TVOLNO"]])
    bad_targets = target_candidates.loc[~target_keys.isin(list(opn_keys))]

    findings = []
    for row in bad_targets.itertuples():
        key = (row.TVOL, row.TVOLNO)
        findings.append(
            make_finding(
                "U1-3",
                SEVERITY_ERROR,
                "ext_sources_target",
                {"row": row.Index, "operation": row.TVOL, "id": row.TVOLNO},
                "EXT SOURCES target is absent from OPN SEQUENCE",
                expected="target operation/id present in OPN SEQUENCE",
                actual=key,
            )
        )
    return findings


def check_geninfo_reconciliation(topology: ModelTopology) -> list:
    """U1-4: OPN SEQUENCE and GEN-INFO rows reconcile by operation type."""

    operations = topology.operations
    tracked = operations.loc[operations["OPERATION"].isin(GENINFO_OPERATIONS)]
    missing_geninfo = tracked.loc[
        tracked["in_opn_sequence"] & ~tracked["has_geninfo"]
    ]
    orphan_geninfo = tracked.loc[
        tracked["has_geninfo"] & ~tracked["in_opn_sequence"]
    ]

    findings = []
    for row in missing_geninfo.sort_values(["OPERATION", "OPNID"]).itertuples(index=False):
        findings.append(
            make_finding(
                "U1-4",
                SEVERITY_ERROR,
                row.OPERATION,
                row.OPNID,
                "Operation is in OPN SEQUENCE but missing GEN-INFO",
                expected="GEN-INFO row",
                actual=None,
            )
        )
    for row in orphan_geninfo.sort_values(["OPERATION", "OPNID"]).itertuples(index=False):
        findings.append(
            make_finding(
                "U1-4",
                SEVERITY_WARNING,
                row.OPERATION,
                row.OPNID,
                "GEN-INFO row has no matching OPN SEQUENCE entry",
                expected="no orphan GEN-INFO rows",
                actual="orphan",
            )
        )
    return findings


def check_unmatched_masslink_transfers(topology: ModelTopology) -> list:
    """U1-5: SCHEMATIC rows match at least one MASS-LINK recipe row."""

    transfers = topology.schematic_member_transfers()
    if transfers.empty:
        return []

    unmatched = transfers.loc[transfers["MLNO"].notna() & transfers["table_name"].isna()]

    findings = []
    for row in unmatched.itertuples():
        source_row = row.source_row if "source_row" in unmatched else row.Index
        findings.append(
            make_finding(
                "U1-5",
                SEVERITY_ERROR,
                "masslink",
                row.MLNO,
                "SCHEMATIC row did not match a MASS-LINK recipe row",
                expected="matching MASS-LINK row for (MLNO, SVOL, TVOL)",
                actual={"source_row": source_row, "mlno": row.MLNO},
            )
        )
    return findings


def check_dangling_land_segments(topology: ModelTopology) -> list:
    """U1-6: PERLND/IMPLND operations in OPN SEQUENCE drain somewhere."""

    opn_sequence = _opn_sequence(topology)
    opn_land_frame = opn_sequence.loc[
        opn_sequence["OPERATION"].isin(LAND_OPERATIONS),
        ["OPERATION", "OPNID"],
    ].dropna()
    routed_land_frame = topology.connections.loc[
        topology.connections["SVOL"].isin(LAND_OPERATIONS),
        ["SVOL", "SVOLNO"],
    ].dropna()
    opn_land = set(opn_land_frame.itertuples(index=False, name=None))
    routed_land = set(routed_land_frame.itertuples(index=False, name=None))
    return [
        make_finding(
            "U1-6",
            SEVERITY_WARNING,
            operation,
            op_id,
            "Land operation is in OPN SEQUENCE but has no outgoing routing edge",
            expected="source edge in SCHEMATIC or NETWORK",
            actual=None,
        )
        for operation, op_id in sort_values(opn_land - routed_land)
    ]


__all__ = [
    "check_connection_membership",
    "check_external_input_targets",
    "check_geninfo_reconciliation",
    "check_unmatched_masslink_transfers",
    "check_dangling_land_segments",
]
