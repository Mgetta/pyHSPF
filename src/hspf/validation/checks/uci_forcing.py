"""UCI forcing, FTABLE, and reach-classification checks."""

from __future__ import annotations

from typing import Iterable

import pandas as pd

from hspf.uci.topology import ModelTopology
from hspf.validation.findings import SEVERITY_ERROR, SEVERITY_INFO, SEVERITY_WARNING
from hspf.validation.support import (
    LAND_OPERATIONS,
    METEOROLOGICAL_MEMBERS,
    as_set,
    make_finding,
    sort_values,
)


def check_reach_classification_flags(classification: pd.DataFrame) -> list:
    """U3: emit one informational finding for each reach with active flags."""

    flags = (
        "lake",
        "terminal",
        "routing_only",
        "non_contributing",
        "dummy_terminal_lake",
        "network_area_basis",
    )
    flag_frame = classification[list(flags)].fillna(False).astype(bool)
    flagged = classification.loc[flag_frame.any(axis=1)]

    findings = []
    for row in flagged.itertuples(index=False):
        active = [flag for flag in flags if bool(getattr(row, flag))]
        findings.append(
            make_finding(
                "U3",
                SEVERITY_INFO,
                "reach",
                row.reach_id,
                "Reach classification flags",
                expected="classification facts",
                actual="classified",
                attributes={"flags": active},
            )
        )
    return findings


def check_ftable_coverage(classification: pd.DataFrame, ftable_ids: Iterable) -> list:
    """U4-1: non-dummy routed reaches have FTABLEs."""

    ftable_set = as_set(ftable_ids)
    has_ftable = classification["reach_id"].isin(ftable_set)
    dummy = classification["dummy_terminal_lake"].fillna(False).astype(bool)
    dummy_missing = classification.loc[dummy & ~has_ftable]
    required_missing = classification.loc[~dummy & ~has_ftable]

    findings = []
    for row in dummy_missing.itertuples(index=False):
        findings.append(
            make_finding(
                "U4-1",
                SEVERITY_INFO,
                "reach",
                row.reach_id,
                "Dummy terminal lake has no FTABLE",
                expected="FTABLE optional for dummy terminal lake",
                actual=None,
            )
        )
    for row in required_missing.itertuples(index=False):
        findings.append(
            make_finding(
                "U4-1",
                SEVERITY_ERROR,
                "reach",
                row.reach_id,
                "RCHRES is missing an FTABLE",
                expected=f"FTABLE{row.reach_id}",
                actual=None,
            )
        )
    return findings


def check_orphan_ftables(topology: ModelTopology) -> list:
    """U4-2: FTABLEs have corresponding RCHRES ids."""

    opn_sequence = topology.operations.loc[topology.operations["in_opn_sequence"]]
    reach_ids = opn_sequence.loc[opn_sequence["OPERATION"] == "RCHRES", "OPNID"].dropna()
    reaches = set(reach_ids)
    return [
        make_finding(
            "U4-2",
            SEVERITY_INFO,
            "ftable",
            ftable_id,
            "FTABLE has no matching RCHRES",
            expected="matching RCHRES in OPN SEQUENCE",
            actual=None,
        )
        for ftable_id in sort_values(as_set(topology.ftable_ids) - reaches)
    ]


def _forcing_members_by_target(
    external_inputs: pd.DataFrame,
) -> dict[tuple, set]:
    if external_inputs.empty:
        return {}
    valid = external_inputs.dropna(subset=["TVOL", "TVOLNO", "TMEMN"])
    grouped = valid.groupby(["TVOL", "TVOLNO"])["TMEMN"].agg(lambda values: set(values))
    return grouped.to_dict()


def check_land_forcing_completeness(
    topology: ModelTopology,
    *,
    required_members: Iterable[str] = ("PREC", "PET"),
) -> list:
    """U5-1: PERLND/IMPLND operations receive required met forcing."""

    required = set(required_members)
    members_by_target = _forcing_members_by_target(topology.external_inputs)
    findings = []
    opn_sequence = topology.operations.loc[topology.operations["in_opn_sequence"]]
    land_frame = opn_sequence.loc[
        opn_sequence["OPERATION"].isin(LAND_OPERATIONS),
        ["OPERATION", "OPNID"],
    ].dropna()
    for row in land_frame.itertuples(index=False):
        key = (row.OPERATION, row.OPNID)
        missing = required - members_by_target.get(key, set())
        if missing:
            findings.append(
                make_finding(
                    "U5-1",
                    SEVERITY_ERROR,
                    key[0],
                    key[1],
                    "Land operation is missing required meteorological forcing",
                    expected=sort_values(required),
                    actual={"missing": sort_values(missing)},
                )
            )
    return findings


