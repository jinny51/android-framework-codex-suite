import importlib.util
import json
import sys
from pathlib import Path


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
