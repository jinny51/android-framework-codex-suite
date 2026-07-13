from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from android_framework_ops.http_client import HttpClientFailure, request_json
from android_framework_ops.knowledge_rules import find_company_project

from ..config import expanded_path, local_now, parse_bool, submission_api_base_url
from ..io_utils import read_json_file
from .common import iter_local_manifests, replacement_run_id


WEEKLY_FACTS_SCHEMA = "akbs-weekly-project-facts-v1"
WEEKLY_FACT_SOURCES_SCHEMA = "akbs-weekly-fact-sources-v1"
COUNT_KEYS = ("custom", "bug", "bsp")
ALLOWED_SOURCES = {"客户需求文档", "TL指派", "Buglist", "测试反馈", "BSP配合"}
ALLOWED_REQUIREMENT_TYPES = {"纯定制", "Buglist", "混合"}
MISSING_VALUES = {"", "unknown", "需成员确认", "需成员补充", "待确认"}
EMPTY_ITEM_VALUES = {
    "暂无明确完成项",
    "无明确剩余项",
    "无超过 3 天无进展事项。",
    "无外部依赖事项。",
}
COUNT_PART_RE = re.compile(r"(定制|Bug|BSP)\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class WeeklyFactsResult:
    projects: list[dict[str, Any]]
    evidence: dict[str, Any]


def clean_text(value: Any, fallback: str = "") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or fallback


def prefer_fact(value: Any, fallback: str) -> str:
    text = clean_text(value)
    return fallback if text in MISSING_VALUES else text


def clean_list(value: Any) -> list[str]:
    rows = value if isinstance(value, list) else [value] if value else []
    result: list[str] = []
    for row in rows:
        text = clean_text(row)
        if not text or text in EMPTY_ITEM_VALUES or text in result:
            continue
        result.append(text)
    return result


def zero_counts() -> dict[str, int]:
    return {key: 0 for key in COUNT_KEYS}


def normalize_counts(value: Any) -> dict[str, int]:
    if isinstance(value, dict):
        result = zero_counts()
        aliases = {"custom": "custom", "定制": "custom", "bug": "bug", "Bug": "bug", "bsp": "bsp", "BSP": "bsp"}
        for raw_key, raw_value in value.items():
            key = aliases.get(str(raw_key))
            if not key:
                continue
            try:
                result[key] = max(0, int(raw_value))
            except (TypeError, ValueError):
                continue
        return result
    text = clean_text(value)
    result = zero_counts()
    for label, raw_count in COUNT_PART_RE.findall(text):
        key = "custom" if label == "定制" else label.lower()
        result[key] = int(raw_count)
    return result


def count_total(counts: dict[str, int]) -> int:
    return sum(int(counts.get(key, 0) or 0) for key in COUNT_KEYS)


def item_category(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\bBSP\b|固件|SDK|驱动|板级", text, re.IGNORECASE):
        return "bsp"
    if any(token in lowered for token in ("bug", "问题", "缺陷", "报错", "失败", "异常", "修复")):
        return "bug"
    return "custom"


def progress_completed(value: Any) -> bool:
    text = clean_text(value)
    if any(token in text for token in ("阻塞", "失败", "未完成", "待处理", "处理中", "进行中", "待验证", "验证中")):
        return False
    return bool(re.search(r"(?:^|[^0-9])100\s*%|已完成|已解决|验证完成|测试通过|构建通过|修复完成", text))


def item_key(value: str) -> str:
    text = re.sub(r"TV[DEAI][A-Za-z0-9]+", "", value, flags=re.IGNORECASE)
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "", text).lower()


def same_item(left: str, right: str) -> bool:
    a = item_key(left)
    b = item_key(right)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 8 and (a in b or b in a))


def add_unique(rows: list[str], value: str) -> None:
    if value and not any(same_item(value, existing) for existing in rows):
        rows.append(value)


