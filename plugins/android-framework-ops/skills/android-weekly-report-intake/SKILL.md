---
name: android-weekly-report-intake
description: "Use when generating, replacing, checking, or submitting a member personal weekly report package through AKBS incoming. Do not use for daily reports, patch packages, administrator summaries, or knowledge curation decisions."
---

# Android Weekly Report Intake

Use this member-facing skill for personal 周报包（weekly report package） work. It answers one question: 这一周完成多少、还剩多少、风险和依赖是什么.

This skill is an entrypoint, not a separate upload implementation. It routes to the shared member intake kernel in `android-knowledge-intake/scripts/android_knowledge_intake.py` with `weekly` mode, so member identity, server submission, manifest protocol, replacement metadata, plugin version gate, session cache gate, duplicate guard, and local validation remain shared with daily and patch intake.

## Boundary

- Owns personal weekly generation, `reports/weekly.md`, `materials/display/report_view.json`, weekly period rules, duplicate weekly replacement, and weekly submission.
- Does not generate daily reports, patch packages, administrator summaries, curation decisions, database writes, knowledge repository writes, or UI changes.
- Weekly reports are progress archives only. They do not become knowledge repository materialization candidates.

## Report Model

Daily reports record what happened today, how the member handled it, and the
current result. Weekly reports do not repeat daily execution details. They
summarize the week around project progress: completed count, remaining count,
risks, dependencies, and next-week closure plan.

Generate `reports/weekly.md` with this required structure:

- 本周概况
- 项目详情
  - 本周完成
  - 当前剩余
  - 风险 / 依赖
- 下周计划

The weekly Markdown baseline is the project block format:

```markdown
## 一、本周概况

### TVE1086U 青鸾云

本周围绕 TVE1086U 青鸾云 项目推进：完成系统接口联调。

- 接到文档时间：2026-06-18
- 来源说明：客户需求文档
- 需求类型：混合
- 需求结构：18 项（定制 8、Bug 8、BSP 2）
- 本周完成：5 项（定制 4、Bug 1）
- 当前剩余：3 项（定制 3、Bug 0）
- 预计完成：下周完成整体收敛
```

For multiple projects, repeat the same block per project. Do not use a large
overview table in `本周概况`.

Generate the same-source UI read model at `materials/display/report_view.json`. Required weekly payload fields include `schema=akbs-report-view-human-v1`, `report_type=weekly`, `week_range`, `display_date`, `material_name`, `material_summary`, and `projects[]`. Each project row contains `project`, `customer`, `week_summary`, `received_date`, `source`, `requirement_type`, `requirement_structure`, `completed_this_week`, `remaining`, `expected_finish`, `completed_items[]`, `remaining_items[]`, `risks[]`, `dependencies[]`, and `next_week_plan[]`.

Weekly card identity is not the week range. `material_name` must be project +
customer, such as `TVE1086U（青鸾云）`; multiple projects must keep each project
paired with its own customer. `material_summary` must summarize each project's
weekly completed count, remaining count, and risk/dependency state. The current read model emits `material_name`, `material_summary`, and `projects`; it does not emit `display_title`, `ui_card`, `one_line_summary`, `project_ledgers`, `weekly_progress_summary`, or `weekly_detail_sections`.

Each project row must include both a recognized company project name
and a customer name. The member can provide this in natural language as
`TVE1086U 青鸾云，本周主要推进...`; parse it as project `TVE1086U` and
customer `青鸾云`. If either value is missing, generate the package with
`需成员补充项目名` or `需成员补充客户名` so the member can edit it, but local
submit must stop until both values are present. Members may manually correct the
Markdown before upload, but the generated `report_view.json` must remain the
same-source structured view of that report content. Any management-side
aggregation happens outside the member workflow and should not be exposed as a
member responsibility.

Before running `--prepare`, `--upload`, or `--submit-latest`, check the current
member request and visible conversation context for a recognized project +
customer pair. If Codex cannot find both values, do not run the command yet.
Reply in the conversation:

```text
缺少项目名和客户名，请补充，例如：TVE1086U 青鸾云。
```

The weekly display date is the last workday of the period. A late weekly submission still displays the weekly period date, not the upload day.

The member's explicit request to generate this weekly report authorizes only this run's derived week window and selected derived fields. Pass `--session-consent --session-field work_summary` for the minimum report input. Add `project_hint`, `command_summary`, or `patch_discovery` only when the request needs them; `patch_discovery` requires `project_hint`. If there is no explicit current-run request, stop before session read, package creation, and HTTP. Do not reuse consent from a previous run or recurring automation.

## Commands

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --session-consent --session-field work_summary --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --session-consent --session-field work_summary --prepare --replace-weekly-run-id <old_run_id>
```

Future periods are blocked. Past periods are late submissions and are allowed. If an ordinary weekly package for the same member and week exists, stop unless the member explicitly replaces it.
