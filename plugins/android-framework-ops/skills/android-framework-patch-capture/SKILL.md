---
name: android-framework-patch-capture
description: "Use after Android Framework code changes are implemented, staged, failed, or blocked but need to be turned into a reviewable or cautionary engineering material package for later android-knowledge-intake incoming submission."
---

# Android Framework Patch Capture

Use this skill when a Framework feature is ready to be packaged as a reviewable or cautionary engineering material package. It does not implement requirements, diagnose root cause, build, deploy, decide final correctness, or make curation decisions. It packages existing source changes into one feature README, one or more repository-level patches, and evidence so `android-knowledge-intake` can submit them as incoming.

Use it after `android-framework-change-workflow` has produced a concrete change, and before `android-knowledge-intake` submits a valuable patch package through the server submission channel. The user's local `android-knowledge-curation-maintainer` skill decides whether it later enters the knowledge repository.

The generated package includes patch content `sha1` for server-side deduplication. If a known daily/weekly incoming run produced the work context, pass `--related-report-run-id <run_id>` so intake can preserve an explicit report link. Weekly links are provenance only; weekly packages are not knowledge repository materialization candidates.

Search evidence is development evidence, not a curation decision. A Codex-authored `validated` patch package must carry pre-change knowledge search evidence with `search_before_change.searched=true`. If no usable knowledge was found, record `--reuse-decision not_found` instead of omitting search evidence. If search has hits, close the search usage decision with `--reuse-decision reuse`, `adapt`, `reference_only`, `not_applicable`, or `not_found`; do not leave it as `unknown`. Record `--reuse-target`, `--reuse-match`, `--reuse-mismatch`, or `--reuse-reason` when a hit influenced the implementation. If the implementation origin is `manual`, `external`, `historical`, `mixed`, or `unknown` and no pre-change search happened, record that fact; do not invent a search record.

`--project` is a high-priority hint only when it contains a company project anchor in the current recognition scope (`TVD`, `TVE`, `TVA`, or `TVI`). If `--project` is omitted or contains a generic label such as `mtk android16 Camera2`, the capture script must continue looking at source roots, repository paths, git branches/remotes, the WSL source-access registry, and feature README/diff/summary text before falling back to `unknown`.

The structured project field must contain only the normalized company model. Any text outside that model is evidence text, not part of `project`: branch suffixes, customer suffixes, build branches, business labels, module labels, Chinese descriptions, and other non-standard trailing text stay in `project_inference.raw_inputs` or `basis`. Examples: `TVE1067M1_H031` -> `TVE1067M1`, `TVE1086U_MAIN_HANGYAN` -> `TVE1086U`, `TVE1091U福建移动高清` -> `TVE1091U`. Do not truncate `TVE1067M1` to `TVE1067M`; those are different projects.

Project inference must be conservative. If `--project`, source roots, repository paths, git branches/remotes, WSL source-access registry, feature summary, or diff text expose multiple different TVD/TVE/TVA/TVI project models, the package must write `project=unknown`, preserve all candidates in `project_inference.candidates`, and record the conflict in `project_inference.limits`; later `android-knowledge-intake` will keep it out of `validated` status until a 补证包（evidence supplement package）closes the ambiguity.

## Boundary

- `android-framework-change-workflow`: owns requirement analysis, source changes, risk, build/deploy coordination, and final verification.
- `android-framework-patch-capture`: owns feature README, repository-level patch, and evidence packaging for existing changes.
- `android-knowledge-intake`: owns daily/weekly/framework_change incoming package submission through the server submission channel.

## Quick Command

From the Android source git repository with local changes. Repeat `--source-root` when one feature spans multiple repo-managed Git repositories:

```bash
python3 "scripts/capture_framework_patch.py" \
  --source-root /work/android/frameworks/base \
  --source-root /work/android/packages/apps/Settings \
  --platform rk14 \
  --feature display-policy-settings-entry \
  --summary "调整显示策略和设置入口" \
  --implementation-origin codex \
  --project "TVE8402M" \
  --status candidate \
  --verification "framework 编译通过" \
  --device rk3576 \
  --device-verification "设备验证通过" \
  --search-query "电源键 用户态 控制" \
  --search-result "命中电源键传递案例但项目和 Android 版本不同" \
  --reuse-decision adapt \
  --reuse-target case-power-key-to-app \
  --reuse-match "同类按键策略需求" \
  --reuse-mismatch "旧变体是 rk12，当前项目是 rk14" \
  --reuse-reason "复用案例思路，按当前项目源码适配" \
  --reuse-outcome adapted_success \
  --build-result /path/to/build-result.json
```

The script writes:

