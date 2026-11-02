"""Shared validation vocabulary and result records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import pandas as pd


SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"
SEVERITIES = frozenset({SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO})


CHECKS: dict[str, str] = {
    "G0-1": "Reach key validity",
    "G0-2": "Downstream reference validity",
    "G0-3": "Reach graph sanity",
    "G0-4": "Catchment attribute completeness",
    "U1-1": "SCHEMATIC membership",
    "U1-2": "NETWORK membership",
    "U1-3": "EXT SOURCES target membership",
    "U1-4": "GEN-INFO reconciliation",
    "U1-5": "MASS-LINK references",
    "U1-6": "Dangling land segments",
    "U2-1": "Routing graph acyclicity",
    "U2-2": "Outlet count",
    "U2-3": "Disconnected sub-networks",
    "U3": "Reach classification",
    "U4-1": "FTABLE coverage",
    "U4-2": "Orphan FTABLEs",
    "U5-1": "Land forcing completeness",
    "U5-2": "Lake forcing completeness",
    "U6-1": "Duplicate PREC targets",
    "U6-2": "PREC MFACTOR sanity",
    "U7": "Subwatershed DSN coherence",
    "U8": "SCHEMATIC/NETWORK overlap",
    "U9": "Assumption guard: no COPY met distribution",
    "G1-1": "Reaches missing from GIS",
    "G1-2": "Extra GIS reaches",
    "G2-1": "Topology edge diff",
    "G2-2": "Multi-exit surplus",
    "G2-3": "Terminal concordance",
    "G3": "Lake concordance",
    "G4-1": "Catchment coverage",
    "G4-2": "Catchment reach validity",
    "G4-3": "Catchments on routing-only reaches",
    "G5-1": "DSN-group construction",
    "G5-2": "Spatial metzone derivation",
    "G5-3": "Round-trip coherence",
    "G5-4": "Crosswalk conformance",
    "G6": "Area comparison",
}


@dataclass(frozen=True)
class Finding:
    """One structured validation finding."""

    check_id: str
    severity: str
    subject_type: str
    subject_id: Any
    message: str
    expected: Any | None = None
    actual: Any | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.check_id not in CHECKS:
            raise ValueError(f"Unknown check id: {self.check_id!r}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"Invalid severity: {self.severity!r}")

    def as_dict(self) -> dict[str, Any]:
        """Return a tabular/JSON-friendly representation."""

        return {
            "check_id": self.check_id,
            "check_name": CHECKS[self.check_id],
            "severity": self.severity,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
            "attributes": self.attributes,
        }


def findings_to_frame(findings: Iterable[Finding]) -> pd.DataFrame:
    """Return findings as a DataFrame for review."""

    return pd.DataFrame.from_records(finding.as_dict() for finding in findings)


__all__ = [
    "CHECKS",
    "SEVERITIES",
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "SEVERITY_INFO",
    "Finding",
    "findings_to_frame",
]
