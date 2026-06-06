---
name: android-knowledge-search
description: Search the team knowledge repository for reusable cases, platform variants, archived patches, search anchors, validation notes, and prior Android Framework solutions. Use before re-implementing a feature, during Android Framework requirement triage, or when a user asks to find existing patches or team knowledge.
---

# Android Knowledge Search

Use this skill to search the team knowledge repository before starting new analysis or implementation. It is the member-side search entry for the knowledge system: `android-knowledge-intake` and `android-framework-patch-capture` submit materials through the server submission channel, and the user's local `android-knowledge-curation-maintainer` skill promotes AI-usable knowledge into the knowledge repository for this skill to retrieve.

This skill does not submit reports, create patches, edit source, or decide correctness by itself. It returns prior facts so Codex can judge whether an existing case, variant, patch, symbol, or validation fact is relevant to the current requirement.

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

# Use an explicit mounted or cloned knowledge repository root.
python3 "scripts/android_knowledge_search.py" \
  "PackageManager permission" --root /path/to/knowledge-worktree
```

## Source Selection

The script searches the first valid knowledge repository root it can find:

1. `--root <path>`
2. `CODEX_KNOWLEDGE_ROOT`
3. `CODEX_KNOWLEDGE_REPO_WORKTREE` or `CODEX_REPORT_KNOWLEDGE_REPO_WORKTREE`
4. `knowledge_repo_worktree` or `knowledge_worktree` from the selected profile in `$CODEX_HOME/report/config.toml`, `$CODEX_HOME/android-knowledge-search.toml`, or the nearest `.codex/report.toml`
5. current directory or its parents, when they contain current `index/*.jsonl` knowledge indexes
6. generic Codex worktrees such as `$CODEX_HOME/worktrees/knowledge` or detected Windows `Documents/Codex/worktrees/knowledge`
7. common mapped server locations such as `/mnt/z/knowledge/knowledge-worktree`

The search skill must not automatically read the database repository. If a local maintainer needs to inspect database internals, pass that path explicitly with `--root` and understand that it is not the normal member reuse path.

Pass `--refresh` only when using a local Git clone and the latest server content is required. Refresh runs `git pull --ff-only`; it skips refresh when the worktree is dirty.

## Search Discipline

When handling a new Android Framework requirement:

1. Search with feature words, affected module, likely class name, property key, Settings key, resource key, search anchor, and artifact name.
2. Read the top matching case, variant, patch readme, or validation fact before deciding whether to reuse.
3. Treat `status`, `reusable`, platform, and validation fields as hints, not truth.
4. Prefer case and variant results first; then inspect related patches, AI evidence, and symbols.
5. Compare facts: modified files, touched symbols, artifact, risk notes, build evidence, device verification, rollback path.
6. If a prior patch looks relevant, report the evidence and remaining uncertainty before applying or adapting it.
7. Use explicit `--type report`, `--type event`, or `--type evidence` only for administrator trace-back or debugging archive material. Default `--type all` is the AI reuse view and does not return report/event archive rows.

For `android-framework-change-workflow`, this is the pre-analysis search gate. Search first; if no useful result exists, continue with normal requirement analysis and implementation.

## References

Read `references/search-contract.md` before changing the script output format or integrating this skill into another workflow.
