from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any, Callable

from android_framework_ops.knowledge_rules import find_company_project

from akbs_intake.config import parse_bool
from akbs_intake.report_sessions import (
    NOISE_TEXT_RE,
    SessionWork,
    compact_text,
    is_report_generation_request,
    project_anchor,
    should_skip_message,
    strip_project_anchor,
)


GitRoot = Callable[[str], Path | None]
GitBranchOrName = Callable[[str], str]


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
    text = " ".join([session.thread_name, *session.messages]).lower()
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


def discover_patches(
    config: dict[str, str],
    sessions: list[SessionWork],
    start,
    end,
    *,
    git_root: GitRoot,
    git_branch_or_name: GitBranchOrName,
    patch_info_factory: Callable[[Path, str, str], Any],
) -> list[Any]:
    if not parse_bool(config.get("include_patches", "true")):
        return []
    roots: set[Path] = set()
    for session in sessions:
        if session.cwd and Path(session.cwd).exists():
            root = git_root(session.cwd)
            roots.add(root if root else Path(session.cwd))
            roots.add(Path(session.cwd))
    patches: dict[Path, Any] = {}
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
                mdate = path.stat().st_mtime
            except OSError:
                continue
            patch_date = dt.datetime.fromtimestamp(mdate).date()
            if not (start <= patch_date <= end):
                continue
            project = git_branch_or_name(str(git_root(str(path.parent)) or base))
            patches[path] = patch_info_factory(path, path.name, project)
    return sorted(patches.values(), key=lambda item: item.name)


def items_by_project(sessions: list[SessionWork], patches: list[Any]) -> dict[str, list[tuple[str, str]]]:
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


def overview_text(report_type: str, items: dict[str, list[tuple[str, str]]], patches: list[Any]) -> str:
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


def work_findings_payload(sessions: list[SessionWork], patches: list[Any]) -> dict[str, Any]:
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
