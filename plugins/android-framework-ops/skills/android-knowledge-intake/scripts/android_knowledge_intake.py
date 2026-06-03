#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
INCOMING_SCHEMA_VERSION = "1"
ENV_PREFIXES = ("CODEX_REPORT_", "CODEX_WORK_REPORT_")
PATCH_FILENAME_RE = re.compile(r"^[a-z0-9]+[0-9]+-[A-Za-z0-9._-]+@[a-z0-9_.-]+\.patch$")
AUTHOR_DATE_RE = re.compile(r"//[A-Za-z0-9_]+\s+\d{8}@")
PROJECT_MODEL_RE = re.compile(r"(?<![A-Z0-9])TV[EAI][A-Z0-9]{5}(?:[A-Z0-9_]+)?(?![A-Z0-9])", re.I)
BANNED_LOG_PATTERNS = ("Log.d(", "Log.i(", "Log.w(", "Slog.d(", "Slog.i(", "Slog.w(")
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
MATURITY_VALUES = {"validated", "candidate", "draft", "failed", "blocked"}
TRACE_REQUIRED_EVIDENCE_KINDS = {"source", "work_findings"}
FRAMEWORK_REQUIRED_EVIDENCE_KINDS = {
    "source",
    "patch_diff_facts",
    "project_inference",
    "patch_problem_summary",
    "risk_surface",
    "verification_result",
    "search_before_change",
}
FRAMEWORK_OPTIONAL_EVIDENCE_KINDS = {"build_result", "deploy_result", "device_health"}
EXPLANATION_EVIDENCE_KINDS = {"patch_problem_summary", "risk_surface"}
REQUIRED_PATCH_EXPLANATION_KINDS = {"patch_problem_summary", "risk_surface"}
EVIDENCE_CONFIDENCE_VALUES = {"low", "medium", "high"}
REPORT_KINDS = {"daily", "weekly", "summary", "session"}
LEGACY_PATCH_PROBLEM_KIND = "patch_" + "problem_" + "inference"
EVIDENCE_KINDS = {
    "source",
    "codex_sessions",
    "changed_files",
    "patch_diff_facts",
    "patch_problem_summary",
    "risk_surface",
    "build_result",
    "verification_result",
    "device_verification",
    "equivalent_verification",
    "search_before_change",
    "package_check",
    "summary",
}
EVIDENCE_RESULTS = {"PASS", "WARN", "FAIL", "INFO", "SKIPPED"}
PATCH_STATUSES = MATURITY_VALUES
RELATION_TYPES = {"described_by", "verified_by", "reported_in", "originated_from", "generated_from"}
VERIFICATION_EVIDENCE_KINDS = {"verification_result", "device_verification", "equivalent_verification"}
DATE_KEY_RE = re.compile(r"^\d{8}$")
DATE_DISPLAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RUN_ID_RE = re.compile(r"^\d{8}-\d{6}(-[A-Za-z0-9_.-]+)?$")
MEMBER_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


CONFIG_DEFAULTS = {
    "default_profile": "",
    "profile": "",
    "role": "",
    "allowed_modes": "",
    "member_alias": "",
    "member_name": "",
    "repo_url": "test35:/home/test35/work/knowledge/remote.git",
    "repo_worktree": "$CODEX_HOME/worktrees/knowledge",
    "git_user_name": "",
    "git_user_email": "",
    "codex_home": "$CODEX_HOME",
    "out_dir": "$CODEX_HOME/artifacts/android-knowledge-intake",
    "incoming_schema_version": "1",
    "include_patches": "true",
    "max_attachment_mb": "5",
    "push_retries": "3",
    "timezone": "Asia/Shanghai",
    "synthetic_data": "false",
    "synthetic_item_count": "3",
}


@dataclass
class SessionWork:
    session_id: str = ""
    thread_name: str = ""
    cwd: str = ""
    project: str = "未识别项目"
    messages: list[str] = field(default_factory=list)


@dataclass
class PatchInfo:
    path: Path
    name: str
    project: str


def run(cmd: list[str], check: bool = False, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        errors="replace",
    )
    if check and cp.returncode != 0:
        detail = cp.stderr.strip() or cp.stdout.strip()
        raise SystemExit(f"命令失败: {' '.join(cmd)}\n{detail}")
    return cp


def default_codex_home() -> str:
    if os.environ.get("CODEX_HOME"):
        return os.environ["CODEX_HOME"]
    return str(Path.home() / ".codex")


def expanded_path(value: str) -> Path:
    codex_home = default_codex_home()
    expanded = str(value).replace("${CODEX_HOME}", codex_home).replace("$CODEX_HOME", codex_home)
    return Path(os.path.expandvars(expanded)).expanduser()


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def synthetic_mode(config: dict[str, str]) -> bool:
    return parse_bool(config.get("synthetic_data", "false"))


def read_toml(path: Path) -> dict[str, Any]:
    try:
        try:
            import tomllib

            return tomllib.loads(path.read_text(encoding="utf-8"))
        except ModuleNotFoundError:
            return parse_simple_toml(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"读取配置失败: {path}: {exc}") from exc


def parse_toml_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        body = value[1:-1].strip()
        if not body:
            return []
        items = []
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