def unwrap_report_view(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    if value.get("kind") == "report_view" and isinstance(value.get("payload"), dict):
        return dict(value["payload"])
    return dict(value)


def report_item_view(item: dict[str, Any]) -> dict[str, Any]:
    for key in ("standard_view", "report_view"):
        view = unwrap_report_view(item.get(key))
        if view:
            return view
    return {}


def _api_enabled(config: dict[str, str]) -> bool:
    return parse_bool(config.get("weekly_history_api_enabled", "true"))


def _api_timeout(config: dict[str, str]) -> float:
    try:
        return max(0.5, min(10.0, float(config.get("weekly_history_api_timeout_seconds", "3"))))
    except ValueError:
        return 3.0


def fetch_current_report_items(config: dict[str, str], package_kind: str, month: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"page": 1, "page_size": 100, "kind": package_kind, "month": month})
    url = f"{submission_api_base_url(config).rstrip('/')}/member/me/packages?{query}"
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "application/json", "X-AKBS-User": config["member_alias"]},
    )
    payload = request_json(request, timeout=_api_timeout(config))
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("AKBS member report history response missing items")
    return [item for item in items if isinstance(item, dict)]


def _manifest_report_view(package_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    display = files.get("display") if isinstance(files.get("display"), list) else []
    for rel in display:
        path = package_dir / str(rel)
        if path.is_file():
            return unwrap_report_view(read_json_file(path))
    return {}


def local_current_report_items(
    config: dict[str, str],
    package_kind: str,
    identities: set[str],
) -> list[dict[str, Any]]:
    candidates: list[tuple[Path, dict[str, Any], str]] = []
    for bucket, package_dir, manifest in iter_local_manifests(config):
        if bucket != "submitted" or manifest.get("member_alias") != config.get("member_alias"):
            continue
        if manifest.get("package_kind") != package_kind:
            continue
        identity = str(manifest.get("date") if package_kind == "daily_trace" else manifest.get("week_range") or "")
        if identity not in identities:
            continue
        candidates.append((package_dir, manifest, identity))
    superseded = {replacement_run_id(manifest) for _, manifest, _ in candidates if replacement_run_id(manifest)}
    rows: list[dict[str, Any]] = []
    for package_dir, manifest, identity in candidates:
        run_id = str(manifest.get("run_id") or package_dir.name)
        if run_id in superseded:
            continue
        view = _manifest_report_view(package_dir, manifest)
        if not view:
            continue
        rows.append(
            {
                "package_key": f"local:{identity}:{run_id}",
                "package_kind": package_kind,
                "report_date": identity if package_kind == "daily_trace" else "",
                "week_range": identity if package_kind == "weekly_trace" else "",
                "report_view": view,
            }
        )
    return rows


def _target_months(dates: Iterable[dt.date]) -> list[str]:
    return sorted({date.strftime("%Y-%m") for date in dates})


def load_history(
    config: dict[str, str],
    start: dt.date,
    end: dt.date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    current_dates = {start + dt.timedelta(days=offset) for offset in range((end - start).days + 1)}
    current_date_keys = {date.isoformat() for date in current_dates}
    previous_start = start - dt.timedelta(days=7)
    previous_end = end - dt.timedelta(days=7)
    previous_key = f"{previous_start:%Y%m%d}-{previous_end:%Y%m%d}"
    daily_items: list[dict[str, Any]] = []
    weekly_items: list[dict[str, Any]] = []
    api_errors: list[str] = []
    api_complete = _api_enabled(config)
    if api_complete:
        try:
            for month in _target_months(current_dates):
                daily_items.extend(fetch_current_report_items(config, "daily_trace", month))
            for month in _target_months((previous_start, previous_end)):
                weekly_items.extend(fetch_current_report_items(config, "weekly_trace", month))
        except (HttpClientFailure, ValueError) as error:
            api_complete = False
            code = error.result.code if isinstance(error, HttpClientFailure) else "invalid_success_response"
            api_errors.append(code)
    daily_items = [item for item in daily_items if clean_text(item.get("report_date")) in current_date_keys]
    weekly_items = [item for item in weekly_items if clean_text(item.get("week_range")) == previous_key]
    source = "akbs_api" if api_complete else "local_submitted"
    if not api_complete:
        daily_items = local_current_report_items(config, "daily_trace", current_date_keys)
        weekly_items = local_current_report_items(config, "weekly_trace", {previous_key})
    provenance = {
        "source": source,
        "api_errors": sorted(set(api_errors)),
        "daily_package_keys": sorted({clean_text(item.get("package_key")) for item in daily_items if item.get("package_key")}),
        "previous_weekly_package_keys": sorted({clean_text(item.get("package_key")) for item in weekly_items if item.get("package_key")}),
        "previous_week_range": previous_key,
    }
    return daily_items, weekly_items, provenance


def _weekly_project_row(value: dict[str, Any]) -> dict[str, Any]:
    project = find_company_project(clean_text(value.get("project"))) or clean_text(value.get("project"), "需成员补充项目名")
    customer = clean_text(value.get("customer") or value.get("customer_name"), "需成员补充客户名")
    return {
        "project": project,
        "customer": customer,
        "customer_name": customer,
        "week_summary": clean_text(value.get("week_summary"), "需成员补充本周主要进展"),
        "received_date": clean_text(value.get("received_date"), "需成员确认"),
        "source": clean_text(value.get("source"), "需成员确认"),
        "requirement_type": clean_text(value.get("requirement_type"), "需成员确认"),
        "requirement_structure_counts": normalize_counts(value.get("requirement_structure_counts", value.get("requirement_structure"))),
        "completed_this_week_counts": normalize_counts(value.get("completed_this_week_counts", value.get("completed_this_week"))),
        "remaining_counts": normalize_counts(value.get("remaining_counts", value.get("remaining"))),
        "expected_finish": clean_text(value.get("expected_finish"), "需成员确认"),
        "completed_items": clean_list(value.get("completed_items")),
        "remaining_items": clean_list(value.get("remaining_items")),
        "risks": clean_list(value.get("risks")) or ["无超过 3 天无进展事项。"],
        "dependencies": clean_list(value.get("dependencies")) or ["无外部依赖事项。"],
        "next_week_plan": clean_list(value.get("next_week_plan")),
    }


def load_explicit_facts(path: Path, week_key: str) -> list[dict[str, Any]]:
    payload = read_json_file(path)
    if payload.get("schema") != WEEKLY_FACTS_SCHEMA:
        raise SystemExit(f"weekly facts schema 必须是 {WEEKLY_FACTS_SCHEMA}")
    if clean_text(payload.get("week_range")) != week_key:
        raise SystemExit(f"weekly facts week_range 必须等于 {week_key}")
    projects = payload.get("projects")
    if not isinstance(projects, list) or not projects:
        raise SystemExit("weekly facts projects 必须是非空数组")
    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, item in enumerate(projects):
        if not isinstance(item, dict):
            errors.append(f"projects[{index}] 必须是对象")
            continue
        project = find_company_project(clean_text(item.get("project"))) or f"projects[{index}]"
        if project.startswith("projects["):
            errors.append(f"{project}.project 必须是公司项目名")
        for field in ("customer", "week_summary", "received_date", "source", "requirement_type", "expected_finish"):
            if clean_text(item.get(field)) in MISSING_VALUES:
                errors.append(f"{project}.{field} 必须提供")
        try:
            dt.date.fromisoformat(clean_text(item.get("received_date")))
        except ValueError:
            errors.append(f"{project}.received_date 必须是 YYYY-MM-DD")
        if item.get("source") not in ALLOWED_SOURCES:
            errors.append(f"{project}.source 非法")
        if item.get("requirement_type") not in ALLOWED_REQUIREMENT_TYPES:
            errors.append(f"{project}.requirement_type 非法")
        if "下周继续" in clean_text(item.get("week_summary")):
            errors.append(f"{project}.week_summary 不得用下周计划代替本周进展")
        count_fields = {
            "requirement_structure": normalize_counts(item.get("requirement_structure")),
            "completed_this_week": normalize_counts(item.get("completed_this_week")),
            "remaining": normalize_counts(item.get("remaining")),
        }
        for field, counts in count_fields.items():
            raw = item.get(field)
            if not isinstance(raw, dict) or any(key not in raw for key in COUNT_KEYS):
                errors.append(f"{project}.{field} 必须包含 custom/bug/bsp")
            invalid_counts = isinstance(raw, dict) and any(
                not isinstance(raw.get(key), int) or isinstance(raw.get(key), bool) or int(raw.get(key)) < 0
                for key in COUNT_KEYS
            )
            if invalid_counts:
                errors.append(f"{project}.{field} 计数必须是非负整数")
        total = count_fields["requirement_structure"]
        completed = count_fields["completed_this_week"]
        remaining = count_fields["remaining"]
        for key in COUNT_KEYS:
            if completed[key] + remaining[key] > total[key]:
                errors.append(f"{project}.{key} 本周完成加当前剩余不能超过需求结构")
        normalized.append(_weekly_project_row(item))
    if errors:
        raise SystemExit("weekly facts 校验失败: " + "；".join(errors))
    return normalized


def _daily_project_records(items: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, str]]]]:
    metadata: dict[str, dict[str, Any]] = {}
    records: dict[str, dict[str, dict[str, str]]] = {}
    for item in sorted(items, key=lambda row: (clean_text(row.get("report_date")), clean_text(row.get("package_key")))):
        report_date = clean_text(item.get("report_date"))
        view = report_item_view(item)
        projects = view.get("projects") if isinstance(view.get("projects"), list) else []
        for raw_project in projects:
            if not isinstance(raw_project, dict):
                continue
            project = find_company_project(clean_text(raw_project.get("project")))
            if not project:
                continue
            metadata.setdefault(project, {})["customer"] = clean_text(
                raw_project.get("customer") or raw_project.get("customer_name"),
                metadata.get(project, {}).get("customer", ""),
            )
            focuses = clean_list(raw_project.get("tomorrow_focus"))
            if focuses:
                metadata[project]["latest_focus"] = focuses
            work_items = raw_project.get("work_items") if isinstance(raw_project.get("work_items"), list) else []
            for work_item in work_items:
                if not isinstance(work_item, dict):
                    continue
                name = clean_text(work_item.get("name"))
                did = clean_list(work_item.get("did"))
                text = name or (did[0] if did else "")
                if not text:
                    continue
                result = clean_text(work_item.get("result") or raw_project.get("current_result"))
                records.setdefault(project, {})[item_key(text) or text] = {
                    "date": report_date,
                    "text": text,
                    "progress": result,
                }
    return metadata, {project: list(project_records.values()) for project, project_records in records.items()}


