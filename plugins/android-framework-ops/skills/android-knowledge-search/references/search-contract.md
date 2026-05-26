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

`knowledge.sqlite` is preferred because it keeps reports, patches, report items, symbols, v2 knowledge events, and evidence in one structured file. JSONL files are the fallback for read-only or partially generated repositories.

## Result Types

- `patch`: archived patch assets, readme path, status hints, modified files, modules, symbols, patch-derived inference, validation notes, and rollback hint.
- `report`: daily, weekly, team daily, or team weekly report entries and report item summaries.
- `symbol`: reverse index from modified files, SystemProperties, Settings keys, string/resource keys, FrameworkLog keys, modules, and patch-derived symbols to patch IDs.
- `event`: v2 knowledge events such as `framework_change`, `patch_contribution`, `daily_trace`, or `weekly_trace`, including channel and quality.
- `evidence`: v2 evidence records such as source metadata, changed files, patch diff facts, patch problem inference, risk surface, build result, device/equivalent verification, search-before-change, and package checks.

## Judgment Boundary

The search result is evidence, not a final reuse decision.

Do not treat these fields as absolute truth:

- `status`
- `reusable`
- platform labels
- author notes
- validation status
- quality
- channel
- evidence result

They are useful hints. The consuming workflow must compare the current requirement with stored facts such as modified files, modules, patch-derived symbols, affected artifacts, touched keys, readme details, build evidence, device verification, inference confidence, inference basis, inference limits, and rollback notes.

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
- inferred problem keyword from old patch analysis

## Patch Inference Boundary

Historical patches may be searchable even when their old readme is weak or missing because the server can parse patch content and infer likely problem, likely solution, keywords, and risk surface.

Search output must label these as inference. A consuming workflow must not treat inferred problem or inferred solution as proof of:

- original customer requirement
- device verification
- release state
- final acceptance

Use inferred results as strong leads for reuse analysis, not as final conclusions.

## Output Contract

The CLI must support:

```text
android_knowledge_search.py <query> [--root PATH] [--type all|patch|report|symbol] [--limit N] [--json] [--refresh]
```

V2-aware type filter:

```text
--type all|patch|report|symbol|event|evidence
```

Markdown output is for humans and Codex final reports. JSON output is for other scripts or workflows.
