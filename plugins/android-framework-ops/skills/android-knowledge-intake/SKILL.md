---
name: android-knowledge-intake
description: Use when handling 个人日报、个人周报、日报周报提交、成员首次启用、插件更新、Framework 修改材料包、工作包、incoming, patch package, or report automation through member-side incoming packages and the server submission channel. Do not use for knowledge curation decisions.
---

# Android Knowledge Intake

Use this skill for member-side incoming package automation. The skill does not write final knowledge reports, curated patches, index, or site directories. It creates a local pending incoming package first, then sends that package through the server submission channel. The member-side skill does not clone, pull, directly search, or push the database repository; member viewing UI is a separate server-side database view.

The member-side Codex agent is the material producer. It should collect session context, git activity, patch diff, build results, verification records, failed paths, blocked paths, and optional human notes, then generate incoming. The server receives the package, performs deterministic validation, stores it in the database repository, and commits as the server-side authority. Knowledge repository content and curation decisions are produced later by the user's local `android-knowledge-curation-maintainer` skill and AI knowledge loop.

Ordinary members use `daily` and `weekly` modes to generate member-level incoming packages on schedule, and use `patch` when a Framework change should be converted into a `framework_change` incoming package. Weekly packages are progress archives only; they do not become knowledge repository materialization candidates. Non-member profiles are only for protocol and server-chain tests; they must not be confused with the user's local `android-knowledge-curation-maintainer` skill.

Default policy: preserve incoming materials automatically first, rank by package status later. Lack of manual confirmation is not a reason to drop daily or patch evidence. Daily traces must preserve `work_findings`; weekly traces preserve progress summaries for database archive and member view only. Framework changes use `package_status` values `validated`, `candidate`, `draft`, `failed`, or `blocked`. These values are not curation decisions.

Use configuration profiles for identity. Global config stores the submission channel and knowledge repository defaults; each `[profiles.<name>]` stores one member identity, knowledge worktree, git author, role, allowed modes, and optional test behavior. Prefer explicit `--profile <name>` in automations so a daily incoming run cannot accidentally use an administrator identity.

Framework change incoming must carry deterministic merge anchors. Patch content `sha1` is emitted in `patch_diff_facts`; `related_report_run_ids` is used only when the daily or weekly run id is explicitly known. A weekly run id is provenance only and does not make the weekly package a knowledge materialization candidate. Do not create fuzzy report links on the member side.

Daily and patch packages consume member-side search usage evidence written by `android-knowledge-search`. Daily packages include same-day search evidence when present. Patch packages prefer explicit capture evidence from `android-framework-patch-capture`, then fall back to same-day member search usage records. These values are development evidence, not curation decisions.

Project metadata is part of the knowledge loop, not a cosmetic UI field. Daily packages must write traceable project inference evidence when the day's context contains a TVE/TVA/TVI project model. Patch packages must prefer explicit `--project` or capture package project evidence, and when a patch is related to a known daily package, `--related-report-run-id` lets the patch inherit that daily project context. Generic labels such as `android16`, `mtk16`, `Camera2`, source folder names, platform, or Android version must not be written as project names. If no traceable project exists, keep `project=unknown` and record the checked sources and limits in `project_inference`; do not invent a project to make the UI look complete.

If a daily package contains multiple candidates that share one base model, such as `TVE1067M1` and `TVE1067M1_H031`, write the shared base model `TVE1067M1` and keep the complete candidates in `project_inference`. Do not truncate it to `TVE1067M`. If candidates have different base models, keep `project=unknown` and preserve the ambiguity.

Platform and Android version metadata are also knowledge applicability boundaries. Framework change packages may only write `platform=mtk`, `platform=rk`, `platform=unisoc`, or `platform=unknown`. Patch filenames or capture packages with `sprd` or `u` aliases normalize to `unisoc`; generic prefixes such as `android14` or `app15` must never become `platform=android` or `platform=app`. If only the numeric Android version is traceable, keep `platform=unknown`; local curation must treat that as an evidence gap instead of materializing high-confidence knowledge.

