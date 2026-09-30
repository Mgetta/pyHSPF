"""Entity catalog records for the HSPF lake.

The entity catalog is the per-run roster of modeled PERLND, IMPLND, and RCHRES
objects.  It turns attribute-based questions ("all cropland PERLNDs") into
entity-id lists that can be used to read raw time series efficiently.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from hspf.core.conventions import validate_run_id
from hspf.core.errors import ConventionError
from hspf.core.types import EntityRef, EntityType
from hspf.model.uci import UCI


ENTITIES_CATALOG_NAME = "entities"
SCHEMA_VERSION = "lake-entities-catalog-v0"

ENTITIES_COLUMNS = (
    "run_id",
    "entity_type",
    "entity_id",
)


@dataclass(frozen=True)
class EntityRecord:
    """One modeled HSPF entity within one run."""

    run_id: str
    entity_type: EntityType | str
    entity_id: int
    
    def __post_init__(self) -> None:
        validate_run_id(self.run_id)
        entity_ref = EntityRef(self.entity_type, self.entity_id)
        object.__setattr__(self, "entity_type", entity_ref.entity_type)
        object.__setattr__(self, "entity_id", entity_ref.entity_id)


    def as_dict(self) -> dict[str, Any]:
        """Return a Parquet-friendly dictionary representation."""

        return {
            "run_id": self.run_id,
            "entity_type": self.entity_type.value,
            "entity_id": self.entity_id}


def entities_from_uci(
    uci: UCI,
    run_id: str,
) -> tuple[EntityRecord, ...]:
    """Compile entity records for ``run_id`` from UCI operation metadata."""

    records: list[EntityRecord] = []
    for entity_type in EntityType:
        opnids = uci.valid_opnids[entity_type.value]
        for entity_id in opnids:
            records.append(
                EntityRecord(
                    run_id=run_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
            )

    return tuple(records)