```text
.codex/patch-packages/YYYYMMDD-HHMMSS-feature/
├── manifest.json
├── README.md
├── patches/
│   ├── rk14-frameworks-base@display-policy-settings-entry.patch
│   └── rk14-settings@display-policy-settings-entry.patch
└── evidence/
    ├── changed-files.json
    ├── patch-diff-facts.json
    ├── patch-problem-summary.json
    ├── risk-surface.json
    ├── coding-standard-check.json
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
3. Feature package text: summary, feature name, README, repository paths, and diffs.

Do not write generic labels such as `android16`, `Camera2`, or `mtk android16 Camera2` as the package project. Preserve them only as checked inference inputs.

Before packaging, inspect `git status --short` for every source repository and preserve unrelated user work. Package only the intended feature change set. If unrelated files are dirty, stop and ask whether to split, stash, or include them.

One capture package represents one feature. If the feature spans multiple repo-managed Git repositories, pass every affected repository with repeated `--source-root`; the package will contain one root `README.md` and one patch per affected repository.

Do not use one capture package for a date-bundled patch set such as “今日补丁合集” or “今天完成 6 个补丁”. A member may implement code manually, but the uploaded framework material must still be wrapped by this skill as a function-level patch package. Multiple independent features must be split into multiple patch packages; only multiple patches that belong to the same feature may stay in one package.

If one feature summary is clear but the diff includes many unrelated resource keys, settings keys, system properties, or other anchors, treat it as patch asset contamination rather than a valid package. Stop and ask the member to recapture the same feature from a clean worktree. If this is fixing an already uploaded package, the corrected capture package must later be submitted as a 补证包（evidence supplement package） linked to the original package key; never hand-edit the original incoming package.

Pure file mode diffs such as `old mode 100755` / `new mode 100644` are usually checkout or chmod noise, not a feature change. Patch capture filters diff sections that contain only mode changes. If every changed file is mode-only, stop with no package. If a repository has both real content changes and mode-only noise, keep the content diff and drop the mode-only sections. A chmod change may be preserved only when it is part of an intentional executable-script or tool behavior change and is accompanied by content, summary, risk, and verification evidence.

Patch filename must follow:

```text
平台Android版本-模块名@补丁功能名.patch
```

`--platform` 必须使用当前受控平台令牌：`mtk<Android版本>`、`rk<Android版本>` 或 `unisoc<Android版本>`。历史别名 `sprd<Android版本>` 和 `u<Android版本>` 会规范化为 `unisoc<Android版本>`。不要使用 `android14`、`app15` 这类泛化令牌；它们只能说明可能的 Android 版本，不能证明平台（platform）。生成的补丁资产（patch asset）文件名也必须使用受控平台前缀，例如 `mtk15-`、`rk14-` 或 `unisoc16-`；`app15-*.patch` 这类文件名不能上传，必须从正确项目和平台工作树重新采集。

Examples:

```text
rk14-frameworks-base@allow-powerkey-to-user.patch
mtk14-systemui@statusbar-icon-policy.patch
unisoc13-framework-res@default-navigation-mode.patch
```

The generated feature README should contain facts first. Do not overclaim reuse, platform compatibility, or validation. Store facts that future AI can judge:

- requirement summary
- modified files
- touched artifacts
- SystemProperties
- Settings keys
- resource/string keys
- FrameworkLog keys
- build and device verification evidence
- pre-change knowledge search decision: `reuse`, `adapt`, `reference_only`, `not_applicable`, `not_found`, or `unknown`
- remote build server, remote source path, artifact path, artifact SHA1, local transfer, local adb serial, and device delivery action when the member workflow spans a remote build server and a local device
- risk and rollback notes

When `android-wsl-remote-build-deploy/scripts/push-artifacts.sh` has written `.codex/evidence/latest-build-delivery.json` under a source root, `capture_framework_patch.py` reads it automatically and merges it into `verification-result.json`. Manual `--remote-build-*`, `--artifact-transfer`, `--local-artifact`, and `--adb-*` arguments remain available for exceptional cases or historical material.

`validated`, `candidate`, `draft`, `failed`, `blocked`, and platform labels are useful hints, not final truth. Future `android-framework-change-workflow` or knowledge-search skills should dynamically judge applicability from the stored facts.

Status meaning:

- `validated`: verified for the original project scope.
- `candidate`: coherent change with partial or incomplete verification.
- `draft`: unfinished but useful Framework work.
- `failed`: failed implementation or verification path worth preserving.
- `blocked`: blocked work evidence worth preserving.

## Hard Stops

Stop before upload when:

- any generated patch is empty
- every changed file is only a file mode change such as `old mode 100755` / `new mode 100644`
- the summary or feature name describes a date-bundled patch set such as “今日补丁合集” instead of one function
- the change set includes unrelated dirty files
- one feature package contains many resource keys, settings keys, or system properties unrelated to the stated feature; recapture a clean patch asset instead
- a patch lacks the required author/date marker such as `//gyf 20251016@`, unless the user explicitly accepts a local-only draft
- new added lines contain direct `Log.*` or `Slog.*`
- README facts are unknown but presented as verified
- build or device verification is missing but status is `validated`
- status is `validated`, implementation origin is `codex`, and pre-change knowledge search evidence is missing
- status is `validated`, knowledge search returned hits, and search usage decision is still `unknown`

Team or project coding rules, such as `jinny-framework-coding-standards`, should be applied during development. This skill only checks and records violations; it is not the place to retrofit coding style after the fact.

When the code was not authored by Codex, pass `--implementation-origin manual`, `external`, `historical`, `mixed`, or `unknown`. The package records this as curation input material; it does not turn the change into curated knowledge and does not fabricate pre-change knowledge search. Admin-side curation can later run post-change overlap check to decide new, merge, archive, or needs evidence.

For `validated`, device verification is required by default. Use `--verification-method equivalent` only when device interaction is not the right proof, and provide `--equivalent-type`, `--equivalent-reason`, at least one `--equivalent-coverage`, and `--remaining-risk`.

## References

Read `references/package-contract.md` before changing the script output format or integrating with other skills.
