from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

try:
    from .common import week_bounds, ymd
except ImportError:  # pragma: no cover - direct script import fallback
    from akbs_intake.reports.common import week_bounds, ymd

from android_framework_ops.knowledge_rules import find_company_project
from android_framework_ops.json_io import write_json
from akbs_intake.report_sessions import (
    MISSING_REPORT_CUSTOMER,
    MISSING_REPORT_PROJECT,
    REPORT_MISSING_CUSTOMER_VALUES,
    REPORT_MISSING_PROJECT_VALUES,
    report_customer_chain_label,
    report_customer_context_for_project,
    report_customer_for_project,
    report_downstream_customer_for_project,
)


REPORT_PROJECT_MARKDOWN_RE = re.compile(
    r"(?<![A-Z0-9*])(TV[DEAI]\d{2}[A-Z0-9]{2}[MRU]\d?|TVI[A-Z0-9]{5}[A-Z0-9]?)(?![A-Z0-9*])",
    re.IGNORECASE,
)


def emphasize_report_project_names(markdown: Any) -> str:
    """Bold every project reference in Markdown without changing structured fields."""
    return REPORT_PROJECT_MARKDOWN_RE.sub(lambda match: f"**{match.group(1)}**", str(markdown or ""))


def compact_text(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def row_customer_context(row: dict[str, Any]) -> dict[str, str]:
    customer = str(row.get("customer") or row.get("customer_name") or MISSING_REPORT_CUSTOMER)
    downstream_customer = str(
        row.get("downstream_customer")
        or row.get("customer_of_customer")
        or row.get("end_customer")
        or ""
    )
    return {
        "customer_name": customer,
        "downstream_customer": downstream_customer,
    }


def project_customer_heading(project: Any, customer: Any, downstream_customer: Any = "") -> str:
    return f"{project} {report_customer_chain_label(customer, downstream_customer)}"


def project_customer_title_label(project: Any, customer: Any, downstream_customer: Any = "") -> str:
    customer_text = str(customer or MISSING_REPORT_CUSTOMER)
    downstream_text = str(downstream_customer or "")
    chain = f"{customer_text} → {downstream_text}" if downstream_text else customer_text
    return f"{project}（{chain}）"


def add_downstream_customer(row: dict[str, Any], downstream_customer: Any) -> dict[str, Any]:
    value = str(downstream_customer or "").strip()
    if value:
        row["downstream_customer"] = value
    return row


def materials_rel(*parts: str) -> str:
    return "/".join(("materials", *parts))


def progress_bucket(progress: str) -> str:
    text = str(progress or "")
    if any(token in text for token in ("阻塞", "blocked", "失败", "报错")):
        return "blocked"
    if re.search(r"(?:^|[^0-9])100\s*%|进度\s*100", text):
        return "completed"
    if any(token in text for token in ("待验证", "验证中")):
        return "in_progress"
    if any(token in text for token in ("处理中", "进行中", "继续排查", "未完成", "待处理")):
        return "in_progress"
    if any(token in text for token in ("已完成", "已解决", "已产出 Patch", "通过", "成功")):
        return "completed"
    return "not_started"

def project_stats(entries: list[tuple[str, str]]) -> dict[str, int]:
    stats = {"total": len(entries), "completed": 0, "in_progress": 0, "not_started": 0, "blocked": 0}
    for _, progress in entries:
        bucket = progress_bucket(progress)
        stats[bucket] = stats.get(bucket, 0) + 1
    return stats

def status_label_from_stats(stats: dict[str, int]) -> str:
    if stats.get("blocked", 0):
        return "有阻塞"
    if stats.get("in_progress", 0):
        return "推进中"
    if stats.get("not_started", 0):
        return "未开始"
    if stats.get("completed", 0):
        return "已完成"
    return "无事项"

def next_step_for_entries(entries: list[tuple[str, str]], report_type: str) -> str:
    issues = [desc for desc, progress in entries if progress_bucket(progress) in {"blocked", "in_progress", "not_started"}]
    if issues:
        prefix = "明日继续" if report_type == "daily" else "下周继续"
        return f"{prefix}推进：{compact_text('；'.join(issues[:3]), 120)}"
    return "保持验证和交付记录完整，必要时补齐 patch-capture 证据。"

def report_item_source(desc: str) -> str:
    text = str(desc or "")
    if any(token in text for token in ("禅道", "zentao", "buglist", "Buglist")):
        return "禅道"
    if any(token in text for token in ("测试", "回归", "复现")):
        return "测试"
    if any(token in text for token in ("客户", "客诉", "现场")):
        return "客户"
    if any(token in text for token in ("项目经理", "PM", "需求文档")):
        return "项目经理"
    if any(token in text for token in ("上级", "TL", "负责人")):
        return "上级"
    return "临时工作/内部优化"

def report_list_type(desc: str) -> str:
    text = str(desc or "").lower()
    if any(token in text for token in ("bug", "问题", "缺陷", "报错", "失败", "异常", "buglist")):
        return "Buglist"
    if any(token in text for token in ("需求", "功能", "适配", "开发", "移植")):
        return "需求清单"
    return "临时工作"

def report_category(desc: str, progress: str) -> str:
    text = f"{desc} {progress}".lower()
    if any(token in text for token in ("bug", "问题", "修复", "异常", "失败", "报错")):
        return "Bug处理"
    if any(token in text for token in ("ui", "界面", "显示", "布局")):
        return "UI修改"
    return "功能添加"

def report_item_name(desc: str) -> str:
    return compact_text(str(desc or "未命名事项"), 80)

def weekly_display_date(date: dt.date) -> str:
    start, end = week_bounds(date)
    friday = start + dt.timedelta(days=4)
    return min(friday, end).isoformat()

def weekly_source_rows(items: dict[str, list[tuple[str, str]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str], list[tuple[str, str]]] = {}
    for project, entries in sorted(items.items()):
        for desc, progress in entries:
            origin = report_item_source(desc)
            list_type = report_list_type(desc)
            list_name = "无正式清单来源" if list_type == "临时工作" else f"{project} {origin} {list_type}"
            grouped.setdefault((project, origin, list_type), []).append((desc, progress))
    for (project, origin, list_type), entries in sorted(grouped.items()):
        stats = project_stats(entries)
        rows.append(
            {
                "project": project,
                "origin": origin,
                "list_type": list_type,
                "list_name": "无正式清单来源" if list_type == "临时工作" else f"{project} {origin} {list_type}",
                "total": stats["total"],
                "new_this_week": stats["total"],
                "completed_this_week": stats["completed"],
                "remaining": stats["in_progress"] + stats["not_started"] + stats["blocked"],
                "risks": stats["blocked"],
                "note": "按临时工作说明记录" if list_type == "临时工作" else status_label_from_stats(stats),
            }
        )
    return rows or [
        {
            "project": "未识别项目",
            "origin": "临时工作/内部优化",
            "list_type": "临时工作",
            "list_name": "无正式清单来源",
            "total": 0,
            "new_this_week": 0,
            "completed_this_week": 0,
            "remaining": 0,
            "risks": 0,
            "note": "未发现可归档事项",
        }
    ]

def project_source_type(entries: list[tuple[str, str]]) -> str:
    list_types = {report_list_type(desc) for desc, _ in entries}
    has_custom = "需求清单" in list_types
    has_bug = "Buglist" in list_types
    if has_custom and has_bug:
        return "混合"
    if has_custom:
        return "定制"
    if has_bug:
        return "Buglist"
    return "临时支持"

def project_source_note(entries: list[tuple[str, str]]) -> str:
    origins = sorted({report_item_source(desc) for desc, _ in entries})
    list_types = sorted({report_list_type(desc) for desc, _ in entries})
    if not entries:
        return "需成员补充需求单、Buglist 或临时安排来源"
    return f"来源：{'、'.join(origins)}；类型：{'、'.join(list_types)}"

def project_ledger_totals(entries: list[tuple[str, str]]) -> dict[str, int]:
    totals = {"feature_add": 0, "bug": 0, "bsp": 0, "other": 0, "total": 0}
    for desc, progress in entries:
        category = report_category(desc, progress)
        is_completed = progress_bucket(progress) == "completed"
        if not is_completed and re.search(r"\bBSP\b", f"{desc} {progress}", re.IGNORECASE):
            totals["bsp"] += 1
        elif category == "Bug处理":
            totals["bug"] += 1
        elif category in {"功能添加", "UI修改"}:
            totals["feature_add"] += 1
        else:
            totals["other"] += 1
    totals["total"] = totals["feature_add"] + totals["bug"] + totals["bsp"] + totals["other"]
    return totals

def canonical_report_project_label(value: Any) -> str:
    project = find_company_project(str(value or ""))
    return project or MISSING_REPORT_PROJECT

def normalized_report_items(items: dict[str, list[tuple[str, str]]]) -> dict[str, list[tuple[str, str]]]:
    normalized: dict[str, list[tuple[str, str]]] = {}
    for raw_project, entries in sorted(items.items()):
        project = canonical_report_project_label(raw_project)
        normalized.setdefault(project, []).extend(entries)
    return normalized

def project_ledger_rows(
    items: dict[str, list[tuple[str, str]]],
    project_customers: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    items = normalized_report_items(items)
    source_rows = weekly_source_rows(items)
    if not items:
        return [
            {
                "project": MISSING_REPORT_PROJECT,
                "source_type": "需补基本信息",
                "source_note": "未发现可归档事项",
                "start_date": "需成员确认",
                "duration_label": "需成员确认",
                "customer_name": MISSING_REPORT_CUSTOMER,
                "downstream_customer": "",
                "previous_week_remaining": 0,
                "totals": {"feature_add": 0, "bug": 0, "bsp": 0, "other": 0, "total": 0},
                "this_week_completed": 0,
                "cumulative_completed": 0,
                "remaining": 0,
                "expected_completion_week": "需成员确认",
                "status": "无事项",
                "risk": "无明确风险",
            }
        ]
    for project, entries in sorted(items.items()):
        stats = project_stats(entries)
        totals = project_ledger_totals(entries)
        remaining = max(0, totals["total"] - stats["completed"])
        project_sources = [row for row in source_rows if row["project"] == project]
        risk_items = [desc for desc, progress in entries if progress_bucket(progress) == "blocked"]
        rows.append(
            {
                "project": project,
                "source_type": project_source_type(entries),
                "source_note": project_source_note(entries),
                "start_date": "需成员确认",
                "duration_label": "需成员确认",
                "customer_name": report_customer_for_project(project, project_customers),
                "downstream_customer": report_downstream_customer_for_project(project, project_customers),
                "source_lists": project_sources,
                "totals": totals,
                "previous_week_remaining": remaining + stats["completed"],
                "this_week_completed": stats["completed"],
                "cumulative_completed": stats["completed"],
                "remaining": remaining,
                "expected_completion_week": "本周已完成" if remaining == 0 and totals["total"] else "需成员确认",
                "status": status_label_from_stats(stats),
                "risk": "；".join(compact_text(item, 80) for item in risk_items[:3]) if risk_items else "无明确风险",
            }
        )
    return rows

def report_project_customer_title(
    items: dict[str, list[tuple[str, str]]],
    project_customers: dict[str, Any] | None = None,
    *,
    max_projects: int = 3,
) -> str:
    normalized = normalized_report_items(items)
    labels: list[str] = []
    for project in sorted(normalized):
        context = report_customer_context_for_project(project, project_customers)
        labels.append(
            project_customer_title_label(
                project,
                context["customer_name"],
                context.get("downstream_customer", ""),
            )
        )
    if not labels:
        return f"{MISSING_REPORT_PROJECT}（{MISSING_REPORT_CUSTOMER}）"
    visible = labels[:max_projects]
    suffix = f"等 {len(labels)} 个项目" if len(labels) > max_projects else ""
    return "、".join(visible + ([suffix] if suffix else []))

def daily_material_summary(
    items: dict[str, list[tuple[str, str]]],
    *,
    max_projects: int = 3,
) -> str:
    normalized = normalized_report_items(items)
    if not normalized:
        return "今日未识别到有效工作内容，需补充日报材料。"
    parts: list[str] = []
    for project, entries in sorted(normalized.items())[:max_projects]:
        topics = "；".join(compact_text(re.sub(r"^(?:处理|修复|排查|完成|推进)\s*", "", desc), 32) for desc, _ in entries[:3])
        parts.append(f"{project}：今日处理{topics or '未明确事项'}。")
    if len(normalized) > max_projects:
        parts.append(f"另有 {len(normalized) - max_projects} 个项目。")
    return compact_text("".join(parts), 220)

def weekly_material_summary(
    items: dict[str, list[tuple[str, str]]],
    project_customers: dict[str, Any] | None = None,
    weekly_projects: list[dict[str, Any]] | None = None,
    *,
    max_projects: int = 3,
) -> str:
    if weekly_projects:
        parts = []
        for row in weekly_projects[:max_projects]:
            completed = weekly_fact_count_text(row, "completed_this_week_counts", include_bsp=False)
            remaining = weekly_fact_count_text(row, "remaining_counts", include_bsp=False)
            risk_text = "有风险" if meaningful_fact_list(row.get("risks"), {"无超过 3 天无进展事项。"}) else "无明确风险"
            parts.append(f"{row['project']}：本周完成 {completed}，剩余 {remaining}，{risk_text}。")
        if len(weekly_projects) > max_projects:
            parts.append(f"另有 {len(weekly_projects) - max_projects} 个项目。")
        return compact_text("".join(parts), 220)
    ledgers = project_ledger_rows(items, project_customers)
    visible = [row for row in ledgers if row["project"] not in {MISSING_REPORT_PROJECT, "未识别项目"}]
    if not visible:
        return "本周未识别到有效项目进展，需补充周报材料。"
    parts: list[str] = []
    for ledger in visible[:max_projects]:
        risk_text = "有风险" if ledger.get("risk") not in ("", "无明确风险") else "无明确风险"
        parts.append(
            f"{ledger['project']}：本周完成 {ledger['this_week_completed']} 项，"
            f"剩余 {ledger['remaining']} 项，{risk_text}。"
        )
    if len(visible) > max_projects:
        parts.append(f"另有 {len(visible) - max_projects} 个项目。")
    return compact_text("".join(parts), 220)

def daily_topic_for_entries(entries: list[tuple[str, str]]) -> str:
    topics = [compact_text(re.sub(r"^(?:处理|修复|排查|完成|推进)\s*", "", desc), 48) for desc, _ in entries[:3]]
    return "、".join(item for item in topics if item) or "今日工作事项需成员确认"

def daily_result_for_entries(entries: list[tuple[str, str]]) -> str:
    stats = project_stats(entries)
    if stats.get("blocked", 0):
        return "存在阻塞或超过预期未收敛事项，需要继续推进。"
    if stats.get("in_progress", 0) or stats.get("not_started", 0):
        return "部分事项仍在推进中，明日继续处理。"
    if stats.get("completed", 0):
        return "相关事项今日已完成或进入验证收尾。"
    return "当前结果需成员确认。"

def weekly_source_label(entries: list[tuple[str, str]]) -> str:
    sources = {report_item_source(desc) for desc, _ in entries}
    if "客户" in sources or "项目经理" in sources:
        return "客户需求文档"
    if "上级" in sources:
        return "TL指派"
    if "禅道" in sources:
        return "Buglist"
    if "测试" in sources:
        return "测试反馈"
    if any(re.search(r"\bBSP\b", desc, re.IGNORECASE) for desc, _ in entries):
        return "BSP配合"
    return "需成员确认"

def weekly_requirement_type(entries: list[tuple[str, str]]) -> str:
    counts = weekly_requirement_counts(entries)
    has_custom = counts["custom"] > 0
    has_bug = counts["bug"] > 0
    if has_custom and has_bug:
        return "混合"
    if has_bug:
        return "Buglist"
    if has_custom:
        return "纯定制"
    return "需成员确认"

def weekly_requirement_counts(entries: list[tuple[str, str]], *, buckets: set[str] | None = None) -> dict[str, int]:
    counts = {"custom": 0, "bug": 0, "bsp": 0}
    completed_scope = buckets == {"completed"}
    for desc, progress in entries:
        if buckets is not None and progress_bucket(progress) not in buckets:
            continue
        text = f"{desc} {progress}"
        if not completed_scope and re.search(r"\bBSP\b", text, re.IGNORECASE):
            counts["bsp"] += 1
        elif report_category(desc, progress) == "Bug处理" or report_list_type(desc) == "Buglist":
            counts["bug"] += 1
        else:
            counts["custom"] += 1
    return counts

def format_requirement_counts(counts: dict[str, int], *, include_bsp: bool) -> str:
    total = counts["custom"] + counts["bug"] + (counts["bsp"] if include_bsp else 0)
    parts = [f"定制 {counts['custom']}", f"Bug {counts['bug']}"]
    if include_bsp:
        parts.append(f"BSP {counts['bsp']}")
    return f"{total} 项（{'、'.join(parts)}）"


def normalize_fact_counts(value: Any) -> dict[str, int]:
    result = {"custom": 0, "bug": 0, "bsp": 0}
    if not isinstance(value, dict):
        return result
    for key in result:
        try:
            result[key] = max(0, int(value.get(key, 0) or 0))
        except (TypeError, ValueError):
            result[key] = 0
    return result


def meaningful_fact_list(value: Any, ignored: set[str] | None = None) -> list[str]:
    rows = value if isinstance(value, list) else []
    ignored = ignored or set()
    return [str(item).strip() for item in rows if str(item).strip() and str(item).strip() not in ignored]


def weekly_fact_count_text(row: dict[str, Any], key: str, *, include_bsp: bool) -> str:
    counts = normalize_fact_counts(row.get(key))
    return format_requirement_counts(counts, include_bsp=include_bsp)

def weekly_risks(entries: list[tuple[str, str]]) -> list[str]:
    risks = [compact_text(desc, 120) for desc, progress in entries if progress_bucket(progress) == "blocked"]
    return risks or ["无超过 3 天无进展事项。"]

def weekly_dependencies(entries: list[tuple[str, str]]) -> list[str]:
    dependencies = [
        compact_text(desc, 120)
        for desc, progress in entries
        if re.search(r"依赖|等待|客户确认|外部|第三方|\bBSP\b|测试反馈", f"{desc} {progress}", re.IGNORECASE)
    ]
    return dependencies or ["无外部依赖事项。"]

def write_daily_report(
    lines: list[str],
    items: dict[str, list[tuple[str, str]]],
    patches: list[PatchInfo],
    project_customers: dict[str, Any] | None = None,
) -> None:
    items = normalized_report_items(items)
    if not items:
        items = {MISSING_REPORT_PROJECT: [("未形成有效工作记录", "需补充真实工作记录")]}
    lines += ["## 一、今日概况", ""]
    for project, entries in sorted(items.items()):
        context = report_customer_context_for_project(project, project_customers)
        lines += [
            f"### {project_customer_heading(project, context['customer_name'], context.get('downstream_customer', ''))}",
            "",
            f"- 今日主题：{daily_topic_for_entries(entries)}",
            f"- 当前结果：{daily_result_for_entries(entries)}",
            "",
        ]
    lines += ["## 二、今日工作", ""]
    for project, entries in sorted(items.items()):
        context = report_customer_context_for_project(project, project_customers)
        lines += [f"### {project_customer_heading(project, context['customer_name'], context.get('downstream_customer', ''))}", ""]
        for index, (desc, progress) in enumerate(entries, start=1):
            lines += [
                f"#### {index}. {report_item_name(desc)}",
                "",
                "做了什么：",
                f"- {desc}",
                "",
                "怎么做的：",
                "- 根据 Codex 会话记录、工程修改、命令执行和材料证据整理实际处理过程。",
                "",
                "结果：",
                f"- {progress}",
                "",
            ]
    lines += ["## 三、明日重点", ""]
    for project, entries in sorted(items.items()):
        context = report_customer_context_for_project(project, project_customers)
        lines += [
            f"### {project_customer_heading(project, context['customer_name'], context.get('downstream_customer', ''))}",
            "",
            f"- {next_step_for_entries(entries, 'daily')}",
            "",
        ]

def write_weekly_report(
    lines: list[str],
    items: dict[str, list[tuple[str, str]]],
    patches: list[PatchInfo],
    project_customers: dict[str, Any] | None = None,
    weekly_projects: list[dict[str, Any]] | None = None,
) -> None:
    items = normalized_report_items(items)
    if not items:
        items = {MISSING_REPORT_PROJECT: [("未形成有效工作记录", "需补充真实工作记录")]}
    ledgers = project_ledger_rows(items, project_customers)
    lines += [
        "## 一、本周概况",
        "",
    ]
    if weekly_projects:
        for row in weekly_projects:
            project = str(row["project"])
            context = row_customer_context(row)
            lines += [
                f"### {project_customer_heading(project, context['customer_name'], context['downstream_customer'])}",
                "",
                str(row.get("week_summary") or "需补充真实工作记录。"),
                "",
                f"- 接到文档时间：{row.get('received_date') or '需成员确认'}",
                f"- 来源说明：{row.get('source') or '需成员确认'}",
                f"- 需求类型：{row.get('requirement_type') or '需成员确认'}",
                f"- 需求结构：{weekly_fact_count_text(row, 'requirement_structure_counts', include_bsp=True)}",
                f"- 本周完成：{weekly_fact_count_text(row, 'completed_this_week_counts', include_bsp=False)}",
                f"- 当前剩余：{weekly_fact_count_text(row, 'remaining_counts', include_bsp=True)}",
                f"- 预计完成：{row.get('expected_finish') or '需成员确认'}",
                "",
            ]
    else:
        for ledger in ledgers:
            project = str(ledger["project"])
            entries = items.get(project, [])
            all_counts = weekly_requirement_counts(entries)
            completed_counts = weekly_requirement_counts(entries, buckets={"completed"})
            remaining_counts = weekly_requirement_counts(entries, buckets={"in_progress", "not_started", "blocked"})
            lines += [
                f"### {project_customer_heading(project, ledger['customer_name'], ledger.get('downstream_customer', ''))}",
                "",
                f"本周围绕 {project_customer_heading(project, ledger['customer_name'], ledger.get('downstream_customer', ''))} 项目推进：{next_step_for_entries(entries, 'weekly') if entries else '需补充真实工作记录。'}",
                "",
                f"- 接到文档时间：{ledger['start_date']}",
                f"- 来源说明：{weekly_source_label(entries)}",
                f"- 需求类型：{weekly_requirement_type(entries)}",
                f"- 需求结构：{format_requirement_counts(all_counts, include_bsp=True)}",
                f"- 本周完成：{format_requirement_counts(completed_counts, include_bsp=False)}",
                f"- 当前剩余：{format_requirement_counts(remaining_counts, include_bsp=True)}",
                f"- 预计完成：{ledger['expected_completion_week']}",
                "",
            ]
    lines += ["", "## 二、项目详情", ""]
    detail_rows = weekly_projects or [
        {
            "project": ledger["project"],
            "customer": ledger["customer_name"],
            "downstream_customer": ledger.get("downstream_customer", ""),
            "completed_items": [desc for desc, progress in items.get(str(ledger["project"]), []) if progress_bucket(progress) == "completed"],
            "remaining_items": [desc for desc, progress in items.get(str(ledger["project"]), []) if progress_bucket(progress) != "completed"],
            "risks": weekly_risks(items.get(str(ledger["project"]), [])),
            "dependencies": weekly_dependencies(items.get(str(ledger["project"]), [])),
        }
        for ledger in ledgers
    ]
    for row in detail_rows:
        project = str(row["project"])
        context = row_customer_context(row)
        completed = meaningful_fact_list(row.get("completed_items"))
        unfinished = meaningful_fact_list(row.get("remaining_items"))
        risks = meaningful_fact_list(row.get("risks")) or ["无超过 3 天无进展事项。"]
        dependencies = meaningful_fact_list(row.get("dependencies")) or ["无外部依赖事项。"]
        lines += [
            f"### {project_customer_heading(project, context['customer_name'], context['downstream_customer'])}",
            "",
            "#### 1. 本周完成",
            "",
            *(f"- {compact_text(item, 120)}" for item in (completed or ["暂无明确完成项"])),
            "",
            "#### 2. 当前剩余",
            "",
            *(f"- {compact_text(item, 120)}" for item in (unfinished or ["无明确剩余项"])),
            "",
            "#### 3. 风险 / 依赖",
            "",
            "风险：",
            "",
            *(f"- {item}" for item in risks),
            "",
            "依赖：",
            "",
            *(f"- {item}" for item in dependencies),
            "",
        ]
    lines += ["## 三、下周计划", ""]
    plan_rows = weekly_projects or [
        {
            "project": ledger["project"],
            "customer": ledger["customer_name"],
            "downstream_customer": ledger.get("downstream_customer", ""),
            "next_week_plan": [next_step_for_entries(items.get(str(ledger["project"]), []), "weekly")],
        }
        for ledger in ledgers
    ]
    for row in plan_rows:
        project = str(row["project"])
        context = row_customer_context(row)
        plans = meaningful_fact_list(row.get("next_week_plan")) or ["继续补充真实工作记录并推进未闭环事项。"]
        lines += [
            f"### {project_customer_heading(project, context['customer_name'], context['downstream_customer'])}",
            "",
            *(f"- {plan}" for plan in plans),
            "",
        ]

def report_view_payload(
    report_type: str,
    date: dt.date,
    week_key: str,
    config: dict[str, str],
    items: dict[str, list[tuple[str, str]]],
    patches: list[PatchInfo],
    summary: str,
    project_customers: dict[str, Any] | None = None,
    weekly_projects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    items = normalized_report_items(items)
    if not items:
        items = {MISSING_REPORT_PROJECT: [("未形成有效工作记录", "需补充真实工作记录")]}
    material_name = report_project_customer_title(items, project_customers)
    material_summary = (
        daily_material_summary(items)
        if report_type == "daily"
        else weekly_material_summary(items, project_customers, weekly_projects)
    )
    payload: dict[str, Any] = {
        "schema": "akbs-report-view-human-v1",
        "report_type": report_type,
        "material_name": material_name,
        "material_summary": material_summary,
        "report_date": date.isoformat(),
        "week_range": week_key if report_type == "weekly" else "",
        "display_date": weekly_display_date(date) if report_type == "weekly" else date.isoformat(),
        "member_alias": config["member_alias"],
        "member_name": config["member_name"],
    }
    if report_type == "daily":
        projects: list[dict[str, Any]] = []
        for project, entries in sorted(items.items()):
            context = report_customer_context_for_project(project, project_customers)
            customer = context["customer_name"]
            work_items = []
            for desc, progress in entries:
                work_items.append(
                    {
                        "name": report_item_name(desc),
                        "did": [desc],
                        "how": ["根据 Codex 会话记录、工程修改、命令执行和材料证据整理实际处理过程。"],
                        "result": progress,
                    }
                )
            projects.append(
                add_downstream_customer({
                    "project": project,
                    "customer": customer,
                    "customer_name": customer,
                    "today_topic": daily_topic_for_entries(entries),
                    "current_result": daily_result_for_entries(entries),
                    "work_items": work_items,
                    "tomorrow_focus": [next_step_for_entries(entries, "daily")],
                }, context.get("downstream_customer", ""))
            )
        payload.update(
            {
                "projects": projects,
            }
        )
        return {"kind": "report_view", "payload": payload}

    if weekly_projects:
        projects = []
        for row in weekly_projects:
            context = row_customer_context(row)
            customer = context["customer_name"]
            projects.append(
                add_downstream_customer({
                    "project": str(row["project"]),
                    "customer": customer,
                    "customer_name": customer,
                    "week_summary": str(row.get("week_summary") or "需补充真实工作记录。"),
                    "received_date": str(row.get("received_date") or "需成员确认"),
                    "source": str(row.get("source") or "需成员确认"),
                    "requirement_type": str(row.get("requirement_type") or "需成员确认"),
                    "requirement_structure": weekly_fact_count_text(row, "requirement_structure_counts", include_bsp=True),
                    "completed_this_week": weekly_fact_count_text(row, "completed_this_week_counts", include_bsp=False),
                    "remaining": weekly_fact_count_text(row, "remaining_counts", include_bsp=True),
                    "expected_finish": str(row.get("expected_finish") or "需成员确认"),
                    "completed_items": meaningful_fact_list(row.get("completed_items")) or ["暂无明确完成项"],
                    "remaining_items": meaningful_fact_list(row.get("remaining_items")) or ["无明确剩余项"],
                    "risks": meaningful_fact_list(row.get("risks")) or ["无超过 3 天无进展事项。"],
                    "dependencies": meaningful_fact_list(row.get("dependencies")) or ["无外部依赖事项。"],
                    "next_week_plan": meaningful_fact_list(row.get("next_week_plan")),
                }, context["downstream_customer"])
            )
        payload.update({"projects": projects})
        return {"kind": "report_view", "payload": payload}

    projects: list[dict[str, Any]] = []
    ledgers = project_ledger_rows(items, project_customers)
    for ledger in ledgers:
        project = str(ledger["project"])
        customer = str(ledger["customer_name"])
        downstream_customer = str(ledger.get("downstream_customer") or "")
        entries = items.get(project, [])
        all_counts = weekly_requirement_counts(entries)
        completed_counts = weekly_requirement_counts(entries, buckets={"completed"})
        remaining_counts = weekly_requirement_counts(entries, buckets={"in_progress", "not_started", "blocked"})
        completed = [compact_text(desc, 120) for desc, progress in entries if progress_bucket(progress) == "completed"]
        remaining = [compact_text(desc, 120) for desc, progress in entries if progress_bucket(progress) != "completed"]
        projects.append(
            add_downstream_customer({
                "project": project,
                "customer": customer,
                "customer_name": customer,
                "week_summary": f"本周围绕 {project_customer_heading(project, customer, downstream_customer)} 项目推进：{next_step_for_entries(entries, 'weekly') if entries else '需补充真实工作记录。'}",
                "received_date": str(ledger.get("start_date") or "需成员确认"),
                "source": weekly_source_label(entries),
                "requirement_type": weekly_requirement_type(entries),
                "requirement_structure": format_requirement_counts(all_counts, include_bsp=True),
                "completed_this_week": format_requirement_counts(completed_counts, include_bsp=False),
                "remaining": format_requirement_counts(remaining_counts, include_bsp=True),
                "expected_finish": str(ledger.get("expected_completion_week") or "需成员确认"),
                "completed_items": completed or ["暂无明确完成项"],
                "remaining_items": remaining or ["无明确剩余项"],
                "risks": weekly_risks(entries),
                "dependencies": weekly_dependencies(entries),
                "next_week_plan": [next_step_for_entries(entries, "weekly")],
            }, downstream_customer)
        )
    payload.update({"projects": projects})
    return {"kind": "report_view", "payload": payload}

def write_report(
    package_dir: Path,
    report_type: str,
    date: dt.date,
    week_key: str,
    config: dict[str, str],
    items: dict[str, list[tuple[str, str]]],
    patches: list[PatchInfo],
    project_customers: dict[str, Any] | None = None,
    weekly_projects: list[dict[str, Any]] | None = None,
) -> Path:
    report_path = package_dir / f"{report_type}.md"
    title_key = ymd(date) if report_type == "daily" else week_key
    title = "日报" if report_type == "daily" else "周报"
    lines = [f"# {title_key}_{config['member_name']}_{title}", ""]
    if report_type == "daily":
        write_daily_report(lines, items, patches, project_customers)
    else:
        write_weekly_report(lines, items, patches, project_customers, weekly_projects)
    markdown = "\n".join(lines).rstrip() + "\n"
    report_path.write_text(emphasize_report_project_names(markdown), encoding="utf-8")
    return report_path

def write_report_view(
    package_dir: Path,
    report_type: str,
    date: dt.date,
    week_key: str,
    config: dict[str, str],
    items: dict[str, list[tuple[str, str]]],
    patches: list[PatchInfo],
    summary: str,
    project_customers: dict[str, Any] | None = None,
    weekly_projects: list[dict[str, Any]] | None = None,
) -> str:
    rel = materials_rel("display", "report_view.json")
    write_json(
        package_dir / rel,
        report_view_payload(report_type, date, week_key, config, items, patches, summary, project_customers, weekly_projects),
    )
    return rel
