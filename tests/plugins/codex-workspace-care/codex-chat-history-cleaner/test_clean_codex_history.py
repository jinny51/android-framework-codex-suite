import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "plugins" / "codex-workspace-care" / "skills" / "codex-chat-history-cleaner" / "scripts" / "clean_codex_history.py"
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


def test_selection_plan_is_pure_and_keeps_cross_db_order() -> None:
    parent = "019e0000-0000-7000-8000-000000000001"
    child = "019e0000-0000-7000-8000-000000000002"
    old_a = "019e0000-0000-7000-8000-000000000003"
    old_b = "019e0000-0000-7000-8000-000000000004"
    db_a = Path("state_a.sqlite")
    db_b = Path("state_b.sqlite")
    rows_by_db = {
        db_a: [
            clean_codex_history.ThreadRow(parent, "parent", 0, ""),
            clean_codex_history.ThreadRow(child, "child", 0, ""),
            clean_codex_history.ThreadRow(old_a, "old a", 0, ""),
        ],
        db_b: [clean_codex_history.ThreadRow(old_b, "old b", 0, "")],
    }
    edges_by_db = {db_a: [(parent, child)], db_b: []}
    args = SimpleNamespace(
        ids=[],
        allow_ambiguous_ids=False,
        delete_not_in_keep=True,
        keep_ids=[parent],
        no_keep_spawn_children=False,
    )
    original_rows = {db_path: list(rows) for db_path, rows in rows_by_db.items()}
    original_edges = {db_path: list(edges) for db_path, edges in edges_by_db.items()}

    plan = clean_codex_history.build_selection_plan(rows_by_db, edges_by_db, args)

    assert plan.keep_ids == {parent, child}
    assert plan.keep_ids_by_db == {
        db_a: frozenset({parent, child}),
        db_b: frozenset({parent}),
    }
    assert [row.id for row in plan.selected_by_db[db_a]] == [old_a]
    assert [row.id for row in plan.selected_by_db[db_b]] == [old_b]
    assert [row.id for row in plan.selected] == [old_a, old_b]
    assert plan.parent_by_child == {child: parent}
    assert rows_by_db == original_rows
    assert edges_by_db == original_edges


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
        "thread-projectless-output-directories": {
            keep: "/tmp/keep-out",
            old: "/tmp/old-out",
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
    assert report["thread_projectless_output_directories_removed"] == 1
    assert report["prompt_history_threads_removed"] == 1
    assert cleaned["projectless-thread-ids"] == [keep]
    assert cleaned["thread-workspace-root-hints"] == {keep: "/tmp/keep"}
    assert cleaned["thread-projectless-output-directories"] == {keep: "/tmp/keep-out"}
    assert cleaned["electron-persisted-atom-state"]["prompt-history"] == {
        keep: ["keep prompt"],
        "new-conversation": ["keep new conversation"],
    }


def test_global_state_health_reports_new_thread_keyed_output_dirs(tmp_path: Path) -> None:
    keep = "019e0000-0000-7000-8000-000000000001"
    old = "019e0000-0000-7000-8000-000000000003"
    write_global_state(
        tmp_path,
        {
            "projectless-thread-ids": [old],
            "thread-workspace-root-hints": {old: "/tmp/old"},
            "thread-projectless-output-directories": {
                keep: "/tmp/keep-out",
                old: "/tmp/old-out",
            },
        },
    )

    report = clean_codex_history.global_state_health(
        tmp_path,
        [clean_codex_history.ThreadRow(keep, "keep", 0, "", "", "vscode")],
    )

    assert report["stale_thread_projectless_output_directories"] == 1
    assert report["stale_thread_projectless_output_directory_prefixes"] == [old[:12]]


def test_sqlite_health_reports_non_fk_thread_reference_orphans(tmp_path: Path) -> None:
    db_path = tmp_path / "state_5.sqlite"
    keep = "019e0000-0000-7000-8000-000000000001"
    missing = "019e0000-0000-7000-8000-000000000099"
    with clean_codex_history.sqlite3.connect(db_path) as conn:
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
            create table agent_job_items (
                id integer primary key,
                assigned_thread_id text
            );
            """
        )
        conn.execute("insert into threads values (?,?,?,?,?,?,?,?)", (keep, "keep", 0, "", "", "vscode", 1, 1))
        conn.executemany(
            "insert into agent_job_items(assigned_thread_id) values (?)",
            [(keep,), (missing,)],
        )

    report = clean_codex_history.sqlite_health(db_path)

    assert report["thread_reference_orphans"] == {"agent_job_items.assigned_thread_id": 1}


def test_ui_keep_set_summary_reads_like_approval_plan() -> None:
    keep_parent = "019e0000-0000-7000-8000-000000000001"
    keep_child = "019e0000-0000-7000-8000-000000000002"
    keep_cli = "019e0000-0000-7000-8000-000000000003"
    old_parent = "019e0000-0000-7000-8000-000000000004"
    old_child = "019e0000-0000-7000-8000-000000000005"
    summary = {
        "mode": "dry-run",
        "actions_requested": {"delete_not_in_keep": True},
        "keep_set": {
            "keep_thread_count": 3,
            "spawn_children_preserved": True,
            "keep_samples": [
                {
                    "id": keep_parent,
                    "id_prefix": keep_parent[:12],
                    "title": "AKBS 主控",
                    "source": "UI",
                    "project": "knowledge",
                },
                {
                    "id": keep_child,
                    "id_prefix": keep_child[:12],
                    "title": "子智能体 Zeno",
                    "source": "subagent:Zeno",
                    "project": "knowledge",
                    "parent_id": keep_parent,
                },
                {"id": keep_cli, "id_prefix": keep_cli[:12], "title": "CLI", "source": "CLI", "project": "Codex"},
            ],
        },
        "databases": [
            {
                "selected_count": 2,
                "selected_samples": [
                    {"id": old_parent, "id_prefix": old_parent[:12], "title": "旧归档会话", "source": "UI", "project": "old"},
                    {
                        "id": old_child,
                        "id_prefix": old_child[:12],
                        "title": "子智能体 Avicenna",
                        "source": "subagent:Avicenna",
                        "project": "old",
                        "parent_id": old_parent,
                    },
                ],
            }
        ],
        "archived_files": {
            "unreferenced_archived_transcript_files": 4,
            "protected_archived_transcript_files_skipped": 1,
        },
        "session_index": {
            "selected_records_removed": 2,
            "not_in_keep_records_removed": 1,
        },
        "global_state_keep_cleanup": {
            "projectless_thread_ids_removed": 3,
            "thread_workspace_hints_removed": 2,
            "thread_projectless_output_directories_removed": 4,
            "prompt_history_threads_removed": 5,
            "would_modify": True,
        },
        "health": {
            "sqlite_primary_dbs": [
                {"db": "state_1.sqlite", "quick_check": "ok", "integrity_check": "ok", "foreign_key_violations": 0}
            ],
            "transcripts": {
                "missing_thread_rollout_files": 7,
                "orphan_transcript_files": 9,
                "orphan_archived_transcript_files": 4,
            },
            "session_index": {"parse_errors": 0},
        },
        "external_execute_command": (
            "python3 /tmp/clean_codex_history.py --codex-home /tmp/.codex "
            "--delete-not-in-keep --keep-ids "
            f"{keep_parent} {keep_cli} --keep-label '{keep_parent}=AKBS 主控' "
            "--execute --require-codex-exited-for-global-state --summary"
        ),
    }

    text = clean_codex_history.render_summary(summary)

    assert "Codex UI 保留集清理计划" in text
    assert "【保留，不会删除】" in text
    assert "AKBS 主控" in text
    assert f"  - {keep_parent[:12]} AKBS 主控" in text
    assert f"    - {keep_child[:12]} 子智能体 Zeno" in text
    assert "【计划删除/清理】" in text
    assert "DB 会话记录：将删除 2 条（不在 UI 保留集）" in text
    assert "旧归档会话" in text
    assert f"    - {old_child[:12]} 子智能体 Avicenna" in text
    assert "归档 transcript 残留：将删除 4 个文件" in text
    assert "搜索索引 session_index：将清理 关联待删会话 2 条、非保留集 1 条" in text
    assert ".codex-global-state.json" in text
    assert "output directory 4 个" in text
    assert "【不会自动删除，只提示】" in text
    assert "普通会话 transcript 缺文件：7 条，仅提示" in text
    assert "归档副本保护：跳过 UI 保留集相关文件 1 个，不删除" in text
    assert "【下一步】" in text
    assert "完全退出 Codex 桌面端" in text
    assert "【完整执行命令】" in text
    assert "--execute --require-codex-exited-for-global-state --summary" in text


def test_thread_row_sample_humanizes_subagent_metadata() -> None:
    source = json.dumps(
        {
            "subagent": {
                "thread_spawn": {
                    "parent_thread_id": "019e0000-0000-7000-8000-000000000001",
                    "agent_nickname": "Zeno",
                }
            }
        }
    )
    row = clean_codex_history.ThreadRow(
        "019e0000-0000-7000-8000-000000000002",
        "你是一个只读 UI 信息架构审视子智能体。\n请不要修改任何文件。" * 3,
        0,
        "",
        "/home/jinny/work/knowledge",
        source,
    )

    sample = clean_codex_history.thread_row_sample(row)

    assert sample["title"] == "子智能体 Zeno"
    assert sample["source"] == "subagent:Zeno"
    assert sample["project"] == "knowledge"
    assert "thread_spawn" not in sample["source"]


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
        "thread-projectless-output-directories": {
            selected: "/tmp/selected-out",
            other: "/tmp/other-out",
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
    assert report["thread_projectless_output_directories_removed"] == 1
    assert report["prompt_history_threads_removed"] == 1
    assert cleaned["projectless-thread-ids"] == [other]
    assert cleaned["thread-workspace-root-hints"] == {other: "/tmp/other"}
    assert cleaned["thread-projectless-output-directories"] == {other: "/tmp/other-out"}
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


def test_keep_set_dry_run_cli_plan_is_stable(tmp_path: Path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "state_5.sqlite"
    make_state_db(db_path)
    db_before = db_path.read_bytes()
    keep_parent = "019e0000-0000-7000-8000-000000000001"
    keep_child = "019e0000-0000-7000-8000-000000000002"
    old_parent = "019e0000-0000-7000-8000-000000000003"
    old_child = "019e0000-0000-7000-8000-000000000004"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--codex-home",
            str(tmp_path),
            "--delete-not-in-keep",
            "--keep-ids",
            keep_parent,
            "--dry-run",
            "--skip-health-check",
        ],
    )

    assert clean_codex_history.main() == 0
    payload = json.loads(capsys.readouterr().out)

    golden_plan = {
        "mode": payload["mode"],
        "actions_requested": payload["actions_requested"],
        "keep_ids": [item["id"] for item in payload["keep_set"]["keep_samples"]],
        "spawn_children_preserved": payload["keep_set"]["spawn_children_preserved"],
        "databases": [
            {
                "db": item["db"],
                "thread_count": item["thread_count"],
                "selected_ids": [sample["id"] for sample in item["selected_samples"]],
                "keep_count": item["keep_count"],
                "selected_existing_session_files": item["selected_existing_session_files"],
                "write_result_keys": sorted(
                    key
                    for key in item
                    if key in {"backups", "removed_thread_rows", "removed_thread_fk_orphans"}
                ),
            }
            for item in payload["databases"]
        ],
        "session_index": payload["session_index"],
        "global_state": {
            key: payload["global_state_keep_cleanup"][key]
            for key in ("exists", "keep_thread_count", "would_modify", "modified")
        },
        "archived_files": payload["archived_files"],
    }
    assert golden_plan == {
        "mode": "dry-run",
        "actions_requested": {
            "archived_sqlite_cleanup": False,
            "delete_not_in_keep": True,
            "selectors_used": True,
            "clean_archived_files": True,
            "repair_thread_orphans": False,
            "clean_stale_index": False,
            "clean_global_state": False,
            "scrub_file": False,
        },
        "keep_ids": [keep_parent, keep_child],
        "spawn_children_preserved": True,
        "databases": [
            {
                "db": "state_5.sqlite",
                "thread_count": 4,
                "selected_ids": [old_parent, old_child],
                "keep_count": 2,
                "selected_existing_session_files": 0,
                "write_result_keys": [],
            }
        ],
        "session_index": {
            "exists": False,
            "lines": 0,
            "parse_errors": 0,
            "selected_records_removed": 0,
            "stale_records_removed": 0,
            "not_in_keep_records_removed": 0,
        },
        "global_state": {
            "exists": False,
            "keep_thread_count": 2,
            "would_modify": False,
            "modified": False,
        },
        "archived_files": {
            "archived_transcript_files": 0,
            "unreferenced_archived_transcript_files": 0,
            "directly_referenced_files_skipped": 0,
            "protected_archived_transcript_files_skipped": 0,
            "deleted_archived_transcript_files": 0,
        },
    }
    assert db_path.read_bytes() == db_before
    assert not list(tmp_path.glob("*.bak-*"))
