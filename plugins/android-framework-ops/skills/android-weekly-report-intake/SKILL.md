---
name: android-weekly-report-intake
description: "Use when generating, replacing, checking, or submitting a member personal weekly report package through AKBS incoming. Do not use for daily reports, patch packages, team weekly summaries, or knowledge curation decisions."
---

# Android Weekly Report Intake

Use this member-facing skill for personal 周报包（weekly report package） work. It answers one question: 这一周整体推进得怎么样.

This skill is an entrypoint, not a separate upload implementation. It routes to the shared member intake kernel in `android-knowledge-intake/scripts/android_knowledge_intake.py` with `weekly` mode, so member identity, server submission, manifest protocol, replacement metadata, plugin version gate, session cache gate, duplicate guard, and local validation remain shared with daily and patch intake.

## Boundary

- Owns personal weekly generation, `reports/weekly.md`, `materials/display/report_view.json`, weekly period rules, duplicate weekly replacement, and weekly submission.
- Does not generate daily reports, patch packages, team weekly summaries, curation decisions, database writes, knowledge repository writes, or UI changes.
- Weekly reports are progress archives only. They do not become knowledge repository materialization candidates.

## Report Model

Generate `reports/weekly.md` with the Codex office weekly template:

- 本周整体概览
- 本周按项目总结
- 本周重点问题与风险
- 本周 Patch 产出
- 本周验证与交付情况
- 下周重点计划

Every formal weekly item should preserve both dimensions when available: 需求来源地（项目经理、上级、客户、测试、禅道） and 需求种类（需求清单、Buglist）. Work without a formal source should stay as 临时工作 / 内部优化 instead of being mixed into formal requirement or Buglist statistics.

Generate the same-source UI read model at `materials/display/report_view.json`. Required weekly payload fields include `report_type=weekly`, `week_range`, `display_date`, `display_title`, `one_line_summary`, `project_overview[]`, `source_lists[]`, `source_category_stats[]`, `requirement_origin`, `requirement_list_type`, `item_statistics[]`, `completed_items[]`, `in_progress_items[]`, `remaining_items[]`, `risks[]`, `patch_outputs[]`, `delivery_verifications[]`, and `next_week_plan[]`.

The weekly display date is the last workday of the period. A late weekly submission still displays the weekly period date, not the upload day.

## Commands

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare --replace-weekly-run-id <old_run_id>
```

Future periods are blocked. Past periods are late submissions and are allowed. If an ordinary weekly package for the same member and week exists, stop unless the member explicitly replaces it.
