from __future__ import annotations

from pathlib import Path


def _is_plugin_suite_source_root(path: Path) -> bool:
    return (
        (path / ".agents" / "plugins" / "marketplace.json").is_file()
        and (path / "plugins").is_dir()
        and (path / "manifests").is_dir()
    )


def _has_parts(parts: tuple[str, ...], sequence: tuple[str, ...]) -> bool:
    width = len(sequence)
    return any(parts[index : index + width] == sequence for index in range(len(parts) - width + 1))


def artifact_path_guard_error(path: Path, *, purpose: str = "output") -> str:
    resolved = path.expanduser().resolve()
    posix = resolved.as_posix()
    if any(part in {".git", "__pycache__", ".pytest_cache"} for part in resolved.parts):
        return f"{purpose} 不能写入源码或缓存目录: {resolved}"
    parts = resolved.parts
    if "/.codex/skills/" in posix or _has_parts(parts, ("skills", ".system")):
        return f"{purpose} 不能写入 Codex skill 安装目录: {resolved}"
    if "/.codex/plugins/cache/" in posix or _has_parts(parts, ("plugins", "cache")):
        return f"{purpose} 不能写入 Codex 插件缓存目录: {resolved}"
    for index in range(0, max(0, len(parts) - 2)):
        if parts[index] == "plugins" and parts[index + 2] == "skills":
            return f"{purpose} 不能写入插件 skill 源码目录: {resolved}"
    for ancestor in (resolved, *resolved.parents):
        if _is_plugin_suite_source_root(ancestor):
            return f"{purpose} 不能写入插件源码仓库: {resolved}"
    return ""


def require_safe_artifact_path(path: Path, *, purpose: str = "output") -> Path:
    resolved = path.expanduser().resolve()
    error = artifact_path_guard_error(resolved, purpose=purpose)
    if error:
        raise SystemExit(error)
    return resolved
