---
name: android-knowledge-intake
description: Use when handling member first setup, doctor checks, plugin updates, config migration, legacy daily/weekly/patch intake commands, or the shared member-side incoming kernel. Prefer the split daily, weekly, or patch intake skills for new business package generation. Do not use for knowledge curation decisions.
---

# Android Knowledge Intake

Use this skill for member-side incoming shared kernel work, setup, doctor checks, plugin updates, config migration, and legacy command routing. New member-facing business entrypoints are split into `android-daily-report-intake`, `android-weekly-report-intake`, and `android-framework-patch-intake`; they all route to this shared script and protocol layer instead of copying upload logic.

The skill does not write final knowledge reports, curated patches, index, or site directories. It creates a local pending incoming package first, then sends that package through the server submission channel. The member-side skill does not clone, pull, directly search, or push the database repository; member viewing UI is a separate server-side database view.

The member-side Codex agent is the material producer. It should collect session context, git activity, patch diff, build results, verification records, failed paths, blocked paths, and optional human notes, then generate incoming. The server submission channel only performs lightweight intake and writes the package to the intake branch. Admin-side local promotion later validates, rejects, requests evidence, or promotes the package into the database repository. Knowledge repository content and curation decisions are produced later by the user's local `akbs-curation-maintainer` skill and AI knowledge loop.

Ordinary members should use `android-daily-report-intake` for daily reports, `android-weekly-report-intake` for weekly reports, and `android-framework-patch-intake` for original patch packages, evidence supplements, replacement packages, and patch asset corrections. The old `android-knowledge-intake daily|weekly|patch` commands remain valid as 旧命令路由（legacy command routing） into the same 共享内核（shared kernel）. Weekly packages are progress archives only; they do not become knowledge repository materialization candidates. Non-member profiles are only for protocol and server-chain tests; they must not be confused with the user's local `akbs-curation-maintainer` skill.

Default policy: preserve work facts locally first, then upload only packages that pass the member-side upload gate. Daily traces must preserve `work_findings`; weekly traces preserve progress summaries for database archive and member view only. Ordinary framework-change upload and evidence supplements must be `validated`: clear function boundary, traceable project/platform/Android version, clean patch assets, and PASS build plus device or accepted equivalent verification. `candidate`, `draft`, `failed`, and `blocked` are local or report-context states; they do not enter the server upload queue by default. These values are not curation decisions.

Daily and weekly generation have no "future submission" mode. A daily package date later than the current local date must stop with "不能提交未来日期的日报，请重新生成正确日期的日报。". A weekly package whose anchor date is later than the current local date, or whose `week_range` is later than the current local week, must stop with "不能提交未来周期的周报，请重新生成正确周期的周报。". Older daily dates and older weekly periods are late submissions and are allowed.

Daily and weekly report bodies are the primary human-readable product. Generate `reports/daily.md` and `reports/weekly.md` with the Codex office report templates. Daily reports answer 今天干了什么 and include project overview, concrete work items, source, description, handling method, result, verification, remaining issue, outputs, risks, and tomorrow focus. Weekly reports answer 这一周整体推进得怎么样 and include project overview, requirement origin, requirement list type, source lists, source category stats, weekly item statistics, completed/in-progress/remaining items, risks, patch output, delivery verification, and next-week plan. Also write `materials/display/report_view.json` as a UI read model for cards, lists, and detail panes; it is a structured index of the same report, not a separate AI/evidence layer. Keep `work_findings.json` as evidence for audit and later analysis.

Daily and weekly generation is idempotent by member and report identity: daily uses `date`, weekly uses `week_range`. If a local pending or submitted report package already exists for the same member and identity, `--prepare`, `--upload`, and `--submit-latest` must stop instead of silently creating or uploading a second ordinary report package. The member must either cancel the new run or explicitly replace the old package. Use `daily --replace-daily-run-id <old_run_id>` or `weekly --replace-weekly-run-id <old_run_id>`; the replacement package writes `replacement_for_run_id` and `supersedes` metadata so it is not another silent ordinary report package.

Use configuration profiles for identity. Global config stores the submission channel and knowledge repository defaults; each `[profiles.<name>]` stores one member identity, knowledge worktree, git author, role, allowed modes, and optional test behavior. Prefer explicit `--profile <name>` in automations so a daily incoming run cannot accidentally use an administrator identity.

