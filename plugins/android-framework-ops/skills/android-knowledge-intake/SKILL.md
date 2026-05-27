---
name: android-knowledge-intake
description: Generate, review, and submit member-side Codex incoming packages into the team knowledge repository. Use when asked about 个人日报、个人周报、日报周报提交、管理员补丁归档、工作包、incoming、patch 归档、知识库入库 or report automation.
---

# Android Knowledge Intake

Use this skill for member-side knowledge intake automation and maintainer patch contribution. The skill does not write final `daily/`, `weekly/`, `patches/`, or `index/` directories. It creates a local pending incoming package first, then submits that package to `incoming/YYYYMMDD/member_alias/run_id/` in the team knowledge Git repository.

The member-side Codex agent is the knowledge producer. It should collect session context, git diff, patch diff, build results, verification records, and optional human notes, then generate incoming. The server validates, archives, indexes, and renders; it does not perform heavy AI inference.

Ordinary members use `daily` and `weekly`. The maintainer alias `jinny` uses `patch` only when manually contributing valuable patches; it must not generate daily or weekly reports for that maintainer flow.

Use configuration profiles for identity. Global config stores server/path defaults; each `[profiles.<name>]` stores one member identity, worktree, git author, role, allowed modes, and optional test behavior. Prefer explicit `--profile <name>` in automations so a daily run cannot accidentally use the maintainer identity.

Synthetic profiles are for protocol and server testing only. Set `synthetic_data = true` for that temporary profile. In synthetic mode, `daily` and `weekly` generate random synthetic work items instead of reading real Codex sessions or source changes; `patch` can generate a synthetic patch when no `--patch` is provided.

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

Prepare a maintainer patch contribution without generating a report:

```bash
python3 "scripts/android_knowledge_intake.py" --profile jinny patch --prepare --patch /path/to/jinny001-feature@framework.patch --project "Android Framework" --summary "功能补丁摘要" --status validated
```

When the patch was packaged by `android-framework-patch-capture`, submit the capture package directory so verification and pre-change search evidence are preserved:

```bash
python3 "scripts/android_knowledge_intake.py" --profile jinny patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --project "Android Framework" --summary "功能补丁摘要" --status validated
```

Submit the latest prepared patch package:

```bash
python3 "scripts/android_knowledge_intake.py" --profile jinny patch --submit-latest
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

Maintainer patch contribution is manual by default. Use it when a patch is worth entering the team knowledge base but should not create personal daily or weekly output.

Prefer `--patch-package` for Framework changes packaged by `android-framework-patch-capture`; it carries patch, readme, verification evidence, and pre-change knowledge search evidence together. Use `--patch` only for legacy standalone patch files.

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

incoming_schema_version = "2.0"

[paths]
codex_home = "$CODEX_HOME"
out_dir = "$CODEX_HOME/artifacts/android-knowledge-intake"

[profiles.member_alias]
member_alias = "member_alias"
member_name = "成员姓名"
role = "member"
allowed_modes = ["daily", "weekly"]
repo_worktree = "$CODEX_HOME/worktrees/knowledge-member_alias"

[profiles.jinny]
member_alias = "jinny"
member_name = "吴金雨"
role = "maintainer"
allowed_modes = ["patch"]
repo_worktree = "$CODEX_HOME/worktrees/knowledge-jinny"
```

`allowed_modes` is enforced before prepare/upload/submit. For `jinny`, `daily` and `weekly` must fail.

## Protocol

Read `references/incoming-package-protocol.md` when changing package generation or debugging server validation failures.

Read `references/patch-maturity-rules.md` before deciding whether a patch should be omitted, uploaded as `draft`, or uploaded as `validated`.

Read `references/android-framework-patch-rules.md` before generating patch readmes or validating Android Framework patch content.
