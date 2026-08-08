from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any, Callable

from android_framework_ops.knowledge_rules import find_company_project

from ..report_sessions import clean_report_customer_name
from ..session_privacy import session_evidence_errors
from .render import REPORT_MISSING_CUSTOMER_VALUES, REPORT_MISSING_PROJECT_VALUES
from .weekly_facts import WEEKLY_FACT_SOURCES_SCHEMA


RequireFile = Callable[[Any, str], Path | None]
LoadEvidence = Callable[[list[Any]], dict[str, dict[str, Any]]]
ReadReferencedJson = Callable[[Path, str], dict[str, Any] | None]


FORBIDDEN_REPORT_VIEW_FIELDS = {
    "ui_card",
    "one_line_summary",
    "display_title",
    "daily_overview",
    "work_items",
    "items",
    "outputs",
    "next_steps",
    "project_overview",
    "source_lists",
    "source_category_stats",
    "project_ledgers",
    "weekly_detail_sections",
    "weekly_progress_summary",
    "patch_outputs",
    "delivery_verifications",
}
WEEKLY_ALLOWED_SOURCES = {"CR", "TL", "PM", "TE", "BSP"}
WEEKLY_ALLOWED_PROJECT_ROLES = {"主责", "协作"}
WEEKLY_EMPTY_PLAN_VALUES = {"无", "无。", "暂无", "暂无。", "无下周计划", "暂无下周计划"}
WEEKLY_COUNT_RE = re.compile(
    r"^(?P<label>共|本周完成|当前剩余)\s+(?P<total>\d+)\s*项(?:：(?P<parts>.+))?$"
)
WEEKLY_COUNT_PART_RE = re.compile(r"^(需求|移植|Bug|BSP)\s+(\d+)$", re.IGNORECASE)
DAILY_STATUS_VALUES = {"已完成", "处理中", "待验证", "阻塞"}
OLD_DAILY_HOW_TEXT = "根据 Codex 会话记录、工程修改、命令执行和材料证据整理实际处理过程。"
MISSING_PROJECT_GUIDANCE = (
    "当前会话未关联项目，请补充项目名和客户名；例如：TVE1086U 青鸾云；"
    "如有客户的客户：TVE1091U AOC 福建移动高清。"
    "建议后续先创建项目，再在项目下创建开发会话。"
)


