---
name: android-knowledge-search
description: Search the team knowledge repository for reusable reports, archived patches, search anchors, validation notes, and prior Android Framework solutions. Use before re-implementing a feature, during Android Framework requirement triage, or when a user asks to find existing patches or team knowledge.
---

# Android Knowledge Search

Use this skill to search the team knowledge repository before starting new analysis or implementation. It is the read-side entry for the knowledge system: `android-knowledge-intake` and `android-framework-patch-capture` produce assets; this skill retrieves them.

This skill does not submit reports, create patches, edit source, or decide correctness by itself. It returns prior facts so Codex can judge whether a patch or report is relevant to the current requirement.

## Quick Command

```bash
python3 "scripts/android_knowledge_search.py" \
  "电源键 frameworks/base" \
  --limit 8
```

Useful variants:

```bash
# Search primary cases.
python3 "scripts/android_knowledge_search.py" \
  "通知音量 SystemUI" --type case

# Search platform/project implementations.
python3 "scripts/android_knowledge_search.py" \
  "TVE8402M VolumeDialogImpl" --type variant

# Search only patch assets.
python3 "scripts/android_knowledge_search.py" \
  "persist.sys launcher" --type patch

# Return machine-readable output for another workflow.
python3 "scripts/android_knowledge_search.py" \
  "WindowManager display" --json

# Use an explicit mounted or cloned knowledge root.
python3 "scripts/android_knowledge_search.py" \
  "PackageManager permission" --root /path/to/knowledge/worktree
```

## Source Selection

The script searches the first valid knowledge root it can find:

1. `--root <path>`
2. `CODEX_KNOWLEDGE_ROOT`
3. `CODEX_REPORT_REPO_WORKTREE`, `CODEX_REPORT_WORKTREE`, `CODEX_WORK_REPORT_REPO_WORKTREE`, or `CODEX_WORK_REPORT_WORKTREE`
4. `repo_worktree` or `worktree` from the selected profile in `$CODEX_HOME/report/config.toml`, `$CODEX_HOME/android-knowledge-search.toml`, or the nearest `.codex/report.toml`
5. current directory or its parents, when they contain current `index/*.jsonl` knowledge indexes
6. generic Codex worktrees such as `$CODEX_HOME/worktrees/knowledge`, `CODEX_DOCUMENTS/worktrees/knowledge`, or detected Windows `Documents/Codex/worktrees/knowledge`
7. common mapped server locations such as `/mnt/z/knowledge/worktree`

Pass `--refresh` only when using a local Git clone and the latest server content is required. Refresh runs `git pull --ff-only`; it skips refresh when the worktree is dirty.

## Search Discipline

When handling a new Android Framework requirement:

1. Search with feature words, affected module, likely class name, property key, Settings key, resource key, search anchor, and artifact name.
2. Read the top matching patch readme or report before deciding whether to reuse.
3. Treat `status`, `reusable`, platform, and validation fields as hints, not truth.
4. Prefer case and variant results first; then inspect related patches, reports, evidence, and symbols.
5. Compare facts: modified files, touched symbols, artifact, risk notes, build evidence, device verification, rollback path.
6. If a prior patch looks relevant, report the evidence and remaining uncertainty before applying or adapting it.

For `android-framework-change-workflow`, this is the pre-analysis search gate. Search first; if no useful result exists, continue with normal requirement analysis and implementation.

## References

Read `references/search-contract.md` before changing the script output format or integrating this skill into another workflow.
