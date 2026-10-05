"""Denormalized routing-transfer catalog records for the HSPF lake.

This module materializes the useful join between SCHEMATIC rows and MASS-LINK
templates, then appends normalized NETWORK rows into the same shape.  The grain
is one concrete source-member to target-member transfer along one concrete
operation-to-operation connection.

The table intentionally avoids globally maintained ``edge_id`` or ``line_id``
surrogate identifiers.  Row identity is deterministic: ``transfer_key`` is a
content hash of the natural row fields plus ``source_order``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from hspf.core.conventions import validate_run_id
from hspf.core.errors import ConventionError
from hspf.core.types import OperationType, TransformFunction
from hspf.lake.catalogs.io import (
    _enum_value,
    _is_missing,
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
from hspf.core.types import EdgeRole, RoutingSource

ROUTING_TRANSFERS_CATALOG_NAME = "routing_transfers"
SCHEMA_VERSION = "lake-routing-transfers-catalog-v0"
TRANSFER_KEY_PREFIX = "rt_"



ROUTING_TRANSFERS_COLUMNS = (
    "run_id",
    "transfer_key",
    "routing_source",
    "edge_role",
    "source_type",
    "source_id",
    "source_group",
    "source_member",
    "source_subscript_1",
    "source_subscript_2",
    "target_type",
    "target_id",
    "target_group",
    "target_member",
    "target_subscript_1",
    "target_subscript_2",
    "mlno",
    "tran",
    "afactr",
    "mfactr",
    "effective_factor",
    "connection_order",
    "source_order",
    "unmatched_schematic",
    "attributes",
)

CONNECTION_COLUMNS = (
    "run_id",
    "routing_source",
    "edge_role",
    "source_type",
    "source_id",
    "target_type",
    "target_id",
    "connection_order",
    "mlno",
    "afactr",
    "target_subscript_1",
    "target_subscript_2",
    "unmatched_schematic",
)


@dataclass(frozen=True)
class RoutingTransferRecord:
    """One denormalized routing-transfer row.

    ``routing_source='SCHEMATIC_MASS_LINK'`` rows are compiled by joining one
    SCHEMATIC connection to the matching rows in its MASS-LINK table.
    ``routing_source='NETWORK'`` rows are concrete NETWORK member transfers.
    """

    run_id: str
    routing_source: RoutingSource | str
    source_type: OperationType | str
    source_id: int
    target_type: OperationType | str
    target_id: int
    source_order: int
    connection_order: int | None = None
    edge_role: EdgeRole | str | None = None
    source_group: str | None = None
    source_member: str | None = None
    source_subscript_1: str | int | None = None
    source_subscript_2: str | int | None = None
    target_group: str | None = None
    target_member: str | None = None
    target_subscript_1: str | int | None = None
    target_subscript_2: str | int | None = None
    mlno: int | None = None
    tran: TransformFunction | str | None = None
    afactr: float | None = None
    mfactr: float | None = None
    effective_factor: float | None = None
    unmatched_schematic: bool = False
    transfer_key: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_run_id(self.run_id)

        routing_source = _coerce_routing_source(self.routing_source)
        source_type = _coerce_operation_type(self.source_type)
        target_type = _coerce_operation_type(self.target_type)
        edge_role = (
            infer_edge_role(source_type, target_type)
            if self.edge_role is None
            else _coerce_edge_role(self.edge_role)
        )
        afactr = _optional_float(self.afactr)
        mfactr = _optional_float(self.mfactr)
        effective_factor = _optional_float(self.effective_factor)
        if effective_factor is None:
            effective_factor = _effective_factor(routing_source, afactr, mfactr)

        object.__setattr__(self, "routing_source", routing_source)
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "source_id", _positive_int(self.source_id, "source_id"))
        object.__setattr__(self, "target_type", target_type)
        object.__setattr__(self, "target_id", _positive_int(self.target_id, "target_id"))
        object.__setattr__(
            self,
            "source_order",
            _positive_int(self.source_order, "source_order"),
        )
        object.__setattr__(
            self,
            "connection_order",
            _positive_int(
                self.connection_order or self.source_order,
                "connection_order",
            ),
        )
        object.__setattr__(self, "edge_role", edge_role)
        object.__setattr__(self, "source_group", _optional_text(self.source_group))
        object.__setattr__(self, "source_member", _optional_text(self.source_member))
        object.__setattr__(
            self,
            "source_subscript_1",
            _optional_text(self.source_subscript_1),
        )
        object.__setattr__(
            self,
            "source_subscript_2",
            _optional_text(self.source_subscript_2),
        )
        object.__setattr__(self, "target_group", _optional_text(self.target_group))
        object.__setattr__(self, "target_member", _optional_text(self.target_member))
        object.__setattr__(
            self,
            "target_subscript_1",
            _optional_text(self.target_subscript_1),
        )
        object.__setattr__(
            self,
            "target_subscript_2",
            _optional_text(self.target_subscript_2),
        )
        object.__setattr__(self, "mlno", _optional_int(self.mlno))
        object.__setattr__(self, "tran", _coerce_transform_text(self.tran))
        object.__setattr__(self, "afactr", afactr)
        object.__setattr__(self, "mfactr", mfactr)
        object.__setattr__(self, "effective_factor", effective_factor)
        object.__setattr__(self, "unmatched_schematic", bool(self.unmatched_schematic))
        object.__setattr__(self, "attributes", _attributes_dict(self.attributes))

        transfer_key = _optional_text(self.transfer_key) or _make_transfer_key(self)
        object.__setattr__(self, "transfer_key", transfer_key)

    def as_dict(self) -> dict[str, Any]:
        """Return a Parquet-friendly dictionary representation."""

        return {
            "run_id": self.run_id,
            "transfer_key": self.transfer_key,
            "routing_source": _enum_value(self.routing_source),
            "edge_role": _enum_value(self.edge_role),
            "source_type": _enum_value(self.source_type),
            "source_id": self.source_id,
            "source_group": self.source_group,
            "source_member": self.source_member,
            "source_subscript_1": self.source_subscript_1,
            "source_subscript_2": self.source_subscript_2,
            "target_type": _enum_value(self.target_type),
            "target_id": self.target_id,
            "target_group": self.target_group,
            "target_member": self.target_member,
            "target_subscript_1": self.target_subscript_1,
            "target_subscript_2": self.target_subscript_2,
            "mlno": self.mlno,
            "tran": self.tran,
            "afactr": self.afactr,
            "mfactr": self.mfactr,
            "effective_factor": self.effective_factor,
            "connection_order": self.connection_order,
            "source_order": self.source_order,
            "unmatched_schematic": self.unmatched_schematic,
            "attributes": json.dumps(self.attributes, sort_keys=True),
        }


def routing_transfers_from_uci(
    uci: UCI,
    run_id: str,
) -> tuple[RoutingTransferRecord, ...]:
    """Compile SCHEMATIC/MASS-LINK and NETWORK rows into routing transfers."""

    validate_run_id(run_id)
    records: list[RoutingTransferRecord] = []
    source_order = 0

    schematic_transfers = _schematic_mass_link_frame(uci)
    for joined_row in schematic_transfers.to_dict("records"):
        source_order += 1
        if bool(joined_row["unmatched_schematic"]):
            records.append(
                _unmatched_schematic_record(
                    run_id,
                    joined_row,
                    source_order,
                )
            )
            continue
        records.append(
            _schematic_mass_link_record(
                run_id,
                joined_row,
                source_order,
            )
        )

    network_transfers = _network_transfers_frame(uci)
    for network_row in network_transfers.to_dict("records"):
        source_order += 1
        records.append(
            _network_record(
                run_id,
                network_row,
                source_order,
            )
        )

    return tuple(records)


def routing_transfers_to_frame(
    records: Iterable[RoutingTransferRecord],
) -> pd.DataFrame:
    """Convert routing-transfer records to the catalog DataFrame shape."""

    return records_to_frame(records, ROUTING_TRANSFERS_COLUMNS)


def read_routing_transfers_catalog(layout: LakeLayout) -> pd.DataFrame:
    """Read ``catalog/routing_transfers.parquet``."""

    return read_catalog_table(
        layout,
        ROUTING_TRANSFERS_CATALOG_NAME,
        ROUTING_TRANSFERS_COLUMNS,
    )


def write_routing_transfers_catalog(
    layout: LakeLayout,
    records: Iterable[RoutingTransferRecord] | pd.DataFrame,
    *,
    overwrite: bool = True,
) -> Path:
    """Write ``catalog/routing_transfers.parquet``."""

    return write_catalog_table(
        layout,
        ROUTING_TRANSFERS_CATALOG_NAME,
        records,
        ROUTING_TRANSFERS_COLUMNS,
        overwrite=overwrite,
        label="Routing transfer",
    )


def connections_from_transfers(
    transfers: Iterable[RoutingTransferRecord] | pd.DataFrame,
) -> pd.DataFrame:
    """Return the distinct connection-grain view used for area calculations."""

    frame = (
        coerce_catalog_frame(transfers, ROUTING_TRANSFERS_COLUMNS)
        if isinstance(transfers, pd.DataFrame)
        else routing_transfers_to_frame(transfers)
    )
    if frame.empty:
        return pd.DataFrame(columns=CONNECTION_COLUMNS)
    return frame.loc[:, CONNECTION_COLUMNS].drop_duplicates().reset_index(drop=True)


def infer_edge_role(
    source_type: OperationType | str,
    target_type: OperationType | str,
) -> EdgeRole:
    """Infer the high-level routing role for an operation connection."""

    source_type = _operation_text(source_type)
    target_type = _operation_text(target_type)
    land_types = {"PERLND", "IMPLND"}

    if source_type in land_types and target_type == "RCHRES":
        return EdgeRole.LAND_TO_REACH
    if source_type in land_types and target_type in land_types:
        return EdgeRole.LAND_TO_LAND
    if source_type == "RCHRES" and target_type == "RCHRES":
        return EdgeRole.REACH_TO_REACH
    return EdgeRole.UTILITY


def _schematic_mass_link_record(
    run_id: str,
    joined_row: dict[str, Any],
    source_order: int,
) -> RoutingTransferRecord:
    source_type = _coerce_operation_type(joined_row["schematic_svol"])
    target_type = _coerce_operation_type(joined_row["schematic_tvol"])
    afactr = _optional_float(joined_row.get("schematic_afactr"))
    mfactr = _factor_float(joined_row.get("mass_link_mfactor"))
    connection_order = _positive_int(
        joined_row["connection_order"],
        "connection_order",
    )

    return RoutingTransferRecord(
        run_id=run_id,
        routing_source=RoutingSource.SCHEMATIC_MASS_LINK,
        edge_role=infer_edge_role(source_type, target_type),
        source_type=source_type,
        source_id=_positive_int(joined_row["schematic_svolno"], "SVOLNO"),
        source_group=_optional_text(joined_row.get("mass_link_sgrpn")),
        source_member=_optional_text(joined_row.get("mass_link_smemn")),
        source_subscript_1=_optional_text(joined_row.get("mass_link_smemsb1")),
        source_subscript_2=_optional_text(joined_row.get("mass_link_smemsb2")),
        target_type=target_type,
        target_id=_positive_int(joined_row["schematic_tvolno"], "TVOLNO"),
        target_group=_optional_text(joined_row.get("mass_link_tgrpn")),
        target_member=_optional_text(joined_row.get("mass_link_tmemn")),
        target_subscript_1=_joined_target_subscript(joined_row, 1),
        target_subscript_2=_joined_target_subscript(joined_row, 2),
        mlno=_optional_int(joined_row.get("schematic_mlno")),
        afactr=afactr,
        mfactr=mfactr,
        effective_factor=_multiply_factors(afactr, mfactr),
        connection_order=connection_order,
        source_order=source_order,
        attributes={
            "source_table": "SCHEMATIC+MASS-LINK",
            "schematic_order": connection_order,
            "mass_link_table": _optional_text(joined_row.get("mass_link_table")),
            "mass_link_order": _optional_int(joined_row.get("mass_link_order")),
        },
    )


def _unmatched_schematic_record(
    run_id: str,
    joined_row: dict[str, Any],
    source_order: int,
) -> RoutingTransferRecord:
    source_type = _coerce_operation_type(joined_row["schematic_svol"])
    target_type = _coerce_operation_type(joined_row["schematic_tvol"])
    connection_order = _positive_int(
        joined_row["connection_order"],
        "connection_order",
    )

    return RoutingTransferRecord(
        run_id=run_id,
        routing_source=RoutingSource.SCHEMATIC_MASS_LINK,
        edge_role=infer_edge_role(source_type, target_type),
        source_type=source_type,
        source_id=_positive_int(joined_row["schematic_svolno"], "SVOLNO"),
        target_type=target_type,
        target_id=_positive_int(joined_row["schematic_tvolno"], "TVOLNO"),
        target_subscript_1=_optional_text(joined_row.get("schematic_tmemsb1")),
        target_subscript_2=_optional_text(joined_row.get("schematic_tmemsb2")),
        mlno=_optional_int(joined_row.get("schematic_mlno")),
        afactr=_optional_float(joined_row.get("schematic_afactr")),
        connection_order=connection_order,
        source_order=source_order,
        unmatched_schematic=True,
        attributes={
            "source_table": "SCHEMATIC",
            "schematic_order": connection_order,
            "unmatched_reason": "no matching MASS-LINK row for MLNO/SVOL/TVOL",
        },
    )


def _network_record(
    run_id: str,
    network_row: dict[str, Any],
    source_order: int,
) -> RoutingTransferRecord:
    source_type = _coerce_operation_type(network_row["SVOL"])
    target_type = _coerce_operation_type(network_row["TVOL"])
    mfactr = _factor_float(network_row.get("MFACTOR"))
    network_order = _positive_int(network_row["network_order"], "network_order")

    return RoutingTransferRecord(
        run_id=run_id,
        routing_source=RoutingSource.NETWORK,
        edge_role=infer_edge_role(source_type, target_type),
        source_type=source_type,
        source_id=_positive_int(network_row["SVOLNO"], "SVOLNO"),
        source_group=_optional_text(network_row.get("SGRPN")),
        source_member=_optional_text(network_row.get("SMEMN")),
        source_subscript_1=_optional_text(network_row.get("SMEMSB1")),
        source_subscript_2=_optional_text(network_row.get("SMEMSB2")),
        target_type=target_type,
        target_id=_positive_int(network_row["target_id"], "target_id"),
        target_group=_optional_text(network_row.get("TGRPN")),
        target_member=_optional_text(network_row.get("TMEMN")),
        target_subscript_1=_optional_text(network_row.get("TMEMSB1")),
        target_subscript_2=_optional_text(network_row.get("TMEMSB2")),
        tran=_coerce_transform_text(network_row.get("TRAN")),
        mfactr=mfactr,
        effective_factor=mfactr,
        connection_order=network_order,
        source_order=source_order,
        attributes={
            "source_table": "NETWORK",
            "network_order": network_order,
            "topfst": _optional_int(network_row.get("TOPFST")),
            "toplst": _optional_int(network_row.get("TOPLST")),
        },
    )


def _schematic_mass_link_frame(uci: UCI) -> pd.DataFrame:
    """Return a materialized SCHEMATIC left join to MASS-LINK rows."""

    if "SCHEMATIC" not in uci.block_names():
        return pd.DataFrame()

    schematic = uci.table("SCHEMATIC").copy()
    if schematic.empty:
        return pd.DataFrame()

    schematic["connection_order"] = range(1, len(schematic) + 1)
    schematic["join_mlno"] = schematic["MLNO"].map(_optional_int)
    schematic["join_svol"] = schematic["SVOL"].map(_join_text)
    schematic["join_tvol"] = schematic["TVOL"].map(_join_text)
    schematic = schematic.rename(
        columns={
            "SVOL": "schematic_svol",
            "SVOLNO": "schematic_svolno",
            "AFACTR": "schematic_afactr",
            "TVOL": "schematic_tvol",
            "TVOLNO": "schematic_tvolno",
            "MLNO": "schematic_mlno",
            "TMEMSB1": "schematic_tmemsb1",
            "TMEMSB2": "schematic_tmemsb2",
        }
    )

    mass_links = _mass_links_frame(uci)
    mass_links["join_mlno"] = mass_links["MLNO"].map(_optional_int)
    mass_links["join_svol"] = mass_links["SVOL"].map(_join_text)
    mass_links["join_tvol"] = mass_links["TVOL"].map(_join_text)
    mass_links = mass_links.rename(
        columns={
            "MLNO": "mass_link_mlno",
            "SVOL": "mass_link_svol",
            "SGRPN": "mass_link_sgrpn",
            "SMEMN": "mass_link_smemn",
            "SMEMSB1": "mass_link_smemsb1",
            "SMEMSB2": "mass_link_smemsb2",
            "MFACTOR": "mass_link_mfactor",
            "TVOL": "mass_link_tvol",
            "TGRPN": "mass_link_tgrpn",
            "TMEMN": "mass_link_tmemn",
            "TMEMSB1": "mass_link_tmemsb1",
            "TMEMSB2": "mass_link_tmemsb2",
        }
    )

    joined = schematic.merge(
        mass_links,
        how="left",
        on=["join_mlno", "join_svol", "join_tvol"],
        sort=False,
    )
    joined["unmatched_schematic"] = joined["mass_link_order"].isna()
    return joined


def _network_transfers_frame(uci: UCI) -> pd.DataFrame:
    """Return NETWORK rows normalized to one concrete target id per row."""

    if "NETWORK" not in uci.block_names():
        return pd.DataFrame()

    network = uci.table("NETWORK").copy()
    if network.empty:
        return pd.DataFrame()

    network["network_order"] = range(1, len(network) + 1)
    network["target_id"] = network.apply(
        lambda row: _network_target_ids(row.to_dict()),
        axis=1,
    )
    return network.explode("target_id").reset_index(drop=True)


def _mass_links_frame(uci: UCI) -> pd.DataFrame:
    columns = (
        "MLNO",
        "SVOL",
        "SGRPN",
        "SMEMN",
        "SMEMSB1",
        "SMEMSB2",
        "MFACTOR",
        "TVOL",
        "TGRPN",
        "TMEMN",
        "TMEMSB1",
        "TMEMSB2",
        "mass_link_table",
        "mass_link_order",
    )
    if "MASS-LINK" not in uci.block_names():
        return pd.DataFrame(columns=columns)

    frames: list[pd.DataFrame] = []
    for table_name in _sorted_mass_link_table_names(uci):
        mass_link = uci.table("MASS-LINK", table_name).copy()
        if mass_link.empty:
            continue
        mass_link["MLNO"] = _mass_link_number(table_name)
        mass_link["mass_link_table"] = table_name
        mass_link["mass_link_order"] = range(1, len(mass_link) + 1)
        frames.append(mass_link)

    if not frames:
        return pd.DataFrame(columns=columns)
    frame = pd.concat(frames, ignore_index=True)
    return _coerce_mass_links_frame(frame, columns)


def _network_target_ids(network_row: dict[str, Any]) -> tuple[int, ...]:
    start = _optional_int(network_row.get("TOPFST"))
    end = _optional_int(network_row.get("TOPLST"))
    if start is None:
        raise ConventionError(f"NETWORK row is missing TOPFST: {network_row!r}")
    if end is None:
        return (start,)
    if end < start:
        raise ConventionError(f"NETWORK TOPLST is less than TOPFST: {network_row!r}")
    return tuple(range(start, end + 1))


def _joined_target_subscript(
    joined_row: dict[str, Any],
    subscript_number: int,
) -> str | None:
    return _optional_text(
        joined_row.get(f"schematic_tmemsb{subscript_number}")
    ) or _optional_text(
        joined_row.get(f"mass_link_tmemsb{subscript_number}")
    )


def _coerce_routing_transfers_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return coerce_catalog_frame(frame, ROUTING_TRANSFERS_COLUMNS)


def _coerce_mass_links_frame(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    return coerce_catalog_frame(frame, columns, keep_extra_columns=False)


def _sorted_mass_link_table_names(uci: UCI) -> list[str]:
    return sorted(uci.table_names("MASS-LINK"), key=_mass_link_number)


def _mass_link_number(table_name: str) -> int:
    text = str(table_name).upper().replace(" ", "")
    prefix = "MASS-LINK"
    if not text.startswith(prefix):
        raise ConventionError(f"Invalid MASS-LINK table name: {table_name!r}")
    return _positive_int(text[len(prefix) :], "MLNO")


def _coerce_operation_type(value: OperationType | str) -> OperationType | str:
    if isinstance(value, OperationType):
        return value
    text = _operation_text(value)
    try:
        return OperationType(text)
    except ValueError:
        return text


def _coerce_routing_source(value: RoutingSource | str) -> RoutingSource | str:
    if isinstance(value, RoutingSource):
        return value
    text = str(value).strip().upper()
    if text == "SCHEMATIC":
        text = RoutingSource.SCHEMATIC_MASS_LINK.value
    try:
        return RoutingSource(text)
    except ValueError:
        return text


def _coerce_edge_role(value: EdgeRole | str) -> EdgeRole | str:
    if isinstance(value, EdgeRole):
        return value
    text = str(value).strip().upper()
    try:
        return EdgeRole(text)
    except ValueError:
        return text


def _coerce_transform_text(value: TransformFunction | str | None) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    if isinstance(value, TransformFunction):
        return value.value
    return text.upper()


def _operation_text(value: OperationType | str) -> str:
    return str(_enum_value(value)).strip().upper()


def _factor_float(value: Any) -> float:
    factor = _optional_float(value)
    return 1.0 if factor is None else factor


def _join_text(value: Any) -> str | None:
    text = _optional_text(value)
    return None if text is None else text.upper()


def _attributes_dict(value: dict[str, Any] | None) -> dict[str, Any]:
    return {} if value is None else dict(value)


def _effective_factor(
    routing_source: RoutingSource | str,
    afactr: float | None,
    mfactr: float | None,
) -> float | None:
    if _enum_value(routing_source) == RoutingSource.NETWORK.value:
        return mfactr
    return _multiply_factors(afactr, mfactr)


def _multiply_factors(
    afactr: float | None,
    mfactr: float | None,
) -> float | None:
    if afactr is None or mfactr is None:
        return None
    return afactr * mfactr


def _make_transfer_key(record: RoutingTransferRecord) -> str:
    values = (
        record.run_id,
        _enum_value(record.routing_source),
        _enum_value(record.edge_role),
        _enum_value(record.source_type),
        record.source_id,
        record.source_group,
        record.source_member,
        record.source_subscript_1,
        record.source_subscript_2,
        _enum_value(record.target_type),
        record.target_id,
        record.target_group,
        record.target_member,
        record.target_subscript_1,
        record.target_subscript_2,
        record.mlno,
        record.tran,
        record.afactr,
        record.mfactr,
        record.effective_factor,
        record.connection_order,
        record.source_order,
        record.unmatched_schematic,
    )
    payload = json.dumps([_key_value(value) for value in values], separators=(",", ":"))
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"{TRANSFER_KEY_PREFIX}{digest}"


def _key_value(value: Any) -> Any:
    if _is_missing(value):
        return None
    return _enum_value(value)

