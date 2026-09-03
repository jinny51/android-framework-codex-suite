---
name: android-framework-patch-capture
description: "Compatibility wrapper for the retired Framework patch-capture Skill ID and CLI. Use only for existing callers, then forward unchanged to android-patch-capture."
---

# Android Framework Patch Capture Compatibility

This is a migration-only thin wrapper. Read and follow
`../android-patch-capture/SKILL.md`; the canonical owner is `android-patch-capture`.
Preserve the caller's arguments, exit status, stdout, and stderr. This wrapper must not
change package status, rewrite an artifact, or implement capture logic.

The legacy Python entry at `scripts/capture_framework_patch.py` directly execs
`../android-patch-capture/scripts/capture_android_patch.py`; when the old caller omits
all component input, the wrapper adds only the legacy `framework` route, which yields
platform/framework plus truthful `unknown` facets. New callers use the canonical path
and all four component fields.
