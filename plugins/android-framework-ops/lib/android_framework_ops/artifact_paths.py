from __future__ import annotations

from pathlib import Path


def artifact_path_guard_error(path: Path, *, purpose: str = "output") -> str:
    resolved = path.expanduser().resolve()
    posix = resolved.as_posix()
    parts = resolved.parts
    forbidden_parts = {".git", "__pycache__", ".pytest_cache"}
    for part in parts:
        if part in forbidden_parts:
            return f"{purpose} 不能写入源码或缓存目录: {resolved}"
    if "/.codex/skills/" in posix:
        return f"{purpose} 不能写入 Codex skill 安装目录: {resolved}"
    if "/.codex/plugins/cache/" in posix and "/skills/" in posix:
        return f"{purpose} 不能写入 Codex 插件缓存 skill 目录: {resolved}"
    for index in range(0, max(0, len(parts) - 2)):
        if parts[index] == "plugins" and parts[index + 2] == "skills":
            return f"{purpose} 不能写入插件 skill 源码目录: {resolved}"
    for index, part in enumerate(parts[:-1]):
        if part == "skills" and parts[index + 1].startswith("akbs-"):
            return f"{purpose} 不能写入 AKBS 管理 skill 源码目录: {resolved}"
    return ""


def require_safe_artifact_path(path: Path, *, purpose: str = "output") -> Path:
    resolved = path.expanduser().resolve()
    error = artifact_path_guard_error(resolved, purpose=purpose)
    if error:
        raise SystemExit(error)
    return resolved
