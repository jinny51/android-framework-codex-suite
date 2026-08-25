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
- 重点说明
- 依赖 / 需协调
- 明日重点

Each `今日工作` item contains `做了什么`, `怎么做的`, `结果`, and `状态`.
`状态` is required and must be exactly one of `已完成`, `处理中`, `待验证`,
or `阻塞`. Split independent work items even when they occurred in one Codex
session. Merge repeated handling of the same item across sessions, keep the
latest result/status, and deduplicate identical process evidence. Describe the
actual handling method from authorized messages, sanitized command categories,
and outcomes; never use a fixed sentence that merely says the report was
organized from Codex records.

In `reports/daily.md`, bold the project name every time it appears, including
headings and body text. Bold only the project name, for example
`**TVE1091U** AOC 福建移动高清`; keep the customer chain unbolded. This is a
Markdown presentation rule only. Keep project and customer values in
`report_view.json` as plain text without Markdown markers.

Generate the same-source UI read model at `materials/display/report_view.json`. Required daily payload fields include `schema=akbs-report-view-human-v1`, `report_type=daily`, `report_date`, `display_date`, `material_name`, `material_summary`, `projects[]`, `documents[]`, and `standalone_work[]`; at least one array must be non-empty. Every project-bound row belongs in `projects[]` and contains `project`, direct `customer`, optional `downstream_customer` (客户的客户), `today_topic`, `current_result`, `work_items[]`, `key_points[]`, `dependencies[]`, and `tomorrow_focus[]`. Project work uses `Patch`, `App`, `GMS`, `Doc`, or `Other`. Only a non-project document belongs in `documents[]` with `work_type=Doc` and `document_name`. A non-project, non-document activity belongs in `standalone_work[]` with `work_type=Other` and `work_name`. Historical `Document` remains readable as `Doc`. Every work item contains `name`, `did[]`, `how[]`, `result`, and fixed-enum `status`.

Every daily scope, including non-project Doc and Other, carries `key_points[]`
and `dependencies[]`. `key_points` records explicit project news, scope
changes, or a key difficulty overcome today. `dependencies` records explicit
external dependencies or coordination needs. Both arrays are required in the
normalized report but may be empty; an empty array must not block generation or
submission. Do not invent either field from an ordinary unfinished item. In
Markdown, render `无。` when all scopes are empty for that section.

Each daily row is one work scope. The five visible categories are exactly
`Patch`, `App`, `GMS`, `Doc`, and `Other`. Patch and App keep their existing
meaning; App requires `app_name`. GMS is always project-bound. A project-bound
Doc or Other row also stays in `projects[]`. Only a non-project Doc uses
`documents[]`; only a non-project Other uses `standalone_work[]`. A shared GMS
ATS environment with no customer project is `Other` standalone work, not GMS.
Resolve it in this order:

1. An explicit type or App name stated by the member in the current development
   context wins.
2. Otherwise use high-confidence development evidence: Android system source or
   Framework module paths, changed files, patch artifacts, standalone App
   modules, Gradle application builds, and APK/AAB outputs.
3. Explicit document actions such as 编写、整理、更新 or 完善 a named document
   resolve to `Doc` when no project development scope conflicts.
4. Explicit GMS testing or certification evidence resolves to project-bound
   `GMS`; explicit non-project work outside documentation resolves to `Other`.
5. Never decide from vague work-item wording alone. If evidence conflicts, App
   is clear but its name is not, or a standalone category is clear but its name is not, ask
   only for the unresolved fact.

SystemUI, Launcher, Settings, framework services, and other Android system-tree
changes are `Patch`, even when the module itself is an Android application.
`App` means a separately delivered application or demo. Separate sessions with
consistent evidence may automatically split the same project into one Patch and
multiple named Apps. A mixed session is not split unless each item can be bound
to a scope without guessing. The same Patch or same App must not be repeated. A
scope with any `处理中`, `待验证`, or `阻塞` item must have a non-empty
`tomorrow_focus[]`. When the member explicitly says there is no next-day focus,
preserve that answer as `tomorrow_focus=["无"]`; never rewrite it to an empty
array or reject the report merely because unfinished work exists.

