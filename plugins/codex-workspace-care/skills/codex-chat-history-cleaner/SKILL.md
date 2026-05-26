---
name: codex-chat-history-cleaner
description: Safely inspect, repair, and clean local Codex chat history state, archived sessions, search-index remnants, SQLite consistency issues, duplicate workspace-root records, and self-referential cleanup traces. Use when a user asks why deleted or archived Codex chats still appear in search, wants to delete local chat records, prevent Codex SQLite migration/update errors, scrub current-session references to old chats, or prepare a privacy-preserving cleanup workflow for sharing.
---

# Codex Chat History Cleaner

## Core Rule

Treat Codex chat cleanup as destructive local-state maintenance. Start with a dry run, identify every storage surface, explain what will be removed, and request approval before executing any deletion outside the current writable workspace.

Do not print private titles, paths, user names, or full thread IDs into the current conversation when the user's goal is search cleanup. Printing the matching text can make the current session become the new search hit.

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
