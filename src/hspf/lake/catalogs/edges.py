"""Topology edge catalog records for the HSPF lake.

The edge catalog persists HSPF operation-to-operation connections. It records
the connection grain of SCHEMATIC rows and grouped NETWORK rows, but it does
not expand MASS-LINK member transfers. Member-level transfer recipes belong in
``mass_links.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable
from enum import StrEnum
from pathlib import Path

import pandas as pd

from hspf.core.conventions import validate_run_id
from hspf.core.errors import ConventionError
from hspf.core.types import OperationType
from hspf.lake.catalogs.io import (
    _optional_float,
    _optional_int,
    _optional_text,
    _positive_int,
    coerce_catalog_frame,
    read_catalog_table,
    records_to_frame,
    write_catalog_table,
)
from hspf.lake.layout import LakeLayout
from hspf.model.uci import UCI


EDGES_CATALOG_NAME = "edges"
SCHEMA_VERSION = "lake-edges-catalog-v0"



class EdgeKind(StrEnum):
    SCHEMATIC = "SCHEMATIC"
    NETWORK = "NETWORK"
    MANUAL = "MANUAL"

class EdgeRole(StrEnum):
    LAND_TO_REACH = "LAND_TO_REACH"
    LAND_TO_LAND = "LAND_TO_LAND"
    REACH_TO_REACH = "REACH_TO_REACH"
    UTILITY = "UTILITY"

EDGES_COLUMNS = (
    "run_id",
    "edge_id",
    "source_type",
    "source_id",
    "target_type",
    "target_id",
    "afactr",
    "mlno",
    "edge_kind",
    "edge_role",
    "tmemsb1",
    "tmemsb2",
    "target_run_id",
    "attributes",
)


@dataclass(frozen=True)
class EdgeRecord:
    """One operation-to-operation connection in a run.

    SCHEMATIC-origin rows preserve AFACTR and MLNO. NETWORK-origin rows
    represent grouped concrete source/target connections; their member-level
    details live in ``mass_links.py`` rows bound by ``edge_id``.
    """

    run_id: str
    edge_id: int
    source_type: OperationType | str
    source_id: int
    target_type: OperationType | str
    target_id: int
    edge_kind: EdgeKind
    edge_role: EdgeRole
    afactr: float | None = None
    mlno: int | None = None
    tmemsb1: str | int | None = None
    tmemsb2: str | int | None = None
    target_run_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_run_id(self.run_id)
        if self.target_run_id is not None:
            validate_run_id(self.target_run_id)

        source_type = _coerce_operation_type(self.source_type)
        target_type = _coerce_operation_type(self.target_type)
        edge_kind = _coerce_edgekind(self.edge_kind)
        edge_role = _coerce_edgerole(self.edge_role)

        #object.__setattr__(self, "edge_id", _nonnegative_int(self.edge_id, "edge_id"))
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "source_id", _positive_int(self.source_id, "source_id"))
        object.__setattr__(self, "target_type", target_type)
        object.__setattr__(self, "target_id", _positive_int(self.target_id, "target_id"))
        object.__setattr__(self, "edge_kind", edge_kind)
        object.__setattr__(self, "edge_role", edge_role)
        object.__setattr__(self, "afactr", _optional_float(self.afactr))
        object.__setattr__(self, "mlno", _optional_int(self.mlno))
        object.__setattr__(self, "tmemsb1", _optional_text(self.tmemsb1))
        object.__setattr__(self, "tmemsb2", _optional_text(self.tmemsb2))

        if edge_kind == EdgeKind.NETWORK and self.afactr is not None:
            raise ConventionError("NETWORK-origin edges must not store afactr")
        if edge_kind == EdgeKind.NETWORK and self.mlno is not None:
            raise ConventionError("NETWORK-origin edges must not store mlno")

    def as_dict(self) -> dict[str, Any]:
        """Return a Parquet-friendly dictionary representation."""

        return {
            "run_id": self.run_id,
            "edge_id": self.edge_id,
            "source_type": self.source_type.value,
            "source_id": self.source_id,
            "target_type": self.target_type.value,
            "target_id": self.target_id,
            "afactr": self.afactr,
            "mlno": self.mlno,
            "edge_kind": self.edge_kind.value,
            "edge_role": self.edge_role.value,
            "tmemsb1": self.tmemsb1,
            "tmemsb2": self.tmemsb2,
            "target_run_id": self.target_run_id,
            "attributes": json.dumps(self.attributes, sort_keys=True),
        }


def edges_from_uci(uci: UCI, run_id: str) -> tuple[EdgeRecord, ...]:
    """Compile SCHEMATIC and NETWORK connections into edge records."""

    #TODO add uci shared lexicon
    edges = []
    if 'SCHEMATIC' in uci.block_names():
        for index, row in uci.table('SCHEMATIC').iterrows():
            # Process each row to create edge records
            source_type = _coerce_operation_type(row['SVOL'])
            target_type = _coerce_operation_type(row['TVOL'])
            edge_role = infer_edge_role(source_type, target_type)
            edges.append(EdgeRecord(run_id=run_id,
                        edge_id=None,  # Replace with actual edge ID if available
                        source_type= source_type,
                        source_id=_positive_int(row["SVOLNO"], "SVOLNO"),
                        target_type= target_type,
                        target_id=_positive_int(row["TVOLNO"], "TVOLNO"),
                        edge_kind= "SCHEMATIC",
                        edge_role=edge_role,
                        afactr=_optional_float(row['AFACTR']),
                        mlno=_optional_int(row['MLNO']),
                        tmemsb1=_optional_text(row['TMEMSB1']),
                        tmemsb2=_optional_text(row['TMEMSB2']),
                        target_run_id=None,
                        attributes=row.get("attributes", {})))

    if 'NETWORK' in uci.block_names():
        for index, row in uci.table('NETWORK').iterrows():
            # Process each row to create edge records
            source_type = _coerce_operation_type(row['SVOL'])
            target_type = _coerce_operation_type(row['TVOL'])
            edge_role = infer_edge_role(source_type, target_type)
            edges.append(EdgeRecord(run_id=run_id,
                        edge_id=None,  # Replace with actual edge ID if available
                        source_type= source_type,
                        source_id=_positive_int(row["SVOLNO"], "SVOLNO"),
                        target_type= target_type,
                        target_id=_positive_int(row["TOPFST"], "TOPFST"),
                        edge_kind= "NETWORK",
                        edge_role= edge_role,
                        afactr= None,
                        mlno= None,
                        tmemsb1=_optional_text(row['TMEMSB1']),
                        tmemsb2=_optional_text(row['TMEMSB2']),
                        target_run_id=None,
                        attributes=row.get("attributes", {})))

    return tuple(edges)


#TODO move io to seaparte catalogs io module?
def edges_to_frame(records: Iterable[EdgeRecord]) -> pd.DataFrame:
    """Convert edge records to the catalog DataFrame shape."""

    return records_to_frame(records, EDGES_COLUMNS)


def read_edges_catalog(layout: LakeLayout, catalog_name) -> pd.DataFrame:
    """Read ``catalog/edges.parquet``."""

    return read_catalog_table(layout, EDGES_CATALOG_NAME, EDGES_COLUMNS)


def write_edges_catalog(
    layout: LakeLayout,
    records: Iterable[EdgeRecord] | pd.DataFrame,
    *,
    overwrite: bool = True,
) -> Path:
    """Write ``catalog/edges.parquet``."""

    return write_catalog_table(
        layout,
        EDGES_CATALOG_NAME,
        records,
        EDGES_COLUMNS,
        overwrite=overwrite,
        label="Edges",
    )


def infer_edge_role(
    source_type: OperationType | str,
    target_type: OperationType | str,
) -> EdgeRole:
    """Infer the high-level routing role for an operation connection."""

    if source_type in ['PERLND','IMPLND'] and target_type == "RCHRES":
        return EdgeRole.LAND_TO_REACH
    elif source_type in ['PERLND','IMPLND'] and target_type in ['PERLND','IMPLND']:
        return EdgeRole.LAND_TO_LAND
    elif source_type == "RCHRES" and target_type == "RCHRES":
        return EdgeRole.REACH_TO_REACH
    elif target_type in ["GENER","COPY"] or source_type in ["GENER","COPY"]:
        return EdgeRole.UTILITY
    else:
        raise ConventionError(f"Cannot infer edge role for source_type={source_type!r}, target_type={target_type!r}")

def _coerce_edges_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return coerce_catalog_frame(frame, EDGES_COLUMNS)

def _coerce_operation_type(value: OperationType | str) -> OperationType:
    if isinstance(value, OperationType):
        return value
    return OperationType(str(value).upper())

def _coerce_edgekind(value: EdgeKind | str) -> EdgeKind:
    if isinstance(value, EdgeKind):
        return value
    return EdgeKind(str(value).upper())

def _coerce_edgerole(value: EdgeRole | str) -> EdgeRole:
    if isinstance(value, EdgeRole):
        return value
    return EdgeRole(str(value).upper())