Framework change incoming must carry deterministic merge anchors. Patch content `sha1` is emitted in `patch_diff_facts`; `related_report_run_ids` is used only when the daily or weekly run id is explicitly known. A weekly run id is provenance only and does not make the weekly package a knowledge materialization candidate. Do not create fuzzy report links on the member side.

Framework change packages must also carry two stable read models. `materials/display/patch_view.json` is the human-facing model for member/admin cards and details: it must name the material as 原始包 or 补证包, provide a human title, problem, solution, result, project/platform/Android version, UI card text, detail sections, and supplement target when present. `materials/evidence/patch_ai_facts.json` is the AI/admin evidence model for validation, curation review, search indexing, and merge judgement: it must provide concrete module, feature domain, patch behavior goal, code anchors, patch assets, verification targets, search usage, search match class, and merge gate inputs. `adapt` and `reference_only` search decisions must be written as reference evidence only and must not imply a merge decision.

Daily and patch packages consume member-side search usage evidence written by `android-knowledge-search`. Daily packages include same-day search evidence when present. Patch packages prefer explicit capture evidence from `android-framework-patch-capture`, then fall back to same-day member search usage records only when the search record matches the current patch feature anchors such as summary, modified files, symbols, resource keys, settings keys, system properties, or framework log keys. Same member and same day are not enough. These values are development evidence, not curation decisions.

Search facts are not enough for a finished patch. Codex normal development should run pre-change knowledge search before source edits and record `reuse`, `adapt`, `reference_only`, `not_applicable`, or `not_found`; if no usable knowledge was found, record `not_found` instead of omitting the evidence. A `validated` package can still preserve real PASS verification when pre-change search did not happen, but the local check must warn instead of asking the member to fabricate search evidence; admin-side curation must run post-change overlap check and the package earns no search-loop reuse score. If a `validated` patch package has actual knowledge search hits, local package check must fail while the search usage decision remains `unknown`; the member-side Codex must close the real decision before upload. A capture package that only carries `unknown` search evidence must not override a same-day member search usage record with an explicit decision.

Manual implementation (`implementation_origin=manual`), external implementation, historical material, mixed implementation, or unknown provenance must not fabricate pre-change knowledge search. If the code was already implemented before search happened, record `search_before_change.searched=false` or leave the search evidence as not performed. The package can still preserve verification and patch facts for later curation, but it does not earn search usage feedback or reuse scoring from a search that never happened.

Project metadata is part of the knowledge loop, not a cosmetic UI field. Daily packages must write traceable project inference evidence when the day's context contains a TVD/TVE/TVA/TVI project model. Patch packages must prefer explicit `--project` or capture package project evidence, and when a patch is related to a known daily package, `--related-report-run-id` lets the patch inherit that daily project context. If no related report is explicit, patch prepare may automatically use the same member's same-day daily package only when that daily context has exactly one TVD/TVE/TVA/TVI project candidate; ambiguous or missing daily context must keep `project=unknown`. A 7-character company model such as `TVE1213` is incomplete by itself; only when the same inference flow already has trusted platform evidence may the plugin rules module complete the platform letter (`mtk -> M`, `rk -> R`, `unisoc -> U`) and then accept the resulting legal model such as `TVE1213M`. TVI is handled separately: an existing eighth character is preserved, while a short TVI model must complete the TVI chip field (`A/X`) instead of the AKBS platform letter (`R/M/U`). Generic labels such as `android16`, `mtk16`, `Camera2`, source folder names, platform, or Android version must not be written as project names. If no traceable project exists, keep `project=unknown` and record the checked sources and limits in `project_inference`; do not invent a project to make the UI look complete.

If project clues disagree, do not choose the first matching value. When explicit `--project`, capture package metadata, source roots, git branch or remote, WSL source-access registry, README/diff text, or related report context contain multiple different TVD/TVE/TVA/TVI project models, keep `project=unknown`, write every candidate into `project_inference.candidates`, record the conflict in `project_inference.limits`, and downgrade any `validated` package to `candidate`.

If a daily package contains multiple raw candidates that normalize to the same company model, such as `TVE1067M1`, `TVE1067M1_H031`, or `TVE1067M1客户描述`, write the normalized model `TVE1067M1` and keep the complete raw candidates in `project_inference`. Do not truncate it to `TVE1067M`. If candidates normalize to different company models, keep `project=unknown` and preserve the ambiguity.

