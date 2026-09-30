"""Stored-series catalog records for the HSPF lake.

The series map is the run-specific inventory of raw time series that are
available in the lake.  It is derived from manifests and enriched with lexicon
defaults.  Raw files answer "where are the values?", the lexicon answers "what
does the variable mean?", and the series map answers "which series exist for
this run?".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from hspf.core.conventions import validate_run_id
from hspf.core.errors import ConventionError
from hspf.core.types import Activity, AggregationMethod, EntityRef, EntityType
from hspf.lake.catalogs.io import (
    _optional_int,
    _optional_text,
    append_catalog_rows,
    coerce_catalog_frame,
    read_catalog_table,
    records_to_frame,
    write_catalog_table,
)
from hspf.lake.catalogs.lexicon import variable_defaults
from hspf.lake.layout import LakeLayout
from hspf.lake.manifest import RunManifest, coverage_frame


SERIES_MAP_CATALOG_NAME = "series_map"
SCHEMA_VERSION = "lake-series-map-v0"

SERIES_MAP_COLUMNS = (
    "run_id",
    "entity_type",
    "activity",
    "variable",
    "timestep",
    "entity_id",
    "output_level",
    "interval_minutes",
    "pyrend",
    "timestamp_start",
    "timestamp_end",
    "n_entities",
    "produced_as",
    "aggregate_by",
    "weight_variable",
    "in_lexicon",
    "ingest_ids",
    "attributes",
)


@dataclass(frozen=True)
class SeriesRecord:
    """One run-specific stored-series catalog row."""

    run_id: str
    entity_type: EntityType | str
    activity: Activity | str
    variable: str
    timestep: str
    output_level: int
    interval_minutes: int | None = None
    pyrend: int = 12
    entity_id: int | None = None
    timestamp_start: str | pd.Timestamp | None = None
    timestamp_end: str | pd.Timestamp | None = None
    n_entities: int = 0
    produced_as: str | None = None
    aggregate_by: AggregationMethod | str | None = None
    weight_variable: str | None = None
    in_lexicon: bool = False
    ingest_ids: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_run_id(self.run_id)
        entity_type = _coerce_entity_type(self.entity_type)
        activity = _coerce_activity(self.activity)
        variable = self.variable.strip()
        timestep = self.timestep.strip()
        if not variable:
            raise ConventionError("variable cannot be empty")
        if not timestep:
            raise ConventionError("timestep cannot be empty")
        if self.entity_id is not None:
            entity_ref = EntityRef(entity_type, self.entity_id)
            object.__setattr__(self, "entity_id", entity_ref.entity_id)

        object.__setattr__(self, "entity_type", entity_type)
        object.__setattr__(self, "activity", activity)
        object.__setattr__(self, "variable", variable)
        object.__setattr__(self, "timestep", timestep)
        object.__setattr__(self, "output_level", int(self.output_level))
        object.__setattr__(
            self,
            "interval_minutes",
            _optional_int(self.interval_minutes),
        )
        object.__setattr__(self, "pyrend", int(self.pyrend))
        object.__setattr__(
            self,
            "timestamp_start",
            _timestamp_text(self.timestamp_start),
        )
        object.__setattr__(
            self,
            "timestamp_end",
            _timestamp_text(self.timestamp_end),
        )
        object.__setattr__(self, "n_entities", int(self.n_entities))
        object.__setattr__(self, "produced_as", _optional_text(self.produced_as))
        object.__setattr__(
            self,
            "aggregate_by",
            _coerce_aggregation(self.aggregate_by),
        )
        object.__setattr__(
            self,
            "weight_variable",
            _optional_text(self.weight_variable),
        )
        object.__setattr__(
            self,
            "ingest_ids",
            tuple(str(value) for value in self.ingest_ids if str(value).strip()),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a Parquet-friendly dictionary representation."""

        return {
            "run_id": self.run_id,
            "entity_type": self.entity_type.value,
            "activity": self.activity.value,
            "variable": self.variable,
            "timestep": self.timestep,
            "entity_id": self.entity_id,
            "output_level": self.output_level,
            "interval_minutes": self.interval_minutes,
            "pyrend": self.pyrend,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "n_entities": self.n_entities,
            "produced_as": self.produced_as,
            "aggregate_by": _enum_value(self.aggregate_by),
            "weight_variable": self.weight_variable,
            "in_lexicon": self.in_lexicon,
            "ingest_ids": json.dumps(list(self.ingest_ids), sort_keys=True),
            "attributes": json.dumps(self.attributes, sort_keys=True),
        }


