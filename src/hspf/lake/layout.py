"""Path grammar for the HSPF lake.

The layout module is intentionally small: it knows folder names and partition
keys, but it does not create directories or write data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hspf.core.conventions import (
    is_unc_path,
    normalize_path,
    timestep_label,
    to_snake_case,
)
from hspf.core.errors import ConventionError
from hspf.core.types import Block, OutputLevel


SERVER_NAME = "pca.state.mn.us"
SHARE_NAME = "xdrive"
LAKE_ROOT_DIR = r"Databases2\Water_Quality\Watershed_Modeling\hspf_lake"

RAW_TIER = "raw"
CATALOG_TIER = "catalog"
CURATED_TIER = "curated"
OBSERVATIONS_TIER = "observations"
VALID_TIERS = frozenset({RAW_TIER, CATALOG_TIER, CURATED_TIER, OBSERVATIONS_TIER})

CURRENT_RELEASE_FILE = "CURRENT.txt"
MANIFEST_FILE = "manifest.json"
DEFAULT_PART_FILE = "part-0.parquet"


def default_lake_root() -> Path:
    """Return the MPCA default lake root."""

    return Path(rf"\\{SERVER_NAME}\{SHARE_NAME}\{LAKE_ROOT_DIR}")


class LakeLayout:
    """Resolve lake paths from a root folder."""

    __slots__ = ("root", "strict_unc")

    def __init__(
        self,
        root: str | Path | None = None,
        strict_unc: bool = False,
    ) -> None:
        root = (
            default_lake_root()
            if root is None
            else Path(normalize_path(root))
        )
        is_unc_path(root, strict_unc=strict_unc)
        self.root = root
        self.strict_unc = strict_unc

    def tier_dir(self, tier: str) -> Path:
        tier = _partition_value("tier", tier)
        if tier not in VALID_TIERS:
            raise ConventionError(f"Invalid lake tier: {tier!r}")
        return self.root / tier

    @property
    def raw_dir(self) -> Path:
        return self.tier_dir(RAW_TIER)

    @property
    def catalog_dir(self) -> Path:
        return self.tier_dir(CATALOG_TIER)

    @property
    def curated_dir(self) -> Path:
        return self.tier_dir(CURATED_TIER)

    @property
    def observations_dir(self) -> Path:
        return self.tier_dir(OBSERVATIONS_TIER)

    @property
    def current_release_path(self) -> Path:
        return self.curated_dir / CURRENT_RELEASE_FILE

    def raw_run_dir(self, run_id: str) -> Path:
        return self.raw_dir / _partition("run_id", run_id)

    def raw_block_dir(
        self,
        run_id: str,
        block: Block | str,
        output_level: OutputLevel | int | str,
        *,
        interval_minutes: int | None = None,
        year: int | None = None,
    ) -> Path:
        path = (
            self.raw_run_dir(run_id)
            / _partition("block", _block_label(block))
            / _partition("timestep", timestep_label(output_level, interval_minutes))
        )
        if year is not None:
            path = path / _partition("year", _year_value(year))
        return path

    def raw_part_path(
        self,
        run_id: str,
        block: Block | str,
        output_level: OutputLevel | int | str,
        *,
        interval_minutes: int | None = None,
        year: int | None = None,
        filename: str = DEFAULT_PART_FILE,
    ) -> Path:
        return (
            self.raw_block_dir(
                run_id,
                block,
                output_level,
                interval_minutes=interval_minutes,
                year=year,
            )
            / _partition_value("filename", filename)
        )

    def manifest_path(self, run_id: str) -> Path:
        return self.raw_run_dir(run_id) / MANIFEST_FILE

    def catalog_path(self, name: str, *, subdir: str | None = None) -> Path:
        filename = _parquet_filename("catalog name", name)
        base = (
            self.catalog_dir
            if subdir is None
            else self.catalog_dir / to_snake_case(subdir)
        )
        return base / filename

    def curated_release_dir(self, version: str) -> Path:
        return self.curated_dir / _partition("v", version)

    def curated_mart_dir(self, version: str, mart: str) -> Path:
        return self.curated_release_dir(version) / _partition(
            "mart", to_snake_case(mart)
        )

    def resolve_current_release(self) -> Path:
        version = self.current_release_path.read_text(encoding="utf-8").strip()
        if not version:
            raise ConventionError(f"{self.current_release_path} is empty")
        return self.curated_release_dir(version)

    def staging_dir(self, name: str | None = None) -> Path:
        staging = self.root / "_staging"
        return (
            staging
            if name is None
            else staging / _partition_value("staging name", name)
        )

    @property
    def lock_dir(self) -> Path:
        return self.root / "_lock"


def _partition(key: str, value: Any) -> str:
    return f"{key}={_partition_value(key, value)}"


def _partition_value(key: str, value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise ConventionError(f"{key} cannot be empty")
    if text in {".", ".."}:
        raise ConventionError(f"{key} cannot be a relative path component: {text!r}")
    if any(separator in text for separator in ("\\", "/")):
        raise ConventionError(f"{key} cannot contain path separators: {text!r}")
    if "=" in text:
        raise ConventionError(f"{key} cannot contain '=': {text!r}")
    return text


def _block_label(block: Block | str) -> str:
    if isinstance(block, Block):
        return block.name
    return to_snake_case(block)


def _year_value(year: int) -> int:
    value = int(year)
    if not 1 <= value <= 9999:
        raise ConventionError(f"year must be between 1 and 9999: {year!r}")
    return value


def _parquet_filename(key: str, name: str) -> str:
    text = _partition_value(key, name)
    suffix = ".parquet"
    stem = text[: -len(suffix)] if text.lower().endswith(suffix) else text
    return f"{to_snake_case(stem)}{suffix}"
