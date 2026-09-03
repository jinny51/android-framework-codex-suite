---
name: android-member-setup
description: "Deprecated compatibility wrapper for akbs-member-setup. Use only when an existing invocation still names android-member-setup."
---

# Android Member Setup Compatibility

Forward the unchanged arguments and exit status from
`scripts/android_member_setup.py` to the canonical `akbs-member-setup` CLI. Tell the
user that `$akbs-member-setup` is the replacement. Do not implement setup or doctor
logic here; the target plugin has one internal incoming v1 kernel.
