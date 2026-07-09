#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
OPS_PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if OPS_PLUGIN_LIB.is_dir() and str(OPS_PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(OPS_PLUGIN_LIB))

from android_framework_ops.knowledge_rules import (
    VALID_FRAMEWORK_PLATFORMS,
    aggregate_package_scope_errors,
    apply_platform_overrides,
    find_company_project,
    find_company_projects,
    find_platform_tokens,
    has_uncontrolled_patch_asset_prefix,
    is_valid_android_version_value,
    is_valid_platform_value,
    normalize_android_version,
    parse_company_project,
    parse_known_platform_token,
    parse_platform_token,
    parse_version_only_token,
    patch_asset_correction_source_errors,
    patch_upload_gate_errors,
    split_company_project,
    supplement_target_relation_errors,
    template_leak_errors,
    text_field_quality_errors,
)
PLUGIN_UPDATE_SKIP_ENV = "CODEX_REPORT_SKIP_PLUGIN_UPDATE_CHECK"
PLUGIN_UPDATE_REQUIRE_ENV = "CODEX_REPORT_REQUIRE_PLUGIN_UPDATE_CHECK"
PLUGIN_REEXEC_ATTEMPT_ENV = "CODEX_REPORT_PLUGIN_REEXEC_ATTEMPTED"
PLUGIN_REMOTE_MANIFEST_TIMEOUT = 6
PATCH_FILENAME_RE = re.compile(r"^[a-z0-9]+[0-9]+-[A-Za-z0-9._-]+@[a-z0-9_.-]+\.patch$")
USB_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])usb(?![A-Za-z0-9])", re.I)
USB_CAMEL_PATH_RE = re.compile(r"(?:^|[/_.-])Usb(?=[A-Z0-9])")
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
REPORT_HEADINGS = {
    "daily": ("今日概览", "项目事项"),
    "weekly": ("本周概览", "项目事项"),
}
PACKAGE_TYPES = {"daily", "weekly", "patch"}
PATCH_README_HEADINGS = ("功能描述", "修改点", "日志控制", "SystemProperties", "字符串国际化", "可回滚性")
PATCH_README_PLACEHOLDER_RE = re.compile(r"(?im)^\s*(?:[-*]\s*)?TODO\b|TODO:")
PATCH_README_FORBIDDEN_MARKERS = (
    "自动生成的草稿说明",
    "根据补丁 diff 自动生成",
    "当前说明仅根据 diff 自动生成",
)
INCOMING_KINDS = {"daily_trace", "weekly_trace", "framework_change"}
PACKAGE_STATUS_VALUES = {"validated", "candidate", "draft", "failed", "blocked"}
MATERIALS_DIR = "materials"
TRACE_REQUIRED_EVIDENCE_KINDS = {"source", "work_findings"}
FRAMEWORK_REQUIRED_EVIDENCE_KINDS = {
    "source",
    "patch_diff_facts",
    "patch_ai_facts",
    "project_inference",
    "patch_problem_summary",
    "risk_surface",
    "verification_result",
    "search_before_change",
}
FIELD_CORRECTION_REQUIRED_EVIDENCE_KINDS = {"source", "project_inference", "evidence_supplement", "field_correction"}
SUPPLEMENT_MODES = {"field_correction", "asset_correction"}
FIELD_CORRECTION_ALLOWED_FIELDS = {
    "project",
    "platform",
    "android_version",
}
FIELD_CORRECTION_MATERIAL_IDENTITY_FIELDS = {
    "material_name",
    "material_summary",
    "feature",
    "feature_name",
    "function_name",
    "display_title",
    "summary",
    "patch_view",
    "report_view",
}
FIELD_CORRECTION_FORBIDDEN_FIELDS = {
    "patch",
    "patches",
    "patch_assets",
    "patch_diff",
    "patch_diff_facts",
    "patch_ai_facts",
    "verification",
    "verification_result",
    "device_verification",
    "equivalent_verification",
    "build_result",
    "deploy_result",
    "search_before_change",
    "search_usage",
    "code_anchors",
    *FIELD_CORRECTION_MATERIAL_IDENTITY_FIELDS,
}
FIELD_CORRECTION_FORBIDDEN_EVIDENCE_KINDS = {
    "patch_diff_facts",
    "patch_ai_facts",
    "verification_result",
    "device_verification",
    "equivalent_verification",
    "build_result",
    "deploy_result",
    "search_before_change",
}
FRAMEWORK_OPTIONAL_EVIDENCE_KINDS = {"build_result", "deploy_result", "device_health"}
REQUIRED_PATCH_EXPLANATION_KINDS = {"patch_problem_summary", "risk_surface"}
LEGACY_PATCH_PROBLEM_KIND = "patch_" + "problem_" + "inference"
DATE_KEY_RE = re.compile(r"^\d{8}$")
DATE_DISPLAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RUN_ID_RE = re.compile(r"^\d{8}-\d{6}(-[A-Za-z0-9_.-]+)?$")
MEMBER_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


LAST_PLUGIN_VERSION_GATE: dict[str, Any] | None = None


@dataclass
class PatchInfo:
    path: Path
    name: str
    project: str


from akbs_intake import version_gate as _version_gate  # noqa: E402
from akbs_intake.version_gate import (  # noqa: E402
    LAST_PLUGIN_VERSION_GATE,
    auto_update_packaged_plugin,
    compare_versions,
    current_skill_cache_metadata,
    env_enabled,
    fetch_remote_plugin_manifest,
    github_raw_plugin_manifest_url,
    latest_installed_plugin_cache_metadata,
    packaged_plugin_freshness,
    plugin_freshness_check,
    plugin_install_metadata,
    plugin_manifest_path,
    plugin_update_unknown,
    plugin_version_gate_check,
    reexec_latest_plugin_script_after_update,
    run,
    updated_plugin_intake_script_path,
    version_parts,
)

_ORIGINAL_VERSION_GATE_RUN = getattr(_version_gate, "_AKBS_ORIGINAL_RUN", _version_gate.run)
_ORIGINAL_VERSION_GATE_FETCH_REMOTE_PLUGIN_MANIFEST = getattr(
    _version_gate,
    "_AKBS_ORIGINAL_FETCH_REMOTE_PLUGIN_MANIFEST",
    _version_gate.fetch_remote_plugin_manifest,
)
_version_gate._AKBS_ORIGINAL_RUN = _ORIGINAL_VERSION_GATE_RUN
_version_gate._AKBS_ORIGINAL_FETCH_REMOTE_PLUGIN_MANIFEST = _ORIGINAL_VERSION_GATE_FETCH_REMOTE_PLUGIN_MANIFEST
run = _ORIGINAL_VERSION_GATE_RUN
fetch_remote_plugin_manifest = _ORIGINAL_VERSION_GATE_FETCH_REMOTE_PLUGIN_MANIFEST


def _call_version_gate(callback):
    original_root = _version_gate.PLUGIN_ROOT
    original_run = _version_gate.run
    original_fetch_remote = _version_gate.fetch_remote_plugin_manifest
    _version_gate.PLUGIN_ROOT = PLUGIN_ROOT
    _version_gate.run = run
    _version_gate.fetch_remote_plugin_manifest = fetch_remote_plugin_manifest
    try:
        return callback()
    finally:
        _version_gate.PLUGIN_ROOT = original_root
        _version_gate.run = original_run
        _version_gate.fetch_remote_plugin_manifest = original_fetch_remote


def plugin_install_metadata() -> dict[str, str]:
    return _call_version_gate(_version_gate.plugin_install_metadata)


def current_skill_cache_metadata() -> dict[str, str]:
    return _call_version_gate(_version_gate.current_skill_cache_metadata)


def latest_installed_plugin_cache_metadata(plugin_name: str = "android-framework-ops") -> dict[str, str]:
    return _call_version_gate(lambda: _version_gate.latest_installed_plugin_cache_metadata(plugin_name))


def plugin_freshness_check(fetch: bool = True, require: bool = False) -> dict[str, Any]:
    return _call_version_gate(lambda: _version_gate.plugin_freshness_check(fetch=fetch, require=require))


def plugin_version_gate_check(config: dict[str, str] | None = None, fetch: bool = True, require: bool = True) -> dict[str, Any]:
    global LAST_PLUGIN_VERSION_GATE
    gate = _call_version_gate(lambda: _version_gate.plugin_version_gate_check(config=config, fetch=fetch, require=require))
    LAST_PLUGIN_VERSION_GATE = gate
    return gate


def synthetic_mode(config: dict[str, str]) -> bool:
    return parse_bool(config.get("synthetic_data", "false"))


from akbs_intake.config import (  # noqa: E402
    AKBS_ENDPOINT_DEFAULTS,
    AKBS_ENDPOINT_ENV_PREFIXES,
    CONFIG_DEFAULTS,
    DEFAULT_KNOWLEDGE_REPO_URL,
    DEFAULT_SUBMISSION_API_BASE_URL,
    DEFAULT_SUBMISSION_API_TOKEN,
    DEFAULT_SUBMISSION_SESSION_COOKIE,
    ENV_PREFIXES,
    INCOMING_SCHEMA_VERSION,
    LEGACY_TEST35_ENDPOINT_VALUES,
    akbs_endpoint_env_value,
    allowed_modes,
    apply_env_overrides,
    artifact_path_guard_error,
    configured_endpoint_fields,
    default_codex_home,
    enforce_mode_allowed,
    endpoint_migration_report,
    expanded_path,
    find_project_report_config,
    flatten_config_payload,
    knowledge_repo_url,
    knowledge_repo_worktree,
    load_config,
    local_now,
    parse_bool,
    parse_date_arg,
    parse_simple_toml,
    parse_toml_scalar,
    profile_configs,
    profile_from_env,
    read_toml,
    require_config,
    require_safe_artifact_path,
    resolve_akbs_endpoint,
    stringify_config_value,
    submission_api_base_url,
    submission_api_token,
    submission_session_cookie,
)
from akbs_intake.report_sessions import (  # noqa: E402
    MISSING_REPORT_CUSTOMER,
    NOISE_TEXT_RE,
    REPORT_MISSING_PROJECT_VALUES,
    SessionWork,
    compact_text,
    git_branch_or_name as _report_git_branch_or_name,
    git_root as _report_git_root,
    is_report_generation_request,
    parse_sessions as _parse_sessions,
    project_anchor,
    report_customer_for_project,
    report_project_customers_from_clues,
    should_skip_message,
    strip_project_anchor,
    synthetic_sessions,
    week_bounds,
    ymd,
)
from akbs_intake.doctor import (  # noqa: E402
    doctor as _intake_doctor,
    doctor_strict_checks as _intake_doctor_strict_checks,
    git_run as _intake_git_run,
    latest_pending as _intake_latest_pending,
    nearest_existing_parent,
)


def git_root(path: str) -> Path | None:
    return _report_git_root(path, run)


def git_branch_or_name(path: str) -> str:
    return _report_git_branch_or_name(path, run)


def parse_sessions(config: dict[str, str], dates: set[dt.date]) -> list[SessionWork]:
    return _parse_sessions(config, dates, run)