def stringify_config_value(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def flatten_config_payload(payload: dict[str, Any]) -> dict[str, str]:
    flattened: dict[str, str] = {}

    def add(key: str, value: Any, section: str = "") -> None:
        if isinstance(value, dict):
            return
        normalized = key
        if section == "member" and key == "alias":
            normalized = "member_alias"
        elif section == "member" and key == "name":
            normalized = "member_name"
        elif section == "server" and key == "repo_url":
            normalized = "repo_url"
        elif section == "server" and key == "worktree":
            normalized = "repo_worktree"
        elif section == "paths" and key in {"worktree", "repo_worktree"}:
            normalized = "repo_worktree"
        elif section == "paths" and key in {"codex_home", "out_dir"}:
            normalized = key
        elif section == "git" and key in {"user_name", "name"}:
            normalized = "git_user_name"
        elif section == "git" and key in {"user_email", "email"}:
            normalized = "git_user_email"
        elif key == "person":
            normalized = "member_name"
        elif key == "name":
            normalized = "member_name"
        if normalized in CONFIG_DEFAULTS:
            flattened[normalized] = stringify_config_value(value)

    for key, value in payload.items():
        if key == "profiles":
            continue
        if isinstance(value, dict):
            for subkey, subvalue in value.items():
                add(str(subkey), subvalue, str(key))
        else:
            add(str(key), value)
    return flattened


def profile_configs(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for name, profile_payload in profiles.items():
        if isinstance(profile_payload, dict):
            result[str(name)] = flatten_config_payload(profile_payload)
    return result


def find_project_report_config(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        candidate = directory / ".codex" / "report.toml"
        if candidate.exists():
            return candidate
    return None


def profile_from_env() -> str:
    for prefix in ENV_PREFIXES:
        value = os.environ.get(f"{prefix}PROFILE")
        if value:
            return value
    return ""


def apply_env_overrides(config: dict[str, str]) -> None:
    aliases = {
        "MEMBER": "member_alias",
        "ALIAS": "member_alias",
        "PERSON": "member_name",
        "PERSON_NAME": "member_name",
        "MEMBER_NAME": "member_name",
        "REPO": "repo_url",
        "WORKTREE": "repo_worktree",
    }
    for env_key, value in os.environ.items():
        for prefix in ENV_PREFIXES:
            if not env_key.startswith(prefix):
                continue
            raw = env_key[len(prefix) :]
            key = aliases.get(raw, raw.lower())
            if key in config:
                config[key] = value


def load_config(profile_override: str | None = None) -> tuple[dict[str, str], list[Path]]:
    config = CONFIG_DEFAULTS.copy()
    codex_home = Path(default_codex_home())
    paths = [
        PLUGIN_ROOT / "config.toml",
        codex_home / "android-knowledge-intake.toml",
        codex_home / "report" / "config.toml",
    ]
    project_config = find_project_report_config()
    if project_config:
        paths.append(project_config)

    loaded: list[Path] = []
    profile_overrides: dict[str, dict[str, str]] = {}
    for path in paths:
        if not path.exists():
            continue
        loaded.append(path)
        payload = read_toml(path)
        for key, value in flatten_config_payload(payload).items():
            config[key] = value
        for name, values in profile_configs(payload).items():
            profile_overrides.setdefault(name, {}).update(values)

    selected_profile = (profile_override or profile_from_env() or config.get("default_profile", "")).strip()
    if selected_profile:
        if selected_profile not in profile_overrides:
            raise SystemExit(f"profile 不存在: {selected_profile}")
        config.update(profile_overrides[selected_profile])
        config["profile"] = selected_profile
    apply_env_overrides(config)
    return config, loaded


def require_config(config: dict[str, str]) -> None:
    missing = [key for key in ("member_alias", "member_name", "repo_url") if not config.get(key, "").strip()]
    if missing:
        raise SystemExit("缺少必要配置: " + ", ".join(missing))


def allowed_modes(config: dict[str, str]) -> set[str]:
    raw = config.get("allowed_modes", "").strip()
    if not raw:
        return set(PACKAGE_TYPES)
    modes = {item.strip() for item in raw.split(",") if item.strip()}
    invalid = modes - PACKAGE_TYPES
    if invalid:
        raise SystemExit("allowed_modes 包含非法类型: " + ", ".join(sorted(invalid)))
    return modes


def enforce_mode_allowed(config: dict[str, str], report_type: str) -> None:
    modes = allowed_modes(config)
    if report_type not in modes:
        profile = config.get("profile") or config.get("member_alias") or "unknown"
        raise SystemExit(f"profile {profile} 不允许执行 {report_type}，允许类型: {', '.join(sorted(modes))}")


def local_now(config: dict[str, str]) -> dt.datetime:
    timezone = config.get("timezone", "Asia/Shanghai")
    if ZoneInfo is not None:
        return dt.datetime.now(ZoneInfo(timezone))
    return dt.datetime.now().astimezone()


def parse_date_arg(value: str | None, config: dict[str, str]) -> dt.date:
    if value:
        return dt.date.fromisoformat(value)
    return local_now(config).date()


def ymd(date: dt.date) -> str:
    return date.strftime("%Y%m%d")


def week_bounds(date: dt.date) -> tuple[dt.date, dt.date]:
    start = date - dt.timedelta(days=date.weekday())
    return start, start + dt.timedelta(days=6)


def compact_text(text: str, limit: int = 160) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) > limit:
        return text[: limit - 1] + "..."
    return text


def local_date(value: str, config: dict[str, str]) -> dt.date | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ZoneInfo is not None:
        parsed = parsed.astimezone(ZoneInfo(config.get("timezone", "Asia/Shanghai")))
    else:
        parsed = parsed.astimezone()
    return parsed.date()


def extract_input_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"input_text", "output_text"}:
                parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    return ""


def read_thread_names(codex_home: Path) -> dict[str, str]:
    index = codex_home / "session_index.jsonl"
    names: dict[str, str] = {}
    if not index.exists():
        return names
    for line in index.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = payload.get("id")
        if sid:
            names[sid] = payload.get("thread_name") or sid
    return names


def session_files(codex_home: Path, dates: set[dt.date]) -> list[Path]:
    root = codex_home / "sessions"
    if not root.exists():
        return []
    candidates: list[Path] = []
    for date in sorted(dates):
        day_dir = root / f"{date:%Y}" / f"{date:%m}" / f"{date:%d}"
        if day_dir.is_dir():
            candidates.extend(day_dir.glob("*.jsonl"))
    if candidates:
        return sorted(set(candidates))
    return sorted(root.glob("*.jsonl"))


def should_skip_message(text: str) -> bool:
    if not text:
        return True
    if re.match(r"^/[^ ]+\s+\w+\s+\d{4}-\d{2}-\d{2}\s+", text):
        return True
    return False


def should_skip_session(work: SessionWork) -> bool:
    if any(message.startswith("Automation:") for message in work.messages):
        return True
    if work.cwd:
        normalized = work.cwd.replace("\\", "/")
        if "/.codex/plugins/cache/" in normalized or "/.codex/skills/android-knowledge-intake/" in normalized:
            return True
    skip_names = ("日报上传测试", "周报上传测试")
    if any(name in work.thread_name for name in skip_names):
        return True
    return "汇总" in work.thread_name and ("日报" in work.thread_name or "周报" in work.thread_name)


def git_root(path: str) -> Path | None:
    if not path:
        return None
    cp = run(["git", "-C", path, "rev-parse", "--show-toplevel"])
    if cp.returncode != 0:
        return None
    root = cp.stdout.strip()
    return Path(root) if root else None


def git_branch_or_name(path: str) -> str:
    cp = run(["git", "-C", path, "branch", "--show-current"])
    branch = cp.stdout.strip()
    if branch:
        return branch
    root = git_root(path)
    return root.name if root else Path(path).name


def project_name(work: SessionWork) -> str:
    text = " ".join([work.thread_name, work.cwd, *work.messages]).lower()
    if "/documents/codex/" in text or "/.codex/" in text:
        return "全局项目"
    return work.project or "未识别项目"


def parse_sessions(config: dict[str, str], dates: set[dt.date]) -> list[SessionWork]:
    codex_home = expanded_path(config["codex_home"])
    names = read_thread_names(codex_home)
    sessions: list[SessionWork] = []
    for file in session_files(codex_home, dates):
        work = SessionWork()
        for line in file.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if local_date(row.get("timestamp", ""), config) not in dates:
                continue
            payload = row.get("payload") or {}
            if row.get("type") == "session_meta":
                work.session_id = payload.get("id", "") or work.session_id
                work.cwd = payload.get("cwd", "") or work.cwd
                continue
            if row.get("type") != "response_item":
                continue
            if payload.get("type") == "message":
                role = payload.get("role")
                text = compact_text(extract_input_text(payload.get("content")), 220)
                if role == "user" and not should_skip_message(text):
                    work.messages.append(text)
            elif payload.get("type") == "function_call" and payload.get("name") == "exec_command":
                try:
                    args = json.loads(payload.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                cmd = compact_text(str(args.get("cmd", "")), 160)
                if cmd and any(token in cmd for token in ("git ", "apply_patch", ".patch", "build", "test", "adb ")):
                    work.messages.append(f"执行命令: {cmd}")

        if not work.session_id:
            match = re.search(r"([0-9a-f]{8}-[0-9a-f-]{27,})", file.name)
            work.session_id = match.group(1) if match else file.stem
        work.thread_name = names.get(work.session_id, work.session_id)
        if work.cwd and Path(work.cwd).exists():
            work.project = git_branch_or_name(work.cwd)
        if should_skip_session(work) or not work.messages:
            continue
        work.project = project_name(work)
        sessions.append(work)
    return sessions


def synthetic_sessions(config: dict[str, str], dates: set[dt.date]) -> list[SessionWork]:
    rng = random.SystemRandom()
    date_key = ymd(min(dates))
    try:
        count = max(1, min(6, int(config.get("synthetic_item_count", "3"))))
    except ValueError:
        count = 3
    projects = ["TVE8402M", "TVA1001A", "TVI2010M"]
    tasks = [
        "模拟设置项开关需求分析",
        "模拟 SystemUI 状态同步问题排查",
        "模拟 Framework 配置读取链路整理",
        "模拟构建产物推送证据采集",
        "模拟补丁 readme 模板补全",
        "模拟日志开关风险检查",
    ]
    statuses = ["已完成", "进行中", "已完成", "继续排查"]
    sessions: list[SessionWork] = []
    chosen_tasks = rng.sample(tasks, k=min(count, len(tasks)))
    for index, task in enumerate(chosen_tasks, start=1):
        token = uuid.uuid4().hex[:8]
        project = projects[(index - 1) % len(projects)]
        status = rng.choice(statuses)
        sessions.append(
            SessionWork(
                session_id=f"synthetic-{date_key}-{token}",
                thread_name=f"合成测试-{task}",
                cwd="",
                project=project,
                messages=[
                    f"合成测试数据：{task}",
                    f"合成测试进度：{status}",
                    "合成测试说明：该记录不来自真实 Codex 会话或真实源码仓库。",
                ],
            )
        )
    return sessions


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
- reusable: false
- owner: {config["member_name"]} ({config["member_alias"]})
""",
        encoding="utf-8",
    )
    return PatchInfo(path=patch_path, name=patch_name, project=project)


def summarize_session(work: SessionWork) -> str:
    text = " ".join([work.thread_name, *work.messages]).lower()
    if all(keyword in text for keyword in ("codex", "日报")) and any(keyword in text for keyword in ("自动化", "skill", "插件", "知识库")):
        return "搭建 Codex incoming 自动沉淀与知识库提交能力"
    name = work.thread_name.strip()
    if name and not re.fullmatch(r"[0-9a-f-]{20,}", name):
        return compact_text(name, 80)
    messages = [item for item in work.messages if not item.startswith("执行命令:")]
    if messages:
        return compact_text(messages[-1], 80)
    return "处理Codex对话中的开发问题"


def progress_for_session(work: SessionWork, has_patch: bool) -> str:
    text = " ".join([work.thread_name, *work.messages])
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
        maturity = "blocked"
    elif framework_like:
        maturity = "candidate"
    else:
        maturity = "draft"
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
        "maturity": maturity,
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
    patch_projects = {patch.project for patch in patches}
    items: dict[str, list[tuple[str, str]]] = {}
    for session in sessions:
        desc = summarize_session(session)
        progress = progress_for_session(session, session.project in patch_projects)
        entry = (desc, progress)
        if entry not in items.setdefault(session.project, []):
            items[session.project].append(entry)
    for patch in patches:
        if not items.get(patch.project):
            items.setdefault(patch.project, []).append(("产出功能补丁", "已产出 Patch"))
    return items


def overview_text(report_type: str, items: dict[str, list[tuple[str, str]]], patches: list[PatchInfo]) -> str:
    tasks: list[str] = []
    for entries in items.values():
        for desc, _ in entries:
            if desc not in tasks and desc != "产出功能补丁":
                tasks.append(desc)
    if not tasks:
        return "未发现可归档事项，无patch。"
    task_text = "、".join(tasks[:3]) + ("等" if len(tasks) > 3 else "")
    patch_text = f"产出 {len(patches)} 个patch。" if patches else "无patch。"
    prefix = "今天" if report_type == "daily" else "本周"
    return f"{prefix}处理了{task_text}，{patch_text}"


def report_dates(report_type: str, date: dt.date) -> tuple[set[dt.date], dt.date, dt.date, str]:
    if report_type in {"daily", "patch"}:
        return {date}, date, date, ymd(date)
    start, end = week_bounds(date)
    days = {start + dt.timedelta(days=offset) for offset in range((end - start).days + 1)}
    return days, start, end, f"{ymd(start)}-{ymd(end)}"


def write_report(
    package_dir: Path,
    report_type: str,
    date: dt.date,
    week_key: str,
    config: dict[str, str],
    items: dict[str, list[tuple[str, str]]],
    patches: list[PatchInfo],
) -> Path:
    report_path = package_dir / f"{report_type}.md"
    title_key = ymd(date) if report_type == "daily" else week_key
    title = "日报" if report_type == "daily" else "周报"
    overview_heading = "今日概览" if report_type == "daily" else "本周概览"
    patch_heading = "今日产出 Patch" if report_type == "daily" else "本周产出 Patch"
    lines = [f"# {title_key}_{config['member_name']}_{title}", "", f"## {overview_heading}", ""]
    lines.append(overview_text(report_type, items, patches))
    lines += ["", "## 项目事项", ""]
    if not items:
        lines += ["### 未识别项目", "", "  事项: 未发现可归档事项", "  进度: 进行中", ""]
    for project, entries in sorted(items.items()):
        lines += [f"### {project}", ""]
        for desc, progress in entries:
            lines.append(f"  事项: {desc}")
            lines.append(f"  进度: {progress}")
            lines.append("")
    lines += [f"## 附录: {patch_heading}", ""]
    if patches:
        for patch in patches:
            lines.append(f"- {patch.name}")
    else:
        lines.append("无产出 Patch")
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return report_path


def paired_readme(path: Path) -> Path | None:
    candidates = [path.with_suffix(".readme.md"), path.with_suffix(".md"), path.with_suffix(".txt")]
    return next((item for item in candidates if item.is_file()), None)


def patch_readme_template(patch: PatchInfo, config: dict[str, str], status: str = "draft", reusable: bool = False) -> str:
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
- reusable: {str(reusable).lower()}
- owner: {config["member_name"]} ({config["member_alias"]})
"""


def copy_patch_assets(
    package_dir: Path,
    patches: list[PatchInfo],
    config: dict[str, str],
    status: str = "draft",
    reusable: bool = False,
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
            readme_target.write_text(patch_readme_template(patch, config, status, reusable), encoding="utf-8")
            generated_readme = True
        entries.append(
            {
                "path": f"patches/{target.name}",
                "readme": f"patches/{readme_target.name}",
                "content_sha1": sha1_file(target),
                "status": status,
                "reusable": reusable,
                "project": patch.project,
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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], bool, list[str]]:
    patch_dir = package_dir / "patches"
    evidence_dir = package_dir / "knowledge" / "evidence" / "capture"
    patch_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    patch_entries: list[dict[str, Any]] = []
    evidence_entries: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    has_pass_verification = False
    related_report_run_ids: list[str] = []

    for raw in package_paths:
        capture_dir = Path(raw).expanduser().resolve()
        manifest = read_json_file(capture_dir / "manifest.json")
        if manifest.get("package_type") != "framework_patch":
            raise SystemExit(f"不是 android-framework-patch-capture 工作包: {capture_dir}")
        related_report_run_ids.extend(list_string_values(manifest.get("related_report_run_ids")))
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
            readme_rel = str(item.get("readme", ""))
            patch_name = Path(patch_rel).name
            readme_name = Path(readme_rel).name
            if not patch_name or not readme_name:
                raise SystemExit(f"capture package patch/readme 路径无效: {capture_dir}")
            copy_capture_file(capture_dir, patch_rel, patch_dir / patch_name)
            copy_capture_file(capture_dir, readme_rel, patch_dir / readme_name)
            entry_status = item.get("status") or default_status
            copied_patch = patch_dir / patch_name
            patch_entries.append(
                {
                    "path": f"patches/{patch_name}",
                    "readme": f"patches/{readme_name}",
                    "content_sha1": item.get("content_sha1") or sha1_file(copied_patch),
                    "status": entry_status,
                    "reusable": bool(item.get("reusable", entry_status == "validated")),
                    "project": item.get("project") or manifest.get("project") or default_project,
                    "note": "来自 android-framework-patch-capture 工作包",
                    "facts": item.get("facts") if isinstance(item.get("facts"), dict) else {},
                }
            )
            sources.append({"name": patch_name, "source": str(capture_dir / patch_rel), "project": item.get("project") or default_project})

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
                "path": f"knowledge/evidence/capture/{target_name}",
                "result": item.get("result", "INFO"),
                "summary": item.get("summary", "captured patch evidence"),
            }
            evidence_entries.append(copied)
            if verification_payload_passes(capture_dir, item):
                has_pass_verification = True

    return patch_entries, evidence_entries, sources, has_pass_verification, unique_strings(related_report_run_ids)


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


def validate_package(package_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.is_file():
        errors.append("缺少 manifest.json")
        return {"status": "FAIL", "errors": errors, "warnings": warnings}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"manifest.json 解析失败: {exc}")
        return {"status": "FAIL", "errors": errors, "warnings": warnings}

    if manifest.get("schema_version") != INCOMING_SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {INCOMING_SCHEMA_VERSION}")
        return {"status": "FAIL", "errors": errors, "warnings": warnings}
    return validate_incoming_package(package_dir, manifest)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def plugin_commit() -> str:
    cp = run(["git", "-C", str(PLUGIN_ROOT), "rev-parse", "--short", "HEAD"])
    if cp.returncode == 0:
        return cp.stdout.strip()
    return ""


def source_metadata(config: dict[str, str], skill: str) -> dict[str, Any]:
    return {
        "source": "android-framework-ops",
        "tool": skill,
        "skill": skill,
        "skill_version": "",
        "plugin_commit": plugin_commit(),
        "member_alias": config["member_alias"],
        "generated_at": local_now(config).isoformat(),
    }


def write_package_source(package_dir: Path, config: dict[str, str], skill: str) -> dict[str, Any]:
    source = source_metadata(config, skill)
    write_json(package_dir / "knowledge" / "evidence" / "source.json", {"kind": "source", "payload": source})
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
                "knowledge/evidence/source.json",
                "knowledge/evidence/codex_sessions.json",
                "knowledge/evidence/work_findings.json",
            ],
        },
    }
    if report_type == "weekly":
        manifest["week_range"] = week_key
    return manifest


