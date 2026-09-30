"""Validation scaffolding for the HSPF lake.

Validation is intentionally separated from ingest and publish:

* ``ingest.py`` records what the HBN output contains.
* ``manifest.py`` records what physical files were written.
* ``catalogs`` record logical model/run identity.
* ``publish.py`` controls when staged artifacts become visible.
* ``validate.py`` eventually checks that those layers agree.

For now, this module defines the validation vocabulary and public API without
enforcing checks.  Use :func:`deferred_validation_report` when a caller needs a
structured "validation intentionally skipped" result during the MVP phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from hspf.core.conventions import validate_run_id
from hspf.core.errors import ConventionError, ValidationError
from hspf.lake.ingest import IngestResult, RawBlockArtifact
from hspf.lake.layout import LakeLayout
from hspf.lake.manifest import ManifestFile, RunManifest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALIDATION_SCHEMA_VERSION = "lake-validation-v0"
VALIDATION_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

VALIDATION_STATUS_PASSED = "passed"
VALIDATION_STATUS_FAILED = "failed"
VALIDATION_STATUS_SKIPPED = "skipped"
VALIDATION_STATUSES = frozenset(
    {
        VALIDATION_STATUS_PASSED,
        VALIDATION_STATUS_FAILED,
        VALIDATION_STATUS_SKIPPED,
    }
)

VALIDATION_SEVERITY_ERROR = "error"
VALIDATION_SEVERITY_WARNING = "warning"
VALIDATION_SEVERITY_INFO = "info"
VALIDATION_SEVERITIES = frozenset(
    {
        VALIDATION_SEVERITY_ERROR,
        VALIDATION_SEVERITY_WARNING,
        VALIDATION_SEVERITY_INFO,
    }
)

CHECK_CATALOG = "catalog"
CHECK_MANIFEST = "manifest"
CHECK_LAYOUT_PATHS = "layout_paths"
CHECK_RAW_FILES = "raw_files"
CHECK_TIME_GEOMETRY = "time_geometry"
CHECK_SOURCE_CONSISTENCY = "source_consistency"
CHECK_CROSS_RESOLUTION = "cross_resolution"
CHECK_INGEST_RESULT = "ingest_result"
VALIDATION_CHECKS = (
    CHECK_CATALOG,
    CHECK_MANIFEST,
    CHECK_LAYOUT_PATHS,
    CHECK_RAW_FILES,
    CHECK_TIME_GEOMETRY,
    CHECK_SOURCE_CONSISTENCY,
    CHECK_CROSS_RESOLUTION,
)

RAW_REQUIRED_COLUMNS = (
    "run_id",
    "entity_id",
    "timestep",
    "entity_type",
    "activity",
    "output_level",
    "timestamp",
)

ValidationStatus = Literal["passed", "failed", "skipped"]
ValidationSeverity = Literal["error", "warning", "info"]


# ---------------------------------------------------------------------------
# Public records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationOptions:
    """Runtime switches for validation categories.

    These switches let the lake turn on checks incrementally.  The MVP can
    keep expensive/domain-specific checks disabled while preserving an honest
    record of which checks were skipped.
    """

    check_catalog: bool = True
    check_manifest: bool = True
    check_layout_paths: bool = True
    check_raw_files: bool = True
    check_time_geometry: bool = False
    check_source_consistency: bool = False
    check_cross_resolution: bool = False
    fail_fast: bool = False
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def requested_checks(self) -> tuple[str, ...]:
        """Return the checks requested by these options."""

        checks: list[str] = []
        if self.check_catalog:
            checks.append(CHECK_CATALOG)
        if self.check_manifest:
            checks.append(CHECK_MANIFEST)
        if self.check_layout_paths:
            checks.append(CHECK_LAYOUT_PATHS)
        if self.check_raw_files:
            checks.append(CHECK_RAW_FILES)
        if self.check_time_geometry:
            checks.append(CHECK_TIME_GEOMETRY)
        if self.check_source_consistency:
            checks.append(CHECK_SOURCE_CONSISTENCY)
        if self.check_cross_resolution:
            checks.append(CHECK_CROSS_RESOLUTION)
        return tuple(checks)


@dataclass(frozen=True)
class ValidationIssue:
    """One structured validation finding."""

    code: str
    severity: ValidationSeverity
    message: str
    run_id: str | None = None
    path: str | None = None
    block: str | None = None
    timestep: str | None = None
    entity_id: int | str | None = None
    variable: str | None = None
    expected: Any | None = None
    observed: Any | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in VALIDATION_SEVERITIES:
            raise ConventionError(f"Invalid validation severity: {self.severity!r}")

    def as_dict(self) -> dict[str, Any]:
        """Return a tabular/JSON-friendly representation."""

        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "run_id": self.run_id,
            "path": self.path,
            "block": self.block,
            "timestep": self.timestep,
            "entity_id": self.entity_id,
            "variable": self.variable,
            "expected": self.expected,
            "observed": self.observed,
            "attributes": self.attributes,
        }


@dataclass(frozen=True)
class ValidationCheckResult:
    """Result for one named validation category."""

    name: str
    status: ValidationStatus
    issues: tuple[ValidationIssue, ...] = ()
    message: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in VALIDATION_STATUSES:
            raise ConventionError(f"Invalid validation status: {self.status!r}")

    @property
    def passed(self) -> bool:
        """Return true if this check has no error findings."""

        return not any(
            issue.severity == VALIDATION_SEVERITY_ERROR
            for issue in self.issues
        )


@dataclass(frozen=True)
class ValidationReport:
    """Validation result for a run, ingest result, or lake object."""

    subject: str
    checked_at: str = field(default_factory=lambda: _utc_now())
    schema_version: str = VALIDATION_SCHEMA_VERSION
    checks: tuple[ValidationCheckResult, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != VALIDATION_SCHEMA_VERSION:
            raise ConventionError(
                f"Unsupported validation schema version: {self.schema_version!r}"
            )

    @property
    def issues(self) -> tuple[ValidationIssue, ...]:
        """Return all issues from all checks."""

        return tuple(issue for check in self.checks for issue in check.issues)

    @property
    def passed(self) -> bool:
        """Return true when no check has error findings."""

        return not any(
            issue.severity == VALIDATION_SEVERITY_ERROR
            for issue in self.issues
        )

    @property
    def skipped_checks(self) -> tuple[str, ...]:
        """Return names of checks that were explicitly skipped."""

        return tuple(
            check.name
            for check in self.checks
            if check.status == VALIDATION_STATUS_SKIPPED
        )

    def to_frame(self) -> pd.DataFrame:
        """Return issues as a DataFrame for notebook/report review."""

        return pd.DataFrame.from_records(
            issue.as_dict()
            for issue in self.issues
        )

    def raise_for_errors(self) -> None:
        """Raise a validation error if any error-severity issue exists."""

        errors = [
            issue
            for issue in self.issues
            if issue.severity == VALIDATION_SEVERITY_ERROR
        ]
        if errors:
            raise ValidationError(
                "Validation failed",
                context={"errors": [issue.as_dict() for issue in errors]},
            )


# ---------------------------------------------------------------------------
# MVP/deferred validation helper
# ---------------------------------------------------------------------------

def deferred_validation_report(
    subject: str,
    *,
    checks: tuple[str, ...] = VALIDATION_CHECKS,
    message: str = "Validation deferred for MVP workflow",
    attributes: dict[str, Any] | None = None,
) -> ValidationReport:
    """Return a report that explicitly marks requested checks as skipped."""

    return ValidationReport(
        subject=subject,
        checks=tuple(
            ValidationCheckResult(
                name=check,
                status=VALIDATION_STATUS_SKIPPED,
                message=message,
            )
            for check in checks
        ),
        attributes={} if attributes is None else dict(attributes),
    )


# ---------------------------------------------------------------------------
# Public validation entry points
# ---------------------------------------------------------------------------

def validate_run(
    layout: LakeLayout,
    run_id: str,
    *,
    options: ValidationOptions | None = None,
) -> ValidationReport:
    """Validate a run's catalog, manifest, raw files, and source consistency."""

    validate_run_id(run_id)
    raise NotImplementedError("Run validation is not yet implemented")


