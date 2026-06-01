# Knowledge Search Contract

## Data Sources

Search reads generated knowledge indexes from a knowledge repository worktree:

```text
index/
├── case-index.jsonl
├── variant-index.jsonl
├── symbol-index.jsonl
├── search-docs.jsonl
└── evidence-index.jsonl
```

Current rebuilt repositories are case/variant first. `case-index.jsonl` and `variant-index.jsonl` are the primary search sources. Older `knowledge.sqlite`, `patch-index.jsonl`, and `report-index.jsonl` are still readable as fallback formats for older local test data.

## Result Types

- `case`: primary Android Framework problem, requirement, or engineering scenario.
- `variant`: one implementation for a platform, Android version, project, branch, source tree, repo path, patch list, reports, and verification status.
- `patch`: archived patch assets, readme path, status hints, modified files, modules, search anchors, patch-derived explanation, validation notes, and rollback hint.
- `report`: member daily or weekly report entries and report item summaries.
- `symbol`: reverse index from modified files, SystemProperties, Settings keys, string/resource keys, FrameworkLog keys, modules, and patch-derived anchors to patch IDs.
- `event`: archived records such as `framework_change`, `daily_trace`, or `weekly_trace`, including member, date, project, platform, and maturity when applicable.
- `evidence`: evidence records such as source metadata, changed files, patch diff facts, patch problem explanation, risk surface, build result, device/equivalent verification, search-before-change, and package checks.

## Judgment Boundary

The search result is evidence, not a final reuse decision.

Do not treat these fields as absolute truth:

- `status`
- `reusable`
- platform labels
- author notes
- validation status
- maturity
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
- patch problem keyword from old patch analysis

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