def referenced_paths(manifest: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for section in ("reports", "evidence", "patches"):
        rows = manifest.get(section, [])
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if isinstance(path, str) and path:
                paths.append(path)
            readme = item.get("readme")
            if isinstance(readme, str) and readme:
                paths.append(readme)
    return paths


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


def validate_source(manifest: dict[str, Any], errors: list[str]) -> None:
    source = manifest.get("source")
    if not isinstance(source, dict):
        errors.append("manifest.source 必须是对象")
        return
    tool = source.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        errors.append("manifest.source.tool 必须提供生成工具名")


def validate_asset_identity(manifest: dict[str, Any], errors: list[str]) -> None:
    for section in ("reports", "evidence", "patches"):
        rows = manifest.get(section, [])
        if not isinstance(rows, list):
            continue
        seen_ids: dict[str, int] = {}
        seen_paths: dict[str, int] = {}
        for index, item in enumerate(rows):
            if not isinstance(item, dict):
                continue
            asset_id = str(item.get("id") or "").strip()
            if not asset_id:
                errors.append(f"{section}[{index}].id 不能为空")
            elif asset_id in seen_ids:
                errors.append(f"{section}[{index}].id 与 {section}[{seen_ids[asset_id]}] 重复: {asset_id}")
            else:
                seen_ids[asset_id] = index

            path = str(item.get("path") or "").strip()
            if path and path in seen_paths:
                errors.append(f"{section}[{index}].path 与 {section}[{seen_paths[path]}] 重复: {path}")
            elif path:
                seen_paths[path] = index


def validate_evidence_result(package_dir: Path, item: dict[str, Any], errors: list[str]) -> None:
    result = item.get("result")
    if result not in EVIDENCE_RESULTS:
        errors.append("evidence.result 必须是 PASS、WARN、FAIL、INFO 或 SKIPPED")
        return

    rel = item.get("path")
    if not isinstance(rel, str) or not rel:
        return
    payload = read_referenced_json(package_dir, rel)
    if payload is None or payload.get("result") is None:
        return
    payload_result = payload.get("result")
    if payload_result not in EVIDENCE_RESULTS:
        errors.append(f"{rel} result 必须是 PASS、WARN、FAIL、INFO 或 SKIPPED")
    elif payload_result != result:
        errors.append(f"{rel} result 必须与 manifest.evidence.result 一致")


def validate_verification_evidence(package_dir: Path, item: dict[str, Any], errors: list[str]) -> None:
    if item.get("kind") not in VERIFICATION_EVIDENCE_KINDS or item.get("result") != "PASS":
        return
    rel = item.get("path")
    if not isinstance(rel, str) or not rel:
        return
    payload = read_referenced_json(package_dir, rel)
    if payload is None or payload.get("result") != "PASS":
        return
    method = payload.get("method")
    if method not in {"device", "equivalent"}:
        errors.append(f"{rel} method 必须是 device 或 equivalent")
        return
    if item.get("kind") == "device_verification" and method != "device":
        errors.append(f"{rel} device_verification 必须使用 method=device")
    if item.get("kind") == "equivalent_verification" and method != "equivalent":
        errors.append(f"{rel} equivalent_verification 必须使用 method=equivalent")
    if method == "equivalent" and not (payload.get("reason") and payload.get("coverage") and "remaining_risk" in payload):
        errors.append(f"{rel} 等价验证必须包含 reason、coverage 和 remaining_risk")


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


def explanation_kinds_for_patch(package_dir: Path, manifest: dict[str, Any], patch: dict[str, Any], patch_count: int) -> set[str]:
    kinds: set[str] = set()
    rows = manifest.get("evidence", [])
    if not isinstance(rows, list):
        return kinds
    for item in rows:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind not in REQUIRED_PATCH_EXPLANATION_KINDS:
            continue
        rel = item.get("path")
        payload = read_referenced_json(package_dir, rel) if isinstance(rel, str) else None
        if evidence_covers_patch(item, payload, patch, patch_count):
            kinds.add(str(kind))
    return kinds


def relation_value(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        if key not in item:
            continue
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def relation_endpoint_index(manifest: dict[str, Any], errors: list[str]) -> dict[str, str]:
    endpoints: dict[str, tuple[str, str]] = {}
    duplicate_refs: set[str] = set()

    def add_ref(raw: Any, item_type: str, asset_key: str) -> None:
        text = str(raw or "").strip()
        if not text:
            return
        existing = endpoints.get(text)
        if existing and existing != (item_type, asset_key):
            duplicate_refs.add(text)
            return
        endpoints[text] = (item_type, asset_key)

    for section, item_type in (("reports", "report"), ("evidence", "evidence"), ("patches", "patch")):
        rows = manifest.get(section, [])
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            asset_key = str(item.get("path") or item.get("id") or "")
            add_ref(item.get("id"), item_type, asset_key)
            add_ref(item.get("path"), item_type, asset_key)

    for ref in sorted(duplicate_refs):
        errors.append(f"relation endpoint 存在歧义: {ref}")
        endpoints.pop(ref, None)
    return {key: value[0] for key, value in endpoints.items()}


def validate_relations(manifest: dict[str, Any], errors: list[str]) -> None:
    rows = manifest.get("relations", [])
    if not isinstance(rows, list):
        errors.append("relations 必须是数组")
        return

    endpoints = relation_endpoint_index(manifest, errors)
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            errors.append(f"relations[{index}] 必须是对象")
            continue
        source = relation_value(item, ("from", "source", "source_id"))
        target = relation_value(item, ("to", "target", "target_id"))
        relation = relation_value(item, ("type", "relation"))
        if not source or not target or not relation:
            errors.append(f"relations[{index}] 必须提供 from、to 和 type")
            continue
        if relation not in RELATION_TYPES:
            errors.append(f"relations[{index}].type 非法: {relation}")
        if source not in endpoints:
            errors.append(f"relations[{index}].from 找不到对应资产: {source}")
        if target not in endpoints:
            errors.append(f"relations[{index}].to 找不到对应资产: {target}")
        if "confidence" in item:
            confidence = relation_value(item, ("confidence",))
            if not confidence or confidence not in EVIDENCE_CONFIDENCE_VALUES:
                errors.append(f"relations[{index}].confidence 必须是 low、medium 或 high")


def patch_diff_modified_files(package_dir: Path, rel: str) -> list[str]:
    try:
        path = reference_path(package_dir, rel)
    except ValueError:
        return []
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    files: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"^\+\+\+\s+(.+)$", text, re.M):
        value = match.group(1).strip()
        if value == "/dev/null":
            continue
        if value.startswith("b/"):
            value = value[2:]
        if value and value not in seen:
            seen.add(value)
            files.append(value)
    return files


def validate_explanation_evidence(package_dir: Path, item: dict[str, Any], errors: list[str]) -> None:
    rel = item.get("path")
    if not isinstance(rel, str) or not rel:
        errors.append("补丁解释 evidence 必须引用 JSON 文件")
        return
    payload = read_referenced_json(package_dir, rel)
    if payload is None:
        return
    confidence = payload.get("confidence")
    basis = payload.get("basis")
    limits = payload.get("limits")
    if confidence not in EVIDENCE_CONFIDENCE_VALUES:
        errors.append(f"{rel} confidence 必须是 low、medium 或 high")
    if not isinstance(basis, list) or not basis:
        errors.append(f"{rel} basis 必须是非空数组")
    if not isinstance(limits, list) or not limits:
        errors.append(f"{rel} limits 必须是非空数组")
    if item.get("kind") == "patch_problem_summary":
        if not payload.get("problem_summary") or not payload.get("solution_summary"):
            errors.append(f"{rel} 必须包含 problem_summary 和 solution_summary")
    if item.get("kind") == "risk_surface":
        risk_areas = payload.get("risk_areas")
        if not isinstance(risk_areas, list) or not risk_areas:
            errors.append(f"{rel} risk_areas 必须是非空数组")


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
    package_kind = manifest.get("package_kind")
    if package_kind not in INCOMING_KINDS:
        errors.append(f"package_kind 非法: {package_kind}")

    if package_kind in {"daily_trace", "weekly_trace"}:
        report_type = "daily" if package_kind == "daily_trace" else "weekly"
        if manifest.get("report_type") != report_type:
            errors.append(f"{package_kind} report_type 必须是 {report_type}")
        report_path = manifest.get("report_path")
        require_file(report_path, "report_path")
        if "case_id" in manifest or "variant_id" in manifest:
            errors.append("report trace 不能携带 case_id 或 variant_id")
        if package_kind == "weekly_trace" and not manifest.get("week_range"):
            errors.append("weekly_trace 必须提供 week_range")
        files = manifest.get("files")
        if not isinstance(files, dict):
            errors.append("report trace files 必须是对象")
            files = {}
        evidence_paths = files.get("evidence", [])
        if not isinstance(evidence_paths, list) or not evidence_paths:
            errors.append("report trace files.evidence 必须是非空数组")
            evidence_paths = []
        evidence_by_kind = load_evidence(evidence_paths)
        for kind in TRACE_REQUIRED_EVIDENCE_KINDS:
            if kind not in evidence_by_kind:
                errors.append(f"report trace 缺少 {kind} evidence")
        work_findings = evidence_by_kind.get("work_findings", {})
        payload = work_findings.get("payload", {}) if isinstance(work_findings, dict) else {}
        if not isinstance(payload.get("scanned_sources"), list) or not payload.get("scanned_sources"):
            errors.append("work_findings.scanned_sources 必须是非空数组")
        if not isinstance(payload.get("items", []), list):
            errors.append("work_findings.items 必须是数组")
        for item in payload.get("items", []) if isinstance(payload.get("items", []), list) else []:
            maturity = item.get("maturity")
            if maturity and maturity not in MATURITY_VALUES:
                errors.append(f"work_findings item maturity 非法: {maturity}")

    if package_kind == "framework_change":
        for field in ("case_id", "variant_id", "maturity", "platform", "android_version", "project"):
            if not manifest.get(field):
                errors.append(f"framework_change 缺少 {field}")
        maturity = str(manifest.get("maturity", ""))
        if maturity not in MATURITY_VALUES:
            errors.append(f"maturity 非法: {maturity}")
        if "related_report_run_ids" in manifest:
            related = manifest.get("related_report_run_ids")
            if not isinstance(related, list):
                errors.append("related_report_run_ids 必须是数组")
            else:
                for item in related:
                    if not RUN_ID_RE.fullmatch(str(item or "")):
                        errors.append(f"related_report_run_ids 包含非法 run_id: {item}")
        files = manifest.get("files")
        if not isinstance(files, dict):
            errors.append("framework_change files 必须是对象")
            files = {}
        case_path = require_file(files.get("case"), "files.case")
        variant_path = require_file(files.get("variant"), "files.variant")
        patch_paths = files.get("patches", [])
        evidence_paths = files.get("evidence", [])
        if not isinstance(patch_paths, list) or not patch_paths:
            errors.append("files.patches 必须是非空数组")
            patch_paths = []
        if not isinstance(evidence_paths, list) or not evidence_paths:
            errors.append("files.evidence 必须是非空数组")
            evidence_paths = []
        for patch_path in patch_paths:
            path = require_file(patch_path, "patch")
            if path and path.suffix not in {".patch", ".diff"}:
                errors.append(f"patch 文件必须是 .patch 或 .diff: {patch_path}")
            if path:
                readme = paired_readme(path)
                if not readme:
                    errors.append(f"{path.name} 缺少配套 readme")
                else:
                    errors.extend(validate_patch_readme(readme))
        if case_path:
            case = read_json_file(case_path)
            if case.get("case_id") != manifest.get("case_id"):
                errors.append("case_id 不一致")
            for field in ("title", "problem", "solution_summary"):
                if not case.get(field):
                    errors.append(f"case 缺少 {field}")
        if variant_path:
            variant = read_json_file(variant_path)
            if variant.get("variant_id") != manifest.get("variant_id"):
                errors.append("variant_id 不一致")
            if variant.get("status") != maturity:
                errors.append("variant.status 必须等于 manifest.maturity")
            for field in ("platform", "android_version", "project", "repo_paths"):
                if not variant.get(field):
                    errors.append(f"variant 缺少 {field}")
        evidence_by_kind = load_evidence(evidence_paths)
        for rel in evidence_paths:
            if not isinstance(rel, str):
                continue
            evidence = read_referenced_json(package_dir, rel)
            if not isinstance(evidence, dict):
                continue
            if evidence.get("kind") == LEGACY_PATCH_PROBLEM_KIND:
                errors.append(f"{rel} 使用了旧补丁问题证据类型；请改用 patch_problem_summary")
            if evidence.get("case_id") != manifest.get("case_id"):
                errors.append(f"{rel} evidence.case_id 必须等于 manifest.case_id")
            if evidence.get("variant_id") != manifest.get("variant_id"):
                errors.append(f"{rel} evidence.variant_id 必须等于 manifest.variant_id")
            if evidence.get("kind") == "patch_problem_summary":
                payload = evidence
                if "payload" in payload:
                    errors.append(f"{rel} 必须直接使用顶层字段，不能再包一层 payload")
                if not payload.get("problem_summary") or not payload.get("solution_summary"):
                    errors.append(f"{rel} 必须包含 problem_summary 和 solution_summary")
                if not isinstance(payload.get("basis"), list) or not payload.get("basis"):
                    errors.append(f"{rel} basis 必须是非空数组")
                if not isinstance(payload.get("limits"), list):
                    errors.append(f"{rel} limits 必须是数组")
        for kind in FRAMEWORK_REQUIRED_EVIDENCE_KINDS:
            if kind not in evidence_by_kind:
                errors.append(f"framework_change 缺少 {kind} evidence")
        verification = evidence_by_kind.get("verification_result", {})
        verification_payload = verification.get("payload", verification) if isinstance(verification, dict) else {}
        result = str(verification_payload.get("result", "")).upper()
        if result not in {"PASS", "FAIL", "MISSING"}:
            errors.append("verification_result.result 必须是 PASS、FAIL 或 MISSING")
        if not verification_payload.get("method"):
            errors.append("verification_result.method 必须提供")
        if maturity == "validated" and result != "PASS":
            errors.append("validated 必须提供 PASS 验证")
        if maturity == "failed" and result != "FAIL":
            errors.append("failed 必须提供 FAIL 验证")
    return {"status": "FAIL" if errors else "PASS", "errors": errors, "warnings": warnings}


def has_pass_verification(package_dir: Path, manifest: dict[str, Any]) -> bool:
    evidence = manifest.get("evidence", [])
    if not isinstance(evidence, list):
        return False
    for item in evidence:
        if not isinstance(item, dict):
            continue
        if item.get("kind") not in {"verification_result", "device_verification", "equivalent_verification"}:
            continue
        if item.get("result") != "PASS":
            continue
        rel = item.get("path")
        if not isinstance(rel, str) or not rel:
            continue
        path = (package_dir / rel).resolve()
        root = package_dir.resolve()
        if path != root and root not in path.parents:
            continue
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict) or payload.get("result") != "PASS":
            continue
        if payload.get("method") == "device":
            return True
        if payload.get("method") == "equivalent" and payload.get("reason") and payload.get("coverage") and "remaining_risk" in payload:
            return True
    return False


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


