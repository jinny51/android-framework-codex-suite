---
name: android-framework-patch-capture
description: "Use after Android Framework code changes are implemented, staged, failed, or blocked but need to be turned into a reusable or cautionary engineering asset: generate a standards-compliant patch file, paired readme, changed-file evidence, symbol facts, log/property checks, and a package manifest for later android-knowledge-intake submission and team knowledge indexing."
---

# Android Framework Patch Capture

Use this skill when a Framework change is ready to be packaged as a reusable, reviewable, or cautionary patch asset. It does not implement requirements, diagnose root cause, build, deploy, or decide final correctness. It packages existing source changes into `patch + readme + evidence` so `android-knowledge-intake` can submit them as incoming.

Use it after `android-framework-change-workflow` has produced a concrete change, and before `android-knowledge-intake` uploads a valuable patch to the team knowledge repository.

## Boundary

- `android-framework-change-workflow`: owns requirement analysis, source changes, risk, build/deploy coordination, and final verification.
- `android-framework-patch-capture`: owns patch/readme/evidence packaging for existing changes.
- `android-knowledge-intake`: owns daily/weekly/patch package submission to the knowledge repository.

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
  --search-result "未发现可直接复用补丁"
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
    ├── verification-result.json
    ├── search-before-change.json
    └── package-check.json
```

To submit later with `android-knowledge-intake`, pass the whole capture package directory so
search-before-change, verification, and package-check evidence are preserved:

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" \
  --profile jinny patch --prepare \
  --patch-package .codex/patch-packages/<run-id>/ \
  --project "TVE8402M" \
  --summary "补丁摘要" \
  --status candidate
```

## Packaging Rules

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
