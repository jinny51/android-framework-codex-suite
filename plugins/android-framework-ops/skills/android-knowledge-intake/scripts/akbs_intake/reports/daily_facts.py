from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from android_framework_ops.knowledge_rules import find_company_project

from ..config import expanded_path
from ..io_utils import read_json_file
from ..report_sessions import (
    REPORT_MISSING_CUSTOMER_VALUES,
    clean_report_customer_name,
    normalize_report_customer_context,
    report_customer_context_for_project,
)
from .document_work import (
    DOCUMENT_WORK_TYPE,
    clean_document_name,
    validate_daily_documents,
)
from .scope import ALLOWED_WORK_TYPES, PROJECT_WORK_TYPES, clean_scope_text, report_scope_key


DAILY_FACTS_SCHEMA = "akbs-daily-work-facts-v2"
LEGACY_DAILY_FACTS_SCHEMA = "akbs-daily-project-facts-v1"
DAILY_FACT_SOURCES_SCHEMA = "akbs-daily-fact-sources-v2"
LEGACY_DAILY_FACT_SOURCES_SCHEMA = "akbs-daily-fact-sources-v1"
DAILY_STATUS_VALUES = {"已完成", "处理中", "待验证", "阻塞"}
NO_TOMORROW_FOCUS_VALUES = {"无", "无。", "暂无", "暂无。", "没有", "没有。"}
OLD_DAILY_HOW_TEXT = "根据 Codex 会话记录、工程修改、命令执行和材料证据整理实际处理过程。"


@dataclass(frozen=True)
class DailyFactsResult:
    projects: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    evidence: dict[str, Any]


def clean_list(value: Any) -> list[str]:
    rows = value if isinstance(value, list) else [value] if value else []
    result: list[str] = []
    for row in rows:
        text = clean_scope_text(row)
        if text and text not in result:
            result.append(text)
    return result


def normalize_work_item(value: Any) -> dict[str, Any]:
    row = value if isinstance(value, dict) else {}
    return {
        "name": clean_scope_text(row.get("name")),
        "did": clean_list(row.get("did")),
        "how": clean_list(row.get("how")),
        "result": clean_scope_text(row.get("result")),
        "status": clean_scope_text(row.get("status")),
    }


