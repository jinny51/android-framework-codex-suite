from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from android_framework_ops.patch_analysis import resource_keys_from_patch_text

AUTHOR_DATE_RE = re.compile(r"//[A-Za-z0-9_]+\s+\d{8}@")
BANNED_LOG_PATTERNS = (
    "Log.v(",
    "Log.d(",
    "Log.i(",
    "Log.w(",
    "Log.e(",
    "Slog.v(",
    "Slog.d(",
    "Slog.i(",
    "Slog.w(",
    "Slog.e(",
    "Slog.wtf(",
)
def run(cmd: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        errors="replace",
    )
    if check and cp.returncode != 0:
        raise SystemExit(cp.stderr.strip() or cp.stdout.strip() or f"command failed: {' '.join(cmd)}")
    return cp


def git_root(path: Path) -> Path:
    cp = run(["git", "rev-parse", "--show-toplevel"], path)
    if cp.returncode != 0:
        raise SystemExit("当前目录不是 git 仓库，无法生成补丁。")
    return Path(cp.stdout.strip()).resolve()


def slug(value: str, *, lower: bool = True) -> str:
    value = value.strip()
    if lower:
        value = value.lower()
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-._")
    return value or "unnamed"


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def changed_files_from_diff(diff_text: str) -> list[str]:
    files: list[str] = []
    for match in re.finditer(r"^diff --git a/(.+?) b/(.+)$", diff_text, re.M):
        old, new = match.group(1), match.group(2)
        path = new if new != "/dev/null" else old
        if path not in files:
            files.append(path)
    return files


def split_diff_sections(diff_text: str) -> list[str]:
    sections: list[str] = []
    current: list[str] = []
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git ") and current:
            sections.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("".join(current))
    return sections


def mode_only_diff_path(section: str) -> str:
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("diff --git "):
        return ""
    has_old_mode = any(line.startswith("old mode ") for line in lines)
    has_new_mode = any(line.startswith("new mode ") for line in lines)
    if not has_old_mode or not has_new_mode:
        return ""
    if not all(line.startswith(("diff --git ", "old mode ", "new mode ")) for line in lines):
        return ""
    match = re.match(r"^diff --git a/(.+?) b/(.+)$", lines[0])
    return match.group(2) if match else ""


def filter_mode_only_diff_sections(diff_text: str) -> tuple[str, list[str]]:
    kept: list[str] = []
    skipped_paths: list[str] = []
    for section in split_diff_sections(diff_text):
        path = mode_only_diff_path(section)
        if path:
            skipped_paths.append(path)
            continue
        kept.append(section)
    return "".join(kept), skipped_paths


def infer_module(files: list[str]) -> str:
    if not files:
        return "frameworks-base"
    first = files[0]
    rules = [
        ("frameworks/base/", "frameworks-base"),
        ("frameworks/native/", "frameworks-native"),
        ("packages/SystemUI/", "systemui"),
        ("packages/apps/Launcher", "launcher"),
        ("packages/apps/Settings/", "settings"),
        ("system/core/", "system-core"),
        ("frameworks/av/", "frameworks-av"),
    ]
    for prefix, module in rules:
        if first.startswith(prefix):
            return module
    parts = first.split("/")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return parts[0]


def added_lines(diff_text: str) -> list[str]:
    return [line[1:] for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++")]


def changed_lines(diff_text: str) -> list[str]:
    return [
        line[1:]
        for line in diff_text.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]


def facts_from_diff(diff_text: str) -> dict[str, Any]:
    files = changed_files_from_diff(diff_text)
    added = "\n".join(added_lines(diff_text))
    changed = "\n".join(changed_lines(diff_text))
    all_text = diff_text
    return {
        "content_sha1": sha1_text(diff_text),
        "modified_files": files,
        "system_properties": sorted(set(re.findall(r"\b(?:persist|ro|sys|debug|vendor)\.[A-Za-z0-9_.-]+", changed))),
        "settings_keys": sorted(set(re.findall(r"Settings\.(?:System|Secure|Global)\.([A-Za-z0-9_.-]+)", changed))),
        "resource_keys": resource_keys_from_patch_text(changed),
        "framework_log_keys": sorted(set(re.findall(r"FrameworkLog\.([A-Za-z0-9_]+)", changed))),
        "banned_log_hits": sorted(pattern for pattern in BANNED_LOG_PATTERNS if pattern in added),
        "author_date_marker_present": bool(AUTHOR_DATE_RE.search(all_text)),
    }


def git_metadata(root: Path) -> dict[str, str]:
    def output(args: list[str]) -> str:
        cp = run(["git", *args], root)
        return cp.stdout.strip() if cp.returncode == 0 else ""

    return {
        "root": str(root),
        "branch": output(["branch", "--show-current"]),
        "head": output(["rev-parse", "--short", "HEAD"]),
        "remote": output(["config", "--get", "remote.origin.url"]),
        "remotes": output(["remote", "-v"]),
        "status": output(["status", "--short"]),
    }


def unique_preserve(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))


def prefixed_files(repo_path: str, files: list[str]) -> list[str]:
    if not repo_path or repo_path == "unknown":
        return files
    prefix = repo_path.rstrip("/") + "/"
    return [path if path.startswith(prefix) else prefix + path for path in files]


def common_parent(paths: list[Path]) -> Path:
    if not paths:
        return Path.cwd().resolve()
    return Path(os.path.commonpath([str(path) for path in paths])).resolve()


def infer_repo_path_from_root(root: Path, roots: list[Path], files: list[str]) -> str:
    normalized_root = root.as_posix()
    known_paths = [
        "frameworks/base",
        "frameworks/native",
        "frameworks/av",
        "frameworks/proto_logging",
        "packages/apps/Settings",
        "packages/apps/Launcher3",
        "packages/SystemUI",
        "system/core",
        "device/mediatek/sepolicy/basic",
        "device/mediatek/vendor/common",
        "vendor/mediatek/proprietary/packages/apps/MtkSettings",
    ]
    for repo_path in known_paths:
        if normalized_root.endswith("/" + repo_path) or normalized_root.endswith(repo_path):
            return repo_path

    if len(roots) > 1:
        parent = common_parent(roots)
        try:
            rel = root.relative_to(parent).as_posix()
        except ValueError:
            rel = root.name
        if rel and rel != ".":
            return rel

    first = files[0] if files else ""
    if first.startswith("frameworks/base/") or first.startswith(("services/", "core/", "data/etc/")):
        return "frameworks/base"
    if first.startswith("frameworks/native/"):
        return "frameworks/native"
    if first.startswith("frameworks/av/"):
        return "frameworks/av"
    if first.startswith("packages/apps/Settings/") or first.startswith("src/com/android/settings/"):
        return "packages/apps/Settings"
    if first.startswith("packages/SystemUI/") or first.startswith("src/com/android/systemui/"):
        return "packages/SystemUI"
    if first.startswith("system/core/"):
        return "system/core"
    parts = first.split("/")
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return root.name or "unknown"


def infer_module_for_repo(repo_path: str, files: list[str]) -> str:
    repo_rules = {
        "frameworks/base": "frameworks-base",
        "frameworks/native": "frameworks-native",
        "frameworks/av": "frameworks-av",
        "frameworks/proto_logging": "frameworks-proto-logging",
        "packages/apps/Settings": "settings",
        "packages/apps/Launcher3": "launcher3",
        "packages/SystemUI": "systemui",
        "system/core": "system-core",
    }
    if repo_path in repo_rules:
        return repo_rules[repo_path]
    if repo_path and repo_path != "unknown":
        return slug(repo_path.replace("/", "-"))
    return slug(infer_module(files))