A patch package can still be preserved when project, platform, or Android version metadata is incomplete, but it must not stay `validated`. Even with PASS verification, if the project remains `unknown`, the platform is `unknown`, or the Android version is `unknown`, downgrade the package to `candidate`, clear direct reuse hints, and record the metadata reason in patch diff facts for later curation.

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

Prepare a Framework change incoming package without generating a report:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch /path/to/rk14-frameworks-base@feature.patch --project "TVE8402M" --summary "功能补丁摘要" --status candidate
```

Attach a known daily or weekly run explicitly:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --summary "功能补丁摘要" --status candidate --related-report-run-id 20260601-210000-daily
```

Use the related daily run id whenever the patch belongs to a work item already described in that day's report. Without an explicit project or related daily context, a patch package may remain `project=unknown`; the server will preserve it, but local curation must treat the missing project as a metadata/evidence gap.

When the patch was packaged by `android-framework-patch-capture`, submit the capture package directory so build, verification, and pre-change search evidence are preserved:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --project "TVE8402M" --summary "功能补丁摘要" --status validated
```

When member view UI shows a previous patch package needs evidence, do not create a fourth package type. Regenerate or resubmit a normal `framework_change` patch package with the missing evidence and link it to the original incoming package:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare \
  --patch-package /path/to/.codex/patch-packages/20260612-171820-feature \
  --project "TVE1234A" \
  --summary "功能补丁摘要" \
  --status validated \
  --supplement-for-package-key 20260612/lincong/20260612-172836-patch \
  --supplement-reason "补充项目（project）证据"
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

Prefer `--patch-package` for Framework changes packaged by `android-framework-patch-capture`; it carries one feature README, one or more repository-level patches, build evidence, verification evidence, and pre-change knowledge search evidence together. Use `--patch` only when directly packaging a standalone patch file into the current incoming protocol.

If member view UI reports 需补证据（needs_evidence）, the member-side action is usually to rerun patch capture/intake with the missing evidence, then pass `--supplement-for-package-key <date/member/run-id>` and `--supplement-reason <reason>` during patch prepare or upload. This creates another normal补丁包（patch package）with `evidence_supplement` evidence. It does not create a fourth incoming type and does not let members decide curation.

For successful automation runs, launch `scripts/archive_automation_runs.py` with `setsid -f` and a short delay so the automation conversation is archived after Codex marks the run complete.

## Member First Setup

When a member needs first-time setup on the current double-repository chain, read `references/member-migration-prompt.md` and give the member the copy-paste prompt. The prompt makes Codex perform 插件更新（plugin update）, 新配置（new configuration）, 服务器上传入口（server upload endpoint） and 知识库仓库（knowledge repository） clone/update checks, and `doctor --strict --check-remote` before any daily, weekly, or patch generation. Members clone only the knowledge repository; they never clone the database repository.

The intake script also runs a plugin freshness check before `daily`, `weekly`, or `patch` `--prepare`, `--upload`, and `--submit-latest`. If it can prove the installed/source plugin checkout is behind its remote, it must stop the run and return an update command. Do not continue generating incoming packages with a stale plugin. Strict doctor fails when the configured knowledge repository worktree is missing or not a Git repository, because member-side search needs that single repository to be present.

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
command = "/home/test35/work/knowledge/database-worktree/scripts/knowledge-submit"

[knowledge]
repo_url = "test35:/home/test35/work/knowledge/knowledge.git"

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

Read `references/incoming-package-protocol.md` when changing package generation or debugging server validation failures.

Read `references/patch-package-status-rules.md` before deciding whether a patch package should be omitted, uploaded as `draft`, or uploaded as `validated`.

Read `references/android-framework-patch-rules.md` before generating patch readmes or validating Android Framework patch content.