Platform and Android version metadata are also knowledge applicability boundaries. Framework change packages may only write `platform=mtk`, `platform=rk`, `platform=unisoc`, or `platform=unknown`. Patch filenames or capture packages with `sprd` or `u` aliases normalize to `unisoc`; generic or non-standard prefixes must never become a project（project）or platform（platform）fact. Patch asset filenames must use a legal project（project）prefix or a controlled platform Android-version prefix such as `TVE1067M1-`, `mtk15-`, `rk14-`, or `unisoc16-`; any other uncontrolled prefix fails local package validation and the member must recapture from the correct project/platform worktree. If only the numeric Android version is traceable, keep `platform=unknown`; local curation must treat that as an evidence gap instead of materializing high-confidence knowledge. When member view UI asks the member to supplement platform or Android version and the capture package cannot prove it, patch prepare may use explicit `--platform mtk|rk|unisoc|unknown` and `--android-version <number>` so the supplement package carries the corrected applicability boundary.

Member-side generation and upload gates call the plugin rules module (`android_framework_ops.knowledge_rules`). This module owns project normalization, platform/Android version parsing, no-common-target aggregate package detection, pre-change knowledge search classification, search usage decision closure checks, patch asset pollution basics, and evidence supplement relationship checks. It only decides facts and gate failures; it does not decide curation decisions or knowledge validity, which remain admin-side local curation work. Server upload entrypoints must not load this module.

A patch package can still be preserved locally when project, platform, or Android version metadata is incomplete, but it must not stay `validated` and must not be uploaded as an ordinary patch package. Even with PASS verification, if the project remains `unknown`, the platform is `unknown`, or the Android version is `unknown`, downgrade the package to `candidate`, clear direct reuse hints, and record the metadata reason in patch diff facts. The member-side Codex must fix the boundary evidence and regenerate a `validated` package before upload, or create a `validated` evidence supplement when closing an existing needs-evidence task.

Synthetic profiles are for protocol and server testing only. Set `synthetic_data = true` for that temporary profile. In synthetic mode, `daily` and `weekly` generate random synthetic work items instead of reading real Codex sessions or source changes; `patch` can generate a synthetic framework_change package when no `--patch` is provided.

## Commands

Prepare a draft package without submitting:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> daily --prepare
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare
```

Submit the latest prepared package:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> daily --submit-latest
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> weekly --submit-latest
```

Prepare and submit in one run:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> daily --upload
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> weekly --upload
```

Explicitly replace an existing daily package for the same member and date:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> daily --prepare --replace-daily-run-id 20260629-210000-daily
```

Explicitly replace an existing weekly package for the same member and week:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare --replace-weekly-run-id 20260618-090102
```

Prepare a Framework change incoming package without generating a report:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch /path/to/rk14-frameworks-base@feature.patch --project "TVE8402M" --summary "功能补丁摘要" --status candidate
```

Attach a known daily or weekly run explicitly:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --summary "功能补丁摘要" --status candidate --related-report-run-id 20260601-210000-daily
```

Use the related daily run id whenever the patch belongs to a work item already described in that day's report. If the run id is omitted, patch prepare can use the same member's same-day daily package as project evidence only when it contains exactly one project candidate. Without an explicit project, capture project, explicit related daily context, or unique same-day daily context, a patch package may remain `project=unknown`; the server will preserve it, but local curation must treat the missing project as a metadata/evidence gap.

When the patch was packaged by `android-framework-patch-capture`, submit the capture package directory so build, verification, and pre-change search evidence are preserved:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --project "TVE8402M" --summary "功能补丁摘要" --status validated
```

When member view UI shows a previous patch package needs evidence, do not create a fourth package type. Regenerate or resubmit a normal `framework_change` patch package with the missing evidence and link it to the original incoming package:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare \
  --patch-package /path/to/.codex/patch-packages/20260612-171820-feature \
  --project "TVE1067M" \
  --platform mtk \
  --android-version 16 \
  --summary "功能补丁摘要" \
  --status validated \
  --supplement-for-package-key 20260612/lincong/20260612-172836-patch \
  --supplement-reason "补充项目（project）、平台（platform）和 Android 版本（Android version）证据"
```

Submit the latest prepared patch package:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --submit-latest
```

Check configuration:

```bash
python3 "scripts/android_knowledge_intake.py" doctor
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> doctor
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> doctor --strict --check-remote
```

## Automation

Recommended member-side incoming automations:

- 21:00 daily prepare: generate pending package for member check.
- 22:30 daily submit: submit the latest pending package.
- Saturday 22:00 weekly prepare.
- Saturday 22:30 weekly submit.

