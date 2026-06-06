---
name: android-framework-patch-capture
description: "Use after Android Framework code changes are implemented, staged, failed, or blocked but need to be turned into a reusable or cautionary engineering asset for later android-knowledge-intake incoming submission."
---

# Android Framework Patch Capture

Use this skill when a Framework change is ready to be packaged as a reusable, reviewable, or cautionary patch asset. It does not implement requirements, diagnose root cause, build, deploy, or decide final correctness. It packages existing source changes into `patch + readme + evidence` so `android-knowledge-intake` can submit them as incoming.

Use it after `android-framework-change-workflow` has produced a concrete change, and before `android-knowledge-intake` submits a valuable patch package through the server submission channel. The user's local `android-knowledge-curation-maintainer` skill decides whether it later enters the knowledge repository.

The generated package includes patch content `sha1` for server-side deduplication. If a known daily/weekly incoming run produced the work context, pass `--related-report-run-id <run_id>` so intake can preserve an explicit report link. Weekly links are provenance only; weekly packages are not knowledge repository materialization candidates.

`--project` is a high-priority hint only when it contains a company project anchor in the current recognition scope (`TVE`, `TVA`, or `TVI`). If `--project` is omitted or contains a generic label such as `mtk android16 Camera2`, the capture script must continue looking at `source_root`, git branch, git remote, the WSL source-access registry, and patch/readme/diff/summary text before falling back to `unknown`.

## Boundary

- `android-framework-change-workflow`: owns requirement analysis, source changes, risk, build/deploy coordination, and final verification.
- `android-framework-patch-capture`: owns patch/readme/evidence packaging for existing changes.
- `android-knowledge-intake`: owns daily/weekly/framework_change incoming package submission through the server submission channel.

## Quick Command

From the Android source git repository with local changes:

```bash
python3 "scripts/capture_framework_patch.py" \
  --platform rk14 \
  --feature allow-powerkey-to-user \
  --summary "允许用户态控制电源键行为" \
  --project "TVE8402M" \
  --status candidate \
  --verification "framework 编译通过" \
  --device rk3576 \
  --device-verification "设备验证通过" \
  --search-query "电源键 用户态 控制" \
  --search-result "未发现可直接复用补丁" \
  --build-result /path/to/build-result.json
```

The script writes:

```text
.codex/patch-packages/YYYYMMDD-HHMMSS-patch/
├── manifest.json
├── patches/
│   ├── rk14-frameworks-base@allow-powerkey-to-user.patch
│   └── rk14-frameworks-base@allow-powerkey-to-user.readme.md
└── evidence/
    ├── changed-files.json
    ├── build-result.json
    ├── verification-result.json
    ├── search-before-change.json
    └── package-check.json
```

To submit later with `android-knowledge-intake`, pass the whole capture package directory so
search-before-change, build, verification, and package-check evidence are preserved:

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" \
  --profile <member_alias> patch --prepare \
  --patch-package .codex/patch-packages/<run-id>/ \
  --project "TVE8402M" \
  --summary "补丁摘要" \
  --status candidate
```

## Packaging Rules

Project recognition priority is:

1. Explicit `--project` containing a `TVE`/`TVA`/`TVI` project model.
2. Source context from the active git tree: `source_root`, git branch, git remote, and remembered WSL source-access registry entries.
3. Patch package text: summary, feature name, readme, and diff.

Do not write generic labels such as `android16`, `Camera2`, or `mtk android16 Camera2` as the package project. Preserve them only as checked inference inputs.

Before packaging, inspect `git status --short` and preserve unrelated user work. Package only the intended change set. If unrelated files are dirty, stop and ask whether to split, stash, or include them.

Patch filename must follow:

```text
平台Android版本-模块名@补丁功能名.patch
```

Examples:

```text
rk14-frameworks-base@allow-powerkey-to-user.patch
mtk14-systemui@statusbar-icon-policy.patch
unisoc13-framework-res@default-navigation-mode.patch
```

The generated readme should contain facts first. Do not overclaim reuse, platform compatibility, or validation. Store facts that future AI can judge:

- requirement summary
- modified files
- touched artifacts
- SystemProperties
- Settings keys
- resource/string keys
- FrameworkLog keys
- build and device verification evidence
- risk and rollback notes

`validated`, `candidate`, `draft`, `failed`, `blocked`, and platform labels are useful hints, not final truth. Future `android-framework-change-workflow` or knowledge-search skills should dynamically judge applicability from the stored facts.

Status meaning:

- `validated`: verified for the original project scope.
- `candidate`: coherent change with partial or incomplete verification.
- `draft`: unfinished but useful Framework work.
- `failed`: failed implementation or verification path worth preserving.
- `blocked`: blocked work evidence worth preserving.

## Hard Stops

Stop before upload when:

- the generated patch is empty
- the change set includes unrelated dirty files
- the patch lacks the required author/date marker such as `//gyf 20251016@`, unless the user explicitly accepts a local-only draft
- new added lines contain direct `Log.d/i/w` or `Slog.d/i/w`
- readme facts are unknown but presented as verified
- build or device verification is missing but status is `validated`

For `validated`, device verification is required by default. Use `--verification-method equivalent` only when device interaction is not the right proof, and provide `--equivalent-type`, `--equivalent-reason`, at least one `--equivalent-coverage`, and `--remaining-risk`.

## References

Read `references/package-contract.md` before changing the script output format or integrating with other skills.
