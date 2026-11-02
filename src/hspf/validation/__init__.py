"""UCI/GIS validation package."""

from hspf.validation.classification import (
    build_reach_classification,
    build_subwatershed_precip_dsns,
    derive_precip_crosswalk,
)
from hspf.validation.findings import (
    CHECKS,
    SEVERITIES,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    Finding,
    findings_to_frame,
)
from hspf.validation.runners import (
    validate_all,
    validate_gis,
    validate_uci,
    validate_uci_gis,
)
from hspf.validation.support import DEFAULT_OUTLET_SENTINELS


__all__ = [
    "CHECKS",
    "SEVERITIES",
    "SEVERITY_ERROR",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "DEFAULT_OUTLET_SENTINELS",
    "Finding",
    "findings_to_frame",
    "build_reach_classification",
    "build_subwatershed_precip_dsns",
    "derive_precip_crosswalk",
    "validate_all",
    "validate_gis",
    "validate_uci",
    "validate_uci_gis",
]