def validate_ingest_result(
    layout: LakeLayout,
    result: IngestResult,
    *,
    options: ValidationOptions | None = None,
) -> ValidationReport:
    """Validate files reported by one ingest result before manifest/publish."""

    validate_run_id(result.run_id)
    raise NotImplementedError("Ingest-result validation is not yet implemented")


def validate_manifest(
    layout: LakeLayout,
    manifest: RunManifest,
    *,
    options: ValidationOptions | None = None,
) -> ValidationReport:
    """Validate one run manifest against files on disk."""

    raise NotImplementedError("Manifest validation is not yet implemented")


def validate_catalog(
    layout: LakeLayout,
    *,
    options: ValidationOptions | None = None,
) -> ValidationReport:
    """Validate lake catalogs such as ``catalog/runs.parquet``."""

    raise NotImplementedError("Catalog validation is not yet implemented")


# ---------------------------------------------------------------------------
# Check skeletons
# ---------------------------------------------------------------------------

def validate_manifest_file(
    layout: LakeLayout,
    manifest_file: ManifestFile,
    *,
    run_id: str | None = None,
) -> ValidationCheckResult:
    """Validate one manifest file record against the referenced Parquet file."""

    raise NotImplementedError("Manifest-file validation is not yet implemented")


def validate_raw_artifact(
    layout: LakeLayout,
    artifact: RawBlockArtifact,
) -> ValidationCheckResult:
    """Validate one raw artifact immediately after ingest writes it."""

    raise NotImplementedError("Raw-artifact validation is not yet implemented")