Run normal generation first and let the shared kernel infer scope from the
authorized evidence. Use `akbs-daily-work-facts-v2` under
`$CODEX_HOME/artifacts/android-knowledge-intake/daily-facts/` only to complete
an unresolved scope, correct an inference, preserve explicit key points or
dependencies, or make an explicit member override;
pass it with `--daily-facts`. Read
`../android-knowledge-intake/references/daily-facts-contract.md`. Explicit facts
take precedence over inferred scope. For multiple unresolved scopes under one
project, assign each work item to its scope explicitly.

Daily card identity is not the date. Project identity preserves the customer chain, such as `TVE1086U（青鸾云）` or `TVE1091U（AOC → 福建移动高清）`; non-project documents and standalone work use their concrete names. Multiple scopes use `、`. `material_summary` is a short daily progress summary. The current read model emits `material_name`, `material_summary`, `projects`, `documents`, and `standalone_work`; it does not emit `display_title`, `ui_card`, `one_line_summary`, top-level `work_items`, `risks`, or `outputs`.

Every project row, including Patch/App/GMS/Doc/Other, must include a recognized company project and direct customer. A third segment is optional and means the direct customer's customer: parse `TVE1091U AOC 福建移动高清` as project `TVE1091U`, customer `AOC`, and downstream customer `福建移动高清`. Keep `TVE1086U 青鸾云` compatible as a two-segment identity. If project or direct customer is missing, local submit must stop; never merge direct and downstream customers as aliases. Non-project `documents[]` and `standalone_work[]` rows must not carry project/customer placeholders.

Before running `--prepare`, `--upload`, or `--submit-latest`, first decide
whether the work is project-bound, a non-project document, or other non-project
work. All project-bound types require a recognized project + customer pair.
Non-project Doc requires a document name; non-project Other requires a work
name. GMS without project/customer is invalid. Only when
neither a valid project scope nor a valid standalone scope can be established should Codex stop
and reply:

```text
当前会话未关联项目，请补充项目名和客户名。
例如：TVE1086U 青鸾云
如有客户的客户：TVE1091U AOC 福建移动高清

建议后续按正确流程开展：先创建项目，再在项目下创建开发会话。

如果本次工作是独立文档整理，请改为提供具体文档名称，例如：
Doc，Android Framework Orchestrator 功能介绍文档。
```

This fallback requests only the minimum project or document identity needed by
the daily report. Do not ask for weekly fields such as project role, requirement date,
requirement source, project total, or remaining count. After the member supplies
the identity, continue daily generation.

If identity exists but the evidence still cannot resolve the scope, ask only:

```text
请确认这项工作属于 Patch、App、GMS、Doc 还是 Other；如果挂靠项目，请提供项目和客户；如果是 App，请提供 App 名称；无项目文档请提供文档名称，其他无项目工作请提供具体工作名称。
```

Do not put raw commands, plugin cache paths, Codex session names, JSON fragments, shell output, package keys, case ids, or source paths into UI display fields. If evidence is missing, write clear human text such as `需补充`, not fabricated facts.

`reports/daily.md` and `report_view.json` are deterministic views of the same
normalized facts. A render-binding evidence file covers both outputs and the
fact hash. Never repair only Markdown or only JSON; update the facts and
regenerate. `--prepare` returns failure when local validation fails,
`--submit-latest` revalidates before HTTP, and an invalid report must not be
described as successfully generated or submitted.

The member's explicit request to generate this daily report authorizes only this run's report date and selected derived fields. Pass `work_summary`, `command_summary`, `project_hint`, and `work_scope_hint` so the report can describe the work and method and derive a safe source-scope hint without retaining the path. Add `patch_discovery` only when patch artifacts are needed; it requires `project_hint`. If there is no explicit current-run request, stop before session read, package creation, and HTTP. Do not reuse consent from a previous run or recurring automation.

## Commands

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --session-consent --session-field work_summary --session-field command_summary --session-field project_hint --session-field work_scope_hint --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --session-consent --session-field work_summary --session-field command_summary --session-field project_hint --session-field work_scope_hint --daily-facts "$CODEX_HOME/artifacts/android-knowledge-intake/daily-facts/<report-date>.json" --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --session-consent --session-field work_summary --session-field command_summary --session-field project_hint --session-field work_scope_hint --prepare --replace-daily-run-id <old_run_id>
```

Future dates are blocked. Past dates are late submissions and are allowed. If an ordinary daily package for the same member and date already exists, stop unless the member explicitly replaces it.