Before enabling member-side incoming automations, run `doctor --strict --check-remote` for the exact profile used by the automation. Strict doctor must pass before scheduled runs are enabled. It verifies identity, role, allowed modes, submission channel, knowledge repository path, Git availability, plugin freshness, and optional remote reachability.

Member profiles submit only through the server submission channel. Search must use the knowledge repository worktree through `android-knowledge-search`, never the database repository. Direct Git submission is removed from member setup and must not be used.

Synthetic profiles are only for protocol and gray-flow testing. Use `doctor --strict --allow-synthetic` only in tests; real member incoming automations must keep `synthetic_data = false`.

Framework change submission is automatic when the member-side Codex can identify a clean change, enough evidence, and a safe package status. If validation evidence is missing, submit as `candidate` or `draft`; do not discard the work. Administrator patch contribution remains manual by default.

Prefer `--patch-package` for Framework changes packaged by `android-framework-patch-capture`; it carries one feature README, one or more repository-level patches, build evidence, verification evidence, and pre-change knowledge search evidence when it really exists. Use `--patch` only when directly packaging one standalone patch file into the current incoming protocol. Multiple raw `--patch` files are rejected; they must first be converted into function-level patch packages by `android-framework-patch-capture`.

Patch packages are function-scoped, not date-scoped. A package may contain multiple repository-level patches only when they implement the same feature across repo-managed Git repositories. Date-bundled summaries such as “今日补丁合集” or one package containing several unrelated feature patches must stop before pending package generation or upload, with no patch-count exception. They must be split into multiple new 原始包（original package） before upload. If a member already has a no-common-target 聚合包（aggregate package）, do not supplement it; regenerate function-level original packages and upload them separately.

If member view UI reports 需补证据（needs_evidence）, the member-side entry remains `android-knowledge-intake`, but the action is routed by the missing field. Project, platform, Android version, verification, risk, rollback, and other evidence gaps should supplement real evidence and pass `--supplement-for-package-key <date/member/run-id>` plus `--supplement-reason <reason>`. Patch asset correction is the case that reruns `android-framework-patch-capture` from a clean source worktree before upload. Function split or no-common-target aggregate packages do not use a supplement package; upload new function-level original packages instead. This does not create a fourth incoming type and does not let members decide curation.

`--supplement-for-package-key` must point to the original package that was returned for evidence, not to another supplement package. If the visible target key contains a supplement-style run id such as `verification-supplement` or `project-supplement`, stop and ask for the original package key. Do not wrap a supplement around another supplement. If the original package is too broad, date-bundled, or has no common feature target, do not supplement it; split the work and upload new original patch packages by function.

If member view UI reports 补丁资产修正（patch asset correction）, do not edit the original incoming package. Re-run `android-framework-patch-capture` from a clean source worktree for the same feature, ensure the new README, patch files, search evidence, and verification evidence only describe that feature, and ensure patch filenames use a legal project（project）prefix or controlled platform prefixes such as `TVE1067M1-`, `mtk15-`, `rk14-`, or `unisoc16-`. Then submit the package as a 补证包（evidence supplement package） with `--supplement-for-package-key <original package key>`. The original polluted patch remains database audit material; curation may only use the corrected patch asset from the supplement.

Patch asset correction supplements must be created from a real `android-framework-patch-capture` package and submitted with `--patch-package <capture package dir>`. Do not use direct `--patch`, copied old patches, or hand-written descriptions to claim patch asset correction. If the source worktree still contains unrelated dirty files, stop before capture and separate the feature first.

Patch asset correction must not justify unrelated resource keys by listing them in README "关键符号", "字符串资源", or similar inventory sections. Local check treats only the feature goal and change description as scope evidence; if the corrected supplement package still contains many unrelated resource, setting, property, or log anchors, stop before upload and recapture from a clean worktree.

When a supplement reason asks for 项目（project）, 平台（platform）, Android 版本（Android version）, or 验证（verification）, the local package check must fail if the new supplement package still carries `project=unknown`, `platform=unknown`, `android_version=unknown`, or non-PASS verification for the requested field. Do not submit a supplement package that only repeats the old gap; collect the missing source path, capture package, related daily context, explicit `--platform` / `--android-version`, platform token, build result, or device verification first. If the old gap is 开发前知识搜索（pre-change knowledge search） but the implementation was manual or the search did not happen before development, do not fabricate a search record; record the manual implementation fact and let admin-side curation perform post-change overlap check.

