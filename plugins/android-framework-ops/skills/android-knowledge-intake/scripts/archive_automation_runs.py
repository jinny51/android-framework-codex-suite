#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def default_codex_home() -> str:
    if os.environ.get("CODEX_HOME"):
        return os.environ["CODEX_HOME"]
    return str(Path.home() / ".codex")


def expanded_path(value: str) -> Path:
    codex_home = default_codex_home()
    expanded = str(value).replace("${CODEX_HOME}", codex_home).replace("$CODEX_HOME", codex_home)
    return Path(os.path.expandvars(expanded)).expanduser()


def same_path(left: str | None, right: Path) -> bool:
    if not left:
        return False
    try:
        return Path(left).resolve() == right.resolve()
    except OSError:
        return os.path.normpath(left) == os.path.normpath(str(right))


def now_ms() -> int:
    return int(time.time() * 1000)


def archive_runs(args: argparse.Namespace) -> dict[str, object]:
    if args.delay_seconds > 0:
        time.sleep(args.delay_seconds)

    codex_home = expanded_path(args.codex_home)
    db_path = codex_home / "sqlite" / "codex-dev.db"
    if not db_path.exists():
        raise SystemExit(f"Codex database not found: {db_path}")

    source_cwd = expanded_path(args.source_cwd) if args.source_cwd else PLUGIN_ROOT
    cutoff = now_ms() - (args.max_age_seconds * 1000)
    archived: list[str] = []

    con = sqlite3.connect(db_path, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT thread_id, source_cwd
            FROM automation_runs
            WHERE automation_id = ?
              AND status IN ('PENDING_REVIEW', 'IN_PROGRESS')
              AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.automation_id, cutoff, args.limit),
        ).fetchall()

        stamp = now_ms()
        for row in rows:
            if not same_path(row["source_cwd"], source_cwd):
                continue
            con.execute("DELETE FROM inbox_items WHERE thread_id = ?", (row["thread_id"],))
            con.execute(
                """
                UPDATE automation_runs
                SET status = 'ARCHIVED',
                    read_at = COALESCE(read_at, ?),
                    inbox_title = NULL,
                    inbox_summary = NULL,
                    updated_at = ?,
                    archived_reason = COALESCE(archived_reason, 'auto')
                WHERE thread_id = ?
                """,
                (stamp, stamp, row["thread_id"]),
            )
            archived.append(row["thread_id"])
        con.commit()
    finally:
        con.close()

    return {
        "automation_id": args.automation_id,
        "source_cwd": str(source_cwd),
        "archived": archived,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive completed Codex automation runs for this skill.")
    parser.add_argument("--automation-id", required=True)
    parser.add_argument("--codex-home", default="${CODEX_HOME}")
    parser.add_argument("--source-cwd", default="")
    parser.add_argument("--delay-seconds", type=int, default=0)
    parser.add_argument("--max-age-seconds", type=int, default=1800)
    parser.add_argument("--limit", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    print(json.dumps(archive_runs(parse_args()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