def patch_modules_from_files(files: list[str]) -> list[str]:
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
        if "frameworks/base/core/res/" in lower:
            modules.append("FrameworkResources")
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
        parts = files[0].split("/")
        modules.append("-".join(parts[:2]) if len(parts) >= 2 else parts[0])
    return sorted(set(modules))


def patch_semantic_flags(joined: str, modules: list[str]) -> dict[str, bool]:
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


def patch_semantic_keywords(flags: dict[str, bool]) -> list[str]:
    labels = {
        "audio": "音频路由/音量",
        "camera": "相机行为",
        "storage": "存储/挂载",
        "wifi": "Wi-Fi",
        "usb": "USB/设备权限",
        "product_config": "产品配置/预置应用",
    }
    return [label for flag, label in labels.items() if flags.get(flag)]


def patch_semantic_problem_solution(modules: list[str], flags: dict[str, bool]) -> tuple[str, str, str]:
    if flags["focus"] and any(module in modules for module in ("WindowManager", "ActivityTaskManager")):
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


def patch_semantic_risk_areas(modules: list[str], flags: dict[str, bool]) -> list[str]:
    risks = sorted(
        {
            *("窗口焦点/显示层级" for _ in [0] if flags["focus"] or "WindowManager" in modules),
            *("Activity 启动/恢复" for _ in [0] if "ActivityTaskManager" in modules),
            *("按键/电源/策略行为" for _ in [0] if flags["power"]),
            *("包安装/包状态" for _ in [0] if "PackageManager" in modules),
            *("资源覆盖/配置优先级" for _ in [0] if "FrameworkResources" in modules),
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
    return {
        "modified_files": files,
        "symbols": patch_symbols_from_text(text),
        "system_properties": sorted(set(re.findall(r"\b(?:persist|ro|sys|debug|vendor)\.[A-Za-z0-9_.-]+", text))),
        "settings_keys": sorted(set(re.findall(r"Settings\.(?:System|Secure|Global)\.([A-Za-z0-9_.-]+)", text))),
        "resource_keys": sorted(set([*re.findall(r"R\.string\.([A-Za-z0-9_]+)", text), *re.findall(r"@string/([A-Za-z0-9_]+)", text)])),
        "framework_log_keys": sorted(set(re.findall(r"FrameworkLog\.([A-Za-z0-9_]+)", text))),
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
    return (
        {
            "kind": "patch_problem_summary",
            "patch_id": patch_id,
            "source_patch": source_patch,
            "confidence": confidence,
            "problem_summary": problem,
            "solution_summary": solution,
            "keywords": keywords,
            "basis": basis,
            "limits": limits,
        },
        {
            "kind": "risk_surface",
            "patch_id": patch_id,
            "source_patch": source_patch,
            "confidence": confidence,
            "risk_areas": risks,
            "basis": basis,
            "limits": limits,
        },
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
    evidence_dir = package_dir / "knowledge" / "evidence"
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
                    "path": f"knowledge/evidence/{diff_facts_path.name}",
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
                    "path": f"knowledge/evidence/{problem_path.name}",
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
                    "path": f"knowledge/evidence/{risk_path.name}",
                    "result": "INFO",
                    "summary": "member-side patch risk surface",
                }
            )


def incoming_patch_item(package_dir: Path, patch_entry: dict[str, Any]) -> dict[str, Any]:
    patch_path = package_dir / str(patch_entry["path"])
    captured_facts = patch_entry.get("facts") if isinstance(patch_entry.get("facts"), dict) else {}
    content_sha1 = str(patch_entry.get("content_sha1") or sha1_file(patch_path))
    facts = {
        "content_sha1": content_sha1,
        "modified_files": captured_facts.get("modified_files") or patch_modified_files(patch_path),
        "modules": captured_facts.get("modules") or [],
        "symbols": captured_facts.get("symbols") or [],
        "system_properties": captured_facts.get("system_properties") or [],
        "settings_keys": captured_facts.get("settings_keys") or [],
        "resource_keys": captured_facts.get("resource_keys") or [],
        "framework_log_keys": captured_facts.get("framework_log_keys") or [],
    }
    reusable = patch_entry.get("reusable", False)
    return {
        "id": Path(str(patch_entry["path"])).stem,
        "path": patch_entry["path"],
        "readme": patch_entry.get("readme", ""),
        "content_sha1": content_sha1,
        "status": patch_entry.get("status", "candidate"),
        "reusable": reusable if isinstance(reusable, bool) else reusable,
        "repo_path": "",
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
    for item in patch_items:
        facts = item.get("facts", {}) if isinstance(item.get("facts"), dict) else {}
        content_sha1 = str(item.get("content_sha1") or facts.get("content_sha1") or "")
        if content_sha1:
            content_hashes.append(content_sha1)
        for key in aggregate:
            aggregate[key].extend(list_string_values(facts.get(key)))
        patches.append(
            {
                "id": item.get("id", ""),
                "path": item.get("path", ""),
                "readme": item.get("readme", ""),
                "content_sha1": content_sha1,
                "status": item.get("status", "candidate"),
                "modified_files": list_string_values(facts.get("modified_files")),
                "modules": list_string_values(facts.get("modules")),
            }
        )
    payload: dict[str, Any] = {
        "patch_count": len(patch_items),
        "patches": patches,
        "content_sha1": content_hashes[0] if len(content_hashes) == 1 else "",
    }
    payload.update({key: unique_strings(values) for key, values in aggregate.items()})
    return payload


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
        if item.get("maturity") == "blocked":
            blocked_or_failed.append(
                {
                    "title": title,
                    "maturity": "blocked",
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
                "maturity": "candidate",
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


def prepare_package(report_type: str, date: dt.date, config: dict[str, str], run_id: str | None = None, schema_version: str = INCOMING_SCHEMA_VERSION) -> Path:
    require_config(config)
    if schema_version != INCOMING_SCHEMA_VERSION:
        raise SystemExit(f"incoming 只支持 schema_version={INCOMING_SCHEMA_VERSION}")
    dates, start, end, week_key = report_dates(report_type, date)
    run_id = run_id or f"{ymd(date)}-{local_now(config):%H%M%S}"
    out_dir = expanded_path(config["out_dir"])
    package_dir = out_dir / "pending" / ymd(date) / config["member_alias"] / run_id
    if package_dir.exists():
        raise SystemExit(f"工作包已存在: {package_dir}")
    package_dir.mkdir(parents=True)

    if synthetic_mode(config):
        sessions = synthetic_sessions(config, dates)
        patches = []
    else:
        sessions = parse_sessions(config, dates)
        patches = discover_patches(config, sessions, start, end)
    items = items_by_project(sessions, patches)
    write_report(package_dir, report_type, date, week_key, config, items, patches)
    summary = overview_text(report_type, items, patches)

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
    write_json(package_dir / "knowledge" / "evidence" / "codex_sessions.json", {"kind": "codex_sessions", "payload": evidence})
    write_json(package_dir / "knowledge" / "evidence" / "work_findings.json", {"kind": "work_findings", "payload": work_findings_payload(sessions, patches)})
    reports_dir = package_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(package_dir / f"{report_type}.md"), reports_dir / f"{report_type}.md")
    source = write_package_source(package_dir, config, "android-knowledge-intake")
    manifest = incoming_report_manifest(report_type, date, week_key, config, summary, source, run_id)
    write_json(package_dir / "manifest.json", manifest)
    check = validate_package(package_dir)
    write_json(package_dir / "local-check.json", check)
    return package_dir


def parse_platform_token(patch_entries: list[dict[str, Any]]) -> tuple[str, str]:
    if not patch_entries:
        return "unknown", "unknown"
    name = Path(str(patch_entries[0].get("path", ""))).name.lower()
    match = re.match(r"^([a-z]+)(\d{1,2})-", name)
    if not match:
        return "unknown", "unknown"
    platform = "unisoc" if match.group(1) == "sprd" else match.group(1)
    version = match.group(2)
    if platform == "rk" and version in {"71", "90"}:
        version = {"71": "7.1", "90": "9.0"}[version]
    return platform, version


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


def parse_company_project(value: str) -> dict[str, Any]:
    base = value[:8]
    return {
        "base_model": base,
        "product_prefix": base[:2],
        "form_code": base[2],
        "mold_code": base[3:7],
        "soc_code": base[7],
        "suffix": value[8:].lstrip("_"),
        "recognition_scope": "TVE/TVA/TVI",
        "company_rule_match": bool(re.fullmatch(r"TV[EAI][A-Z0-9]{5}", base)),
    }


def find_company_project(text: str) -> str:
    match = PROJECT_MODEL_RE.search(text.upper())
    return match.group(0) if match else ""


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
) -> tuple[str, dict[str, Any]]:
    clues: list[tuple[str, str]] = []
    if explicit_project and explicit_project.strip() != "unknown":
        clues.append(("命令参数 project", explicit_project.strip()))
    for item in patch_entries:
        for key, label in (("project", "capture package project"), ("path", "补丁路径"), ("readme", "补丁说明路径")):
            value = item.get(key)
            if isinstance(value, str) and value:
                clues.append((label, value))
            if package_dir and key in {"path", "readme"} and isinstance(value, str) and value:
                sample = read_text_sample(package_dir / value)
                if sample:
                    clues.append((label.replace("路径", "内容"), sample))
    for item in patch_sources:
        for key, label in (("project", "补丁来源 project"), ("name", "补丁名称"), ("source", "补丁来源路径")):
            value = item.get(key)
            if isinstance(value, str) and value:
                clues.append((label, value))
    if summary:
        clues.append(("补丁摘要", summary))

    checked_sources = sorted(dict.fromkeys(label for label, _ in clues))
    raw_inputs = [f"{label}: {value}" for label, value in clues]
    for label, value in clues:
        project = find_company_project(value)
        if project:
            return project, project_inference_payload(project, [f"{label}: {value}"], checked_sources, raw_inputs)

    limits = ["未从命令参数、capture package、补丁名称、补丁路径或补丁摘要中识别到 TVE/TVA/TVI 项目型号"]
    if explicit_project and explicit_project.strip() not in {"", "unknown"}:
        limits.append("命令参数 project 未匹配公司项目型号规范，未作为项目名入库")
    return "unknown", project_inference_payload("unknown", [], checked_sources, raw_inputs, limits)


def write_default_evidence(package_dir: Path, rel: str, payload: dict[str, Any]) -> str:
    write_json(package_dir / rel, payload)
    return rel


def framework_maturity_from_patch_statuses(statuses: set[str], has_pass_verification: bool) -> str:
    clean = {item for item in statuses if item in MATURITY_VALUES}
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
) -> Path:
    require_config(config)
    if schema_version != INCOMING_SCHEMA_VERSION:
        raise SystemExit(f"incoming 只支持 schema_version={INCOMING_SCHEMA_VERSION}")
    run_id = run_id or f"{ymd(date)}-{local_now(config):%H%M%S}-patch"
    out_dir = expanded_path(config["out_dir"])
    package_dir = out_dir / "pending" / ymd(date) / config["member_alias"] / run_id
    if package_dir.exists():
        raise SystemExit(f"工作包已存在: {package_dir}")
    package_dir.mkdir(parents=True)

    patch_entries: list[dict[str, Any]] = []
    capture_evidence_entries: list[dict[str, Any]] = []
    patch_sources: list[dict[str, Any]] = []
    has_pass_verification = False
    all_related_report_run_ids = list_string_values(related_report_run_ids)

    if patch_package_paths:
        capture_entries, evidence_entries, source_entries, capture_has_pass, capture_related_report_run_ids = copy_patch_capture_packages(
            package_dir,
            patch_package_paths,
            project,
            status,
        )
        patch_entries.extend(capture_entries)
        capture_evidence_entries.extend(evidence_entries)
        patch_sources.extend(source_entries)
        has_pass_verification = has_pass_verification or capture_has_pass
        all_related_report_run_ids.extend(capture_related_report_run_ids)

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
        patch_entries.extend(copy_patch_assets(package_dir, patches, config, status=status, reusable=status == "validated", note="管理员手动归档补丁"))
        patch_sources.extend([{"name": item.name, "source": str(item.path), "project": item.project} for item in patches])
    write_json(
        package_dir / "knowledge" / "evidence" / "framework_change_summary.json",
        {
            "source": "android-knowledge-intake",
            "mode": "patch",
            "synthetic_data": synthetic_mode(config),
            "patch_count": len(patch_entries),
            "patches": patch_sources,
            "capture_package_count": len(patch_package_paths or []),
        },
    )
    ensure_patch_analysis_evidence(package_dir, patch_entries, capture_evidence_entries, summary)
    if not has_pass_verification:
        for item in patch_entries:
            if item.get("status") == "validated":
                item["status"] = "candidate"
                item["reusable"] = False
                item["note"] = "未携带 PASS 设备验证或合格等价验证，已按 candidate 提交"
    for item in patch_entries:
        if item.get("status") in {"failed", "blocked"}:
            item["reusable"] = False
    statuses = {str(item.get("status", "")) for item in patch_entries}
    source = write_package_source(package_dir, config, "android-knowledge-intake")
    maturity = framework_maturity_from_patch_statuses(statuses, has_pass_verification)

    platform, android_version = parse_platform_token(patch_entries)
    project, project_payload = infer_project(project, patch_entries, patch_sources, summary, package_dir)
    all_patch_items = [incoming_patch_item(package_dir, item) for item in patch_entries]
    modified_files = sorted(
        {
            file
            for item in all_patch_items
            for file in item.get("facts", {}).get("modified_files", [])
            if isinstance(file, str) and file
        }
    )
    repo_paths = repo_paths_from_files(modified_files)
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

    case_path = "knowledge/case.json"
    variant_path = "knowledge/variant.json"
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
            "status": maturity,
        },
    )

    source_path = "knowledge/evidence/source.json"
    project_path = write_default_evidence(
        package_dir,
        "knowledge/evidence/project_inference.json",
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
            "summary": "未携带设备或等价验证证据，按非 validated 成熟度入库。",
        }
    verification_path = write_default_evidence(
        package_dir,
        "knowledge/evidence/verification_result.json",
        {
            "kind": "verification_result",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": verification_payload,
        },
    )
    if maturity == "validated" and str(verification_payload.get("result", "")).upper() != "PASS":
        maturity = "candidate"

    search_payload = first_evidence_payload(package_dir, capture_evidence_entries, "search_before_change")
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
        "knowledge/evidence/search_before_change.json",
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

    patch_diff_path = write_default_evidence(
        package_dir,
        "knowledge/evidence/patch_diff_facts.json",
        {
            "kind": "patch_diff_facts",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": aggregate_patch_diff_facts(all_patch_items),
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
            fallback = f"knowledge/evidence/{kind}.json"
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
            "status": maturity,
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
        "maturity": maturity,
        "platform": platform,
        "android_version": android_version,
        "project": project,
        "summary": summary,
        "files": {
            "case": case_path,
            "variant": variant_path,
            "patches": patch_rel_paths,
            "evidence": [
                source_path,
                required_generated["patch_diff_facts"],
                project_path,
                required_generated["patch_problem_summary"],
                required_generated["risk_surface"],
                verification_path,
                search_path,
                *optional_evidence_paths,
            ],
        },
    }
    if all_related_report_run_ids:
        manifest["related_report_run_ids"] = all_related_report_run_ids
    for evidence_rel in manifest["files"]["evidence"]:
        bind_framework_evidence(package_dir, evidence_rel, case_id, variant_id)
    write_json(package_dir / "manifest.json", manifest)
    check = validate_package(package_dir)
    write_json(package_dir / "local-check.json", check)
    return package_dir


def git_run(repo: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    cp = run(["git", "-C", str(repo), *args])
    if check and cp.returncode != 0:
        detail = cp.stderr.strip() or cp.stdout.strip()
        raise SystemExit(f"git {' '.join(args)} 失败: {detail}")
    return cp


def ensure_repo(config: dict[str, str]) -> Path:
    repo = expanded_path(config["repo_worktree"])
    repo_url = config["repo_url"].strip()
    if not repo_url:
        raise SystemExit("repo_url 不能为空")
    if not (repo / ".git").exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        cp = run(["git", "clone", repo_url, str(repo)])
        if cp.returncode != 0:
            raise SystemExit(f"clone knowledge 仓库失败: {cp.stderr.strip() or cp.stdout.strip()}")
    git_run(repo, ["remote", "set-url", "origin", repo_url])
    name = config.get("git_user_name") or config.get("member_name") or config.get("member_alias")
    email = config.get("git_user_email") or f"{config.get('member_alias', 'codex')}@codex.local"
    git_run(repo, ["config", "user.name", name])
    git_run(repo, ["config", "user.email", email])
    return repo


def default_branch(repo: Path) -> str:
    git_run(repo, ["fetch", "origin"])
    cp = git_run(repo, ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], check=False)
    value = cp.stdout.strip()
    if value.startswith("origin/"):
        return value.split("/", 1)[1]
    for branch in ("master", "main"):
        if git_run(repo, ["rev-parse", "--verify", f"origin/{branch}"], check=False).returncode == 0:
            return branch
    return "master"


def pull_rebase(repo: Path, branch: str) -> None:
    git_run(repo, ["pull", "--rebase", "origin", branch])


def outgoing_paths(repo: Path, branch: str) -> list[str]:
    cp = git_run(repo, ["diff", "--name-only", f"origin/{branch}..HEAD"], check=False)
    if cp.returncode != 0:
        return []
    return [line.strip() for line in cp.stdout.splitlines() if line.strip()]


def non_incoming_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if not (path == "incoming" or path.startswith("incoming/"))]


