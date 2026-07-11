from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from akbs_intake.config import (
    allowed_modes,
    artifact_path_guard_error,
    default_codex_home,
    expanded_path,
    knowledge_repo_worktree,
    parse_bool,
    resolve_akbs_endpoint,
    submission_api_base_url,
    submission_api_token_status,
)


MEMBER_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
RunCommand = Callable[[list[str]], subprocess.CompletedProcess[str]]
PluginGateCheck = Callable[..., dict[str, Any]]


def latest_pending(report_type: str, config: dict[str, str], date: dt.date | None = None) -> Path:
    out_dir = expanded_path(config["out_dir"]) / "pending"
    candidates: list[Path] = []
    for manifest_path in out_dir.glob("*/*/*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        kind = str(manifest.get("package_kind", ""))
        manifest_type = (
            "daily"
            if kind == "daily_trace"
            else "weekly"
            if kind == "weekly_trace"
            else "patch"
            if kind == "framework_change"
            else ""
        )
        if manifest_type != report_type:
            continue
        if manifest.get("member_alias") != config.get("member_alias"):
            continue
        if date and str(manifest.get("date")) != date.isoformat():
            continue
        candidates.append(manifest_path.parent)
    if not candidates:
        raise SystemExit(f"没有找到 {report_type} pending 工作包")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def nearest_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


def doctor_strict_checks(
    config: dict[str, str],
    loaded: list[Path],
    check_remote: bool,
    allow_synthetic: bool,
    *,
    run_command: RunCommand,
    plugin_gate_check: PluginGateCheck,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    def error(message: str) -> None:
        errors.append(message)

    def warn(message: str) -> None:
        warnings.append(message)

    profile = config.get("profile", "").strip()
    alias = config.get("member_alias", "").strip()
    name = config.get("member_name", "").strip()
    role = config.get("role", "").strip()
    knowledge_repo = knowledge_repo_worktree(config)
    out_dir = expanded_path(config.get("out_dir", ""))

    if not loaded:
        warn("未加载任何配置文件，仅依赖默认值或环境变量；成员端自动化建议使用显式 profile 配置。")
    if not profile:
        error("必须显式选择 profile，避免自动化误用默认身份。")
    if not alias:
        error("member_alias 不能为空。")
    elif alias in {"member_alias", "admin_alias", "unknown"}:
        error(f"member_alias 仍是占位值: {alias}")
    elif not MEMBER_ALIAS_RE.fullmatch(alias):
        error("member_alias 只能使用小写字母、数字、点、下划线或横线，且必须以小写字母或数字开头。")
    if not name:
        error("member_name 不能为空，UI 和索引必须显示真实姓名。")
    elif name in {"成员姓名", "管理员姓名", "unknown", "未知"}:
        error(f"member_name 仍是占位值: {name}")

    if role not in {"member", "admin"}:
        error("role 必须是 member 或 admin。")
        modes: set[str] = set()
    else:
        try:
            modes = allowed_modes(config)
        except SystemExit as exc:
            error(str(exc))
            modes = set()
        if role == "member":
            missing = {"daily", "weekly", "patch"} - modes
            if missing:
                error("member profile 必须允许 daily、weekly、patch，缺少: " + ", ".join(sorted(missing)))
        if role == "admin" and ({"daily", "weekly"} & modes):
            error("admin profile 只能用于手动 patch 贡献，不允许 daily/weekly 自动化。")

    if parse_bool(config.get("synthetic_data", "false")) and not allow_synthetic:
        error("synthetic_data=true 只能用于协议/灰度测试，成员端正式自动化必须关闭。")

    if not submission_api_base_url(config):
        error("submission_api_base_url 不能为空。")
    token_status = submission_api_token_status(config)
    if token_status["status"] != "configured":
        error("缺少安全上传 token；必须先通过受保护环境完成配置。")
    if ".codex/plugins/cache" in knowledge_repo.as_posix():
        error("knowledge_repo_worktree 不能放在插件缓存目录下。")
    if ".codex/plugins/cache" in out_dir.as_posix():
        error("out_dir 不能放在插件缓存目录下。")
    out_dir_guard_error = artifact_path_guard_error(out_dir, purpose="out_dir")
    if out_dir_guard_error:
        error(out_dir_guard_error)

    git_version = run_command(["git", "--version"])
    if git_version.returncode != 0:
        error("找不到 git，无法检查知识库仓库。")

    freshness = plugin_gate_check(config, fetch=check_remote, require=check_remote)
    if freshness.get("blocking"):
        error(str(freshness.get("message") or "插件更新检查失败。"))
    elif freshness.get("status") == "UNKNOWN":
        warn(str(freshness.get("message") or "无法确认插件是否为最新版本。"))

    if not knowledge_repo.exists():
        warn(f"knowledge_repo_worktree 不存在，本地离线搜索不可用: {knowledge_repo}")
    elif not (knowledge_repo / ".git").exists():
        warn(f"knowledge_repo_worktree 已存在但不是 Git 仓库，本地兜底搜索不可用: {knowledge_repo}")

    out_parent = nearest_existing_parent(out_dir.parent)
    if not os.access(out_parent, os.W_OK):
        error(f"out_dir 父目录不可写，无法生成 pending 包: {out_parent}")

    return {
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "warnings": warnings,
    }


def doctor(
    config: dict[str, str],
    loaded: list[Path],
    strict: bool = False,
    check_remote: bool = False,
    allow_synthetic: bool = False,
    *,
    plugin_root: Path,
    run_command: RunCommand,
    plugin_gate_check: PluginGateCheck,
) -> dict[str, Any]:
    knowledge_repo = knowledge_repo_worktree(config)
    endpoint = resolve_akbs_endpoint(config)
    token_status = submission_api_token_status(config)
    public_endpoint = {
        "source": endpoint["source"],
        "submission_api_base_url": endpoint["submission_api_base_url"],
    }
    payload: dict[str, Any] = {
        "skill_root": str(plugin_root),
        "codex_home": default_codex_home(),
        "loaded_config": [str(path) for path in loaded],
        "profile": config.get("profile"),
        "role": config.get("role"),
        "allowed_modes": sorted(allowed_modes(config)),
        "synthetic_data": parse_bool(config.get("synthetic_data", "false")),
        "member_alias": config.get("member_alias"),
        "member_name": config.get("member_name"),
        "akbs_endpoint": public_endpoint,
        "submission_api_base_url": submission_api_base_url(config),
        "upload_token": token_status,
        "submission_api_token_configured": token_status["status"] == "configured",
        "knowledge_repo_worktree": str(knowledge_repo),
        "knowledge_repo_cloned": (knowledge_repo / ".git").exists(),
        "out_dir": str(expanded_path(config["out_dir"])),
        "git": run_command(["git", "--version"]).stdout.strip(),
        "plugin_freshness": plugin_gate_check(config, fetch=check_remote, require=False),
    }
    if strict:
        payload["strict"] = doctor_strict_checks(
            config,
            loaded,
            check_remote,
            allow_synthetic,
            run_command=run_command,
            plugin_gate_check=plugin_gate_check,
        )
        payload["status"] = payload["strict"]["status"]
    return payload