def check_lake_forcing_completeness(
    classification: pd.DataFrame,
    topology: ModelTopology,
    *,
    required_members: Iterable[str] = ("PREC", "PEVT"),
) -> list:
    """U5-2: LKFG=1 reaches receive lake-surface forcing."""

    required = set(required_members)
    members_by_target = _forcing_members_by_target(topology.external_inputs)
    findings = []
    lake_reaches = classification.loc[classification["lake"], "reach_id"].dropna()
    for reach_id in lake_reaches:
        missing = required - members_by_target.get(("RCHRES", reach_id), set())
        if missing:
            findings.append(
                make_finding(
                    "U5-2",
                    SEVERITY_WARNING,
                    "reach",
                    reach_id,
                    "Lake RCHRES is missing expected lake-surface forcing",
                    expected=sort_values(required),
                    actual={"missing": sort_values(missing)},
                )
            )
    return findings


def check_duplicate_precip_targets(
    topology: ModelTopology,
    *,
    weight_tolerance: float = 0.01,
) -> list:
    """U6-1: duplicate PREC targets are either valid weights or errors."""

    precip = topology.precip_assignments()
    findings = []
    grouped = precip.groupby(["TVOL", "TVOLNO"], dropna=False)
    for key, group in grouped:
        if len(group) <= 1:
            continue
        factor_sum = pd.to_numeric(group["MFACTOR"], errors="coerce").fillna(0).sum()
        severity = (
            SEVERITY_INFO
            if abs(float(factor_sum) - 1.0) <= weight_tolerance
            else SEVERITY_ERROR
        )
        findings.append(
            make_finding(
                "U6-1",
                severity,
                key[0],
                key[1],
                "Multiple PREC rows target one operation",
                expected="single PREC row or weights summing to 1.0",
                actual={
                    "row_count": len(group),
                    "dsn_values": sort_values(group["SVOLNO"].dropna().tolist()),
                    "factor_sum": float(factor_sum),
                },
            )
        )
    return findings


def check_precip_factors(
    topology: ModelTopology,
    *,
    max_reasonable_factor: float = 10.0,
) -> list:
    """U6-2: PREC factors are positive and not obviously unreasonable."""

    precip = topology.precip_assignments()
    if precip.empty:
        return []

    checked = precip.copy()
    checked["numeric_factor"] = pd.to_numeric(checked["MFACTOR"], errors="coerce")
    bad = checked.loc[
        checked["numeric_factor"].notna()
        & (
            (checked["numeric_factor"] <= 0)
            | (checked["numeric_factor"] > max_reasonable_factor)
        )
    ]

    findings = []
    for row in bad.itertuples(index=False):
        findings.append(
            make_finding(
                "U6-2",
                SEVERITY_WARNING,
                row.TVOL,
                row.TVOLNO,
                "PREC MFACTOR is outside the expected sanity range",
                expected=f"0 < MFACTOR <= {max_reasonable_factor}",
                actual=float(row.numeric_factor),
            )
        )
    return findings


def check_subwatershed_dsn_coherence(subwatershed_dsns: pd.DataFrame) -> list:
    """U7: direct contributors use the same PREC DSN as their receiving reach."""

    mismatch_mask = subwatershed_dsns["reach_dsn"].ne(
        subwatershed_dsns["contributor_dsn"]
    ).fillna(True)
    mismatches = subwatershed_dsns.loc[mismatch_mask]
    findings = []
    for row in mismatches.itertuples(index=False):
        findings.append(
            make_finding(
                "U7",
                SEVERITY_WARNING,
                "reach",
                row.reach_id,
                "Direct contributor PREC DSN differs from reach PREC DSN",
                expected=row.reach_dsn,
                actual=row.contributor_dsn,
                attributes={
                    "contributor_operation": row.contributor_operation,
                    "contributor_id": row.contributor_id,
                },
            )
        )
    return findings


def check_copy_met_distribution(
    topology: ModelTopology,
    *,
    meteorological_members: Iterable[str] = METEOROLOGICAL_MEMBERS,
) -> list:
    """U9: direct DSN lookup assumption fails if met is routed through COPY."""

    external_inputs = topology.external_inputs
    if external_inputs.empty:
        return []

    met_members = set(meteorological_members)
    findings = []
    copy_rows = external_inputs.loc[
        (external_inputs["TVOL"] == "COPY") & (external_inputs["TMEMN"].isin(met_members))
    ]
    for row in copy_rows.itertuples():
        findings.append(
            make_finding(
                "U9",
                SEVERITY_ERROR,
                "copy_operation",
                row.TVOLNO,
                "Meteorological input is routed through COPY; direct DSN lookup is unsupported",
                expected="direct EXT SOURCES met target",
                actual={"row": row.Index, "member": row.TMEMN},
            )
        )
    return findings


__all__ = [
    "check_reach_classification_flags",
    "check_ftable_coverage",
    "check_orphan_ftables",
    "check_land_forcing_completeness",
    "check_lake_forcing_completeness",
    "check_duplicate_precip_targets",
    "check_precip_factors",
    "check_subwatershed_dsn_coherence",
    "check_copy_met_distribution",
]