def synthetic_patch_info(package_dir: Path, date: dt.date, project: str, config: dict[str, str]) -> PatchInfo:
    token = uuid.uuid4().hex[:8]
    patch_dir = package_dir / "evidence" / "synthetic"
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_name = f"mtk15-frameworks-base@synthetic-settings-{token}.patch"
    patch_path = patch_dir / patch_name
    readme_path = patch_dir / f"{patch_path.stem}.readme.md"
    patch_path.write_text(
        "\n".join(
            [
                "diff --git a/frameworks/base/core/java/android/provider/Settings.java b/frameworks/base/core/java/android/provider/Settings.java",
                "--- a/frameworks/base/core/java/android/provider/Settings.java",
                "+++ b/frameworks/base/core/java/android/provider/Settings.java",
                "@@ -1,3 +1,4 @@",
                f"+//synthetic {ymd(date)}@ synthetic test patch, not from real source code",
                "+// synthetic setting key: persist.sys.codex.synthetic_flag",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    readme_path.write_text(
        f"""# {patch_name}

## 功能描述

合成测试补丁，用于验证 incoming 协议、服务器解析、索引构建和可视化展示流程，不来自真实源码仓库。

## 修改点

- 合成一条注释级 diff，避免引入真实业务代码。
- 合成系统属性 `persist.sys.codex.synthetic_flag`，用于验证 symbol 索引。

## 日志控制

无新增运行时日志。

## SystemProperties

`persist.sys.codex.synthetic_flag`，仅作为合成测试索引样例。

## 字符串国际化

无新增字符串资源。

## 可回滚性

合成测试包可直接删除对应 incoming/patches 归档，不参与真实版本回滚。

## 补丁状态

- status: draft
- reuse_hint: false
- owner: {config["member_name"]} ({config["member_alias"]})
""",
        encoding="utf-8",
    )
    return PatchInfo(path=patch_path, name=patch_name, project=project)


def summarize_session(work: SessionWork) -> str:
    text = " ".join([work.thread_name, *work.messages]).lower()
    if all(keyword in text for keyword in ("codex", "日报")) and any(keyword in text for keyword in ("自动化", "skill", "插件", "知识库")):
        return "搭建 Codex incoming 自动上传材料与知识库检索能力"
    project = project_anchor(" ".join([work.project, work.thread_name, *work.messages]))
    messages = [
        item
        for item in work.messages
        if not item.startswith("执行命令:") and not should_skip_message(item) and not is_report_generation_request(item)
    ]
    anchored_messages = [item for item in messages if project and project.lower() in item.lower()]
    candidates = anchored_messages or messages
    if candidates:
        summaries = [clean_work_summary(item, project) for item in candidates[:3]]
        summary = "；".join(item for item in summaries if item)
        if summary:
            return compact_text(summary, 240)
    name = work.thread_name.strip()
    if name and not re.fullmatch(r"[0-9a-f-]{20,}", name) and not NOISE_TEXT_RE.search(name):
        summary = clean_work_summary(name, project)
        if summary:
            return compact_text(summary, 120)
    return "处理Codex对话中的开发问题"


def clean_work_summary(text: str, project: str) -> str:
    text = strip_project_anchor(text, project)
    text = re.sub(r"(?i)\b(?:today|daily|weekly)\b", " ", text)
    text = re.sub(r"^(?:今天|今日|本周|继续|主要|围绕|完成|处理|修复|排查|整理|在|通过)\s*", "", text)
    text = re.sub(r"源码里\s*", "", text)
    text = re.sub(r"连接服务器\s*", "", text)
    text = re.sub(r"通过\s*[，,]?\s*", "", text)
    text = re.sub(r"在\s*/?\s*处理", "处理", text)
    text = re.sub(r"在\s*/?\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ，,。；;")
    return text


def progress_phrase(text: str) -> str:
    progress = ""
    match = re.search(r"(?:进度|完成度)[:：]?\s*([0-9]{1,3}%\s*(?:->|~|～|-|到)\s*[0-9]{1,3}%|[0-9]{1,3}%)", text)
    if match:
        progress = match.group(1).replace(" ", "")
    if any(word in text for word in ("阻塞", "blocked", "缺少", "等待", "依赖")):
        status = "阻塞"
    elif any(word in text for word in ("待验证", "验证中", "等待测试验证", "待设备验证", "待客户验证")):
        status = "待验证"
    elif any(word in text for word in ("失败", "报错", "未解决", "未完成", "待处理", "继续排查", "修改中", "处理中")):
        status = "处理中"
    elif any(word in text for word in ("已完成", "解决", "修复", "成功", "通过", "验证完成", "改好", "完成")):
        status = "已完成"
    else:
        status = ""
    if progress and status:
        return f"{progress}，{status}"
    return progress or status


def progress_for_session(work: SessionWork, has_patch: bool) -> str:
    text = " ".join([work.thread_name, *work.messages])
    phrase = progress_phrase(text)
    if phrase:
        return phrase
    if any(word in text for word in ("失败", "报错", "未解决", "未完成", "待处理", "继续排查")):
        return "进行中"
    if any(word in text for word in ("已完成", "解决", "修复", "成功", "通过", "验证完成", "改好", "完成")):
        return "已完成并产出 Patch" if has_patch else "已完成"
    return "已产出 Patch" if has_patch else "进行中"


def work_finding_for_session(session: SessionWork) -> dict[str, Any]:
    text = " ".join([session.thread_name, session.cwd, *session.messages]).lower()
    blocked = any(word in text for word in ("失败", "报错", "未解决", "阻塞", "blocked", "fail"))
    framework_like = any(
        token in text
        for token in (
            "framework",
            "frameworks/base",
            "systemui",
            "launcher",
            "settings",
            "patch",
            "补丁",
            "修复",
            "验证",
        )
    )
    if blocked:
        work_status = "blocked"
    elif framework_like:
        work_status = "candidate"
    else:
        work_status = "draft"
    basis = [session.thread_name or session.session_id]
    if session.cwd:
        basis.append(f"工作目录: {session.cwd}")
    basis.extend(session.messages[:3])
    missing_evidence = []
    if framework_like:
        missing_evidence.append("需要 patch-capture 判断是否可升级为 framework_change")
    else:
        missing_evidence.append("未识别到可直接归档的 Framework patch")
    return {
        "title": summarize_session(session),
        "kind": "possible_framework_change" if framework_like else "work_record",
        "work_status": work_status,
        "project": session.project,
        "basis": basis,
        "missing_evidence": missing_evidence,
        "recommended_action": "补齐 diff、构建或验证证据后再判断是否升级为 framework_change",
    }


def discover_patches(config: dict[str, str], sessions: list[SessionWork], start: dt.date, end: dt.date) -> list[PatchInfo]:
    if not parse_bool(config.get("include_patches", "true")):
        return []
    roots: set[Path] = set()
    for session in sessions:
        if session.cwd and Path(session.cwd).exists():
            root = git_root(session.cwd)
            roots.add(root if root else Path(session.cwd))
            roots.add(Path(session.cwd))
    patches: dict[Path, PatchInfo] = {}
    for base in sorted(roots):
        if not base.exists():
            continue
        candidates: list[Path] = []
        for pattern in ("*.patch", "patches/*.patch"):
            try:
                candidates.extend(path.resolve() for path in base.glob(pattern))
            except OSError:
                continue
        for path in candidates:
            try:
                mdate = dt.datetime.fromtimestamp(path.stat().st_mtime).date()
            except OSError:
                continue
            if not (start <= mdate <= end):
                continue
            project = git_branch_or_name(str(git_root(str(path.parent)) or base))
            patches[path] = PatchInfo(path=path, name=path.name, project=project)
    return sorted(patches.values(), key=lambda item: item.name)


def items_by_project(sessions: list[SessionWork], patches: list[PatchInfo]) -> dict[str, list[tuple[str, str]]]:
    valid_session_projects = sorted(
        dict.fromkeys(project for session in sessions for project in [find_company_project(session.project)] if project)
    )
    fallback_project = valid_session_projects[0] if len(valid_session_projects) == 1 else ""
    patch_projects = {find_company_project(patch.project) or fallback_project or patch.project for patch in patches}
    items: dict[str, list[tuple[str, str]]] = {}
    for session in sessions:
        desc = summarize_session(session)
        progress = progress_for_session(session, session.project in patch_projects)
        entry = (desc, progress)
        if entry not in items.setdefault(session.project, []):
            items[session.project].append(entry)
    for patch in patches:
        project = find_company_project(patch.project) or fallback_project or patch.project
        if not items.get(project):
            items.setdefault(project, []).append(("产出功能补丁", "已产出 Patch"))
    return items


def overview_text(report_type: str, items: dict[str, list[tuple[str, str]]], patches: list[PatchInfo]) -> str:
    tasks: list[str] = []
    for entries in items.values():
        for desc, _ in entries:
            if desc not in tasks and desc != "产出功能补丁":
                tasks.append(desc)
    if not tasks:
        return "未发现可归档事项，无patch。"
    task_text = "、".join(compact_text(item, 36) for item in tasks[:3]) + ("等" if len(tasks) > 3 else "")
    patch_text = f"产出 {len(patches)} 个patch。" if patches else "无patch。"
    prefix = "今天" if report_type == "daily" else "本周"
    return f"{prefix}处理了{task_text}，{patch_text}"


def report_dates(report_type: str, date: dt.date) -> tuple[set[dt.date], dt.date, dt.date, str]:
    if report_type in {"daily", "patch"}:
        return {date}, date, date, ymd(date)
    start, end = week_bounds(date)
    days = {start + dt.timedelta(days=offset) for offset in range((end - start).days + 1)}
    return days, start, end, f"{ymd(start)}-{ymd(end)}"


def paired_readme(path: Path) -> Path | None:
    candidates = [path.with_suffix(".readme.md"), path.with_suffix(".md"), path.with_suffix(".txt")]
    return next((item for item in candidates if item.is_file()), None)


def patch_readme_template(patch: PatchInfo, config: dict[str, str], status: str = "draft", reuse_hint: bool = False) -> str:
    return f"""# {patch.name}

## 功能描述

TODO: 说明这个补丁解决的具体问题、适用平台和复用边界。

## 修改点

- TODO: 列出核心修改文件和关键逻辑。

## 日志控制

TODO: 说明是否使用 FrameworkLog，以及对应的 debug 属性。

## SystemProperties

TODO: 说明新增或依赖的系统属性；没有则写“无”。

## 字符串国际化

TODO: 说明是否新增字符串资源；没有则写“无”。

## 可回滚性

TODO: 说明回滚方式、风险点和验证建议。

## 补丁状态

- status: {status}
- reuse_hint: {str(reuse_hint).lower()}
- owner: {config["member_name"]} ({config["member_alias"]})
"""


def copy_patch_assets(
    package_dir: Path,
    patches: list[PatchInfo],
    config: dict[str, str],
    status: str = "draft",
    reuse_hint: bool = False,
    note: str = "待成员确认复用状态",
) -> list[dict[str, Any]]:
    patch_dir = package_dir / "patches"
    patch_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = int(float(config.get("max_attachment_mb", "5")) * 1024 * 1024)
    entries: list[dict[str, Any]] = []
    for patch in patches:
        if patch.path.stat().st_size > max_bytes:
            continue
        target = patch_dir / patch.name
        shutil.copy2(patch.path, target)
        source_readme = paired_readme(patch.path)
        readme_target = patch_dir / f"{patch.path.stem}.readme.md"
        generated_readme = False
        if source_readme:
            shutil.copy2(source_readme, readme_target)
        else:
            readme_target.write_text(patch_readme_template(patch, config, status, reuse_hint), encoding="utf-8")
            generated_readme = True
        entries.append(
            {
                "path": f"patches/{target.name}",
                "readme": f"patches/{readme_target.name}",
                "content_sha1": sha1_file(target),
                "status": status,
                "reuse_hint": reuse_hint,
                "project": patch.project,
                "implementation_origin": "manual",
                "captured_by": "android-knowledge-intake",
                "coding_standard_check": {
                    "required": True,
                    "mode": "legacy_patch_gate",
                    "result": "UNKNOWN",
                },
                "note": "缺少原始readme，已生成模板，提交前请补充" if generated_readme else note,
            }
        )
    return entries


def patch_infos_from_paths(paths: list[str], project: str) -> list[PatchInfo]:
    result: dict[Path, PatchInfo] = {}
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"patch 文件不存在: {path}")
        if path.suffix != ".patch":
            raise SystemExit(f"不是 .patch 文件: {path}")
        result[path] = PatchInfo(path=path, name=path.name, project=project)
    return sorted(result.values(), key=lambda item: item.name)


def safe_id(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return value or "item"


def sha1_text(value: str, length: int = 10) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def stable_slug_id(value: str, fallback: str, limit: int, hash_source: str | None = None) -> str:
    base = safe_id(value).lower()
    if base == "item":
        base = safe_id(fallback).lower()
    digest = sha1_text(hash_source if hash_source is not None else value)
    head_limit = max(1, limit - len(digest) - 1)
    head = base[:head_limit].strip("-._") or safe_id(fallback).lower()
    return f"{head}-{digest}"[:limit].strip("-._")


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def list_string_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value:
        return [str(value).strip()]
    return []


def unique_strings(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(item for item in values if item))


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"读取 JSON 失败: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"JSON 必须是对象: {path}")
    return payload


def read_optional_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def copy_capture_file(source_root: Path, rel: str, target: Path) -> None:
    source = (source_root / rel).resolve()
    root = source_root.resolve()
    if source != root and root not in source.parents:
        raise SystemExit(f"capture package 引用路径越界: {rel}")
    if not source.is_file():
        raise SystemExit(f"capture package 引用文件不存在: {rel}")
    if target.exists():
        raise SystemExit(f"目标文件已存在，避免覆盖: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def verification_payload_passes(package_root: Path, evidence_item: dict[str, Any]) -> bool:
    if evidence_item.get("kind") not in {"verification_result", "device_verification", "equivalent_verification"}:
        return False
    if evidence_item.get("result") != "PASS":
        return False
    rel = evidence_item.get("path")
    if not isinstance(rel, str) or not rel:
        return False
    payload = read_json_file(package_root / rel)
    if payload.get("result") != "PASS":
        return False
    if payload.get("method") == "device":
        return True
    if payload.get("method") == "equivalent":
        return bool(payload.get("reason") and payload.get("coverage") and "remaining_risk" in payload)
    return False


def copy_patch_capture_packages(
    package_dir: Path,
    package_paths: list[str],
    default_project: str,
    default_status: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], bool, list[str], list[dict[str, Any]], str]:
    if len(package_paths) > 1:
        raise SystemExit("framework_change incoming 一次只接受一个功能级 patch-capture 包；多个功能请分别提交。")
    patch_dir = package_dir / "patches"
    materials_dir = package_dir / MATERIALS_DIR
    evidence_dir = package_dir / MATERIALS_DIR / "evidence" / "capture"
    patch_dir.mkdir(parents=True, exist_ok=True)
    materials_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    patch_entries: list[dict[str, Any]] = []
    evidence_entries: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    has_pass_verification = False
    related_report_run_ids: list[str] = []
    source_contexts: list[dict[str, Any]] = []
    feature_readme_rel = ""

    for raw in package_paths:
        capture_dir = Path(raw).expanduser().resolve()
        manifest = read_json_file(capture_dir / "manifest.json")
        if manifest.get("package_type") != "framework_feature_patch":
            raise SystemExit(f"不是功能级 android-framework-patch-capture 工作包: {capture_dir}")
        readme_rel = str(manifest.get("readme") or "")
        if not readme_rel:
            raise SystemExit(f"capture package 缺少功能 readme: {capture_dir}")
        implementation_origin = str(manifest.get("implementation_origin") or "unknown")
        captured_by = str(manifest.get("captured_by") or "codex")
        coding_standard_check = manifest.get("coding_standard_check") if isinstance(manifest.get("coding_standard_check"), dict) else {}
        feature_readme_rel = materials_rel("readme.md")
        copy_capture_file(capture_dir, readme_rel, package_dir / feature_readme_rel)
        related_report_run_ids.extend(list_string_values(manifest.get("related_report_run_ids")))
        repositories = manifest.get("git_repositories", [])
        if isinstance(repositories, list):
            for repository in repositories:
                if not isinstance(repository, dict):
                    continue
                git = repository.get("git") if isinstance(repository.get("git"), dict) else {}
                source_contexts.append(
                    {
                        "source_root": str(repository.get("root") or ""),
                        "repo_path": str(repository.get("repo_path") or ""),
                        "local_mount_path": str(repository.get("local_mount_path") or ""),
                        "remote_root": str(repository.get("remote_root") or ""),
                        "ssh_host": str(repository.get("ssh_host") or ""),
                        "sdk_name": str(repository.get("sdk_name") or ""),
                        "git_branch": str(git.get("branch") or ""),
                        "git_remote": str(git.get("remote") or ""),
                        "git_remotes": str(git.get("remotes") or ""),
                        "implementation_origin": implementation_origin,
                        "captured_by": captured_by,
                    }
                )
        capture_id = safe_id(capture_dir.name)
        patches = manifest.get("patches", [])
        if not isinstance(patches, list) or not patches:
            raise SystemExit(f"capture package 缺少 patches: {capture_dir}")
        evidence = manifest.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []

        for index, item in enumerate(patches, start=1):
            if not isinstance(item, dict):
                raise SystemExit(f"capture package patches[{index}] 不是对象: {capture_dir}")
            patch_rel = str(item.get("path", ""))
            patch_name = Path(patch_rel).name
            if not patch_name:
                raise SystemExit(f"capture package patch 路径无效: {capture_dir}")
            copy_capture_file(capture_dir, patch_rel, patch_dir / patch_name)
            entry_status = item.get("status") or default_status
            copied_patch = patch_dir / patch_name
            patch_entries.append(
                {
                    "path": f"patches/{patch_name}",
                    "repo_path": str(item.get("repo_path") or ""),
                    "source_root": str(item.get("source_root") or ""),
                    "content_sha1": item.get("content_sha1") or sha1_file(copied_patch),
                    "status": entry_status,
                    "reuse_hint": bool(item.get("reuse_hint", entry_status == "validated")),
                    "project": item.get("project") or manifest.get("project") or default_project,
                    "platform_token": str(item.get("platform_token") or manifest.get("platform_token") or ""),
                    "platform": str(item.get("platform") or manifest.get("platform") or ""),
                    "android_version": str(item.get("android_version") or manifest.get("android_version") or ""),
                    "implementation_origin": str(item.get("implementation_origin") or implementation_origin),
                    "captured_by": str(item.get("captured_by") or captured_by),
                    "coding_standard_check": coding_standard_check,
                    "note": "来自 android-framework-patch-capture 工作包",
                    "facts": item.get("facts") if isinstance(item.get("facts"), dict) else {},
                }
            )
            sources.append(
                {
                    "name": patch_name,
                    "source": str(capture_dir / patch_rel),
                    "project": item.get("project") or default_project,
                    "implementation_origin": str(item.get("implementation_origin") or implementation_origin),
                    "captured_by": str(item.get("captured_by") or captured_by),
                }
            )

        for item in evidence:
            if not isinstance(item, dict):
                continue
            rel = item.get("path")
            if not isinstance(rel, str) or not rel:
                continue
            base_id = safe_id(str(item.get("id") or Path(rel).stem))
            target_name = f"{capture_id}-{Path(rel).name}"
            target = evidence_dir / target_name
            copy_capture_file(capture_dir, rel, target)
            copied = {
                "id": f"{capture_id}-{base_id}",
                "kind": item.get("kind", "capture_evidence"),
                "path": materials_rel("evidence", "capture", target_name),
                "result": item.get("result", "INFO"),
                "summary": item.get("summary", "captured patch evidence"),
            }
            evidence_entries.append(copied)
            if verification_payload_passes(capture_dir, item):
                has_pass_verification = True

    return patch_entries, evidence_entries, sources, has_pass_verification, unique_strings(related_report_run_ids), source_contexts, feature_readme_rel


def discover_patches_from_cwd(project: str, date: dt.date) -> list[PatchInfo]:
    candidates: dict[Path, PatchInfo] = {}
    for pattern in ("*.patch", "patches/*.patch"):
        for path in Path.cwd().glob(pattern):
            if not path.is_file():
                continue
            try:
                mdate = dt.datetime.fromtimestamp(path.stat().st_mtime).date()
            except OSError:
                continue
            if mdate == date:
                resolved = path.resolve()
                candidates[resolved] = PatchInfo(path=resolved, name=resolved.name, project=project)
    return sorted(candidates.values(), key=lambda item: item.name)


def has_heading(text: str, heading: str) -> bool:
    return re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.M) is not None


def validate_patch_readme(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        return [f"{path.name} readme 不能为空"]
    if PATCH_README_PLACEHOLDER_RE.search(text):
        errors.append(f"{path.name} readme 仍包含 TODO 模板内容")
    for marker in PATCH_README_FORBIDDEN_MARKERS:
        if marker in text:
            errors.append(f"{path.name} readme 包含草稿/模板说明: {marker}")
    for heading in PATCH_README_HEADINGS:
        if not has_heading(text, heading):
            errors.append(f"{path.name} 缺少必填章节: ## {heading}")
    return errors


def patch_readme_usable_for_inference(path: Path) -> bool:
    return path.is_file() and not validate_patch_readme(path)


def evidence_payload(evidence: dict[str, Any]) -> dict[str, Any]:
    payload = evidence.get("payload")
    return payload if isinstance(payload, dict) else evidence


def patch_capture_package_scope_errors(package_paths: list[str] | None, summary: str, run_id: str) -> list[str]:
    texts = [str(summary or ""), str(run_id or "")]
    patch_count = 0
    for raw in package_paths or []:
        capture_dir = Path(raw).expanduser().resolve()
        manifest = read_json_file(capture_dir / "manifest.json")
        texts.append(str(manifest.get("summary") or ""))
        texts.append(str(manifest.get("feature") or ""))
        patches = manifest.get("patches")
        if isinstance(patches, list):
            patch_count = max(patch_count, len(patches))
        readme_rel = str(manifest.get("readme") or "")
        if readme_rel:
            readme_path = (capture_dir / readme_rel).resolve()
            root = capture_dir.resolve()
            try:
                readme_path.relative_to(root)
            except ValueError as exc:
                raise SystemExit(f"capture package readme 路径越界: {readme_rel}") from exc
            if readme_path.is_file():
                texts.append(readme_path.read_text(encoding="utf-8", errors="ignore"))
    return aggregate_package_scope_errors("\n".join(texts), patch_count)


def validate_patch_file(path: Path) -> list[str]:
    errors: list[str] = []
    if not PATCH_FILENAME_RE.fullmatch(path.name):
        errors.append(f"patch 文件名不符合规范: {path.name}")
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not AUTHOR_DATE_RE.search(text):
        errors.append(f"{path.name} 缺少作者日期备注，例如 //gyf 20251016@")
    added_lines = [line for line in text.splitlines() if line.startswith("+") and not line.startswith("+++")]
    for pattern in BANNED_LOG_PATTERNS:
        if any(pattern in line for line in added_lines):
            errors.append(f"{path.name} 新增代码禁止直接使用 {pattern}，应使用 FrameworkLog")
            break
    readme = paired_readme(path)
    if not readme:
        errors.append(f"{path.name} 缺少配套 readme")
    else:
        errors.extend(validate_patch_readme(readme))
    return errors


def write_feature_readme_from_patch_entries(package_dir: Path, summary: str, patch_entries: list[dict[str, Any]]) -> str:
    target_rel = materials_rel("readme.md")
    target = package_dir / target_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    for entry in patch_entries:
        readme_rel = entry.get("readme")
        if isinstance(readme_rel, str) and readme_rel:
            source = package_dir / readme_rel
            if source.is_file():
                shutil.copy2(source, target)
                return target_rel
    patches = "\n".join(f"- `{entry.get('path', '')}`" for entry in patch_entries) or "- 待补充"
    target.write_text(
        f"""# {summary}

## 功能描述

TODO: 说明这个功能解决的具体问题、适用平台和复用边界。

## 修改点

{patches}

## 日志控制

TODO: 说明是否使用 FrameworkLog，以及对应的 debug 属性。

## SystemProperties

TODO: 说明新增或依赖的系统属性；没有则写“无”。

## 字符串国际化

TODO: 说明是否新增字符串资源；没有则写“无”。

## 可回滚性

TODO: 说明涉及的源码仓库、回滚顺序、风险点和验证建议。
""",
        encoding="utf-8",
    )
    return target_rel


from akbs_intake import validation as _validation  # noqa: E402


def validate_package(package_dir: Path) -> dict[str, Any]:
    return _validation.validate_package(
        package_dir,
        incoming_schema_version=INCOMING_SCHEMA_VERSION,
        validate_incoming_package_fn=validate_incoming_package,
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def materials_rel(*parts: str) -> str:
    clean = [part.strip("/") for part in parts if part]
    return "/".join([MATERIALS_DIR, *clean])


from akbs_intake.search_usage import (  # noqa: E402
    implementation_origins_require_pre_change_search,
    patch_search_feature_tokens,
    search_payload_has_member_decision,
    search_payload_missing_required_pre_change_search,
    search_payload_needs_closed_decision,
    search_usage_payload,
)


from akbs_intake import source_metadata as _source_metadata  # noqa: E402


def source_metadata(config: dict[str, str], skill: str) -> dict[str, Any]:
    return _source_metadata.source_metadata(
        config,
        skill,
        plugin_root=PLUGIN_ROOT,
        run_command=run,
        plugin_install_metadata_fn=plugin_install_metadata,
        plugin_version_gate_check_fn=lambda gate_config, fetch, require: plugin_version_gate_check(
            gate_config,
            fetch=fetch,
            require=require,
        ),
        last_plugin_version_gate=LAST_PLUGIN_VERSION_GATE,
    )


def write_package_source(package_dir: Path, config: dict[str, str], skill: str) -> dict[str, Any]:
    source = source_metadata(config, skill)
    write_json(package_dir / materials_rel("evidence", "source.json"), {"kind": "source", "payload": source})
    return source


def bind_framework_evidence(package_dir: Path, rel: str, case_id: str, variant_id: str) -> None:
    path = package_dir / rel
    if not path.is_file():
        return
    payload = read_json_file(path)
    payload["case_id"] = case_id
    payload["variant_id"] = variant_id
    if payload.get("kind") == "source":
        source_payload = payload.get("payload")
        if not isinstance(source_payload, dict):
            source_payload = {}
        payload["payload"] = source_payload
    write_json(path, payload)


def incoming_report_manifest(
    report_type: str,
    date: dt.date,
    week_key: str,
    config: dict[str, str],
    summary: str,
    source: dict[str, Any],
    run_id: str,
    project: str = "",
    project_evidence_path: str = "",
    display_path: str = "",
) -> dict[str, Any]:
    report_name = f"{report_type}.md"
    package_kind = "daily_trace" if report_type == "daily" else "weekly_trace"
    manifest: dict[str, Any] = {
        "schema": "knowledge-incoming-package",
        "schema_version": INCOMING_SCHEMA_VERSION,
        "package_kind": package_kind,
        "member_alias": config["member_alias"],
        "member_name": config["member_name"],
        "date": date.isoformat(),
        "run_id": run_id,
        "tool": "android-knowledge-intake",
        "report_type": report_type,
        "report_path": f"reports/{report_name}",
        "summary": summary,
        "files": {
            "evidence": [
                materials_rel("evidence", "source.json"),
                materials_rel("evidence", "codex_sessions.json"),
                materials_rel("evidence", "work_findings.json"),
            ],
            "display": [display_path or materials_rel("display", "report_view.json")],
        },
    }
    if report_type == "weekly":
        manifest["week_range"] = week_key
    if report_type == "daily" and project:
        manifest["project"] = project
    if project_evidence_path:
        manifest["files"]["evidence"].append(project_evidence_path)
    return manifest


from akbs_intake.reports.common import (  # noqa: E402
    ensure_report_date_allowed,
    ensure_report_not_duplicate,
    ensure_report_submit_allowed,
    format_report_duplicate_message,
    iter_local_manifests,
    local_report_packages,
    package_key_from_manifest,
    record_submitted_package,
    replacement_run_id,
    report_dates,
    report_duplicate_label,
    report_identity,
    report_identity_from_manifest,
    report_replace_option,
    report_type_from_manifest,
)
from akbs_intake.reports.render import (  # noqa: E402
    project_ledger_rows,
    write_report,
    write_report_view,
)
from akbs_intake.reports.validation import validate_report_trace_package  # noqa: E402


def reference_path(package_dir: Path, rel: str) -> Path:
    path = (package_dir / rel).resolve()
    root = package_dir.resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"引用路径越界: {rel}")
    return path


def read_referenced_json(package_dir: Path, rel: str) -> dict[str, Any] | None:
    try:
        path = reference_path(package_dir, rel)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def evidence_covers_patch(item: dict[str, Any], payload: dict[str, Any] | None, patch: dict[str, Any], patch_count: int) -> bool:
    if patch_count == 1:
        return True
    patch_id = str(patch.get("id") or "")
    patch_path = str(patch.get("path") or "")
    values = [item.get("patch_id"), item.get("patch"), item.get("source_patch")]
    if isinstance(payload, dict):
        values.extend([payload.get("patch_id"), payload.get("patch"), payload.get("source_patch"), payload.get("patch_path")])
    normalized = {str(value) for value in values if value}
    return bool((patch_id and patch_id in normalized) or (patch_path and patch_path in normalized))


def validate_incoming_package(package_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    def require_file(rel: Any, label: str) -> Path | None:
        if not isinstance(rel, str) or not rel:
            errors.append(f"{label} path 必须提供")
            return None
        try:
            path = reference_path(package_dir, rel)
        except ValueError as exc:
            errors.append(str(exc))
            return None
        if not path.is_file():
            errors.append(f"{label} 文件不存在: {rel}")
            return None
        return path

    def load_evidence(paths: list[Any]) -> dict[str, dict[str, Any]]:
        by_kind: dict[str, dict[str, Any]] = {}
        for rel in paths:
            path = require_file(rel, "evidence")
            if not path:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"{rel} 解析失败: {exc}")
                continue
            if not isinstance(payload, dict):
                errors.append(f"{rel} evidence 必须是对象")
                continue
            kind = payload.get("kind")
            if not kind:
                errors.append(f"{rel} evidence.kind 必须提供")
                continue
            by_kind[str(kind)] = payload
        return by_kind

    required = {
        "schema",
        "schema_version",
        "package_kind",
        "member_alias",
        "member_name",
        "date",
        "run_id",
        "tool",
        "summary",
    }
    for field in sorted(required - set(manifest)):
        errors.append(f"manifest 缺少必填字段: {field}")
    if manifest.get("schema") != "knowledge-incoming-package":
        errors.append("schema 必须是 knowledge-incoming-package")
    if manifest.get("schema_version") != INCOMING_SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {INCOMING_SCHEMA_VERSION}")
    if not DATE_DISPLAY_RE.fullmatch(str(manifest.get("date") or "")):
        errors.append("manifest.date 必须是 YYYY-MM-DD")
    if not RUN_ID_RE.fullmatch(str(manifest.get("run_id") or "")):
        errors.append("manifest.run_id 必须是 YYYYMMDD-HHMMSS 或 YYYYMMDD-HHMMSS-suffix")
    errors.extend(
        text_field_quality_errors(
            {
                "manifest.summary": manifest.get("summary"),
                "manifest.supplement_reason": manifest.get("supplement_reason"),
            }
        )
    )
    package_kind = manifest.get("package_kind")
    if package_kind not in INCOMING_KINDS:
        errors.append(f"package_kind 非法: {package_kind}")

    if package_kind in {"daily_trace", "weekly_trace"}:
        validate_report_trace_package(
            package_dir=package_dir,
            manifest=manifest,
            trace_required_evidence_kinds=TRACE_REQUIRED_EVIDENCE_KINDS,
            package_status_values=PACKAGE_STATUS_VALUES,
            require_file=require_file,
            load_evidence=load_evidence,
            read_referenced_json=read_referenced_json,
            errors=errors,
        )

    if package_kind == "framework_change":
        patch_context = validate_framework_change_manifest_and_files(
            package_dir=package_dir,
            manifest=manifest,
            package_status_values=PACKAGE_STATUS_VALUES,
            supplement_modes=SUPPLEMENT_MODES,
            run_id_re=RUN_ID_RE,
            require_file=require_file,
            validate_patch_readme=validate_patch_readme,
            has_uncontrolled_patch_asset_prefix=has_uncontrolled_patch_asset_prefix,
            is_valid_platform_value=is_valid_platform_value,
            is_valid_android_version_value=is_valid_android_version_value,
            errors=errors,
        )
        manifest_platform = patch_context.manifest_platform
        manifest_android_version = patch_context.manifest_android_version
        package_status = patch_context.package_status
        supplement_target = patch_context.supplement_target
        is_field_correction = patch_context.is_field_correction
        is_asset_correction = patch_context.is_asset_correction
        case_path = patch_context.case_path
        variant_path = patch_context.variant_path
        readme_path = patch_context.readme_path
        patch_paths = patch_context.patch_paths
        display_paths = patch_context.display_paths
        evidence_paths = patch_context.evidence_paths
        validate_patch_display_files(
            package_dir=package_dir,
            display_paths=display_paths,
            manifest=manifest,
            supplement_target=supplement_target,
            require_file=require_file,
            read_referenced_json=read_referenced_json,
            errors=errors,
        )
        structure_context = validate_framework_change_structure(
            package_dir=package_dir,
            manifest=manifest,
            package_status=package_status,
            is_field_correction=is_field_correction,
            supplement_target=supplement_target,
            case_path=case_path,
            variant_path=variant_path,
            evidence_paths=evidence_paths,
            load_evidence=load_evidence,
            read_json_file=read_json_file,
            read_referenced_json=read_referenced_json,
            text_field_quality_errors=text_field_quality_errors,
            is_valid_platform_value=is_valid_platform_value,
            is_valid_android_version_value=is_valid_android_version_value,
            legacy_patch_problem_kind=LEGACY_PATCH_PROBLEM_KIND,
            framework_required_evidence_kinds=FRAMEWORK_REQUIRED_EVIDENCE_KINDS,
            field_correction_required_evidence_kinds=FIELD_CORRECTION_REQUIRED_EVIDENCE_KINDS,
            field_correction_forbidden_evidence_kinds=FIELD_CORRECTION_FORBIDDEN_EVIDENCE_KINDS,
            field_correction_allowed_fields=FIELD_CORRECTION_ALLOWED_FIELDS,
            field_correction_forbidden_fields=FIELD_CORRECTION_FORBIDDEN_FIELDS,
            errors=errors,
        )
        case_problem = structure_context.case_problem
        case_solution = structure_context.case_solution
        evidence_by_kind = structure_context.evidence_by_kind
        ai_context = validate_patch_ai_facts_and_diff(
            evidence_by_kind=evidence_by_kind,
            is_field_correction=is_field_correction,
            evidence_payload=evidence_payload,
            list_string_values=list_string_values,
            unique_strings=unique_strings,
            errors=errors,
        )
        modified_files = ai_context.modified_files
        if not is_field_correction:
            validate_patch_template_leaks(
                package_dir=package_dir,
                manifest=manifest,
                evidence_paths=evidence_paths,
                case_problem=case_problem,
                case_solution=case_solution,
                patch_paths=patch_paths,
                modified_files=modified_files,
                read_referenced_json=read_referenced_json,
                template_leak_errors=template_leak_errors,
                errors=errors,
            )
            errors.extend(
                validate_framework_function_scope(
                    package_dir=package_dir,
                    manifest=manifest,
                    readme_path=readme_path,
                    patch_paths=patch_paths,
                    evidence_by_kind=evidence_by_kind,
                    list_string_values=list_string_values,
                    aggregate_package_scope_errors=aggregate_package_scope_errors,
                )
            )
        framework_change_summary = read_optional_json_object(package_dir / materials_rel("evidence", "framework_change_summary.json"))
        validate_patch_supplement_basics(
            manifest=manifest,
            evidence_by_kind=evidence_by_kind,
            supplement_target=supplement_target,
            is_field_correction=is_field_correction,
            is_asset_correction=is_asset_correction,
            manifest_platform=manifest_platform,
            manifest_android_version=manifest_android_version,
            framework_change_summary=framework_change_summary,
            supplement_target_relation_errors=supplement_target_relation_errors,
            patch_asset_correction_source_errors=patch_asset_correction_source_errors,
            split_company_project=split_company_project,
            errors=errors,
        )
        validate_patch_verification_result(
            evidence_by_kind=evidence_by_kind,
            package_status=package_status,
            is_field_correction=is_field_correction,
            errors=errors,
        )
        validate_patch_pre_change_search(
            manifest=manifest,
            evidence_by_kind=evidence_by_kind,
            package_status=package_status,
            is_field_correction=is_field_correction,
            list_string_values=list_string_values,
            implementation_origins_require_pre_change_search=implementation_origins_require_pre_change_search,
            search_payload_missing_required_pre_change_search=search_payload_missing_required_pre_change_search,
            search_payload_needs_closed_decision=search_payload_needs_closed_decision,
            errors=errors,
            warnings=warnings,
        )
        validate_patch_supplement_verification_closure(
            package_dir=package_dir,
            manifest=manifest,
            supplement_target=supplement_target,
            is_field_correction=is_field_correction,
            errors=errors,
        )
    return {"status": "FAIL" if errors else "PASS", "errors": errors, "warnings": warnings}


from akbs_intake.patch.facts import (  # noqa: E402
    has_usb_semantic_anchor,
    patch_facts_from_text,
    patch_modified_files,
    patch_modules_from_files,
    patch_problem_and_risk_payloads,
    patch_semantic_flags,
    patch_semantic_keywords,
    patch_semantic_problem_solution,
    patch_semantic_risk_areas,
    patch_symbols_from_text,
)
from akbs_intake.patch.validation import (  # noqa: E402
    validate_framework_change_manifest_and_files,
    validate_framework_change_structure,
    validate_framework_function_scope,
    validate_patch_display_files,
    validate_patch_ai_facts_and_diff,
    validate_patch_template_leaks,
    validate_patch_verification_result,
    validate_patch_pre_change_search,
    validate_patch_supplement_basics,
    validate_patch_supplement_verification_closure,
)


def existing_explanation_kinds_for_entry(package_dir: Path, evidence_entries: list[dict[str, Any]], entry: dict[str, Any], patch_count: int) -> set[str]:
    patch = {"id": Path(str(entry.get("path", ""))).stem, "path": entry.get("path", "")}
    kinds: set[str] = set()
    for item in evidence_entries:
        if item.get("kind") not in REQUIRED_PATCH_EXPLANATION_KINDS:
            continue
        rel = item.get("path")
        payload = read_referenced_json(package_dir, rel) if isinstance(rel, str) else None
        if evidence_covers_patch(item, payload, patch, patch_count):
            kinds.add(str(item.get("kind")))
    return kinds


def ensure_patch_analysis_evidence(package_dir: Path, patch_entries: list[dict[str, Any]], evidence_entries: list[dict[str, Any]], summary: str) -> None:
    evidence_dir = package_dir / MATERIALS_DIR / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    patch_count = len(patch_entries)
    for entry in patch_entries:
        rel = str(entry.get("path") or "")
        if not rel:
            continue
        patch_path = package_dir / rel
        if not patch_path.is_file():
            continue
        text = patch_path.read_text(encoding="utf-8", errors="ignore")
        facts = patch_facts_from_text(text)
        captured_facts = entry.get("facts") if isinstance(entry.get("facts"), dict) else {}
        merged_facts = {**facts, **{key: value for key, value in captured_facts.items() if value}}
        entry["facts"] = merged_facts

        existing = existing_explanation_kinds_for_entry(package_dir, evidence_entries, entry, patch_count)
        patch_id = Path(rel).stem
        safe_patch_id = safe_id(patch_id)
        source_patch = rel

        diff_facts_payload = {
            "kind": "patch_diff_facts",
            "patch_id": patch_id,
            "source_patch": source_patch,
            "content_sha1": merged_facts.get("content_sha1") or sha1_file(patch_path),
            "modified_files": merged_facts.get("modified_files", []),
            "modules": merged_facts.get("modules", []),
            "symbols": merged_facts.get("symbols", []),
            "system_properties": merged_facts.get("system_properties", []),
            "settings_keys": merged_facts.get("settings_keys", []),
            "resource_keys": merged_facts.get("resource_keys", []),
            "framework_log_keys": merged_facts.get("framework_log_keys", []),
        }
        diff_facts_path = evidence_dir / f"{safe_patch_id}-patch-diff-facts.json"
        if not diff_facts_path.exists():
            write_json(diff_facts_path, diff_facts_payload)
            evidence_entries.append(
                {
                    "id": f"{safe_patch_id}-patch-diff-facts",
                    "kind": "patch_diff_facts",
                    "patch_id": patch_id,
                    "path": materials_rel("evidence", diff_facts_path.name),
                    "result": "INFO",
                    "summary": "patch facts from member-side package generation",
                }
            )

        problem_payload, risk_payload = patch_problem_and_risk_payloads(patch_id, source_patch, summary, merged_facts)
        if "patch_problem_summary" not in existing:
            problem_path = evidence_dir / f"{safe_patch_id}-patch-problem.json"
            write_json(problem_path, problem_payload)
            evidence_entries.append(
                {
                    "id": f"{safe_patch_id}-patch-problem",
                    "kind": "patch_problem_summary",
                    "patch_id": patch_id,
                    "path": materials_rel("evidence", problem_path.name),
                    "result": "INFO",
                    "summary": "member-side patch problem explanation",
                }
            )
        if "risk_surface" not in existing:
            risk_path = evidence_dir / f"{safe_patch_id}-risk-surface.json"
            write_json(risk_path, risk_payload)
            evidence_entries.append(
                {
                    "id": f"{safe_patch_id}-risk-surface",
                    "kind": "risk_surface",
                    "patch_id": patch_id,
                    "path": materials_rel("evidence", risk_path.name),
                    "result": "INFO",
                    "summary": "member-side patch risk surface",
                }
            )


def incoming_patch_item(package_dir: Path, patch_entry: dict[str, Any]) -> dict[str, Any]:
    patch_path = package_dir / str(patch_entry["path"])
    captured_facts = patch_entry.get("facts") if isinstance(patch_entry.get("facts"), dict) else {}
    content_sha1 = str(patch_entry.get("content_sha1") or sha1_file(patch_path))
    repo_path = str(patch_entry.get("repo_path") or captured_facts.get("repo_path") or "").strip("/")
    implementation_origin = str(patch_entry.get("implementation_origin") or captured_facts.get("implementation_origin") or "unknown")
    captured_by = str(patch_entry.get("captured_by") or captured_facts.get("captured_by") or "")
    coding_standard_check = patch_entry.get("coding_standard_check") if isinstance(patch_entry.get("coding_standard_check"), dict) else {}
    modified_files = captured_facts.get("modified_files") or patch_modified_files(patch_path)
    if repo_path:
        prefix = repo_path + "/"
        modified_files = [path if str(path).startswith(prefix) else prefix + str(path) for path in list_string_values(modified_files)]
    facts = {
        "content_sha1": content_sha1,
        "repo_path": repo_path,
        "platform_token": str(patch_entry.get("platform_token") or ""),
        "platform": str(patch_entry.get("platform") or ""),
        "android_version": str(patch_entry.get("android_version") or ""),
        "implementation_origin": implementation_origin,
        "captured_by": captured_by,
        "modified_files": modified_files,
        "modules": captured_facts.get("modules") or [],
        "symbols": captured_facts.get("symbols") or [],
        "system_properties": captured_facts.get("system_properties") or [],
        "settings_keys": captured_facts.get("settings_keys") or [],
        "resource_keys": captured_facts.get("resource_keys") or [],
        "framework_log_keys": captured_facts.get("framework_log_keys") or [],
    }
    reuse_hint = patch_entry.get("reuse_hint", False)
    return {
        "id": Path(str(patch_entry["path"])).stem,
        "path": patch_entry["path"],
        "readme": patch_entry.get("readme", ""),
        "content_sha1": content_sha1,
        "status": patch_entry.get("status", "candidate"),
        "reuse_hint": reuse_hint if isinstance(reuse_hint, bool) else reuse_hint,
        "note": str(patch_entry.get("note") or ""),
        "repo_path": repo_path,
        "implementation_origin": implementation_origin,
        "captured_by": captured_by,
        "coding_standard_check": coding_standard_check,
        "artifact": "",
        "facts": facts,
    }


def aggregate_patch_diff_facts(patch_items: list[dict[str, Any]]) -> dict[str, Any]:
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
    implementation_origins: list[str] = []
    capture_tools: list[str] = []
    for item in patch_items:
        facts = item.get("facts", {}) if isinstance(item.get("facts"), dict) else {}
        content_sha1 = str(item.get("content_sha1") or facts.get("content_sha1") or "")
        if content_sha1:
            content_hashes.append(content_sha1)
        implementation_origin = str(item.get("implementation_origin") or facts.get("implementation_origin") or "").strip()
        captured_by = str(item.get("captured_by") or facts.get("captured_by") or "").strip()
        if implementation_origin:
            implementation_origins.append(implementation_origin)
        if captured_by:
            capture_tools.append(captured_by)
        for key in aggregate:
            aggregate[key].extend(list_string_values(facts.get(key)))
        patches.append(
            {
                "id": item.get("id", ""),
                "path": item.get("path", ""),
                "repo_path": item.get("repo_path", ""),
                "content_sha1": content_sha1,
                "status": item.get("status", "candidate"),
                "reuse_hint": bool(item.get("reuse_hint")),
                "note": str(item.get("note") or ""),
                "implementation_origin": implementation_origin,
                "captured_by": captured_by,
                "modified_files": list_string_values(facts.get("modified_files")),
                "modules": list_string_values(facts.get("modules")),
            }
        )
    payload: dict[str, Any] = {
        "patch_count": len(patch_items),
        "patches": patches,
        "content_sha1": content_hashes[0] if len(content_hashes) == 1 else "",
        "implementation_origins": unique_strings(implementation_origins),
        "capture_tools": unique_strings(capture_tools),
    }
    payload.update({key: unique_strings(values) for key, values in aggregate.items()})
    return payload


def concrete_module_from_files(modified_files: list[str], repo_paths: list[str]) -> str:
    for path in modified_files:
        parts = [part for part in Path(path).parts if part not in {"", "."}]
        if len(parts) >= 4:
            return "/".join(parts[:4])
        if len(parts) >= 2:
            return "/".join(parts[:2])
    for repo_path in repo_paths:
        if repo_path:
            return repo_path
    return "unknown"


def feature_domain_from_text(summary: str, problem: str, modified_files: list[str]) -> str:
    text = " ".join([summary, problem, *modified_files]).lower()
    domains = [
        ("lockscreen", "锁屏"),
        ("launcher", "Launcher"),
        ("settings", "Settings"),
        ("systemui", "SystemUI"),
        ("display", "显示策略"),
        ("navigation", "导航策略"),
        ("audio", "音频策略"),
        ("camera", "相机"),
        ("usb", "USB 权限"),
        ("hdmi", "HDMI"),
        ("permission", "权限"),
    ]
    for token, label in domains:
        if token in text or label.lower() in text:
            return label
    if modified_files:
        stem = Path(modified_files[0]).stem
        return stem or "Framework 功能"
    return "Framework 功能"


def search_decision_value(search_payload: dict[str, Any]) -> str:
    payload = search_payload.get("payload", search_payload) if isinstance(search_payload, dict) else {}
    if not isinstance(payload, dict):
        return "unknown"
    decision = str(payload.get("reuse_decision") or payload.get("decision") or "").strip()
    if decision in {"reuse", "adapt", "reference_only", "not_found", "not_applicable", "unknown"}:
        return decision
    if payload.get("searched") is False:
        return "unknown"
    return "unknown"


def search_match_class_payload(search_payload: dict[str, Any]) -> dict[str, Any]:
    decision = search_decision_value(search_payload)
    if decision == "reuse":
        merge_hint = "candidate_only"
        explanation = "成员声明直接复用已有知识，但仍必须通过模块、细分领域、代码锚点、补丁行为和验证目标硬门禁。"
    elif decision in {"adapt", "reference_only"}:
        merge_hint = "reference_only"
        explanation = f"{decision} 只能作为参考证据，不能直接触发合并。"
    elif decision == "not_found":
        merge_hint = "not_found"
        explanation = "成员搜索未命中可复用知识，管理端仍需执行沉淀前重叠检索。"
    elif decision == "not_applicable":
        merge_hint = "not_applicable"
        explanation = "成员判断搜索结果不适用，不能触发合并。"
    else:
        merge_hint = "insufficient_evidence"
        explanation = "搜索使用决策缺失或未知，不能让管理端用标题猜合并。"
    payload = search_payload.get("payload", search_payload) if isinstance(search_payload, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "decision": decision,
        "merge_hint": merge_hint,
        "targets": list_string_values(payload.get("targets")),
        "queries": list_string_values(payload.get("queries")),
        "explanation": explanation,
    }


def patch_view_payload(
    manifest_like: dict[str, Any],
    *,
    case_problem: str,
    case_solution: str,
    verification_payload: dict[str, Any],
    risk_payload: dict[str, Any],
    patch_rel_paths: list[str],
    supplement_for_package_key: str,
    supplement_reason: str,
    supplement_mode: str = "",
    corrected_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = str(manifest_like.get("summary") or "").strip() or "Framework 补丁包"
    material_kind_label = "字段补证包" if supplement_mode == "field_correction" else ("补证包" if supplement_for_package_key else "原始包")
    material_identity_mode = "inherit_target_package" if supplement_for_package_key else "self"
    result_summary = str(verification_payload.get("summary") or verification_payload.get("result") or "验证结果未提供")
    if supplement_mode == "field_correction":
        result_summary = "字段级补证，不包含补丁 diff、验证结论或代码证据。"
    risks = list_string_values(risk_payload.get("risk_areas")) or list_string_values(risk_payload.get("limits"))
    risk_or_gap = "；".join(risks[:2]) if risks else "暂无明确遗留风险"
    if supplement_for_package_key:
        risk_or_gap = f"补证目标：{supplement_for_package_key}；{supplement_reason or risk_or_gap}"
    corrected_items = [f"{key}: {value}" for key, value in sorted((corrected_fields or {}).items())]
    detail_sections = [
        {"title": "问题", "items": [case_problem or summary]},
        {"title": "修改内容", "items": [case_solution or summary, *patch_rel_paths]},
        {"title": "验证结果", "items": [result_summary]},
        {"title": "遗留风险", "items": risks or ["暂无明确遗留风险"]},
        {"title": "下一步", "items": ["按管理端入库校验和沉淀判断继续处理。"]},
    ]
    if supplement_mode == "field_correction":
        detail_sections[1] = {
            "title": "字段修正",
            "items": corrected_items or ["未列出字段修正内容。"],
        }
    if supplement_for_package_key:
        detail_sections.insert(
            1,
            {
                "title": "补证关系",
                "items": [f"补证包补充原始包：{supplement_for_package_key}", supplement_reason or "补充原始包证据。"],
            },
        )
    return {
        "kind": "patch_view",
        "payload": {
            "material_kind_label": material_kind_label,
            "material_identity_mode": material_identity_mode,
            "material_identity_target_package_key": supplement_for_package_key,
            "display_title": compact_text(summary, 80),
            "problem_summary": case_problem or summary,
            "solution_summary": case_solution or summary,
            "result_summary": result_summary,
            "project": manifest_like.get("project", "unknown"),
            "platform": manifest_like.get("platform", "unknown"),
            "android_version": manifest_like.get("android_version", "unknown"),
            "member_alias": manifest_like.get("member_alias", ""),
            "member_name": manifest_like.get("member_name", ""),
            "supplement_for_package_key": supplement_for_package_key,
            "ui_card": {
                "title": compact_text(summary, 48),
                "subtitle": f"{manifest_like.get('project', 'unknown')} / {manifest_like.get('platform', 'unknown')} / Android {manifest_like.get('android_version', 'unknown')}",
                "summary": compact_text(case_problem or summary, 120),
                "risk_or_gap": compact_text(risk_or_gap, 160),
            },
            "detail_sections": detail_sections,
        },
    }


def patch_ai_facts_payload(
    *,
    manifest_like: dict[str, Any],
    patch_diff_payload: dict[str, Any],
    search_payload: dict[str, Any],
    verification_payload: dict[str, Any],
    case_problem: str,
    case_solution: str,
    plugin_version: str,
) -> dict[str, Any]:
    modified_files = list_string_values(patch_diff_payload.get("modified_files"))
    repo_paths = unique_strings(str(item.get("repo_path") or "").strip("/") for item in patch_diff_payload.get("patches", []) if isinstance(item, dict))
    module = concrete_module_from_files(modified_files, repo_paths)
    feature_domain = feature_domain_from_text(str(manifest_like.get("summary") or ""), case_problem, modified_files)
    code_anchors = {
        "files": modified_files,
        "symbols": list_string_values(patch_diff_payload.get("symbols")),
        "resource_keys": list_string_values(patch_diff_payload.get("resource_keys")),
        "settings_keys": list_string_values(patch_diff_payload.get("settings_keys")),
        "system_properties": list_string_values(patch_diff_payload.get("system_properties")),
        "framework_log_keys": list_string_values(patch_diff_payload.get("framework_log_keys")),
    }
    patch_assets = [
        {
            "path": item.get("path", ""),
            "content_sha1": item.get("content_sha1", ""),
            "repo_path": item.get("repo_path", ""),
            "modified_files": list_string_values(item.get("modified_files")),
        }
        for item in patch_diff_payload.get("patches", [])
        if isinstance(item, dict)
    ]
    search_class = search_match_class_payload(search_payload)
    verification_targets = {
        "result": verification_payload.get("result", "MISSING"),
        "method": verification_payload.get("method", "not_provided"),
        "summary": verification_payload.get("summary", ""),
    }
    return {
        "module": module,
        "feature_domain": feature_domain,
        "patch_behavior_goal": case_problem or str(manifest_like.get("summary") or ""),
        "solution_summary": case_solution,
        "code_anchors": code_anchors,
        "patch_assets": patch_assets,
        "verification_targets": verification_targets,
        "search_usage": search_payload.get("payload", search_payload),
        "search_match_class": search_class,
        "merge_gate_inputs": {
            "module": module,
            "feature_domain": feature_domain,
            "code_anchors": code_anchors,
            "patch_behavior_goal": case_problem or str(manifest_like.get("summary") or ""),
            "verification_targets": verification_targets,
            "project": manifest_like.get("project", "unknown"),
            "platform": manifest_like.get("platform", "unknown"),
            "android_version": manifest_like.get("android_version", "unknown"),
            "search_match_class": search_class,
        },
        "protocol_version": "patch-human-ai-evidence-v1",
        "plugin_version": plugin_version,
    }


def work_findings_payload(sessions: list[SessionWork], patches: list[PatchInfo]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    blocked_or_failed: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for session in sessions:
        item = work_finding_for_session(session)
        title = str(item.get("title", ""))
        if title and title not in seen_titles:
            seen_titles.add(title)
            items.append(item)
        if item.get("work_status") == "blocked":
            blocked_or_failed.append(
                {
                    "title": title,
                    "work_status": "blocked",
                    "basis": item.get("basis", []),
                }
            )
    for patch in patches:
        title = patch.name
        if title in seen_titles:
            continue
        seen_titles.add(title)
        items.append(
            {
                "title": title,
                "kind": "possible_framework_change",
                "work_status": "candidate",
                "basis": [f"发现 patch 文件: {patch.name}", f"项目线索: {patch.project}"],
                "missing_evidence": ["需要 patch-capture 补齐 case/variant/风险/验证证据"],
                "recommended_action": "满足验证条件后升级为 framework_change",
            }
        )
    return {
        "scanned_sources": ["codex_sessions", "git_activity", "patch_files", "build_or_verification_records"],
        "items": items,
        "blocked_or_failed": blocked_or_failed,
    }


def prepare_package(
    report_type: str,
    date: dt.date,
    config: dict[str, str],
    run_id: str | None = None,
    schema_version: str = INCOMING_SCHEMA_VERSION,
    replace_report_run_id: str = "",
) -> Path:
    require_config(config)
    if schema_version != INCOMING_SCHEMA_VERSION:
        raise SystemExit(f"incoming 只支持 schema_version={INCOMING_SCHEMA_VERSION}")
    dates, start, end, week_key = report_dates(report_type, date)
    ensure_report_date_allowed(report_type, date, config)
    run_id = run_id or f"{ymd(date)}-{local_now(config):%H%M%S}"
    out_dir = require_safe_artifact_path(expanded_path(config["out_dir"]), purpose="out_dir")
    package_dir = require_safe_artifact_path(out_dir / "pending" / ymd(date) / config["member_alias"] / run_id, purpose="incoming package output")
    if package_dir.exists():
        raise SystemExit(f"工作包已存在: {package_dir}")
    report_duplicates: list[dict[str, str]] = []
    replace_report_run_id = str(replace_report_run_id or "").strip()
    if report_type in {"daily", "weekly"}:
        report_duplicates = ensure_report_not_duplicate(
            config,
            report_type,
            report_identity(report_type, date, week_key),
            run_id,
            replace_report_run_id,
        )
    package_dir.mkdir(parents=True)

    if synthetic_mode(config):
        sessions = synthetic_sessions(config, dates)
        patches = []
    else:
        sessions = parse_sessions(config, dates)
        patches = discover_patches(config, sessions, start, end)
    items = items_by_project(sessions, patches)
    summary = overview_text(report_type, items, patches)
    report_project, project_payload = infer_report_project(report_type, summary, items, sessions, patches)
    project_customers = {
        str(item.get("project")): str(item.get("customer_name"))
        for item in project_payload.get("project_customers", [])
        if isinstance(item, dict) and item.get("project") and item.get("customer_name")
    }
    write_report(package_dir, report_type, date, week_key, config, items, patches, project_customers)
    project_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "project_inference.json"),
        {
            "kind": "project_inference",
            "payload": project_payload,
        },
    )

    evidence = {
        "source": "android-knowledge-intake",
        "synthetic_data": synthetic_mode(config),
        "session_count": len(sessions),
        "patch_count": len(patches),
        "date_range": [start.isoformat(), end.isoformat()],
        "sessions": [
            {
                "id": item.session_id,
                "thread_name": item.thread_name,
                "cwd": item.cwd,
                "project": item.project,
                "message_count": len(item.messages),
            }
            for item in sessions
        ],
    }
    write_json(package_dir / materials_rel("evidence", "codex_sessions.json"), {"kind": "codex_sessions", "payload": evidence})
    write_json(package_dir / materials_rel("evidence", "work_findings.json"), {"kind": "work_findings", "payload": work_findings_payload(sessions, patches)})
    search_path = ""
    if report_type == "daily":
        member_search_payload = search_usage_payload(config, date)
        if member_search_payload:
            search_path = materials_rel("evidence", "search_before_change.json")
            write_json(package_dir / search_path, {"kind": "search_before_change", "payload": member_search_payload})
    reports_dir = package_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(package_dir / f"{report_type}.md"), reports_dir / f"{report_type}.md")
    source = write_package_source(package_dir, config, "android-knowledge-intake")
    display_path = write_report_view(package_dir, report_type, date, week_key, config, items, patches, summary, project_customers)
    manifest = incoming_report_manifest(
        report_type,
        date,
        week_key,
        config,
        summary,
        source,
        run_id,
        report_project,
        project_path,
        display_path,
    )
    if report_type in {"daily", "weekly"} and replace_report_run_id:
        replacement = next((item for item in report_duplicates if item["run_id"] == replace_report_run_id), {})
        manifest["replacement_for_run_id"] = replace_report_run_id
        manifest["supersedes"] = {
            "report_type": report_type,
            "run_id": replace_report_run_id,
            "date": date.isoformat(),
            "week_range": week_key if report_type == "weekly" else "",
            "identity": report_identity(report_type, date, week_key),
            "package_key": replacement.get("package_key", ""),
        }
    if search_path:
        manifest["files"]["evidence"].append(search_path)
    write_json(package_dir / "manifest.json", manifest)
    check = validate_package(package_dir)
    write_json(package_dir / "local-check.json", check)
    return package_dir


def evidence_text_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            values.extend(evidence_text_values(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(evidence_text_values(item))
    elif isinstance(value, str) and value.strip():
        values.append(value)
    return values


def infer_platform_metadata(
    patch_entries: list[dict[str, Any]],
    evidence_entries: list[dict[str, Any]] | None = None,
    package_dir: Path | None = None,
) -> tuple[str, str]:
    platform, android_version = parse_platform_token(patch_entries)
    evidence_tokens: list[tuple[str, str]] = []
    for entry in evidence_entries or []:
        payload: Any = entry.get("payload") if isinstance(entry, dict) else None
        if package_dir and isinstance(entry, dict) and not payload:
            rel = entry.get("path")
            if isinstance(rel, str) and rel:
                payload = read_json_file(package_dir / rel)
        for value in evidence_text_values(payload):
            evidence_tokens.extend(find_platform_tokens(value))
    unique_evidence_tokens = sorted(set(evidence_tokens))
    if len(unique_evidence_tokens) == 1:
        evidence_platform, evidence_android_version = unique_evidence_tokens[0]
        if platform in {"", "unknown"}:
            platform = evidence_platform
        if android_version in {"", "unknown"}:
            android_version = evidence_android_version
    return platform or "unknown", android_version or "unknown"


def repo_paths_from_files(files: list[str]) -> list[str]:
    repos: list[str] = []
    for path in files:
        parts = path.split("/")
        if path.startswith(("services/", "core/", "data/etc/")):
            repos.append("frameworks/base")
        elif len(parts) >= 2:
            repos.append("/".join(parts[:2]))
    return sorted(dict.fromkeys(repos)) or ["unknown"]


def first_evidence_path(entries: list[dict[str, Any]], kind: str) -> str:
    for entry in entries:
        if entry.get("kind") == kind and isinstance(entry.get("path"), str):
            return str(entry["path"])
    return ""


def first_evidence_payload(package_dir: Path, entries: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    rel = first_evidence_path(entries, kind)
    if not rel:
        return {}
    return read_json_file(package_dir / rel)


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


def source_access_registry_clues(source_paths: list[str]) -> list[tuple[str, str]]:
    registry_dir = Path.home() / ".servers" / "projects"
    if not registry_dir.is_dir():
        return []
    source_paths = [path for path in source_paths if path]
    if not source_paths:
        return []
    clues: list[tuple[str, str]] = []
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
            if not any(path_strings_overlap(source_path, project_path) for source_path in source_paths):
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


def source_context_clues(source_contexts: list[dict[str, Any]]) -> list[tuple[str, str]]:
    clues: list[tuple[str, str]] = []
    registry_paths: list[str] = []
    fields = (
        ("source_root", "capture source_root"),
        ("repo_path", "capture repo_path"),
        ("local_mount_path", "capture local_mount_path"),
        ("git_branch", "capture git branch"),
        ("git_remote", "capture git remote"),
        ("git_remotes", "capture git remotes"),
        ("remote_root", "capture remote_root"),
        ("ssh_host", "capture ssh_host"),
        ("sdk_name", "capture sdk_name"),
    )
    for context in source_contexts:
        for key, label in fields:
            value = context.get(key)
            if isinstance(value, str) and value.strip():
                clues.append((label, value))
                if key in {"source_root", "local_mount_path", "remote_root"}:
                    registry_paths.append(value)
    clues.extend(source_access_registry_clues(registry_paths))
    return clues


def related_report_project_clues(
    config: dict[str, str],
    run_ids: list[str],
    *,
    daily_label_prefix: str = "关联日报",
    weekly_label_prefix: str = "关联周报",
) -> list[tuple[str, str]]:
    out_dir = expanded_path(config.get("out_dir", ""))
    member_alias = config.get("member_alias", "")
    clues: list[tuple[str, str]] = []
    for run_id in unique_strings(run_ids):
        if not run_id:
            continue
        manifests_by_path: dict[Path, Path] = {}
        for bucket in ("pending", "submitted"):
            patterns = [f"*/*/{run_id}/manifest.json"]
            if member_alias:
                patterns.insert(0, f"*/{member_alias}/{run_id}/manifest.json")
            for pattern in patterns:
                for manifest_path in sorted((out_dir / bucket).glob(pattern)):
                    manifests_by_path[manifest_path] = manifest_path
        for manifest_path in manifests_by_path:
            package_dir = manifest_path.parent
            manifest = read_json_file(manifest_path)
            if manifest.get("package_kind") not in {"daily_trace", "weekly_trace"}:
                continue
            label_prefix = daily_label_prefix if manifest.get("package_kind") == "daily_trace" else weekly_label_prefix
            project = str(manifest.get("project") or "").strip()
            if project:
                clues.append((f"{label_prefix} project", project))
            projects = manifest.get("projects")
            if isinstance(projects, list):
                for item in projects:
                    if isinstance(item, str) and item.strip():
                        clues.append((f"{label_prefix} projects", item))
            summary = str(manifest.get("summary") or "").strip()
            if summary:
                clues.append((f"{label_prefix} summary", summary))
            report_path = manifest.get("report_path")
            if isinstance(report_path, str) and report_path:
                report_text = read_text_sample(package_dir / report_path)
                if report_text:
                    clues.append((f"{label_prefix}正文", report_text))
            files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
            evidence_paths = files.get("evidence", []) if isinstance(files, dict) else []
            if isinstance(evidence_paths, list):
                for rel in evidence_paths:
                    if not isinstance(rel, str) or Path(rel).name != "project_inference.json":
                        continue
                    evidence = read_json_file(package_dir / rel)
                    payload = evidence.get("payload") if isinstance(evidence.get("payload"), dict) else {}
                    for value in [payload.get("project"), *(payload.get("basis") or []), *(payload.get("raw_inputs") or [])]:
                        if isinstance(value, str) and value.strip():
                            clues.append((f"{label_prefix} project_inference", value))
    return clues


def same_day_daily_report_run_ids(config: dict[str, str], date: dt.date) -> list[str]:
    out_dir = expanded_path(config.get("out_dir", ""))
    member_alias = config.get("member_alias", "")
    run_ids: list[str] = []
    for bucket in ("submitted", "pending"):
        daily_root = out_dir / bucket / ymd(date) / member_alias
        for manifest_path in sorted(daily_root.glob("*/manifest.json")):
            manifest = read_json_file(manifest_path)
            if manifest.get("package_kind") != "daily_trace":
                continue
            if str(manifest.get("date") or "") != date.isoformat():
                continue
            run_id = str(manifest.get("run_id") or manifest_path.parent.name)
            if run_id:
                run_ids.append(run_id)
    run_ids = unique_strings(run_ids)
    if not run_ids:
        return []

    clues = related_report_project_clues(config, run_ids, daily_label_prefix="自动关联同日日报")
    projects = sorted(dict.fromkeys(project for _, text in clues for project in find_company_projects(text)))
    return run_ids if len(projects) == 1 else []


def read_text_sample(path: Path, limit: int = 12000) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def project_inference_payload(
    project: str,
    basis: list[str],
    checked_sources: list[str],
    raw_inputs: list[str],
    limits: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "project": project,
        "recognized": project != "unknown",
        "basis": basis,
        "checked_sources": checked_sources,
        "raw_inputs": raw_inputs[:20],
        "limits": limits or [],
        "company_rule_match": False,
    }
    if project != "unknown":
        payload.update(parse_company_project(project))
    return payload


def infer_project(
    explicit_project: str,
    patch_entries: list[dict[str, Any]],
    patch_sources: list[dict[str, Any]],
    summary: str,
    package_dir: Path | None = None,
    source_contexts: list[dict[str, Any]] | None = None,
    related_report_clues: list[tuple[str, str]] | None = None,
    trusted_platform: str = "",
) -> tuple[str, dict[str, Any]]:
    explicit_clues: list[tuple[str, str]] = []
    if explicit_project and explicit_project.strip() != "unknown":
        explicit_clues.append(("命令参数 project", explicit_project.strip()))

    capture_project_clues: list[tuple[str, str]] = []
    for item in patch_entries:
        for key, label in (("project", "capture package project"),):
            value = item.get(key)
            if isinstance(value, str) and value:
                capture_project_clues.append((label, value))

    context_clues = source_context_clues(source_contexts or [])

    patch_clues: list[tuple[str, str]] = []
    for item in patch_entries:
        for key, label in (("path", "补丁路径"), ("readme", "补丁说明路径")):
            value = item.get(key)
            if isinstance(value, str) and value:
                patch_clues.append((label, value))
            if package_dir and key in {"path", "readme"} and isinstance(value, str) and value:
                source = package_dir / value
                if key == "readme" and not patch_readme_usable_for_inference(source):
                    continue
                sample = read_text_sample(source)
                if sample:
                    patch_clues.append((label.replace("路径", "内容"), sample))
    for item in patch_sources:
        for key, label in (("project", "补丁来源 project"), ("name", "补丁名称"), ("source", "补丁来源路径")):
            value = item.get(key)
            if isinstance(value, str) and value:
                if key == "project":
                    capture_project_clues.append((label, value))
                else:
                    patch_clues.append((label, value))
    if summary:
        patch_clues.append(("补丁摘要", summary))

    groups = [
        ("explicit", explicit_clues),
        ("capture_package_project", capture_project_clues),
        ("source_context", context_clues),
        ("patch_context", patch_clues),
        ("related_report", related_report_clues or []),
    ]
    clues = [(label, value) for _, values in groups for label, value in values if str(value).strip()]
    checked_sources = sorted(dict.fromkeys(label for label, _ in clues))
    raw_inputs = [f"{label}: {value}" for label, value in clues]
    matched: list[tuple[str, str, str]] = []
    for _, values in groups:
        for label, value in values:
            matched.extend((candidate, label, value) for candidate in find_company_projects(value, platform=trusted_platform))
    unique_projects = sorted(dict.fromkeys(project for project, _, _ in matched))
    if len(unique_projects) == 1:
        project = unique_projects[0]
        basis = [f"{label}: {value}" for matched_project, label, value in matched if matched_project == project]
        if trusted_platform and not any(project in str(value).upper() for matched_project, _, value in matched if matched_project == project):
            if project.startswith("TVI"):
                basis.append(f"可信平台证据 platform={trusted_platform} 用于按 TVI 芯片字段补齐，候选规范项目 {project}")
            else:
                basis.append(f"可信平台证据 platform={trusted_platform} 用于补齐缺失项目平台位，候选规范项目 {project}")
        return project, project_inference_payload(project, basis[:5], checked_sources, raw_inputs)
    if len(unique_projects) > 1:
        limits = [f"识别到多个项目型号: {', '.join(unique_projects)}，不能写成单一项目"]
        if explicit_project and explicit_project.strip() not in {"", "unknown"}:
            limits.append("命令参数 project 与其他项目线索不一致，未作为项目名写入上传包")
        payload = project_inference_payload("unknown", [], checked_sources, raw_inputs, limits)
        payload["candidates"] = unique_projects
        return "unknown", payload

    limits = ["未从命令参数、capture package、source_root/git/registry、补丁内容或关联报告中识别到 TVD/TVE/TVA/TVI 项目型号"]
    if explicit_project and explicit_project.strip() not in {"", "unknown"}:
        limits.append("命令参数 project 未匹配公司项目型号规范，未作为项目名写入上传包")
    weak_capture_projects = [
        value
        for label, value in capture_project_clues
        if value.strip() and value.strip() != "unknown" and not find_company_project(value, platform=trusted_platform)
    ]
    if weak_capture_projects:
        limits.append("capture package project 未匹配公司项目型号规范，未作为项目名写入上传包")
    return "unknown", project_inference_payload("unknown", [], checked_sources, raw_inputs, limits)


def infer_report_project(
    report_type: str,
    summary: str,
    items: dict[str, list[tuple[str, str]]],
    sessions: list[SessionWork],
    patches: list[PatchInfo],
) -> tuple[str, dict[str, Any]]:
    label_prefix = "日报上下文" if report_type == "daily" else "周报上下文"
    clues: list[tuple[str, str]] = []
    if summary:
        clues.append((f"{label_prefix} summary", summary))
    for project, entries in sorted(items.items()):
        if project:
            clues.append((f"{label_prefix} 项目分组", project))
        for title, progress in entries:
            if title:
                clues.append((f"{label_prefix} 工作项", title))
            if progress:
                clues.append((f"{label_prefix} 进展", progress))
    for session in sessions:
        for label, value in (
            ("session project", session.project),
            ("session cwd", session.cwd),
            ("session thread", session.thread_name),
        ):
            if value:
                clues.append((f"{label_prefix} {label}", value))
        for message in session.messages:
            if message:
                clues.append((f"{label_prefix} session message", message))
    for patch in patches:
        for label, value in (("patch project", patch.project), ("patch name", patch.name), ("patch path", str(patch.path))):
            if value:
                clues.append((f"{label_prefix} {label}", value))

    checked_sources = sorted(dict.fromkeys(label for label, value in clues if str(value).strip()))
    raw_inputs = [f"{label}: {value}" for label, value in clues if str(value).strip()]
    project_customers, customer_basis = report_project_customers_from_clues(clues)

    def attach_customers(payload: dict[str, Any]) -> dict[str, Any]:
        payload["project_customers"] = [
            {"project": project, "customer_name": customer}
            for project, customer in sorted(project_customers.items())
        ]
        payload["customer_basis"] = {
            project: basis[:5]
            for project, basis in sorted(customer_basis.items())
        }
        project = str(payload.get("project") or "")
        if project and project not in REPORT_MISSING_PROJECT_VALUES:
            payload["customer_name"] = project_customers.get(project, MISSING_REPORT_CUSTOMER)
        return payload

    matched: list[tuple[str, str, str]] = []
    for label, value in clues:
        project = find_company_project(str(value))
        if project:
            matched.append((project, label, str(value)))

    unique_projects = sorted(dict.fromkeys(project for project, _, _ in matched))
    if len(unique_projects) == 1:
        project, label, value = matched[0]
        return project, attach_customers(project_inference_payload(project, [f"{label}: {value}"], checked_sources, raw_inputs))
    if len(unique_projects) > 1:
        base_models = sorted(dict.fromkeys(parse_company_project(project).get("base_model", "") for project in unique_projects))
        if len(base_models) == 1:
            base_project = base_models[0]
            payload = attach_customers(project_inference_payload(
                base_project,
                [f"{label_prefix}候选项目: {', '.join(unique_projects)}"],
                checked_sources,
                raw_inputs,
                [f"多个候选共享基础项目 {base_project}，日报写入基础项目并保留完整候选证据"],
            ))
            payload["candidates"] = unique_projects
            return base_project, payload
        payload = attach_customers(project_inference_payload(
            "unknown",
            [],
            checked_sources,
            raw_inputs,
            [f"{label_prefix}包含多个项目型号: {', '.join(unique_projects)}，不能写成单一项目"],
        ))
        payload["candidates"] = unique_projects
        return "unknown", payload
    return "unknown", attach_customers(project_inference_payload(
        "unknown",
        [],
        checked_sources,
        raw_inputs,
        [f"{label_prefix}未识别到 TVD/TVE/TVA/TVI 项目型号"],
    ))


def write_default_evidence(package_dir: Path, rel: str, payload: dict[str, Any]) -> str:
    write_json(package_dir / rel, payload)
    return rel


def parse_corrected_field_args(items: list[str] | None) -> dict[str, str]:
    corrected: dict[str, str] = {}
    for raw in items or []:
        item = str(raw or "").strip()
        if not item:
            continue
        if "=" not in item:
            raise SystemExit(f"--corrected-field 必须使用 field=value 格式: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise SystemExit(f"--corrected-field 字段名不能为空: {item}")
        corrected[key] = value
    return corrected


def normalize_corrected_fields(
    corrected_fields: dict[str, Any] | None,
    *,
    project: str = "",
    platform: str = "",
    android_version: str = "",
) -> dict[str, str]:
    normalized = {
        str(key or "").strip(): str(value or "").strip()
        for key, value in (corrected_fields or {}).items()
        if str(key or "").strip() and str(value or "").strip()
    }
    identity_fields = sorted(set(normalized) & FIELD_CORRECTION_MATERIAL_IDENTITY_FIELDS)
    if identity_fields:
        raise SystemExit(
            "字段级补证不能修正材料身份字段: "
            + ", ".join(identity_fields)
            + "；材料名或材料摘要错误时，请重新生成替换原始包。"
        )
    if project and project != "unknown":
        normalized.setdefault("project", project)
    if platform and platform != "unknown":
        normalized.setdefault("platform", platform)
    if android_version and android_version != "unknown":
        normalized.setdefault("android_version", android_version)
    return normalized


def infer_supplement_mode(explicit_mode: str, supplement_for_package_key: str, supplement_reason: str, corrected_fields: dict[str, Any] | None) -> str:
    mode = str(explicit_mode or "").strip()
    if mode:
        return mode
    if not str(supplement_for_package_key or "").strip():
        return ""
    if corrected_fields:
        return "field_correction"
    if patch_asset_correction_source_errors(
        {
            "package_kind": "framework_change",
            "supplement_for_package_key": supplement_for_package_key,
            "supplement_reason": supplement_reason,
        },
        {"capture_package_count": 0},
    ):
        return "asset_correction"
    return ""


def framework_package_status_from_patch_statuses(statuses: set[str], has_pass_verification: bool) -> str:
    clean = {item for item in statuses if item in PACKAGE_STATUS_VALUES}
    if has_pass_verification and "validated" in clean:
        return "validated"
    if "candidate" in clean or ("validated" in clean and not has_pass_verification):
        return "candidate"
    if "draft" in clean:
        return "draft"
    if "failed" in clean:
        return "failed"
    if "blocked" in clean:
        return "blocked"
    return "candidate"


def downgrade_validated_patch_entries(patch_entries: list[dict[str, Any]], note: str) -> None:
    for item in patch_entries:
        if item.get("status") == "validated":
            item["status"] = "candidate"
            item["reuse_hint"] = False
            previous_note = str(item.get("note") or "").strip()
            item["note"] = f"{previous_note}；{note}" if previous_note else note


def framework_metadata_is_traceable(project: str, platform: str, android_version: str) -> bool:
    return (
        project not in {"", "unknown"}
        and platform in VALID_FRAMEWORK_PLATFORMS
        and is_valid_android_version_value(android_version)
        and android_version != "unknown"
    )


def prepare_field_correction_package(
    date: dt.date,
    config: dict[str, str],
    run_id: str,
    *,
    project: str,
    platform: str,
    android_version: str,
    summary: str,
    schema_version: str,
    supplement_for_package_key: str,
    supplement_reason: str,
    corrected_fields: dict[str, str],
    correction_reason: str,
) -> Path:
    if not supplement_for_package_key:
        raise SystemExit("字段级补证必须提供 --supplement-for-package-key，且必须指向原始包。")
    out_dir = require_safe_artifact_path(expanded_path(config["out_dir"]), purpose="out_dir")
    package_dir = require_safe_artifact_path(out_dir / "pending" / ymd(date) / config["member_alias"] / run_id, purpose="incoming package output")
    if package_dir.exists():
        raise SystemExit(f"工作包已存在: {package_dir}")
    package_dir.mkdir(parents=True)

    source_path = materials_rel("evidence", "source.json")
    source = write_package_source(package_dir, config, "android-knowledge-intake")
    case_id = "case-" + stable_slug_id(supplement_for_package_key, "field-correction", 80)
    variant_seed = json.dumps(
        {
            "target": supplement_for_package_key,
            "project": project,
            "platform": platform,
            "android_version": android_version,
            "corrected_fields": corrected_fields,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    variant_id = "variant-" + stable_slug_id(supplement_for_package_key, "field-correction", 100, variant_seed)
    case_path = materials_rel("case.json")
    variant_path = materials_rel("variant.json")
    readme_path = "README.md"
    package_status = "validated"

    readme_lines = [
        f"# {summary}",
        "",
        "## 补证类型",
        "",
        "字段级 / 展示级补证（field correction）。",
        "",
        "## 补证目标",
        "",
        supplement_for_package_key,
        "",
        "## 修正字段",
        "",
        *[f"- {key}: {value}" for key, value in sorted(corrected_fields.items())],
        "",
        "## 说明",
        "",
        correction_reason or supplement_reason or "补充原始包的结构化字段。",
        "",
        "本包不包含补丁 diff、验证结论、patch_ai_facts 或代码证据；这些核心证据缺口必须完整重采。",
        "",
    ]
    (package_dir / readme_path).write_text("\n".join(readme_lines), encoding="utf-8")
    write_json(
        package_dir / case_path,
        {
            "case_id": case_id,
            "title": summary,
            "problem": correction_reason or supplement_reason or summary,
            "solution_summary": "补充结构化字段和展示字段，不修改补丁资产或验证证据。",
        },
    )
    write_json(
        package_dir / variant_path,
        {
            "variant_id": variant_id,
            "case_id": case_id,
            "platform": platform,
            "android_version": android_version,
            "project": project,
            "repo_paths": [],
            "related_report_run_ids": [],
            "implementation_origins": [],
            "capture_tools": [],
            "package_status": package_status,
        },
    )

    project_payload = project_inference_payload(
        project,
        [f"字段补证 corrected_fields.project={project}"] if project != "unknown" else [],
        ["corrected_fields", "command_args"],
        [f"{key}: {value}" for key, value in sorted(corrected_fields.items())],
        [] if project != "unknown" else ["字段补证未提供可识别项目名"],
    )
    project_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "project_inference.json"),
        {
            "kind": "project_inference",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": project_payload,
        },
    )
    expected_source_key = f"{ymd(date)}/{config['member_alias']}/{run_id}"
    correction_payload = {
        "target_package_key": supplement_for_package_key,
        "source_package_key": expected_source_key,
        "supplement_mode": "field_correction",
        "corrected_fields": corrected_fields,
        "correction_reason": correction_reason or supplement_reason,
        "corrected_by": {
            "member_alias": config["member_alias"],
            "member_name": config["member_name"],
        },
        "corrected_at": local_now(config).isoformat(),
        "notes": "字段级补证不携带补丁 diff、验证结论、patch_ai_facts 或代码证据。",
    }
    field_correction_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "field_correction.json"),
        {
            "kind": "field_correction",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": correction_payload,
        },
    )
    supplement_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "evidence_supplement.json"),
        {
            "kind": "evidence_supplement",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": {
                "target_package_key": supplement_for_package_key,
                "reason": supplement_reason or correction_reason,
                "source_package_key": expected_source_key,
                "project": project,
                "platform": platform,
                "android_version": android_version,
                "package_status": package_status,
                "summary": summary,
                "supplement_mode": "field_correction",
                "corrected_fields": corrected_fields,
                "correction_reason": correction_reason or supplement_reason,
                "corrected_by": correction_payload["corrected_by"],
                "corrected_at": correction_payload["corrected_at"],
            },
        },
    )
    patch_view_path = materials_rel("display", "patch_view.json")
    manifest_context = {
        "summary": summary,
        "project": project,
        "platform": platform,
        "android_version": android_version,
        "member_alias": config["member_alias"],
        "member_name": config["member_name"],
    }
    write_json(
        package_dir / patch_view_path,
        patch_view_payload(
            manifest_context,
            case_problem=correction_reason or supplement_reason or summary,
            case_solution="补充结构化字段和展示字段，不修改补丁资产或验证证据。",
            verification_payload={"result": "INFO", "method": "field_correction", "summary": "字段级补证，不包含补丁 diff、验证结论或代码证据。"},
            risk_payload={"risk_areas": ["仅修正字段；核心证据缺口仍需完整重采。"]},
            patch_rel_paths=[],
            supplement_for_package_key=supplement_for_package_key,
            supplement_reason=supplement_reason or correction_reason,
            supplement_mode="field_correction",
            corrected_fields=corrected_fields,
        ),
    )
    manifest = {
        "schema": "knowledge-incoming-package",
        "schema_version": schema_version,
        "package_kind": "framework_change",
        "member_alias": config["member_alias"],
        "member_name": config["member_name"],
        "date": date.isoformat(),
        "run_id": run_id,
        "tool": "android-knowledge-intake",
        "case_id": case_id,
        "variant_id": variant_id,
        "package_status": package_status,
        "platform": platform,
        "android_version": android_version,
        "project": project,
        "summary": summary,
        "implementation_origins": [],
        "capture_tools": [],
        "supplement_for_package_key": supplement_for_package_key,
        "supplement_reason": supplement_reason or correction_reason,
        "supplement_mode": "field_correction",
        "material_identity": {
            "mode": "inherit_target_package",
            "target_package_key": supplement_for_package_key,
            "editable": False,
        },
        "corrected_fields": corrected_fields,
        "correction_reason": correction_reason or supplement_reason,
        "files": {
            "case": case_path,
            "variant": variant_path,
            "readme": readme_path,
            "patches": [],
            "display": [patch_view_path],
            "evidence": [source_path, project_path, supplement_path, field_correction_path],
        },
    }
    for evidence_rel in manifest["files"]["evidence"]:
        bind_framework_evidence(package_dir, evidence_rel, case_id, variant_id)
    write_json(package_dir / "manifest.json", manifest)
    check = validate_package(package_dir)
    write_json(package_dir / "local-check.json", check)
    return package_dir


def prepare_patch_package(
    date: dt.date,
    config: dict[str, str],
    run_id: str | None = None,
    patch_paths: list[str] | None = None,
    patch_package_paths: list[str] | None = None,
    project: str = "unknown",
    summary: str = "管理员手动归档补丁",
    status: str = "validated",
    schema_version: str = INCOMING_SCHEMA_VERSION,
    related_report_run_ids: list[str] | None = None,
    supplement_for_package_key: str = "",
    supplement_reason: str = "",
    platform_override: str = "",
    android_version_override: str = "",
    supplement_mode: str = "",
    corrected_fields: dict[str, Any] | None = None,
    correction_reason: str = "",
) -> Path:
    require_config(config)
    if schema_version != INCOMING_SCHEMA_VERSION:
        raise SystemExit(f"incoming 只支持 schema_version={INCOMING_SCHEMA_VERSION}")
    supplement_for_package_key = str(supplement_for_package_key or "").strip()
    supplement_reason = str(supplement_reason or "").strip()
    inferred_mode = infer_supplement_mode(supplement_mode, supplement_for_package_key, supplement_reason, corrected_fields)
    if inferred_mode and inferred_mode not in SUPPLEMENT_MODES:
        raise SystemExit(f"supplement_mode 非法: {inferred_mode}")
    if inferred_mode == "field_correction":
        run_id = run_id or f"{ymd(date)}-{local_now(config):%H%M%S}-field-supplement"
        platform, android_version = apply_platform_overrides(
            "unknown",
            "unknown",
            platform_override=platform_override or str((corrected_fields or {}).get("platform") or ""),
            android_version_override=android_version_override or str((corrected_fields or {}).get("android_version") or ""),
        )
        normalized_fields = normalize_corrected_fields(
            corrected_fields,
            project=project,
            platform=platform,
            android_version=android_version,
        )
        return prepare_field_correction_package(
            date,
            config,
            run_id,
            project=project if project else normalized_fields.get("project", "unknown"),
            platform=platform,
            android_version=android_version,
            summary=summary,
            schema_version=schema_version,
            supplement_for_package_key=supplement_for_package_key,
            supplement_reason=supplement_reason,
            corrected_fields=normalized_fields,
            correction_reason=correction_reason,
        )
    if patch_paths and len(patch_paths) > 1:
        raise SystemExit(
            "直接 --patch 只允许单个独立补丁。多个补丁必须先用补丁采集技能（android-framework-patch-capture）"
            "按功能生成补丁包（patch package）；一个补丁包只能对应一个功能。"
        )
    run_id = run_id or f"{ymd(date)}-{local_now(config):%H%M%S}-patch"
    scope_errors = patch_capture_package_scope_errors(patch_package_paths, summary, run_id)
    if scope_errors:
        raise SystemExit("\n".join(scope_errors))
    out_dir = require_safe_artifact_path(expanded_path(config["out_dir"]), purpose="out_dir")
    package_dir = require_safe_artifact_path(out_dir / "pending" / ymd(date) / config["member_alias"] / run_id, purpose="incoming package output")
    if package_dir.exists():
        raise SystemExit(f"工作包已存在: {package_dir}")
    package_dir.mkdir(parents=True)

    patch_entries: list[dict[str, Any]] = []
    capture_evidence_entries: list[dict[str, Any]] = []
    patch_sources: list[dict[str, Any]] = []
    source_contexts: list[dict[str, Any]] = []
    has_pass_verification = False
    all_related_report_run_ids = list_string_values(related_report_run_ids)
    feature_readme_rel = ""

    if patch_package_paths:
        (
            capture_entries,
            evidence_entries,
            source_entries,
            capture_has_pass,
            capture_related_report_run_ids,
            capture_source_contexts,
            capture_feature_readme_rel,
        ) = copy_patch_capture_packages(
            package_dir,
            patch_package_paths,
            project,
            status,
        )
        patch_entries.extend(capture_entries)
        capture_evidence_entries.extend(evidence_entries)
        patch_sources.extend(source_entries)
        source_contexts.extend(capture_source_contexts)
        has_pass_verification = has_pass_verification or capture_has_pass
        all_related_report_run_ids.extend(capture_related_report_run_ids)
        feature_readme_rel = capture_feature_readme_rel

    if patch_paths:
        patches = patch_infos_from_paths(patch_paths, project)
    elif synthetic_mode(config):
        patches = [synthetic_patch_info(package_dir, date, project, config)]
        summary = summary if summary != "管理员手动归档补丁" else "合成测试补丁包"
        status = "candidate" if status == "validated" else status
    elif not patch_entries:
        patches = discover_patches_from_cwd(project, date)
    else:
        patches = []
    if not patches:
        if not patch_entries:
            raise SystemExit("patch 模式未找到补丁，请使用 --patch/--patch-package 指定，或在当前目录/patches 下放置当天修改的 .patch 文件。")
    else:
        patch_entries.extend(copy_patch_assets(package_dir, patches, config, status=status, reuse_hint=status == "validated", note="管理员手动归档补丁"))
        patch_sources.extend([{"name": item.name, "source": str(item.path), "project": item.project} for item in patches])
    if not feature_readme_rel:
        feature_readme_rel = write_feature_readme_from_patch_entries(package_dir, summary, patch_entries)
    write_json(
        package_dir / materials_rel("evidence", "framework_change_summary.json"),
        {
            "source": "android-knowledge-intake",
            "mode": "patch",
            "synthetic_data": synthetic_mode(config),
            "patch_count": len(patch_entries),
            "patches": patch_sources,
            "capture_package_count": len(patch_package_paths or []),
            "supplement_mode": inferred_mode,
            "implementation_origins": unique_strings(
                str(item.get("implementation_origin") or "")
                for item in patch_entries
                if str(item.get("implementation_origin") or "").strip()
            ),
            "capture_tools": unique_strings(str(item.get("captured_by") or "") for item in patch_entries if str(item.get("captured_by") or "").strip()),
        },
    )
    ensure_patch_analysis_evidence(package_dir, patch_entries, capture_evidence_entries, summary)
    if not has_pass_verification:
        downgrade_validated_patch_entries(patch_entries, "未携带 PASS 设备验证或合格等价验证，已按 candidate 提交")
    for item in patch_entries:
        if item.get("status") in {"failed", "blocked"}:
            item["reuse_hint"] = False

    platform, android_version = apply_platform_overrides(
        *infer_platform_metadata(patch_entries, capture_evidence_entries, package_dir),
        platform_override=platform_override,
        android_version_override=android_version_override,
    )
    auto_related_report_run_ids: list[str] = []
    if not all_related_report_run_ids:
        auto_related_report_run_ids = same_day_daily_report_run_ids(config, date)
        all_related_report_run_ids.extend(auto_related_report_run_ids)
    related_project_clues = related_report_project_clues(
        config,
        all_related_report_run_ids,
        daily_label_prefix="自动关联同日日报" if auto_related_report_run_ids else "关联日报",
    )
    project, project_payload = infer_project(
        project,
        patch_entries,
        patch_sources,
        summary,
        package_dir,
        source_contexts,
        related_project_clues,
        trusted_platform=platform,
    )
    if not framework_metadata_is_traceable(project, platform, android_version):
        downgrade_validated_patch_entries(
            patch_entries,
            "项目（project）、平台（platform）或 Android 版本（Android version）缺少可追溯元数据，已按 candidate 提交",
        )
    statuses = {str(item.get("status", "")) for item in patch_entries}
    source_path = materials_rel("evidence", "source.json")
    source = write_package_source(package_dir, config, "android-knowledge-intake")
    package_status = framework_package_status_from_patch_statuses(statuses, has_pass_verification)
    all_patch_items = [incoming_patch_item(package_dir, item) for item in patch_entries]
    implementation_origins = unique_strings(
        str(item.get("implementation_origin") or "")
        for item in all_patch_items
        if str(item.get("implementation_origin") or "").strip()
    )
    if implementation_origins:
        source["implementation_origins"] = implementation_origins
        if len(implementation_origins) == 1:
            source["implementation_origin"] = implementation_origins[0]
        write_json(package_dir / source_path, {"kind": "source", "payload": source})
    capture_tools = unique_strings(str(item.get("captured_by") or "") for item in all_patch_items if str(item.get("captured_by") or "").strip())
    modified_files = sorted(
        {
            file
            for item in all_patch_items
            for file in item.get("facts", {}).get("modified_files", [])
            if isinstance(file, str) and file
        }
    )
    repo_paths = sorted(
        {
            str(item.get("repo_path") or "").strip("/")
            for item in all_patch_items
            if str(item.get("repo_path") or "").strip("/")
        }
    ) or repo_paths_from_files(modified_files)
    patch_rel_paths = [str(item["path"]) for item in all_patch_items]
    all_related_report_run_ids = unique_strings(all_related_report_run_ids)
    case_id = "case-" + stable_slug_id(summary, "framework-change", 80)
    variant_seed = json.dumps(
        {
            "android_version": android_version,
            "case_id": case_id,
            "platform": platform,
            "project": project,
            "repo_paths": repo_paths,
            "summary": summary,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    variant_id = "variant-" + stable_slug_id("-".join([platform, android_version, project, summary]), "framework-change", 100, variant_seed)
    patch_problem_payload = first_evidence_payload(package_dir, capture_evidence_entries, "patch_problem_summary")
    case_problem = str(patch_problem_payload.get("problem_summary") or summary)
    case_solution = str(patch_problem_payload.get("solution_summary") or summary)

    case_path = materials_rel("case.json")
    variant_path = materials_rel("variant.json")
    write_json(
        package_dir / case_path,
        {
            "case_id": case_id,
            "title": summary,
            "problem": case_problem,
            "solution_summary": case_solution,
        },
    )
    write_json(
        package_dir / variant_path,
        {
            "variant_id": variant_id,
            "case_id": case_id,
            "platform": platform,
            "android_version": android_version,
            "project": project,
            "repo_paths": repo_paths,
            "implementation_origins": implementation_origins,
            "capture_tools": capture_tools,
            "package_status": package_status,
        },
    )

    project_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "project_inference.json"),
        {
            "kind": "project_inference",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": project_payload,
        },
    )

    verification_payload = first_evidence_payload(package_dir, capture_evidence_entries, "verification_result")
    verification_result_value = str(verification_payload.get("result", "")).upper()
    if verification_result_value not in {"PASS", "FAIL"}:
        verification_payload = {
            "result": "MISSING",
            "method": "not_provided",
            "summary": "未携带设备或等价验证证据，按非 validated 包状态上传。",
        }
    verification_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "verification_result.json"),
        {
            "kind": "verification_result",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": verification_payload,
        },
    )
    if package_status == "validated" and str(verification_payload.get("result", "")).upper() != "PASS":
        package_status = "candidate"

    capture_search_payload = first_evidence_payload(package_dir, capture_evidence_entries, "search_before_change")
    member_search_payload = search_usage_payload(config, date, feature_tokens=patch_search_feature_tokens(summary, all_patch_items, modified_files))
    if search_payload_has_member_decision(capture_search_payload):
        search_payload = capture_search_payload
    elif member_search_payload:
        search_payload = member_search_payload
    else:
        search_payload = capture_search_payload
    if not search_payload:
        search_payload = {
            "result": "INFO",
            "method": "knowledge_search",
            "searched": False,
            "queries": [],
            "results": [],
            "summary": "未提供开发前知识库检索记录。",
        }
    search_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "search_before_change.json"),
        {
            "kind": "search_before_change",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": search_payload,
        },
    )
    optional_evidence_paths = [
        rel
        for kind in sorted(FRAMEWORK_OPTIONAL_EVIDENCE_KINDS)
        for rel in [first_evidence_path(capture_evidence_entries, kind)]
        if rel
    ]

    patch_diff_payload = aggregate_patch_diff_facts(all_patch_items)
    patch_diff_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "patch_diff_facts.json"),
        {
            "kind": "patch_diff_facts",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": patch_diff_payload,
        },
    )
    patch_problem_path = first_evidence_path(capture_evidence_entries, "patch_problem_summary")
    risk_path = first_evidence_path(capture_evidence_entries, "risk_surface")
    required_generated = {
        "patch_diff_facts": patch_diff_path,
        "patch_problem_summary": patch_problem_path,
        "risk_surface": risk_path,
    }
    for kind, rel in list(required_generated.items()):
        if not rel:
            fallback = materials_rel("evidence", f"{kind}.json")
            payload: dict[str, Any] = {"basis": ["自动生成兜底证据"], "limits": ["缺少可解析补丁证据"]}
            if kind == "patch_problem_summary":
                payload.update(
                    {
                        "problem_summary": summary,
                        "solution_summary": "成员端 Codex 未取得更完整的补丁说明，需结合 diff 和验证证据复核。",
                        "keywords": [],
                    }
                )
            if kind == "risk_surface":
                payload["risk_areas"] = ["修改路径需按需求验证"]
            write_default_evidence(
                package_dir,
                fallback,
                {
                    "kind": kind,
                    "case_id": case_id,
                    "variant_id": variant_id,
                    **payload,
                },
            )
            required_generated[kind] = fallback

    supplement_for_package_key = str(supplement_for_package_key or "").strip()
    supplement_reason = str(supplement_reason or "").strip()
    supplement_path = ""
    if supplement_for_package_key:
        if not supplement_reason:
            supplement_reason = "补充原始上传包的沉淀证据。"
        supplement_path = write_default_evidence(
            package_dir,
            materials_rel("evidence", "evidence_supplement.json"),
            {
                "kind": "evidence_supplement",
                "case_id": case_id,
                "variant_id": variant_id,
                "payload": {
                    "target_package_key": supplement_for_package_key,
                    "reason": supplement_reason,
                    "source_package_key": f"{ymd(date)}/{config['member_alias']}/{run_id}",
                    "project": project,
                    "platform": platform,
                    "android_version": android_version,
                    "package_status": package_status,
                    "summary": summary,
                    "supplement_mode": inferred_mode,
                },
            },
        )

    manifest_context = {
        "summary": summary,
        "project": project,
        "platform": platform,
        "android_version": android_version,
        "member_alias": config["member_alias"],
        "member_name": config["member_name"],
    }
    risk_payload = first_evidence_payload(package_dir, capture_evidence_entries, "risk_surface")
    if not risk_payload:
        risk_payload = {"risk_areas": ["修改路径需按需求验证"], "limits": ["缺少可解析风险证据"]}
    patch_view_path = materials_rel("display", "patch_view.json")
    write_json(
        package_dir / patch_view_path,
        patch_view_payload(
            manifest_context,
            case_problem=case_problem,
            case_solution=case_solution,
            verification_payload=verification_payload,
            risk_payload=risk_payload,
            patch_rel_paths=patch_rel_paths,
            supplement_for_package_key=supplement_for_package_key,
            supplement_reason=supplement_reason,
        ),
    )
    patch_ai_facts_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "patch_ai_facts.json"),
        {
            "kind": "patch_ai_facts",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": patch_ai_facts_payload(
                manifest_like=manifest_context,
                patch_diff_payload=patch_diff_payload,
                search_payload=search_payload,
                verification_payload=verification_payload,
                case_problem=case_problem,
                case_solution=case_solution,
                plugin_version=plugin_install_metadata().get("plugin_version", ""),
            ),
        },
    )

    write_json(
        package_dir / variant_path,
        {
            "variant_id": variant_id,
            "case_id": case_id,
            "platform": platform,
            "android_version": android_version,
            "project": project,
            "repo_paths": repo_paths,
            "related_report_run_ids": all_related_report_run_ids,
            "implementation_origins": implementation_origins,
            "capture_tools": capture_tools,
            "package_status": package_status,
        },
    )
    manifest = {
        "schema": "knowledge-incoming-package",
        "schema_version": INCOMING_SCHEMA_VERSION,
        "package_kind": "framework_change",
        "member_alias": config["member_alias"],
        "member_name": config["member_name"],
        "date": date.isoformat(),
        "run_id": run_id,
        "tool": "android-knowledge-intake",
        "case_id": case_id,
        "variant_id": variant_id,
        "package_status": package_status,
        "platform": platform,
        "android_version": android_version,
        "project": project,
        "summary": summary,
        "implementation_origins": implementation_origins,
        "capture_tools": capture_tools,
        "files": {
            "case": case_path,
            "variant": variant_path,
            "readme": feature_readme_rel,
            "patches": patch_rel_paths,
            "display": [patch_view_path],
            "evidence": [
                source_path,
                required_generated["patch_diff_facts"],
                patch_ai_facts_path,
                project_path,
                required_generated["patch_problem_summary"],
                required_generated["risk_surface"],
                verification_path,
                search_path,
                *([supplement_path] if supplement_path else []),
                *optional_evidence_paths,
            ],
        },
    }
    if all_related_report_run_ids:
        manifest["related_report_run_ids"] = all_related_report_run_ids
    if supplement_for_package_key:
        manifest["supplement_for_package_key"] = supplement_for_package_key
        manifest["supplement_reason"] = supplement_reason
        manifest["material_identity"] = {
            "mode": "inherit_target_package",
            "target_package_key": supplement_for_package_key,
            "editable": False,
        }
        if inferred_mode:
            manifest["supplement_mode"] = inferred_mode
    for evidence_rel in manifest["files"]["evidence"]:
        bind_framework_evidence(package_dir, evidence_rel, case_id, variant_id)
    write_json(package_dir / "manifest.json", manifest)
    check = validate_package(package_dir)
    write_json(package_dir / "local-check.json", check)
    return package_dir



