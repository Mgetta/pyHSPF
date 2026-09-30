"""Ingest HSPF binary output into the raw lake tier.

This module is intentionally a translation layer over the model components:
callers provide a :class:`hspf.model.hbn.hbnInterface` or explicit HBN paths,
and ingest writes wide-per-block Parquet files using :class:`LakeLayout`.
It does not use the session-level ``hspfModel`` facade because ingest should
not auto-run models or construct report/output accessors as side effects.

In production, callers should pass a staging-rooted layout created by
``hspf.lake.publish.staging_layout``; direct-to-raw writes are intended for
local development only until the full publish protocol lands.

Pipeline shape:
    source UCI/HBN files
        -> read HBN blocks
        -> infer observed HBN time geometry
        -> keep base-resolution variables
        -> normalize timestamps/identity columns
        -> write Parquet parts
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from hspf.core.conventions import (
    shift_to_period_start,
    timestep_label,
    validate_run_id,
)
from hspf.core.errors import ConventionError
from hspf.core.types import Block, OutputLevel
from hspf.lake.layout import LakeLayout
from hspf.model.hbn import hbnInterface
from hspf.model.uci import UCI


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IDENTITY_COLUMNS = frozenset({"OPNID", "datetime", "entity_id", "timestamp"})


# ---------------------------------------------------------------------------
# Public records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IngestOptions:
    """Runtime knobs for raw-tier ingest.

    ``interval_minutes`` and ``pyrend`` are fallbacks used only when a block is
    too short for observed HBN timestamps to determine those values.
    """

    interval_minutes: int | None = None
    pyrend: int | None = None
    partition_level2_by_year: bool = False
    parquet_compression: str = "zstd"
    row_group_size: int | None = 1_000_000
    overwrite: bool = False


@dataclass(frozen=True)
class IngestSources:
    """Explicit UCI/HBN pair used by lake ingest.

    This intentionally duplicates only the tiny part of ``hspfModel`` ingest
    needs until the model session class is refactored to be side-effect safe.
    """

    uci: UCI
    hbns: hbnInterface


@dataclass(frozen=True)
class RawBlockFrame:
    """In-memory representation of one HBN block between ingest stages."""

    block: Block
    output_level: OutputLevel
    frame: pd.DataFrame
    interval_minutes: int | None = None
    pyrend: int = 12


@dataclass(frozen=True)
class RawBlockArtifact:
    """Manifest-like metadata for one raw Parquet file written by ingest."""

    path: Path
    block: Block
    output_level: OutputLevel
    timestep: str
    rows: int
    columns: tuple[str, ...]
    interval_minutes: int | None = None
    pyrend: int = 12
    year: int | None = None


@dataclass(frozen=True)
class IngestResult:
    """Summary returned after ingesting one run."""

    run_id: str
    artifacts: tuple[RawBlockArtifact, ...]


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def sources_from_uci(
    uci_path: str | Path,
    *,
    hbn_paths: Iterable[str | Path] | None = None,
) -> IngestSources:
    """Build ingest sources from a UCI path and optional explicit HBN paths."""

    uci = UCI(uci_path)
    resolved_hbn_paths = list(hbn_paths) if hbn_paths is not None else uci.hbn_paths
    if not resolved_hbn_paths:
        raise ConventionError(f"No HBN files found for {uci_path!r}")
    return IngestSources(uci=uci, hbns=hbnInterface(resolved_hbn_paths))


def ingest_block_frames(
    run_id: str,
    block_frames: Iterable[RawBlockFrame],
    layout: LakeLayout
) -> IngestResult:
    """Core ingest worker; callers must validate ``run_id`` before entry."""

    artifacts: list[RawBlockArtifact] = []
    for block_frame in block_frames:
        prepared = prepare_raw_frame(
            block_frame,
            run_id,
        )
        artifacts.extend(
            write_raw_frame(
                prepared,
                layout,
                run_id,
            )
        )

    return IngestResult(
        run_id=run_id,
        artifacts=tuple(artifacts)
    )


# ---------------------------------------------------------------------------
# HBN reading and observed time-geometry enrichment
# ---------------------------------------------------------------------------
def read_blocks(hbns: hbnInterface) -> list[RawBlockFrame]:
    """Read every block advertised by an HBN interface."""
    frames: list[RawBlockFrame] = []
    for operation, activity, tcode in hbns.iter_blocks():
        block = Block.from_strings(operation, activity, tcode)
        output_level = OutputLevel(int(tcode))
        frame = hbns.get_block(operation, activity, tcode)
        #TODO: Infer interval_minutes from HBN metadata when available
        interval_minutes = None
        if output_level is OutputLevel.HOURLY:
            interval_minutes = 60 #Assumes 2 is hourly and pivl is 1
        pyrend = None
        if output_level is OutputLevel.YEARLY:
            pyrend = 12

        if not frame.empty:
            frames.append(
                RawBlockFrame(
                    block=block,
                    output_level=output_level,
                    frame=frame,
                    interval_minutes = interval_minutes,
                    pyrend = pyrend,
                )
            )
    return frames


# ---------------------------------------------------------------------------
# Raw-frame normalization and Parquet writes
# ---------------------------------------------------------------------------

def prepare_raw_frame(
    block_frame: RawBlockFrame,
    run_id: str,
) -> RawBlockFrame:
    """Normalize identifiers and timestamps before writing a raw block."""

    output_level = block_frame.output_level
    interval = (
        block_frame.interval_minutes
        if output_level is OutputLevel.HOURLY
        else None
    )
    frame = block_frame.frame.copy()
    frame = frame.rename(columns={"datetime": "timestamp",
                                  "OPNID": "entity_id"})
    frame.insert(0, "run_id", run_id)
    frame.insert(2, "timestep", timestep_label(output_level, interval))
    frame.insert(3, "entity_type", block_frame.block.entity_type.value)
    frame.insert(4, "activity", block_frame.block.activity.value)
    frame.insert(5, "output_level", int(output_level))

    # Partition columns are also materialized in the file so a copied Parquet
    # part remains self-describing outside the Hive-style folder tree.
    partition_columns = [
        "run_id",
        "entity_id",
        "timestep",
        "entity_type",
        "activity",
        "output_level",
        "timestamp",
    ]
    variable_columns = [
        column for column in frame.columns if column not in partition_columns
    ]
    frame = frame.loc[:, [*partition_columns, *variable_columns]]
    frame = frame.sort_values(["entity_id", "timestamp"]).reset_index(drop=True)

    return RawBlockFrame(
        block=block_frame.block,
        output_level=output_level,
        frame=frame,
        interval_minutes=interval,
        pyrend=block_frame.pyrend,
    )


def write_raw_frame(
    block_frame: RawBlockFrame,
    layout: LakeLayout,
    run_id: str,
    *,
    options: IngestOptions | None = None,
) -> list[RawBlockArtifact]:
    """Write one prepared raw block frame to Parquet."""

    options = options or IngestOptions()
    if (
        block_frame.output_level is OutputLevel.HOURLY
        and options.partition_level2_by_year
    ):
        artifacts: list[RawBlockArtifact] = []
        for year, frame in block_frame.frame.groupby(
            block_frame.frame["timestamp"].dt.year,
            sort=True,
        ):
            artifacts.append(
                _write_part(
                    frame,
                    layout,
                    run_id,
                    block_frame.block,
                    block_frame.output_level,
                    year=int(year),
                    options=options,
                    interval_minutes=block_frame.interval_minutes,
                    pyrend=block_frame.pyrend,
                )
            )
        return artifacts

    return [
        _write_part(
            block_frame.frame,
            layout,
            run_id,
            block_frame.block,
            block_frame.output_level,
            year=None,
            options=options,
            interval_minutes=block_frame.interval_minutes,
            pyrend=block_frame.pyrend,
        )
    ]


def _write_part(
    frame: pd.DataFrame,
    layout: LakeLayout,
    run_id: str,
    block: Block,
    output_level: OutputLevel,
    *,
    interval_minutes: int | None,
    pyrend: int,
    year: int | None,
    options: IngestOptions,
) -> RawBlockArtifact:
    """Write one physical Parquet part and return its artifact metadata."""

    path = layout.raw_part_path(
        run_id,
        block.name,
        output_level,
        interval_minutes=interval_minutes,
        year=year,
    )
    if path.exists() and not options.overwrite:
        raise ConventionError(f"Raw lake file already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    parquet_kwargs = {}
    if options.row_group_size is not None:
        parquet_kwargs["row_group_size"] = options.row_group_size
    frame.to_parquet(
        path,
        index=False,
        compression=options.parquet_compression,
        **parquet_kwargs,
    )
    return RawBlockArtifact(
        path=path,
        block=block,
        output_level=output_level,
        timestep=timestep_label(output_level, interval_minutes),
        rows=len(frame),
        columns=tuple(frame.columns),
        interval_minutes=interval_minutes,
        pyrend=pyrend,
        year=year,
    )
