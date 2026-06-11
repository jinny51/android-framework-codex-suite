---
name: codex-chat-history-cleaner
description: Use when a user asks why archived/deleted Codex chats still appear, wants to delete local chat records, repair Codex SQLite/search/global-state issues, scrub cleanup traces, or diagnose Codex subagent tabs showing only prompts or missing history.
---

# Codex Chat History Cleaner

## Core Rule

Treat Codex chat cleanup as destructive local-state maintenance. Start with a dry run, identify every storage surface, explain what will be removed, and request approval before executing any deletion outside the current writable workspace.

Do not print private titles, paths, user names, or full thread IDs into the current conversation when the user's goal is search cleanup. Printing the matching text can make the current session become the new search hit.

## Why This Exists

A WSL-based Codex agent cannot use Codex Desktop's built-in archive/delete UI controls directly. This skill is the safe fallback for that environment: use Codex only to inspect the UI-visible keep set and produce a dry-run plan, then run the cleanup script from external WSL/PowerShell after Codex Desktop exits. The script edits local state stores (`state_*.sqlite`, transcripts, `session_index.jsonl`, and thread-keyed `.codex-global-state.json`) with backups and explicit guards instead of pretending it can click the desktop UI.

## Storage Surfaces

Check these local Codex locations under `CODEX_HOME` or `~/.codex`:

- `state_*.sqlite`: thread metadata; `threads.archived=1` means archived, not deleted.
- Child tables in `state_*.sqlite`, especially rows with `thread_id` foreign keys.
- `sessions/**/rollout-*.jsonl`: normal chat record files.
- `archived_sessions/**/rollout-*.jsonl`: archived chat record files.
- `session_index.jsonl`: lightweight search/list index.
- `.codex-global-state.json`: workspace roots, project order, thread workspace hints, projectless thread IDs, and prompt history keyed by thread ID.
- `generated_images/` and related artifact directories: optional per-thread artifacts.
- `logs_*.sqlite`: diagnostic logs. On WSL/Windows, direct reads under `/mnt/c` can report `disk I/O error`; verify by copying `.sqlite`, `-wal`, and `-shm` to `/tmp` before calling it corruption.

## UI Keep-Set Cleanup

When the user wants "only keep chats visible in the Codex UI", do not use `threads.archived` as the main decision boundary. Build a UI keep set first.

1. In Codex, call `codex_app.list_threads` and list the UI-visible thread IDs/titles for user confirmation.
2. Add the current cleanup thread and the UI-visible CLI thread if they are present in that list.
3. Preserve child subagents automatically through `thread_spawn_edges`. A UI-visible parent means its right-side subagent tabs are also protected.
4. Run only dry-run inside Codex:

```bash
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" \
  --delete-not-in-keep --keep-ids THREAD_ID... --dry-run --summary
```

5. After the user confirms the dry-run plan, tell them to fully exit Codex Desktop.
6. Execute from external WSL/PowerShell, not from inside Codex:

```bash
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" \
  --delete-not-in-keep --keep-ids THREAD_ID... \
  --execute --require-codex-exited-for-global-state --summary
```

The script backs up changed stores by default. The `--require-codex-exited-for-global-state` guard must abort before writes if Codex Desktop still appears to be running, because `.codex-global-state.json` can otherwise be rewritten from the app's in-memory state.

## Separate Subagent History Diagnosis

If a right-side Codex subagent tab shows only the initial prompt but its rollout exists, this is a history-display diagnosis, not a cleanup selector. UI-visible parent-linked subagents are protected regardless of whether their tab is hydrated.

## Workflow

1. Locate `CODEX_HOME`.
2. For the common user request "clean archived chats and prevent SQLite update errors", use `--archived-sqlite-cleanup`. It expands to archived cleanup, stale search-index cleanup, thread foreign-key orphan repair, health checks, and readable summary output. It intentionally does not clean project-list/global-state roots, CLI sessions, missing-project sessions, missing-transcript thread rows, or ordinary non-archived orphan transcripts.
   - When the user asks to list or delete archived chats, only treat `archived=1` thread rows and files under `archived_sessions/` as archived targets. Do not include ordinary `sessions/` transcripts or unrelated stale search-index examples in the archived deletion list.
   - Stale search-index cleanup must preserve records whose ordinary `sessions/` transcript still exists, even if the thread row is missing from SQLite. Such records are ordinary orphan transcript candidates, not archived cleanup targets.
