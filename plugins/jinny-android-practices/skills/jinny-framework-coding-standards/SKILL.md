---
name: jinny-framework-coding-standards
description: "Use when implementing, modifying, packaging, or reviewing Android Framework code that must follow Jinny team coding standards, FrameworkLog rules, patch annotations, resource strings, SystemProperties, patch README, or team patch/log specs."
---

# Jinny Framework Coding Standards

Use this skill as the Jinny team coding constraint layer for Android Framework work. It is meant to run before code edits when a requirement is implemented by Codex, and as a verification layer when reviewing, packaging, or inheriting code that was written manually or imported from another source.

When this skill applies together with `android-framework-change-workflow`, load it before Gate 3 code changes and keep its rules active through patch capture.

## Required Reference

Read `references/android-framework-coding-standards.md` before editing Framework code or judging whether a patch is acceptable.

## Core Rules

- Do not treat patch capture as the place to repair coding style. Code produced by Codex must already follow the team rules before capture.
- Every custom code block or single-line custom change must carry an author/date marker such as `//gyf 20251016@`.
- New direct `Log.*` or `Slog.*` calls are forbidden; use `FrameworkLog` and the appropriate debug switch.
- New `persist.sys.framework.debug.*` switches must be centralized in `frameworks/base/services/core/java/com/android/server/FrameworkLog.java`.
- User-visible strings and log message templates should use resources, including Chinese and English values when user-visible or reused.
- If two or more custom helper methods are added for the same feature, extract a same-package utility class named with the author suffix and `Utils`, such as `ActivityManagerGyfUtils`.
- Patch material should be organized by function: one feature README with one or more repository-level patches when the feature spans multiple repo-managed Git repositories.

## Capture Boundary

For Codex-authored code, patch capture should mostly confirm the rules and preserve evidence. For manual, historical, external, or half-inherited code, capture must run the checks and report violations as evidence; it must not silently present noncompliant code as compliant.

If a violation changes runtime behavior risk, package as `candidate`, `draft`, `failed`, or stop before upload instead of claiming `validated`.
