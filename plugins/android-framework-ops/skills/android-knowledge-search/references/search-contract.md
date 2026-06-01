# Knowledge Search Contract

## Data Sources

Search reads generated knowledge indexes from a knowledge repository worktree:

```text
index/
├── knowledge.sqlite
├── patch-index.jsonl
├── report-index.jsonl
├── symbol-index.jsonl
├── knowledge-event-index.jsonl
└── evidence-index.jsonl
```

`knowledge.sqlite` is preferred because it keeps reports, patches, report items, search anchors, archived records, and evidence in one structured file. JSONL files are the fallback for read-only or partially generated repositories.

## Result Types

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
android_knowledge_search.py <query> [--root PATH] [--type all|patch|report|symbol] [--limit N] [--json] [--refresh]
```

Full type filter:

```text
--type all|patch|report|symbol|event|evidence
```

Markdown output is for humans and Codex final reports. JSON output is for other scripts or workflows.
