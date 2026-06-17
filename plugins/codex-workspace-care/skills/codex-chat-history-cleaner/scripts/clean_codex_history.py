#!/usr/bin/env python3
"""Safely inspect and clean local Codex chat history stores."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any


@dataclass(frozen=True)
class ThreadRow:
    id: str
    title: str
    archived: int
    rollout_path: str
    cwd: str = ""
    source: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", default=str(Path.home() / ".codex"))
    parser.add_argument("--dry-run", action="store_true", help="Inspect only. This is the default unless --execute is passed.")
    parser.add_argument("--execute", action="store_true", help="Actually delete or scrub matched records.")
    parser.add_argument(
        "--archived-sqlite-cleanup",
        action="store_true",
        help="Simple safe preset: clean archived remnants, repair thread FK orphans, clean stale search index, and print a readable summary.",
    )
    parser.add_argument("--all-archived", action="store_true", help="Select archived thread rows and unreferenced archived transcript files.")
    parser.add_argument("--clean-archived-files", action="store_true", help="Remove unreferenced archived_sessions transcript files.")
    parser.add_argument("--all-except-current", action="store_true", help="Select all threads except --current-thread-id.")
    parser.add_argument("--current-thread-id", help="Thread ID to preserve when using --all-except-current.")
    parser.add_argument("--delete-not-in-keep", action="store_true", help="Select every DB/index/global-state thread not in --keep-ids.")
    parser.add_argument("--keep-ids", nargs="*", default=[], help="Thread IDs or unique prefixes to preserve with --delete-not-in-keep.")
    parser.add_argument("--keep-label", action="append", default=[], metavar="THREAD_ID=TITLE", help="Optional UI title label for a kept thread; display only, repeatable.")
    parser.add_argument("--no-keep-spawn-children", action="store_true", help="Do not recursively preserve child threads from thread_spawn_edges.")
    parser.add_argument("--ids", nargs="*", default=[], help="Thread IDs or unique prefixes to select.")
    parser.add_argument("--allow-ambiguous-ids", action="store_true", help="Allow an --ids term to match multiple threads.")
    parser.add_argument("--title-contains", nargs="*", default=[], help="Case-insensitive title substrings to select.")
    parser.add_argument("--scrub-file", help="Remove lines matching selected IDs or title substrings from this rollout JSONL file.")
    parser.add_argument("--repair-thread-orphans", action="store_true", help="Delete child rows whose thread_id points to missing threads.")
    parser.add_argument("--clean-stale-index", action="store_true", help="Remove session_index.jsonl records for thread IDs not present in state DBs.")
    parser.add_argument("--clean-global-state", action="store_true", help="Remove stale thread IDs from .codex-global-state.json.")
    parser.add_argument("--skip-health-check", action="store_true", help="Skip post-run consistency checks.")
    parser.add_argument("--skip-logs-db", action="store_true", help="Skip logs_*.sqlite copy-based checks during health checks.")
    parser.add_argument("--require-codex-exited-for-global-state", action="store_true", help="Abort before execution if Codex desktop appears to be running and global state would be changed.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create .bak backups before writes.")
    parser.add_argument("--show-full-ids", action="store_true", help="Print full selected thread IDs instead of redacted prefixes.")
    parser.add_argument("--summary", action="store_true", help="Print a concise human-readable Chinese summary instead of JSON.")
    return parser.parse_args()


def state_dbs(codex_home: Path) -> list[Path]:
    return sorted(codex_home.glob("state_*.sqlite"))


def sqlite_dbs_for_health(codex_home: Path) -> list[Path]:
    paths: list[Path] = []
    paths.extend(sorted(codex_home.glob("state_*.sqlite")))
    paths.extend(sorted(codex_home.glob("goals_*.sqlite")))
    dev_db = codex_home / "sqlite" / "codex-dev.db"
    if dev_db.exists():
        paths.append(dev_db)
    return paths


def logs_dbs(codex_home: Path) -> list[Path]:
    return sorted(codex_home.glob("logs_*.sqlite"))


def rollout_files(codex_home: Path) -> list[Path]:
    roots = [codex_home / "sessions", codex_home / "archived_sessions"]
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(root.glob("**/rollout-*.jsonl"))
    return sorted(files)


def rollout_file_thread_id(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                payload = json.loads(line).get("payload")
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            thread_id = str(payload.get("id") or payload.get("thread_id") or "").strip()
            if thread_id:
                return thread_id
    except OSError:
        pass

    match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", path.name, re.IGNORECASE)
    return match.group(1) if match else ""


def transcript_thread_ids(codex_home: Path, *, archived: bool | None = None) -> set[str]:
    ids: set[str] = set()
    for path in rollout_files(codex_home):
        is_archived = "archived_sessions" in path.parts
        if archived is not None and is_archived != archived:
            continue
        thread_id = rollout_file_thread_id(path)
        if thread_id:
            ids.add(thread_id)
    return ids


def resolve_rollout_path(codex_home: Path, path_text: str) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text).expanduser()
    if path.exists():
        return path

    # Stored rollout paths can come from another OS view of the same Codex home.
    # Fall back to matching the rollout filename under the same transcript root
    # class; a normal sessions row must not be masked by an archived copy.
    name = PureWindowsPath(path_text).name if "\\" in path_text else path.name
    if not name:
        return path
    normalized = path_text.replace("\\", "/")
    wants_archived = "archived_sessions/" in normalized
    wants_sessions = "sessions/" in normalized and not wants_archived
    matches = []
    for candidate in rollout_files(codex_home):
        if candidate.name != name:
            continue
        is_archived = "archived_sessions" in candidate.parts
        is_session = "sessions" in candidate.parts and not is_archived
        if wants_archived and not is_archived:
            continue
        if wants_sessions and not is_session:
            continue
        matches.append(candidate)
    if len(matches) == 1:
        return matches[0]
    return path


def fetch_threads(db_path: Path) -> list[ThreadRow]:
    def query(conn: sqlite3.Connection) -> list[ThreadRow]:
        rows = conn.execute(
            "select id, title, archived, rollout_path, cwd, source from threads order by updated_at_ms desc, updated_at desc"
        ).fetchall()
        return [
            ThreadRow(str(row[0]), str(row[1]), int(row[2] or 0), str(row[3] or ""), str(row[4] or ""), str(row[5] or ""))
            for row in rows
        ]

    return with_readonly_db(db_path, query)


def validate_id_selectors(rows: list[ThreadRow], args: argparse.Namespace) -> None:
    if not args.ids or args.allow_ambiguous_ids:
        return
    for term in args.ids:
        lowered = term.lower()
        matches = [row for row in rows if row.id.lower() == lowered or row.id.lower().startswith(lowered)]
        if len(matches) != 1:
            raise SystemExit(
                f"--ids term {term!r} matched {len(matches)} threads. Use a longer prefix or --allow-ambiguous-ids."
            )


def resolve_id_terms(
    rows: list[ThreadRow],
    terms: list[str],
    *,
    allow_ambiguous_ids: bool = False,
    allow_missing_full_ids: bool = False,
) -> set[str]:
    resolved: set[str] = set()
    for term in terms:
        lowered = term.lower()
        matches = [row.id for row in rows if row.id.lower() == lowered or row.id.lower().startswith(lowered)]
        if not matches:
            if allow_missing_full_ids and re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                lowered,
                re.IGNORECASE,
            ):
                resolved.add(term)
                continue
            raise SystemExit(f"--keep-ids term {term!r} matched 0 threads. Use a full visible thread ID.")
        if len(matches) > 1 and not allow_ambiguous_ids:
            raise SystemExit(
                f"--keep-ids term {term!r} matched {len(matches)} threads. Use a longer prefix or --allow-ambiguous-ids."
            )
        resolved.update(matches)
    return resolved


def fetch_spawn_edges(db_path: Path) -> list[tuple[str, str]]:
    def query(conn: sqlite3.Connection) -> list[tuple[str, str]]:
        tables = {
            row[0]
            for row in conn.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'").fetchall()
        }
        if "thread_spawn_edges" not in tables:
            return []
        return [
            (str(parent), str(child))
            for parent, child in conn.execute("select parent_thread_id, child_thread_id from thread_spawn_edges").fetchall()
            if parent and child
        ]

    return with_readonly_db(db_path, query)


def expand_keep_ids_with_spawn_children(db_path: Path, keep_ids: set[str]) -> set[str]:
    expanded = set(keep_ids)
    edges = fetch_spawn_edges(db_path)
    changed = True
    while changed:
        changed = False
        for parent, child in edges:
            if parent in expanded and child not in expanded:
                expanded.add(child)
                changed = True
    return expanded


def spawn_parent_map(db_paths: list[Path]) -> dict[str, str]:
    parents: dict[str, str] = {}
    for db_path in db_paths:
        for parent, child in fetch_spawn_edges(db_path):
            parents.setdefault(child, parent)
    return parents


def select_threads(rows: list[ThreadRow], args: argparse.Namespace, keep_ids: set[str] | None = None) -> list[ThreadRow]:
    if args.delete_not_in_keep:
        keep = keep_ids or set()
        return [row for row in rows if row.id not in keep]

    selected: list[ThreadRow] = []
    id_terms = [term.lower() for term in args.ids]
    title_terms = [term.lower() for term in args.title_contains]
    current_id = (args.current_thread_id or "").lower()

    for row in rows:
        row_id = row.id.lower()
        title = row.title.lower()
        match = False
        if args.all_archived and row.archived:
            match = True
        if args.all_except_current and row_id != current_id:
            match = True
        if id_terms and any(row_id.startswith(term) or row_id == term for term in id_terms):
            match = True
        if title_terms and any(term in title for term in title_terms):
            match = True
        if match:
            selected.append(row)
    return selected


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, dst)
    return dst


def backup_sqlite_family(db_path: Path) -> list[str]:
    backups: list[str] = []
    for path in [db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")]:
        if path.exists():
            backups.append(str(backup(path)))
    return backups


def sqlite_family_temp_copy(db_path: Path) -> tuple[Path, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="codex-sqlite-read."))
    for suffix in ("", "-wal", "-shm"):
        src = Path(f"{db_path}{suffix}")
        if src.exists():
            shutil.copy2(src, temp_root / src.name)
    return temp_root / db_path.name, temp_root


def is_wsl_wal_io_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "disk i/o error" in message or "unable to open database file" in message


def with_readonly_db(db_path: Path, callback):
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3) as conn:
            return callback(conn)
    except sqlite3.Error as exc:
        if not is_wsl_wal_io_error(exc):
            raise
        copied_db, temp_root = sqlite_family_temp_copy(db_path)
        try:
            with sqlite3.connect(str(copied_db), timeout=3) as conn:
                return callback(conn)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def delete_threads(db_path: Path, rows: list[ThreadRow]) -> int:
    ids = [row.id for row in rows]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with sqlite3.connect(db_path, timeout=5) as conn:
        conn.execute("pragma foreign_keys=on")
        conn.execute(f"delete from threads where id in ({placeholders})", ids)
        conn.commit()
    return len(ids)


def remove_file(codex_home: Path, path_text: str) -> bool:
    path = resolve_rollout_path(codex_home, path_text)
    if path and path.exists() and path.is_file():
        path.unlink()
        return True
    return False


def count_existing_rollouts(codex_home: Path, rows: list[ThreadRow]) -> int:
    return sum(
        1
        for row in rows
        if (path := resolve_rollout_path(codex_home, row.rollout_path)) and path.exists() and path.is_file()
    )


def clean_session_index(
    codex_home: Path,
    selected: list[ThreadRow],
    stale_thread_ids: set[str],
    execute: bool,
    no_backup: bool,
    delete_not_in_keep_ids: set[str] | None = None,
) -> dict[str, Any]:
    index_path = codex_home / "session_index.jsonl"
    report: dict[str, Any] = {
        "exists": index_path.exists(),
        "lines": 0,
        "parse_errors": 0,
        "selected_records_removed": 0,
        "stale_records_removed": 0,
        "not_in_keep_records_removed": 0,
    }
    if not index_path.exists():
        return report

    selected_ids = {row.id for row in selected}
    kept: list[str] = []
    for line in index_path.read_text(encoding="utf-8", errors="replace").splitlines(True):
        report["lines"] += 1
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            report["parse_errors"] += 1
            kept.append(line)
            continue
        record_ids = {str(payload.get("id", "")), str(payload.get("thread_id", ""))}
        if selected_ids.intersection(record_ids):
            report["selected_records_removed"] += 1
        elif delete_not_in_keep_ids is not None and any(record_ids) and not delete_not_in_keep_ids.intersection(record_ids):
            report["not_in_keep_records_removed"] += 1
        elif stale_thread_ids.intersection(record_ids):
            report["stale_records_removed"] += 1
        else:
            kept.append(line)

    removed = report["selected_records_removed"] + report["stale_records_removed"] + report["not_in_keep_records_removed"]
    if execute and removed:
        if not no_backup:
            report["backup"] = str(backup(index_path))
        index_path.write_text("".join(kept), encoding="utf-8")
    return report


def scrub_file(path: Path, rows: list[ThreadRow], title_terms: list[str], execute: bool) -> tuple[int, int]:
    if not path.exists():
        raise FileNotFoundError(path)
    needles = {row.id for row in rows}
    needles.update(term for term in title_terms if term)
    kept: list[str] = []
    removed = 0
    total = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines(True):
        total += 1
        hay = line.lower()
        if any(needle.lower() in hay for needle in needles):
            removed += 1
        else:
            kept.append(line)
    if execute and removed:
        path.write_text("".join(kept), encoding="utf-8")
    return (total, removed)


def archived_path_is_directly_referenced(candidate: Path, rows: list[ThreadRow], index_text: str) -> bool:
    try:
        candidate_resolved = str(candidate.resolve())
    except OSError:
        candidate_resolved = str(candidate)
    candidate_text = str(candidate).replace("\\", "/")
    if str(candidate) in index_text or candidate_text in index_text.replace("\\", "/"):
        return True
    for row in rows:
        rollout_text = row.rollout_path.replace("\\", "/")
        if "archived_sessions/" not in rollout_text:
            continue
        if Path(rollout_text).name != candidate.name:
            continue
        resolved = Path(row.rollout_path).expanduser()
        if str(resolved) == str(candidate) or str(resolved) == candidate_resolved or candidate.name in rollout_text:
            return True
    return False


def unreferenced_archived_files(
    codex_home: Path,
    rows: list[ThreadRow],
    protected_thread_ids: set[str] | None = None,
) -> tuple[list[Path], int, int, int]:
    arch_root = codex_home / "archived_sessions"
    archived_files = sorted(arch_root.glob("**/rollout-*.jsonl")) if arch_root.exists() else []
    index_path = codex_home / "session_index.jsonl"
    index_text = index_path.read_text(encoding="utf-8", errors="replace") if index_path.exists() else ""
    candidates: list[Path] = []
    skipped = 0
    protected_skipped = 0
    for path in archived_files:
        thread_id = rollout_file_thread_id(path)
        if protected_thread_ids and thread_id in protected_thread_ids:
            protected_skipped += 1
            continue
        if archived_path_is_directly_referenced(path, rows, index_text):
            skipped += 1
        else:
            candidates.append(path)
    return candidates, skipped, len(archived_files), protected_skipped


def clean_unreferenced_archived_files(
    codex_home: Path,
    rows: list[ThreadRow],
    execute: bool,
    protected_thread_ids: set[str] | None = None,
) -> dict[str, Any]:
    arch_root = codex_home / "archived_sessions"
    candidates, skipped, archived_count, protected_skipped = unreferenced_archived_files(codex_home, rows, protected_thread_ids)

    deleted = 0
    if execute:
        for path in candidates:
            if path.exists() and path.is_file():
                path.unlink()
                deleted += 1
        if arch_root.exists():
            for directory in sorted([item for item in arch_root.rglob("*") if item.is_dir()], key=lambda item: len(item.parts), reverse=True):
                try:
                    directory.rmdir()
                except OSError:
                    pass

    return {
        "archived_transcript_files": archived_count,
        "unreferenced_archived_transcript_files": len(candidates),
        "directly_referenced_files_skipped": skipped,
        "protected_archived_transcript_files_skipped": protected_skipped,
        "deleted_archived_transcript_files": deleted,
    }


def simple_thread_fk_columns(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    tables = [
        row[0]
        for row in conn.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'").fetchall()
    ]
    columns: list[tuple[str, str]] = []
    for table in tables:
        fk_rows = conn.execute(f"pragma foreign_key_list({quote_ident(table)})").fetchall()
        groups: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
        for row in fk_rows:
            groups[int(row[0])].append(row)
        for group in groups.values():
            if len(group) != 1:
                continue
            row = group[0]
            parent = str(row[2])
            from_col = str(row[3])
            to_col = str(row[4] or "id")
            if parent == "threads" and to_col == "id":
                columns.append((table, from_col))
    return columns


def thread_fk_orphan_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, column in simple_thread_fk_columns(conn):
        count = conn.execute(
            f"""
            select count(*)
            from {quote_ident(table)}
            where {quote_ident(column)} is not null
              and not exists (
                select 1 from threads where threads.id = {quote_ident(table)}.{quote_ident(column)}
              )
            """
        ).fetchone()[0]
        if count:
            counts[table] = int(count)
    return counts


def known_non_fk_thread_reference_columns(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    tables = {
        row[0]
        for row in conn.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'").fetchall()
    }
    columns: list[tuple[str, str]] = []
    if "agent_job_items" in tables:
        table_columns = {
            row[1]
            for row in conn.execute(f"pragma table_info({quote_ident('agent_job_items')})").fetchall()
        }
        if "assigned_thread_id" in table_columns:
            columns.append(("agent_job_items", "assigned_thread_id"))
    return columns


def thread_reference_orphan_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, column in known_non_fk_thread_reference_columns(conn):
        count = conn.execute(
            f"""
            select count(*)
            from {quote_ident(table)}
            where {quote_ident(column)} is not null
              and not exists (
                select 1 from threads where threads.id = {quote_ident(table)}.{quote_ident(column)}
              )
            """
        ).fetchone()[0]
        if count:
            counts[f"{table}.{column}"] = int(count)
    return counts


def repair_thread_fk_orphans(db_path: Path) -> dict[str, int]:
    removed: dict[str, int] = {}
    with sqlite3.connect(db_path, timeout=5) as conn:
        conn.execute("pragma foreign_keys=on")
        for table, column in simple_thread_fk_columns(conn):
            before = conn.execute(
                f"""
                select count(*)
                from {quote_ident(table)}
                where {quote_ident(column)} is not null
                  and not exists (
                    select 1 from threads where threads.id = {quote_ident(table)}.{quote_ident(column)}
                  )
                """
            ).fetchone()[0]
            if not before:
                continue
            conn.execute(
                f"""
                delete from {quote_ident(table)}
                where {quote_ident(column)} is not null
                  and not exists (
                    select 1 from threads where threads.id = {quote_ident(table)}.{quote_ident(column)}
                  )
                """
            )
            removed[table] = int(before)
        conn.commit()
    return removed


def read_session_index_ids(codex_home: Path) -> tuple[int, int, Counter[str]]:
    index_path = codex_home / "session_index.jsonl"
    ids: Counter[str] = Counter()
    lines = 0
    parse_errors = 0
    if not index_path.exists():
        return (lines, parse_errors, ids)
    for line in index_path.read_text(encoding="utf-8", errors="replace").splitlines():
        lines += 1
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        for key in ("id", "thread_id"):
            value = str(payload.get(key, ""))
            if value:
                ids[value] += 1
    return (lines, parse_errors, ids)


def project_name(raw: str) -> str:
    text = str(raw).strip()
    if text.startswith("file://"):
        text = text[7:]
    text = re.sub(r"^\\\\\?\\", "", text)
    if "\\" in text or re.match(r"^[A-Za-z]:", text):
        return PureWindowsPath(text).name or PureWindowsPath(text).drive or text
    return Path(text).name or text


def read_session_index_names(codex_home: Path) -> dict[str, str]:
    index_path = codex_home / "session_index.jsonl"
    names: dict[str, str] = {}
    if not index_path.exists():
        return names
    for line in index_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        title = payload.get("thread_name") or payload.get("title") or payload.get("name")
        if not title:
            continue
        for key in ("id", "thread_id"):
            thread_id = str(payload.get(key, "")).strip()
            if thread_id:
                names[thread_id] = str(title).strip()
    return names


def thread_name_lookup(codex_home: Path, rows: list[ThreadRow] | None = None) -> dict[str, str]:
    names = read_session_index_names(codex_home)
    for row in rows or []:
        if row.title:
            names[row.id] = row.title
    return names


def describe_thread_refs(
    ids: list[str],
    names: dict[str, str],
    extra_by_id: dict[str, str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for thread_id in ids[:limit]:
        item: dict[str, Any] = {
            "id_prefix": thread_id[:12],
            "title": names.get(thread_id) or "(标题未知)",
        }
        if extra_by_id and thread_id in extra_by_id:
            item["workspace"] = extra_by_id[thread_id]
        samples.append(item)
    return samples


def thread_keyed_dict_items(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def describe_thread_keyed_dict_refs(ids: list[str], names: dict[str, str], values: dict[str, Any]) -> list[dict[str, Any]]:
    return describe_thread_refs(ids, names, {key: str(values.get(key, "")) for key in ids})


def global_state_health(codex_home: Path, rows: list[ThreadRow]) -> dict[str, Any]:
    thread_ids = {row.id for row in rows}
    names = thread_name_lookup(codex_home, rows)
    path = codex_home / ".codex-global-state.json"
    report: dict[str, Any] = {"exists": path.exists()}
    if not path.exists():
        return report
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        report.update({"json_ok": False, "error": type(exc).__name__, "message": str(exc)[:200]})
        return report

    report["json_ok"] = True
    report["saved_workspace_roots_count"] = len(data.get("electron-saved-workspace-roots", [])) if isinstance(data.get("electron-saved-workspace-roots"), list) else None
    report["project_order_count"] = len(data.get("project-order", [])) if isinstance(data.get("project-order"), list) else None
    projectless = data.get("projectless-thread-ids", [])
    stale_projectless = (
        [item for item in projectless if isinstance(item, str) and item not in thread_ids]
        if isinstance(projectless, list)
        else []
    )
    report["stale_projectless_thread_ids"] = len(stale_projectless) if isinstance(projectless, list) else None
    report["stale_projectless_thread_id_prefixes"] = [item[:12] for item in stale_projectless[:10]]
    report["stale_projectless_thread_samples"] = describe_thread_refs(stale_projectless, names)
    hints = data.get("thread-workspace-root-hints", {})
    stale_hints = [key for key in hints if key not in thread_ids] if isinstance(hints, dict) else []
    report["stale_thread_workspace_hints"] = len(stale_hints) if isinstance(hints, dict) else None
    report["stale_thread_workspace_hint_prefixes"] = [item[:12] for item in stale_hints[:10]]
    report["stale_thread_workspace_hint_samples"] = describe_thread_refs(
        stale_hints,
        names,
        {key: str(hints.get(key, "")) for key in stale_hints} if isinstance(hints, dict) else {},
    )
    output_dirs = data.get("thread-projectless-output-directories", {})
    stale_output_dirs = [key for key in output_dirs if key not in thread_ids] if isinstance(output_dirs, dict) else []
    report["stale_thread_projectless_output_directories"] = len(stale_output_dirs) if isinstance(output_dirs, dict) else None
    report["stale_thread_projectless_output_directory_prefixes"] = [item[:12] for item in stale_output_dirs[:10]]
    report["stale_thread_projectless_output_directory_samples"] = describe_thread_refs(
        stale_output_dirs,
        names,
        {key: str(output_dirs.get(key, "")) for key in stale_output_dirs} if isinstance(output_dirs, dict) else {},
    )

    by_name: dict[str, set[str]] = defaultdict(set)
    for key in ("electron-saved-workspace-roots", "project-order", "active-workspace-roots"):
        value = data.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, str):
                by_name[project_name(item)].add(item)
    report["same_project_name_multiple_path_groups"] = sum(1 for paths in by_name.values() if len(paths) > 1)
    return report


def clean_global_state(codex_home: Path, thread_ids: set[str], execute: bool, no_backup: bool) -> dict[str, Any]:
    path = codex_home / ".codex-global-state.json"
    report: dict[str, Any] = {"exists": path.exists(), "runtime_warning": "close Codex before editing global state, or the app may rewrite old in-memory values"}
    if not path.exists():
        return report
    names = thread_name_lookup(codex_home)
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    changed = False

    projectless = data.get("projectless-thread-ids")
    if isinstance(projectless, list):
        stale_projectless = [item for item in projectless if isinstance(item, str) and item not in thread_ids]
        kept = [item for item in projectless if not isinstance(item, str) or item in thread_ids]
        report["projectless_thread_ids_removed"] = len(projectless) - len(kept)
        report["projectless_thread_id_prefixes_removed"] = [item[:12] for item in stale_projectless[:10]]
        report["projectless_thread_samples_removed"] = describe_thread_refs(stale_projectless, names)
        if kept != projectless:
            data["projectless-thread-ids"] = kept
            changed = True

    hints = data.get("thread-workspace-root-hints")
    if isinstance(hints, dict):
        stale_hint_ids = [key for key in hints if key not in thread_ids]
        kept_hints = {key: value for key, value in hints.items() if key in thread_ids}
        report["thread_workspace_hints_removed"] = len(hints) - len(kept_hints)
        report["thread_workspace_hint_prefixes_removed"] = [item[:12] for item in stale_hint_ids[:10]]
        report["thread_workspace_hint_samples_removed"] = describe_thread_refs(
            stale_hint_ids,
            names,
            {key: str(hints.get(key, "")) for key in stale_hint_ids},
        )
        if kept_hints != hints:
            data["thread-workspace-root-hints"] = kept_hints
            changed = True

    output_dirs = data.get("thread-projectless-output-directories")
    if isinstance(output_dirs, dict):
        stale_output_dir_ids = [key for key in output_dirs if key not in thread_ids]
        kept_output_dirs = {key: value for key, value in output_dirs.items() if key in thread_ids}
        report["thread_projectless_output_directories_removed"] = len(output_dirs) - len(kept_output_dirs)
        report["thread_projectless_output_directory_prefixes_removed"] = [item[:12] for item in stale_output_dir_ids[:10]]
        report["thread_projectless_output_directory_samples_removed"] = describe_thread_keyed_dict_refs(
            stale_output_dir_ids,
            names,
            output_dirs,
        )
        if kept_output_dirs != output_dirs:
            data["thread-projectless-output-directories"] = kept_output_dirs
            changed = True

    report["would_modify"] = changed
    if execute and changed:
        if not no_backup:
            report["backup"] = str(backup(path))
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        report["modified"] = True
    else:
        report["modified"] = False
    return report


def clean_global_state_for_thread_ids(codex_home: Path, thread_ids: set[str], execute: bool, no_backup: bool) -> dict[str, Any]:
    path = codex_home / ".codex-global-state.json"
    report: dict[str, Any] = {"exists": path.exists(), "runtime_warning": "close Codex before editing global state, or the app may rewrite old in-memory values"}
    target_ids = {thread_id for thread_id in thread_ids if thread_id}
    report["target_thread_count"] = len(target_ids)
    if not path.exists() or not target_ids:
        report["would_modify"] = False
        report["modified"] = False
        return report

    names = thread_name_lookup(codex_home)
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    changed = False

    projectless = data.get("projectless-thread-ids")
    if isinstance(projectless, list):
        removed = [item for item in projectless if isinstance(item, str) and item in target_ids]
        kept = [item for item in projectless if not (isinstance(item, str) and item in target_ids)]
        report["projectless_thread_ids_removed"] = len(removed)
        report["projectless_thread_id_prefixes_removed"] = [item[:12] for item in removed[:10]]
        report["projectless_thread_samples_removed"] = describe_thread_refs(removed, names)
        if kept != projectless:
            data["projectless-thread-ids"] = kept
            changed = True

    hints = data.get("thread-workspace-root-hints")
    if isinstance(hints, dict):
        removed_hint_ids = [key for key in hints if key in target_ids]
        kept_hints = {key: value for key, value in hints.items() if key not in target_ids}
        report["thread_workspace_hints_removed"] = len(removed_hint_ids)
        report["thread_workspace_hint_prefixes_removed"] = [item[:12] for item in removed_hint_ids[:10]]
        report["thread_workspace_hint_samples_removed"] = describe_thread_refs(
            removed_hint_ids,
            names,
            {key: str(hints.get(key, "")) for key in removed_hint_ids},
        )
        if kept_hints != hints:
            data["thread-workspace-root-hints"] = kept_hints
            changed = True

    output_dirs = data.get("thread-projectless-output-directories")
    if isinstance(output_dirs, dict):
        removed_output_dir_ids = [key for key in output_dirs if key in target_ids]
        kept_output_dirs = {key: value for key, value in output_dirs.items() if key not in target_ids}
        report["thread_projectless_output_directories_removed"] = len(removed_output_dir_ids)
        report["thread_projectless_output_directory_prefixes_removed"] = [item[:12] for item in removed_output_dir_ids[:10]]
        report["thread_projectless_output_directory_samples_removed"] = describe_thread_keyed_dict_refs(
            removed_output_dir_ids,
            names,
            output_dirs,
        )
        if kept_output_dirs != output_dirs:
            data["thread-projectless-output-directories"] = kept_output_dirs
            changed = True

    atom = data.get("electron-persisted-atom-state")
    prompt_history = atom.get("prompt-history") if isinstance(atom, dict) else None
    if isinstance(prompt_history, dict):
        removed_prompt_ids = [key for key in prompt_history if key in target_ids]
        kept_prompt_history = {key: value for key, value in prompt_history.items() if key not in target_ids}
        report["prompt_history_threads_removed"] = len(removed_prompt_ids)
        report["prompt_history_thread_prefixes_removed"] = [item[:12] for item in removed_prompt_ids[:10]]
        report["prompt_history_thread_samples_removed"] = describe_thread_refs(removed_prompt_ids, names)
        if kept_prompt_history != prompt_history:
            atom["prompt-history"] = kept_prompt_history
            changed = True

    report["would_modify"] = changed
    if execute and changed:
        if not no_backup:
            report["backup"] = str(backup(path))
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        report["modified"] = True
    else:
        report["modified"] = False
    return report


def clean_global_state_not_in_keep(codex_home: Path, keep_thread_ids: set[str], execute: bool, no_backup: bool) -> dict[str, Any]:
    path = codex_home / ".codex-global-state.json"
    report: dict[str, Any] = {"exists": path.exists(), "runtime_warning": "close Codex before editing global state, or the app may rewrite old in-memory values"}
    keep_ids = {thread_id for thread_id in keep_thread_ids if thread_id}
    report["keep_thread_count"] = len(keep_ids)
    if not path.exists():
        report["would_modify"] = False
        report["modified"] = False
        return report

    names = thread_name_lookup(codex_home)
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    changed = False

    projectless = data.get("projectless-thread-ids")
    if isinstance(projectless, list):
        removed = [item for item in projectless if isinstance(item, str) and item not in keep_ids]
        kept = [item for item in projectless if not isinstance(item, str) or item in keep_ids]
        report["projectless_thread_ids_removed"] = len(removed)
        report["projectless_thread_id_prefixes_removed"] = [item[:12] for item in removed[:10]]
        report["projectless_thread_samples_removed"] = describe_thread_refs(removed, names)
        if kept != projectless:
            data["projectless-thread-ids"] = kept
            changed = True

    hints = data.get("thread-workspace-root-hints")
    if isinstance(hints, dict):
        removed_hint_ids = [key for key in hints if key not in keep_ids]
        kept_hints = {key: value for key, value in hints.items() if key in keep_ids}
        report["thread_workspace_hints_removed"] = len(removed_hint_ids)
        report["thread_workspace_hint_prefixes_removed"] = [item[:12] for item in removed_hint_ids[:10]]
        report["thread_workspace_hint_samples_removed"] = describe_thread_refs(
            removed_hint_ids,
            names,
            {key: str(hints.get(key, "")) for key in removed_hint_ids},
        )
        if kept_hints != hints:
            data["thread-workspace-root-hints"] = kept_hints
            changed = True

    output_dirs = data.get("thread-projectless-output-directories")
    if isinstance(output_dirs, dict):
        removed_output_dir_ids = [key for key in output_dirs if key not in keep_ids]
        kept_output_dirs = {key: value for key, value in output_dirs.items() if key in keep_ids}
        report["thread_projectless_output_directories_removed"] = len(removed_output_dir_ids)
        report["thread_projectless_output_directory_prefixes_removed"] = [item[:12] for item in removed_output_dir_ids[:10]]
        report["thread_projectless_output_directory_samples_removed"] = describe_thread_keyed_dict_refs(
            removed_output_dir_ids,
            names,
            output_dirs,
        )
        if kept_output_dirs != output_dirs:
            data["thread-projectless-output-directories"] = kept_output_dirs
            changed = True

    atom = data.get("electron-persisted-atom-state")
    prompt_history = atom.get("prompt-history") if isinstance(atom, dict) else None
    if isinstance(prompt_history, dict):
        removed_prompt_ids = [key for key in prompt_history if key != "new-conversation" and key not in keep_ids]
        kept_prompt_history = {
            key: value
            for key, value in prompt_history.items()
            if key == "new-conversation" or key in keep_ids
        }
        report["prompt_history_threads_removed"] = len(removed_prompt_ids)
        report["prompt_history_thread_prefixes_removed"] = [item[:12] for item in removed_prompt_ids[:10]]
        report["prompt_history_thread_samples_removed"] = describe_thread_refs(removed_prompt_ids, names)
        if kept_prompt_history != prompt_history:
            atom["prompt-history"] = kept_prompt_history
            changed = True

    report["would_modify"] = changed
    if execute and changed:
        if not no_backup:
            report["backup"] = str(backup(path))
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        report["modified"] = True
    else:
        report["modified"] = False
    return report


def sqlite_health(db_path: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "db": db_path.name if db_path.parent.name != "sqlite" else f"sqlite/{db_path.name}",
        "size_bytes": db_path.stat().st_size if db_path.exists() else None,
    }
    try:
        def query(conn: sqlite3.Connection) -> dict[str, Any]:
            report["quick_check"] = conn.execute("pragma quick_check").fetchone()[0]
            report["integrity_check"] = conn.execute("pragma integrity_check").fetchone()[0]
            report["foreign_key_violations"] = len(conn.execute("pragma foreign_key_check").fetchall())
            report["table_count"] = conn.execute("select count(*) from sqlite_master where type='table'").fetchone()[0]
            if conn.execute("select count(*) from sqlite_master where type='table' and name='_sqlx_migrations'").fetchone()[0]:
                count, success, max_version = conn.execute(
                    "select count(*), coalesce(sum(case when success=1 then 1 else 0 end),0), max(version) from _sqlx_migrations"
                ).fetchone()
                report["migrations"] = {"count": count, "success": success, "max_version": max_version}
            if conn.execute("select count(*) from sqlite_master where type='table' and name='threads'").fetchone()[0]:
                report["thread_fk_orphans"] = thread_fk_orphan_counts(conn)
                report["thread_reference_orphans"] = thread_reference_orphan_counts(conn)
            return report

        return with_readonly_db(db_path, query)
    except Exception as exc:
        report["error"] = type(exc).__name__
        report["message"] = str(exc)[:200]
    return report


def logs_sqlite_health(db_path: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"db": db_path.name, "size_bytes": db_path.stat().st_size if db_path.exists() else None}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2) as conn:
            report["direct_ro_quick_check"] = conn.execute("pragma quick_check").fetchone()[0]
    except Exception as exc:
        report["direct_ro_error"] = type(exc).__name__
        report["direct_ro_message"] = str(exc)[:120]

    temp_root = Path(tempfile.mkdtemp(prefix="codex-logdb-check."))
    try:
        for suffix in ("", "-wal", "-shm"):
            src = Path(f"{db_path}{suffix}")
            if src.exists():
                shutil.copy2(src, temp_root / src.name)
        copied_db = temp_root / db_path.name
        if copied_db.exists():
            with sqlite3.connect(str(copied_db), timeout=3) as conn:
                report["temp_copy_quick_check"] = conn.execute("pragma quick_check").fetchone()[0]
                report["temp_copy_integrity_check"] = conn.execute("pragma integrity_check").fetchone()[0]
    except Exception as exc:
        report["temp_copy_error"] = type(exc).__name__
        report["temp_copy_message"] = str(exc)[:120]
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    return report


def transcript_health(codex_home: Path, rows: list[ThreadRow]) -> dict[str, Any]:
    files = rollout_files(codex_home)
    referenced_names = {
        PureWindowsPath(row.rollout_path).name if "\\" in row.rollout_path else Path(row.rollout_path).name
        for row in rows
        if row.rollout_path
    }
    missing = 0
    existing = 0
    for row in rows:
        path = resolve_rollout_path(codex_home, row.rollout_path)
        if path and path.exists() and path.is_file():
            existing += 1
        else:
            missing += 1
    orphan_files = [path for path in files if path.name not in referenced_names]
    archived_files = [path for path in files if "archived_sessions" in path.parts]
    orphan_archived = [path for path in orphan_files if "archived_sessions" in path.parts]
    return {
        "thread_rows": len(rows),
        "existing_thread_rollout_files": existing,
        "missing_thread_rollout_files": missing,
        "session_transcript_files": sum(1 for path in files if "sessions" in path.parts and "archived_sessions" not in path.parts),
        "archived_transcript_files": len(archived_files),
        "orphan_transcript_files": len(orphan_files),
        "orphan_archived_transcript_files": len(orphan_archived),
        "archived_thread_rows": sum(1 for row in rows if row.archived),
        "rows_with_archived_rollout_path": sum(1 for row in rows if "archived_sessions" in row.rollout_path.replace("\\", "/")),
    }


def normalize_cwd_path(cwd: str) -> Path | None:
    text = str(cwd or "").strip()
    if not text:
        return None
    if text.startswith("\\\\wsl.localhost\\Ubuntu\\") or text.startswith("\\\\wsl$\\Ubuntu\\"):
        rest = text.split("Ubuntu\\", 1)[1].replace("\\", "/")
        return Path("/" + rest)
    if text.startswith("\\\\?\\C:\\"):
        return Path("/mnt/c/" + text[7:].replace("\\", "/"))
    if re.match(r"^[A-Za-z]:\\", text):
        return Path("/mnt/" + text[0].lower() + "/" + text[3:].replace("\\", "/"))
    return Path(text).expanduser()


def missing_project_health(rows: list[ThreadRow]) -> dict[str, Any]:
    missing: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        path = normalize_cwd_path(row.cwd)
        if path is None:
            continue
        key = str(path)
        if path.exists():
            continue
        if row.id in seen:
            continue
        seen.add(row.id)
        missing.append(
            {
                "id_prefix": row.id[:12],
                "title": (row.title or "").strip()[:120] or "(无标题)",
                "project": path.name or key,
                "cwd": key,
                "archived": int(row.archived or 0),
            }
        )
    return {
        "missing_project_thread_count": len(missing),
        "samples": missing[:5],
    }


def review_candidate_health(codex_home: Path, rows: list[ThreadRow]) -> dict[str, Any]:
    def sample(row: ThreadRow) -> dict[str, Any]:
        path = normalize_cwd_path(row.cwd)
        return {
            "id_prefix": row.id[:12],
            "title": (row.title or "").strip()[:120] or "(无标题)",
            "source": row.source,
            "project": (path.name if path else "") or project_name(row.cwd),
            "cwd": str(path) if path else row.cwd,
        }

    cli_threads = [row for row in rows if row.source == "cli"]
    missing_rollouts = [
        row
        for row in rows
        if not ((path := resolve_rollout_path(codex_home, row.rollout_path)) and path.exists() and path.is_file())
    ]
    return {
        "cli_thread_count": len(cli_threads),
        "cli_samples": [sample(row) for row in cli_threads[:5]],
        "missing_transcript_thread_count": len(missing_rollouts),
        "missing_transcript_samples": [sample(row) for row in missing_rollouts[:5]],
    }


def artifact_health(codex_home: Path) -> dict[str, Any]:
    dirs = ["generated_images", "shell_snapshots", "computer-use", "browser"]
    report: dict[str, Any] = {}
    for name in dirs:
        root = codex_home / name
        if root.exists():
            report[name] = {"files": sum(1 for item in root.rglob("*") if item.is_file())}
    return report


def health_report(
    codex_home: Path,
    db_rows: dict[Path, list[ThreadRow]],
    skip_logs_db: bool,
) -> dict[str, Any]:
    all_rows = [row for rows in db_rows.values() for row in rows]
    thread_ids = {row.id for row in all_rows}
    index_lines, index_parse_errors, index_ids = read_session_index_ids(codex_home)
    ordinary_transcript_ids = transcript_thread_ids(codex_home, archived=False)
    stale_index_ids = {thread_id for thread_id in index_ids if thread_id not in thread_ids and thread_id not in ordinary_transcript_ids}
    index_names = read_session_index_names(codex_home)
    return {
        "global_state": global_state_health(codex_home, all_rows),
        "session_index": {
            "exists": (codex_home / "session_index.jsonl").exists(),
            "lines": index_lines,
            "parse_errors": index_parse_errors,
            "stale_thread_id_records": sum(index_ids[thread_id] for thread_id in stale_index_ids),
            "stale_thread_id_prefixes": [thread_id[:12] for thread_id in sorted(stale_index_ids)[:10]],
            "stale_thread_samples": describe_thread_refs(sorted(stale_index_ids), index_names),
        },
        "sqlite_primary_dbs": [sqlite_health(db_path) for db_path in sqlite_dbs_for_health(codex_home)],
        "logs_dbs": [] if skip_logs_db else [logs_sqlite_health(db_path) for db_path in logs_dbs(codex_home)],
        "transcripts": transcript_health(codex_home, all_rows),
        "missing_projects": missing_project_health(all_rows),
        "review_candidates": review_candidate_health(codex_home, all_rows),
        "artifact_directories": artifact_health(codex_home),
    }


def stale_index_thread_ids(codex_home: Path, thread_ids: set[str]) -> set[str]:
    _, _, ids = read_session_index_ids(codex_home)
    ordinary_transcript_ids = transcript_thread_ids(codex_home, archived=False)
    return {thread_id for thread_id in ids if thread_id not in thread_ids and thread_id not in ordinary_transcript_ids}


def sum_dict_values(value: Any) -> int:
    if isinstance(value, dict):
        return sum(int(item) for item in value.values() if isinstance(item, int))
    return 0


def shell_command(parts: list[Any]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def codex_desktop_process_report() -> dict[str, Any]:
    report: dict[str, Any] = {"checked": True, "running": False, "matches": []}
    powershell = shutil.which("powershell.exe")
    if powershell:
        command = (
            "Get-Process | "
            "Where-Object { $_.ProcessName -match '^(Codex|OpenAI\\.Codex)$' -or ($_.Path -and $_.Path -match 'OpenAI\\.Codex') } | "
            "Select-Object -First 10 -ExpandProperty ProcessName"
        )
        try:
            result = subprocess.run(
                [powershell, "-NoProfile", "-Command", command],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            matches = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            report.update(
                {
                    "method": "powershell.exe Get-Process",
                    "running": bool(matches),
                    "matches": matches,
                    "returncode": result.returncode,
                }
            )
            if result.stderr.strip():
                report["stderr"] = result.stderr.strip()[:300]
            return report
        except Exception as exc:
            report["powershell_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    proc = Path("/proc")
    matches: list[str] = []
    if proc.exists():
        for item in proc.iterdir():
            if not item.name.isdigit():
                continue
            try:
                if int(item.name) == os.getpid():
                    continue
                comm = (item / "comm").read_text(encoding="utf-8", errors="replace").strip()
                cmdline = (item / "cmdline").read_text(encoding="utf-8", errors="replace").replace("\x00", " ")
            except Exception:
                continue
            hay = f"{comm} {cmdline}"
            if "clean_codex_history.py" in hay:
                continue
            if "OpenAI.Codex" in hay or comm.lower() in {"codex", "codex.exe", "openai.codex", "openai.codex.exe"}:
                matches.append(f"{item.name}:{comm}")
                if len(matches) >= 10:
                    break
    report.update({"method": "procfs", "running": bool(matches), "matches": matches})
    return report


def optional_global_cleanup_command(codex_home: str) -> str:
    return shell_command(
        [
            "python3",
            Path(__file__).resolve(),
            "--codex-home",
            codex_home,
            "--clean-stale-index",
            "--clean-global-state",
            "--execute",
            "--no-backup",
            "--summary",
        ]
    )


def ui_keep_set_execute_command(args: argparse.Namespace, codex_home: Path) -> str:
    parts: list[Any] = [
        "python3",
        Path(__file__).resolve(),
        "--codex-home",
        str(codex_home),
        "--delete-not-in-keep",
        "--keep-ids",
    ]
    parts.extend(args.keep_ids)
    for label in args.keep_label:
        parts.extend(["--keep-label", label])
    if args.no_keep_spawn_children:
        parts.append("--no-keep-spawn-children")
    if args.allow_ambiguous_ids:
        parts.append("--allow-ambiguous-ids")
    if args.no_backup:
        parts.append("--no-backup")
    if args.show_full_ids:
        parts.append("--show-full-ids")
    if args.skip_health_check:
        parts.append("--skip-health-check")
    if args.skip_logs_db:
        parts.append("--skip-logs-db")
    parts.extend(["--execute", "--require-codex-exited-for-global-state", "--summary"])
    return shell_command(parts)


def render_thread_samples(samples: Any, limit: int = 3) -> str:
    if not isinstance(samples, list):
        return ""
    rendered: list[str] = []
    seen: set[str] = set()
    for item in samples:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id_prefix") or "")
        if key in seen:
            continue
        seen.add(key)
        title = str(item.get("title") or "(无标题)").strip()
        project = str(item.get("project") or item.get("workspace") or "").strip()
        suffix = f" [{project}]" if project else ""
        rendered.append(f"{item.get('id_prefix')} {title}{suffix}")
        if len(rendered) >= limit:
            break
    return "：" + "；".join(rendered) if rendered else ""


def compact_display_text(text: str, limit: int = 64) -> str:
    compacted = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compacted) <= limit:
        return compacted
    return compacted[: max(1, limit - 1)].rstrip() + "…"


def subagent_nickname_from_source(source: str) -> str:
    text = str(source or "").strip()
    if not text.startswith("{"):
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ""
    subagent = payload.get("subagent") if isinstance(payload, dict) else None
    if not isinstance(subagent, dict):
        return ""
    spawn = subagent.get("thread_spawn")
    if not isinstance(spawn, dict):
        return ""
    return compact_display_text(str(spawn.get("agent_nickname") or ""), limit=32)


def source_display_label(source: str) -> tuple[str, str]:
    nickname = subagent_nickname_from_source(source)
    if nickname:
        return (f"subagent:{nickname}", nickname)
    value = str(source or "").strip()
    lowered = value.lower()
    if lowered == "cli":
        return ("CLI", "")
    if lowered in {"vscode", "desktop", "user"}:
        return ("UI", "")
    if value.startswith("{"):
        return ("subagent", "")
    return (compact_display_text(value, limit=24), "")


def thread_row_sample(row: ThreadRow, parent_by_child: dict[str, str] | None = None) -> dict[str, Any]:
    path = normalize_cwd_path(row.cwd)
    project = (path.name if path else "") or project_name(row.cwd)
    source_label, subagent_nickname = source_display_label(row.source)
    title = compact_display_text(row.title)
    if subagent_nickname:
        title = f"子智能体 {subagent_nickname}"
    elif source_label == "CLI":
        title = "CLI 会话"
    return {
        "id": row.id,
        "id_prefix": row.id[:12],
        "title": title or "(无标题)",
        "source": source_label,
        "project": compact_display_text(project, limit=32),
        "archived": int(row.archived or 0),
        "parent_id": (parent_by_child or {}).get(row.id, ""),
    }


def describe_thread_rows(
    rows: list[ThreadRow],
    limit: int = 50,
    parent_by_child: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    return [thread_row_sample(row, parent_by_child) for row in rows[:limit]]


def describe_thread_ids(
    thread_ids: set[str],
    rows: list[ThreadRow],
    limit: int = 50,
    parent_by_child: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    remaining = set(thread_ids)
    samples: list[dict[str, Any]] = []
    for row in rows:
        if row.id not in remaining:
            continue
        samples.append(thread_row_sample(row, parent_by_child))
        remaining.remove(row.id)
        if len(samples) >= limit:
            return samples
    for thread_id in sorted(remaining):
        samples.append(
            {
                "id": thread_id,
                "id_prefix": thread_id[:12],
                "title": "(UI 保留 ID，当前 DB 未找到标题)",
                "source": "",
                "project": "",
                "archived": 0,
            }
        )
        if len(samples) >= limit:
            break
    return samples


def parse_keep_labels(items: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit("--keep-label must be THREAD_ID=TITLE.")
        thread_id, title = item.split("=", 1)
        thread_id = thread_id.strip()
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", thread_id, re.IGNORECASE):
            raise SystemExit("--keep-label requires a full thread ID before '='.")
        labels[thread_id] = compact_display_text(title, limit=64) or "(无标题)"
    return labels


def apply_keep_labels(samples: list[dict[str, Any]], labels: dict[str, str]) -> list[dict[str, Any]]:
    if not labels:
        return samples
    labeled: list[dict[str, Any]] = []
    for item in samples:
        copy = dict(item)
        item_id = str(copy.get("id") or "")
        for thread_id, title in labels.items():
            if thread_id == item_id:
                copy["title"] = title
                break
        labeled.append(copy)
    return labeled


def render_approval_item_line(item: dict[str, Any], *, indent: str, orphan_subagent: bool = False) -> str:
    prefix = str(item.get("id_prefix") or "").strip()
    title = str(item.get("title") or "(无标题)").strip()
    if orphan_subagent and title.startswith("子智能体 "):
        title = "孤立" + title
    source = str(item.get("source") or "").strip()
    project = str(item.get("project") or item.get("workspace") or "").strip()
    tags: list[str] = []
    if source:
        tags.append(source)
    if project:
        tags.append(project)
    if int(item.get("archived") or 0):
        tags.append("archived")
    tag_text = f" [{' / '.join(tags)}]" if tags else ""
    id_text = f"{prefix} " if prefix else ""
    return f"{indent}{id_text}{title}{tag_text}"


def group_approval_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(item.get("id") or ""): item for item in samples if isinstance(item, dict) and item.get("id")}
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for item in samples:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        parent_id = str(item.get("parent_id") or "")
        parent_is_in_same_set = bool(parent_id and parent_id in by_id)
        group_id = parent_id if parent_is_in_same_set else item_id
        if group_id not in groups:
            groups[group_id] = {
                "parent": by_id.get(group_id, item),
                "children": [],
                "orphan_subagent": bool(parent_id and not parent_is_in_same_set),
            }
            order.append(group_id)
        if item_id == group_id:
            groups[group_id]["parent"] = item
        else:
            groups[group_id]["children"].append(item)

    return [groups[group_id] for group_id in order]


def render_grouped_approval_sample_lines(samples: Any, *, group_limit: int = 20) -> list[str]:
    if not isinstance(samples, list) or not samples:
        return []
    groups = group_approval_samples([item for item in samples if isinstance(item, dict)])
    lines: list[str] = []
    rendered_groups = 0
    for group in groups[:group_limit]:
        parent = group.get("parent")
        if not isinstance(parent, dict):
            continue
        lines.append(render_approval_item_line(parent, indent="  - ", orphan_subagent=bool(group.get("orphan_subagent"))))
        children = group.get("children") if isinstance(group.get("children"), list) else []
        for child in children:
            if isinstance(child, dict):
                lines.append(render_approval_item_line(child, indent="    - "))
        rendered_groups += 1
    if len(groups) > rendered_groups:
        lines.append(f"  - ... 还有 {len(groups) - rendered_groups} 组未展开")
    return lines


def render_ui_keep_set_summary(summary: dict[str, Any]) -> str:
    mode = summary.get("mode")
    dry_run = mode != "execute"
    lines: list[str] = []
    lines.append("Codex UI 保留集清理计划")
    lines.append(f"模式：{'预览，不会修改任何文件' if dry_run else '执行，已按计划修改'}")

    keep_set = summary.get("keep_set") if isinstance(summary.get("keep_set"), dict) else {}
    keep_count = int(keep_set.get("keep_thread_count") or 0)
    keep_reason = "UI 可见会话"
    if keep_set.get("spawn_children_preserved"):
        keep_reason += " + 关联子智能体"
    lines.append("")
    lines.append("【保留，不会删除】")
    lines.append(f"- 共 {keep_count} 个线程：{keep_reason}")
    lines.extend(render_grouped_approval_sample_lines(keep_set.get("keep_samples"), group_limit=25))

    selected_thread_count = sum(
        int(db.get("selected_count") or 0)
        for db in summary.get("databases", [])
        if isinstance(db, dict)
    )
    selected_samples: list[dict[str, Any]] = []
    for db in summary.get("databases", []):
        if isinstance(db, dict):
            selected_samples.extend(db.get("selected_samples") or [])

    archived = summary.get("archived_files") if isinstance(summary.get("archived_files"), dict) else {}
    protected_archived = int(archived.get("protected_archived_transcript_files_skipped") or 0) if archived else 0
    archived_count = int(archived.get("unreferenced_archived_transcript_files") or 0) if archived else 0
    archived_deleted = int(archived.get("deleted_archived_transcript_files") or 0) if archived else 0

    index_report = summary.get("session_index", {}) if isinstance(summary.get("session_index"), dict) else {}
    stale_index = int(index_report.get("stale_records_removed") or 0)
    selected_index = int(index_report.get("selected_records_removed") or 0)
    not_in_keep_index = int(index_report.get("not_in_keep_records_removed") or 0)
    index_total = stale_index + selected_index + not_in_keep_index

    keep_global_cleanup = summary.get("global_state_keep_cleanup") if isinstance(summary.get("global_state_keep_cleanup"), dict) else {}
    global_projectless = int(keep_global_cleanup.get("projectless_thread_ids_removed") or 0) if keep_global_cleanup else 0
    global_hints = int(keep_global_cleanup.get("thread_workspace_hints_removed") or 0) if keep_global_cleanup else 0
    global_output_dirs = int(keep_global_cleanup.get("thread_projectless_output_directories_removed") or 0) if keep_global_cleanup else 0
    global_prompts = int(keep_global_cleanup.get("prompt_history_threads_removed") or 0) if keep_global_cleanup else 0

    lines.append("")
    lines.append("【计划删除/清理】")
    planned_any = False
    if selected_thread_count:
        planned_any = True
        lines.append(f"- DB 会话记录：{'将删除' if dry_run else '已删除'} {selected_thread_count} 条（不在 UI 保留集）")
        lines.extend(render_grouped_approval_sample_lines(selected_samples, group_limit=10))
    if archived:
        planned_any = planned_any or bool(archived_count or archived_deleted)
        if dry_run:
            lines.append(f"- 归档 transcript 残留：将删除 {archived_count} 个文件")
        else:
            lines.append(f"- 归档 transcript 残留：已删除 {archived_deleted} 个文件")
    if index_total:
        planned_any = True
        parts = []
        if selected_index:
            parts.append(f"关联待删会话 {selected_index} 条")
        if not_in_keep_index:
            parts.append(f"非保留集 {not_in_keep_index} 条")
        if stale_index:
            parts.append(f"stale {stale_index} 条")
        lines.append(f"- 搜索索引 session_index：{'将清理' if dry_run else '已清理'} " + "、".join(parts))
    if global_projectless or global_hints or global_output_dirs or global_prompts:
        planned_any = True
        action = "将清理" if dry_run else "已清理"
        lines.append(
            "- 全局状态 .codex-global-state.json："
            f"{action} projectless {global_projectless} 个、workspace hint {global_hints} 个、"
            f"output directory {global_output_dirs} 个、prompt-history {global_prompts} 个"
        )
    if not planned_any:
        lines.append("- 未发现需要按当前保留集删除或清理的内容")

    health = summary.get("health", {}) if isinstance(summary.get("health"), dict) else {}
    sqlite_dbs = health.get("sqlite_primary_dbs", []) if isinstance(health.get("sqlite_primary_dbs"), list) else []
    sqlite_bad: list[str] = []
    sqlite_reference_orphans = 0
    for db in sqlite_dbs:
        if not isinstance(db, dict):
            continue
        name = str(db.get("db", "sqlite"))
        if db.get("quick_check") != "ok":
            sqlite_bad.append(f"{name}: quick_check={db.get('quick_check')}")
        if db.get("integrity_check") != "ok":
            sqlite_bad.append(f"{name}: integrity_check={db.get('integrity_check')}")
        if int(db.get("foreign_key_violations") or 0):
            sqlite_bad.append(f"{name}: 外键违规 {db.get('foreign_key_violations')}")
        sqlite_reference_orphans += sum_dict_values(db.get("thread_reference_orphans"))

    transcripts = health.get("transcripts") if isinstance(health.get("transcripts"), dict) else {}
    missing_transcripts = int(transcripts.get("missing_thread_rollout_files") or 0) if transcripts else 0
    ordinary_orphans = (
        int(transcripts.get("orphan_transcript_files") or 0) - int(transcripts.get("orphan_archived_transcript_files") or 0)
        if transcripts
        else 0
    )
    health_index = health.get("session_index", {}) if isinstance(health.get("session_index"), dict) else {}
    parse_errors = int(index_report.get("parse_errors") or health_index.get("parse_errors") or 0)

    notes: list[str] = []
    notes.append("- SQLite：" + ("正常" if not sqlite_bad else "需要先处理 - " + "；".join(sqlite_bad[:4])))
    if sqlite_reference_orphans:
        notes.append(f"- 新版 SQLite 非外键 thread 引用残留：{sqlite_reference_orphans} 条，仅提示，不按本计划自动删除")
    if protected_archived:
        notes.append(f"- 归档副本保护：跳过 UI 保留集相关文件 {protected_archived} 个，不删除")
    if missing_transcripts:
        notes.append(f"- 普通会话 transcript 缺文件：{missing_transcripts} 条，仅提示，不按本计划自动删除")
    if ordinary_orphans:
        notes.append(f"- 普通孤儿 transcript：{ordinary_orphans} 个，仅提示，不按本计划自动删除")
    if parse_errors:
        notes.append(f"- 搜索索引 JSONL 解析错误：{parse_errors} 条，需要单独检查")
    lines.append("")
    lines.append("【不会自动删除，只提示】")
    lines.extend(notes)

    lines.append("")
    lines.append("【下一步】")
    if sqlite_bad:
        lines.append("- 先不要执行删除；SQLite 主库检查有风险，需要看 JSON 详情。")
    elif dry_run and planned_any:
        lines.append("- 确认上面的保留清单和删除计划无误后，完全退出 Codex 桌面端。")
        lines.append("- 在外部 WSL/PowerShell 执行下面的完整命令。")
        if global_projectless or global_hints or global_output_dirs or global_prompts:
            lines.append("- 这次会改 .codex-global-state.json，所以必须退出 Codex，避免桌面端把旧内存状态写回。")
    elif dry_run:
        lines.append("- 当前没有需要执行的清理项。")
    else:
        lines.append("- 重新打开 Codex 后复查 UI 会话列表和搜索结果。")
    command = str(summary.get("external_execute_command") or "").strip()
    if dry_run and planned_any and command and not sqlite_bad:
        lines.append("")
        lines.append("【完整执行命令】")
        lines.append("```bash")
        lines.append(command)
        lines.append("```")
    return "\n".join(lines)


def render_summary(summary: dict[str, Any]) -> str:
    mode = summary.get("mode")
    dry_run = mode != "execute"
    actions = summary.get("actions_requested", {}) if isinstance(summary.get("actions_requested"), dict) else {}
    simple_archived_sqlite = bool(actions.get("archived_sqlite_cleanup"))
    if actions.get("delete_not_in_keep"):
        return render_ui_keep_set_summary(summary)
    lines: list[str] = []
    lines.append("Codex 本地状态检查结果")
    lines.append(f"模式：{'预览，不会修改' if dry_run else '执行，已按参数修改'}")
    keep_set = summary.get("keep_set") if isinstance(summary.get("keep_set"), dict) else None
    if keep_set:
        lines.append(
            f"UI 保留集模式：保留 {keep_set.get('keep_thread_count', 0)} 个线程"
            f"{'，包含关联子智能体' if keep_set.get('spawn_children_preserved') else ''}"
        )

    health = summary.get("health", {}) if isinstance(summary.get("health"), dict) else {}
    sqlite_dbs = health.get("sqlite_primary_dbs", []) if isinstance(health.get("sqlite_primary_dbs"), list) else []
    sqlite_bad: list[str] = []
    for db in sqlite_dbs:
        if not isinstance(db, dict):
            continue
        name = str(db.get("db", "sqlite"))
        if db.get("quick_check") != "ok":
            sqlite_bad.append(f"{name}: quick_check={db.get('quick_check')}")
        if db.get("integrity_check") != "ok":
            sqlite_bad.append(f"{name}: integrity_check={db.get('integrity_check')}")
        if int(db.get("foreign_key_violations") or 0):
            sqlite_bad.append(f"{name}: 外键违规 {db.get('foreign_key_violations')}")
        migrations = db.get("migrations")
        if isinstance(migrations, dict) and migrations.get("count") != migrations.get("success"):
            sqlite_bad.append(f"{name}: migration {migrations.get('success')}/{migrations.get('count')} 成功")
    lines.append("SQLite：正常" if not sqlite_bad else "SQLite：需要处理 - " + "；".join(sqlite_bad[:4]))

    log_notes: list[str] = []
    for db in health.get("logs_dbs", []) if isinstance(health.get("logs_dbs"), list) else []:
        if not isinstance(db, dict):
            continue
        if db.get("direct_ro_error") and db.get("temp_copy_integrity_check") == "ok":
            log_notes.append(f"{db.get('db')}: WSL 直读报错，但临时副本检查正常")
        elif db.get("temp_copy_integrity_check") not in (None, "ok"):
            log_notes.append(f"{db.get('db')}: 日志库检查异常")
    if log_notes:
        lines.append("日志库：" + "；".join(log_notes[:3]))

    db_orphans_before = sum(sum_dict_values(db.get("thread_fk_orphans")) for db in summary.get("databases", []) if isinstance(db, dict))
    db_orphans_removed = sum(sum_dict_values(db.get("removed_thread_fk_orphans")) for db in summary.get("databases", []) if isinstance(db, dict))
    if db_orphans_removed:
        lines.append(f"线程子表孤儿记录：已清理 {db_orphans_removed} 条")
    elif db_orphans_before:
        lines.append(f"线程子表孤儿记录：发现 {db_orphans_before} 条，执行时会清理")
    else:
        lines.append("线程子表孤儿记录：无")
    thread_reference_orphans = sum(
        sum_dict_values(db.get("thread_reference_orphans"))
        for db in sqlite_dbs
        if isinstance(db, dict)
    )
    if thread_reference_orphans:
        lines.append(f"新版 SQLite 非外键 thread 引用残留：{thread_reference_orphans} 条，仅列出不自动删除")

    selected_thread_count = sum(
        int(db.get("selected_count") or 0)
        for db in summary.get("databases", [])
        if isinstance(db, dict)
    )
    if selected_thread_count:
        if actions.get("delete_not_in_keep"):
            lines.append(f"非 UI 保留集 DB 会话：{'将删除' if dry_run else '已删除'} {selected_thread_count} 条")
        else:
            lines.append(f"选中 DB 会话：{'将删除' if dry_run else '已删除'} {selected_thread_count} 条")

    archived = summary.get("archived_files") if isinstance(summary.get("archived_files"), dict) else None
    transcripts = health.get("transcripts") if isinstance(health.get("transcripts"), dict) else {}
    if archived:
        protected_archived = int(archived.get("protected_archived_transcript_files_skipped") or 0)
        if dry_run:
            lines.append(f"归档残留：发现 {archived.get('unreferenced_archived_transcript_files', 0)} 个可清理文件")
        else:
            lines.append(f"归档残留：已删除 {archived.get('deleted_archived_transcript_files', 0)} 个文件")
        if protected_archived:
            lines.append(f"归档副本保护：跳过 UI 保留集相关文件 {protected_archived} 个")
    elif transcripts:
        lines.append(f"归档残留：{transcripts.get('orphan_archived_transcript_files', 0)} 个")

    index_report = summary.get("session_index", {}) if isinstance(summary.get("session_index"), dict) else {}
    stale_index = int(index_report.get("stale_records_removed") or 0)
    selected_index = int(index_report.get("selected_records_removed") or 0)
    not_in_keep_index = int(index_report.get("not_in_keep_records_removed") or 0)
    index_removed = stale_index + selected_index + not_in_keep_index
    health_index = health.get("session_index", {}) if isinstance(health.get("session_index"), dict) else {}
    if index_removed:
        parts = []
        if selected_index:
            parts.append(f"选中 {selected_index} 条")
        if not_in_keep_index:
            parts.append(f"非保留集 {not_in_keep_index} 条")
        if stale_index:
            parts.append(f"stale {stale_index} 条")
        lines.append(f"搜索索引记录：{'将清理' if dry_run else '已清理'} " + "、".join(parts))
    elif int(health_index.get("stale_thread_id_records") or 0):
        lines.append(f"搜索索引 stale 记录：还有 {health_index.get('stale_thread_id_records')} 条")
    else:
        lines.append("搜索索引：无 stale 记录")
    if int(index_report.get("parse_errors") or health_index.get("parse_errors") or 0):
        lines.append("搜索索引：存在 JSONL 解析错误，需要单独检查")

    global_cleanup = summary.get("global_state_cleanup") if isinstance(summary.get("global_state_cleanup"), dict) else None
    selected_global_cleanup = summary.get("global_state_selected_cleanup") if isinstance(summary.get("global_state_selected_cleanup"), dict) else None
    keep_global_cleanup = summary.get("global_state_keep_cleanup") if isinstance(summary.get("global_state_keep_cleanup"), dict) else None
    global_health = health.get("global_state", {}) if isinstance(health.get("global_state"), dict) else {}
    if keep_global_cleanup:
        removed_threads = int(keep_global_cleanup.get("projectless_thread_ids_removed") or 0)
        removed_hints = int(keep_global_cleanup.get("thread_workspace_hints_removed") or 0)
        removed_output_dirs = int(keep_global_cleanup.get("thread_projectless_output_directories_removed") or 0)
        removed_prompts = int(keep_global_cleanup.get("prompt_history_threads_removed") or 0)
        if removed_threads or removed_hints or removed_output_dirs or removed_prompts:
            action = "会清理" if dry_run else "已清理"
            lines.append(
                f"全局状态非保留集残留：{action} projectless {removed_threads} 个、"
                f"workspace hint {removed_hints} 个、output directory {removed_output_dirs} 个、"
                f"prompt-history {removed_prompts} 个"
            )
    if selected_global_cleanup:
        removed_threads = int(selected_global_cleanup.get("projectless_thread_ids_removed") or 0)
        removed_hints = int(selected_global_cleanup.get("thread_workspace_hints_removed") or 0)
        removed_output_dirs = int(selected_global_cleanup.get("thread_projectless_output_directories_removed") or 0)
        removed_prompts = int(selected_global_cleanup.get("prompt_history_threads_removed") or 0)
        if removed_threads or removed_hints or removed_output_dirs or removed_prompts:
            action = "会清理" if dry_run else "已清理"
            lines.append(
                f"全局状态关联残留：{action} projectless {removed_threads} 个、"
                f"workspace hint {removed_hints} 个、output directory {removed_output_dirs} 个、"
                f"prompt-history {removed_prompts} 个"
            )
    if global_cleanup:
        removed_threads = int(global_cleanup.get("projectless_thread_ids_removed") or 0)
        removed_hints = int(global_cleanup.get("thread_workspace_hints_removed") or 0)
        removed_output_dirs = int(global_cleanup.get("thread_projectless_output_directories_removed") or 0)
        if dry_run:
            lines.append(
                f"全局项目状态：会清理 stale 线程 {removed_threads} 个、"
                f"workspace hint {removed_hints} 个、output directory {removed_output_dirs} 个"
            )
        else:
            lines.append(f"全局项目状态：{'已修改' if global_cleanup.get('modified') else '无需修改'}")
    elif global_health and not simple_archived_sqlite:
        stale_threads = int(global_health.get("stale_projectless_thread_ids") or 0)
        stale_hints = int(global_health.get("stale_thread_workspace_hints") or 0)
        stale_output_dirs = int(global_health.get("stale_thread_projectless_output_directories") or 0)
        if stale_threads or stale_hints or stale_output_dirs:
            lines.append(
                f"全局项目状态：有 stale 线程 {stale_threads} 个、"
                f"workspace hint {stale_hints} 个、output directory {stale_output_dirs} 个"
            )
        else:
            lines.append("全局项目状态：正常")

    if transcripts and not simple_archived_sqlite:
        missing = int(transcripts.get("missing_thread_rollout_files") or 0)
        ordinary_orphans = int(transcripts.get("orphan_transcript_files") or 0) - int(transcripts.get("orphan_archived_transcript_files") or 0)
        if missing:
            lines.append(f"普通会话 transcript：有 {missing} 条线程记录找不到文件")
        if ordinary_orphans:
            lines.append(f"普通会话孤儿 transcript：{ordinary_orphans} 个，脚本不会自动删除")

    if not actions.get("delete_not_in_keep"):
        review = health.get("review_candidates", {}) if isinstance(health.get("review_candidates"), dict) else {}
        cli_count = int(review.get("cli_thread_count") or 0)
        if cli_count:
            lines.append(f"CLI 会话候选：{cli_count} 条，仅列出不自动删除{render_thread_samples(review.get('cli_samples'))}")
        bad_count = int(review.get("missing_transcript_thread_count") or 0)
        if bad_count:
            lines.append(
                f"坏会话记录候选：{bad_count} 条，DB 有线程但 transcript 缺失，仅列出不自动删除"
                f"{render_thread_samples(review.get('missing_transcript_samples'))}"
            )

    missing_projects = health.get("missing_projects", {}) if isinstance(health.get("missing_projects"), dict) else {}
    missing_project_count = int(missing_projects.get("missing_project_thread_count") or 0)
    if missing_project_count:
        samples = missing_projects.get("samples", [])
        sample_text = ""
        if isinstance(samples, list) and samples:
            rendered = [
                f"{item.get('id_prefix')} {item.get('title')} [{item.get('project')}]"
                for item in samples
                if isinstance(item, dict)
            ]
            sample_text = "：" + "；".join(rendered[:3])
        lines.append(f"项目目录不存在的会话：{missing_project_count} 条，仅列出不自动删除{sample_text}")

    if simple_archived_sqlite:
        search_residual = 0
        global_stale_threads = 0
        global_stale_hints = 0
        global_stale_output_dirs = 0
        global_samples = []
    else:
        search_residual = int(health_index.get("stale_thread_id_records") or 0) or (stale_index if dry_run else 0)
        if global_cleanup:
            global_stale_threads = int(global_cleanup.get("projectless_thread_ids_removed") or 0)
            global_stale_hints = int(global_cleanup.get("thread_workspace_hints_removed") or 0)
            global_stale_output_dirs = int(global_cleanup.get("thread_projectless_output_directories_removed") or 0)
            global_samples = list(global_cleanup.get("projectless_thread_samples_removed") or [])
            global_samples.extend(global_cleanup.get("thread_workspace_hint_samples_removed") or [])
            global_samples.extend(global_cleanup.get("thread_projectless_output_directory_samples_removed") or [])
        else:
            global_stale_threads = int(global_health.get("stale_projectless_thread_ids") or 0)
            global_stale_hints = int(global_health.get("stale_thread_workspace_hints") or 0)
            global_stale_output_dirs = int(global_health.get("stale_thread_projectless_output_directories") or 0)
            global_samples = list(global_health.get("stale_projectless_thread_samples") or [])
            global_samples.extend(global_health.get("stale_thread_workspace_hint_samples") or [])
            global_samples.extend(global_health.get("stale_thread_projectless_output_directory_samples") or [])
    residual_parts: list[str] = []
    if search_residual:
        residual_parts.append(f"搜索索引 stale {search_residual} 条")
    if global_stale_threads or global_stale_hints or global_stale_output_dirs:
        residual_parts.append(
            f"全局状态 stale 线程 {global_stale_threads} 个、workspace hint {global_stale_hints} 个、"
            f"output directory {global_stale_output_dirs} 个"
        )
    if residual_parts:
        lines.append("搜索/全局状态残留：" + "；".join(residual_parts))
        if health_index.get("stale_thread_samples"):
            lines.append("搜索索引 stale 会话示例" + render_thread_samples(health_index.get("stale_thread_samples"), limit=8))
        if global_samples:
            lines.append("全局 stale 会话示例" + render_thread_samples(global_samples, limit=8))
        if global_stale_threads or global_stale_hints or global_stale_output_dirs:
            if actions.get("delete_not_in_keep"):
                lines.append("退出 Codex 后执行：使用同一条 UI 保留集命令，把 --dry-run 换成 --execute，并加 --require-codex-exited-for-global-state。")
            else:
                lines.append("退出 Codex 后可选执行：" + optional_global_cleanup_command(str(summary.get("codex_home") or Path.home() / ".codex")))

    would_change = any(
        [
            selected_thread_count,
            index_removed,
            db_orphans_before,
            archived and int(archived.get("unreferenced_archived_transcript_files") or 0),
            selected_global_cleanup and bool(selected_global_cleanup.get("would_modify")),
            keep_global_cleanup and bool(keep_global_cleanup.get("would_modify")),
            global_cleanup and bool(global_cleanup.get("would_modify")),
        ]
    )
    needs_codex_exit = bool(
        (selected_global_cleanup and selected_global_cleanup.get("would_modify"))
        or (keep_global_cleanup and keep_global_cleanup.get("would_modify"))
        or (global_cleanup and global_cleanup.get("would_modify"))
    )
    if sqlite_bad:
        lines.append("结论：SQLite 主库还有风险，先不要升级或继续清理，需看 JSON 详情。")
    elif dry_run and would_change:
        if needs_codex_exit:
            lines.append("结论：涉及全局项目状态，建议完全退出 Codex 后把 --dry-run 换成 --execute 执行。")
        else:
            lines.append("结论：可以把 --dry-run 换成 --execute 执行。")
    elif dry_run and any(actions.values()):
        lines.append("结论：这次预览没有发现这些参数需要修改的内容。")
    elif dry_run:
        lines.append("结论：主 SQLite 状态正常；如要清理 stale 项，带上对应 clean 参数再预览/执行。")
    else:
        lines.append("结论：执行完成。重新打开 Codex 后检查项目列表和搜索结果。")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    if args.archived_sqlite_cleanup:
        args.all_archived = True
        args.repair_thread_orphans = True
        args.clean_stale_index = True
        args.summary = True

    execute = bool(args.execute)
    if args.dry_run and args.execute:
        raise SystemExit("Use either --dry-run or --execute, not both.")
    if args.all_except_current and not args.current_thread_id:
        raise SystemExit("--all-except-current requires --current-thread-id.")
    if args.delete_not_in_keep and not args.keep_ids:
        raise SystemExit("--delete-not-in-keep requires --keep-ids.")
    if args.delete_not_in_keep and (args.all_archived or args.all_except_current or args.ids or args.title_contains or args.scrub_file):
        raise SystemExit("--delete-not-in-keep cannot be combined with other thread selectors or --scrub-file.")

    codex_home = Path(args.codex_home).expanduser()
    dbs = state_dbs(codex_home)
    if not dbs:
        raise SystemExit(f"No state_*.sqlite databases found in {codex_home}")

    db_rows = {db_path: fetch_threads(db_path) for db_path in dbs}
    all_rows = [row for rows in db_rows.values() for row in rows]
    parent_by_child = spawn_parent_map(dbs)
    validate_id_selectors(all_rows, args)

    keep_ids_all: set[str] = set()
    keep_ids_by_db: dict[Path, set[str]] = {}
    keep_labels = parse_keep_labels(args.keep_label)
    if args.delete_not_in_keep:
        base_keep_ids = resolve_id_terms(
            all_rows,
            args.keep_ids,
            allow_ambiguous_ids=args.allow_ambiguous_ids,
            allow_missing_full_ids=True,
        )
        keep_ids_all.update(base_keep_ids)
        for db_path in dbs:
            keep_ids = set(base_keep_ids)
            if not args.no_keep_spawn_children:
                keep_ids = expand_keep_ids_with_spawn_children(db_path, keep_ids)
            keep_ids_by_db[db_path] = keep_ids
            keep_ids_all.update(keep_ids)

    clean_archived_files = args.clean_archived_files or args.all_archived or args.delete_not_in_keep
    selectors_used = args.all_archived or args.all_except_current or args.ids or args.title_contains or args.delete_not_in_keep
    actions_used = (
        selectors_used
        or args.scrub_file
        or args.repair_thread_orphans
        or args.clean_stale_index
        or args.clean_global_state
        or clean_archived_files
    )
    if execute and args.require_codex_exited_for_global_state and (selectors_used or args.clean_global_state or clean_archived_files):
        process_report = codex_desktop_process_report()
        if process_report.get("running"):
            raise SystemExit(
                "Codex desktop appears to be running; close Codex before executing cleanup that changes .codex-global-state.json. "
                f"Detected: {process_report.get('matches')}"
            )
    mode = "execute" if execute else "dry-run"
    summary: dict[str, Any] = {
        "mode": mode,
        "codex_home": str(codex_home),
        "actions_requested": {
            "archived_sqlite_cleanup": bool(args.archived_sqlite_cleanup),
            "delete_not_in_keep": bool(args.delete_not_in_keep),
            "selectors_used": bool(selectors_used),
            "clean_archived_files": bool(clean_archived_files),
            "repair_thread_orphans": bool(args.repair_thread_orphans),
            "clean_stale_index": bool(args.clean_stale_index),
            "clean_global_state": bool(args.clean_global_state),
            "scrub_file": bool(args.scrub_file),
        },
        "databases": [],
    }
    if args.delete_not_in_keep:
        keep_samples = describe_thread_ids(keep_ids_all, all_rows, limit=50, parent_by_child=parent_by_child)
        summary["keep_set"] = {
            "keep_thread_count": len(keep_ids_all),
            "keep_id_prefixes": [thread_id[:12] for thread_id in sorted(keep_ids_all)[:25]],
            "keep_samples": apply_keep_labels(keep_samples, keep_labels),
            "spawn_children_preserved": not args.no_keep_spawn_children,
        }
        summary["external_execute_command"] = ui_keep_set_execute_command(args, codex_home)

    backup_done: set[Path] = set()
    selected_all: list[ThreadRow] = []
    for db_path, rows in db_rows.items():
        selected = select_threads(rows, args, keep_ids_by_db.get(db_path))
        selected_all.extend(selected)
        db_report: dict[str, Any] = {
            "db": db_path.name,
            "thread_count": len(rows),
            "selected_count": len(selected),
            "selected_id_prefixes": [row.id[:12] for row in selected],
            "selected_samples": describe_thread_rows(selected, limit=50, parent_by_child=parent_by_child),
            "selected_existing_session_files": count_existing_rollouts(codex_home, selected),
        }
        if args.delete_not_in_keep:
            db_report["keep_count"] = len(keep_ids_by_db.get(db_path, set()))
            db_report["keep_id_prefixes"] = [thread_id[:12] for thread_id in sorted(keep_ids_by_db.get(db_path, set()))[:25]]
        if args.show_full_ids:
            db_report["selected_ids"] = [row.id for row in selected]
        if execute and selected:
            if not args.no_backup and db_path not in backup_done:
                db_report["backups"] = backup_sqlite_family(db_path)
                backup_done.add(db_path)
            db_report["removed_thread_rows"] = delete_threads(db_path, selected)
        existing_orphans = with_readonly_db(db_path, thread_fk_orphan_counts)
        if execute and args.repair_thread_orphans and existing_orphans:
            if not args.no_backup and db_path not in backup_done:
                db_report["backups"] = backup_sqlite_family(db_path)
                backup_done.add(db_path)
            db_report["removed_thread_fk_orphans"] = repair_thread_fk_orphans(db_path)
        elif execute and args.repair_thread_orphans:
            db_report["removed_thread_fk_orphans"] = {}
        else:
            db_report["thread_fk_orphans"] = existing_orphans
        summary["databases"].append(db_report)

    if execute and selected_all:
        summary["removed_selected_session_files"] = sum(1 for row in selected_all if remove_file(codex_home, row.rollout_path))

    # Refresh rows after DB mutations before cleaning unreferenced files or stale global state.
    db_rows_after = {db_path: fetch_threads(db_path) for db_path in dbs}
    rows_after = [row for rows in db_rows_after.values() for row in rows]
    thread_ids_after = {row.id for row in rows_after}

    stale_ids: set[str] = set()
    if args.clean_stale_index:
        stale_ids = stale_index_thread_ids(codex_home, thread_ids_after)
        if args.archived_sqlite_cleanup:
            archived_candidates, _, _, _ = unreferenced_archived_files(codex_home, rows_after)
            archived_cleanup_ids = {row.id for row in selected_all}
            archived_cleanup_ids.update(
                thread_id
                for path in archived_candidates
                if (thread_id := rollout_file_thread_id(path))
            )
            stale_ids &= archived_cleanup_ids
    summary["session_index"] = clean_session_index(
        codex_home,
        selected_all,
        stale_ids,
        execute,
        args.no_backup,
        keep_ids_all if args.delete_not_in_keep else None,
    )

    if clean_archived_files:
        archived_candidates_for_global_state, _, _, _ = unreferenced_archived_files(
            codex_home,
            rows_after,
            keep_ids_all if args.delete_not_in_keep else None,
        )
    else:
        archived_candidates_for_global_state = []

    global_state_selected_ids = {row.id for row in selected_all}
    global_state_selected_ids.update(
        thread_id
        for path in archived_candidates_for_global_state
        if (thread_id := rollout_file_thread_id(path))
    )
    if args.delete_not_in_keep:
        summary["global_state_keep_cleanup"] = clean_global_state_not_in_keep(
            codex_home,
            keep_ids_all,
            execute,
            args.no_backup,
        )
    elif global_state_selected_ids:
        summary["global_state_selected_cleanup"] = clean_global_state_for_thread_ids(
            codex_home,
            global_state_selected_ids,
            execute,
            args.no_backup,
        )

    if clean_archived_files:
        summary["archived_files"] = clean_unreferenced_archived_files(
            codex_home,
            rows_after,
            execute,
            keep_ids_all if args.delete_not_in_keep else None,
        )

    if args.clean_global_state:
        summary["global_state_cleanup"] = clean_global_state(codex_home, thread_ids_after, execute, args.no_backup)

    if args.scrub_file:
        scrub_path = Path(args.scrub_file).expanduser()
        if execute and not args.no_backup:
            summary["scrub_backup"] = str(backup(scrub_path))
        scrub_total, scrub_removed = scrub_file(scrub_path, selected_all, args.title_contains, execute)
        summary["scrub_file_lines"] = scrub_total
        summary["scrub_file_removed"] = scrub_removed

    if not args.skip_health_check:
        # Re-read rows so health reflects file and DB cleanup effects.
        final_rows = {db_path: fetch_threads(db_path) for db_path in dbs}
        summary["health"] = health_report(codex_home, final_rows, args.skip_logs_db)
    elif not actions_used:
        summary["state_dbs"] = [str(db_path) for db_path in dbs]

    if args.summary:
        print(render_summary(summary))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
