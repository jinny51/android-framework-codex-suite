---
name: android-knowledge-intake
description: Generate, review, and submit member-side Codex incoming packages into the team knowledge repository. Use when asked about 个人日报、个人周报、日报周报提交、Framework 修改沉淀、工作包、incoming、patch 入库、知识库入库 or report automation.
---

# Android Knowledge Intake

Use this skill for member-side knowledge intake automation. The skill does not write final reports, patches, index, or site directories. It creates a local pending incoming package first, then submits that package to `incoming/YYYYMMDD/member_alias/run_id/` in the team knowledge Git repository.

The member-side Codex agent is the knowledge producer. It should collect session context, git activity, patch diff, build results, verification records, failed paths, blocked paths, and optional human notes, then generate incoming. The knowledge repository server validates, archives, indexes, and renders; it does not perform heavy AI reasoning.

Ordinary members use `daily` and `weekly` automation as the baseline and use `patch` when a Framework change should be converted into a `framework_change` incoming package. Administrator profiles are for occasional manual patch contribution only; they must not generate personal daily or weekly reports.

Default policy: preserve automatically first, rank by maturity later. Lack of manual confirmation is not a reason to drop knowledge. Daily and weekly traces must preserve `work_findings`; Framework changes use `maturity` values `validated`, `candidate`, `draft`, `failed`, or `blocked`.

Use configuration profiles for identity. Global config stores server/path defaults; each `[profiles.<name>]` stores one member identity, worktree, git author, role, allowed modes, and optional test behavior. Prefer explicit `--profile <name>` in automations so a daily run cannot accidentally use an administrator identity.

Framework change incoming must carry deterministic merge anchors. Patch content `sha1` is emitted in `patch_diff_facts`; `related_report_run_ids` is used only when the daily/weekly run id is explicitly known. Do not create fuzzy report links on the member side.

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

When the patch was packaged by `android-framework-patch-capture`, submit the capture package directory so verification and pre-change search evidence are preserved:

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --project "TVE8402M" --summary "功能补丁摘要" --status validated
```

Submit the latest prepared patch package:

```bash
python3 "scripts/android_knowledge_intake.py" --profile admin_alias patch --submit-latest
```

Check configuration:

```bash
python3 "scripts/android_knowledge_intake.py" doctor
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> doctor
```

## Automation

Recommended member-side automations:

- 21:00 daily prepare: generate pending package for member review.
- 22:30 daily submit: submit the latest pending package.
- Saturday 22:00 weekly prepare.
- Saturday 22:30 weekly submit.

Framework change submission is automatic when the member-side Codex can identify a clean change, enough evidence, and a safe maturity level. If validation evidence is missing, submit as `candidate` or `draft`; do not discard the work. Maintainer patch contribution remains manual by default.

Prefer `--patch-package` for Framework changes packaged by `android-framework-patch-capture`; it carries patch, readme, verification evidence, and pre-change knowledge search evidence together. Use `--patch` only when directly packaging a single patch file into the current incoming protocol.

For successful automation runs, launch `scripts/archive_automation_runs.py` with `setsid -f` and a short delay so the automation conversation is archived after Codex marks the run complete.

## Configuration

Configuration is loaded from low to high priority:

1. Built-in defaults.
2. This skill's `config.toml`.
3. `$CODEX_HOME/android-knowledge-intake.toml`.
4. `$CODEX_HOME/report/config.toml`.
5. The current repository's nearest `.codex/report.toml`.
6. Environment variables such as `CODEX_REPORT_PROFILE`, `CODEX_REPORT_MEMBER_ALIAS`, `CODEX_REPORT_MEMBER_NAME`, `CODEX_REPORT_REPO_URL`, `CODEX_REPORT_REPO_WORKTREE`.

Recommended profile config:

```toml
default_profile = "member_alias"

[server]
repo_url = "test35:/home/test35/work/knowledge/remote.git"

incoming_schema_version = "1"

[paths]
codex_home = "$CODEX_HOME"
out_dir = "$CODEX_HOME/artifacts/android-knowledge-intake"

[profiles.member_alias]
member_alias = "member_alias"
member_name = "成员姓名"
role = "member"
allowed_modes = ["daily", "weekly", "patch"]
repo_worktree = "$CODEX_HOME/worktrees/knowledge-member_alias"

[profiles.admin_alias]
member_alias = "admin_alias"
member_name = "管理员姓名"
role = "admin"
allowed_modes = ["patch"]
repo_worktree = "$CODEX_HOME/worktrees/knowledge-admin_alias"
```

`allowed_modes` is enforced before prepare/upload/submit. For administrator profiles, `daily` and `weekly` must fail.

## Protocol

Read `references/incoming-package-protocol.md` when changing package generation or debugging server validation failures.

Read `references/patch-maturity-rules.md` before deciding whether a patch should be omitted, uploaded as `draft`, or uploaded as `validated`.

Read `references/android-framework-patch-rules.md` before generating patch readmes or validating Android Framework patch content.
