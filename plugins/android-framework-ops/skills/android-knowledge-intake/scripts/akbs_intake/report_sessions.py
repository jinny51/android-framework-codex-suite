from __future__ import annotations

import datetime as dt
import json
import random
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from android_framework_ops.knowledge_rules import (
    PROJECT_ANCHOR_RE,
    canonical_company_project,
    find_company_project,
)
from akbs_intake.config import expanded_path
from akbs_intake.reports.common import week_bounds, ymd


RunCommand = Callable[[list[str]], subprocess.CompletedProcess[str]]

REMOTE_PATH_RE = re.compile(r"(?:/[A-Za-z0-9_.@+-]+){2,}")
NOISE_TEXT_RE = re.compile(
    r"(?i)("
    r"enter\s+passphrase|"
    r"codex agent history|"
    r"request action you are assessing|"
    r"the user interrupted the previous turn|"
    r"files mentioned by the user|"
    r"files-mentioned-by-the-user|"
    r"plugin://|"
    r"日报上传测试|"
    r"周报上传测试|"
    r"daily report draft|"
    r"weekly report draft"
    r")"
)

MISSING_REPORT_PROJECT = "需成员补充项目名"
MISSING_REPORT_CUSTOMER = "需成员补充客户名"
REPORT_MISSING_PROJECT_VALUES = {"", "unknown", "未识别项目", MISSING_REPORT_PROJECT}
REPORT_MISSING_CUSTOMER_VALUES = {"", "unknown", "未识别客户", "需成员确认", MISSING_REPORT_CUSTOMER}
REPORT_CUSTOMER_STOP_RE = re.compile(r"\s*(?:[，,。.;；\n\r]|帮我|请|生成|提交|上传|日报|周报|报告)")
REPORT_CUSTOMER_COMMAND_RE = re.compile(r"(帮我|请|生成|提交|上传|日报|周报|报告|今天|本周|主要工作|围绕|处理|完成|进度)")
REPORT_CUSTOMER_WORK_TERM_RE = re.compile(
    r"(?:功能|模块|策略|需求|事项|问题|补丁|开发|修复|适配|排查|验证|联调|进度|状态栏|锁屏|鼠标|副屏)$"
)
REPORT_GENERATION_REQUEST_RE = re.compile(r"(?:帮我|请).{0,24}(?:生成|提交|上传).{0,24}(?:日报|周报|报告)")


@dataclass
class SessionWork:
    session_id: str = ""
    thread_name: str = ""
    cwd: str = ""
    project: str = "未识别项目"
    messages: list[str] = field(default_factory=list)


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
    if NOISE_TEXT_RE.search(text):
        return True
    return False


def has_project_anchor(text: str) -> bool:
    return bool(PROJECT_ANCHOR_RE.search(text or ""))


def project_anchor(text: str) -> str:
    match = PROJECT_ANCHOR_RE.search(text or "")
    return canonical_company_project(match.group("base")) if match else ""


