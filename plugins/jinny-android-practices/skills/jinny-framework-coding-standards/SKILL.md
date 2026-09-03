---
name: jinny-framework-coding-standards
description: "Compatibility wrapper for the retired Jinny Framework coding Skill ID. Use only when an existing prompt names this ID, then continue with jinny-android-coding-practices under an explicitly selected provider."
---

# Jinny Framework Coding Standards Compatibility

This is a migration-only thin wrapper. Read and follow
`../jinny-android-coding-practices/SKILL.md`, then return the same decision as
`$jinny-android-coding-practices`.

Do not keep coding rules, model routing, provider discovery, or decision construction in
this wrapper. It cannot implicitly enable the Jinny provider; the core extension resolver
must already have selected and validated it.
