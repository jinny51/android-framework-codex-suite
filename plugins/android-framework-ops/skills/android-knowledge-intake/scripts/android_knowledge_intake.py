#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
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
SCHEMA_VERSION = "1.0"
ENV_PREFIXES = ("CODEX_REPORT_", "CODEX_WORK_REPORT_")
PATCH_FILENAME_RE = re.compile(r"^[a-z0-9]+[0-9]+-[A-Za-z0-9._-]+@[a-z0-9_.-]+\.patch$")
AUTHOR_DATE_RE = re.compile(r"//[A-Za-z0-9_]+\s+\d{8}@")
BANNED_LOG_PATTERNS = ("Log.d(", "Log.i(", "Log.w(", "Slog.d(", "Slog.i(", "Slog.w(")
REPORT_HEADINGS = {
    "daily": ("今日概览", "项目事项"),
    "weekly": ("本周概览", "项目事项"),
}
PACKAGE_TYPES = {"daily", "weekly", "patch"}
PATCH_README_HEADINGS = ("功能描述", "修改点", "日志控制", "SystemProperties", "字符串国际化", "可回滚性")
V2_LIGHT_KINDS = {"daily_trace", "weekly_trace", "session_trace"}
V2_STRICT_KINDS = {"framework_change", "patch_contribution", "reuse_decision"}
V2_LIGHT_QUALITIES = {"imported", "trace", "candidate"}
V2_STRICT_QUALITIES = {"imported", "candidate", "validated", "released", "buggy"}
V2_INFERENCE_EVIDENCE_KINDS = {"patch_problem_inference", "risk_surface"}
V2_CONFIDENCE_VALUES = {"low", "medium", "high"}


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
    "incoming_schema_version": "2.0",
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
    projects = ["合成测试项目-A", "合成测试项目-B", "合成测试项目-C"]
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
    patch_name = f"test001-synthetic-{token}@framework.patch"
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
                "+// synthetic setting key: persist.sys.codex.synthetic_demo",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    readme_path.write_text(
        f"""# {patch_name}

## 功能描述

合成测试补丁，用于验证 incoming 协议、服务端解析、索引构建和可视化展示流程，不来自真实源码仓库。

## 修改点

- 合成一条注释级 diff，避免引入真实业务代码。
- 合成系统属性 `persist.sys.codex.synthetic_demo`，用于验证 symbol 索引。

## 日志控制

无新增运行时日志。

## SystemProperties

`persist.sys.codex.synthetic_demo`，仅作为合成测试索引样例。

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
        return "搭建codex日报周报自动化与知识库提交能力"
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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], bool]:
    patch_dir = package_dir / "patches"
    evidence_dir = package_dir / "evidence"
    patch_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    patch_entries: list[dict[str, Any]] = []
    evidence_entries: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    has_pass_verification = False

    for raw in package_paths:
        capture_dir = Path(raw).expanduser().resolve()
        manifest = read_json_file(capture_dir / "manifest.json")
        if manifest.get("package_type") != "framework_patch":
            raise SystemExit(f"不是 android-framework-patch-capture 工作包: {capture_dir}")
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
            patch_entries.append(
                {
                    "path": f"patches/{patch_name}",
                    "readme": f"patches/{readme_name}",
                    "status": entry_status,
                    "reusable": bool(item.get("reusable", entry_status in {"validated", "released"})),
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
                "path": f"evidence/{target_name}",
                "result": item.get("result", "INFO"),
                "summary": item.get("summary", "captured patch evidence"),
            }
            evidence_entries.append(copied)
            if verification_payload_passes(capture_dir, item):
                has_pass_verification = True

    return patch_entries, evidence_entries, sources, has_pass_verification


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
        readme_text = readme.read_text(encoding="utf-8", errors="ignore")
        for heading in PATCH_README_HEADINGS:
            if not has_heading(readme_text, heading):
                errors.append(f"{readme.name} 缺少必填章节: ## {heading}")
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

    if manifest.get("schema_version") == "2.0":
        return validate_v2_package(package_dir, manifest)

    report_type = str(manifest.get("type", ""))
    for field in ("schema_version", "type", "member", "date", "project", "summary", "patches"):
        if field not in manifest:
            errors.append(f"manifest 缺少必填字段: {field}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {SCHEMA_VERSION}")
    if report_type not in PACKAGE_TYPES:
        errors.append("type 必须是 daily、weekly 或 patch")
    if report_type == "weekly" and not re.fullmatch(r"\d{8}-\d{8}", str(manifest.get("week_range", ""))):
        errors.append("weekly 工作包必须提供 week_range: YYYYMMDD-YYYYMMDD")

    if report_type in REPORT_HEADINGS:
        report = package_dir / f"{report_type}.md"
        if not report.is_file():
            errors.append(f"缺少 {report_type}.md")
        else:
            text = report.read_text(encoding="utf-8", errors="ignore")
            for heading in REPORT_HEADINGS.get(report_type, ()):
                if not has_heading(text, heading):
                    errors.append(f"{report.name} 缺少必填章节: ## {heading}")

    patches = manifest.get("patches")
    if not isinstance(patches, list):
        errors.append("manifest.patches 必须是数组")
        patches = []
    if report_type == "patch" and not patches:
        errors.append("patch 工作包必须至少包含一个补丁")
    listed = set()
    for item in patches:
        rel = item.get("path") if isinstance(item, dict) else item
        if not isinstance(rel, str) or not rel:
            errors.append("manifest.patches 中每一项必须是路径字符串，或包含 path 的对象")
            continue
        listed.add(rel)
        path = package_dir / rel
        if not path.is_file():
            errors.append(f"manifest.patches 指向的文件不存在: {rel}")
            continue
        errors.extend(validate_patch_file(path))
        readme = paired_readme(path)
        if readme and "TODO:" in readme.read_text(encoding="utf-8", errors="ignore"):
            warnings.append(f"{readme.name} 仍包含 TODO 模板内容，建议成员提交前补全")
    for patch in sorted((package_dir / "patches").glob("*.patch")) if (package_dir / "patches").is_dir() else []:
        rel = patch.relative_to(package_dir).as_posix()
        if rel not in listed:
            errors.append(f"patches/ 下存在未写入 manifest.patches 的 patch: {patch.name}")
    return {"status": "FAIL" if errors else "PASS", "errors": errors, "warnings": warnings}


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
        "skill": skill,
        "skill_version": "",
        "plugin_commit": plugin_commit(),
        "member_alias": config["member_alias"],
        "generated_at": local_now(config).isoformat(),
        "host": os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "",
        "cwd": str(Path.cwd()),
    }


def write_v2_source(package_dir: Path, config: dict[str, str], skill: str) -> dict[str, Any]:
    source = source_metadata(config, skill)
    write_json(package_dir / "evidence" / "source.json", source)
    return source


def v2_report_manifest(
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
    title = "日报" if report_type == "daily" else "周报"
    title_key = ymd(date) if report_type == "daily" else week_key
    manifest: dict[str, Any] = {
        "schema_version": "2.0",
        "package_kind": package_kind,
        "channel": "light",
        "quality": "trace",
        "member": config["member_alias"],
        "date": date.isoformat(),
        "run_id": run_id,
        "project": "全局项目",
        "summary": summary,
        "source": source,
        "reports": [
            {
                "id": f"report-{report_type}",
                "kind": report_type,
                "path": f"reports/{report_name}",
                "title": f"{title_key}_{config['member_name']}_{title}",
            }
        ],
        "patches": [],
        "evidence": [
            {
                "id": "source",
                "kind": "source",
                "path": "evidence/source.json",
                "result": "INFO",
                "summary": "package source metadata",
            },
            {
                "id": "codex-sessions",
                "kind": "codex_sessions",
                "path": "evidence/codex-sessions.json",
                "result": "INFO",
                "summary": "Codex session trace evidence",
            },
        ],
        "relations": [
            {
                "from": f"report-{report_type}",
                "to": "codex-sessions",
                "type": "generated_from",
            }
        ],
        "quality_claims": {},
    }
    if report_type == "weekly":
        manifest["week_range"] = week_key
    return manifest


def v2_referenced_paths(manifest: dict[str, Any]) -> list[str]:
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


def v2_reference_path(package_dir: Path, rel: str) -> Path:
    path = (package_dir / rel).resolve()
    root = package_dir.resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"引用路径越界: {rel}")
    return path


def v2_read_referenced_json(package_dir: Path, rel: str) -> dict[str, Any] | None:
    try:
        path = v2_reference_path(package_dir, rel)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def v2_patch_diff_modified_files(package_dir: Path, rel: str) -> list[str]:
    try:
        path = v2_reference_path(package_dir, rel)
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


def v2_validate_inference_evidence(package_dir: Path, item: dict[str, Any], errors: list[str]) -> None:
    rel = item.get("path")
    if not isinstance(rel, str) or not rel:
        errors.append("反推 evidence 必须引用 JSON 文件")
        return
    payload = v2_read_referenced_json(package_dir, rel)
    if payload is None:
        return
    confidence = payload.get("confidence")
    basis = payload.get("basis")
    limits = payload.get("limits")
    if confidence not in V2_CONFIDENCE_VALUES:
        errors.append(f"{rel} confidence 必须是 low、medium 或 high")
    if not isinstance(basis, list) or not basis:
        errors.append(f"{rel} basis 必须是非空数组")
    if not isinstance(limits, list) or not limits:
        errors.append(f"{rel} limits 必须是非空数组")


def validate_v2_package(package_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    required = {
        "schema_version",
        "package_kind",
        "channel",
        "quality",
        "member",
        "date",
        "run_id",
        "project",
        "summary",
        "source",
        "reports",
        "patches",
        "evidence",
        "relations",
    }
    for field in sorted(required - set(manifest)):
        errors.append(f"manifest 缺少必填字段: {field}")
    if manifest.get("schema_version") != "2.0":
        errors.append("schema_version 必须是 2.0")

    channel = manifest.get("channel")
    quality = manifest.get("quality")
    package_kind = manifest.get("package_kind")
    if channel == "light":
        if package_kind not in V2_LIGHT_KINDS:
            errors.append(f"light channel 不能使用 package_kind={package_kind}")
        if quality not in V2_LIGHT_QUALITIES:
            errors.append(f"light channel 不能使用 quality={quality}")
    elif channel == "strict":
        if package_kind not in V2_STRICT_KINDS:
            errors.append(f"strict channel 不能使用 package_kind={package_kind}")
        if quality not in V2_STRICT_QUALITIES:
            errors.append(f"strict channel 不能使用 quality={quality}")
    else:
        errors.append("channel 必须是 light 或 strict")

    for rel in v2_referenced_paths(manifest):
        try:
            path = v2_reference_path(package_dir, rel)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"引用文件不存在: {rel}")

    evidence = manifest.get("evidence", [])
    if not isinstance(evidence, list):
        errors.append("evidence 必须是数组")
        evidence = []
    for item in evidence:
        if not isinstance(item, dict):
            errors.append("evidence 中每一项必须是对象")
            continue
        if item.get("kind") in V2_INFERENCE_EVIDENCE_KINDS:
            v2_validate_inference_evidence(package_dir, item, errors)

    patches = manifest.get("patches", [])
    if not isinstance(patches, list):
        errors.append("patches 必须是数组")
        patches = []
    for item in patches:
        if not isinstance(item, dict):
            errors.append("patches 中每一项必须是对象")
            continue
        facts = item.get("facts", {})
        modified_files = facts.get("modified_files") if isinstance(facts, dict) else None
        if not modified_files:
            patch_rel = item.get("path")
            if isinstance(patch_rel, str) and v2_patch_diff_modified_files(package_dir, patch_rel):
                warnings.append(f"patch facts.modified_files 已从补丁 diff 反推: {patch_rel}")
            else:
                errors.append("patch 必须提供 facts.modified_files，或可从补丁 diff 反推")
        if quality in {"candidate", "validated"}:
            readme = item.get("readme")
            if not isinstance(readme, str) or not readme:
                errors.append("candidate/validated patch 必须提供 readme")

    if quality == "validated":
        claims = manifest.get("quality_claims", {})
        if not isinstance(claims, dict):
            claims = {}
        for field in ("risk_notes", "rollback_notes", "scope"):
            if not claims.get(field):
                errors.append(f"validated 必须提供 quality_claims.{field}")
        if not v2_has_pass_verification(package_dir, manifest):
            errors.append("validated 必须提供 PASS 的设备验证或合格等价验证 evidence")
    return {"status": "FAIL" if errors else "PASS", "errors": errors, "warnings": warnings}


def v2_has_pass_verification(package_dir: Path, manifest: dict[str, Any]) -> bool:
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


def v2_patch_item(package_dir: Path, patch_entry: dict[str, Any]) -> dict[str, Any]:
    patch_path = package_dir / str(patch_entry["path"])
    captured_facts = patch_entry.get("facts") if isinstance(patch_entry.get("facts"), dict) else {}
    facts = {
        "modified_files": captured_facts.get("modified_files") or patch_modified_files(patch_path),
        "symbols": captured_facts.get("symbols") or [],
        "system_properties": captured_facts.get("system_properties") or [],
        "settings_keys": captured_facts.get("settings_keys") or [],
        "resource_keys": captured_facts.get("resource_keys") or [],
        "framework_log_keys": captured_facts.get("framework_log_keys") or [],
    }
    return {
        "id": Path(str(patch_entry["path"])).stem,
        "path": patch_entry["path"],
        "readme": patch_entry.get("readme", ""),
        "status": patch_entry.get("status", "candidate"),
        "reusable": bool(patch_entry.get("reusable", False)),
        "repo_path": "",
        "artifact": "",
        "facts": facts,
    }


def prepare_package(report_type: str, date: dt.date, config: dict[str, str], run_id: str | None = None, schema_version: str = "1.0") -> Path:
    require_config(config)
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
    patch_entries = copy_patch_assets(package_dir, patches, config)
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
    write_json(package_dir / "evidence" / "codex-sessions.json", evidence)
    if schema_version == "2.0":
        reports_dir = package_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(package_dir / f"{report_type}.md"), reports_dir / f"{report_type}.md")
        source = write_v2_source(package_dir, config, "android-knowledge-intake")
        manifest = v2_report_manifest(report_type, date, week_key, config, summary, source, run_id)
    else:
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "type": report_type,
            "member": config["member_alias"],
            "date": date.isoformat(),
            "project": "全局项目" if "全局项目" in items else (next(iter(items)) if items else "全局项目"),
            "summary": summary,
            "patches": patch_entries,
            "synthetic_data": synthetic_mode(config),
        }
        if report_type == "weekly":
            manifest["week_range"] = week_key
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
    project: str = "Android Framework",
    summary: str = "管理员手动归档补丁",
    status: str = "validated",
    schema_version: str = "1.0",
) -> Path:
    require_config(config)
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

    if patch_package_paths:
        capture_entries, evidence_entries, source_entries, capture_has_pass = copy_patch_capture_packages(
            package_dir,
            patch_package_paths,
            project,
            status,
        )
        patch_entries.extend(capture_entries)
        capture_evidence_entries.extend(evidence_entries)
        patch_sources.extend(source_entries)
        has_pass_verification = has_pass_verification or capture_has_pass

    if patch_paths:
        patches = patch_infos_from_paths(patch_paths, project)
    elif synthetic_mode(config):
        patches = [synthetic_patch_info(package_dir, date, project, config)]
        summary = summary if summary != "管理员手动归档补丁" else "合成测试补丁包"
        status = "draft" if status == "validated" else status
    elif not patch_entries:
        patches = discover_patches_from_cwd(project, date)
    else:
        patches = []
    if not patches:
        if not patch_entries:
            raise SystemExit("patch 模式未找到补丁，请使用 --patch/--patch-package 指定，或在当前目录/patches 下放置当天修改的 .patch 文件。")
    else:
        patch_entries.extend(copy_patch_assets(package_dir, patches, config, status=status, reusable=status in {"validated", "released"}, note="管理员手动归档补丁"))
        patch_sources.extend([{"name": item.name, "source": str(item.path), "project": item.project} for item in patches])
    has_validated_patch = any(str(item.get("status", "")) in {"validated", "released"} for item in patch_entries)

    write_json(
        package_dir / "evidence" / "patch-contribution.json",
        {
            "source": "android-knowledge-intake",
            "mode": "patch",
            "synthetic_data": synthetic_mode(config),
            "patch_count": len(patch_entries),
            "patches": patch_sources,
            "capture_package_count": len(patch_package_paths or []),
        },
    )
    if schema_version == "2.0":
        source = write_v2_source(package_dir, config, "android-knowledge-intake")
        quality = "validated" if has_validated_patch and has_pass_verification else "candidate"
        manifest = {
            "schema_version": "2.0",
            "package_kind": "patch_contribution",
            "channel": "strict",
            "quality": quality,
            "member": config["member_alias"],
            "date": date.isoformat(),
            "run_id": run_id,
            "project": project,
            "summary": summary,
            "source": source,
            "reports": [],
            "patches": [v2_patch_item(package_dir, item) for item in patch_entries],
            "evidence": [
                {
                    "id": "source",
                    "kind": "source",
                    "path": "evidence/source.json",
                    "result": "INFO",
                    "summary": "package source metadata",
                },
                {
                    "id": "patch-contribution",
                    "kind": "manual_note",
                    "path": "evidence/patch-contribution.json",
                    "result": "INFO",
                    "summary": "manual patch contribution facts",
                },
                *capture_evidence_entries,
            ],
            "relations": [],
            "quality_claims": {
                "risk_notes": "手动补丁贡献，风险以配套 readme 为准。",
                "rollback_notes": "回滚对应 patch 并重新编译相关模块。",
                "scope": project,
            },
        }
    else:
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "type": "patch",
            "member": config["member_alias"],
            "date": date.isoformat(),
            "project": project,
            "summary": summary,
            "patches": patch_entries,
            "synthetic_data": synthetic_mode(config),
        }
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


def copy_package_to_repo(package_dir: Path, repo: Path) -> Path:
    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    date_key = str(manifest["date"]).replace("-", "")
    member = str(manifest["member"])
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
    manifest_type = manifest.get("type")
    if not manifest_type and manifest.get("schema_version") == "2.0":
        manifest_type = manifest.get("package_kind", "knowledge_event")
    msg = f"incoming({manifest_type}): {manifest['member']} {manifest['date']}"
    cp = git_run(repo, ["commit", "-m", msg], check=False)
    if cp.returncode != 0 and "nothing to commit" not in (cp.stdout + cp.stderr):
        raise SystemExit(f"git commit 失败: {cp.stderr.strip() or cp.stdout.strip()}")

    retries = max(1, int(config.get("push_retries", "3")))
    last_error = ""
    for _ in range(retries):
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
        manifest_type = manifest.get("type")
        if not manifest_type and manifest.get("schema_version") == "2.0":
            kind = str(manifest.get("package_kind", ""))
            manifest_type = "daily" if kind == "daily_trace" else "weekly" if kind == "weekly_trace" else "patch" if kind == "patch_contribution" else ""
        if manifest_type != report_type:
            continue
        if manifest.get("member") != config.get("member_alias"):
            continue
        if date and str(manifest.get("date")) != date.isoformat():
            continue
        candidates.append(manifest_path.parent)
    if not candidates:
        raise SystemExit(f"没有找到 {report_type} pending 工作包")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def doctor(config: dict[str, str], loaded: list[Path]) -> dict[str, Any]:
    repo = expanded_path(config["repo_worktree"])
    return {
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and submit Codex team knowledge incoming packages.")
    parser.add_argument("--profile", help="profile name from config, for example jinny or member_alias")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.set_defaults(report_type="")

    for report_type in ("daily", "weekly", "patch"):
        sub = subparsers.add_parser(report_type)
        sub.set_defaults(report_type=report_type)
        sub.add_argument("--date", help="YYYY-MM-DD, defaults to today")
        sub.add_argument("--run-id", help="override run id, format YYYYMMDD-HHMMSS[-suffix]")
        sub.add_argument("--schema-version", choices=["1.0", "2.0"], default="", help="incoming package schema version")
        if report_type == "patch":
            sub.add_argument("--patch", dest="patches", action="append", default=[], help="patch file to include; repeatable")
            sub.add_argument("--patch-package", dest="patch_packages", action="append", default=[], help="android-framework-patch-capture package directory to include; repeatable")
            sub.add_argument("--project", default="Android Framework", help="project name for patch contribution")
            sub.add_argument("--summary", default="管理员手动归档补丁", help="summary for patch contribution")
            sub.add_argument(
                "--status",
                choices=["draft", "candidate", "validated", "released", "buggy"],
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
        print(json.dumps(doctor(config, loaded), ensure_ascii=False, indent=2))
        return 0

    date = parse_date_arg(args.date, config)
    if args.validate:
        result = validate_package(Path(args.validate))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PASS" else 1
    if args.prepare or args.submit_latest or args.upload:
        enforce_mode_allowed(config, args.report_type)
    if args.prepare:
        schema_version = args.schema_version or config.get("incoming_schema_version", "1.0")
        if args.report_type == "patch":
            package_dir = prepare_patch_package(date, config, args.run_id, args.patches, args.patch_packages, args.project, args.summary, args.status, schema_version)
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
        schema_version = args.schema_version or config.get("incoming_schema_version", "1.0")
        if args.report_type == "patch":
            package_dir = prepare_patch_package(date, config, args.run_id, args.patches, args.patch_packages, args.project, args.summary, args.status, schema_version)
        else:
            package_dir = prepare_package(args.report_type, date, config, args.run_id, schema_version)
        result = git_submit_package(package_dir, config)
        print(json.dumps({"package": str(package_dir), "submit": result}, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