def git_run(repo: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return _intake_git_run(repo, args, run, check=check)


def submit_package(package_dir: Path, config: dict[str, str]) -> dict[str, Any]:
    check = validate_package(package_dir)
    write_json(package_dir / "local-check.json", check)
    if check["status"] != "PASS":
        raise SystemExit("本地工作包校验失败，已停止提交。请查看 local-check.json。")
    manifest = read_json_file(package_dir / "manifest.json")
    ensure_report_submit_allowed(package_dir, config, manifest)
    gate_errors = patch_upload_gate_errors(manifest)
    if gate_errors:
        raise SystemExit("\n".join(gate_errors))

    result = server_submit_package(package_dir, config)
    if manifest.get("package_kind") in {"daily_trace", "weekly_trace"}:
        record_submitted_package(package_dir, config, manifest)
    return result


from akbs_intake.submit import (  # noqa: E402
    http_submit_package,
    package_tar_gz_bytes,
    server_submit_package,
    upload_type_for_manifest,
)


def latest_pending(report_type: str, config: dict[str, str], date: dt.date | None = None) -> Path:
    return _intake_latest_pending(report_type, config, date)


def doctor_strict_checks(
    config: dict[str, str],
    loaded: list[Path],
    check_remote: bool,
    allow_synthetic: bool,
) -> dict[str, Any]:
    return _intake_doctor_strict_checks(
        config,
        loaded,
        check_remote,
        allow_synthetic,
        run_command=run,
        plugin_gate_check=plugin_version_gate_check,
    )


def doctor(
    config: dict[str, str],
    loaded: list[Path],
    strict: bool = False,
    check_remote: bool = False,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    return _intake_doctor(
        config,
        loaded,
        strict,
        check_remote,
        allow_synthetic,
        plugin_root=PLUGIN_ROOT,
        run_command=run,
        plugin_gate_check=plugin_version_gate_check,
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and submit Codex team knowledge incoming packages.")
    parser.add_argument("--profile", help="profile name from config, for example admin_alias or member_alias")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--strict", action="store_true", help="fail when the selected profile is unsafe for member-side automation")
    doctor_parser.add_argument("--check-remote", action="store_true", help="also verify plugin freshness and optional local knowledge fallback reachability")
    doctor_parser.add_argument("--allow-synthetic", action="store_true", help="allow synthetic_data=true for protocol or gray-flow testing")
    doctor_parser.set_defaults(report_type="")

    for report_type in ("daily", "weekly", "patch"):
        sub = subparsers.add_parser(report_type)
        sub.set_defaults(report_type=report_type)
        sub.add_argument("--date", help="YYYY-MM-DD, defaults to today")
        sub.add_argument("--run-id", help="override run id, format YYYYMMDD-HHMMSS[-suffix]")
        sub.add_argument("--schema-version", choices=[INCOMING_SCHEMA_VERSION], default="", help="incoming package schema version")
        if report_type == "patch":
            sub.add_argument("--patch", dest="patches", action="append", default=[], help="patch file to include; repeatable")
            sub.add_argument("--patch-package", dest="patch_packages", action="append", default=[], help="android-framework-patch-capture package directory to include; repeatable")
            sub.add_argument("--project", default="unknown", help="project name for framework_change incoming")
            sub.add_argument("--platform", default="", help="explicit platform for framework_change incoming: mtk, rk, unisoc, or unknown")
            sub.add_argument("--android-version", default="", help="explicit Android version for framework_change incoming, for example 14, 16, or 9.0")
            sub.add_argument("--summary", default="Framework 修改沉淀", help="summary for framework_change incoming")
            sub.add_argument("--related-report-run-id", dest="related_report_run_ids", action="append", default=[], help="daily/weekly incoming run_id related to this framework_change; repeatable")
            sub.add_argument("--supplement-for-package-key", default="", help="original incoming package key that this framework_change package supplements")
            sub.add_argument("--supplement-reason", default="", help="why this package supplements the original incoming package")
            sub.add_argument("--supplement-mode", choices=["field_correction", "asset_correction"], default="", help="field_correction for project/platform/Android version metadata supplements, asset_correction for full patch asset recapture")
            sub.add_argument("--corrected-field", dest="corrected_fields", action="append", default=[], help="field=value correction for field_correction supplements; repeatable")
            sub.add_argument("--correction-reason", default="", help="audit reason for field_correction supplements")
            sub.add_argument(
                "--status",
                choices=["draft", "candidate", "validated", "failed", "blocked"],
                default="validated",
                help="patch package status",
            )
        if report_type == "weekly":
            sub.add_argument(
                "--replace-weekly-run-id",
                default="",
                help="explicitly regenerate a weekly package for an existing week_range and write supersedes metadata",
            )
        if report_type == "daily":
            sub.add_argument(
                "--replace-daily-run-id",
                default="",
                help="explicitly regenerate a daily package for an existing report date and write supersedes metadata",
            )
        action = sub.add_mutually_exclusive_group(required=True)
        action.add_argument("--prepare", action="store_true", help="generate pending package only")
        action.add_argument("--submit-latest", action="store_true", help="submit latest pending package")
        action.add_argument("--upload", action="store_true", help="prepare then submit")
        action.add_argument("--validate", metavar="PACKAGE_DIR", help="validate an existing package")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    config, loaded = load_config(args.profile)

    if args.command == "doctor":
        result = doctor(config, loaded, args.strict, args.check_remote, args.allow_synthetic)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not args.strict or result.get("status") == "PASS" else 1

    if args.command in PACKAGE_TYPES and not args.validate and (args.prepare or args.submit_latest or args.upload):
        freshness = plugin_version_gate_check(config, fetch=True, require=True)
        if freshness.get("blocking"):
            reexec_error = reexec_latest_plugin_script_after_update(freshness)
            if reexec_error:
                freshness["reexec_error"] = reexec_error
            print(
                json.dumps(
                    {
                        "status": "FAIL",
                        "message": freshness.get("reexec_error") or freshness.get("message") or "插件更新检查失败。",
                        "plugin_freshness": freshness,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1

    date = parse_date_arg(args.date, config)
    if args.validate:
        result = validate_package(Path(args.validate))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PASS" else 1
    if args.prepare or args.submit_latest or args.upload:
        enforce_mode_allowed(config, args.report_type)
    if args.prepare:
        schema_version = args.schema_version or config.get("incoming_schema_version", INCOMING_SCHEMA_VERSION)
        if args.report_type == "patch":
            package_dir = prepare_patch_package(
                date,
                config,
                args.run_id,
                args.patches,
                args.patch_packages,
                args.project,
                args.summary,
                args.status,
                schema_version,
                args.related_report_run_ids,
                args.supplement_for_package_key,
                args.supplement_reason,
                args.platform,
                args.android_version,
                args.supplement_mode,
                parse_corrected_field_args(args.corrected_fields),
                args.correction_reason,
            )
        else:
            package_dir = prepare_package(
                args.report_type,
                date,
                config,
                args.run_id,
                schema_version,
                getattr(args, "replace_daily_run_id", "") or getattr(args, "replace_weekly_run_id", ""),
            )
        result = json.loads((package_dir / "local-check.json").read_text(encoding="utf-8"))
        print(json.dumps({"package": str(package_dir), "local_check": result}, ensure_ascii=False, indent=2))
        if args.report_type in {"daily", "weekly"}:
            return 0
        return 0 if result["status"] == "PASS" else 1
    if args.submit_latest:
        package_dir = latest_pending(args.report_type, config, date if args.date else None)
        result = submit_package(package_dir, config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.upload:
        schema_version = args.schema_version or config.get("incoming_schema_version", INCOMING_SCHEMA_VERSION)
        if args.report_type == "patch":
            package_dir = prepare_patch_package(
                date,
                config,
                args.run_id,
                args.patches,
                args.patch_packages,
                args.project,
                args.summary,
                args.status,
                schema_version,
                args.related_report_run_ids,
                args.supplement_for_package_key,
                args.supplement_reason,
                args.platform,
                args.android_version,
                args.supplement_mode,
                parse_corrected_field_args(args.corrected_fields),
                args.correction_reason,
            )
        else:
            package_dir = prepare_package(
                args.report_type,
                date,
                config,
                args.run_id,
                schema_version,
                getattr(args, "replace_daily_run_id", "") or getattr(args, "replace_weekly_run_id", ""),
            )
        result = submit_package(package_dir, config)
        print(json.dumps({"package": str(package_dir), "submit": result}, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
