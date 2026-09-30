"""MASS-LINK and NETWORK member-transfer catalog records for the HSPF lake.

This module stores the member-level transfer declarations that complement
``edges.py``. MASS-LINK rows are reusable templates bound to SCHEMATIC edges by
``mlno``. NETWORK rows are concrete inline transfers bound directly to an edge
by ``edge_id``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from enum import StrEnum

import pandas as pd

from hspf.core.conventions import validate_run_id
from hspf.core.errors import ConventionError
from hspf.core.types import OperationType, TransformFunction
from hspf.lake.catalogs.io import (
    _enum_value,
    _nonnegative_int,
    _optional_float,
    _optional_int,
    _optional_text,
    _required_text,
)
from hspf.lake.catalogs.edges import EdgeRecord
from hspf.model.uci import UCI
from hspf.model.uci import _masslinks

class MassLinkOrigin(StrEnum):
    MASS_LINK = "MASS_LINK"
    NETWORK = "NETWORK"


MASS_LINKS_COLUMNS = (
    "run_id",
    "origin",
    "mlno",
    "svol",
    "svolno",
    "sgrpn",
    "smemn",
    "smemsb1",
    "smemsb2",
    "mfactr",
    "tran",
    "tvol",
    "tvolno",
    "tgrpn",
    "tmemn",
    "tmemsb1",
    "tmemsb2",
    "attributes",
)


@dataclass(frozen=True)
class MassLinkRecord:
    """One source-member to target-member transfer declaration.

    ``origin='mass_link'`` rows are entity-agnostic templates read from numbered
    MASS-LINK tables. ``origin='network'`` rows are concrete inline transfers
    read from NETWORK rows after target ranges have been expanded.
    """

    run_id: str
    origin: MassLinkOrigin
    svol: OperationType | str
    sgrpn: str
    smemn: str
    tvol: OperationType | str
    tgrpn: str
    tmemn: str
    mfactr: float = 1.0
    mlno: int | None = None
    edge_id: int | None = None
    svolno: int | None = None
    smemsb1: str | int | None = None
    smemsb2: str | int | None = None
    tran: TransformFunction | str | None = None
    tvolno: int | None = None
    tmemsb1: str | int | None = None
    tmemsb2: str | int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_run_id(self.run_id)
        origin = _coerce_choice("origin", self.origin, MassLinkOrigin)
        svol = _coerce_operation_type(self.svol)
        tvol = _coerce_operation_type(self.tvol)

        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "svol", svol)
        object.__setattr__(self, "svolno", _optional_int(self.svolno))
        object.__setattr__(self, "sgrpn", _required_text(self.sgrpn, "sgrpn"))
        object.__setattr__(self, "smemn", _required_text(self.smemn, "smemn"))
        object.__setattr__(self, "smemsb1", _optional_text(self.smemsb1))
        object.__setattr__(self, "smemsb2", _optional_text(self.smemsb2))
        object.__setattr__(self, "mfactr", float(self.mfactr))
        object.__setattr__(self, "tran", _coerce_transform(self.tran))
        object.__setattr__(self, "tvol", tvol)
        object.__setattr__(self, "tvolno", _optional_int(self.tvolno))
        object.__setattr__(self, "tgrpn", _required_text(self.tgrpn, "tgrpn"))
        object.__setattr__(self, "tmemn", _required_text(self.tmemn, "tmemn"))
        object.__setattr__(self, "tmemsb1", _optional_text(self.tmemsb1))
        object.__setattr__(self, "tmemsb2", _optional_text(self.tmemsb2))
        object.__setattr__(self, "mlno", _optional_int(self.mlno))
        object.__setattr__(self, "edge_id", _optional_int(self.edge_id))

        if origin == MassLinkOrigin.MASS_LINK:
            if self.mlno is None:
                raise ConventionError("MASS-LINK template rows require mlno")
            if (
                self.edge_id is not None
                or self.svolno is not None
                or self.tvolno is not None
            ):
                raise ConventionError(
                    "MASS-LINK template rows must not store edge_id, svolno, or tvolno"
                )
            if self.tran is not None:
                raise ConventionError("MASS-LINK template rows must not store tran")
        if origin == MassLinkOrigin.NETWORK:
#            if self.edge_id is None:
#                raise ConventionError("NETWORK-origin transfer rows require edge_id")
            if self.mlno is not None:
                raise ConventionError("NETWORK-origin transfer rows must not store mlno")
            if self.svolno is None or self.tvolno is None:
                raise ConventionError(
                    "NETWORK-origin transfer rows require concrete svolno and tvolno"
                )

    def as_dict(self) -> dict[str, Any]:
        """Return a Parquet-friendly dictionary representation."""

        return {
            "run_id": self.run_id,
            "origin": self.origin,
            "mlno": self.mlno,
            "svol": self.svol.value,
            "svolno": self.svolno,
            "sgrpn": self.sgrpn,
            "smemn": self.smemn,
            "smemsb1": self.smemsb1,
            "smemsb2": self.smemsb2,
            "mfactr": self.mfactr,
            "tran": _enum_value(self.tran),
            "tvol": self.tvol.value,
            "tvolno": self.tvolno,
            "tgrpn": self.tgrpn,
            "tmemn": self.tmemn,
            "tmemsb1": self.tmemsb1,
            "tmemsb2": self.tmemsb2,
            "attributes": json.dumps(self.attributes, sort_keys=True),
        }


def mass_links_from_uci(
    uci: UCI,
    run_id: str,
    edges: tuple[EdgeRecord, ...],
) -> tuple[MassLinkRecord, ...]:
    """Compile MASS-LINK templates and NETWORK inline transfers."""

    mass_links = _masslinks(uci)
    #TODO add uci shared lexicon
    records = []
    for index, row in mass_links.iterrows():
        # Process each row to create edge records
        source_type = _coerce_operation_type(row['SVOL'])
        target_type = _coerce_operation_type(row['TVOL'])
        edges.append(MassLinkRecord(
                    run_id = run_id,
                    origin = MassLinkOrigin.MASS_LINK,
                    mlno=_optional_int(row['MLNO']),
                    source_type= source_type,
                    source_group=_optional_text(row['SGRPN']),
                    target_type= target_type,
                    target_group=_optional_text(row['TGRPN']),
                    mfactor=_optional_float(row['MFACTOR']),
                    smemn=_optional_text(row['SMEMN']),
                    smemsb1=_optional_text(row['SMEMSB1']),
                    smemsb2=_optional_text(row['SMEMSB2']),
                    tmemn=_optional_text(row['TMEMN']),
                    tmemsb1=_optional_text(row['TMEMSB1']),
                    tmemsb2=_optional_text(row['TMEMSB2']),
                    target_run_id=None,
                    attributes=row.get("attributes", {})))

    if 'NETWORK' in uci.block_names():
        for index, row in _network(uci).iterrows():
            # Process each row to create edge records
            source_type = _coerce_operation_type(row['SVOL'])
            target_type = _coerce_operation_type(row['TVOL'])
            edges.append(EdgeRecord(run_id=run_id,
                        edge_id=None,  # Replace with actual edge ID if available
                        source_type= source_type,
                        target_type= target_type,
                        edge_kind= "NETWORK",
                        afactr= None,
                        mlno= None,
                        tmemsb1=_optional_text(row['TMEMSB1']),
                        tmemsb2=_optional_text(row['TMEMSB2']),
                        target_run_id=None,
                        attributes=row.get("attributes", {})))

    return tuple(edges)
    raise NotImplementedError("MASS-LINK catalog compilation is not yet implemented")


def _network(uci: UCI) -> pd.DataFrame:
    df_network = uci.table('NETWORK').rename(columns = {'TOPFST':'TVOLNO'})
    df = df_network.loc[(df_network['SVOL'] == 'GENER') & (df_network['TRAN'] == 'SAME')]
    # Switch the Source and Target information when TRAN is SAME and the SVOL is a GENER as it appears in some cases 
    # You can define the gener input timeseries backwards
    df2 = df.copy()
    df.loc[:,['SVOL','SVOLNO','SGRPN','SMEMN','SMEMSB1','SMEMSB2']] = df.loc[:,['TVOL','TVOLNO','TGRPN','TMEMN','TMEMSB1','TMEMSB2']]
    df.loc[:,['TVOL','TVOLNO','TGRPN','TMEMN','TMEMSB1','TMEMSB2']] = df2.loc[:,['SVOL','SVOLNO','SGRPN','SMEMN','SMEMSB1','SMEMSB2']]
    df_network = df_network.loc[df_network['TVOL'] == 'GENER']
    df_network = pd.concat([df_network,df])
    return df_network

def effective_transfers(
    edges: tuple[EdgeRecord, ...],
    mass_links: tuple[MassLinkRecord, ...],
) -> tuple[dict[str, Any], ...]:
    """Derive effective source-to-target member transfers from stored declarations."""

    raise NotImplementedError("Effective transfer derivation is not yet implemented")


def _coerce_operation_type(value: OperationType | str) -> OperationType:
    if isinstance(value, OperationType):
        return value
    return OperationType(str(value).upper())


def _coerce_transform(value: TransformFunction | str | None) -> TransformFunction | None:
    if value is None:
        return None
    if isinstance(value, TransformFunction):
        return value
    text = _optional_text(value)
    if text is None:
        return None
    return TransformFunction(text.upper())


def _coerce_choice(label: str, value: str, choices: frozenset[str]) -> str:
    text = str(value).strip().lower()
    if text not in choices:
        raise ConventionError(f"Invalid {label}: {value!r}")
    return text

