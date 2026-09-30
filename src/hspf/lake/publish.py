"""Write-side publish helpers for HSPF lake artifacts.

The publish layer is responsible for making staged lake artifacts durable and
visible.  It should not parse HBN files, transform DataFrames, or own catalog
schemas.  Those responsibilities belong to ``ingest.py``, ``manifest.py``,
``validate.py``, and ``catalogs``.

The intended lifecycle is:

    1. Create a staging-rooted :class:`LakeLayout`.
    2. Write raw files/manifests/catalog updates into staging.
    3. Validate staged contents.
    4. Acquire a publish lock.
    5. Promote staged files into the final lake, metadata last.
    6. Release the lock and optionally clean staging.

Only the directory initialization and staging-layout helpers are implemented
for now.  The publish/lock functions are deliberately sketched but
unimplemented so the API can be reviewed before behavior is locked in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal
from uuid import uuid4

from hspf.core.conventions import validate_run_id
from hspf.core.errors import ConventionError
from hspf.lake.layout import LakeLayout


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PUBLISH_SCHEMA_VERSION = "lake-publish-v0"
PUBLISH_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

DEFAULT_STAGING_PREFIX = "publish"
DEFAULT_LOCK_NAME = "publish"
LOCK_FILE_SUFFIX = ".lock.json"

PUBLISH_MODE_APPEND = "append"
PUBLISH_MODE_REPLACE = "replace"
PUBLISH_MODES = frozenset({PUBLISH_MODE_APPEND, PUBLISH_MODE_REPLACE})

PUBLISH_STATUS_PLANNED = "planned"
PUBLISH_STATUS_STAGED = "staged"
PUBLISH_STATUS_VALIDATED = "validated"
PUBLISH_STATUS_COMMITTED = "committed"
PUBLISH_STATUS_ABORTED = "aborted"
PUBLISH_STATUS_FAILED = "failed"
PUBLISH_STATUSES = frozenset(
    {
        PUBLISH_STATUS_PLANNED,
        PUBLISH_STATUS_STAGED,
        PUBLISH_STATUS_VALIDATED,
        PUBLISH_STATUS_COMMITTED,
        PUBLISH_STATUS_ABORTED,
        PUBLISH_STATUS_FAILED,
    }
)

PUBLISH_ACTION_COPY = "copy"
PUBLISH_ACTION_MOVE = "move"
PUBLISH_ACTION_DELETE = "delete"
PUBLISH_ACTION_WRITE = "write"
PUBLISH_ACTIONS = frozenset(
    {
        PUBLISH_ACTION_COPY,
        PUBLISH_ACTION_MOVE,
        PUBLISH_ACTION_DELETE,
        PUBLISH_ACTION_WRITE,
    }
)

PublishMode = Literal["append", "replace"]
PublishStatus = Literal[
    "planned",
    "staged",
    "validated",
    "committed",
    "aborted",
    "failed",
]
PublishActionKind = Literal["copy", "move", "delete", "write"]


# ---------------------------------------------------------------------------
# Public records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PublishOptions:
    """Runtime knobs for publish behavior.

    ``mode`` describes how staged files should relate to existing final files:
    append/backfill should only add or update targeted paths, while replace is
    reserved for intentionally replacing a full run or release.
    """

    mode: PublishMode = PUBLISH_MODE_APPEND
    validate_before_commit: bool = True
    cleanup_staging_on_success: bool = True
    allow_overwrite: bool = False
    lock_name: str = DEFAULT_LOCK_NAME
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in PUBLISH_MODES:
            raise ConventionError(f"Invalid publish mode: {self.mode!r}")
        _validate_name("lock_name", self.lock_name)


@dataclass(frozen=True)
class PublishContext:
    """The layouts and identifiers for one publish attempt."""

    publish_id: str
    final_layout: LakeLayout
    staging_layout: LakeLayout
    options: PublishOptions = field(default_factory=PublishOptions)
    created_at: str = field(default_factory=lambda: _utc_now())

    def __post_init__(self) -> None:
        _validate_name("publish_id", self.publish_id)


@dataclass(frozen=True)
class PublishLock:
    """A filesystem lock record for a publish attempt."""

    lock_id: str
    name: str
    path: Path
    publish_id: str
    created_at: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_name("lock_id", self.lock_id)
        _validate_name("name", self.name)
        _validate_name("publish_id", self.publish_id)


@dataclass(frozen=True)
class PublishAction:
    """One planned or completed filesystem action."""

    source: Path
    target: Path
    action: PublishActionKind
    status: PublishStatus = PUBLISH_STATUS_PLANNED
    message: str | None = None

    def __post_init__(self) -> None:
        if self.action not in PUBLISH_ACTIONS:
            raise ConventionError(f"Invalid publish action: {self.action!r}")
        if self.status not in PUBLISH_STATUSES:
            raise ConventionError(f"Invalid publish status: {self.status!r}")


@dataclass(frozen=True)
class PublishPlan:
    """A set of filesystem actions needed to promote staged artifacts."""

    publish_id: str
    mode: PublishMode
    actions: tuple[PublishAction, ...]
    run_ids: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_name("publish_id", self.publish_id)
        if self.mode not in PUBLISH_MODES:
            raise ConventionError(f"Invalid publish mode: {self.mode!r}")
        for run_id in self.run_ids:
            validate_run_id(run_id)


@dataclass(frozen=True)
class PublishResult:
    """Summary returned after a publish attempt."""

    publish_id: str
    status: PublishStatus
    actions: tuple[PublishAction, ...] = ()
    lock: PublishLock | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        _validate_name("publish_id", self.publish_id)
        if self.status not in PUBLISH_STATUSES:
            raise ConventionError(f"Invalid publish status: {self.status!r}")


# ---------------------------------------------------------------------------
# Implemented setup helpers
# ---------------------------------------------------------------------------

def staging_layout(layout: LakeLayout, name: str) -> LakeLayout:
    """Return a layout rooted under ``_staging`` for write-then-promote flows."""

    return LakeLayout(layout.staging_dir(name), strict_unc=layout.strict_unc)


def initialize_lake(layout: LakeLayout) -> LakeLayout:
    """Create the top-level directories for a lake layout."""

    for path in (
        layout.root,
        layout.raw_dir,
        layout.catalog_dir,
        layout.curated_dir,
        layout.observations_dir,
        layout.staging_dir(),
        layout.lock_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)

    return layout


# ---------------------------------------------------------------------------
# Publish lifecycle skeleton
# ---------------------------------------------------------------------------

def begin_publish(
    layout: LakeLayout,
    *,
    publish_id: str | None = None,
    options: PublishOptions | None = None,
) -> PublishContext:
    """Create a publish context with a staging-rooted layout.

    Intended use:

        ``context = begin_publish(layout)``
        ``ingest`` writes to ``context.staging_layout``
        ``commit_publish(context, plan)`` promotes to ``context.final_layout``
    """

    raise NotImplementedError("Publish context creation is not yet implemented")


def plan_raw_run_publish(
    context: PublishContext,
    run_id: str,
    *,
    mode: PublishMode | None = None,
) -> PublishPlan:
    """Plan promotion actions for one staged raw run.

    The eventual implementation should compare the staged run directory against
    the final run directory and return the ordered actions needed to publish
    data files before manifest/catalog metadata.
    """

    raise NotImplementedError("Raw-run publish planning is not yet implemented")


def commit_publish(
    context: PublishContext,
    plan: PublishPlan,
    *,
    lock: PublishLock | None = None,
) -> PublishResult:
    """Promote staged artifacts described by ``plan`` into the final lake."""

    raise NotImplementedError("Publish commit is not yet implemented")


def abort_publish(
    context: PublishContext,
    *,
    reason: str | None = None,
    cleanup_staging: bool | None = None,
) -> PublishResult:
    """Abort a publish attempt and optionally remove its staging directory."""

    raise NotImplementedError("Publish abort is not yet implemented")


def cleanup_staging(context: PublishContext) -> None:
    """Remove the staging directory for ``context`` after success or abort."""

    raise NotImplementedError("Staging cleanup is not yet implemented")


# ---------------------------------------------------------------------------
# Lock skeleton
# ---------------------------------------------------------------------------

def lock_path(layout: LakeLayout, name: str = DEFAULT_LOCK_NAME) -> Path:
    """Return the lock-file path for ``name``."""

    _validate_name("lock name", name)
    return layout.lock_dir / f"{name}{LOCK_FILE_SUFFIX}"


def acquire_lock(
    context: PublishContext,
    *,
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> PublishLock:
    """Acquire a filesystem publish lock.

    A future implementation should create the lock atomically and fail if an
    unexpired lock already exists.
    """

    raise NotImplementedError("Publish locking is not yet implemented")


def release_lock(lock: PublishLock) -> None:
    """Release a filesystem publish lock."""

    raise NotImplementedError("Publish lock release is not yet implemented")


def read_lock(layout: LakeLayout, name: str = DEFAULT_LOCK_NAME) -> PublishLock | None:
    """Read an existing publish lock if present."""

    raise NotImplementedError("Publish lock reading is not yet implemented")


# ---------------------------------------------------------------------------
# Promotion skeleton
# ---------------------------------------------------------------------------

def promote_path(
    source: Path,
    target: Path,
    *,
    allow_overwrite: bool = False,
) -> PublishAction:
    """Promote one staged filesystem path to a final target path."""

    raise NotImplementedError("Path promotion is not yet implemented")


def promote_paths(
    actions: Iterable[PublishAction],
    *,
    allow_overwrite: bool = False,
) -> tuple[PublishAction, ...]:
    """Promote all paths in ``actions`` in order."""

    raise NotImplementedError("Batch path promotion is not yet implemented")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def make_publish_id(prefix: str = DEFAULT_STAGING_PREFIX) -> str:
    """Return a filesystem-safe publish identifier."""

    _validate_name("publish prefix", prefix)
    timestamp = _utc_now().replace("-", "").replace(":", "")
    return f"{prefix}-{timestamp}-{uuid4().hex[:8]}"


def _utc_now() -> str:
    """Return the current UTC time in the publish timestamp format."""

    return datetime.now(timezone.utc).strftime(PUBLISH_TIMESTAMP_FORMAT)


def _validate_name(label: str, value: str) -> None:
    """Validate a publish name/identifier used as one path component."""

    text = str(value).strip()
    if not text:
        raise ConventionError(f"{label} cannot be empty")
    if text in {".", ".."}:
        raise ConventionError(f"{label} cannot be a relative path component")
    if any(separator in text for separator in ("\\", "/")):
        raise ConventionError(f"{label} cannot contain path separators: {text!r}")
    if "=" in text:
        raise ConventionError(f"{label} cannot contain '=': {text!r}")