def report_project_customer_errors(rel: str, rows: Any, label: str) -> list[str]:
    row_errors: list[str] = []
    if not isinstance(rows, list) or not rows:
        row_errors.append(f"{rel} payload.{label} 必须包含项目和客户信息")
        return row_errors
    seen_projects: dict[str, tuple[int, str, str]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            row_errors.append(f"{rel} payload.{label}[{index}] 必须是对象")
            continue
        project = str(row.get("project") or "").strip()
        canonical_project = find_company_project(project)
        if project in REPORT_MISSING_PROJECT_VALUES or not canonical_project:
            row_errors.append(f"{rel} payload.{label}[{index}].project 未识别到公司项目名。{MISSING_PROJECT_GUIDANCE}")
        elif project.upper() != canonical_project.upper():
            row_errors.append(
                f"{rel} payload.{label}[{index}].project 只能填写规范项目编号 {canonical_project}；其他内容应写入事项字段"
            )
        customer = str(row.get("customer") or row.get("customer_name") or "").strip()
        compatibility_customer = str(row.get("customer_name") or "").strip()
        if customer and compatibility_customer and customer != compatibility_customer:
            row_errors.append(
                f"{rel} payload.{label}[{index}].customer 与 customer_name 必须一致"
            )
        if customer in REPORT_MISSING_CUSTOMER_VALUES or not clean_report_customer_name(customer):
            row_errors.append(
                f"{rel} payload.{label}[{index}].customer 缺少客户名，请按“项目名 客户名”补充；可选第三段为客户的客户，例如：TVE1091U AOC 福建移动高清"
            )
        downstream_customer = str(
            row.get("downstream_customer")
            or row.get("customer_of_customer")
            or row.get("end_customer")
            or ""
        ).strip()
        if downstream_customer and not clean_report_customer_name(downstream_customer):
            row_errors.append(
                f"{rel} payload.{label}[{index}].downstream_customer 不是有效的客户名称"
            )
        if canonical_project:
            identity = (customer, downstream_customer)
            previous = seen_projects.get(canonical_project)
            if previous:
                previous_index, previous_customer, previous_downstream = previous
                if identity == (previous_customer, previous_downstream):
                    row_errors.append(
                        f"{rel} payload.{label}[{index}].project 与 [{previous_index}] 重复；"
                        "同一项目只能有一行，具体工作内容应合并到事项数组"
                    )
                else:
                    row_errors.append(
                        f"{rel} payload.{label}[{index}] 与 [{previous_index}] 的 {canonical_project} 客户链冲突；"
                        "同一项目必须保留唯一客户链"
                    )
            else:
                seen_projects[canonical_project] = (index, customer, downstream_customer)
    return row_errors


def validate_daily_project_inference(
    *,
    manifest: dict[str, Any],
    evidence_by_kind: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    project_inference = evidence_by_kind.get("project_inference")
    if not project_inference:
        errors.append("daily_trace 缺少 project_inference evidence")
        return
    project_payload = project_inference.get("payload", {}) if isinstance(project_inference, dict) else {}
    project = str(project_payload.get("project") or "")
    if not project:
        errors.append("project_inference.project 必须提供")
    if project == "unknown":
        errors.append(f"project_inference.project 未识别到公司项目名。{MISSING_PROJECT_GUIDANCE}")
        if not isinstance(project_payload.get("checked_sources"), list) or not project_payload.get("checked_sources"):
            errors.append("unknown project_inference 必须记录 checked_sources")
        if not isinstance(project_payload.get("limits"), list) or not project_payload.get("limits"):
            errors.append("unknown project_inference 必须记录 limits")
    elif manifest.get("project") != project:
        errors.append("daily_trace manifest.project 必须等于 project_inference.project")
    customer = str(project_payload.get("customer_name") or "").strip()
    if project and project != "unknown" and (
        customer in REPORT_MISSING_CUSTOMER_VALUES or not clean_report_customer_name(customer)
    ):
        errors.append("project_inference.customer_name 缺少客户名，请按“项目名 客户名”补充；可选第三段为客户的客户，例如：TVE1091U AOC 福建移动高清")
    downstream_customer = str(project_payload.get("downstream_customer") or "").strip()
    if downstream_customer and not clean_report_customer_name(downstream_customer):
        errors.append("project_inference.downstream_customer 不是有效的客户名称")


def validate_work_findings(
    *,
    evidence_by_kind: dict[str, dict[str, Any]],
    package_status_values: set[str],
    errors: list[str],
) -> None:
    work_findings = evidence_by_kind.get("work_findings", {})
    payload = work_findings.get("payload", {}) if isinstance(work_findings, dict) else {}
    if not isinstance(payload.get("scanned_sources"), list) or not payload.get("scanned_sources"):
        errors.append("work_findings.scanned_sources 必须是非空数组")
    if not isinstance(payload.get("items", []), list):
        errors.append("work_findings.items 必须是数组")
    for item in payload.get("items", []) if isinstance(payload.get("items", []), list) else []:
        if "maturity" in item:
            errors.append("work_findings item 不允许使用 maturity；请使用 work_status")
        work_status = item.get("work_status")
        if work_status and work_status not in package_status_values:
            errors.append(f"work_findings item work_status 非法: {work_status}")


def validate_session_privacy_evidence(*, evidence_by_kind: dict[str, dict[str, Any]], errors: list[str]) -> None:
    evidence = evidence_by_kind.get("codex_sessions")
    if not isinstance(evidence, dict):
        errors.append("report trace 缺少 codex_sessions privacy evidence")
        return
    errors.extend(session_evidence_errors(evidence.get("payload")))


def validate_weekly_fact_sources(
    *,
    manifest: dict[str, Any],
    evidence_by_kind: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    evidence = evidence_by_kind.get("weekly_fact_sources")
    if not isinstance(evidence, dict):
        errors.append("weekly_trace 缺少 weekly_fact_sources evidence")
        return
    payload = evidence.get("payload")
    if not isinstance(payload, dict):
        errors.append("weekly_fact_sources payload 必须是对象")
        return
    if payload.get("schema") != WEEKLY_FACT_SOURCES_SCHEMA:
        errors.append(f"weekly_fact_sources.schema 必须是 {WEEKLY_FACT_SOURCES_SCHEMA}")
    if payload.get("week_range") != manifest.get("week_range"):
        errors.append("weekly_fact_sources.week_range 必须等于 manifest.week_range")
    try:
        project_count = int(payload.get("project_count") or 0)
    except (TypeError, ValueError):
        project_count = 0
    if project_count < 1:
        errors.append("周报未形成项目级事实，请补充有效日报、上一周周报或 --weekly-facts")
    missing = payload.get("missing_fields")
    if not isinstance(missing, list):
        errors.append("weekly_fact_sources.missing_fields 必须是数组")
    elif missing:
        errors.append("周报项目事实不完整，请补充后使用 --weekly-facts 重新生成: " + "、".join(str(item) for item in missing))
    identity_conflicts = payload.get("identity_conflicts", [])
    if not isinstance(identity_conflicts, list):
        errors.append("weekly_fact_sources.identity_conflicts 必须是数组")
    elif identity_conflicts:
        errors.append("周报项目客户链与当前会话已确认身份冲突，请修正结构化事实后重新生成")


def weekly_project_identity_consistency_errors(
    rel: str,
    rows: Any,
    expected_rows: Any,
) -> list[str]:
    if not isinstance(rows, list) or not isinstance(expected_rows, list) or not expected_rows:
        return []

    def identities(values: list[Any]) -> dict[str, tuple[str, str]]:
        result: dict[str, tuple[str, str]] = {}
        for value in values:
            if not isinstance(value, dict):
                continue
            project = find_company_project(str(value.get("project") or ""))
            customer = str(value.get("customer") or value.get("customer_name") or "").strip()
            downstream = str(value.get("downstream_customer") or "").strip()
            if project and customer:
                result[project] = (customer, downstream)
        return result

    actual = identities(rows)
    expected = identities(expected_rows)
    if actual == expected:
        return []
    return [
        f"{rel} payload.projects 项目客户身份必须与 project_inference.project_customers 来源证据一致"
    ]


def validate_daily_report_view_project(rel: str, index: int, project: dict[str, Any], errors: list[str]) -> None:
    for field in ("today_topic", "current_result"):
        if not project.get(field):
            errors.append(f"{rel} payload.projects[{index}].{field} 必须提供")
    for field in ("work_items", "tomorrow_focus"):
        if not isinstance(project.get(field), list):
            errors.append(f"{rel} payload.projects[{index}].{field} 必须是数组")
    work_items = project.get("work_items") if isinstance(project.get("work_items"), list) else []
    if not work_items:
        errors.append(f"{rel} payload.projects[{index}].work_items 必须至少包含一项今日工作")
    for item_index, item in enumerate(work_items):
        prefix = f"{rel} payload.projects[{index}].work_items[{item_index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        for field in ("name", "result"):
            if not str(item.get(field) or "").strip():
                errors.append(f"{prefix}.{field} 必须提供")
        for field in ("did", "how"):
            rows = item.get(field)
            if not isinstance(rows, list) or not any(str(value or "").strip() for value in rows):
                errors.append(f"{prefix}.{field} 必须是非空数组")
        if OLD_DAILY_HOW_TEXT in [str(value) for value in item.get("how", []) if isinstance(item.get("how"), list)]:
            errors.append(f"{prefix}.how 不得使用固定套话，必须写实际处理方法")
        if item.get("status") not in DAILY_STATUS_VALUES:
            errors.append(f"{prefix}.status 必须是已完成、处理中、待验证或阻塞")


def parse_weekly_count_text(
    value: Any,
    *,
    expected_label: str,
    allow_bsp: bool,
    field_path: str,
    errors: list[str],
) -> dict[str, int] | None:
    match = WEEKLY_COUNT_RE.fullmatch(str(value or "").strip())
    if not match or match.group("label") != expected_label:
        errors.append(f"{field_path} 计数格式非法，应使用“{expected_label} N 项：需求 N、移植 N、Bug N”")
        return None
    counts = {"demand": 0, "migration": 0, "bug": 0, "bsp": 0}
    label_keys = {"需求": "demand", "移植": "migration", "bug": "bug", "bsp": "bsp"}
    parts_text = str(match.group("parts") or "").strip()
    seen: set[str] = set()
    if parts_text:
        for part in re.split(r"、", parts_text):
            part_match = WEEKLY_COUNT_PART_RE.fullmatch(part.strip())
            if not part_match:
                errors.append(f"{field_path} 含非法分类: {part.strip()}")
                return None
            key = label_keys[part_match.group(1).lower()]
            count = int(part_match.group(2))
            if key in seen:
                errors.append(f"{field_path} 分类重复: {part_match.group(1)}")
                return None
            if count == 0:
                errors.append(f"{field_path} 为 0 的分类应省略")
            if key == "bsp" and not allow_bsp:
                errors.append(f"{field_path} 本周完成不得包含 BSP")
            seen.add(key)
            counts[key] = count
    total = int(match.group("total"))
    if total != sum(counts.values()):
        errors.append(f"{field_path} 合计与分类不一致")
    if total > 0 and not any(counts[key] > 0 for key in ("demand", "migration", "bug")):
        errors.append(f"{field_path} 至少要有一项需求、移植或 Bug，不能只填 BSP")
    return counts


def validate_weekly_report_view_project(rel: str, index: int, project: dict[str, Any], errors: list[str]) -> None:
    for old_field in ("received_date", "source", "requirement_type", "expected_finish"):
        if old_field in project:
            errors.append(f"{rel} payload.projects[{index}].{old_field} 是旧周报字段，不得继续提供")
    for field in (
        "week_summary",
        "project_role",
        "requirement_date",
        "requirement_source",
        "completed_this_week",
        "remaining",
    ):
        if not project.get(field):
            errors.append(f"{rel} payload.projects[{index}].{field} 必须提供")
    role = project.get("project_role")
    if role not in WEEKLY_ALLOWED_PROJECT_ROLES:
        errors.append(f"{rel} payload.projects[{index}].project_role 只能是主责或协作")
    if role == "主责" and not project.get("requirement_structure"):
        errors.append(f"{rel} payload.projects[{index}].requirement_structure 主责必须提供")
    if project.get("requirement_source") not in WEEKLY_ALLOWED_SOURCES:
        errors.append(
            f"{rel} payload.projects[{index}].requirement_source 只能是 CR、TL、PM、TE 或 BSP"
        )
    requirement_date = str(project.get("requirement_date") or "")
    try:
        valid_requirement_date = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", requirement_date))
        if valid_requirement_date:
            dt.date.fromisoformat(requirement_date)
    except ValueError:
        valid_requirement_date = False
    if not valid_requirement_date:
        errors.append(f"{rel} payload.projects[{index}].requirement_date 必须是 YYYY-MM-DD")
    if "下周继续" in str(project.get("week_summary") or ""):
        errors.append(f"{rel} payload.projects[{index}].week_summary 不得用下周计划代替本周进展")
    parsed_counts: dict[str, dict[str, int]] = {}
    count_specs = (
        ("requirement_structure", "共", True),
        ("completed_this_week", "本周完成", False),
        ("remaining", "当前剩余", True),
    )
    for field, label, allow_bsp in count_specs:
        if field == "requirement_structure" and not project.get(field):
            continue
        counts = parse_weekly_count_text(
            project.get(field),
            expected_label=label,
            allow_bsp=allow_bsp,
            field_path=f"{rel} payload.projects[{index}].{field}",
            errors=errors,
        )
        if counts is not None:
            parsed_counts[field] = counts
    if all(field in parsed_counts for field in ("requirement_structure", "completed_this_week", "remaining")):
        total = parsed_counts["requirement_structure"]
        completed = parsed_counts["completed_this_week"]
        remaining = parsed_counts["remaining"]
        for category in ("demand", "migration", "bug", "bsp"):
            if completed[category] + remaining[category] > total[category]:
                errors.append(f"{rel} payload.projects[{index}].{category} 本周完成加当前剩余不能超过项目总量")
    for field in ("completed_items", "remaining_items", "key_points", "risks", "dependencies", "next_week_plan"):
        if not isinstance(project.get(field), list):
            errors.append(f"{rel} payload.projects[{index}].{field} 必须是数组")
    next_week_plan = project.get("next_week_plan")
    effective_next_week_plan = (
        [str(item).strip() for item in next_week_plan if str(item).strip() not in WEEKLY_EMPTY_PLAN_VALUES and str(item).strip()]
        if isinstance(next_week_plan, list)
        else []
    )
    if isinstance(next_week_plan, list) and any(str(item).strip() in WEEKLY_EMPTY_PLAN_VALUES for item in next_week_plan):
        errors.append(
            f"{rel} payload.projects[{index}].next_week_plan 不得使用“无”或空计划占位；没有下周动作时应使用空数组"
        )
    if parsed_counts.get("remaining") and sum(parsed_counts["remaining"].values()) > 0 and not effective_next_week_plan:
        errors.append(f"{rel} payload.projects[{index}].next_week_plan 有剩余事项时必须提供")


def validate_report_view_payload(
    *,
    rel: str,
    report_type: str,
    manifest: dict[str, Any],
    view: dict[str, Any],
    expected_weekly_project_identities: Any = None,
    errors: list[str],
) -> None:
    for field in ("schema", "report_type", "material_name", "material_summary", "member_alias", "member_name", "display_date", "projects"):
        if not view.get(field):
            errors.append(f"{rel} payload.{field} 必须提供")
    if view.get("schema") != "akbs-report-view-human-v1":
        errors.append(f"{rel} payload.schema 必须是 akbs-report-view-human-v1")
    if view.get("report_type") != report_type:
        errors.append(f"{rel} payload.report_type 必须是 {report_type}")
    for field in sorted(FORBIDDEN_REPORT_VIEW_FIELDS & set(view)):
        errors.append(f"{rel} payload.{field} 是已废弃的 report_view 字段，新包不得提供")

    errors.extend(report_project_customer_errors(rel, view.get("projects"), "projects"))
    if report_type == "weekly":
        errors.extend(
            weekly_project_identity_consistency_errors(
                rel,
                view.get("projects"),
                expected_weekly_project_identities,
            )
        )
    if not isinstance(view.get("projects"), list):
        errors.append(f"{rel} payload.projects 必须是数组")
        return
    for index, project in enumerate(view.get("projects", [])):
        if not isinstance(project, dict):
            continue
        if report_type == "daily":
            validate_daily_report_view_project(rel, index, project, errors)
        else:
            validate_weekly_report_view_project(rel, index, project, errors)
    if report_type == "daily" and view.get("report_date") != manifest.get("date"):
        errors.append(f"{rel} payload.report_date 必须等于 manifest.date")
    if report_type == "weekly":
        if view.get("week_range") != manifest.get("week_range"):
            errors.append(f"{rel} payload.week_range 必须等于 manifest.week_range")
        if not view.get("display_date"):
            errors.append(f"{rel} payload.display_date 必须提供")


def validate_report_display_files(
    *,
    package_dir: Path,
    files: dict[str, Any],
    manifest: dict[str, Any],
    report_type: str,
    expected_weekly_project_identities: Any,
    require_file: RequireFile,
    read_referenced_json: ReadReferencedJson,
    errors: list[str],
) -> None:
    display_paths = files.get("display", [])
    if not isinstance(display_paths, list) or not display_paths:
        errors.append("report trace files.display 必须包含 report_view.json")
        display_paths = []
    for rel in display_paths:
        path = require_file(rel, "display")
        if not path:
            continue
        report_view = read_referenced_json(package_dir, rel)
        if not isinstance(report_view, dict):
            continue
        if report_view.get("kind") != "report_view":
            errors.append(f"{rel} kind 必须是 report_view")
            continue
        view = report_view.get("payload", {})
        if not isinstance(view, dict):
            errors.append(f"{rel} payload 必须是对象")
            continue
        validate_report_view_payload(
            rel=rel,
            report_type=report_type,
            manifest=manifest,
            view=view,
            expected_weekly_project_identities=expected_weekly_project_identities,
            errors=errors,
        )


def validate_report_trace_package(
    *,
    package_dir: Path,
    manifest: dict[str, Any],
    trace_required_evidence_kinds: set[str],
    package_status_values: set[str],
    require_file: RequireFile,
    load_evidence: LoadEvidence,
    read_referenced_json: ReadReferencedJson,
    errors: list[str],
) -> None:
    package_kind = manifest.get("package_kind")
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
    for kind in trace_required_evidence_kinds:
        if kind not in evidence_by_kind:
            errors.append(f"report trace 缺少 {kind} evidence")
    if package_kind == "daily_trace":
        validate_daily_project_inference(manifest=manifest, evidence_by_kind=evidence_by_kind, errors=errors)
    else:
        validate_weekly_fact_sources(manifest=manifest, evidence_by_kind=evidence_by_kind, errors=errors)
    validate_session_privacy_evidence(evidence_by_kind=evidence_by_kind, errors=errors)
    validate_work_findings(evidence_by_kind=evidence_by_kind, package_status_values=package_status_values, errors=errors)
    validate_report_display_files(
        package_dir=package_dir,
        files=files,
        manifest=manifest,
        report_type=report_type,
        expected_weekly_project_identities=(
            evidence_by_kind.get("project_inference", {}).get("payload", {}).get("project_customers")
            if package_kind == "weekly_trace"
            and isinstance(evidence_by_kind.get("project_inference", {}).get("payload"), dict)
            else None
        ),
        require_file=require_file,
        read_referenced_json=read_referenced_json,
        errors=errors,
    )