def series_from_manifest(
    manifest: RunManifest,
    *,
    lexicon: pd.DataFrame | None = None,
) -> tuple[SeriesRecord, ...]:
    """Build series-map records from a run manifest."""

    coverage = coverage_frame(manifest, current_only=True)
    if coverage.empty:
        return ()

    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for _, row in coverage.iterrows():
        key = (
            manifest.run_id,
            str(row["entity_type"]).upper(),
            str(row["activity"]).upper(),
            str(row["variable"]).strip(),
            str(row["timestep"]).strip(),
            _optional_int(row.get("output_level")),
            _optional_int(row.get("interval_minutes")),
            int(_optional_int(row.get("pyrend")) or 12),
        )
        group = groups.setdefault(
            key,
            {
                "entity_ids": set(),
                "ingest_ids": set(),
                "timestamp_start": [],
                "timestamp_end": [],
                "attributes": {},
            },
        )
        entity_id = _optional_int(row.get("entity_id"))
        if entity_id is not None:
            group["entity_ids"].add(entity_id)
        if not _is_missing(row.get("ingest_id")):
            group["ingest_ids"].add(str(row.get("ingest_id")))
        if not _is_missing(row.get("timestamp_start")):
            group["timestamp_start"].append(pd.Timestamp(row.get("timestamp_start")))
        if not _is_missing(row.get("timestamp_end")):
            group["timestamp_end"].append(pd.Timestamp(row.get("timestamp_end")))

    records: list[SeriesRecord] = []
    for key, group in groups.items():
        (
            run_id,
            entity_type,
            activity,
            variable,
            timestep,
            output_level,
            interval_minutes,
            pyrend,
        ) = key
        defaults = _lexicon_defaults(
            lexicon,
            entity_type=entity_type,
            activity=activity,
            variable=variable,
        )
        records.append(
            SeriesRecord(
                run_id=run_id,
                entity_type=entity_type,
                activity=activity,
                variable=variable,
                timestep=timestep,
                output_level=output_level,
                interval_minutes=interval_minutes,
                pyrend=pyrend,
                entity_id=None,
                timestamp_start=_min_timestamp(group["timestamp_start"]),
                timestamp_end=_max_timestamp(group["timestamp_end"]),
                n_entities=len(group["entity_ids"]),
                aggregate_by=defaults.get("aggregate_by"),
                weight_variable=defaults.get("weight_variable"),
                in_lexicon=bool(defaults.get("in_lexicon")),
                ingest_ids=tuple(sorted(group["ingest_ids"])),
                attributes=group["attributes"],
            )
        )

    return tuple(records)


def series_to_frame(records: Iterable[SeriesRecord]) -> pd.DataFrame:
    """Convert series-map records to the catalog DataFrame shape."""

    return records_to_frame(records, SERIES_MAP_COLUMNS)


def read_series_map(layout: LakeLayout) -> pd.DataFrame:
    """Read ``catalog/series_map.parquet``."""

    return read_catalog_table(layout, SERIES_MAP_CATALOG_NAME, SERIES_MAP_COLUMNS)


def write_series_map(
    layout: LakeLayout,
    records: Iterable[SeriesRecord] | pd.DataFrame,
    *,
    overwrite: bool = True,
) -> Path:
    """Write ``catalog/series_map.parquet``."""

    return write_catalog_table(
        layout,
        SERIES_MAP_CATALOG_NAME,
        records,
        SERIES_MAP_COLUMNS,
        overwrite=overwrite,
        label="Series map",
    )


def append_series_records(
    layout: LakeLayout,
    records: Iterable[SeriesRecord],
    *,
    replace_run_id: bool = False,
) -> Path:
    """Append series records, optionally replacing all rows for their run_ids."""

    return append_catalog_rows(
        layout,
        SERIES_MAP_CATALOG_NAME,
        records,
        SERIES_MAP_COLUMNS,
        replace_existing=replace_run_id,
        label="Series map",
    )


