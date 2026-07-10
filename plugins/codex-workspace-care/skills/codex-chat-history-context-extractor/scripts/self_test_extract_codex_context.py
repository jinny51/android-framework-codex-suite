#!/usr/bin/env python3
"""Self-test the read-only Codex context extractor with synthetic local data."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("extract_codex_context.py")


def write_jsonl(path: Path) -> None:
    events = [
        {"item": {"role": "user", "content": [{"text": "Fix the build failure in module alpha."}]}},
        {"item": {"role": "assistant", "content": [{"text": "I found that alpha/config.py needs a path update."}]}},
        {"item": {"type": "tool_output", "output": "secret terminal output should be skipped by default"}},
        {"item": {"role": "user", "content": "Next, run the focused test."}},
    ]
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")


def create_codex_home(root: Path) -> tuple[Path, str]:
    codex_home = root / ".codex"
    rollout_dir = codex_home / "sessions" / "2026" / "05" / "20"
    rollout_dir.mkdir(parents=True)
    thread_id = "abcdef1234567890"
    rollout = rollout_dir / f"rollout-{thread_id}.jsonl"
    write_jsonl(rollout)

    db = codex_home / "state_5.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "create table threads (id text, title text, archived integer, rollout_path text, updated_at_ms integer, updated_at text)"
        )
        conn.execute(
            "insert into threads values (?, ?, ?, ?, ?, ?)",
            (thread_id, "Synthetic private title", 1, str(rollout), 1770000000000, "2026-05-20T00:00:00Z"),
        )
        conn.commit()
    return codex_home, thread_id


def run_cmd(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(SCRIPT), *args], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        codex_home, thread_id = create_codex_home(Path(tmp))

        inventory = json.loads(run_cmd("--codex-home", str(codex_home), "--inventory").stdout)
        assert inventory["thread_count"] == 1
        assert inventory["archived_thread_count"] == 1

        candidates = json.loads(run_cmd("--codex-home", str(codex_home), "--list-candidates").stdout)
        assert candidates["candidates"][0]["id_prefix"] == thread_id[:12]
        assert candidates["candidates"][0]["title_redacted"] is True
        assert "Synthetic private title" not in json.dumps(candidates)

        default_out = Path(tmp) / "default.md"
        run_cmd("--codex-home", str(codex_home), "--ids", thread_id[:8], "--output", str(default_out))
        default_text = default_out.read_text(encoding="utf-8")
        assert "Fix the build failure" in default_text
        assert "secret terminal output" not in default_text

        tool_out = Path(tmp) / "tool.md"
        run_cmd("--codex-home", str(codex_home), "--ids", thread_id[:8], "--include-tool-output", "--output", str(tool_out))
        assert "secret terminal output" in tool_out.read_text(encoding="utf-8")

        truncated_out = Path(tmp) / "truncated.md"
        run_cmd("--codex-home", str(codex_home), "--ids", thread_id[:8], "--max-chars", "140", "--output", str(truncated_out))
        assert "[Truncated by --max-chars]" in truncated_out.read_text(encoding="utf-8")

    print("self-test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
