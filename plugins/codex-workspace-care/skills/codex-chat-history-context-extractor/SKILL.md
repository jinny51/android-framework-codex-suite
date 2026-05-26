---
name: codex-chat-history-context-extractor
description: Safely inspect local Codex chat history and generate a privacy-conscious handoff context that lets a new Codex conversation continue as if the previous conversation had been compacted, without deleting or modifying history.
---

# Codex Chat History Context Extractor

## Core Rule

Treat Codex chat context extraction as privacy-sensitive local history inspection whose product is a new-window handoff, not a generic summary. Operate read-only, identify the target session with the narrowest selector available, avoid printing private titles, paths, user names, full thread IDs, or chat record excerpts unless needed for the user's explicit goal, and produce a continuation brief that helps the next Codex window resume as if the old conversation had just been compacted.

Do not modify or delete Codex history. If cleanup is requested, use `codex-chat-history-cleaner` instead.

## Output Goal

Optimize for continuity. The final answer should be a ready-to-paste prompt for a fresh Codex conversation. It should let the next Codex agent continue immediately from the current task state without re-discovering settled facts, repeating failed paths, or asking the user to restate context.

Prefer concrete operational state over narrative:

- The user's active goal and any recent redirect.
- The current workspace, repo, project, device, branch, or environment when relevant.
- Files, commands, logs, errors, tests, builds, and artifacts that matter.
- Changes already made and whether they were verified.
- Decisions, constraints, user preferences, and safety boundaries.
- Failed, abandoned, or stale paths that should not be repeated.
- The next action the new window should take first.

For coding, debugging, Android, build, or deployment tasks, preserve these details when present:

- Repository/worktree, branch, dirty-worktree notes, and user edits that must not be reverted.
- Files already changed, intended ownership boundaries, and relevant line-level behavior.
- Exact build/test/deploy commands already run and whether they passed or failed.
- Important logs, error signatures, device state, environment variables, remote hosts, or artifact paths.
- The next command or file inspection the new Codex window should run first.

## Storage Surfaces

Inspect the same local Codex locations as the cleaner skill under `CODEX_HOME` or `~/.codex`:

- `state_*.sqlite`: thread metadata, titles, archive state, and rollout paths.
- `sessions/**/rollout-*.jsonl`: normal chat record files.
- `archived_sessions/**/rollout-*.jsonl`: archived chat record files.
- `session_index.jsonl`: lightweight search/list index; use for discovery only.

## Workflow

1. Locate `CODEX_HOME`.
2. Run `scripts/extract_codex_context.py --inventory` to count available databases and rollout files without printing chat record content.
3. If the target thread is unknown, run `scripts/extract_codex_context.py --list-candidates` to show redacted candidates with short ID prefixes and archive/update hints.
4. Choose the narrowest selector:
   - Use `--ids <id-prefix-or-id>` when thread IDs are known.
   - Use `--title-contains <text>` sparingly; avoid echoing sensitive titles in chat.
   - Use `--all-archived` only when the user wants to review archived sessions broadly.
   - Use `--rollout-file <path>` only when the user explicitly provides a chat record path.
5. Extract the target session to a local scratch file with `--output <path>` instead of dumping private chat record content into chat.
6. Synthesize the handoff in two phases:
   - Phase 1: Read the extracted chat record source and identify current operational state.
   - Phase 2: Write a compact, ready-to-paste new-window prompt using the template below.
7. Include enough facts for a new Codex window to continue from the latest useful state, but omit irrelevant backtracking, repeated tool output, secrets, local-only identifiers, and obsolete failure paths.
8. Start the brief with an instruction telling the new Codex agent to continue as if this were a compacted context restore.

## Continuation Brief Shape

Use this structure unless the user asks for another format:

```markdown
Please continue from the context below as if this were the restored compacted context from the same Codex conversation. Do not restart from scratch. Prefer the "Immediate next step" unless new evidence invalidates it.

# Continuation Context

Current goal:
...

Current state:
...

Relevant workspace, files, and environment:
- ...

Changes already made:
- ...

Commands, builds, and tests already run:
- ...

Important findings and decisions:
- ...

Failed or abandoned paths:
- ...

Immediate next step:
1. ...

User preferences and constraints:
- ...
```

## Bundled Script

Use `scripts/extract_codex_context.py` for deterministic, read-only inventory and chat record extraction.

Useful commands:

```bash
# Inventory only; does not print chat record content
python3 scripts/extract_codex_context.py --codex-home "$HOME/.codex" --inventory

# Redacted candidate list for choosing an ID prefix
python3 scripts/extract_codex_context.py --codex-home "$HOME/.codex" --list-candidates

# Extract one selected thread to a scratch file for summarization
python3 scripts/extract_codex_context.py --codex-home "$HOME/.codex" \
  --ids THREAD_PREFIX \
  --output /tmp/codex-context-source.md

# Extract from an explicit rollout JSONL path
python3 scripts/extract_codex_context.py \
  --rollout-file "$HOME/.codex/sessions/YYYY/MM/DD/rollout-THREAD.jsonl" \
  --output /tmp/codex-context-source.md
```

The script is read-only and never changes SQLite databases, JSONL chat records, indexes, artifacts, or generated images.

Run `scripts/self_test_extract_codex_context.py` after changing the extractor script.

## Privacy Before Sharing

Before publishing this skill, read `references/privacy.md`. Do not include real usernames, absolute local paths, conversation titles, thread IDs, screenshots, database rows, generated images, auth files, or logs.
