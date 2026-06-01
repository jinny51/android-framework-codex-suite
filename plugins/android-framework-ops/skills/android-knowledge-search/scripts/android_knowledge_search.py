#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT_MARKERS = (
    Path("index") / "case-index.jsonl",
    Path("index") / "variant-index.jsonl",
    Path("index") / "symbol-index.jsonl",
    Path("index") / "evidence-index.jsonl",
    Path("index") / "search-docs.jsonl",
)
ENV_PREFIXES = ("CODEX_KNOWLEDGE_", "CODEX_REPORT_", "CODEX_WORK_REPORT_")


def expand_path(value: str | os.PathLike[str]) -> Path:
    codex_home_value = os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
    text = str(value).replace("${CODEX_HOME}", codex_home_value).replace("$CODEX_HOME", codex_home_value)
    return Path(os.path.expandvars(os.path.expanduser(text))).resolve()


def codex_home() -> Path:
    return expand_path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def parse_toml_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        body = value[1:-1].strip()
        if not body:
            return []
        items: list[Any] = []
        current = ""
        quote = ""
        for char in body:
            if quote:
                current += char
                if char == quote:
                    quote = ""
            elif char in {"'", '"'}:
                quote = char
                current += char
            elif char == ",":
                items.append(parse_toml_scalar(current))
                current = ""
            else:
                current += char
        if current.strip():
            items.append(parse_toml_scalar(current))
        return items
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    return value