def ensure_outgoing_only_incoming(repo: Path, branch: str, config: dict[str, str]) -> None:
    if config.get("role") == "admin":
        return
    paths = outgoing_paths(repo, branch)
    bad = non_incoming_paths(paths)
    if bad:
        preview = "\n".join(f"- {path}" for path in bad[:20])
        extra = f"\n... 另有 {len(bad) - 20} 个路径" if len(bad) > 20 else ""
        raise SystemExit(
            "本地待 push 提交包含非 incoming 路径，已停止提交。成员端只能上传 incoming 包；"
            "cases/variants/patches/reports/evidence/events/index/site/docs/scripts 等只能由服务器或管理员维护。\n"
            + preview
            + extra
        )


def copy_package_to_repo(package_dir: Path, repo: Path) -> Path:
    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    date_key = str(manifest["date"]).replace("-", "")
    member = str(manifest["member_alias"])
    run_id = package_dir.name
    target = repo / "incoming" / date_key / member / run_id
    if target.exists():
        raise SystemExit(f"远端工作区已存在同名工作包，避免覆盖: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(package_dir, target)
    return target


def git_submit_package(package_dir: Path, config: dict[str, str]) -> dict[str, Any]:
    check = validate_package(package_dir)
    write_json(package_dir / "local-check.json", check)
    if check["status"] != "PASS":
        raise SystemExit("本地工作包校验失败，已停止提交。请查看 local-check.json。")

    repo = ensure_repo(config)
    branch = default_branch(repo)
    pull_rebase(repo, branch)
    target = copy_package_to_repo(package_dir, repo)
    rel = target.relative_to(repo).as_posix()
    git_run(repo, ["add", rel])
    status = git_run(repo, ["status", "--short", "--", rel]).stdout.strip()
    if not status:
        return {"committed": False, "pushed": False, "message": "no changes", "repo": str(repo), "path": rel}

    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_type = manifest.get("package_kind", "incoming")
    msg = f"incoming({manifest_type}): {manifest['member_alias']} {manifest['date']}"
    cp = git_run(repo, ["commit", "-m", msg], check=False)
    if cp.returncode != 0 and "nothing to commit" not in (cp.stdout + cp.stderr):
        raise SystemExit(f"git commit 失败: {cp.stderr.strip() or cp.stdout.strip()}")

    retries = max(1, int(config.get("push_retries", "3")))
    last_error = ""
    for _ in range(retries):
        ensure_outgoing_only_incoming(repo, branch, config)
        push = git_run(repo, ["push", "origin", branch], check=False)
        if push.returncode == 0:
            commit = git_run(repo, ["rev-parse", "--short", "HEAD"]).stdout.strip()
            return {"committed": True, "pushed": True, "commit": commit, "repo": str(repo), "path": rel}
        last_error = push.stderr.strip() or push.stdout.strip()
        pull_rebase(repo, branch)
    raise SystemExit(f"git push 失败: {last_error}")


def latest_pending(report_type: str, config: dict[str, str], date: dt.date | None = None) -> Path:
    out_dir = expanded_path(config["out_dir"]) / "pending"
    candidates: list[Path] = []
    for manifest_path in out_dir.glob(f"*/*/*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        kind = str(manifest.get("package_kind", ""))
        manifest_type = "daily" if kind == "daily_trace" else "weekly" if kind == "weekly_trace" else "patch" if kind == "framework_change" else ""
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
    repo_url = config.get("repo_url", "").strip()
    repo = expanded_path(config.get("repo_worktree", ""))
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

    if synthetic_mode(config) and not allow_synthetic:
        error("synthetic_data=true 只能用于协议/灰度测试，成员端正式自动化必须关闭。")

    if not repo_url:
        error("repo_url 不能为空。")
    if ".codex/plugins/cache" in repo.as_posix():
        error("repo_worktree 不能放在插件缓存目录下。")
    if ".codex/plugins/cache" in out_dir.as_posix():
        error("out_dir 不能放在插件缓存目录下。")

    git_version = run(["git", "--version"])
    if git_version.returncode != 0:
        error("找不到 git，无法提交 incoming。")

    if (repo / ".git").exists():
        origin = git_run(repo, ["config", "--get", "remote.origin.url"], check=False)
        origin_url = origin.stdout.strip()
        if not origin_url:
            error(f"repo_worktree 缺少 origin remote: {repo}")
        elif repo_url and origin_url != repo_url:
            error(f"repo_worktree origin 与 repo_url 不一致: origin={origin_url}, repo_url={repo_url}")
        dirty = git_run(repo, ["status", "--porcelain"], check=False)
        if dirty.returncode == 0 and dirty.stdout.strip():
            error(f"repo_worktree 存在未提交改动，自动化提交前必须清理: {repo}")
        if role == "member":
            branch = git_run(repo, ["rev-parse", "--abbrev-ref", "HEAD"], check=False)
            fetch = git_run(repo, ["fetch", "origin"], check=False)
            if branch.returncode == 0 and fetch.returncode == 0:
                branch_name = branch.stdout.strip()
                bad_paths = non_incoming_paths(outgoing_paths(repo, branch_name))
                if bad_paths:
                    error("member profile 存在待 push 的非 incoming 提交路径: " + ", ".join(bad_paths[:10]))
            else:
                warn("无法检查待 push 路径；提交时仍会强制限制 member profile 只能 push incoming/**。")
    elif repo.exists():
        error(f"repo_worktree 已存在但不是 Git 仓库: {repo}")
    else:
        parent = nearest_existing_parent(repo.parent)
        if not os.access(parent, os.W_OK):
            error(f"repo_worktree 父目录不可写，无法自动 clone: {parent}")

    out_parent = nearest_existing_parent(out_dir.parent)
    if not os.access(out_parent, os.W_OK):
        error(f"out_dir 父目录不可写，无法生成 pending 包: {out_parent}")

    if check_remote and repo_url:
        remote = run(["git", "ls-remote", "--heads", repo_url])
        if remote.returncode != 0:
            error("repo_url 无法访问，请先配置 SSH/Git 权限: " + (remote.stderr.strip() or remote.stdout.strip()))

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
) -> dict[str, Any]:
    repo = expanded_path(config["repo_worktree"])
    payload: dict[str, Any] = {
        "skill_root": str(PLUGIN_ROOT),
        "codex_home": default_codex_home(),
        "loaded_config": [str(path) for path in loaded],
        "profile": config.get("profile"),
        "role": config.get("role"),
        "allowed_modes": sorted(allowed_modes(config)),
        "synthetic_data": synthetic_mode(config),
        "member_alias": config.get("member_alias"),
        "member_name": config.get("member_name"),
        "repo_url": config.get("repo_url"),
        "repo_worktree": str(repo),
        "repo_cloned": (repo / ".git").exists(),
        "out_dir": str(expanded_path(config["out_dir"])),
        "git": run(["git", "--version"]).stdout.strip(),
    }
    if strict:
        payload["strict"] = doctor_strict_checks(config, loaded, check_remote, allow_synthetic)
        payload["status"] = payload["strict"]["status"]
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and submit Codex team knowledge incoming packages.")
    parser.add_argument("--profile", help="profile name from config, for example admin_alias or member_alias")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--strict", action="store_true", help="fail when the selected profile is unsafe for member-side automation")
    doctor_parser.add_argument("--check-remote", action="store_true", help="also verify repo_url is reachable with git ls-remote")
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
            sub.add_argument("--summary", default="Framework 修改沉淀", help="summary for framework_change incoming")
            sub.add_argument("--related-report-run-id", dest="related_report_run_ids", action="append", default=[], help="daily/weekly incoming run_id related to this framework_change; repeatable")
            sub.add_argument(
                "--status",
                choices=["draft", "candidate", "validated", "failed", "blocked"],
                default="validated",
                help="patch maturity status",
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
            package_dir = prepare_patch_package(date, config, args.run_id, args.patches, args.patch_packages, args.project, args.summary, args.status, schema_version, args.related_report_run_ids)
        else:
            package_dir = prepare_package(args.report_type, date, config, args.run_id, schema_version)
        result = json.loads((package_dir / "local-check.json").read_text(encoding="utf-8"))
        print(json.dumps({"package": str(package_dir), "local_check": result}, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PASS" else 1
    if args.submit_latest:
        package_dir = latest_pending(args.report_type, config, date if args.date else None)
        result = git_submit_package(package_dir, config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.upload:
        schema_version = args.schema_version or config.get("incoming_schema_version", INCOMING_SCHEMA_VERSION)
        if args.report_type == "patch":
            package_dir = prepare_patch_package(date, config, args.run_id, args.patches, args.patch_packages, args.project, args.summary, args.status, schema_version, args.related_report_run_ids)
        else:
            package_dir = prepare_package(args.report_type, date, config, args.run_id, schema_version)
        result = git_submit_package(package_dir, config)
        print(json.dumps({"package": str(package_dir), "submit": result}, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