def validate_layout_paths(
    layout: LakeLayout,
    manifest: RunManifest,
) -> ValidationCheckResult:
    """Validate path partitions against manifest/file metadata."""

    raise NotImplementedError("Layout-path validation is not yet implemented")


def validate_raw_file_schema(path: str | Path) -> ValidationCheckResult:
    """Validate required raw Parquet columns and basic schema expectations."""

    raise NotImplementedError("Raw-file schema validation is not yet implemented")


def validate_time_geometry(
    layout: LakeLayout,
    manifest: RunManifest,
) -> ValidationCheckResult:
    """Validate timestamp spacing, alignment, interval, and PYREND metadata."""

    raise NotImplementedError("Time-geometry validation is not yet implemented")


def validate_source_consistency(
    layout: LakeLayout,
    manifest: RunManifest,
) -> ValidationCheckResult:
    """Validate HBN-observed output against UCI-declared output settings."""

    raise NotImplementedError("Source-consistency validation is not yet implemented")


def validate_cross_resolution(
    layout: LakeLayout,
    manifest: RunManifest,
) -> ValidationCheckResult:
    """Validate consistency between fine and coarse engine-written outputs."""

    raise NotImplementedError("Cross-resolution validation is not yet implemented")


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def combine_reports(
    subject: str,
    reports: tuple[ValidationReport, ...],
    *,
    attributes: dict[str, Any] | None = None,
) -> ValidationReport:
    """Combine multiple validation reports into one report."""

    checks = tuple(check for report in reports for check in report.checks)
    return ValidationReport(
        subject=subject,
        checks=checks,
        attributes={} if attributes is None else dict(attributes),
    )


def skipped_check(
    name: str,
    *,
    message: str = "Validation check is not implemented",
) -> ValidationCheckResult:
    """Return one skipped validation check result."""

    return ValidationCheckResult(
        name=name,
        status=VALIDATION_STATUS_SKIPPED,
        message=message,
    )


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    """Return the current UTC time in the validation timestamp format."""

    return datetime.now(timezone.utc).strftime(VALIDATION_TIMESTAMP_FORMAT)
