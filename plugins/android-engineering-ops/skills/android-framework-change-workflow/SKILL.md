---
name: android-framework-change-workflow
description: "Compatibility wrapper for the retired Android Framework workflow Skill ID. Use only when an existing prompt names this ID; immediately continue with android-change-workflow and preserve the original arguments and intent."
---

# Android Framework Change Workflow Compatibility

This is a migration-only thin wrapper. Read and follow
`../android-change-workflow/SKILL.md`, then perform the request as
`$android-change-workflow` with compatibility hints `component.layer=platform` and
`component.type=framework`. Partition and ownership remain explicit facts or
`unknown`; the wrapper must not infer `system` or `aosp`.

Do not implement policy, routing, source access, build, verification, capture, provider
selection, or acceptance in this wrapper. The canonical owner is
`android-change-workflow`.
