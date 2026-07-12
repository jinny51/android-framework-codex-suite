#!/usr/bin/env python3
"""Read-only inventory and transcript extraction for local Codex chat history."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable


PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if PLUGIN_LIB.is_dir() and str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from codex_workspace_care.history import ThreadRow, resolve_rollout_path, rollout_files, state_dbs
from codex_workspace_care.artifact_paths import require_safe_artifact_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", default=str(Path.home() / ".codex"))
    parser.add_argument("--inventory", action="store_true", help="Print counts only; do not print transcript content.")
    parser.add_argument("--list-candidates", action="store_true", help="Print redacted thread candidates with short ID prefixes.")
    parser.add_argument("--candidate-limit", type=int, default=25, help="Maximum candidates to print with --list-candidates.")
    parser.add_argument("--all-archived", action="store_true", help="Select all archived threads.")
    parser.add_argument("--ids", nargs="*", default=[], help="Thread IDs or unique prefixes to select.")
    parser.add_argument("--title-contains", nargs="*", default=[], help="Case-insensitive title substrings to select.")
    parser.add_argument("--rollout-file", help="Extract from an explicit rollout JSONL file.")
    parser.add_argument("--output", help="Write extracted markdown to this file. Required unless --inventory is used.")
    parser.add_argument("--max-chars", type=int, default=250000, help="Maximum transcript characters to write.")
    parser.add_argument("--include-tool-output", action="store_true", help="Include tool output events when recognizable.")
    return parser.parse_args()


def fetch_threads(db_path: Path) -> list[ThreadRow]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "select id, title, archived, rollout_path, coalesce(updated_at_ms, 0), coalesce(updated_at, '') "
            "from threads order by updated_at_ms desc, updated_at desc"
        ).fetchall()
    return [
        ThreadRow(
            str(row[0]),
            str(row[1] or ""),
            int(row[2] or 0),
            str(row[3] or ""),
            updated_at_ms=int(row[4] or 0),
            updated_at=str(row[5] or ""),
        )
        for row in rows
    ]


def select_threads(rows: list[ThreadRow], args: argparse.Namespace) -> list[ThreadRow]:
    selected: list[ThreadRow] = []
    id_terms = [term.lower() for term in args.ids]
    title_terms = [term.lower() for term in args.title_contains]

    for row in rows:
        row_id = row.id.lower()
        title = row.title.lower()
        match = False
        if args.all_archived and row.archived:
            match = True
        if id_terms and any(row_id.startswith(term) or row_id == term for term in id_terms):
            match = True
        if title_terms and any(term in title for term in title_terms):
            match = True
        if match:
            selected.append(row)
    return selected


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                value = item.get("text") or item.get("content") or item.get("output")
                if isinstance(value, str):
                    parts.append(value)
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        value = content.get("text") or content.get("content") or content.get("output")
        return value if isinstance(value, str) else ""
    return ""


def iter_message_candidates(payload: Any) -> Iterable[tuple[str, str]]:
    if not isinstance(payload, dict):
        return

    item = payload.get("item")
    if isinstance(item, dict):
        role = str(item.get("role") or item.get("type") or "")
        text = text_from_content(item.get("content") or item.get("text") or item.get("output"))
        if role and text:
            yield role, text

    role = str(payload.get("role") or payload.get("type") or "")
    text = text_from_content(payload.get("content") or payload.get("text") or payload.get("output"))
    if role and text:
        yield role, text

    message = payload.get("message")
    if isinstance(message, dict):
        role = str(message.get("role") or message.get("type") or "")
        text = text_from_content(message.get("content") or message.get("text") or message.get("output"))
        if role and text:
            yield role, text


def normalize_role(role: str) -> str:
    role = role.lower()
    if "user" in role:
        return "User"
    if "assistant" in role or "agent" in role:
        return "Assistant"
    if "system" in role or "developer" in role:
        return "System"
    if "tool" in role or "function" in role or "command" in role:
        return "Tool"
    return role[:1].upper() + role[1:] if role else "Event"


def extract_rollout(path: Path, include_tool_output: bool, max_chars: int) -> str:
    sections: list[str] = [f"# Extracted Codex Transcript\n\nSource: `{path}`\n"]
    used = sum(len(section) for section in sections)

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        for raw_role, raw_text in iter_message_candidates(payload):
            role = normalize_role(raw_role)
            if role == "Tool" and not include_tool_output:
                continue
            text = raw_text.strip()
            if not text:
                continue
            block = f"\n## {role}\n\n{text}\n"
            if used + len(block) > max_chars:
                remaining = max_chars - used
                if remaining > 100:
                    sections.append(block[:remaining])
                sections.append("\n\n[Truncated by --max-chars]\n")
                return "".join(sections)
            sections.append(block)
            used += len(block)
    return "".join(sections)


def inventory(codex_home: Path) -> dict[str, object]:
    dbs = state_dbs(codex_home)
    reports: list[dict[str, object]] = []
    total_threads = 0
    archived_threads = 0
    for db in dbs:
        try:
            rows = fetch_threads(db)
        except sqlite3.Error as exc:
            reports.append({"db": str(db), "error": str(exc)})
            continue
        total_threads += len(rows)
        archived_threads += sum(1 for row in rows if row.archived)
        reports.append({"db": str(db), "thread_count": len(rows), "archived_count": sum(1 for row in rows if row.archived)})
    return {
        "codex_home": str(codex_home),
        "state_db_count": len(dbs),
        "thread_count": total_threads,
        "archived_thread_count": archived_threads,
        "rollout_file_count": len(rollout_files(codex_home)),
        "databases": reports,
    }


def candidate_list(codex_home: Path, limit: int) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    for db in state_dbs(codex_home):
        rows = fetch_threads(db)
        for row in rows:
            rollout = resolve_rollout_path(codex_home, row.rollout_path)
            candidates.append(
                {
                    "index": len(candidates) + 1,
                    "id_prefix": row.id[:12],
                    "archived": bool(row.archived),
                    "has_rollout_path": bool(row.rollout_path),
                    "rollout_exists": bool(rollout and rollout.exists()),
                    "updated_at": row.updated_at,
                    "updated_at_ms": row.updated_at_ms,
                    "title_redacted": True,
                    "title_char_count": len(row.title),
                }
            )
    return {
        "codex_home": str(codex_home),
        "candidate_count": len(candidates),
        "returned_count": min(max(limit, 0), len(candidates)),
        "candidates": candidates[: max(limit, 0)],
    }


def selected_rollouts(codex_home: Path, args: argparse.Namespace) -> list[Path]:
    if args.rollout_file:
        return [Path(args.rollout_file).expanduser()]

    selected: list[ThreadRow] = []
    for db in state_dbs(codex_home):
        selected.extend(select_threads(fetch_threads(db), args))

    paths: list[Path] = []
    seen: set[Path] = set()
    for row in selected:
        path = resolve_rollout_path(codex_home, row.rollout_path)
        if path is None:
            continue
        if path not in seen:
            paths.append(path)
            seen.add(path)
    return paths


def main() -> int:
    args = parse_args()
    codex_home = Path(args.codex_home).expanduser()

    if args.inventory:
        print(json.dumps(inventory(codex_home), ensure_ascii=False, indent=2))
        return 0

    if args.list_candidates:
        print(json.dumps(candidate_list(codex_home, args.candidate_limit), ensure_ascii=False, indent=2))
        return 0

    if not args.output:
        raise SystemExit("--output is required unless --inventory is used.")
    output = require_safe_artifact_path(Path(args.output), purpose="context extraction output")

    selectors_used = args.rollout_file or args.all_archived or args.ids or args.title_contains
    if not selectors_used:
        raise SystemExit("Use --inventory first, then provide --ids, --title-contains, --all-archived, or --rollout-file.")

    paths = selected_rollouts(codex_home, args)
    existing = [path for path in paths if path.exists() and path.is_file()]
    if not existing:
        raise SystemExit("No matching rollout files found.")

    output.parent.mkdir(parents=True, exist_ok=True)
    chunks = [extract_rollout(path, args.include_tool_output, args.max_chars) for path in existing]
    output.write_text("\n\n---\n\n".join(chunks), encoding="utf-8")

    print(json.dumps({"selected_rollout_count": len(paths), "written_rollout_count": len(existing), "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