def strip_project_anchor(text: str, project: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[*`#]+", "", text)
    if project:
        cleaned = re.sub(re.escape(project), "", cleaned, flags=re.I)
    cleaned = REMOTE_PATH_RE.sub(" ", cleaned)
    cleaned = re.sub(r"(?i)\bssh\s+[A-Za-z0-9_.@:-]+", " ", cleaned)
    cleaned = PROJECT_ANCHOR_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" _-:/\\，,。；;（）()")
    return cleaned


def is_noise_session(work: SessionWork) -> bool:
    text = " ".join([work.thread_name, work.cwd, *work.messages])
    if has_project_anchor(text):
        return False
    if NOISE_TEXT_RE.search(text):
        return True
    normalized = work.cwd.replace("\\", "/").lower()
    if any(part in normalized for part in ("/.codex/", "/documents/codex/worktrees/knowledge-", "/android-framework-codex-suite/")):
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
    if "汇总" in work.thread_name and ("日报" in work.thread_name or "周报" in work.thread_name):
        return True
    return is_noise_session(work)


def git_root(path: str, run_command: RunCommand) -> Path | None:
    if not path:
        return None
    cp = run_command(["git", "-C", path, "rev-parse", "--show-toplevel"])
    if cp.returncode != 0:
        return None
    root = cp.stdout.strip()
    return Path(root) if root else None


def git_branch_or_name(path: str, run_command: RunCommand) -> str:
    cp = run_command(["git", "-C", path, "branch", "--show-current"])
    branch = cp.stdout.strip()
    if branch:
        return branch
    root = git_root(path, run_command)
    return root.name if root else Path(path).name


def project_name(work: SessionWork) -> str:
    candidates = [work.project, work.cwd, work.thread_name, *work.messages]
    for text in candidates:
        project = find_company_project(text)
        if project:
            return project
    return MISSING_REPORT_PROJECT


def clean_report_customer_name(value: Any) -> str:
    customer = re.sub(r"\s+", " ", str(value or "")).strip(" \t'\"`，,。.;；:：|-_/")
    if not customer or customer in REPORT_MISSING_CUSTOMER_VALUES:
        return ""
    if REPORT_CUSTOMER_COMMAND_RE.search(customer):
        return ""
    if REPORT_CUSTOMER_WORK_TERM_RE.search(customer):
        return ""
    if len(customer) > 32:
        return ""
    if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", customer):
        return ""
    return customer


def project_customer_pairs_from_text(text: Any) -> list[tuple[str, str]]:
    raw_text = str(text or "")
    pairs: list[tuple[str, str]] = []
    for match in PROJECT_ANCHOR_RE.finditer(raw_text):
        project = find_company_project(match.group("base"))
        if not project:
            continue
        tail = raw_text[match.end() :]
        if not tail or not tail[0].isspace():
            continue
        tail = tail.lstrip()
        customer_part = REPORT_CUSTOMER_STOP_RE.split(tail, 1)[0]
        customer = clean_report_customer_name(customer_part)
        if customer:
            pair = (project, customer)
            if pair not in pairs:
                pairs.append(pair)
    return pairs


def report_project_customers_from_clues(clues: list[tuple[str, str]]) -> tuple[dict[str, str], dict[str, list[str]]]:
    customers: dict[str, str] = {}
    basis: dict[str, list[str]] = {}
    for label, value in clues:
        for project, customer in project_customer_pairs_from_text(value):
            customers.setdefault(project, customer)
            basis.setdefault(project, []).append(f"{label}: {project} {customer}")
    return customers, basis


def report_customer_for_project(project: Any, project_customers: dict[str, str] | None = None) -> str:
    canonical = find_company_project(str(project or ""))
    if not canonical:
        return MISSING_REPORT_CUSTOMER
    customer = (project_customers or {}).get(canonical, "")
    return customer or MISSING_REPORT_CUSTOMER


def is_report_generation_request(text: str) -> bool:
    return bool(REPORT_GENERATION_REQUEST_RE.search(str(text or "")))


def parse_sessions(config: dict[str, str], dates: set[dt.date], run_command: RunCommand) -> list[SessionWork]:
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
                if cmd and any(token in cmd for token in ("git ", "apply_patch", ".patch", "build", "test", "adb ", "ssh ", "cd ", "/home/")):
                    work.messages.append(f"执行命令: {cmd}")

        if not work.session_id:
            match = re.search(r"([0-9a-f]{8}-[0-9a-f-]{27,})", file.name)
            work.session_id = match.group(1) if match else file.stem
        work.thread_name = names.get(work.session_id, work.session_id)
        if work.cwd and Path(work.cwd).exists():
            work.project = git_branch_or_name(work.cwd, run_command)
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
    projects = ["TVE8402M", "TVA10A2R", "TVI2010M"]
    project_customers = {
        "TVE8402M": "合成客户一",
        "TVA10A2R": "合成客户二",
        "TVI2010M": "合成客户三",
    }
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
    for task in chosen_tasks:
        token = uuid.uuid4().hex[:8]
        project = projects[0]
        status = rng.choice(statuses)
        sessions.append(
            SessionWork(
                session_id=f"synthetic-{date_key}-{token}",
                thread_name=f"合成测试-{task}",
                cwd="",
                project=project,
                messages=[
                    f"项目客户：{project} {project_customers[project]}",
                    f"合成测试数据：{task}",
                    f"合成测试进度：{status}",
                    "合成测试说明：该记录不来自真实 Codex 会话或真实源码仓库。",
                ],
            )
        )
    return sessions