def fallback_work_items(
    project: str,
    project_items: dict[str, list[tuple[str, str]]],
    daily_work_items: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows = [normalize_work_item(item) for item in daily_work_items.get(project, [])]
    if rows:
        return rows
    return [
        {
            "name": clean_scope_text(description),
            "did": [clean_scope_text(description)],
            "how": ["未从授权会话中提取到具体处理过程，需成员补充。"],
            "result": clean_scope_text(progress),
            "status": status_from_progress(progress),
        }
        for description, progress in project_items.get(project, [])
        if clean_scope_text(description)
    ]


def status_from_progress(value: Any) -> str:
    text = clean_scope_text(value)
    if any(token in text for token in ("阻塞", "失败", "报错")):
        return "阻塞"
    if any(token in text for token in ("待验证", "验证中", "待回归")):
        return "待验证"
    if any(token in text for token in ("已完成", "已解决", "通过", "成功", "100%")):
        return "已完成"
    return "处理中"


def topic_from_work_items(work_items: list[dict[str, Any]]) -> str:
    names = [clean_scope_text(item.get("name")) for item in work_items]
    return "、".join(name for name in names[:3] if name) or "今日工作事项需成员确认"


def result_from_work_items(work_items: list[dict[str, Any]]) -> str:
    statuses = {clean_scope_text(item.get("status")) for item in work_items}
    if "阻塞" in statuses:
        return "存在阻塞事项，需要继续推进。"
    if statuses & {"处理中", "待验证"}:
        return "部分事项仍在推进或验证中。"
    if statuses == {"已完成"}:
        return "相关事项今日已完成。"
    return "当前结果需成员确认。"


def focus_from_work_items(work_items: list[dict[str, Any]]) -> list[str]:
    unfinished = [
        clean_scope_text(item.get("name"))
        for item in work_items
        if clean_scope_text(item.get("status")) != "已完成"
    ]
    return ["继续推进：" + "、".join(item for item in unfinished[:3] if item)] if any(unfinished) else ["无"]


def normalize_tomorrow_focus(
    value: Any,
    *,
    field_present: bool,
    work_items: list[dict[str, Any]],
) -> list[str]:
    if not field_present:
        return focus_from_work_items(work_items)
    focus = [item for item in clean_list(value) if item not in NO_TOMORROW_FOCUS_VALUES]
    return focus or ["无"]


def normalize_daily_project(
    value: dict[str, Any],
    *,
    project_items: dict[str, list[tuple[str, str]]],
    daily_work_items: dict[str, list[dict[str, Any]]],
    scope_count_by_project: dict[str, int],
) -> dict[str, Any]:
    raw_project = clean_scope_text(value.get("project"))
    project = find_company_project(raw_project) or raw_project
    raw_work_items = value.get("work_items")
    if isinstance(raw_work_items, list) and raw_work_items:
        work_items = [normalize_work_item(item) for item in raw_work_items]
    elif scope_count_by_project.get(project, 0) <= 1:
        work_items = fallback_work_items(project, project_items, daily_work_items)
    else:
        work_items = []
    tomorrow_focus = normalize_tomorrow_focus(
        value.get("tomorrow_focus"),
        field_present="tomorrow_focus" in value,
        work_items=work_items,
    )
    customer = clean_scope_text(value.get("customer") or value.get("customer_name"))
    row: dict[str, Any] = {
        "project": project,
        "customer": customer,
        "customer_name": customer,
        "work_type": clean_scope_text(value.get("work_type") or value.get("type")),
        "today_topic": clean_scope_text(value.get("today_topic")) or topic_from_work_items(work_items),
        "current_result": clean_scope_text(value.get("current_result")) or result_from_work_items(work_items),
        "work_items": work_items,
        "tomorrow_focus": tomorrow_focus,
    }
    downstream = clean_scope_text(
        value.get("downstream_customer")
        or value.get("customer_of_customer")
        or value.get("end_customer")
    )
    if downstream:
        row["downstream_customer"] = downstream
    app_name = clean_scope_text(value.get("app_name"))
    if app_name:
        row["app_name"] = app_name
    return row


def normalize_daily_document(value: dict[str, Any]) -> dict[str, Any]:
    raw_items = value.get("work_items")
    work_items = (
        [normalize_work_item(item) for item in raw_items if isinstance(item, dict)]
        if isinstance(raw_items, list)
        else []
    )
    tomorrow_focus = normalize_tomorrow_focus(
        value.get("tomorrow_focus"),
        field_present="tomorrow_focus" in value,
        work_items=work_items,
    )
    return {
        "work_type": DOCUMENT_WORK_TYPE,
        "document_name": clean_document_name(value.get("document_name")),
        "today_topic": clean_scope_text(value.get("today_topic")) or topic_from_work_items(work_items),
        "current_result": clean_scope_text(value.get("current_result")) or result_from_work_items(work_items),
        "work_items": work_items,
        "tomorrow_focus": tomorrow_focus,
    }


def validate_daily_projects(
    projects: list[dict[str, Any]],
    *,
    expected_project_customers: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    seen_customers: dict[str, tuple[str, str]] = {}
    seen_scopes: dict[tuple[str, str, str], int] = {}
    expected = {
        str(project).upper(): normalize_report_customer_context(context)
        for project, context in (expected_project_customers or {}).items()
    }
    for index, row in enumerate(projects):
        prefix = f"projects[{index}]"
        project = clean_scope_text(row.get("project"))
        canonical = find_company_project(project)
        if not canonical or canonical.upper() != project.upper():
            errors.append(f"{prefix}.project 必须是规范公司项目名")
            continue
        customer = clean_scope_text(row.get("customer") or row.get("customer_name"))
        downstream = clean_scope_text(row.get("downstream_customer"))
        if customer in REPORT_MISSING_CUSTOMER_VALUES or not clean_report_customer_name(customer):
            errors.append(f"{prefix}.customer 必须提供直接客户")
        if downstream and not clean_report_customer_name(downstream):
            errors.append(f"{prefix}.downstream_customer 不是有效客户名称")
        identity = (customer, downstream)
        previous = seen_customers.get(canonical)
        if previous and previous != identity:
            errors.append(f"{prefix} 与同项目其他范围的客户链不一致")
        else:
            seen_customers[canonical] = identity
        expected_context = expected.get(canonical.upper(), {})
        if expected_context and identity != (
            clean_scope_text(expected_context.get("customer_name")),
            clean_scope_text(expected_context.get("downstream_customer")),
        ):
            errors.append(f"{prefix}.customer 客户链与当前会话已确认身份不一致")
        work_type = clean_scope_text(row.get("work_type"))
        if work_type not in PROJECT_WORK_TYPES:
            errors.append(f"{prefix}.work_type 只能是 Patch 或 App")
        app_name = clean_scope_text(row.get("app_name"))
        if work_type == "App" and not app_name:
            errors.append(f"{prefix}.app_name 类型为 App 时必须提供")
        if work_type == "Patch" and app_name:
            errors.append(f"{prefix}.app_name 类型为 Patch 时不得提供")
        scope = report_scope_key(row)
        if scope in seen_scopes:
            errors.append(f"{prefix} 与 projects[{seen_scopes[scope]}] 的统计对象重复")
        else:
            seen_scopes[scope] = index
        for field in ("today_topic", "current_result"):
            if not clean_scope_text(row.get(field)):
                errors.append(f"{prefix}.{field} 必须提供")
        work_items = row.get("work_items")
        if not isinstance(work_items, list) or not work_items:
            errors.append(
                f"{prefix}.work_items 必须至少包含一项；同一项目有多个 Patch/App 范围时必须按范围明确填写"
            )
            work_items = []
        unfinished = False
        for item_index, item in enumerate(work_items):
            item_prefix = f"{prefix}.work_items[{item_index}]"
            if not isinstance(item, dict):
                errors.append(f"{item_prefix} 必须是对象")
                continue
            for field in ("name", "result"):
                if not clean_scope_text(item.get(field)):
                    errors.append(f"{item_prefix}.{field} 必须提供")
            for field in ("did", "how"):
                values = item.get(field)
                if not isinstance(values, list) or not clean_list(values):
                    errors.append(f"{item_prefix}.{field} 必须是非空数组")
            if OLD_DAILY_HOW_TEXT in clean_list(item.get("how")):
                errors.append(f"{item_prefix}.how 不得使用固定套话")
            status = clean_scope_text(item.get("status"))
            if status not in DAILY_STATUS_VALUES:
                errors.append(f"{item_prefix}.status 必须是已完成、处理中、待验证或阻塞")
            unfinished = unfinished or status in {"处理中", "待验证", "阻塞"}
        focus = row.get("tomorrow_focus")
        if not isinstance(focus, list):
            errors.append(f"{prefix}.tomorrow_focus 必须是数组")
        elif unfinished and not clean_list(focus):
            errors.append(f"{prefix}.tomorrow_focus 存在未完成事项时必须提供")
    return errors


def load_explicit_facts(
    path: Path,
    report_date: dt.date,
    *,
    project_items: dict[str, list[tuple[str, str]]],
    daily_work_items: dict[str, list[dict[str, Any]]],
    expected_project_customers: dict[str, Any] | None = None,
    include_documents: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = read_json_file(path)
    schema = payload.get("schema")
    if schema not in {DAILY_FACTS_SCHEMA, LEGACY_DAILY_FACTS_SCHEMA}:
        raise SystemExit(f"daily facts schema 必须是 {DAILY_FACTS_SCHEMA}")
    if clean_scope_text(payload.get("report_date")) != report_date.isoformat():
        raise SystemExit(f"daily facts report_date 必须等于 {report_date.isoformat()}")
    raw_projects = payload.get("projects")
    raw_documents = payload.get("documents", [])
    if not isinstance(raw_projects, list):
        raise SystemExit("daily facts projects 必须是数组")
    if not isinstance(raw_documents, list):
        raise SystemExit("daily facts documents 必须是数组")
    if schema == LEGACY_DAILY_FACTS_SCHEMA and raw_documents:
        raise SystemExit(f"文档工作必须改用 {DAILY_FACTS_SCHEMA}")
    if not raw_projects and not raw_documents:
        raise SystemExit("daily facts projects 和 documents 至少提供一项")
    project_names = [
        find_company_project(clean_scope_text(item.get("project"))) or clean_scope_text(item.get("project"))
        for item in raw_projects
        if isinstance(item, dict)
    ]
    scope_count_by_project = {project: project_names.count(project) for project in set(project_names)}
    projects = [
        normalize_daily_project(
            item,
            project_items=project_items,
            daily_work_items=daily_work_items,
            scope_count_by_project=scope_count_by_project,
        )
        for item in raw_projects
        if isinstance(item, dict)
    ]
    documents = [normalize_daily_document(item) for item in raw_documents if isinstance(item, dict)]
    errors = validate_daily_projects(projects, expected_project_customers=expected_project_customers)
    errors.extend(validate_daily_documents(documents))
    if len(projects) != len(raw_projects):
        errors.append("projects 中每一项都必须是对象")
    if len(documents) != len(raw_documents):
        errors.append("documents 中每一项都必须是对象")
    if errors:
        raise SystemExit("daily facts 校验失败: " + "；".join(errors))
    return (projects, documents) if include_documents else projects


def fallback_projects(
    *,
    project_items: dict[str, list[tuple[str, str]]],
    daily_work_items: dict[str, list[dict[str, Any]]],
    project_customers: dict[str, Any],
    synthetic: bool,
    inferred_scopes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    scopes_by_project: dict[str, list[dict[str, Any]]] = {}
    if not synthetic:
        for scope in inferred_scopes:
            if clean_scope_text(scope.get("work_type")) == DOCUMENT_WORK_TYPE:
                continue
            raw_project = clean_scope_text(scope.get("project"))
            project = find_company_project(raw_project) or raw_project
            if project:
                scopes_by_project.setdefault(project, []).append(scope)
    has_document_scopes = any(
        clean_scope_text(scope.get("work_type")) == DOCUMENT_WORK_TYPE
        for scope in inferred_scopes
    )
    item_projects = (
        {project for project in project_items if find_company_project(project)}
        if has_document_scopes
        else set(project_items)
    )
    project_names = sorted(item_projects | set(scopes_by_project))
    for project in project_names:
        context = report_customer_context_for_project(project, project_customers)
        scope_rows = scopes_by_project.get(project) or [{}]
        for scope in scope_rows:
            raw_scope_items = scope.get("work_items")
            work_items = (
                [normalize_work_item(item) for item in raw_scope_items if isinstance(item, dict)]
                if isinstance(raw_scope_items, list) and raw_scope_items
                else fallback_work_items(project, project_items, daily_work_items)
            )
            work_type = "Patch" if synthetic else clean_scope_text(scope.get("work_type")) or "需成员确认"
            row: dict[str, Any] = {
                "project": project,
                "customer": context["customer_name"],
                "customer_name": context["customer_name"],
                "work_type": work_type,
                "today_topic": topic_from_work_items(work_items),
                "current_result": result_from_work_items(work_items),
                "work_items": work_items,
                "tomorrow_focus": focus_from_work_items(work_items),
            }
            app_name = clean_scope_text(scope.get("app_name"))
            if work_type == "App" and app_name:
                row["app_name"] = app_name
            if context.get("downstream_customer"):
                row["downstream_customer"] = context["downstream_customer"]
            projects.append(row)
    return projects


def fallback_documents(*, inferred_scopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for scope in inferred_scopes:
        if clean_scope_text(scope.get("work_type")) != DOCUMENT_WORK_TYPE:
            continue
        raw_items = scope.get("work_items")
        work_items = (
            [normalize_work_item(item) for item in raw_items if isinstance(item, dict)]
            if isinstance(raw_items, list)
            else []
        )
        documents.append(
            {
                "work_type": DOCUMENT_WORK_TYPE,
                "document_name": clean_document_name(scope.get("document_name")),
                "today_topic": topic_from_work_items(work_items),
                "current_result": result_from_work_items(work_items),
                "work_items": work_items,
                "tomorrow_focus": focus_from_work_items(work_items),
            }
        )
    return documents


def facts_hash(projects: list[dict[str, Any]], documents: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        {"projects": projects, "documents": documents},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_daily_facts(
    report_date: dt.date,
    *,
    explicit_path: str = "",
    synthetic: bool = False,
    project_items: dict[str, list[tuple[str, str]]] | None = None,
    daily_work_items: dict[str, list[dict[str, Any]]] | None = None,
    project_customers: dict[str, Any] | None = None,
    inferred_scopes: list[dict[str, Any]] | None = None,
) -> DailyFactsResult:
    project_items = project_items or {}
    daily_work_items = daily_work_items or {}
    project_customers = project_customers or {}
    inferred_scopes = inferred_scopes or []
    if explicit_path:
        path = expanded_path(explicit_path)
        projects, documents = load_explicit_facts(
            path,
            report_date,
            project_items=project_items,
            daily_work_items=daily_work_items,
            expected_project_customers=project_customers,
            include_documents=True,
        )
        source = "explicit_daily_facts"
        source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        projects = fallback_projects(
            project_items=project_items,
            daily_work_items=daily_work_items,
            project_customers=project_customers,
            synthetic=synthetic,
            inferred_scopes=inferred_scopes,
        )
        documents = fallback_documents(inferred_scopes=inferred_scopes)
        inference_complete = bool(inferred_scopes) and all(
            clean_scope_text(row.get("work_type")) in ALLOWED_WORK_TYPES
            and (
                (clean_scope_text(row.get("work_type")) == "Patch")
                or (
                    clean_scope_text(row.get("work_type")) == "App"
                    and bool(clean_scope_text(row.get("app_name")))
                )
                or (
                    clean_scope_text(row.get("work_type")) == DOCUMENT_WORK_TYPE
                    and bool(clean_document_name(row.get("document_name")))
                )
            )
            and not bool(row.get("inference_conflict"))
            for row in inferred_scopes
        )
        if synthetic:
            source = "synthetic_fixture"
        elif inference_complete:
            source = "session_scope_inference"
        else:
            source = "session_draft"
        source_sha256 = ""
    missing_fields: list[str] = []
    if not explicit_path and not synthetic:
        for row in projects:
            project = clean_scope_text(row.get("project"))
            work_type = clean_scope_text(row.get("work_type"))
            if work_type not in ALLOWED_WORK_TYPES:
                missing_fields.append(f"{project}.work_type")
            elif work_type == "App" and not clean_scope_text(row.get("app_name")):
                missing_fields.append(f"{project}.app_name")
        for row in documents:
            if not clean_document_name(row.get("document_name")):
                missing_fields.append("document.document_name")
    scope_inference = []
    if not explicit_path and not synthetic:
        for row in inferred_scopes:
            item: dict[str, Any] = {
                "project": clean_scope_text(row.get("project")),
                "work_type": clean_scope_text(row.get("work_type")) or "unresolved",
                "basis": clean_list(row.get("inference_basis")),
                "conflict": bool(row.get("inference_conflict")),
            }
            if clean_scope_text(row.get("app_name")):
                item["app_name"] = clean_scope_text(row.get("app_name"))
            if clean_document_name(row.get("document_name")):
                item["document_name"] = clean_document_name(row.get("document_name"))
            scope_inference.append(item)
    evidence = {
        "schema": DAILY_FACT_SOURCES_SCHEMA,
        "report_date": report_date.isoformat(),
        "source": source,
        "source_sha256": source_sha256,
        "project_count": len({clean_scope_text(row.get("project")) for row in projects}),
        "document_count": len(documents),
        "work_scope_count": len(projects) + len(documents),
        "missing_fields": sorted(set(missing_fields)),
        "scope_inference": scope_inference,
        "facts_sha256": facts_hash(projects, documents),
    }
    return DailyFactsResult(projects, documents, evidence)


def project_rows_to_items(projects: list[dict[str, Any]]) -> dict[str, list[tuple[str, str]]]:
    result: dict[str, list[tuple[str, str]]] = {}
    for row in projects:
        project = clean_scope_text(row.get("project"))
        for item in row.get("work_items", []) if isinstance(row.get("work_items"), list) else []:
            if not isinstance(item, dict):
                continue
            name = clean_scope_text(item.get("name"))
            progress = " ".join(
                value
                for value in (
                    clean_scope_text(item.get("status")),
                    clean_scope_text(item.get("result")),
                )
                if value
            )
            if project and name:
                result.setdefault(project, []).append((name, progress))
    return result
