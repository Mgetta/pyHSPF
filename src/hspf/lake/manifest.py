"""Manifest records for raw lake ingests.

The run catalog answers "which logical model runs exist?".  A run manifest
answers "which physical files were written for this run, and what series do
they contain?".  Manifests are scoped to one run and live beside that run's raw
files as ``manifest.json``.

Object shape:

    RunManifest
        └── ManifestIngest
                └── ManifestFile

``RunManifest`` is the JSON document for one run. ``ManifestIngest`` is one
append-only write event. ``ManifestFile`` is one physical Parquet artifact and
the coarse coverage metadata needed to plan backfills and simple lake queries.

This MVP manifest is intentionally simple:

* It is append-only at the ingest-event level.
* It records one file entry per raw Parquet artifact.
* It can derive an entity/variable coverage table for query planning and
  future backfill checks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import pandas as pd

from hspf.core.conventions import validate_run_id
from hspf.core.errors import ConventionError
from hspf.lake.ingest import IngestResult, RawBlockArtifact
from hspf.lake.layout import LakeLayout


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIFEST_SCHEMA_VERSION = "lake-run-manifest-v0"
MANIFEST_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Columns added by lake ingest for identity, partitioning, and timestamps.
# Everything else in a raw Parquet file is treated as an HBN variable/member.
FILE_METADATA_COLUMNS = frozenset(
    {
        "run_id",
        "block",
        "timestep",
        "entity_type",
        "activity",
        "output_level",
        "entity_id",
        "timestamp",
    }
)


# ---------------------------------------------------------------------------
# Small helpers needed by dataclass defaults
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    """Return the current UTC time in the manifest timestamp format."""

    return datetime.now(timezone.utc).strftime(MANIFEST_TIMESTAMP_FORMAT)


# ---------------------------------------------------------------------------
# Public manifest records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ManifestFile:
    """One physical raw Parquet file recorded in a run manifest.

    This is the manifest's lowest-level record.  It intentionally stores
    coarse coverage only: which entities, variables, and timestamp extent are
    present in the file.  It does not store row-level values.
    """

    path: str
    block: str
    entity_type: str
    activity: str
    output_level: int
    timestep: str
    rows: int
    columns: tuple[str, ...]
    variables: tuple[str, ...]
    entity_ids: tuple[Any, ...] = ()
    timestamp_start: str | None = None
    timestamp_end: str | None = None
    interval_minutes: int | None = None
    pyrend: int = 12
    year: int | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "path": self.path,
            "block": self.block,
            "entity_type": self.entity_type,
            "activity": self.activity,
            "output_level": self.output_level,
            "timestep": self.timestep,
            "rows": self.rows,
            "columns": list(self.columns),
            "variables": list(self.variables),
            "entity_ids": list(self.entity_ids),
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "interval_minutes": self.interval_minutes,
            "pyrend": self.pyrend,
            "year": self.year,
        }

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "ManifestFile":
        """Build a manifest file record from parsed JSON."""

        return cls(
            path=str(values["path"]),
            block=str(values["block"]),
            entity_type=str(values["entity_type"]),
            activity=str(values["activity"]),
            output_level=int(values["output_level"]),
            timestep=str(values["timestep"]),
            rows=int(values["rows"]),
            columns=tuple(str(column) for column in values.get("columns", ())),
            variables=tuple(str(variable) for variable in values.get("variables", ())),
            entity_ids=tuple(values.get("entity_ids", ())),
            timestamp_start=values.get("timestamp_start"),
            timestamp_end=values.get("timestamp_end"),
            interval_minutes=_optional_int(values.get("interval_minutes")),
            pyrend=int(values.get("pyrend", 12)),
            year=_optional_int(values.get("year")),
        )


@dataclass(frozen=True)
class ManifestIngest:
    """One append-only ingest event in a run manifest.

    A later backfill can append a new ingest event to the same run manifest
    without rewriting the earlier event.  The latest file record for a physical
    path is treated as current state.
    """

    ingest_id: str
    created_at: str
    files: tuple[ManifestFile, ...]
    source_uci: str | None = None
    source_hbns: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "ingest_id": self.ingest_id,
            "created_at": self.created_at,
            "source_uci": self.source_uci,
            "source_hbns": list(self.source_hbns),
            "attributes": self.attributes,
            "files": [file.as_dict() for file in self.files],
        }

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "ManifestIngest":
        """Build an ingest event from parsed JSON."""

        return cls(
            ingest_id=str(values["ingest_id"]),
            created_at=str(values["created_at"]),
            source_uci=values.get("source_uci"),
            source_hbns=tuple(str(path) for path in values.get("source_hbns", ())),
            attributes=dict(values.get("attributes", {})),
            files=tuple(
                ManifestFile.from_dict(file_values)
                for file_values in values.get("files", ())
            ),
        )


@dataclass(frozen=True)
class RunManifest:
    """Manifest for one raw lake run.

    The run manifest is deliberately scoped below the run catalog.  It should
    describe the contents of one run's raw files, not own model/run lifecycle
    information such as active/deprecated status.
    """

    run_id: str
    schema_version: str = MANIFEST_SCHEMA_VERSION
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    ingests: tuple[ManifestIngest, ...] = ()

    def __post_init__(self) -> None:
        validate_run_id(self.run_id)
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ConventionError(
                f"Unsupported manifest schema version: {self.schema_version!r}"
            )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ingests": [ingest.as_dict() for ingest in self.ingests],
        }

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "RunManifest":
        """Build a run manifest from parsed JSON."""

        return cls(
            schema_version=str(values["schema_version"]),
            run_id=str(values["run_id"]),
            created_at=str(values["created_at"]),
            updated_at=str(values["updated_at"]),
            ingests=tuple(
                ManifestIngest.from_dict(ingest_values)
                for ingest_values in values.get("ingests", ())
            ),
        )

    def append(self, ingest: ManifestIngest) -> "RunManifest":
        """Return a copy with ``ingest`` appended."""

        return RunManifest(
            run_id=self.run_id,
            schema_version=self.schema_version,
            created_at=self.created_at,
            updated_at=_utc_now(),
            ingests=(*self.ingests, ingest),
        )

    @property
    def files(self) -> tuple[ManifestFile, ...]:
        """Return all files recorded across ingest events."""

        return tuple(file for ingest in self.ingests for file in ingest.files)


# ---------------------------------------------------------------------------
# Manifest JSON read/write
# ---------------------------------------------------------------------------

def read_manifest(
    layout: LakeLayout,
    run_id: str,
    *,
    missing_ok: bool = True,
) -> RunManifest:
    """Read a run manifest from ``layout``.

    If ``missing_ok`` is true, a new empty manifest is returned when the file
    does not exist.
    """

    validate_run_id(run_id)
    path = layout.manifest_path(run_id)
    if not path.exists():
        if missing_ok:
            return RunManifest(run_id=run_id)
        raise ConventionError(f"Manifest does not exist: {path}")

    values = json.loads(path.read_text(encoding="utf-8"))
    manifest = RunManifest.from_dict(values)
    if manifest.run_id != run_id:
        raise ConventionError(
            f"Manifest run_id {manifest.run_id!r} does not match requested "
            f"run_id {run_id!r}"
        )
    return manifest


def write_manifest(
    layout: LakeLayout,
    manifest: RunManifest,
    *,
    overwrite: bool = True,
) -> Path:
    """Write ``manifest`` to its run folder and return the path."""

    path = layout.manifest_path(manifest.run_id)
    if path.exists() and not overwrite:
        raise ConventionError(f"Manifest already exists: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest.as_dict(), indent=2, sort_keys=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(f"{payload}\n", encoding="utf-8")
    temp_path.replace(path)
    return path


# ---------------------------------------------------------------------------
# Ingest-result conversion
# ---------------------------------------------------------------------------

def record_ingest(
    layout: LakeLayout,
    result: IngestResult,
    *,
    source_uci: str | Path | None = None,
    source_hbns: Iterable[str | Path] = (),
    attributes: dict[str, Any] | None = None,
    inspect_files: bool = True,
) -> RunManifest:
    """Append one ingest result to the run manifest and write it to disk."""

    manifest = read_manifest(layout, result.run_id, missing_ok=True)
    ingest = ingest_event_from_result(
        layout,
        result,
        source_uci=source_uci,
        source_hbns=source_hbns,
        attributes=attributes,
        inspect_files=inspect_files,
    )
    manifest = manifest.append(ingest)
    write_manifest(layout, manifest)
    return manifest


def ingest_event_from_result(
    layout: LakeLayout,
    result: IngestResult,
    *,
    source_uci: str | Path | None = None,
    source_hbns: Iterable[str | Path] = (),
    attributes: dict[str, Any] | None = None,
    inspect_files: bool = True,
) -> ManifestIngest:
    """Create a manifest ingest event from an ``IngestResult``."""

    validate_run_id(result.run_id)
    created_at = _utc_now()
    return ManifestIngest(
        ingest_id=f"{created_at.replace(':', '').replace('-', '')}-{uuid4().hex[:8]}",
        created_at=created_at,
        source_uci=None if source_uci is None else str(source_uci),
        source_hbns=tuple(str(path) for path in source_hbns),
        attributes={} if attributes is None else dict(attributes),
        files=tuple(
            file_record_from_artifact(
                layout,
                artifact,
                inspect_file=inspect_files,
            )
            for artifact in result.artifacts
        ),
    )


def file_record_from_artifact(
    layout: LakeLayout,
    artifact: RawBlockArtifact,
    *,
    inspect_file: bool = True,
) -> ManifestFile:
    """Create one manifest file record from an ingest artifact."""

    variables = tuple(
        column
        for column in artifact.columns
        if column not in FILE_METADATA_COLUMNS
    )
    entity_ids: tuple[Any, ...] = ()
    timestamp_start: str | None = None
    timestamp_end: str | None = None

    if inspect_file:
        entity_ids, timestamp_start, timestamp_end = _read_file_coverage(
            artifact.path
        )

    return ManifestFile(
        path=_relative_manifest_path(layout, artifact.path),
        block=artifact.block.name,
        entity_type=artifact.block.entity_type.value,
        activity=artifact.block.activity.value,
        output_level=int(artifact.output_level),
        timestep=artifact.timestep,
        rows=artifact.rows,
        columns=tuple(artifact.columns),
        variables=variables,
        entity_ids=entity_ids,
        timestamp_start=timestamp_start,
        timestamp_end=timestamp_end,
        interval_minutes=artifact.interval_minutes,
        pyrend=artifact.pyrend,
        year=artifact.year,
    )


# ---------------------------------------------------------------------------
# Coverage/query helpers
# ---------------------------------------------------------------------------

def coverage_frame(
    manifest: RunManifest,
    *,
    current_only: bool = True,
) -> pd.DataFrame:
    """Return one row per manifest file/entity/variable combination.

    By default, only the latest record for each physical path is returned.
    Pass ``current_only=False`` to inspect every append-only ingest event.
    """

    rows: list[dict[str, Any]] = []
    for ingest, file in _file_records(manifest, current_only=current_only):
        entity_ids = file.entity_ids or (None,)
        variables = file.variables or (None,)
        for entity_id in entity_ids:
            for variable in variables:
                rows.append(
                    {
                        "run_id": manifest.run_id,
                        "ingest_id": ingest.ingest_id,
                        "path": file.path,
                        "block": file.block,
                        "entity_type": file.entity_type,
                        "activity": file.activity,
                        "output_level": file.output_level,
                        "timestep": file.timestep,
                        "entity_id": entity_id,
                        "variable": variable,
                        "timestamp_start": file.timestamp_start,
                        "timestamp_end": file.timestamp_end,
                        "rows": file.rows,
                        "interval_minutes": file.interval_minutes,
                        "pyrend": file.pyrend,
                        "year": file.year,
                    }
                )
    return pd.DataFrame.from_records(rows)


def current_files(manifest: RunManifest) -> tuple[ManifestFile, ...]:
    """Return the latest record for each physical manifest path."""

    return tuple(file for _, file in _file_records(manifest, current_only=True))


# ---------------------------------------------------------------------------
# Internal manifest traversal and file inspection
# ---------------------------------------------------------------------------

def _file_records(
    manifest: RunManifest,
    *,
    current_only: bool,
) -> tuple[tuple[ManifestIngest, ManifestFile], ...]:
    """Return manifest file records with their owning ingest event."""

    if not current_only:
        return tuple(
            (ingest, file)
            for ingest in manifest.ingests
            for file in ingest.files
        )

    # Assumes append only file writes to manfiest (could order by ingest timestamp if needed to determine the latest file)
    by_path: dict[str, tuple[ManifestIngest, ManifestFile]] = {}
    for ingest in manifest.ingests:
        for file in ingest.files:
            by_path[file.path] = (ingest, file)
    return tuple(by_path.values())


def _read_file_coverage(path: Path) -> tuple[tuple[Any, ...], str | None, str | None]:
    """Read entity ids and timestamp extent from a raw Parquet file."""

    if not path.exists():
        raise ConventionError(f"Manifest artifact does not exist: {path}")

    frame = pd.read_parquet(path, columns=["entity_id", "timestamp"])
    missing_columns = {"entity_id", "timestamp"} - set(frame.columns)
    if missing_columns:
        raise ConventionError(
            f"Manifest artifact {path} is missing required columns: "
            f"{sorted(missing_columns)!r}"
        )
    if frame.empty:
        return (), None, None

    entity_ids = tuple(
        _json_scalar(value)
        for value in sorted(frame["entity_id"].dropna().unique())
    )
    timestamps = pd.to_datetime(frame["timestamp"]).dropna()
    if timestamps.empty:
        return entity_ids, None, None

    return (
        entity_ids,
        _timestamp_text(timestamps.min()),
        _timestamp_text(timestamps.max()),
    )


def _relative_manifest_path(layout: LakeLayout, path: Path) -> str:
    """Return a path relative to the lake root for stable manifest storage."""

    root = layout.root.resolve()
    resolved_path = Path(path).resolve()
    try:
        return resolved_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ConventionError(
            f"Manifest artifact path is outside the lake root: {path}"
        ) from exc


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _timestamp_text(value: Any) -> str:
    """Return an ISO timestamp string for JSON storage."""

    return pd.Timestamp(value).isoformat()


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _json_scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value