def available_series(
    series: pd.DataFrame,
    *,
    run_id: str,
    entity_type: EntityType | str | None = None,
    activity: Activity | str | None = None,
    variable: str | None = None,
    timestep: str | None = None,
) -> pd.DataFrame:
    """Return series-map rows matching common query filters."""

    validate_run_id(run_id)
    frame = _coerce_series_frame(series)
    mask = frame["run_id"] == run_id
    if entity_type is not None:
        mask &= frame["entity_type"] == _coerce_entity_type(entity_type).value
    if activity is not None:
        mask &= frame["activity"] == _coerce_activity(activity).value
    if variable is not None:
        mask &= frame["variable"] == variable
    if timestep is not None:
        mask &= frame["timestep"] == timestep
    return frame.loc[mask].copy()


def finest_timestep(
    series: pd.DataFrame,
    *,
    run_id: str,
    entity_type: EntityType | str,
    activity: Activity | str,
    variable: str,
) -> str | None:
    """Return the finest available timestep label for one stored series."""

    rows = available_series(
        series,
        run_id=run_id,
        entity_type=entity_type,
        activity=activity,
        variable=variable,
    )
    if rows.empty:
        return None
    rows = rows.sort_values(["output_level", "interval_minutes"], na_position="last")
    return str(rows.iloc[0]["timestep"])


def effective_series_row(
    series: pd.DataFrame,
    *,
    run_id: str,
    entity_type: EntityType | str,
    activity: Activity | str,
    variable: str,
    timestep: str,
    entity_id: int | None = None,
) -> pd.Series:
    """Return the entity-specific row if present, otherwise the default row."""

    rows = available_series(
        series,
        run_id=run_id,
        entity_type=entity_type,
        activity=activity,
        variable=variable,
        timestep=timestep,
    )
    if rows.empty:
        raise ConventionError(
            f"Series is not registered: {run_id} {entity_type} {activity} "
            f"{variable} {timestep}"
        )
    if entity_id is not None:
        specific = rows.loc[rows["entity_id"] == int(entity_id)]
        if not specific.empty:
            return specific.iloc[0]
    defaults = rows.loc[rows["entity_id"].isna()]
    if not defaults.empty:
        return defaults.iloc[0]
    return rows.iloc[0]


def _coerce_series_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return coerce_catalog_frame(frame, SERIES_MAP_COLUMNS)


def _lexicon_defaults(
    lexicon: pd.DataFrame | None,
    *,
    entity_type: str,
    activity: str,
    variable: str,
) -> dict[str, Any]:
    if lexicon is None or lexicon.empty:
        return {"in_lexicon": False}
    try:
        record = variable_defaults(
            lexicon,
            entity_type=entity_type,
            activity=activity,
            variable=variable,
        )
    except ConventionError:
        return {"in_lexicon": False}
    return {
        "in_lexicon": True,
        "aggregate_by": record.aggregate_by,
        "weight_variable": record.weight_variable,
    }


def _coerce_entity_type(value: EntityType | str) -> EntityType:
    if isinstance(value, EntityType):
        return value
    return EntityType(str(value).upper())


def _coerce_activity(value: Activity | str) -> Activity:
    if isinstance(value, Activity):
        return value
    return Activity(str(value).upper())


def _coerce_aggregation(
    value: AggregationMethod | str | None,
) -> AggregationMethod | None:
    value = _none_if_na(value)
    if value is None:
        return None
    if isinstance(value, AggregationMethod):
        return value
    return AggregationMethod(str(value).upper())


def _min_timestamp(values: list[pd.Timestamp]) -> str | None:
    if not values:
        return None
    return pd.Timestamp(min(values)).isoformat()


def _max_timestamp(values: list[pd.Timestamp]) -> str | None:
    if not values:
        return None
    return pd.Timestamp(max(values)).isoformat()


def _timestamp_text(value: str | pd.Timestamp | None) -> str | None:
    value = _none_if_na(value)
    if value is None:
        return None
    return pd.Timestamp(value).isoformat()


def _none_if_na(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _is_missing(value: Any) -> bool:
    return _none_if_na(value) is None


def _enum_value(value: Any) -> str | None:
    value = _none_if_na(value)
    return None if value is None else getattr(value, "value", value)
