import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "clean_codex_history.py"
SPEC = importlib.util.spec_from_file_location("clean_codex_history", SCRIPT)
clean_codex_history = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = clean_codex_history
SPEC.loader.exec_module(clean_codex_history)


def write_global_state(codex_home: Path, data: dict) -> None:
    codex_home.mkdir(exist_ok=True)
    (codex_home / ".codex-global-state.json").write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )


def make_state_db(path: Path) -> None:
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
            create table thread_spawn_edges (
                parent_thread_id text not null,
                child_thread_id text not null primary key,
                status text not null
            );
            """
        )
        rows = [
            ("019e0000-0000-7000-8000-000000000001", "UI parent", 0, "", "", "user", 10, 10),
            ("019e0000-0000-7000-8000-000000000002", "UI child", 0, "", "", "subagent", 9, 9),
            ("019e0000-0000-7000-8000-000000000003", "old parent", 0, "", "", "user", 8, 8),
            ("019e0000-0000-7000-8000-000000000004", "old child", 0, "", "", "subagent", 7, 7),
        ]
        conn.executemany("insert into threads values (?,?,?,?,?,?,?,?)", rows)
        conn.executemany(
            "insert into thread_spawn_edges values (?,?,?)",
            [
                ("019e0000-0000-7000-8000-000000000001", "019e0000-0000-7000-8000-000000000002", "open"),
                ("019e0000-0000-7000-8000-000000000003", "019e0000-0000-7000-8000-000000000004", "open"),
            ],
        )


def test_delete_not_in_keep_preserves_spawn_children(tmp_path: Path) -> None:
    db_path = tmp_path / "state_5.sqlite"
    make_state_db(db_path)
    rows = clean_codex_history.fetch_threads(db_path)

    keep = clean_codex_history.resolve_id_terms(rows, ["019e0000-0000-7000-8000-000000000001"])
    keep = clean_codex_history.expand_keep_ids_with_spawn_children(db_path, keep)
    args = SimpleNamespace(delete_not_in_keep=True)
    selected = clean_codex_history.select_threads(rows, args, keep)

    assert keep == {
        "019e0000-0000-7000-8000-000000000001",
        "019e0000-0000-7000-8000-000000000002",
    }
    assert {row.id for row in selected} == {
        "019e0000-0000-7000-8000-000000000003",
        "019e0000-0000-7000-8000-000000000004",
    }


def test_clean_session_index_delete_not_in_keep(tmp_path: Path) -> None:
    keep_parent = "019e0000-0000-7000-8000-000000000001"
    keep_child = "019e0000-0000-7000-8000-000000000002"
    old_thread = "019e0000-0000-7000-8000-000000000003"
    index = tmp_path / "session_index.jsonl"
    index.write_text(
        "\n".join(
            json.dumps({"thread_id": thread_id, "thread_name": thread_id})
            for thread_id in (keep_parent, keep_child, old_thread)
        )
        + "\n",
        encoding="utf-8",
    )

    report = clean_codex_history.clean_session_index(
        tmp_path,
        selected=[],
        stale_thread_ids=set(),
        execute=True,
        no_backup=True,
        delete_not_in_keep_ids={keep_parent, keep_child},
    )
    kept = [json.loads(line)["thread_id"] for line in index.read_text(encoding="utf-8").splitlines()]

    assert report["not_in_keep_records_removed"] == 1
    assert kept == [keep_parent, keep_child]


def test_unreferenced_archived_files_skips_protected_keep_ids(tmp_path: Path) -> None:
    keep = "019e0000-0000-7000-8000-000000000001"
    old = "019e0000-0000-7000-8000-000000000003"
    arch = tmp_path / "archived_sessions"
    arch.mkdir()
    keep_file = arch / f"rollout-2026-06-01T00-00-00-{keep}.jsonl"
    old_file = arch / f"rollout-2026-06-01T00-00-00-{old}.jsonl"
    keep_file.write_text(json.dumps({"payload": {"id": keep}}) + "\n", encoding="utf-8")
    old_file.write_text(json.dumps({"payload": {"id": old}}) + "\n", encoding="utf-8")

    candidates, directly_referenced, archived_count, protected = clean_codex_history.unreferenced_archived_files(
        tmp_path,
        rows=[],
        protected_thread_ids={keep},
    )

    assert archived_count == 2
    assert protected == 1
    assert directly_referenced == 0
    assert candidates == [old_file]


def test_clean_global_state_not_in_keep_removes_thread_keyed_residue(tmp_path: Path) -> None:
    keep = "019e0000-0000-7000-8000-000000000001"
    old = "019e0000-0000-7000-8000-000000000003"
    state = {
        "projectless-thread-ids": [keep, old],
        "thread-workspace-root-hints": {
            keep: "/tmp/keep",
            old: "/tmp/old",
        },
        "electron-persisted-atom-state": {
            "prompt-history": {
                keep: ["keep prompt"],
                old: ["old prompt"],
                "new-conversation": ["keep new conversation"],
            }
        },
    }
    write_global_state(tmp_path, state)

    report = clean_codex_history.clean_global_state_not_in_keep(
        tmp_path,
        {keep},
        execute=True,
        no_backup=True,
    )
    cleaned = json.loads((tmp_path / ".codex-global-state.json").read_text(encoding="utf-8"))

    assert report["projectless_thread_ids_removed"] == 1
    assert report["thread_workspace_hints_removed"] == 1
    assert report["prompt_history_threads_removed"] == 1
    assert cleaned["projectless-thread-ids"] == [keep]
    assert cleaned["thread-workspace-root-hints"] == {keep: "/tmp/keep"}
    assert cleaned["electron-persisted-atom-state"]["prompt-history"] == {
        keep: ["keep prompt"],
        "new-conversation": ["keep new conversation"],
    }


def test_global_state_health_ignores_old_wsl_paths(tmp_path: Path) -> None:
    write_global_state(
        tmp_path,
        {
            "electron-saved-workspace-roots": [
                r"\\wsl$\Ubuntu\home\jinny\work",
            ],
            "project-order": [],
            "active-workspace-roots": [],
            "projectless-thread-ids": [],
            "thread-workspace-root-hints": {},
        },
    )

    report = clean_codex_history.global_state_health(tmp_path, [])

    assert "old_wsl_dollar_occurrences" not in report
    assert "wsl_localhost_occurrences" not in report


def test_clean_global_state_does_not_rewrite_old_wsl_paths(tmp_path: Path) -> None:
    state = {
        "electron-saved-workspace-roots": [
            r"\\wsl$\Ubuntu\home\jinny\work",
        ],
        "project-order": [
            r"\\wsl$\Ubuntu\home\jinny\work",
        ],
        "active-workspace-roots": [
            r"\\wsl$\Ubuntu\home\jinny\work",
        ],
        "projectless-thread-ids": [],
        "thread-workspace-root-hints": {},
    }
    write_global_state(tmp_path, state)

    report = clean_codex_history.clean_global_state(
        tmp_path,
        thread_ids=set(),
        execute=False,
        no_backup=True,
    )

    assert report["would_modify"] is False
    assert not any(key.endswith("_old_wsl_entries") for key in report)
    assert not any(key.endswith("_removed_or_merged") for key in report)


def test_clean_global_state_for_ids_removes_only_selected_thread_residue(tmp_path: Path) -> None:
    selected = "019e61f2-f01a-7000-8000-000000000001"
    other = "019e5f00-ba4b-7000-8000-000000000002"
    state = {
        "projectless-thread-ids": [selected, other],
        "thread-workspace-root-hints": {
            selected: "/tmp/selected",
            other: "/tmp/other",
        },
        "electron-persisted-atom-state": {
            "prompt-history": {
                selected: ["selected prompt"],
                other: ["other prompt"],
                "new-conversation": ["keep this"],
            }
        },
    }
    write_global_state(tmp_path, state)

    report = clean_codex_history.clean_global_state_for_thread_ids(
        tmp_path,
        {selected},
        execute=True,
        no_backup=True,
    )
    cleaned = json.loads((tmp_path / ".codex-global-state.json").read_text(encoding="utf-8"))

    assert report["would_modify"] is True
    assert report["projectless_thread_ids_removed"] == 1
    assert report["thread_workspace_hints_removed"] == 1
    assert report["prompt_history_threads_removed"] == 1
    assert cleaned["projectless-thread-ids"] == [other]
    assert cleaned["thread-workspace-root-hints"] == {other: "/tmp/other"}
    assert cleaned["electron-persisted-atom-state"]["prompt-history"] == {
        other: ["other prompt"],
        "new-conversation": ["keep this"],
    }


def test_clean_global_state_for_ids_noops_when_selected_thread_absent(tmp_path: Path) -> None:
    selected = "019e61f2-f01a-7000-8000-000000000001"
    other = "019e5f00-ba4b-7000-8000-000000000002"
    state = {
        "projectless-thread-ids": [other],
        "thread-workspace-root-hints": {other: "/tmp/other"},
        "electron-persisted-atom-state": {
            "prompt-history": {
                other: ["other prompt"],
                "new-conversation": ["keep this"],
            }
        },
    }
    write_global_state(tmp_path, state)

    report = clean_codex_history.clean_global_state_for_thread_ids(
        tmp_path,
        {selected},
        execute=True,
        no_backup=True,
    )
    cleaned = json.loads((tmp_path / ".codex-global-state.json").read_text(encoding="utf-8"))

    assert report["would_modify"] is False
    assert cleaned == state
