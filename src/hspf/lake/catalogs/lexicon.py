"""Variable lexicon records for the HSPF lake.

The lexicon is the run-independent dictionary for raw HBN columns.  It answers
"what does this variable mean?" but not "which runs contain it?".  Run-specific
availability belongs in ``series_map.py`` and physical file coverage belongs in
``manifest.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

import pandas as pd

from hspf.core.errors import ConventionError
from hspf.core.types import (
    Activity,
    AggregationMethod,
    EntityType,
    TemporalSemantics,
    VALID_ACTIVITIES,
    VariableKind,
)
from hspf.lake.catalogs.io import (
    _optional_text,
    coerce_catalog_frame,
    read_catalog_table,
    records_to_frame,
    write_catalog_table,
)
from hspf.lake.layout import LakeLayout
from hspf.lake.manifest import RunManifest, coverage_frame


LEXICON_CATALOG_NAME = "variables"
SCHEMA_VERSION = "lake-variable-lexicon-v0"

LEXICON_COLUMNS = (
    "entity_type",
    "activity",
    "variable",
    "base_member",
    "qualifier",
    "description",
    "temporal_semantics",
    "physical_kind",
    "aggregate_by",
    "weight_variable",
    "unit_dimension",
    "english_unit",
    "metric_unit",
    "aliases",
    "source",
    "attributes",
)


@dataclass(frozen=True)
class VariableRecord:
    """One run-independent variable dictionary row."""

    entity_type: EntityType | str
    activity: Activity | str
    variable: str
    base_member: str | None = None
    qualifier: str | None = None
    description: str | None = None
    temporal_semantics: TemporalSemantics | str | None = None
    physical_kind: VariableKind | str | None = None
    aggregate_by: AggregationMethod | str | None = None
    weight_variable: str | None = None
    unit_dimension: str | None = None
    english_unit: str | None = None
    metric_unit: str | None = None
    aliases: tuple[str, ...] = ()
    source: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        entity_type = _coerce_entity_type(self.entity_type)
        activity = _coerce_activity(self.activity)
        variable = self.variable.strip()
        if not variable:
            raise ConventionError("variable cannot be empty")
        if activity not in VALID_ACTIVITIES[entity_type]:
            raise ConventionError(
                f"{activity.value} is not valid for {entity_type.value}"
            )

        object.__setattr__(self, "entity_type", entity_type)
        object.__setattr__(self, "activity", activity)
        object.__setattr__(self, "variable", variable)
        object.__setattr__(
            self,
            "base_member",
            _optional_text(self.base_member) or variable,
        )
        object.__setattr__(self, "qualifier", _optional_text(self.qualifier))
        object.__setattr__(self, "description", _optional_text(self.description))
        object.__setattr__(
            self,
            "temporal_semantics",
            _coerce_temporal(self.temporal_semantics),
        )
        object.__setattr__(
            self,
            "physical_kind",
            _coerce_variable_kind(self.physical_kind),
        )
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
            "unit_dimension",
            _optional_text(self.unit_dimension),
        )
        object.__setattr__(self, "english_unit", _optional_text(self.english_unit))
        object.__setattr__(self, "metric_unit", _optional_text(self.metric_unit))
        object.__setattr__(
            self,
            "aliases",
            tuple(alias.strip() for alias in self.aliases if alias.strip()),
        )
        object.__setattr__(self, "source", _optional_text(self.source))

    def as_dict(self) -> dict[str, Any]:
        """Return a Parquet-friendly dictionary representation."""

        return {
            "entity_type": self.entity_type.value,
            "activity": self.activity.value,
            "variable": self.variable,
            "base_member": self.base_member,
            "qualifier": self.qualifier,
            "description": self.description,
            "temporal_semantics": _enum_value(self.temporal_semantics),
            "physical_kind": _enum_value(self.physical_kind),
            "aggregate_by": _enum_value(self.aggregate_by),
            "weight_variable": self.weight_variable,
            "unit_dimension": self.unit_dimension,
            "english_unit": self.english_unit,
            "metric_unit": self.metric_unit,
            "aliases": json.dumps(list(self.aliases), sort_keys=True),
            "source": self.source,
            "attributes": json.dumps(self.attributes, sort_keys=True),
        }



def lexicon_to_frame(records: Iterable[VariableRecord]) -> pd.DataFrame:
    """Convert variable records to the catalog DataFrame shape."""

    return records_to_frame(records, LEXICON_COLUMNS)


def frame_to_records(frame: pd.DataFrame) -> tuple[VariableRecord, ...]:
    """Convert a lexicon DataFrame into variable records."""

    frame = _coerce_lexicon_frame(frame)
    return tuple(VariableRecord(**_row_to_record_kwargs(row)) for _, row in frame.iterrows())


def read_lexicon(layout: LakeLayout) -> pd.DataFrame:
    """Read ``catalog/variables.parquet``."""

    return read_catalog_table(layout, LEXICON_CATALOG_NAME, LEXICON_COLUMNS)


def unknown_variables(
    lexicon: pd.DataFrame,
    manifest_or_coverage: RunManifest | pd.DataFrame,
) -> pd.DataFrame:
    """Return manifest variables that do not have lexicon rows."""

    coverage = (
        coverage_frame(manifest_or_coverage)
        if isinstance(manifest_or_coverage, RunManifest)
        else manifest_or_coverage.copy()
    )
    if coverage.empty:
        return coverage.loc[:, []]

    known_keys = _lexicon_keys(_coerce_lexicon_frame(lexicon))
    rows = []
    for _, row in coverage.iterrows():
        key = (
            str(row["entity_type"]).upper(),
            str(row["activity"]).upper(),
            str(row["variable"]).strip(),
        )
        if key not in known_keys:
            rows.append(
                {
                    "run_id": row.get("run_id"),
                    "entity_type": key[0],
                    "activity": key[1],
                    "variable": key[2],
                    "timestep": row.get("timestep"),
                    "path": row.get("path"),
                }
            )
    return pd.DataFrame.from_records(rows).drop_duplicates()


def _coerce_lexicon_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return coerce_catalog_frame(frame, LEXICON_COLUMNS)


def _row_to_record_kwargs(row: pd.Series) -> dict[str, Any]:
    values = {column: _none_if_na(row[column]) for column in LEXICON_COLUMNS}
    values["aliases"] = tuple(_json_list(values["aliases"]))
    values["attributes"] = _json_dict(values["attributes"])
    return values


def _lexicon_keys(frame: pd.DataFrame) -> set[tuple[str, str, str]]:
    if frame.empty:
        return set()
    return {
        (
            str(row["entity_type"]).upper(),
            str(row["activity"]).upper(),
            str(row["variable"]).strip(),
        )
        for _, row in frame.iterrows()
    }


def _drop_lexicon_keys(
    frame: pd.DataFrame,
    keys: set[tuple[str, str, str]],
) -> pd.DataFrame:
    if not keys:
        return frame
    keep = [
        (
            str(row["entity_type"]).upper(),
            str(row["activity"]).upper(),
            str(row["variable"]).strip(),
        )
        not in keys
        for _, row in frame.iterrows()
    ]
    return frame.loc[keep].copy()


def _matches_variable(record: VariableRecord, requested: str) -> bool:
    normalized = requested.strip().lower()
    names = {record.variable.lower(), record.base_member.lower()}
    names.update(alias.lower() for alias in record.aliases)
    return normalized in names


def _coerce_entity_type(value: EntityType | str) -> EntityType:
    if isinstance(value, EntityType):
        return value
    return EntityType(str(value).upper())


def _coerce_activity(value: Activity | str) -> Activity:
    if isinstance(value, Activity):
        return value
    return Activity(str(value).upper())


def _coerce_temporal(value: TemporalSemantics | str | None) -> TemporalSemantics | None:
    text = _optional_text(value)
    if text is None:
        return None
    if isinstance(value, TemporalSemantics):
        return value
    return TemporalSemantics(text.upper().replace("_", "-"))


def _coerce_variable_kind(value: VariableKind | str | None) -> VariableKind | None:
    text = _optional_text(value)
    if text is None:
        return None
    if isinstance(value, VariableKind):
        return value
    return VariableKind(text.lower())


def _coerce_aggregation(
    value: AggregationMethod | str | None,
) -> AggregationMethod | None:
    text = _optional_text(value)
    if text is None:
        return None
    if isinstance(value, AggregationMethod):
        return value
    return AggregationMethod(text.upper())


def _none_if_na(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _json_list(value: Any) -> list[Any]:
    value = _none_if_na(value)
    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _json_dict(value: Any) -> dict[str, Any]:
    value = _none_if_na(value)
    if value is None:
        return {}
    if isinstance(value, str):
        return dict(json.loads(value))
    return dict(value)


def _enum_value(value: Any) -> str | None:
    value = _none_if_na(value)
    return None if value is None else getattr(value, "value", value)
