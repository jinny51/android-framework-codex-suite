#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "2.0"
PATCH_NAME_RE = re.compile(r"^[a-z0-9]+[0-9]+-[A-Za-z0-9._-]+@[a-z0-9_.-]+\.patch$")
PLATFORM_TOKEN_RE = re.compile(r"^(mtk|rk|unisoc|sprd|u)(\d{1,2})$")
PLATFORM_PREFIX_ALIASES = {
    "mtk": "mtk",
    "rk": "rk",
    "unisoc": "unisoc",
    "sprd": "unisoc",
    "u": "unisoc",
}
PROJECT_MODEL_RE = re.compile(r"(?<![A-Z0-9])TV[EAI][A-Z0-9]{5}(?:[A-Z0-9_]+)?(?![A-Z0-9])", re.I)
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
FRAMEWORK_LOG_LITERAL_RE = re.compile(r"FrameworkLog\.(?:d|i|w|e)\s*\([^,]+,\s*\"")
SUPPORTED_EXTERNAL_EVIDENCE_KINDS = {"build_result", "deploy_result", "device_health"}
AUTO_VERIFICATION_EVIDENCE_NAMES = (
    ".codex/evidence/latest-build-delivery.json",
    ".codex/evidence/build-delivery.json",
)
IMPLEMENTATION_ORIGINS = ("codex", "manual", "external", "historical", "mixed", "unknown")
CAPTURE_REVIEW_REQUIRED_ORIGINS = {"manual", "external", "historical", "mixed", "unknown"}
REUSE_DECISIONS = ("reuse", "adapt", "reference_only", "not_applicable", "not_found", "unknown")
REUSE_OUTCOMES = ("not_started", "reused_success", "adapted_success", "failed", "partial", "unverified", "not_applicable")


@dataclass
class RepositoryCapture:
    source_root: Path
    repo_path: str
    git_info: dict[str, str]
    diff_text: str
    facts: dict[str, Any]
    module: str
    patch_name: str
    patch_rel: str


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


def normalize_android_version(platform: str, version: str) -> str:
    if platform == "rk" and version in {"71", "90"}:
        return {"71": "7.1", "90": "9.0"}[version]
    return version.lstrip("0") or version


def parse_platform_arg(value: str) -> tuple[str, str, str]:
    token = slug(value)
    match = PLATFORM_TOKEN_RE.fullmatch(token)
    if not match:
        return "", "", ""
    prefix, raw_version = match.groups()
    platform = PLATFORM_PREFIX_ALIASES[prefix]
    android_version = normalize_android_version(platform, raw_version)
    filename_version = raw_version.lstrip("0") or raw_version
    return f"{platform}{filename_version}", platform, android_version


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


