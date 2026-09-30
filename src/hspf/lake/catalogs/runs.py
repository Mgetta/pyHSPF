"""Run catalog records for the HSPF lake.

The run catalog is the lake's model-run identity table. It replaces the old
warehouse natural key with a surrogate ``run_id`` and captures only run-level
facts here; entity, series, recipe, and UCI-table details belong in later
catalog modules.
"""

from __future__ import annotations

import getpass
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from hspf.core.conventions import (
    make_run_id,
    normalize_path,
    normalize_unit_system,
    validate_run_id,
)
from hspf.core.errors import ConventionError
from hspf.core.types import UnitSystem
from hspf.lake.catalogs.io import (
    append_one_record,
    coerce_catalog_frame,
    read_catalog_table,
    records_to_frame,
    write_catalog_table,
)
from hspf.lake.layout import LakeLayout
from hspf.model.uci import UCI


RUNS_CATALOG_NAME = "runs"
RUN_STATUS_ACTIVE = "active"
RUN_STATUS_DEPRECATED = "deprecated"
SCHEMA_VERSION = "lake-run-catalog-v0"
RUNS_COLUMNS = (
    "run_id",
    "model_name",
    "run_timestamp",
    "execution_user",
    "sim_start",
    "sim_end",
    "unit_system",
    "engine_version",
    "schema_version",
    "pipeline_git_hash",
    "source_uci",
    "source_hbns",
    "status",
    "attributes",
)


@dataclass(frozen=True)
class RunRecord:
    """One row in the lake run catalog."""

    run_id: str
    model_name: str
    run_timestamp: pd.Timestamp
    execution_user: str
    sim_start: pd.Timestamp
    sim_end: pd.Timestamp
    unit_system: UnitSystem
    engine_version: str | None = None
    schema_version: str = SCHEMA_VERSION
    pipeline_git_hash: str | None = None
    source_uci: str | None = None
    source_hbns: tuple[str, ...] = ()
    status: str = RUN_STATUS_ACTIVE
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_run_id(self.run_id)
        _validate_status(self.status)
        object.__setattr__(self, "model_name", self.model_name.strip())
        object.__setattr__(self, "run_timestamp", pd.Timestamp(self.run_timestamp))
        object.__setattr__(self, "sim_start", pd.Timestamp(self.sim_start))
        object.__setattr__(self, "sim_end", pd.Timestamp(self.sim_end))
        object.__setattr__(
            self,
            "unit_system",
            normalize_unit_system(self.unit_system),
        )
        object.__setattr__(
            self,
            "source_hbns",
            tuple(str(path) for path in self.source_hbns),
        )
        if not self.model_name:
            raise ConventionError("model_name cannot be empty")

    def as_dict(self) -> dict[str, Any]:
        """Return a Parquet-friendly dictionary representation."""

        return {
            "run_id": self.run_id,
            "model_name": self.model_name,
            "run_timestamp": self.run_timestamp,
            "execution_user": self.execution_user,
            "sim_start": self.sim_start,
            "sim_end": self.sim_end,
            "unit_system": int(self.unit_system),
            "engine_version": self.engine_version,
            "schema_version": self.schema_version,
            "pipeline_git_hash": self.pipeline_git_hash,
            "source_uci": self.source_uci,
            "source_hbns": json.dumps(list(self.source_hbns), sort_keys=True),
            "status": self.status,
            "attributes": json.dumps(self.attributes, sort_keys=True),
        }