3. For custom cleanup, choose selectors:
   - Use `--all-archived` for archived sessions.
   - Use `--ids <id-prefix-or-id>` when thread IDs are known.
   - Use `--title-contains <text>` sparingly; avoid echoing sensitive titles in chat.
   - Use `--all-except-current --current-thread-id <id>` only when the user asks to remove all historical search results while preserving the active thread.
   - When deleting selected threads, clean only those same thread IDs from `.codex-global-state.json` projectless IDs, workspace hints, and thread-keyed prompt history. Do not clear unrelated prompt history or `new-conversation`.
4. Run another dry run with selectors or repair flags and review counts:
   - `--all-archived` also reports unreferenced `archived_sessions` transcript files.
   - `--repair-thread-orphans` reports child rows whose `thread_id` points to missing threads.
   - `--clean-stale-index` reports stale `session_index.jsonl` records for missing thread IDs.
   - `--clean-global-state` reports stale thread IDs and workspace hints.
5. Execute only after approval: add `--execute`. Use `--no-backup` only when the user explicitly requests no backups.
6. Verify with the script health report. Require `quick_check=ok`, `integrity_check=ok`, `foreign_key_violations=0`, JSONL parse errors at `0`, and no unintended archived transcript files.
7. Tell the user to restart Codex if UI search still displays stale cached results. For `.codex-global-state.json` project-root edits, advise fully quitting Codex first or the running app may write old in-memory roots back.

## Self-Referential Search Hits

If old titles still appear after deletion, inspect whether the current cleanup conversation contains command output or assistant text that repeated those old titles. In that case, scrub the current `rollout-*.jsonl` with `--scrub-file <path>` and selectors. Prefer ID selectors or encoded/local-only patterns to avoid reintroducing sensitive terms into chat.

Example:

```bash
python3 scripts/clean_codex_history.py \
  --codex-home "$HOME/.codex" \
  --scrub-file "$HOME/.codex/sessions/YYYY/MM/DD/rollout-THREAD.jsonl" \
  --ids THREAD_PREFIX \
  --dry-run
```

Then execute with `--execute` after approval.

## Bundled Script

Use `scripts/clean_codex_history.py` for deterministic cleanup. It defaults to dry-run mode and creates timestamped backups before changing SQLite databases or index files unless `--no-backup` is passed.

Useful commands:

```bash
# Recommended simple dry run: archived cleanup + SQLite safety checks
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" \
  --archived-sqlite-cleanup --dry-run

# Recommended simple execution after approval
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" \
  --archived-sqlite-cleanup --execute

# Full inventory and health check only, readable summary
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" --dry-run --summary

# UI keep-set cleanup dry run inside Codex
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" \
  --delete-not-in-keep --keep-ids THREAD_ID... --dry-run --summary

# UI keep-set cleanup execution after fully exiting Codex Desktop
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" \
  --delete-not-in-keep --keep-ids THREAD_ID... \
  --execute --require-codex-exited-for-global-state --summary

# Delete archived records plus unreferenced archived transcript files only
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" --all-archived --execute --summary

# Repair SQLite child-table rows that reference deleted threads
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" \
  --repair-thread-orphans --execute --summary

# Clean stale search index records and global workspace/thread hints
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" \
  --clean-stale-index --clean-global-state --execute --summary

# Delete all non-current threads after approval
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" \
  --all-except-current --current-thread-id THREAD_ID --execute
```

## Health Interpretation

- `state_*.sqlite` or `goals_*.sqlite` with failed `quick_check`, `integrity_check`, or nonzero `foreign_key_violations` needs attention before claiming cleanup is complete.
- `thread_fk_orphans` are repairable with `--repair-thread-orphans`; the script deletes only simple child-table rows whose parent thread is missing.
- `orphan_archived_transcript_files` are safe candidates for `--all-archived` or `--clean-archived-files`; ordinary `sessions/` orphans can be the active conversation and should not be deleted automatically.
- `CLI 会话`, `missing_projects`, and missing-transcript thread rows are review candidates. List them with ID prefixes and titles for user judgment; do not delete them unless the user explicitly names the IDs or changes the cleanup scope.
- Search/global-state stale references should also be listed with ID prefixes and recoverable titles. If the title cannot be recovered from the DB, search index, or transcript files, say `标题未知` instead of guessing.
- `missing_projects` reports ordinary sessions whose `threads.cwd` directory no longer exists. Report these for user judgment; do not delete them as part of archived/SQLite cleanup.
- `logs_*.sqlite` direct `disk I/O error` is not enough to call the DB corrupt. Trust the temp-copy check when it reports `temp_copy_integrity_check=ok`.

## Privacy Before Sharing

Before publishing this skill, read `references/privacy.md`. Do not include real usernames, absolute local paths, conversation titles, thread IDs, screenshots, database rows, generated images, auth files, or logs.