def facts_from_diff(diff_text: str) -> dict[str, Any]:
    files = changed_files_from_diff(diff_text)
    added = "\n".join(added_lines(diff_text))
    all_text = diff_text
    return {
        "content_sha1": sha1_text(diff_text),
        "modified_files": files,
        "system_properties": sorted(set(re.findall(r"\b(?:persist|ro|sys|debug|vendor)\.[A-Za-z0-9_.-]+", all_text))),
        "settings_keys": sorted(set(re.findall(r"Settings\.(?:System|Secure|Global)\.([A-Za-z0-9_.-]+)", all_text))),
        "resource_keys": sorted(set([*re.findall(r"R\.string\.([A-Za-z0-9_]+)", all_text), *re.findall(r"@string/([A-Za-z0-9_]+)", all_text)])),
        "framework_log_keys": sorted(set(re.findall(r"FrameworkLog\.([A-Za-z0-9_]+)", all_text))),
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


def direct_log_call_lines(diff_text: str) -> list[str]:
    hits: list[str] = []
    for line in added_lines(diff_text):
        if any(pattern in line for pattern in BANNED_LOG_PATTERNS):
            hits.append(line.strip())
    return hits


def framework_log_literal_lines(diff_text: str) -> list[str]:
    return [line.strip() for line in added_lines(diff_text) if FRAMEWORK_LOG_LITERAL_RE.search(line)]


def direct_debug_property_lines(capture: RepositoryCapture) -> list[str]:
    if any(path.endswith("FrameworkLog.java") for path in capture.facts.get("modified_files", [])):
        return []
    lines: list[str] = []
    for line in added_lines(capture.diff_text):
        if "SystemProperties.getBoolean(" in line and "persist.sys.framework.debug" in line:
            lines.append(line.strip())
    return lines


def collect_repository_captures(args: argparse.Namespace, platform: str, feature: str) -> list[RepositoryCapture]:
    raw_roots = args.source_root or ["."]
    roots: list[Path] = []
    for raw_root in raw_roots:
        root = git_root(Path(raw_root).expanduser().resolve())
        if root not in roots:
            roots.append(root)
    if len(roots) > 1 and args.module:
        raise SystemExit("多源码仓库功能包不接受单个 --module；模块名会按每个源码仓库自动推断。")

    captures: list[RepositoryCapture] = []
    used_names: set[str] = set()
    for root in roots:
        diff_cp = run(["git", "diff", "--binary", "--full-index", "HEAD", "--"], root, check=True)
        diff_text = diff_cp.stdout
        if not diff_text.strip():
            raise SystemExit(f"源码仓库没有发现相对 HEAD 的 git diff，无法生成补丁: {root}")

        facts = facts_from_diff(diff_text)
        repo_path = infer_repo_path_from_root(root, roots, facts["modified_files"])
        facts["repo_path"] = repo_path
        facts["modules"] = modules_from_files(prefixed_files(repo_path, facts["modified_files"]))
        facts["symbols"] = symbols_from_diff(diff_text)
        module = slug(args.module or infer_module_for_repo(repo_path, facts["modified_files"]))
        patch_name = f"{platform}-{module}@{feature}.patch"
        if patch_name in used_names:
            module = slug(repo_path.replace("/", "-"))
            patch_name = f"{platform}-{module}@{feature}.patch"
        if patch_name in used_names:
            module = f"{module}-{sha1_text(str(root))[:8]}"
            patch_name = f"{platform}-{module}@{feature}.patch"
        if not PATCH_NAME_RE.fullmatch(patch_name):
            raise SystemExit(f"生成的 patch 文件名不符合规范: {patch_name}")
        used_names.add(patch_name)
        captures.append(
            RepositoryCapture(
                source_root=root,
                repo_path=repo_path,
                git_info=git_metadata(root),
                diff_text=diff_text,
                facts=facts,
                module=module,
                patch_name=patch_name,
                patch_rel=f"patches/{patch_name}",
            )
        )
    return captures


def infer_capture_project_for_feature(args: argparse.Namespace, captures: list[RepositoryCapture]) -> tuple[str, dict[str, Any]]:
    source_values: list[tuple[str, str]] = []
    for capture in captures:
        source_values.extend(
            [
                ("source_root", str(capture.source_root)),
                ("repo_path", capture.repo_path),
                ("git branch", capture.git_info.get("branch", "")),
                ("git remote", capture.git_info.get("remote", "")),
                ("git remotes", capture.git_info.get("remotes", "")),
                *source_access_registry_clues(capture.source_root),
            ]
        )
    diff_text = "\n".join(capture.diff_text for capture in captures)
    groups: list[tuple[str, list[tuple[str, str]]]] = [
        ("explicit", [("命令参数 project", args.project or "")]),
        ("source_context", source_values),
        (
            "patch_context",
            [
                ("功能摘要", args.summary or ""),
                ("功能名", args.feature or ""),
                ("补丁 diff", diff_text),
            ],
        ),
    ]
    clues = [(label, value) for _, values in groups for label, value in values if str(value).strip()]
    checked_sources = sorted(dict.fromkeys(label for label, _ in clues))
    raw_inputs = [f"{label}: {value}" for label, value in clues]
    matched: list[tuple[str, str, str]] = []
    for _, values in groups:
        for label, value in values:
            matched.extend((candidate, label, value) for candidate in find_company_projects(value))
    unique_projects = sorted(dict.fromkeys(project for project, _, _ in matched))
    if len(unique_projects) == 1:
        project = unique_projects[0]
        basis = [f"{label}: {value}" for matched_project, label, value in matched if matched_project == project]
        return project, project_inference_payload(project, basis[:5], checked_sources, raw_inputs)
    if len(unique_projects) > 1:
        limits = [f"识别到多个项目型号: {', '.join(unique_projects)}，不能写成单一项目"]
        if args.project and args.project.strip() not in {"", "unknown"}:
            limits.append("命令参数 project 与其他项目线索不一致，未作为项目名写入补丁包")
        payload = project_inference_payload("unknown", [], checked_sources, raw_inputs, limits)
        payload["candidates"] = unique_projects
        return "unknown", payload

    limits = ["未从命令参数、source_root、repo_path、git branch、git remote、source-access registry、功能摘要或 diff 中识别到 TVE/TVA/TVI 项目型号"]
    if args.project and args.project.strip() not in {"", "unknown"}:
        limits.append("命令参数 project 未匹配公司项目型号规范，未作为项目名写入补丁包")
    return "unknown", project_inference_payload("unknown", [], checked_sources, raw_inputs, limits)


def find_company_project(text: str) -> str:
    match = PROJECT_MODEL_RE.search((text or "").upper())
    return match.group(0) if match else ""


def find_company_projects(text: str) -> list[str]:
    return sorted(dict.fromkeys(match.group(0).upper() for match in PROJECT_MODEL_RE.finditer((text or "").upper())))


def parse_shell_array(text: str, name: str) -> list[str]:
    match = re.search(rf"^{re.escape(name)}=\((.*)\)$", text, re.M)
    if not match:
        return []
    try:
        return [item for item in shlex.split(match.group(1)) if item]
    except ValueError:
        return []


def path_strings_overlap(left: str, right: str) -> bool:
    left = left.replace("\\", "/").rstrip("/")
    right = right.replace("\\", "/").rstrip("/")
    if not left or not right:
        return False
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def source_access_registry_clues(source_root: Path) -> list[tuple[str, str]]:
    registry_dir = Path.home() / ".codex" / "android-wsl-source-access-info" / "projects"
    if not registry_dir.is_dir():
        return []
    clues: list[tuple[str, str]] = []
    source_text = str(source_root)
    for registry_file in sorted(registry_dir.glob("*.env")):
        try:
            text = registry_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        paths = parse_shell_array(text, "PROJECT_PATHS")
        if not paths:
            continue
        ssh_hosts = parse_shell_array(text, "REMOTE_SSH_HOSTS")
        remote_roots = parse_shell_array(text, "REMOTE_ROOTS")
        platforms = parse_shell_array(text, "PLATFORMS")
        sdk_names = parse_shell_array(text, "SDK_NAMES")
        shares = parse_shell_array(text, "SAMBA_PROJECT_SHARES")
        for index, project_path in enumerate(paths):
            if not path_strings_overlap(source_text, project_path):
                continue
            if index < len(sdk_names):
                clues.append(("source-access registry sdk_name", sdk_names[index]))
            if index < len(remote_roots):
                clues.append(("source-access registry remote_root", remote_roots[index]))
            if index < len(shares):
                clues.append(("source-access registry share", shares[index]))
            if index < len(platforms):
                clues.append(("source-access registry platform", platforms[index]))
            if index < len(ssh_hosts):
                clues.append(("source-access registry ssh_host", ssh_hosts[index]))
    return clues


def project_inference_payload(
    project: str,
    basis: list[str],
    checked_sources: list[str],
    raw_inputs: list[str],
    limits: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "project": project,
        "recognized": project != "unknown",
        "basis": basis,
        "checked_sources": checked_sources,
        "raw_inputs": raw_inputs[:20],
        "limits": limits or [],
        "recognition_scope": "TVE/TVA/TVI",
        "company_rule_match": project != "unknown",
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"读取 evidence JSON 失败: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"evidence JSON 必须是对象: {path}")
    return payload


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def merge_string_lists(first: list[str], second: list[str]) -> list[str]:
    result: list[str] = []
    for item in [*first, *second]:
        if item and item not in result:
            result.append(item)
    return result


def evidence_kind_from_file(path: Path, payload: dict[str, Any]) -> str:
    kind = str(payload.get("kind") or "").strip()
    if kind:
        return slug(kind)
    stem = path.stem.lower().replace("-", "_")
    aliases = {
        "build": "build_result",
        "build_result": "build_result",
        "deploy_result": "deploy_result",
        "device_health": "device_health",
        "verification_result": "verification_result",
        "search_before_change": "search_before_change",
    }
    return aliases.get(stem, stem or "external_evidence")


def evidence_result(payload: dict[str, Any]) -> str:
    value = str(payload.get("result") or payload.get("status") or "").upper()
    if value in {"PASS", "FAIL", "WARN", "INFO", "SKIPPED", "MISSING"}:
        return value
    return "INFO"


def source_roots_for_auto_evidence(args: argparse.Namespace) -> list[Path]:
    roots = [Path(item).expanduser().resolve() for item in args.source_root or []]
    if not roots:
        roots = [Path.cwd().resolve()]
    result: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root not in seen:
            seen.add(root)
            result.append(root)
    return result


def merge_auto_verification_payload(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    if not base:
        return dict(incoming)
    merged = dict(base)
    for key in ("result", "method", "summary", "device"):
        if not merged.get(key) and incoming.get(key):
            merged[key] = incoming[key]
    for key in ("build", "steps", "health_checks", "artifacts"):
        merged[key] = merge_string_lists(string_list(merged.get(key)), string_list(incoming.get(key)))
    for key in ("remote_build", "local_delivery"):
        current = merged.get(key) if isinstance(merged.get(key), dict) else {}
        update = incoming.get(key) if isinstance(incoming.get(key), dict) else {}
        combined = dict(current)
        for field, value in update.items():
            if field == "artifacts":
                combined[field] = list(value) if isinstance(value, list) else value
            elif not combined.get(field) and value:
                combined[field] = value
        if combined:
            merged[key] = combined
    return merged


def load_auto_verification_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for root in source_roots_for_auto_evidence(args):
        for rel in AUTO_VERIFICATION_EVIDENCE_NAMES:
            path = root / rel
            if not path.is_file():
                continue
            item = read_json(path)
            kind = evidence_kind_from_file(path, item)
            if kind != "verification_result":
                continue
            payload = merge_auto_verification_payload(payload, item)
    return payload


def implementation_review_required(origin: str) -> bool:
    return origin in CAPTURE_REVIEW_REQUIRED_ORIGINS


def implementation_review_mode(origin: str) -> str:
    return "capture_gate" if implementation_review_required(origin) else "development_safety_net"


def evidence_file_name(kind: str, source: Path, used_names: set[str]) -> str:
    base = f"{kind.replace('_', '-')}.json"
    if base not in used_names:
        return base
    return f"{kind.replace('_', '-')}-{sha1_text(str(source))[:8]}.json"


def collect_external_evidence(args: argparse.Namespace, evidence_dir: Path) -> list[dict[str, Any]]:
    sources: list[Path] = []
    for raw_dir in args.evidence_dir or []:
        directory = Path(raw_dir).expanduser().resolve()
        if not directory.is_dir():
            raise SystemExit(f"--evidence-dir 不是目录: {directory}")
        sources.extend(sorted(directory.glob("*.json")))
    for raw_file in args.build_result or []:
        source = Path(raw_file).expanduser().resolve()
        if not source.is_file():
            raise SystemExit(f"--build-result 文件不存在: {source}")
        sources.append(source)

    entries: list[dict[str, Any]] = []
    seen: set[Path] = set()
    used_names: set[str] = set()
    for source in sources:
        source = source.resolve()
        if source in seen:
            continue
        seen.add(source)
        payload = read_json(source)
        kind = evidence_kind_from_file(source, payload)
        if kind not in SUPPORTED_EXTERNAL_EVIDENCE_KINDS:
            allowed = ", ".join(sorted(SUPPORTED_EXTERNAL_EVIDENCE_KINDS))
            raise SystemExit(f"外部 evidence kind 不支持: {kind} ({source}); 允许: {allowed}")
        payload.setdefault("kind", kind)
        target_name = evidence_file_name(kind, source, used_names)
        used_names.add(target_name)
        target = evidence_dir / target_name
        write_json(target, payload)
        entries.append(
            {
                "id": slug(target.stem),
                "kind": kind,
                "path": f"evidence/{target.name}",
                "result": evidence_result(payload),
                "summary": str(payload.get("summary") or payload.get("message") or f"{kind} evidence"),
            }
        )
    return entries


def bullet_list(items: list[str]) -> str:
    if not items:
        return "无"
    return "\n".join(f"- `{item}`" for item in items)


def plain_bullets(items: list[str]) -> str:
    if not items:
        return "待补充"
    return "\n".join(f"- {item}" for item in items)


def inferred_verification_method(args: argparse.Namespace, auto_payload: dict[str, Any] | None = None) -> str:
    if args.verification_method:
        return args.verification_method
    if auto_payload and auto_payload.get("method"):
        return str(auto_payload.get("method"))
    if args.equivalent_type or args.equivalent_reason or args.equivalent_coverage or args.remaining_risk:
        return "equivalent"
    if args.device or args.device_verification:
        return "device"
    return "not_provided"


def verification_result(args: argparse.Namespace, auto_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    auto_payload = auto_payload or {}
    method = inferred_verification_method(args, auto_payload)
    has_evidence = bool(
        args.verification
        or args.device_verification
        or args.equivalent_coverage
        or args.equivalent_reason
        or args.health_check
        or args.artifact
        or auto_payload
    )
    result = args.verification_result or str(auto_payload.get("result") or "") or ("PASS" if has_evidence else "INFO")
    auto_remote_build = auto_payload.get("remote_build") if isinstance(auto_payload.get("remote_build"), dict) else {}
    auto_local_delivery = auto_payload.get("local_delivery") if isinstance(auto_payload.get("local_delivery"), dict) else {}
    auto_local_artifacts = string_list(auto_local_delivery.get("local_artifacts") if isinstance(auto_local_delivery, dict) else [])
    auto_adb_actions = string_list(auto_local_delivery.get("adb_actions") if isinstance(auto_local_delivery, dict) else [])
    auto_device_restarts = string_list(auto_local_delivery.get("device_restarts") if isinstance(auto_local_delivery, dict) else [])
    payload: dict[str, Any] = {
        "result": result,
        "method": method,
        "build": args.verification or string_list(auto_payload.get("build")),
        "device": args.device or str(auto_payload.get("device") or auto_local_delivery.get("adb_serial") or ""),
        "steps": args.device_verification or string_list(auto_payload.get("steps")),
        "observed": "\n".join(args.device_verification or string_list(auto_payload.get("steps"))),
        "health_checks": args.health_check or string_list(auto_payload.get("health_checks")),
        "artifacts": args.artifact or string_list(auto_payload.get("artifacts")),
    }
    remote_artifacts: list[dict[str, str]] = []
    for index, artifact in enumerate(args.remote_artifact or []):
        sha1 = args.artifact_sha1[index] if index < len(args.artifact_sha1 or []) else ""
        remote_artifacts.append({"path": artifact, "sha1": sha1})
    if not remote_artifacts and isinstance(auto_remote_build.get("artifacts"), list):
        remote_artifacts = [item for item in auto_remote_build.get("artifacts", []) if isinstance(item, dict)]
    payload["remote_build"] = {
        "host": args.remote_build_host or str(auto_remote_build.get("host") or ""),
        "source_root": args.remote_source_root or str(auto_remote_build.get("source_root") or ""),
        "command": args.remote_build_command or str(auto_remote_build.get("command") or ""),
        "profile": args.remote_build_profile or str(auto_remote_build.get("profile") or ""),
        "artifacts": remote_artifacts,
    }
    payload["local_delivery"] = {
        "transfer": args.artifact_transfer or str(auto_local_delivery.get("transfer") or ""),
        "local_artifacts": args.local_artifact or auto_local_artifacts,
        "adb_serial": args.adb_serial or str(auto_local_delivery.get("adb_serial") or ""),
        "adb_actions": args.adb_action or auto_adb_actions,
        "device_restarts": args.device_restart or auto_device_restarts,
    }
    if method == "equivalent":
        payload.update(
            {
                "equivalent_type": args.equivalent_type or "",
                "reason": args.equivalent_reason or "",
                "coverage": args.equivalent_coverage or [],
                "remaining_risk": args.remaining_risk or "",
            }
        )
    return payload


def search_before_change(args: argparse.Namespace) -> dict[str, Any]:
    queries = args.search_query or []
    results = args.search_result or []
    summary = args.search_summary or ""
    decision = args.reuse_decision or infer_reuse_decision(queries, results, summary)
    return {
        "result": "INFO",
        "method": "knowledge_search",
        "searched": bool(queries or results or summary),
        "queries": queries,
        "results": results,
        "summary": summary or "not provided by capture command",
        "decision": decision,
        "reuse_decision": decision,
        "targets": args.reuse_target or [],
        "match_points": args.reuse_match or [],
        "mismatch_points": args.reuse_mismatch or [],
        "reason": args.reuse_reason or "",
        "outcome": args.reuse_outcome or "not_started",
    }


def infer_reuse_decision(queries: list[str], results: list[str], summary: str) -> str:
    text = "\n".join([*queries, *results, summary]).lower()
    if not text.strip():
        return "unknown"
    if any(token in text for token in ("未发现", "未命中", "no reuse", "no candidate", "not found")):
        return "not_found"
    return "unknown"


def modules_from_files(files: list[str]) -> list[str]:
    modules: list[str] = []
    for path in files:
        lower = path.lower()
        if "/com/android/server/wm/" in lower or "windowstate" in lower:
            modules.append("WindowManager")
        if "activitytaskmanager" in lower or "activityrecord" in lower:
            modules.append("ActivityTaskManager")
        if "phonewindowmanager" in lower or "/com/android/server/policy/" in lower:
            modules.append("Policy")
        if "packagemanager" in lower or "/com/android/server/pm/" in lower:
            modules.append("PackageManager")
        if "systemui" in lower or "/com/android/systemui/" in lower:
            modules.append("SystemUI")
        if "launcher" in lower or "quickstep" in lower or "recentsview" in lower:
            modules.append("Launcher")
        if "/input/" in lower or "inputflinger" in lower:
            modules.append("Input")
        if "/com/android/server/audio/" in lower or "audioservice" in lower or "audioflinger" in lower or "mediafocuscontrol" in lower:
            modules.append("Audio")
        if "cameraservice" in lower or "camera2" in lower:
            modules.append("Camera")
        if "vold" in lower or "volumemanager" in lower or "publicvolume" in lower or "obbvolume" in lower or "externalstorage" in lower:
            modules.append("Storage")
        if "wifiservice" in lower or "/wifi/" in lower:
            modules.append("Wifi")
        if "ueventd" in lower or "/usb/" in lower or "usb" in lower:
            modules.append("USB")
        if any(name in lower for name in ("rockchip_apps.mk", "apps.mk", "boardconfig.mk", "device.mk")):
            modules.append("ProductConfig")
    if not modules and files:
        modules.append(infer_module(files))
    return sorted(set(modules))


def semantic_flags(joined: str, modules: list[str]) -> dict[str, bool]:
    module_set = set(modules)
    return {
        "focus": "focus" in joined,
        "launcher": "Launcher" in module_set or "launcher" in joined or "quickstep" in joined,
        "power": "power" in joined or "Policy" in module_set,
        "package": "package" in joined or "PackageManager" in module_set,
        "input": "input" in joined or "Input" in module_set,
        "audio": "Audio" in module_set or "audio" in joined or "microphone" in joined or "volume" in joined,
        "camera": "Camera" in module_set or "camera" in joined or "qrcode" in joined or "preview" in joined,
        "storage": "Storage" in module_set or "storage" in joined or "vold" in joined or "volume" in joined or "obb" in joined,
        "wifi": "Wifi" in module_set or "wifi" in joined or "wlan" in joined,
        "usb": "USB" in module_set or "usb" in joined or "ueventd" in joined,
        "product_config": "ProductConfig" in module_set or "boardconfig" in joined or "device.mk" in joined or "apps.mk" in joined,
    }


def semantic_keywords(flags: dict[str, bool]) -> list[str]:
    labels = {
        "audio": "音频路由/音量",
        "camera": "相机行为",
        "storage": "存储/挂载",
        "wifi": "Wi-Fi",
        "usb": "USB/设备权限",
        "product_config": "产品配置/预置应用",
    }
    return [label for flag, label in labels.items() if flags.get(flag)]


def semantic_problem_solution(modules: list[str], flags: dict[str, bool]) -> tuple[str, str, str]:
    if flags["focus"] and ("WindowManager" in modules or "ActivityTaskManager" in modules):
        return (
            "窗口或 Activity 焦点行为需要按产品需求调整。",
            "修改 WindowManager 或 ActivityTaskManager 相关路径中的焦点处理逻辑。",
            "medium",
        )
    if flags["power"]:
        return (
            "按键、策略或电源相关行为需要按产品需求调整。",
            "修改 Framework policy 路径中的策略处理逻辑。",
            "medium",
        )
    if flags["audio"] and flags["camera"]:
        return (
            "音频录制、麦克风或相机链路可能不符合产品权限或回退策略要求。",
            "调整 Audio/Camera 相关服务或 HAL 路径，并验证录音、拍照、扫码和权限切换场景。",
            "medium",
        )
    if flags["audio"]:
        return (
            "音频路由、音量或麦克风行为可能不符合产品要求。",
            "调整 AudioService、AudioFlinger 或音量策略相关路径，并验证音量、录音和媒体播放场景。",
            "medium",
        )
    if flags["camera"]:
        return (
            "相机预览、扫码、拍照或相机权限行为可能不符合产品要求。",
            "调整 CameraService、Camera2 或相机 HAL 相关路径，并验证目标相机场景。",
            "medium",
        )
    if flags["storage"]:
        return (
            "外部存储、挂载或应用访问存储的权限行为可能不符合产品要求。",
            "调整 vold、VolumeManager 或存储访问相关路径，并验证 U 盘、OBB 和外部存储访问场景。",
            "medium",
        )
    if flags["wifi"]:
        return (
            "Wi-Fi 服务、默认配置或连接权限行为可能不符合产品要求。",
            "调整 Wi-Fi service 或产品配置路径，并验证连接、开关和权限相关场景。",
            "medium",
        )
    if flags["usb"]:
        return (
            "USB 设备节点、权限或外设识别行为可能不符合产品要求。",
            "调整 ueventd、USB 权限或设备配置路径，并验证目标外设识别和访问权限。",
            "medium",
        )
    if flags["product_config"]:
        return (
            "产品编译配置、预置应用或板级开关可能不符合项目要求。",
            "调整 BoardConfig、device makefile 或预置应用清单，并验证编译产物和首次开机状态。",
            "medium",
        )
    if modules:
        return (
            f"{'、'.join(modules)} 相关行为需要按产品需求调整。",
            "结合需求、修改文件和验证记录复核对应逻辑。",
            "low",
        )
    return (
        "补丁对应的具体问题需要结合原始需求和会话记录确认。",
        "先阅读补丁 diff、readme 和验证记录，再决定是否复用或适配。",
        "low",
    )


def semantic_risk_areas(modules: list[str], flags: dict[str, bool]) -> list[str]:
    risks = sorted(
        {
            *("窗口焦点/显示层级" for _ in [0] if flags["focus"] or "WindowManager" in modules),
            *("Activity 启动/恢复" for _ in [0] if "ActivityTaskManager" in modules),
            *("按键/电源/策略行为" for _ in [0] if flags["power"]),
            *("包安装/包状态" for _ in [0] if "PackageManager" in modules),
            *("音频路由/音量行为" for _ in [0] if flags["audio"]),
            *("相机行为" for _ in [0] if flags["camera"]),
            *("存储/挂载管理" for _ in [0] if flags["storage"]),
            *("Wi-Fi 服务/配置" for _ in [0] if flags["wifi"]),
            *("USB/设备权限" for _ in [0] if flags["usb"]),
            *("产品配置/预置应用" for _ in [0] if flags["product_config"]),
            *("输入分发" for _ in [0] if flags["input"]),
        }
    )
    return risks or ["修改路径需要按当前项目需求重新验证"]


def symbols_from_diff(diff_text: str) -> list[str]:
    symbols: list[str] = []
    current_class = ""
    for raw in diff_text.splitlines():
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


def validate_verification_for_status(args: argparse.Namespace, payload: dict[str, Any]) -> list[str]:
    if args.status != "validated":
        return []

    errors: list[str] = []
    method = payload.get("method")
    if payload.get("result") != "PASS":
        errors.append("status 是 validated 时 verification-result.result 必须是 PASS")

    if method == "device":
        if not payload.get("build"):
            errors.append("status 是 validated 且 method=device 时必须提供 --verification 构建验证")
        if not payload.get("steps"):
            errors.append("status 是 validated 且 method=device 时必须提供 --device-verification 真机验证")
    elif method == "equivalent":
        if not payload.get("equivalent_type"):
            errors.append("status 是 validated 且 method=equivalent 时必须提供 --equivalent-type")
        if not payload.get("reason"):
            errors.append("status 是 validated 且 method=equivalent 时必须提供 --equivalent-reason")
        if not payload.get("coverage"):
            errors.append("status 是 validated 且 method=equivalent 时必须提供 --equivalent-coverage")
        if not payload.get("remaining_risk"):
            errors.append("status 是 validated 且 method=equivalent 时必须提供 --remaining-risk")
    else:
        errors.append("status 是 validated 时必须提供 device 或 equivalent 验证证据")

    return errors


def aggregate_feature_facts(captures: list[RepositoryCapture]) -> dict[str, Any]:
    aggregate: dict[str, list[str]] = {
        "modified_files": [],
        "modules": [],
        "symbols": [],
        "system_properties": [],
        "settings_keys": [],
        "resource_keys": [],
        "framework_log_keys": [],
    }
    patches: list[dict[str, Any]] = []
    content_hashes: list[str] = []
    for capture in captures:
        facts = capture.facts
        content_sha1 = str(facts.get("content_sha1") or "")
        if content_sha1:
            content_hashes.append(content_sha1)
        modified_files = prefixed_files(capture.repo_path, list(facts.get("modified_files", [])))
        aggregate["modified_files"].extend(modified_files)
        aggregate["modules"].extend(list(facts.get("modules", [])))
        aggregate["symbols"].extend(list(facts.get("symbols", [])))
        for key in ("system_properties", "settings_keys", "resource_keys", "framework_log_keys"):
            aggregate[key].extend(list(facts.get(key, [])))
        patches.append(
            {
                "id": Path(capture.patch_name).stem,
                "path": capture.patch_rel,
                "repo_path": capture.repo_path,
                "source_root": str(capture.source_root),
                "content_sha1": content_sha1,
                "status": "",
                "modified_files": modified_files,
                "modules": list(facts.get("modules", [])),
                "symbols": list(facts.get("symbols", [])),
            }
        )
    payload: dict[str, Any] = {
        "kind": "patch_diff_facts",
        "scope": "feature",
        "patch_count": len(captures),
        "patches": patches,
        "content_sha1": content_hashes[0] if len(content_hashes) == 1 else "",
    }
    payload.update({key: unique_preserve(values) for key, values in aggregate.items()})
    return payload


def feature_problem_and_risk_payloads(args: argparse.Namespace, captures: list[RepositoryCapture], facts: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    files = list(facts.get("modified_files", []))
    modules = list(facts.get("modules", []))
    symbols = list(facts.get("symbols", []))
    joined = "\n".join([args.summary, args.feature, " ".join(files), " ".join(modules)]).lower()
    flags = semantic_flags(joined, modules)
    keywords = sorted(
        {
            *modules,
            *[Path(path).stem for path in files],
            *semantic_keywords(flags),
            *[item for item in ["focus", "launcher", "power", "policy", "package", "input"] if item in joined],
        }
    )
    basis = [f"功能涉及源码仓库: {capture.repo_path}" for capture in captures]
    basis.extend(f"补丁修改文件: {path}" for path in files)
    basis.extend(f"根据路径归属到模块: {module}" for module in modules)
    basis.extend(f"根据 diff hunk 识别符号: {symbol}" for symbol in symbols)
    if args.summary:
        basis.append("提交时提供了功能摘要")

    problem_summary, solution_summary, confidence = semantic_problem_solution(modules, flags)
    risks = semantic_risk_areas(modules, flags)
    limits = [
        "补丁内容不能单独证明原始需求文字",
        "补丁内容不能单独证明设备验证结果",
        "补丁内容不能单独证明发布状态",
    ]
    patch_paths = [capture.patch_rel for capture in captures]
    return (
        {
            "kind": "patch_problem_summary",
            "scope": "feature",
            "patches": patch_paths,
            "confidence": confidence,
            "problem_summary": problem_summary,
            "solution_summary": solution_summary,
            "keywords": keywords,
            "basis": basis,
            "limits": limits,
        },
        {
            "kind": "risk_surface",
            "scope": "feature",
            "patches": patch_paths,
            "confidence": confidence,
            "risk_areas": risks,
            "basis": basis,
            "limits": limits,
        },
    )


def coding_standard_check(args: argparse.Namespace, captures: list[RepositoryCapture]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    repositories: list[dict[str, Any]] = []
    for capture in captures:
        facts = capture.facts
        repo_errors: list[str] = []
        repo_warnings: list[str] = []
        direct_logs = direct_log_call_lines(capture.diff_text)
        hardcoded_logs = framework_log_literal_lines(capture.diff_text)
        direct_debug_props = direct_debug_property_lines(capture)
        non_framework_debug_props = [
            prop
            for prop in facts.get("system_properties", [])
            if prop.startswith("debug.") or (prop.startswith("persist.") and ".debug" in prop and not prop.startswith("persist.sys.framework.debug"))
        ]

        if not facts.get("author_date_marker_present") and not args.allow_missing_author_date:
            repo_errors.append("缺少作者日期备注，例如 //gyf 20251016@")
        if direct_logs and not args.allow_banned_logs:
            repo_errors.append("新增代码包含直接 Log/Slog 调用，应改用 FrameworkLog")
        if hardcoded_logs:
            repo_warnings.append("FrameworkLog 调用疑似包含硬编码字符串，应优先使用字符串资源")
        if direct_debug_props:
            repo_warnings.append("模块代码疑似直接读取 persist.sys.framework.debug.*，应通过 FrameworkLog 统一访问")
        if non_framework_debug_props:
            repo_warnings.append("检测到非 FrameworkLog 规范调试属性: " + ", ".join(non_framework_debug_props))

        repositories.append(
            {
                "repo_path": capture.repo_path,
                "patch": capture.patch_rel,
                "author_date_marker_present": bool(facts.get("author_date_marker_present")),
                "direct_log_lines": direct_logs[:20],
                "framework_log_literal_lines": hardcoded_logs[:20],
                "direct_debug_property_lines": direct_debug_props[:20],
                "system_properties": facts.get("system_properties", []),
                "framework_log_keys": facts.get("framework_log_keys", []),
                "resource_keys": facts.get("resource_keys", []),
                "errors": repo_errors,
                "warnings": repo_warnings,
            }
        )
        errors.extend(f"{capture.repo_path}: {item}" for item in repo_errors)
        warnings.extend(f"{capture.repo_path}: {item}" for item in repo_warnings)

    return {
        "kind": "coding_standard_check",
        "result": "FAIL" if errors else ("WARN" if warnings else "PASS"),
        "implementation_origin": args.implementation_origin,
        "captured_by": "codex",
        "review_required": implementation_review_required(args.implementation_origin),
        "review_mode": implementation_review_mode(args.implementation_origin),
        "standard_sources": [
            "Android Framework 补丁开发规范 v2.1 2025-10-16",
            "Android Framework 日志管理规范 v1.0 2025-10-16",
        ],
        "rules": [
            "补丁必须包含作者日期备注",
            "直接 Log/Slog 调用禁止进入补丁，应使用 FrameworkLog",
            "persist.sys.framework.debug.* 调试属性集中在 FrameworkLog.java",
            "日志字符串和新增用户可见字符串应使用资源国际化",
            "功能说明文件必须记录功能、修改点、日志控制、SystemProperties、字符串国际化和可回滚性",
        ],
        "repositories": repositories,
        "errors": errors,
        "warnings": warnings,
    }


def feature_readme_text(
    args: argparse.Namespace,
    captures: list[RepositoryCapture],
    facts: dict[str, Any],
    package_check: dict[str, Any],
    coding_check: dict[str, Any],
    verification_payload: dict[str, Any],
) -> str:
    remote_build = verification_payload.get("remote_build") if isinstance(verification_payload.get("remote_build"), dict) else {}
    local_delivery = verification_payload.get("local_delivery") if isinstance(verification_payload.get("local_delivery"), dict) else {}
    verification = args.verification or string_list(verification_payload.get("build"))
    device_verification = args.device_verification or string_list(verification_payload.get("steps"))
    remote_artifacts = args.remote_artifact or [
        " ".join(
            item
            for item in (
                str(artifact.get("path") or "").strip(),
                f"sha1={artifact.get('sha1')}" if artifact.get("sha1") else "",
            )
            if item
        )
        for artifact in remote_build.get("artifacts", [])
        if isinstance(artifact, dict)
    ]
    local_artifacts = args.local_artifact or string_list(local_delivery.get("local_artifacts"))
    adb_actions = args.adb_action or string_list(local_delivery.get("adb_actions"))
    device_restarts = args.device_restart or string_list(local_delivery.get("device_restarts"))
    risk = args.risk or "待结合当前项目、触发路径和验证结果补充。"
    rollback = args.rollback or "在对应源码仓库逐个执行 `git apply -R <patch>`，或回退对应源码仓库提交。"
    repo_lines = "\n".join(f"- `{capture.repo_path}` -> `{capture.patch_rel}`" for capture in captures)
    modification_sections = "\n\n".join(
        f"### {capture.repo_path}\n\n{bullet_list(prefixed_files(capture.repo_path, capture.facts['modified_files']))}" for capture in captures
    )
    modules = unique_preserve([module for capture in captures for module in capture.facts.get("modules", [])])
    direct_log_lines = [line for repo in coding_check["repositories"] for line in repo.get("direct_log_lines", [])]
    if direct_log_lines:
        log_control = "检测到直接 Log/Slog 新增，提交前必须改为 FrameworkLog：\n" + plain_bullets(direct_log_lines)
    else:
        log_control = "未检测到直接 Log/Slog 新增；如本功能新增调试日志，应统一使用 FrameworkLog。"

    return f"""# {args.feature}

## 功能描述

{args.summary}

## 实现来源

- implementation_origin: {args.implementation_origin}
- captured_by: codex
- coding_standard_review: {coding_check["review_mode"]}

## 涉及源码仓库

{repo_lines}

## 修改点

{modification_sections}

## 影响范围

- 项目: {args.project}
- 模块: {", ".join(modules) if modules else "unknown"}
- 状态: {args.status}

## 关键符号

### SystemProperties

{bullet_list(facts["system_properties"])}

### Settings Key

{bullet_list(facts["settings_keys"])}

### FrameworkLog Key

{bullet_list(facts["framework_log_keys"])}

### 字符串资源

{bullet_list(facts["resource_keys"])}

## 日志控制

{log_control}

## SystemProperties

{bullet_list(facts["system_properties"])}

## 字符串国际化

{bullet_list(facts["resource_keys"])}

## 构建验证

{plain_bullets(verification)}

## 设备验证

{plain_bullets(device_verification)}

## 开发前知识库检索

### 检索词

{plain_bullets(args.search_query or [])}

### 检索结果

{plain_bullets(args.search_result or [])}

### 使用决策

- decision: {args.reuse_decision or infer_reuse_decision(args.search_query or [], args.search_result or [], args.search_summary or "")}
- targets: {", ".join(args.reuse_target or []) if args.reuse_target else "待补充"}
- match_points: {", ".join(args.reuse_match or []) if args.reuse_match else "待补充"}
- mismatch_points: {", ".join(args.reuse_mismatch or []) if args.reuse_mismatch else "待补充"}
- reason: {args.reuse_reason or "待补充"}
- outcome: {args.reuse_outcome or "not_started"}

## 远端构建链路

- remote_build_host: {args.remote_build_host or str(remote_build.get("host") or "") or "待补充"}
- remote_source_root: {args.remote_source_root or str(remote_build.get("source_root") or "") or "待补充"}
- remote_build_profile: {args.remote_build_profile or str(remote_build.get("profile") or "") or "待补充"}
- remote_build_command: {args.remote_build_command or str(remote_build.get("command") or "") or "待补充"}
- remote_artifacts: {", ".join(remote_artifacts) if remote_artifacts else "待补充"}

## 本机交付和设备验证链路

- artifact_transfer: {args.artifact_transfer or str(local_delivery.get("transfer") or "") or "待补充"}
- local_artifacts: {", ".join(local_artifacts) if local_artifacts else "待补充"}
- adb_serial: {args.adb_serial or str(local_delivery.get("adb_serial") or "") or "待补充"}
- adb_actions: {", ".join(adb_actions) if adb_actions else "待补充"}
- device_restarts: {", ".join(device_restarts) if device_restarts else "待补充"}

## 风险说明

{risk}

## 可回滚性

{rollback}

## 团队规范检查

- coding_standard_check: {coding_check["result"]}
- errors: {len(coding_check["errors"])}
- warnings: {len(coding_check["warnings"])}

## 打包检查

- package_check: {package_check["status"]}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package one Android Framework feature into README, patches, and evidence assets.")
    parser.add_argument("--source-root", action="append", default=[], help="Android source git repository. Repeat for multi-repository features. Default: current directory.")
    parser.add_argument("--out-dir", default=".codex/patch-packages", help="Output root. Default: .codex/patch-packages")
    parser.add_argument("--run-id", help="Output package id. Default: YYYYMMDD-HHMMSS-feature")
    parser.add_argument("--platform", required=True, help="Platform plus Android version token, for example rk14, mtk14, unisoc13.")
    parser.add_argument("--module", help="Patch module name. Default inferred from changed files.")
    parser.add_argument("--feature", required=True, help="Feature slug for filename, for example allow-powerkey-to-user.")
    parser.add_argument("--summary", required=True, help="Human-readable requirement or patch summary.")
    parser.add_argument(
        "--implementation-origin",
        choices=IMPLEMENTATION_ORIGINS,
        default="codex",
        help="Who implemented the code before packaging. Use manual/external/historical/mixed/unknown for non-Codex-authored code.",
    )
    parser.add_argument("--project", default="unknown", help="Project name for manifest/readme.")
    parser.add_argument("--status", choices=["draft", "candidate", "validated", "failed", "blocked"], default="draft")
    parser.add_argument("--verification", action="append", default=[], help="Build verification fact. Repeatable.")
    parser.add_argument("--verification-result", choices=["PASS", "FAIL", "WARN", "INFO", "SKIPPED"], help="Overall verification result. Default: PASS when evidence is present, otherwise INFO.")
    parser.add_argument("--verification-method", choices=["device", "equivalent", "not_provided"], help="Verification method. Default inferred from verification arguments.")
    parser.add_argument("--device", default="", help="Device or board used for device verification.")
    parser.add_argument("--device-verification", action="append", default=[], help="Device verification fact. Repeatable.")
    parser.add_argument("--health-check", action="append", default=[], help="Health check evidence, such as boot, logcat, or dumpsys checks. Repeatable.")
    parser.add_argument("--artifact", action="append", default=[], help="Build or verification artifact path/reference. Repeatable.")
    parser.add_argument("--equivalent-type", default="", help="Equivalent verification type, for example artifact_static_check.")
    parser.add_argument("--equivalent-reason", default="", help="Why equivalent verification is acceptable.")
    parser.add_argument("--equivalent-coverage", action="append", default=[], help="Equivalent verification coverage item. Repeatable.")
    parser.add_argument("--remaining-risk", default="", help="Remaining risk after equivalent verification.")
    parser.add_argument("--search-query", action="append", default=[], help="Knowledge-base query performed before development. Repeatable.")
    parser.add_argument("--search-result", action="append", default=[], help="Search result or reuse decision from the pre-change search. Repeatable.")
    parser.add_argument("--search-summary", default="", help="Short summary of pre-change knowledge search.")
    parser.add_argument("--reuse-decision", choices=REUSE_DECISIONS, help="Pre-change knowledge use decision: reuse, adapt, reference_only, not_applicable, not_found, or unknown.")
    parser.add_argument("--reuse-target", action="append", default=[], help="Matched case, variant, patch, or evidence id considered before the change. Repeatable.")
    parser.add_argument("--reuse-match", action="append", default=[], help="Why the matched knowledge may apply. Repeatable.")
    parser.add_argument("--reuse-mismatch", action="append", default=[], help="Why the matched knowledge may not directly apply. Repeatable.")
    parser.add_argument("--reuse-reason", default="", help="Reason for the pre-change reuse/adapt/reference/not-applicable decision.")
    parser.add_argument("--reuse-outcome", choices=REUSE_OUTCOMES, help="Outcome after implementing and verifying with the pre-change decision.")
    parser.add_argument("--related-report-run-id", action="append", default=[], help="daily/weekly incoming run_id related to this patch package. Repeatable.")
    parser.add_argument("--evidence-dir", action="append", default=[], help="Directory containing structured evidence JSON files such as build-result.json. Repeatable.")
    parser.add_argument("--build-result", action="append", default=[], help="Structured build-result.json to include as build_result evidence. Repeatable.")
    parser.add_argument("--remote-build-host", default="", help="SSH host or alias of the remote build server used for source edits/build.")
    parser.add_argument("--remote-source-root", default="", help="Remote Android source root used for the build.")
    parser.add_argument("--remote-build-command", default="", help="Remote build command or wrapper invocation.")
    parser.add_argument("--remote-build-profile", default="", help="Remote build profile, module group, or wrapper profile.")
    parser.add_argument("--remote-artifact", action="append", default=[], help="Remote build artifact path. Repeatable.")
    parser.add_argument("--artifact-sha1", action="append", default=[], help="SHA1 for the corresponding --remote-artifact. Repeatable.")
    parser.add_argument("--artifact-transfer", default="", help="How the artifact moved from remote build server to member local machine.")
    parser.add_argument("--local-artifact", action="append", default=[], help="Local artifact path used for device delivery. Repeatable.")
    parser.add_argument("--adb-serial", default="", help="Local adb device serial used for verification.")
    parser.add_argument("--adb-action", action="append", default=[], help="Local adb push/install/sync action. Repeatable.")
    parser.add_argument("--device-restart", action="append", default=[], help="Device restart, remount, process restart, or reload action after delivery. Repeatable.")
    parser.add_argument("--risk", default="", help="Risk note for readme.")
    parser.add_argument("--rollback", default="", help="Rollback note for readme.")
    parser.add_argument("--allow-missing-author-date", action="store_true", help="Allow package even when patch lacks //name YYYYMMDD@ marker.")
    parser.add_argument("--allow-banned-logs", action="store_true", help="Allow package even when added lines contain direct Log/Slog calls.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    platform_token, platform_name, android_version = parse_platform_arg(args.platform)
    if not platform_token:
        raise SystemExit("--platform 必须使用受控平台和 Android 版本，例如 rk14、mtk14、unisoc13；不能使用 android14、app15 这类泛化令牌。")

    platform = platform_token
    feature = slug(args.feature)
    args.feature = feature
    captures = collect_repository_captures(args, platform, feature)
    resolved_project, project_inference = infer_capture_project_for_feature(args, captures)
    args.project = resolved_project

    now = dt.datetime.now()
    run_id = args.run_id or f"{now:%Y%m%d-%H%M%S}-feature"
    out_root = Path(args.out_dir).expanduser()
    if not out_root.is_absolute():
        out_root = Path.cwd() / out_root
    package_dir = (out_root / run_id).resolve()
    if package_dir.exists():
        raise SystemExit(f"输出目录已存在: {package_dir}")

    patch_dir = package_dir / "patches"
    evidence_dir = package_dir / "evidence"
    patch_dir.mkdir(parents=True)
    evidence_dir.mkdir(parents=True)

    for capture in captures:
        (patch_dir / capture.patch_name).write_text(capture.diff_text, encoding="utf-8")

    errors: list[str] = []
    warnings: list[str] = []
    auto_verification_payload = load_auto_verification_payload(args)
    verification_payload = verification_result(args, auto_verification_payload)
    search_payload = search_before_change(args)
    feature_facts = aggregate_feature_facts(captures)
    problem_payload, risk_payload = feature_problem_and_risk_payloads(args, captures, feature_facts)
    coding_check = coding_standard_check(args, captures)
    errors.extend(coding_check["errors"])
    warnings.extend(coding_check["warnings"])
    errors.extend(validate_verification_for_status(args, verification_payload))

    package_check = {"status": "FAIL" if errors else "PASS", "errors": errors, "warnings": warnings}
    readme_path = package_dir / "README.md"
    readme_path.write_text(feature_readme_text(args, captures, feature_facts, package_check, coding_check, verification_payload), encoding="utf-8")
    evidence_items = [
        {
            "id": "changed-files",
            "kind": "changed_files",
            "path": "evidence/changed-files.json",
            "result": "INFO",
            "scope": "feature",
            "summary": "changed files and extracted feature facts",
        },
        {
            "id": "verification-result",
            "kind": "verification_result",
            "path": "evidence/verification-result.json",
            "result": verification_payload["result"],
            "scope": "feature",
            "summary": f"{verification_payload['method']} verification evidence",
        },
        {
            "id": "patch-diff-facts",
            "kind": "patch_diff_facts",
            "path": "evidence/patch-diff-facts.json",
            "result": "INFO",
            "scope": "feature",
            "summary": "功能补丁 diff 中解析出的客观事实",
        },
        {
            "id": "patch-problem-summary",
            "kind": "patch_problem_summary",
            "path": "evidence/patch-problem-summary.json",
            "result": "INFO",
            "scope": "feature",
            "summary": "功能对应的问题与方案说明",
        },
        {
            "id": "risk-surface",
            "kind": "risk_surface",
            "path": "evidence/risk-surface.json",
            "result": "INFO",
            "scope": "feature",
            "summary": "功能风险面说明",
        },
        {
            "id": "coding-standard-check",
            "kind": "coding_standard_check",
            "path": "evidence/coding-standard-check.json",
            "result": coding_check["result"],
            "scope": "feature",
            "summary": "团队补丁开发与日志规范检查",
        },
        {
            "id": "search-before-change",
            "kind": "search_before_change",
            "path": "evidence/search-before-change.json",
            "result": "INFO",
            "scope": "feature",
            "summary": "knowledge search performed before development",
        },
        {
            "id": "package-check",
            "kind": "package_check",
            "path": "evidence/package-check.json",
            "result": package_check["status"],
            "scope": "feature",
            "summary": "local patch package checks",
        },
    ]
    evidence_items.extend(collect_external_evidence(args, evidence_dir))

    patch_items = [
        {
            "id": Path(capture.patch_name).stem,
            "path": capture.patch_rel,
            "repo_path": capture.repo_path,
            "source_root": str(capture.source_root),
            "content_sha1": capture.facts["content_sha1"],
            "status": args.status,
            "reuse_hint": args.status == "validated",
            "project": args.project,
            "platform_token": platform_token,
            "platform": platform_name,
            "android_version": android_version,
            "implementation_origin": args.implementation_origin,
            "captured_by": "codex",
            "facts": capture.facts,
        }
        for capture in captures
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "package_type": "framework_feature_patch",
        "feature": feature,
        "readme": "README.md",
        "project": args.project,
        "platform_token": platform_token,
        "platform": platform_name,
        "android_version": android_version,
        "summary": args.summary,
        "status": args.status,
        "implementation_origin": args.implementation_origin,
        "captured_by": "codex",
        "coding_standard_check": {
            "required": implementation_review_required(args.implementation_origin),
            "mode": implementation_review_mode(args.implementation_origin),
            "path": "evidence/coding-standard-check.json",
            "result": coding_check["result"],
        },
        "created_at": now.isoformat(timespec="seconds"),
        "related_report_run_ids": args.related_report_run_id or [],
        "source_roots": [str(capture.source_root) for capture in captures],
        "git_repositories": [
            {
                "repo_path": capture.repo_path,
                "root": str(capture.source_root),
                "git": capture.git_info,
            }
            for capture in captures
        ],
        "project_inference": project_inference,
        "verification_chain": {
            "remote_build": bool(
                verification_payload.get("remote_build", {}).get("host")
                or verification_payload.get("remote_build", {}).get("source_root")
                or verification_payload.get("remote_build", {}).get("command")
                or verification_payload.get("remote_build", {}).get("artifacts")
            ),
            "local_delivery": bool(
                verification_payload.get("local_delivery", {}).get("transfer")
                or verification_payload.get("local_delivery", {}).get("local_artifacts")
                or verification_payload.get("local_delivery", {}).get("adb_serial")
                or verification_payload.get("local_delivery", {}).get("adb_actions")
            ),
            "device_verification": bool(verification_payload.get("device") or verification_payload.get("steps")),
        },
        "patches": patch_items,
        "evidence": evidence_items,
    }
    write_json(package_dir / "manifest.json", manifest)
    write_json(
        evidence_dir / "changed-files.json",
        {
            "kind": "changed_files",
            "scope": "feature",
            "repositories": [
                {
                    "repo_path": capture.repo_path,
                    "root": str(capture.source_root),
                    "modified_files": prefixed_files(capture.repo_path, capture.facts["modified_files"]),
                }
                for capture in captures
            ],
            "modified_files": feature_facts["modified_files"],
        },
    )
    write_json(evidence_dir / "patch-diff-facts.json", feature_facts)
    write_json(evidence_dir / "patch-problem-summary.json", problem_payload)
    write_json(evidence_dir / "risk-surface.json", risk_payload)
    write_json(evidence_dir / "coding-standard-check.json", coding_check)
    write_json(evidence_dir / "verification-result.json", verification_payload)
    write_json(evidence_dir / "search-before-change.json", search_payload)
    write_json(evidence_dir / "package-check.json", package_check)

    result = {
        "package": str(package_dir),
        "patches": [str(package_dir / capture.patch_rel) for capture in captures],
        "readme": str(readme_path),
        "implementation_origin": args.implementation_origin,
        "local_check": package_check,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
