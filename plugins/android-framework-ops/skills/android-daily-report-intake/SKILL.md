---
name: android-daily-report-intake
description: "Use when generating, replacing, checking, or submitting a member personal daily report package through AKBS incoming. Do not use for weekly reports, patch packages, team weekly summaries, or knowledge curation decisions."
---

# Android Daily Report Intake

Use this member-facing skill for personal 日报包（daily report package） work. It answers one question: 今天干了什么.

This skill is an entrypoint, not a separate upload implementation. It routes to the shared member intake kernel in `android-knowledge-intake/scripts/android_knowledge_intake.py` with `daily` mode, so member identity, server submission, manifest protocol, replacement metadata, plugin version gate, session cache gate, duplicate guard, and local validation remain shared with weekly and patch intake.

## Boundary

- Owns personal daily generation, `reports/daily.md`, `materials/display/report_view.json`, daily date rules, duplicate daily replacement, and daily submission.
- Does not generate weekly reports, patch packages, team weekly summaries, curation decisions, database writes, knowledge repository writes, or UI changes.
- Daily reports are archive material. They do not become knowledge repository materialization candidates.

## Report Model

Generate `reports/daily.md` with the Codex office daily template:

- 今日工作概览
- 今日具体事项
- 今日阻塞 / 风险
- 今日产出
- 明日重点

Generate the same-source UI read model at `materials/display/report_view.json`. Required daily payload fields include `report_type=daily`, `report_date`, `display_title`, `one_line_summary`, `projects[]`, `work_items[]`, `risks[]`, `outputs[]`, and `tomorrow_focus[]`.

Do not put raw commands, plugin cache paths, Codex session names, JSON fragments, shell output, package keys, case ids, or source paths into UI display fields. If evidence is missing, write clear human text such as `需补充`, not fabricated facts.

## Commands

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --prepare --replace-daily-run-id <old_run_id>
```

Future dates are blocked. Past dates are late submissions and are allowed. If an ordinary daily package for the same member and date already exists, stop unless the member explicitly replaces it.