For successful automation runs, launch `scripts/archive_automation_runs.py` with `setsid -f` and a short delay so the automation conversation is archived after Codex marks the run complete.

## Member First Setup

When a member needs first-time setup on the current double-repository chain, read `references/member-migration-prompt.md` and give the member the copy-paste prompt. The prompt makes Codex perform 插件更新（plugin update）, 新配置（new configuration）, 服务器上传入口（server upload endpoint） and 知识库仓库（knowledge repository） clone/update checks, and `doctor --strict --check-remote` before any daily, weekly, or patch generation. Members clone only the knowledge repository; they never clone the database repository.

The intake script also runs a plugin version gate before `daily`, `weekly`, or `patch` `--prepare`, `--upload`, and `--submit-latest`. It checks three versions: the plugin code running the script, the latest installed Codex plugin cache for `android-framework-ops`, and the GitHub marketplace version when reachable. Git checkouts are compared with their configured upstream; when a clean fast-forward update is possible, the script runs it automatically, then stops because the current Python process and Codex session cannot hot-refresh already loaded skill instructions. Packaged Codex plugin installs read `.codex-plugin/plugin.json`; if Codex already installed a newer plugin but this session still runs an older skill cache, the script must stop and tell the member to open or restart the Codex session. Do not continue generating incoming packages with a stale plugin or stale session skill cache.

Before daily, weekly, patch, or supplement package generation, the skill must confirm the running plugin, installed plugin cache, session skill cache, and remote plugin version are compatible. If the latest version cannot be confirmed, stop instead of generating a package. Every generated package must write source evidence with `plugin_name=android-framework-ops`, current `plugin_version`, current `skill_version`, `plugin_installation`, `plugin_commit` when available, `installed_plugin_version`, `remote_plugin_version`, `skill_cache_version`, and a `plugin_version_check` object containing check time, result, blocking status, message, and auto-update result. Admin-side local promotion uses this evidence to distinguish plugin not updated, session cache not refreshed, old package no longer compatible, and missing version evidence; historical package handling must use the shared source version compatibility matrix instead of requiring `plugin_version` or `skill_version` to equal the latest plugin at processing time. The server upload entrypoint only receives and stores the package on the intake branch. Strict doctor fails when the configured knowledge repository worktree is missing or not a Git repository, because member-side search needs that single repository to be present.

## Configuration

Configuration is loaded from low to high priority:

1. Built-in defaults.
2. This skill's `config.toml`.
3. `$CODEX_HOME/android-knowledge-intake.toml`.
4. `$CODEX_HOME/report/config.toml`.
5. The current repository's nearest `.codex/report.toml`.
6. Environment variables such as `CODEX_REPORT_PROFILE`, `CODEX_REPORT_MEMBER_ALIAS`, `CODEX_REPORT_MEMBER_NAME`, `CODEX_REPORT_SUBMISSION_METHOD`, `CODEX_REPORT_SUBMISSION_SSH_HOST`, `CODEX_REPORT_SUBMISSION_COMMAND`, and `CODEX_REPORT_KNOWLEDGE_REPO_WORKTREE`.

Recommended profile config:

```toml
default_profile = "member_alias"

[submission]
method = "ssh"
ssh_host = "test35"
command = "/home/test35/work/akbs/database-intake-worktree/scripts/akbs-submit"

[knowledge]
repo_url = "test35:/home/test35/work/akbs/knowledge.git"

incoming_schema_version = "1"

[paths]
codex_home = "$CODEX_HOME"
out_dir = "$CODEX_HOME/artifacts/android-knowledge-intake"

[profiles.member_alias]
member_alias = "member_alias"
member_name = "成员姓名"
role = "member"
allowed_modes = ["daily", "weekly", "patch"]
knowledge_repo_worktree = "$CODEX_HOME/worktrees/knowledge"

[profiles.admin_alias]
member_alias = "admin_alias"
member_name = "链路测试"
role = "admin"
allowed_modes = ["patch"]
knowledge_repo_worktree = "$CODEX_HOME/worktrees/knowledge"
```

`allowed_modes` is enforced before prepare/upload/submit. For non-member protocol profiles, `daily` and `weekly` must fail.

## Protocol

Read `references/incoming-package-protocol.md` when changing package generation, upload behavior, or admin-side local promotion failures.

Read `references/patch-package-status-rules.md` before deciding whether a patch package should stay local/report-only, be regenerated, or be uploaded as `validated`.

Read `references/android-framework-patch-rules.md` before generating patch readmes or validating Android Framework patch content.
