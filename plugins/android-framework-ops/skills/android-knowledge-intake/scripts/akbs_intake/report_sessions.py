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
from akbs_intake.session_privacy import (
    minimal_source_id,
    require_report_session_consent,
    sanitize_command_summary,
    sanitize_work_summary,
    session_extraction_workspace,
)


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
REPORT_DIRECT_CUSTOMER_LABEL_RE = re.compile(
    r"(?:直接)?客户(?:名|名称)?\s*(?:是|为|[:：])\s*([^，,。.;；、\n\r()（）]+)"
)
REPORT_DOWNSTREAM_CUSTOMER_LABEL_RE = re.compile(
    r"(?:客户的客户|下游客户|终端客户)\s*(?:是|为|[:：])\s*([^，,。.;；、\n\r()（）]+)"
)
REPORT_GENERATION_REQUEST_RE = re.compile(r"(?:帮我|请).{0,24}(?:生成|提交|上传).{0,24}(?:日报|周报|报告)")


@dataclass
class SessionWork:
    session_id: str = ""
    thread_name: str = ""
    cwd: str = ""
    project: str = "未识别项目"
    messages: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    latest_at: str = ""


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


def session_files(codex_home: Path, dates: set[dt.date], timezone_name: str = "Asia/Shanghai") -> list[Path]:
    root = codex_home / "sessions"
    if not root.exists():
        return []
    candidates: list[Path] = []
    for date in sorted(dates):
        day_dir = root / f"{date:%Y}" / f"{date:%m}" / f"{date:%d}"
        if day_dir.is_dir():
            candidates.extend(day_dir.glob("*.jsonl"))
    start = min(dates)
    end = max(dates)
    timezone = ZoneInfo(timezone_name) if ZoneInfo is not None else None
    threshold = dt.datetime.combine(start, dt.time.min, tzinfo=timezone).timestamp()
    for path in root.glob("*/*/*/*.jsonl"):
        try:
            directory_date = dt.date(int(path.parts[-4]), int(path.parts[-3]), int(path.parts[-2]))
            modified_at = path.stat().st_mtime
        except (OSError, ValueError):
            continue
        if directory_date <= end and modified_at >= threshold:
            candidates.append(path)
    return sorted(set(candidates))


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
    text = " ".join([work.thread_name, work.cwd, *work.messages, *work.outcomes])
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
    candidates = [work.project, work.cwd, work.thread_name, *work.messages, *work.outcomes]
    for text in candidates:
        project = find_company_project(text)
        if project:
            return project
    return MISSING_REPORT_PROJECT


def clean_report_customer_name(value: Any) -> str:
    customer = re.sub(r"\s+", " ", str(value or "")).strip(" \t'\"`，,。.;；:：|-_/")
    if not customer or customer in REPORT_MISSING_CUSTOMER_VALUES:
        return ""
    if len(customer) > 32:
        return ""
    if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", customer):
        return ""
    return customer


def inferred_report_customer_name(value: Any) -> str:
    customer = clean_report_customer_name(value)
    if not customer or REPORT_CUSTOMER_COMMAND_RE.search(customer) or REPORT_CUSTOMER_WORK_TERM_RE.search(customer):
        return ""
    return customer


def split_report_customer_context(value: Any) -> dict[str, str]:
    parts = re.split(r"\s+", str(value or "").strip())
    if not parts or not parts[0]:
        return {}
    customer = inferred_report_customer_name(parts[0])
    if not customer:
        return {}
    context = {"customer_name": customer}
    if len(parts) > 1:
        downstream = inferred_report_customer_name(" ".join(parts[1:]))
        if downstream:
            context["downstream_customer"] = downstream
    return context


def project_customer_contexts_from_text(text: Any) -> list[tuple[str, dict[str, str]]]:
    raw_text = str(text or "")
    contexts: list[tuple[str, dict[str, str]]] = []
    for match in PROJECT_ANCHOR_RE.finditer(raw_text):
        project = find_company_project(match.group("base"))
        if not project:
            continue
        raw_tail = raw_text[match.end() :]
        next_project = PROJECT_ANCHOR_RE.search(raw_tail)
        tail = raw_tail[: next_project.start()] if next_project else raw_tail
        direct_match = REPORT_DIRECT_CUSTOMER_LABEL_RE.search(tail)
        downstream_match = REPORT_DOWNSTREAM_CUSTOMER_LABEL_RE.search(tail)
        context: dict[str, str] = {}
        if direct_match:
            customer = clean_report_customer_name(direct_match.group(1))
            if customer:
                context["customer_name"] = customer
                if downstream_match:
                    downstream = clean_report_customer_name(downstream_match.group(1))
                    if downstream:
                        context["downstream_customer"] = downstream
        elif raw_tail and raw_tail[0].isspace():
            customer_part = REPORT_CUSTOMER_STOP_RE.split(raw_tail.lstrip(), 1)[0]
            context = split_report_customer_context(customer_part)
        if context:
            item = (project, context)
            if item not in contexts:
                contexts.append(item)
    return contexts


def project_customer_pairs_from_text(text: Any) -> list[tuple[str, str]]:
    return [
        (project, context["customer_name"])
        for project, context in project_customer_contexts_from_text(text)
    ]