def create_run_record(
    uci: UCI,
    *,
    model_name: str | None = None,
    run_id: str | None = None,
    run_timestamp: pd.Timestamp | None = None,
    execution_user: str | None = None,
    hbn_paths: Iterable[str | Path] | None = None,
    engine_version: str | None = None,
    schema_version: str = SCHEMA_VERSION,
    pipeline_git_hash: str | None = None,
    status: str = RUN_STATUS_ACTIVE,
    attributes: dict[str, Any] | None = None,
) -> RunRecord:
    """Create a run-catalog record from UCI-level metadata."""

    global_row = _global_row(uci)
    timestamp = _utc_now() if run_timestamp is None else pd.Timestamp(run_timestamp)
    resolved_model_name = model_name or uci.name
    resolved_run_id = run_id or make_run_id(timestamp, resolved_model_name)
    source_hbns = tuple(
        normalize_path(path)
        for path in (hbn_paths if hbn_paths is not None else uci.hbn_paths)
    )

    return RunRecord(
        run_id=resolved_run_id,
        model_name=resolved_model_name,
        run_timestamp=timestamp,
        execution_user=execution_user or getpass.getuser(),
        sim_start=_global_date(global_row, "start_date"),
        sim_end=_global_date(global_row, "end_date"),
        unit_system=normalize_unit_system(int(global_row["units_flag"])),
        engine_version=engine_version,
        schema_version=schema_version,
        pipeline_git_hash=pipeline_git_hash,
        source_uci=normalize_path(uci.filepath),
        source_hbns=source_hbns,
        status=status,
        attributes=attributes or {},
    )


def runs_to_frame(records: Iterable[RunRecord]) -> pd.DataFrame:
    """Convert run records to the catalog DataFrame shape."""

    return records_to_frame(records, RUNS_COLUMNS)


def read_runs_catalog(layout: LakeLayout) -> pd.DataFrame:
    """Read ``catalog/runs.parquet``."""

    return read_catalog_table(layout, RUNS_CATALOG_NAME, RUNS_COLUMNS)


def write_runs_catalog(
    layout: LakeLayout,
    records: Iterable[RunRecord] | pd.DataFrame,
    *,
    overwrite: bool = True,
) -> Path:
    """Write ``catalog/runs.parquet``."""

    return write_catalog_table(
        layout,
        RUNS_CATALOG_NAME,
        records,
        RUNS_COLUMNS,
        overwrite=overwrite,
        label="Run",
    )


def append_run_record(
    layout: LakeLayout,
    record: RunRecord,
    *,
    replace_existing: bool = False,
) -> Path:
    """Append one run record to ``catalog/runs.parquet``."""

    return append_one_record(
        layout,
        RUNS_CATALOG_NAME,
        record,
        RUNS_COLUMNS,
        key_column="run_id",
        key_value=record.run_id,
        replace_existing=replace_existing,
        label="Run",
    )


def superseded_status(replacement_run_id: str) -> str:
    """Return the catalog status string for a superseded run."""

    validate_run_id(replacement_run_id)
    return f"superseded_by:{replacement_run_id}"


def update_run_status(
    runs: pd.DataFrame,
    run_id: str,
    status: str,
) -> pd.DataFrame:
    """Return a copy of a run catalog frame with one updated status."""

    validate_run_id(run_id)
    _validate_status(status)
    if run_id not in set(runs["run_id"]):
        raise ConventionError(f"Run is not registered: {run_id}")

    updated = runs.copy()
    updated.loc[updated["run_id"] == run_id, "status"] = status
    return updated


def _coerce_runs_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return coerce_catalog_frame(frame, RUNS_COLUMNS)


def _global_row(uci: UCI) -> pd.Series:
    global_table = uci.table("GLOBAL")
    if global_table.empty:
        raise ConventionError(f"UCI GLOBAL table is empty: {uci.filepath}")
    return global_table.iloc[0]


def _global_date(row: pd.Series, column: str) -> pd.Timestamp:
    return pd.Timestamp(str(row[column]).replace("/", "-"))


def _utc_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC").tz_localize(None)


def _validate_status(status: str) -> None:
    if status in {RUN_STATUS_ACTIVE, RUN_STATUS_DEPRECATED}:
        return
    if status.startswith("superseded_by:"):
        validate_run_id(status.split(":", 1)[1])
        return
    raise ConventionError(f"Invalid run status: {status!r}")