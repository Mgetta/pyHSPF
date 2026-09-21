"""Shared exception types for pyHSPF."""

from __future__ import annotations

from typing import Any


class HspfError(Exception):
    """Base package error."""


class ConventionError(HspfError):
    """Raised when a core convention is violated."""


class ValidationError(HspfError):
    """Publish-blocking validation failure."""

    def __init__(
        self,
        message: str,
        *,
        gate: int | str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.gate = gate
        self.context = context or {}


class SchemaConformanceError(ValidationError):
    """Schema-conformance validation failure."""
