"""Explicit optional-practices provider resolution for Android engineering."""

from .provider import (
    CapabilityBinding,
    ExtensionResolution,
    ExtensionResolutionError,
    ProviderValidationError,
    resolve_extension,
    validate_coding_decision,
    validate_execution_decision,
    validate_execution_decision_for_resolution,
)

__all__ = [
    "CapabilityBinding",
    "ExtensionResolution",
    "ExtensionResolutionError",
    "ProviderValidationError",
    "resolve_extension",
    "validate_coding_decision",
    "validate_execution_decision",
    "validate_execution_decision_for_resolution",
]
