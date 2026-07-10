from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-workspace-care"
PLUGIN_LIB = PLUGIN_ROOT / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from codex_workspace_care.history import resolve_rollout_path, rollout_files, state_dbs


def test_history_store_discovery_is_shared(tmp_path: Path) -> None:
    state = tmp_path / "state_5.sqlite"
    state.touch()
    active = tmp_path / "sessions" / "2026" / "07" / "rollout-same.jsonl"
    archived = tmp_path / "archived_sessions" / "rollout-same.jsonl"
    active.parent.mkdir(parents=True)
    archived.parent.mkdir(parents=True)
    active.touch()
    archived.touch()

    assert state_dbs(tmp_path) == [state]
    assert rollout_files(tmp_path) == [archived, active]
    assert resolve_rollout_path(tmp_path, r"C:\old\.codex\sessions\2026\07\rollout-same.jsonl") == active
    assert resolve_rollout_path(tmp_path, r"C:\old\.codex\archived_sessions\rollout-same.jsonl") == archived


def test_history_entrypoints_do_not_reimplement_store_discovery() -> None:
    scripts = [
        PLUGIN_ROOT / "skills" / "codex-chat-history-cleaner" / "scripts" / "clean_codex_history.py",
        PLUGIN_ROOT / "skills" / "codex-chat-history-context-extractor" / "scripts" / "extract_codex_context.py",
    ]
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        assert "def state_dbs" not in text
        assert "def rollout_files" not in text
        assert "def resolve_rollout_path" not in text
