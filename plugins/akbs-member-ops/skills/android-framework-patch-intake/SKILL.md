---
name: android-framework-patch-intake
description: "Deprecated compatibility wrapper for akbs-patch-submit. Use only when an existing invocation still names android-framework-patch-intake."
---

# Android Framework Patch Intake Compatibility

Forward the unchanged arguments and exit status from
`scripts/android_framework_patch_intake.py` to `akbs-patch-submit`. Tell the user that
`$akbs-patch-submit` is the replacement. This wrapper contains no package builder,
validator, uploader, or protocol fallback.
