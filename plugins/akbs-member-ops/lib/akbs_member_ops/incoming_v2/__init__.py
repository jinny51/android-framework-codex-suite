"""Standalone client-side support for the frozen Android change v2 contracts."""

from .capture_adapter import preflight_capture
from .materializer import materialize_capture
from .validation import (
    AndroidChangeV2Error,
    check_package,
    prepare_package,
    read_package,
    writer_status,
)

__all__ = [
    "AndroidChangeV2Error",
    "check_package",
    "materialize_capture",
    "preflight_capture",
    "prepare_package",
    "read_package",
    "writer_status",
]