def _previous_week_projects(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        view = report_item_view(item)
        projects = view.get("projects") if isinstance(view.get("projects"), list) else []
        for raw_project in projects:
            if not isinstance(raw_project, dict):
                continue
            row = _weekly_project_row(raw_project)
            project = find_company_project(row["project"])
            if project:
                row["project"] = project
                result.setdefault(project, row)
    return result


def _history_project_row(
    project: str,
    previous: dict[str, Any] | None,
    daily_meta: dict[str, Any],
    daily_records: list[dict[str, str]],
    *,
    period_start: dt.date,
    as_of: dt.date,
) -> tuple[dict[str, Any], list[str]]:
    prior = dict(previous or {})
    total_counts = normalize_counts(prior.get("requirement_structure_counts"))
    remaining_counts = normalize_counts(prior.get("remaining_counts"))
    completed_counts = zero_counts()
    prior_remaining = clean_list(prior.get("remaining_items"))
    current_remaining = list(prior_remaining)
    completed_items: list[str] = []
    current_unfinished: list[str] = []

    for record in sorted(daily_records, key=lambda item: item.get("date", "")):
        text = record["text"]
        category = item_category(text)
        matched = next((item for item in prior_remaining if same_item(text, item)), "")
        if progress_completed(record.get("progress")):
            add_unique(completed_items, text)
            completed_counts[category] += 1
            if matched:
                current_remaining = [item for item in current_remaining if not same_item(item, matched)]
                matched_category = item_category(matched)
                if remaining_counts[matched_category] > 0:
                    remaining_counts[matched_category] -= 1
            else:
                total_counts[category] += 1
        else:
            add_unique(current_unfinished, text)
            if not matched:
                total_counts[category] += 1
                remaining_counts[category] += 1
    for item in current_unfinished:
        add_unique(current_remaining, item)

    all_current_text = " ".join([*completed_items, *current_remaining])
    inferred_source = "需成员确认"
    if re.search(r"禅道|buglist", all_current_text, re.IGNORECASE):
        inferred_source = "Buglist"
    elif re.search(r"客户|客诉|现场|需求文档", all_current_text):
        inferred_source = "客户需求文档"
    elif re.search(r"测试|回归|复现", all_current_text):
        inferred_source = "测试反馈"
    elif re.search(r"\bBSP\b|固件|SDK|驱动|板级", all_current_text, re.IGNORECASE):
        inferred_source = "BSP配合"
    elif re.search(r"TL|负责人|上级", all_current_text, re.IGNORECASE):
        inferred_source = "TL指派"

    has_custom = total_counts["custom"] > 0
    has_bug = total_counts["bug"] > 0
    inferred_type = "混合" if has_custom and has_bug else "Buglist" if has_bug else "纯定制" if has_custom else "需成员确认"
    customer = clean_text(prior.get("customer") or daily_meta.get("customer"), "需成员补充客户名")
    if completed_items:
        summary = "本周完成" + "、".join(completed_items[:3]) + ("等事项。" if len(completed_items) > 3 else "。")
    elif current_remaining:
        summary = "本周持续推进" + "、".join(current_remaining[:3]) + ("等事项。" if len(current_remaining) > 3 else "。")
    else:
        summary = "本周无可确认的项目进展。"
    blocked = [record["text"] for record in daily_records if re.search(r"阻塞|失败|等待|依赖", record.get("progress", ""))]
    risks = clean_list(prior.get("risks"))
    for item in blocked:
        add_unique(risks, item)
    for item in current_remaining:
        recorded_dates: list[dt.date] = []
        for record in daily_records:
            if not same_item(item, record.get("text", "")):
                continue
            try:
                recorded_dates.append(dt.date.fromisoformat(record.get("date", "")))
            except ValueError:
                continue
        last_progress = max(recorded_dates) if recorded_dates else period_start - dt.timedelta(days=1)
        if (as_of - last_progress).days > 3:
            add_unique(risks, f"超过 3 天无进展：{item}（最后记录 {last_progress.isoformat()}）")
    dependencies = clean_list(prior.get("dependencies"))
    for record in daily_records:
        if re.search(r"依赖|等待|客户确认|外部|第三方|\bBSP\b|测试反馈", f"{record['text']} {record.get('progress', '')}", re.IGNORECASE):
            add_unique(dependencies, record["text"])
    plans = clean_list(daily_meta.get("latest_focus")) or clean_list(prior.get("next_week_plan"))
    if not plans and current_remaining:
        plans = ["继续推进：" + "、".join(current_remaining[:3])]

    row = {
        "project": project,
        "customer": customer,
        "customer_name": customer,
        "week_summary": summary,
        "received_date": clean_text(prior.get("received_date"), "需成员确认"),
        "source": prefer_fact(prior.get("source"), inferred_source),
        "requirement_type": prefer_fact(prior.get("requirement_type"), inferred_type),
        "requirement_structure_counts": total_counts,
        "completed_this_week_counts": completed_counts,
        "remaining_counts": remaining_counts,
        "expected_finish": "本周已完成" if count_total(remaining_counts) == 0 and count_total(total_counts) else clean_text(prior.get("expected_finish"), "需成员确认"),
        "completed_items": completed_items,
        "remaining_items": current_remaining,
        "risks": risks or ["无超过 3 天无进展事项。"],
        "dependencies": dependencies or ["无外部依赖事项。"],
        "next_week_plan": plans,
    }
    missing: list[str] = []
    for field in ("customer", "received_date", "source", "requirement_type", "expected_finish"):
        if clean_text(row.get(field)) in MISSING_VALUES or clean_text(row.get(field)).startswith("需成员补充"):
            missing.append(f"{project}.{field}")
    if not row["next_week_plan"] and count_total(row["remaining_counts"]):
        missing.append(f"{project}.next_week_plan")
    if previous and count_total(normalize_counts(previous.get("remaining_counts"))) > len(prior_remaining) and daily_records:
        missing.append(f"{project}.remaining_item_identity")
    return row, missing


def _project_missing_fields(row: dict[str, Any]) -> list[str]:
    project = clean_text(row.get("project"), "unknown")
    missing: list[str] = []
    for field in ("customer", "received_date", "source", "requirement_type", "expected_finish"):
        value = clean_text(row.get(field))
        if value in MISSING_VALUES or value.startswith("需成员补充"):
            missing.append(f"{project}.{field}")
    if not clean_list(row.get("next_week_plan")) and count_total(normalize_counts(row.get("remaining_counts"))):
        missing.append(f"{project}.next_week_plan")
    return missing


def _session_fallback_projects(
    start: dt.date,
    items: dict[str, list[tuple[str, str]]],
    project_customers: dict[str, str],
    *,
    synthetic: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    projects: list[dict[str, Any]] = []
    missing: list[str] = []
    for raw_project, entries in sorted(items.items()):
        project = find_company_project(raw_project)
        if not project:
            continue
        total_counts = zero_counts()
        completed_counts = zero_counts()
        remaining_counts = zero_counts()
        completed_items: list[str] = []
        remaining_items: list[str] = []
        for description, progress in entries:
            category = item_category(description)
            total_counts[category] += 1
            if progress_completed(progress):
                completed_counts[category] += 1
                add_unique(completed_items, description)
            else:
                remaining_counts[category] += 1
                add_unique(remaining_items, description)
        has_custom = total_counts["custom"] > 0
        has_bug = total_counts["bug"] > 0
        requirement_type = "混合" if has_custom and has_bug else "Buglist" if has_bug else "纯定制" if has_custom else "需成员确认"
        if completed_items:
            summary = "本周完成" + "、".join(completed_items[:3]) + ("等事项。" if len(completed_items) > 3 else "。")
        else:
            summary = "本周持续推进" + "、".join(remaining_items[:3]) + ("等事项。" if len(remaining_items) > 3 else "。")
        row = {
            "project": project,
            "customer": clean_text(project_customers.get(project), "需成员补充客户名"),
            "customer_name": clean_text(project_customers.get(project), "需成员补充客户名"),
            "week_summary": summary,
            "received_date": start.isoformat() if synthetic else "需成员确认",
            "source": "TL指派" if synthetic else "需成员确认",
            "requirement_type": requirement_type,
            "requirement_structure_counts": total_counts,
            "completed_this_week_counts": completed_counts,
            "remaining_counts": remaining_counts,
            "expected_finish": "本周已完成" if count_total(remaining_counts) == 0 else "下周继续收敛" if synthetic else "需成员确认",
            "completed_items": completed_items,
            "remaining_items": remaining_items,
            "risks": ["无超过 3 天无进展事项。"],
            "dependencies": ["无外部依赖事项。"],
            "next_week_plan": ["继续推进：" + "、".join(remaining_items[:3])] if remaining_items else ["保持交付和验证记录完整。"],
        }
        projects.append(row)
        if not synthetic:
            missing.extend(_project_missing_fields(row))
    return projects, missing


def project_rows_to_items(projects: list[dict[str, Any]]) -> dict[str, list[tuple[str, str]]]:
    result: dict[str, list[tuple[str, str]]] = {}
    for row in projects:
        project = clean_text(row.get("project"), "需成员补充项目名")
        entries: list[tuple[str, str]] = []
        entries.extend((item, "已完成") for item in clean_list(row.get("completed_items")))
        entries.extend((item, "进行中") for item in clean_list(row.get("remaining_items")))
        if not entries:
            entries.append((clean_text(row.get("week_summary"), "未形成有效工作记录"), "进行中"))
        result[project] = entries
    return result


def facts_hash(projects: list[dict[str, Any]]) -> str:
    payload = json.dumps(projects, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_weekly_facts(
    config: dict[str, str],
    start: dt.date,
    end: dt.date,
    week_key: str,
    *,
    explicit_path: str = "",
    synthetic: bool = False,
    fallback_items: dict[str, list[tuple[str, str]]] | None = None,
    project_customers: dict[str, str] | None = None,
) -> WeeklyFactsResult:
    missing_fields: list[str] = []
    if explicit_path:
        projects = load_explicit_facts(expanded_path(explicit_path), week_key)
        provenance: dict[str, Any] = {"source": "explicit_weekly_facts", "daily_package_keys": [], "previous_weekly_package_keys": []}
        for row in projects:
            missing_fields.extend(_project_missing_fields(row))
    elif synthetic:
        provenance = {"source": "synthetic_fixture", "daily_package_keys": [], "previous_weekly_package_keys": []}
        projects, synthetic_missing = _session_fallback_projects(
            start,
            fallback_items or {},
            project_customers or {},
            synthetic=True,
        )
        missing_fields.extend(synthetic_missing)
    else:
        daily_items, weekly_items, provenance = load_history(config, start, end)
        as_of = min(end, local_now(config).date())
        daily_meta, daily_records = _daily_project_records(daily_items)
        previous = _previous_week_projects(weekly_items)
        session_supplements: list[str] = []
        for raw_project, entries in sorted((fallback_items or {}).items()):
            project = find_company_project(raw_project)
            if not project or project in daily_records:
                continue
            daily_records[project] = [
                {"date": as_of.isoformat(), "text": description, "progress": progress}
                for description, progress in entries
            ]
            customer = clean_text((project_customers or {}).get(project))
            if customer:
                daily_meta.setdefault(project, {})["customer"] = customer
            session_supplements.append(project)
        provenance["session_supplement_projects"] = session_supplements
        if not daily_items and not weekly_items and session_supplements:
            provenance["source"] = "session_fallback"
        projects = []
        project_names = sorted(set(previous) | set(daily_records))
        for project in project_names:
            row, project_missing = _history_project_row(
                project,
                previous.get(project),
                daily_meta.get(project, {}),
                daily_records.get(project, []),
                period_start=start,
                as_of=as_of,
            )
            projects.append(row)
            missing_fields.extend(project_missing)
    if not projects:
        projects, fallback_missing = _session_fallback_projects(
            start,
            fallback_items or {},
            project_customers or {},
            synthetic=synthetic,
        )
        missing_fields.extend(fallback_missing)
        provenance["source"] = "session_fallback" if not synthetic else "synthetic_fixture"
    evidence = {
        "schema": WEEKLY_FACT_SOURCES_SCHEMA,
        "week_range": week_key,
        **provenance,
        "project_count": len(projects),
        "missing_fields": sorted(set(missing_fields)),
        "facts_sha256": facts_hash(projects),
    }
    return WeeklyFactsResult(projects, evidence)
