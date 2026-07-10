from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath


@dataclass(frozen=True)
class ThreadRow:
    id: str
    title: str
    archived: int
    rollout_path: str
    cwd: str = ""
    source: str = ""
    updated_at_ms: int = 0
    updated_at: str = ""


def state_dbs(codex_home: Path) -> list[Path]:
    return sorted(codex_home.glob("state_*.sqlite"))


def rollout_files(codex_home: Path) -> list[Path]:
    files: list[Path] = []
    for root in (codex_home / "sessions", codex_home / "archived_sessions"):
        if root.exists():
            files.extend(root.glob("**/rollout-*.jsonl"))
    return sorted(files)


def resolve_rollout_path(codex_home: Path, path_text: str) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text).expanduser()
    if path.exists():
        return path

    name = PureWindowsPath(path_text).name if "\\" in path_text else path.name
    if not name:
        return path
    normalized = path_text.replace("\\", "/")
    wants_archived = "archived_sessions/" in normalized
    wants_sessions = "sessions/" in normalized and not wants_archived
    matches: list[Path] = []
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
    return matches[0] if len(matches) == 1 else path
