# Knowledge Search Contract

## Data Sources

Search reads generated knowledge indexes from the knowledge repository worktree:

```text
index/
├── case-index.jsonl
├── variant-index.jsonl
├── symbol-index.jsonl
├── search-docs.jsonl
└── evidence-index.jsonl
```

Current repositories are case/variant first. `case-index.jsonl` and `variant-index.jsonl` are the primary search sources. Default search loads `patches/by-id` plus generated AI indexes only. `reports/by-id`, `events/by-id`, and raw `evidence/by-id` are loaded only for explicit archive filters. It must not read residual generated SQLite or residual patch/report indexes.

Search must not automatically use the database repository or member incoming worktree. It may inspect those only when an administrator passes an explicit `--root`.

When `search-docs.jsonl` includes replacement fields, case results must preserve and display them:

```text
replacement_case_id
replacement_title
replaces_case_ids
```

These fields mean the local curation skill has marked an old case as obsolete or contradicted and linked a recommended replacement case. Search should surface the relationship as guidance, not as a final reuse decision.

Default `--type all` is the AI reuse view. It returns only `case`, `variant`, `patch`, `symbol`, and AI evidence kinds:

- `patch_diff_facts`
- `patch_problem_summary`
- `project_inference`
- `risk_surface`
- `build_result`
- `verification_result`
- `search_before_change`

Default `--type all` must not return report rows, event rows, or human/archive evidence kinds such as `source`, `work_findings`, `report_context`, or `package_check`. These archive records remain available only through explicit type filters for administrator trace-back and debugging.

## Result Types

- `case`: primary Android Framework problem, requirement, or engineering scenario.
- `variant`: one implementation for a platform, Android version, project, branch, source tree, repo path, patch list, reports, and verification status.
- `patch`: archived patch assets, readme path, status hints, modified files, modules, search anchors, patch-derived explanation, validation notes, and rollback hint.
- `report`: member daily or weekly report entries and report item summaries. Explicit filter only; not part of default AI reuse search.
- `symbol`: reverse index from modified files, SystemProperties, Settings keys, string/resource keys, FrameworkLog keys, modules, and patch-derived anchors to patch IDs.
- `event`: archived records such as `framework_change`, `daily_trace`, or `weekly_trace`, including member, date, project, platform, and package status when applicable. Explicit filter only; not part of default AI reuse search.
- `evidence`: evidence records. Default AI search includes only patch facts, patch problem explanation, project inference, risk surface, build result, device/equivalent verification, and search-before-change. Source metadata, work findings, report context, and package checks require explicit `--type evidence`.

## Judgment Boundary

The search result is evidence, not a final reuse decision.

Do not treat these fields as absolute truth:

- `status`
- `package_status`
- `reuse_hint`
- platform labels
- author notes
- validation status
- evidence result

They are useful hints. The consuming workflow must compare the current requirement with stored facts such as modified files, modules, patch-derived anchors, affected artifacts, touched keys, readme details, build evidence, device verification, explanation basis, explanation limits, and rollback notes.

## Recommended Query Terms

Use several searches when needed:

- user-facing feature words
- subsystem: `WindowManager`, `ActivityTaskManager`, `PackageManager`, `SystemUI`, `Launcher3`
- file or class name
- artifact: `services.jar`, `framework.jar`, `framework-res.apk`, `SystemUI.apk`
- system property: `persist.sys.*`
- Settings key
- resource or string key
- visible log keyword
- patch-derived problem keyword

## Patch Explanation Boundary

Historical patches may be searchable even when their old readme is weak or missing because patch content can provide problem/solution leads, keywords, and risk surface.

Human-facing search output should present these as patch problem/solution leads, not as verified facts. A consuming workflow must not treat them as proof of:

- original customer requirement
- device verification
- release state
- final acceptance

Use these leads for reuse analysis, not as final conclusions.

## Output Contract

The CLI must support:

```text
android_knowledge_search.py <query> [--root PATH] [--type all|case|variant|patch|report|symbol|event|evidence] [--limit N] [--json] [--refresh]
```

Full type filter:

```text
--type all|case|variant|patch|report|symbol|event|evidence
```

Markdown output is for humans and Codex final reports. JSON output is for other scripts or workflows.
