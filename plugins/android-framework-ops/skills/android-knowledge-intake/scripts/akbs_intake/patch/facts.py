from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from android_framework_ops.patch_analysis import (
    modules_from_files as patch_modules_from_files,
    resource_keys_from_patch_text,
    semantic_flags as patch_semantic_flags,
    semantic_keywords as patch_semantic_keywords,
    semantic_problem_solution as patch_semantic_problem_solution,
    semantic_risk_areas as patch_semantic_risk_areas,
)

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
def patch_modified_files(path: Path) -> list[str]:
    files: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        item = parts[3]
        if item.startswith("b/"):
            item = item[2:]
        if item not in files:
            files.append(item)
    return files


def patch_added_lines(text: str) -> list[str]:
    return [line[1:] for line in text.splitlines() if line.startswith("+") and not line.startswith("+++")]


def patch_changed_lines(text: str) -> list[str]:
    return [
        line[1:]
        for line in text.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]


def patch_symbols_from_text(text: str) -> list[str]:
    symbols: list[str] = []
    current_class = ""
    for raw in text.splitlines():
        if raw.startswith("+++ "):
            path = raw.removeprefix("+++ ").strip()
            if path.startswith("b/"):
                path = path[2:]
            current_class = Path(path).stem if path and path != "/dev/null" else ""
            continue
        if not raw.startswith("@@") or not current_class:
            continue
        match = re.match(r"^@@ .* @@\s*(.*)$", raw)
        context = match.group(1).strip() if match else ""
        methods = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", context)
        method = next((item for item in reversed(methods) if item not in {"if", "for", "while", "switch"}), "")
        if method:
            symbols.append(f"{current_class}.{method}")
    return sorted(set(symbols))


def patch_facts_from_text(text: str) -> dict[str, Any]:
    files = []
    for match in re.finditer(r"^diff --git a/(.+?) b/(.+)$", text, re.M):
        path = match.group(2)
        if path != "/dev/null" and path not in files:
            files.append(path)
    added = "\n".join(patch_added_lines(text))
    changed = "\n".join(patch_changed_lines(text))
    return {
        "modified_files": files,
        "symbols": patch_symbols_from_text(text),
        "system_properties": sorted(set(re.findall(r"\b(?:persist|ro|sys|debug|vendor)\.[A-Za-z0-9_.-]+", changed))),
        "settings_keys": sorted(set(re.findall(r"Settings\.(?:System|Secure|Global)\.([A-Za-z0-9_.-]+)", changed))),
        "resource_keys": resource_keys_from_patch_text(changed),
        "framework_log_keys": sorted(set(re.findall(r"FrameworkLog\.([A-Za-z0-9_]+)", changed))),
        "modules": patch_modules_from_files(files),
        "banned_log_hits": sorted(pattern for pattern in BANNED_LOG_PATTERNS if pattern in added),
        "author_date_marker_present": bool(AUTHOR_DATE_RE.search(text)),
    }


def patch_problem_and_risk_payloads(patch_id: str, source_patch: str, summary: str, facts: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    files = facts.get("modified_files") or []
    modules = facts.get("modules") or patch_modules_from_files(files)
    joined = " ".join([summary, " ".join(files), " ".join(modules)]).lower()
    flags = patch_semantic_flags(joined, modules)
    keywords = sorted(
        {
            *modules,
            *[Path(path).stem for path in files],
            *patch_semantic_keywords(flags),
            *[item for item in ["focus", "launcher", "power", "policy", "package", "input"] if item in joined],
        }
    )
    basis = [f"补丁修改文件: {path}" for path in files]
    basis.extend(f"根据路径归属到模块: {module}" for module in modules)
    basis.extend(f"根据 diff hunk 识别符号: {symbol}" for symbol in facts.get("symbols", []))
    if summary:
        basis.append("提交时提供了补丁摘要")
    if not basis:
        basis = ["补丁文件存在，但缺少可解析的 diff 路径"]

    problem, solution, confidence = patch_semantic_problem_solution(modules, flags)
    risks = patch_semantic_risk_areas(modules, flags)

    limits = [
        "补丁内容不能单独证明原始需求文字",
        "补丁内容不能单独证明设备验证结果",
        "补丁内容不能单独证明发布状态",
    ]
    problem_payload = {
        "kind": "patch_problem_summary",
        "patch_id": patch_id,
        "source_patch": source_patch,
        "confidence": confidence,
        "problem_summary": problem,
        "solution_summary": solution,
        "keywords": keywords,
        "basis": basis,
        "limits": limits,
    }
    risk_payload = {
        "kind": "risk_surface",
        "patch_id": patch_id,
        "source_patch": source_patch,
        "confidence": confidence,
        "risk_areas": risks,
        "basis": basis,
        "limits": limits,
    }
    return problem_payload, risk_payload
