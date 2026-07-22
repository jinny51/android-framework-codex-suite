import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "codex-workspace-care"
    / "skills"
    / "codex-chat-history-cleaner"
    / "scripts"
    / "clean_codex_history.py"
)
SPEC = importlib.util.spec_from_file_location("clean_codex_history_failure_atomicity", SCRIPT)
clean_codex_history = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = clean_codex_history
SPEC.loader.exec_module(clean_codex_history)


KEEP_ID = "019e0000-0000-7000-8000-000000000001"
OLD_ID = "019e0000-0000-7000-8000-000000000003"
SECOND_OLD_ID = "019e0000-0000-7000-8000-000000000005"
ARCHIVED_ID = "019e0000-0000-7000-8000-000000000007"


def _make_db(path: Path, rows: list[tuple[str, str, str]]) -> None:
    with clean_codex_history.sqlite3.connect(path) as conn:
        conn.executescript(
            """
            create table threads (
                id text primary key,
                title text not null,
                archived integer not null default 0,
                rollout_path text not null,
                cwd text not null default '',
                source text not null default '',
                updated_at_ms integer,
                updated_at integer
            );
            """
        )
        conn.executemany(
            "insert into threads values (?,?,?,?,?,?,?,?)",
            [
                (thread_id, title, 0, rollout_path, "/tmp/project", "user", order, order)
                for order, (thread_id, title, rollout_path) in enumerate(rows, start=1)
            ],
        )


def _write_rollout(path: Path, thread_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"payload": {"id": thread_id}}) + "\n", encoding="utf-8")


def _make_execution_fixture(tmp_path: Path, *, two_dbs: bool = False) -> Path:
    codex_home = tmp_path / ".codex"
    sessions = codex_home / "sessions" / "2026" / "07"
    keep_rollout = sessions / f"rollout-keep-{KEEP_ID}.jsonl"
    old_rollout = sessions / f"rollout-old-{OLD_ID}.jsonl"
    archived_rollout = codex_home / "archived_sessions" / f"rollout-old-{ARCHIVED_ID}.jsonl"
    _write_rollout(keep_rollout, KEEP_ID)
    _write_rollout(old_rollout, OLD_ID)
    _write_rollout(archived_rollout, ARCHIVED_ID)
    _make_db(
        codex_home / "state_5.sqlite",
        [
            (KEEP_ID, "keep", str(keep_rollout)),
            (OLD_ID, "old", str(old_rollout)),
        ],
    )
    if two_dbs:
        second_rollout = sessions / f"rollout-old-{SECOND_OLD_ID}.jsonl"
        _write_rollout(second_rollout, SECOND_OLD_ID)
        _make_db(
            codex_home / "state_6.sqlite",
            [(SECOND_OLD_ID, "second old", str(second_rollout))],
        )

    index_ids = [KEEP_ID, OLD_ID, ARCHIVED_ID]
    if two_dbs:
        index_ids.append(SECOND_OLD_ID)
    (codex_home / "session_index.jsonl").write_text(
        "".join(json.dumps({"thread_id": thread_id}) + "\n" for thread_id in index_ids),
        encoding="utf-8",
    )
    (codex_home / ".codex-global-state.json").write_text(
        json.dumps(
            {
                "projectless-thread-ids": index_ids,
                "thread-workspace-root-hints": {
                    thread_id: f"/tmp/{thread_id}" for thread_id in index_ids
                },
                "thread-projectless-output-directories": {
                    thread_id: f"/tmp/out/{thread_id}" for thread_id in index_ids
                },
                "electron-persisted-atom-state": {
                    "prompt-history": {
                        **{thread_id: [thread_id] for thread_id in index_ids},
                        "new-conversation": ["keep"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return codex_home


def _authority_snapshot(codex_home: Path) -> dict[str, bytes]:
    paths = [
        *codex_home.glob("state_*.sqlite"),
        codex_home / "session_index.jsonl",
        codex_home / ".codex-global-state.json",
        *codex_home.glob("sessions/**/rollout-*.jsonl"),
        *codex_home.glob("archived_sessions/**/rollout-*.jsonl"),
    ]
    return {
        path.relative_to(codex_home).as_posix(): path.read_bytes()
        for path in sorted(set(paths))
        if path.exists() and path.is_file()
    }


def _execute_args(codex_home: Path) -> list[str]:
    return [
        str(SCRIPT),
        "--codex-home",
        str(codex_home),
        "--delete-not-in-keep",
        "--keep-ids",
        KEEP_ID,
        "--execute",
    ]


def _raise_fault(*_args, **_kwargs):
    raise RuntimeError("AKBS-DEBT-020 injected failure")


def test_first_backup_failure_aborts_before_any_authority_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = _make_execution_fixture(tmp_path)
    before = _authority_snapshot(codex_home)
    monkeypatch.setattr(sys, "argv", _execute_args(codex_home))
    monkeypatch.setattr(clean_codex_history, "backup_sqlite_family", _raise_fault)

    with pytest.raises(RuntimeError, match="injected failure"):
        clean_codex_history.main()

    assert _authority_snapshot(codex_home) == before


@pytest.mark.parametrize(
    "fault_target",
    [
        "clean_session_index",
        "clean_global_state_not_in_keep",
        "clean_unreferenced_archived_files",
        "health_report",
    ],
)
@pytest.mark.xfail(
    strict=True,
    reason="AKBS-BUG-06-PLUGIN-001: cross-artifact cleanup lacks rollback after a later failure",
)
def test_later_failure_restores_every_authority_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault_target: str,
) -> None:
    codex_home = _make_execution_fixture(tmp_path)
    before = _authority_snapshot(codex_home)
    monkeypatch.setattr(sys, "argv", _execute_args(codex_home))
    monkeypatch.setattr(clean_codex_history, fault_target, _raise_fault)

    with pytest.raises(RuntimeError, match="injected failure"):
        clean_codex_history.main()

    assert _authority_snapshot(codex_home) == before


@pytest.mark.xfail(
    strict=True,
    reason="AKBS-BUG-06-PLUGIN-001: a second SQLite failure leaves the first database committed",
)
def test_second_database_failure_restores_first_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = _make_execution_fixture(tmp_path, two_dbs=True)
    before = _authority_snapshot(codex_home)
    original_delete_threads = clean_codex_history.delete_threads
    calls = 0

    def fail_on_second_database(db_path, rows):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("AKBS-DEBT-020 injected failure")
        return original_delete_threads(db_path, rows)

    monkeypatch.setattr(sys, "argv", _execute_args(codex_home))
    monkeypatch.setattr(clean_codex_history, "delete_threads", fail_on_second_database)

    with pytest.raises(RuntimeError, match="injected failure"):
        clean_codex_history.main()

    assert calls == 2
    assert _authority_snapshot(codex_home) == before
