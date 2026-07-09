---
name: android-daily-report-intake
description: "Use when generating, replacing, checking, or submitting a member personal daily report package through AKBS incoming. Do not use for weekly reports, patch packages, administrator summaries, or knowledge curation decisions."
---

# Android Daily Report Intake

Use this member-facing skill for personal 日报包（daily report package） work. It answers one question: 今天干了什么、怎么干的、结果是什么.

This skill is an entrypoint, not a separate upload implementation. It routes to the shared member intake kernel in `android-knowledge-intake/scripts/android_knowledge_intake.py` with `daily` mode, so member identity, server submission, manifest protocol, replacement metadata, plugin version gate, session cache gate, duplicate guard, and local validation remain shared with weekly and patch intake.

## Boundary

- Owns personal daily generation, `reports/daily.md`, `materials/display/report_view.json`, daily date rules, duplicate daily replacement, and daily submission.
- Does not generate weekly reports, patch packages, administrator summaries, curation decisions, database writes, knowledge repository writes, or UI changes.
- Daily reports are archive material. They do not become knowledge repository materialization candidates.

## Report Model

Generate `reports/daily.md` with the Codex office daily template:

- 今日概况
- 今日工作
- 明日重点

Generate the same-source UI read model at `materials/display/report_view.json`. Required daily payload fields include `schema=akbs-report-view-human-v1`, `report_type=daily`, `report_date`, `display_date`, `material_name`, `material_summary`, and `projects[]`. Each project row contains `project`, `customer`, `today_topic`, `current_result`, `work_items[]`, and `tomorrow_focus[]`.

Daily card identity is not the date. `material_name` must be project + customer, such as `TVE1086U（青鸾云）`; multiple projects use `、` and keep each project paired with its own customer. `material_summary` must be a short daily topic summary, such as `TVE1086U：今日处理锁屏鼠标位置刷新、云电脑崩溃排查。`. Do not emit legacy `display_title`, `ui_card`, `one_line_summary`, top-level `work_items`, `risks`, or `outputs`.

Daily project rows must include both a recognized company project name and a customer name. The member can provide this in natural language as `TVE1086U 青鸾云，帮我生成日报并提交`; parse it as project `TVE1086U` and customer `青鸾云`. If either value is missing, generate the package with `需成员补充项目名` or `需成员补充客户名` so the member can edit it, but local submit must stop until both values are present.

Before running `--prepare`, `--upload`, or `--submit-latest`, check the current member request and visible conversation context for a recognized project + customer pair. If Codex cannot find both values, do not run the command yet. Reply in the conversation:

```text
缺少项目名和客户名，请补充，例如：TVE1086U 青鸾云。
```

Do not put raw commands, plugin cache paths, Codex session names, JSON fragments, shell output, package keys, case ids, or source paths into UI display fields. If evidence is missing, write clear human text such as `需补充`, not fabricated facts.

## Commands

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --prepare --replace-daily-run-id <old_run_id>
```

Future dates are blocked. Past dates are late submissions and are allowed. If an ordinary daily package for the same member and date already exists, stop unless the member explicitly replaces it.
