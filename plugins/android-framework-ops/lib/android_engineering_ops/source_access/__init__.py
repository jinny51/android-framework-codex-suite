"""Host routing for the canonical Android source-access intent."""

from .host import (
    SourceAccessHost,
    UnsupportedSourceAccessHost,
    adapter_root,
    detect_source_access_host,
)
from .dispatch import (
    ADAPTER_COMMANDS,
    adapter_environment,
    adapter_skill_root,
    dispatch_adapter_command,
    resolve_adapter_command,
)

__all__ = [
    "SourceAccessHost",
    "UnsupportedSourceAccessHost",
    "adapter_root",
    "detect_source_access_host",
    "ADAPTER_COMMANDS",
    "adapter_environment",
    "adapter_skill_root",
    "dispatch_adapter_command",
    "resolve_adapter_command",
]