def report_project_customers_from_clues(clues: list[tuple[str, str]]) -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    customers: dict[str, dict[str, str]] = {}
    basis: dict[str, list[str]] = {}
    for label, value in clues:
        for project, context in project_customer_contexts_from_text(value):
            current = customers.setdefault(project, dict(context))
            if (
                current.get("customer_name") == context.get("customer_name")
                and not current.get("downstream_customer")
                and context.get("downstream_customer")
            ):
                current["downstream_customer"] = context["downstream_customer"]
            chain = " ".join(
                item
                for item in (context.get("customer_name", ""), context.get("downstream_customer", ""))
                if item
            )
            basis.setdefault(project, []).append(f"{label}: {project} {chain}")
    return customers, basis


def normalize_report_customer_context(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        customer = clean_report_customer_name(
            value.get("customer_name") or value.get("customer")
        )
        downstream = clean_report_customer_name(
            value.get("downstream_customer")
            or value.get("customer_of_customer")
            or value.get("end_customer")
            or value.get("客户的客户")
        )
    else:
        customer = clean_report_customer_name(value)
        downstream = ""
    context = {"customer_name": customer} if customer else {}
    if downstream:
        context["downstream_customer"] = downstream
    return context


def report_customer_context_for_project(project: Any, project_customers: dict[str, Any] | None = None) -> dict[str, str]:
    canonical = find_company_project(str(project or ""))
    if not canonical:
        return {"customer_name": MISSING_REPORT_CUSTOMER}
    context = normalize_report_customer_context((project_customers or {}).get(canonical, ""))
    if not context.get("customer_name"):
        context["customer_name"] = MISSING_REPORT_CUSTOMER
    return context


def report_customer_for_project(project: Any, project_customers: dict[str, Any] | None = None) -> str:
    return report_customer_context_for_project(project, project_customers)["customer_name"]


def report_downstream_customer_for_project(project: Any, project_customers: dict[str, Any] | None = None) -> str:
    return report_customer_context_for_project(project, project_customers).get("downstream_customer", "")


def report_customer_chain_label(customer: Any, downstream_customer: Any = "") -> str:
    customer_text = clean_report_customer_name(customer) or MISSING_REPORT_CUSTOMER
    downstream_text = clean_report_customer_name(downstream_customer)
    return " ".join(item for item in (customer_text, downstream_text) if item)


def is_report_generation_request(text: str) -> bool:
    return bool(REPORT_GENERATION_REQUEST_RE.search(str(text or "")))


def parse_sessions(config: dict[str, str], dates: set[dt.date], run_command: RunCommand) -> list[SessionWork]:
    consent = require_report_session_consent(config, dates, synthetic=False)
    codex_home = expanded_path(config["codex_home"])
    sessions: list[SessionWork] = []
    try:
        with session_extraction_workspace():
            for file in session_files(codex_home, dates, config.get("timezone", "Asia/Shanghai")):
                work = SessionWork()
                raw_cwd = ""
                for line in file.read_text(encoding="utf-8", errors="ignore").splitlines():
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if local_date(row.get("timestamp", ""), config) not in dates:
                        continue
                    work.latest_at = max(work.latest_at, str(row.get("timestamp") or ""))
                    payload = row.get("payload") or {}
                    if row.get("type") == "session_meta":
                        work.session_id = str(payload.get("id", "") or work.session_id)
                        if consent.fields & {"project_hint", "patch_discovery"}:
                            raw_cwd = str(payload.get("cwd", "") or raw_cwd)
                        continue
                    if row.get("type") != "response_item":
                        continue
                    if payload.get("type") == "message" and "work_summary" in consent.fields:
                        role = payload.get("role")
                        raw_text = extract_input_text(payload.get("content"))
                        text = sanitize_work_summary(raw_text)
                        if role == "user" and not should_skip_message(text):
                            work.messages.append(text)
                        elif role == "assistant" and text and not should_skip_message(text):
                            work.outcomes.append(text)
                    elif (
                        payload.get("type") == "function_call"
                        and payload.get("name") == "exec_command"
                        and "command_summary" in consent.fields
                    ):
                        try:
                            args = json.loads(payload.get("arguments") or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        command = sanitize_command_summary(args.get("cmd", ""))
                        if command:
                            work.commands.append(command)

                if not work.session_id:
                    match = re.search(r"([0-9a-f]{8}-[0-9a-f-]{27,})", file.name)
                    work.session_id = match.group(1) if match else file.stem
                work.session_id = minimal_source_id(work.session_id)
                if raw_cwd:
                    anchored = find_company_project(raw_cwd)
                    if anchored:
                        work.project = anchored
                    if "patch_discovery" in consent.fields and Path(raw_cwd).exists():
                        work.cwd = raw_cwd
                        work.project = git_branch_or_name(raw_cwd, run_command)
                if should_skip_session(work) or (not work.messages and not work.outcomes):
                    continue
                work.project = project_name(work)
                sessions.append(work)
    except (Exception, SystemExit):
        raise SystemExit("Codex session extraction failed safely; no raw session content or path was retained.") from None
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
                outcomes=[f"处理结果：{status}"],
            )
        )
    return sessions