def parse_simple_toml(text: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    current: dict[str, Any] = payload
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = payload
            for part in line[1:-1].split("."):
                key = part.strip().strip('"').strip("'")
                nested = current.setdefault(key, {})
                if not isinstance(nested, dict):
                    nested = {}
                    current[key] = nested
                current = nested
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        current[key.strip()] = parse_toml_scalar(value)
    return payload


def read_toml(path: Path) -> dict[str, Any]:
    try:
        try:
            import tomllib

            return tomllib.loads(path.read_text(encoding="utf-8"))
        except ModuleNotFoundError:
            return parse_simple_toml(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def find_project_report_config(start: Path | None = None) -> Path | None:
    try:
        current = (start or Path.cwd()).resolve()
    except OSError:
        return None
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        candidate = directory / ".codex" / "report.toml"
        if candidate.exists():
            return candidate
    return None


def selected_profile(payload: dict[str, Any]) -> str:
    for prefix in ENV_PREFIXES:
        value = os.environ.get(f"{prefix}PROFILE")
        if value:
            return value
    value = payload.get("default_profile", "")
    return str(value).strip() if value else ""


def configured_worktree_values(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            values.append(value.strip())

    add(payload.get("repo_worktree"))
    server = payload.get("server")
    if isinstance(server, dict):
        add(server.get("worktree"))
        add(server.get("repo_worktree"))
    paths = payload.get("paths")
    if isinstance(paths, dict):
        add(paths.get("worktree"))
        add(paths.get("repo_worktree"))
    profiles = payload.get("profiles")
    profile = selected_profile(payload)
    if profile and isinstance(profiles, dict):
        profile_payload = profiles.get(profile)
        if isinstance(profile_payload, dict):
            add(profile_payload.get("repo_worktree"))
            add(profile_payload.get("worktree"))
    return values


def configured_roots() -> list[Path]:
    roots: list[Path] = []
    for env_key in (
        "CODEX_REPORT_REPO_WORKTREE",
        "CODEX_REPORT_WORKTREE",
        "CODEX_WORK_REPORT_REPO_WORKTREE",
        "CODEX_WORK_REPORT_WORKTREE",
    ):
        if os.environ.get(env_key):
            roots.append(expand_path(os.environ[env_key]))

    home = codex_home()
    config_paths = [
        home / "android-knowledge-search.toml",
        home / "report" / "config.toml",
    ]
    project_config = find_project_report_config()
    if project_config:
        config_paths.append(project_config)

    for path in config_paths:
        if not path.exists():
            continue
        for value in configured_worktree_values(read_toml(path)):
            roots.append(expand_path(value))
    return roots


def codex_documents_roots() -> list[Path]:
    candidates: list[Path] = []
    if os.environ.get("CODEX_DOCUMENTS"):
        candidates.append(expand_path(os.environ["CODEX_DOCUMENTS"]))
    candidates.append(expand_path(Path.home() / "Documents" / "Codex"))

    windows_users = Path("/mnt/c/Users")
    if windows_users.is_dir():
        try:
            for user_dir in windows_users.iterdir():
                candidates.append(user_dir / "Documents" / "Codex")
        except OSError:
            pass

    result: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def is_knowledge_root(path: Path) -> bool:
    return path.is_dir() and any((path / marker).exists() for marker in ROOT_MARKERS)


def parent_candidates(path: Path) -> list[Path]:
    candidates = [path]
    candidates.extend(path.parents)
    return candidates


def candidate_roots(explicit_root: str | None) -> list[Path]:
    candidates: list[Path] = []
    if explicit_root:
        candidates.append(expand_path(explicit_root))
    env_root = os.environ.get("CODEX_KNOWLEDGE_ROOT")
    if env_root:
        candidates.append(expand_path(env_root))
    candidates.extend(configured_roots())

    try:
        candidates.extend(parent_candidates(Path.cwd().resolve()))
    except OSError:
        pass

    home = codex_home()
    for documents in codex_documents_roots():
        candidates.extend(
            [
                documents / "worktrees" / "knowledge",
            ]
        )
    candidates.extend(
        [
            home / "worktrees" / "knowledge",
            home / "knowledge",
            Path("/mnt/z/knowledge/worktree"),
            Path("/mnt/z/knowledge"),
            Path("/home/test35/work/knowledge/worktree"),
        ]
    )

    result: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        try:
            resolved = item.resolve()
        except OSError:
            resolved = item
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def find_root(explicit_root: str | None) -> Path:
    checked: list[str] = []
    for root in candidate_roots(explicit_root):
        checked.append(str(root))
        if is_knowledge_root(root):
            return root
    raise SystemExit(
        "knowledge root not found. Pass --root <path>, set CODEX_KNOWLEDGE_ROOT, or configure repo_worktree. Checked:\n"
        + "\n".join(f" - {item}" for item in checked[:16])
    )


def refresh_root(root: Path) -> str:
    if not (root / ".git").exists():
        return "skip: root is not a Git worktree"
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if status.returncode != 0:
        return f"skip: git status failed: {status.stderr.strip()}"
    if status.stdout.strip():
        return "skip: worktree is dirty"
    pull = subprocess.run(
        ["git", "-C", str(root), "pull", "--ff-only"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if pull.returncode != 0:
        return f"failed: {pull.stderr.strip() or pull.stdout.strip()}"
    return pull.stdout.strip() or "already up to date"


def parse_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def evidence_row(item: dict[str, Any]) -> dict[str, Any]:
    row = dict(item)
    row["evidence_kind"] = row.pop("kind", "")
    row["id"] = row.get("id") or row.get("evidence_id") or ""
    row["payload"] = parse_json(row.get("payload"), {})
    row["kind"] = "evidence"
    return row


def load_from_jsonl(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    search_docs = {str(item.get("case_id", "")): item for item in read_jsonl(root / "index" / "search-docs.jsonl")}
    for item in read_jsonl(root / "index" / "case-index.jsonl"):
        case_id = str(item.get("case_id", ""))
        doc = search_docs.get(case_id, {})
        rows.append(
            {
                **item,
                "kind": "case",
                "id": case_id,
                "source_priority": doc.get("source_priority", item.get("source_priority", 0)),
                "text": doc.get("text", item.get("text", "")),
                "variant_ids": doc.get("variant_ids", item.get("variant_ids", [])),
            }
        )
    for item in read_jsonl(root / "index" / "variant-index.jsonl"):
        rows.append({"kind": "variant", "id": item.get("variant_id", ""), **item})
    for item in read_jsonl(root / "index" / "symbol-index.jsonl"):
        rows.append({"kind": "symbol", "id": item.get("symbol_id", ""), "symbol": item.get("value", ""), **item})
    for item in read_jsonl(root / "index" / "evidence-index.jsonl"):
        rows.append(evidence_row(item))
    if not any(row.get("kind") == "evidence" for row in rows):
        for path in sorted(root.glob("evidence/by-id/*.json")):
            item = parse_json(path.read_text(encoding="utf-8", errors="ignore"), {})
            if isinstance(item, dict):
                rows.append(evidence_row({**item, "path": str(path.relative_to(root))}))
    for path in sorted(root.glob("patches/by-id/*/patch.json")):
        item = parse_json(path.read_text(encoding="utf-8", errors="ignore"), {})
        if isinstance(item, dict):
            rows.append({"kind": "patch", "id": item.get("patch_id", ""), "path": str(path.relative_to(root)), **item})
    for path in sorted(root.glob("reports/by-id/*.json")):
        item = parse_json(path.read_text(encoding="utf-8", errors="ignore"), {})
        if isinstance(item, dict):
            rows.append({"kind": "report", "id": item.get("report_id", ""), "path": str(path.relative_to(root)), **item})
    for path in sorted(root.glob("events/by-id/*.json")):
        item = parse_json(path.read_text(encoding="utf-8", errors="ignore"), {})
        if isinstance(item, dict):
            rows.append({"kind": "event", "id": item.get("event_id", ""), "path": str(path.relative_to(root)), **item})
    return rows


def load_rows(root: Path) -> list[dict[str, Any]]:
    return load_from_jsonl(root)


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(stringify(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {stringify(item)}" for key, item in value.items())
    return str(value)


def row_text(row: dict[str, Any]) -> str:
    keys = [
        "id",
        "type",
        "case_id",
        "variant_id",
        "variant_ids",
        "report_ids",
        "title",
        "problem",
        "requirement_or_symptom",
        "solution_summary",
        "implementation_scope",
        "summary",
        "text",
        "overview",
        "author",
        "member_alias",
        "member_name",
        "project",
        "scope",
        "platform",
        "android_version",
        "repo_paths",
        "repo_path",
        "branch",
        "source_tree",
        "feature_slug",
        "original_patch_name",
        "patch_name",
        "patch_names",
        "content_sha1",
        "filename_confidence",
        "module",
        "status",
        "maturity",
        "package_kind",
        "validation_status",
        "result",
        "kind",
        "evidence_kind",
        "note",
        "source_package",
        "readme",
        "report_path",
        "patch_files",
        "modified_files",
        "modules",
        "symbols",
        "framework_log_keys",
        "system_properties",
        "settings_keys",
        "resource_keys",
        "strings",
        "keywords",
        "inferred_problem",
        "inferred_solution",
        "inferred_keywords",
        "inference_confidence",
        "inference_basis",
        "inference_limits",
        "risk_areas",
        "symbol",
        "path",
        "patch_id",
        "patch_ids",
        "items",
        "payload",
        "package_id",
        "event_id",
    ]
    return " ".join(stringify(row.get(key)) for key in keys)


def query_terms(query: str) -> list[str]:
    return [item.lower() for item in re.split(r"\s+", query.strip()) if item.strip()]


def score_row(row: dict[str, Any], terms: list[str]) -> tuple[int, list[str]]:
    if not terms:
        return 1, []
    weighted_fields = [
        (8, "title"),
        (8, "summary"),
        (8, "problem"),
        (8, "requirement_or_symptom"),
        (8, "solution_summary"),
        (8, "implementation_scope"),
        (8, "text"),
        (8, "feature_slug"),
        (8, "repo_path"),
        (8, "repo_paths"),
        (8, "summary"),
        (7, "scope"),
        (7, "symbol"),
        (7, "maturity"),
        (6, "modified_files"),
        (6, "patch_ids"),
        (6, "modules"),
        (6, "inferred_keywords"),
        (6, "inferred_problem"),
        (6, "payload"),
        (6, "system_properties"),
        (6, "settings_keys"),
        (5, "risk_areas"),
        (5, "symbols"),
        (5, "strings"),
        (5, "framework_log_keys"),
        (4, "overview"),
        (4, "items"),
        (3, "project"),
        (3, "original_patch_name"),
        (3, "id"),
        (3, "case_id"),
        (3, "variant_id"),
        (2, "author"),
        (2, "status"),
        (2, "result"),
        (2, "package_kind"),
        (2, "evidence_kind"),
        (2, "note"),
        (1, "patch_files"),
        (1, "report_path"),
        (1, "path"),
    ]
    full_text = row_text(row).lower()
    score = 0
    matched: list[str] = []
    for term in terms:
        if term not in full_text:
            continue
        matched.append(term)
        score += 1
        for weight, field in weighted_fields:
            if term in stringify(row.get(field)).lower():
                score += weight
    return score, matched


def result_priority(row: dict[str, Any]) -> int:
    priority = 0
    try:
        priority += int(row.get("source_priority") or 0)
    except (TypeError, ValueError):
        pass
    status = str(row.get("status") or row.get("maturity") or "").lower()
    priority += {
        "validated": 50,
        "candidate": 30,
        "draft": 20,
        "failed": 10,
        "blocked": 5,
    }.get(status, 0)
    verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
    if str(verification.get("status", "")).lower() in {"pass", "passed"}:
        priority += 20
    return priority


def result_date(row: dict[str, Any]) -> str:
    return str(row.get("date") or row.get("week_range") or "")


def search(rows: list[dict[str, Any]], q: str, result_type: str, limit: int, include_synthetic: bool) -> list[dict[str, Any]]:
    terms = query_terms(q)
    results: list[dict[str, Any]] = []
    kind_filter = "" if result_type == "all" else result_type
    for row in rows:
        if kind_filter and row.get("kind") != kind_filter:
            continue
        if not include_synthetic and bool(row.get("synthetic_data")):
            continue
        score, matched = score_row(row, terms)
        if score <= 0:
            continue
        normalized = dict(row)
        normalized["_score"] = score
        normalized["_matched_terms"] = matched
        results.append(normalized)
    results.sort(
        key=lambda item: (
            int(item.get("_score", 0)),
            result_priority(item),
            result_date(item),
            str(item.get("id") or item.get("case_id") or item.get("variant_id") or item.get("patch_id") or ""),
        ),
        reverse=True,
    )
    return results[:limit]


def rel_or_empty(root: Path, value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    if text.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", text):
        return text
    return str(root / text)


def compact_list(value: Any, limit: int = 4) -> str:
    items = parse_json(value, value)
    if not isinstance(items, list):
        items = [items] if items else []
    text_items = [localized_analysis_text(str(item)) for item in items if str(item)]
    if len(text_items) > limit:
        return ", ".join(text_items[:limit]) + f" ... (+{len(text_items) - limit})"
    return ", ".join(text_items)


def localized_analysis_text(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    exact = {
        "Launcher or activity launch path may leave window focus in an unexpected state": "Launcher 或 Activity 启动链路可能导致窗口焦点状态异常",
        "Adjust ActivityTaskManager or WindowManager focus update behavior around resumed activity or visible windows": "调整 ActivityTaskManager 或 WindowManager 中恢复 Activity、可见窗口相关的焦点更新逻辑",
        "Power or policy behavior may not match the product requirement": "电源或策略行为可能与产品需求不一致",
        "Adjust policy or power handling code in the modified Framework path": "调整修改路径中的策略或电源处理逻辑",
        "Problem cannot be confidently inferred from patch paths alone": "需要结合修改文件和说明确认问题场景",
        "Review the changed files and readme before reuse": "复用前先核对修改文件和说明",
        "Audio capture/microphone or camera path may not match product permission or fallback policy": "音频录制、麦克风或相机链路可能不符合产品权限或回退策略要求",
        "Adjust Audio/Camera services or HAL paths, then verify recording, camera, scan, and permission-switch scenarios": "调整 Audio/Camera 相关服务或 HAL 路径，并验证录音、拍照、扫码和权限切换场景",
        "Audio route, volume, or microphone behavior may not match the product requirement": "音频路由、音量或麦克风行为可能不符合产品要求",
        "Adjust AudioService, AudioFlinger, or volume policy paths and verify volume, recording, and media playback scenarios": "调整 AudioService、AudioFlinger 或音量策略相关路径，并验证音量、录音和媒体播放场景",
        "Camera preview, scan, capture, or permission behavior may not match the product requirement": "相机预览、扫码、拍照或相机权限行为可能不符合产品要求",
        "Adjust CameraService, Camera2, or camera HAL paths and verify target camera scenarios": "调整 CameraService、Camera2 或相机 HAL 相关路径，并验证目标相机场景",
        "External storage, mount, or app storage-access permission behavior may not match the product requirement": "外部存储、挂载或应用访问存储的权限行为可能不符合产品要求",
        "Adjust vold, VolumeManager, or storage-access paths and verify USB disk, OBB, and external-storage scenarios": "调整 vold、VolumeManager 或存储访问相关路径，并验证 U 盘、OBB 和外部存储访问场景",
        "Wi-Fi service, default configuration, or connection permission behavior may not match the product requirement": "Wi-Fi 服务、默认配置或连接权限行为可能不符合产品要求",
        "Adjust Wi-Fi service or product configuration paths and verify connect, toggle, and permission scenarios": "调整 Wi-Fi service 或产品配置路径，并验证连接、开关和权限相关场景",
        "USB device node, permission, or peripheral detection behavior may not match the product requirement": "USB 设备节点、权限或外设识别行为可能不符合产品要求",
        "Adjust ueventd, USB permission, or device configuration paths and verify target peripheral detection and access permission": "调整 ueventd、USB 权限或设备配置路径，并验证目标外设识别和访问权限",
        "Product build configuration, preinstalled apps, or board-level toggles may not match the project requirement": "产品编译配置、预置应用或板级开关可能不符合项目要求",
        "Adjust BoardConfig, device makefiles, or preinstall lists and verify build artifacts and first-boot state": "调整 BoardConfig、device makefile 或预置应用清单，并验证编译产物和首次开机状态",
        "power or policy behavior": "按键/电源/策略行为",
        "activity launch/resume": "Activity 启动/恢复",
        "window focus": "窗口焦点/显示层级",
        "launcher handoff": "Launcher 交接",
        "input dispatch": "输入分发",
        "system UI behavior": "SystemUI 行为",
        "package install or package state": "包安装/包状态",
        "keyguard or password flow": "锁屏/密码流程",
        "recovery or factory reset flow": "Recovery/恢复出厂流程",
        "split screen behavior": "分屏行为",
        "screenshot behavior": "截屏行为",
        "media sound behavior": "媒体声音行为",
        "launcher workspace or recents": "Launcher 桌面/最近任务",
        "quick settings interaction": "快捷设置交互",
        "modified code path requires requirement-specific verification": "修改路径需按需求验证",
        "settings provider defaults": "Settings 默认值",
        "permission grant state": "权限授权状态",
        "resource overlay or string display": "资源覆盖/字符串显示",
        "wallpaper settings": "壁纸设置",
        "font rendering": "字体显示",
        "locale or language display": "语言/地区显示",
        "settings regulatory info": "法规信息设置",
        "audio route or volume behavior": "音频路由/音量行为",
        "camera behavior": "相机行为",
        "storage or volume management": "存储/挂载管理",
        "wifi service or configuration": "Wi-Fi 服务/配置",
        "usb or device permission": "USB/设备权限",
        "product config or preinstall": "产品配置/预置应用",
        "audio route/volume": "音频路由/音量",
        "storage/volume": "存储/挂载",
        "usb/device permission": "USB/设备权限",
        "product config/preinstall": "产品配置/预置",
    }
    if raw in exact:
        return exact[raw]
    match = re.match(r"^Behavior in (.+) may need correction$", raw)
    if match:
        return f"{match.group(1)} 相关行为需要核对和修正"
    match = re.match(r"^Patch changes (.+) code paths and should be reviewed against the target requirement$", raw)
    if match:
        return f"补丁修改了 {match.group(1)} 相关代码路径，复用前需要按目标需求核对"
    return raw


def format_case(root: Path, row: dict[str, Any], index: int) -> str:
    title = row.get("title") or row.get("case_id") or row.get("id") or "(case)"
    lines = [
        f"{index}. [case] {title}",
        f"   - id: {row.get('case_id') or row.get('id', '')}",
    ]
    if row.get("problem") or row.get("requirement_or_symptom"):
        lines.append(f"   - 问题/需求: {row.get('problem') or row.get('requirement_or_symptom')}")
    if row.get("solution_summary"):
        lines.append(f"   - 方案摘要: {row.get('solution_summary')}")
    if row.get("variant_ids"):
        lines.append(f"   - variants: {compact_list(row.get('variant_ids'), 6)}")
    if row.get("source_priority"):
        lines.append(f"   - source_priority: {row.get('source_priority')}")
    if row.get("_matched_terms"):
        lines.append(f"   - matched: {', '.join(row.get('_matched_terms', []))}")
    return "\n".join(lines)


def format_variant(root: Path, row: dict[str, Any], index: int) -> str:
    title = row.get("implementation_scope") or row.get("variant_id") or row.get("id") or "(variant)"
    lines = [
        f"{index}. [variant] {title}",
        f"   - id: {row.get('variant_id') or row.get('id', '')}",
        f"   - case/status: {row.get('case_id', '')} / {row.get('status', '')}",
    ]
    lines.append(
        "   - 平台/Android/项目: "
        f"{row.get('platform') or 'unknown'} / {row.get('android_version') or 'unknown'} / {row.get('project') or 'unknown'}"
    )
    if row.get("repo_paths"):
        lines.append(f"   - 仓库路径: {compact_list(row.get('repo_paths'), 6)}")
    if row.get("modified_files"):
        lines.append(f"   - 修改文件: {compact_list(row.get('modified_files'), 6)}")
    if row.get("patch_ids"):
        lines.append(f"   - patches: {compact_list(row.get('patch_ids'), 6)}")
    verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
    if verification:
        lines.append(f"   - 验证: {verification.get('status', '')} / {verification.get('method', '')} / {verification.get('summary', '')}")
    if row.get("report_ids"):
        lines.append(f"   - reports: {compact_list(row.get('report_ids'), 6)}")
    if row.get("_matched_terms"):
        lines.append(f"   - matched: {', '.join(row.get('_matched_terms', []))}")
    return "\n".join(lines)


def format_patch(root: Path, row: dict[str, Any], index: int) -> str:
    title = row.get("title") or row.get("summary") or row.get("patch_name") or row.get("id") or row.get("patch_id") or "(untitled patch)"
    lines = [
        f"{index}. [patch] {title}",
        f"   - id: {row.get('id') or row.get('patch_id', '')}",
        f"   - author/date/status: {row.get('author', '')} / {result_date(row)} / {row.get('status', '') or 'unknown'}",
    ]
    if row.get("project"):
        lines.append(f"   - project: {row.get('project')}")
    if row.get("scope") or row.get("repo_path") or row.get("feature_slug"):
        lines.append(
            "   - scope/repo/feature: "
            f"{row.get('scope') or 'unknown'} / {row.get('repo_path') or 'unknown'} / {row.get('feature_slug') or 'unknown'}"
        )
    if row.get("filename_confidence") or row.get("original_patch_name"):
        lines.append(f"   - filename: {row.get('filename_confidence') or 'unknown'} / {row.get('original_patch_name') or ''}")
    if row.get("summary") and row.get("summary") != title:
        lines.append(f"   - summary: {row.get('summary')}")
    if row.get("modified_files"):
        lines.append(f"   - modified_files: {compact_list(row.get('modified_files'))}")
    if row.get("modules"):
        lines.append(f"   - modules: {compact_list(row.get('modules'))}")
    if row.get("inferred_problem") or row.get("inferred_solution"):
        lines.append(
            "   - 补丁问题线索: "
            f"{localized_analysis_text(row.get('inferred_problem') or '')}"
        )
        if row.get("inferred_solution"):
            lines.append(f"   - 补丁方案线索: {localized_analysis_text(row.get('inferred_solution') or '')}")
    if row.get("inferred_keywords") or row.get("risk_areas"):
        lines.append(
            "   - 关键词/风险面: "
            f"{compact_list(row.get('inferred_keywords'))}"
            f" / {compact_list(row.get('risk_areas'))}"
        )
    symbols = compact_list(
        [
            *parse_json(row.get("system_properties"), []),
            *parse_json(row.get("settings_keys"), []),
            *parse_json(row.get("resource_keys"), []),
            *parse_json(row.get("strings"), []),
            *parse_json(row.get("framework_log_keys"), []),
        ]
    )
    if symbols:
        lines.append(f"   - symbols: {symbols}")
    if row.get("readme"):
        lines.append(f"   - readme: {rel_or_empty(root, row.get('readme'))}")
    if row.get("patch_files"):
        patch_files = parse_json(row.get("patch_files"), [])
        if patch_files:
            lines.append(f"   - patch: {rel_or_empty(root, patch_files[0])}")
    elif row.get("path"):
        lines.append(f"   - patch: {rel_or_empty(root, Path(str(row.get('path'))).parent / 'patch.patch')}")
    if row.get("_matched_terms"):
        lines.append(f"   - matched: {', '.join(row.get('_matched_terms', []))}")
    return "\n".join(lines)


def format_report(root: Path, row: dict[str, Any], index: int) -> str:
    title = row.get("overview") or row.get("id") or "(report)"
    lines = [
        f"{index}. [report] {title}",
        f"   - id: {row.get('id', '')}",
        f"   - type/author/date: {row.get('type', '')} / {row.get('author', '')} / {result_date(row)}",
    ]
    items = row.get("items") or []
    if isinstance(items, list) and items:
        sample = []
        for item in items[:3]:
            sample.append(f"{item.get('project', '')}:{item.get('title', '')}".strip(":"))
        lines.append(f"   - items: {', '.join(sample)}")
    if row.get("report_path"):
        lines.append(f"   - report: {rel_or_empty(root, row.get('report_path'))}")
    if row.get("_matched_terms"):
        lines.append(f"   - matched: {', '.join(row.get('_matched_terms', []))}")
    return "\n".join(lines)


def format_symbol(root: Path, row: dict[str, Any], index: int) -> str:
    lines = [
        f"{index}. [symbol] {row.get('symbol', '')}",
        f"   - type/patch/author: {row.get('type', '')} / {row.get('patch_id', '')} / {row.get('author', '')}",
    ]
    if row.get("path"):
        lines.append(f"   - path: {rel_or_empty(root, row.get('path'))}")
    if row.get("_matched_terms"):
        lines.append(f"   - matched: {', '.join(row.get('_matched_terms', []))}")
    return "\n".join(lines)


def format_event(root: Path, row: dict[str, Any], index: int) -> str:
    title = row.get("summary") or row.get("id") or "(knowledge event)"
    lines = [
        f"{index}. [event] {title}",
        f"   - id: {row.get('id', '')}",
        f"   - kind/maturity: {row.get('package_kind', '')} / {row.get('maturity', '')}",
        f"   - member/date/platform: {row.get('member', '')} / {result_date(row)} / {row.get('platform', '')}",
    ]
    if row.get("project"):
        lines.append(f"   - project: {row.get('project')}")
    if row.get("path"):
        lines.append(f"   - event: {rel_or_empty(root, row.get('path'))}")
    if row.get("_matched_terms"):
        lines.append(f"   - matched: {', '.join(row.get('_matched_terms', []))}")
    return "\n".join(lines)


def format_evidence(root: Path, row: dict[str, Any], index: int) -> str:
    title = row.get("summary") or row.get("id") or "(evidence)"
    lines = [
        f"{index}. [evidence] {title}",
        f"   - id: {row.get('id', '')}",
        f"   - event/kind/result: {row.get('event_id', '')} / {row.get('evidence_kind', '')} / {row.get('result', '')}",
    ]
    if row.get("maturity") or row.get("project") or row.get("platform"):
        lines.append(f"   - context: {row.get('maturity', '')} / {row.get('project', '')} / {row.get('platform', '')}")
    if row.get("path"):
        lines.append(f"   - evidence: {rel_or_empty(root, row.get('path'))}")
    if row.get("_matched_terms"):
        lines.append(f"   - matched: {', '.join(row.get('_matched_terms', []))}")
    return "\n".join(lines)


def format_markdown(root: Path, q: str, results: list[dict[str, Any]], refresh_status: str | None) -> str:
    lines = [
        "# 知识库搜索结果",
        "",
        f"- root: {root}",
        f"- query: {q or '(empty)'}",
        f"- results: {len(results)}",
    ]
    if refresh_status:
        lines.append(f"- refresh: {refresh_status}")
    lines.append("")
    if not results:
        lines.append("未找到匹配结果。可以换用类名、文件路径、属性名、Settings key、资源 key 或项目名再搜。")
        return "\n".join(lines)

    for index, row in enumerate(results, start=1):
        kind = row.get("kind")
        if kind == "case":
            lines.append(format_case(root, row, index))
        elif kind == "variant":
            lines.append(format_variant(root, row, index))
        elif kind == "patch":
            lines.append(format_patch(root, row, index))
        elif kind == "report":
            lines.append(format_report(root, row, index))
        elif kind == "symbol":
            lines.append(format_symbol(root, row, index))
        elif kind == "event":
            lines.append(format_event(root, row, index))
        elif kind == "evidence":
            lines.append(format_evidence(root, row, index))
        else:
            lines.append(f"{index}. [{kind}] {row.get('id') or row.get('title') or row.get('symbol')}")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search the Codex team knowledge repository.")
    parser.add_argument("query", nargs="*", help="Search terms. Use spaces to combine feature words, files, symbols, or project names.")
    parser.add_argument("--root", help="Knowledge repository worktree path.")
    parser.add_argument("--type", choices=["all", "case", "variant", "patch", "report", "symbol", "event", "evidence"], default="all", help="Result type filter.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum result count.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--refresh", action="store_true", help="Run git pull --ff-only first when root is a clean Git worktree.")
    parser.add_argument("--include-synthetic", action="store_true", help="Include synthetic test data.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    query = " ".join(args.query).strip()
    root = find_root(args.root)
    refresh_status = refresh_root(root) if args.refresh else None
    rows = load_rows(root)
    results = search(rows, query, args.type, max(args.limit, 1), args.include_synthetic)

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "query": query,
                    "type": args.type,
                    "count": len(results),
                    "refresh": refresh_status,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(format_markdown(root, query, results, refresh_status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
