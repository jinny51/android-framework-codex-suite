---
name: android-weekly-report-intake
description: "Use when generating, replacing, checking, or submitting a member personal weekly report package through AKBS incoming. Do not use for daily reports, patch packages, administrator summaries, or knowledge curation decisions."
---

# Android Weekly Report Intake

Use this member-facing skill for personal 周报包（weekly report package） work. It answers one question: 这一周整体推进得怎么样.

This skill is an entrypoint, not a separate upload implementation. It routes to the shared member intake kernel in `android-knowledge-intake/scripts/android_knowledge_intake.py` with `weekly` mode, so member identity, server submission, manifest protocol, replacement metadata, plugin version gate, session cache gate, duplicate guard, and local validation remain shared with daily and patch intake.

## Boundary

- Owns personal weekly generation, `reports/weekly.md`, `materials/display/report_view.json`, weekly period rules, duplicate weekly replacement, and weekly submission.
- Does not generate daily reports, patch packages, administrator summaries, curation decisions, database writes, knowledge repository writes, or UI changes.
- Weekly reports are progress archives only. They do not become knowledge repository materialization candidates.

## Report Model

Daily reports record what happened today, how the member handled it, and the
current result. Weekly reports do not repeat daily execution details. They
summarize the week around project total ledgers that the member can correct
before uploading.

Generate `reports/weekly.md` with this required structure:

- 本周概况
- 项目详情
  - 基本信息
  - 本周进展
  - 本周重点说明
  - 风险与依赖
- 下周计划

Each project section must preserve:

- 项目名称
- 客户名称；if not proven, write `需成员补充客户名` and block local submit until corrected
- 来源类型：定制 / Buglist / 混合 / 临时支持
- 来源说明：需求单、Buglist、客户、测试、项目经理、临时安排等
- 接到文档时间 and 已持续时间; if not proven, write `需成员确认`
- 需求结构：定制需求、移植适配、Bug、BSP、其他、合计
- 上周一剩余、本周完成、当前剩余；混合项目要按定制 / Bug / BSP 等分类说明
- 本周完成事项、当前剩余事项、本周重点说明
- 风险或依赖
- 下周计划

Every formal weekly item should preserve both dimensions when available: 需求来源地（项目经理、上级、客户、测试、禅道） and 需求种类（需求清单、Buglist）. Work without a formal source should stay as 临时工作 / 内部优化 instead of being mixed into formal requirement or Buglist statistics.

Generate the same-source UI read model at `materials/display/report_view.json`. Required weekly payload fields include `report_type=weekly`, `week_range`, `display_date`, `display_title`, `one_line_summary`, `project_ledgers[]`, `weekly_progress_summary`, `weekly_detail_sections[]`, `project_overview[]`, `source_lists[]`, `source_category_stats[]`, `requirement_origin`, `requirement_list_type`, `item_statistics[]`, `completed_items[]`, `in_progress_items[]`, `remaining_items[]`, `risks[]`, `patch_outputs[]`, `delivery_verifications[]`, and `next_week_plan[]`.

`project_ledgers[]` is the structured view of the member's own weekly project
ledger. Each project ledger must include both a recognized company project name
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

## Commands

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare --replace-weekly-run-id <old_run_id>
```

Future periods are blocked. Past periods are late submissions and are allowed. If an ordinary weekly package for the same member and week exists, stop unless the member explicitly replaces it.
