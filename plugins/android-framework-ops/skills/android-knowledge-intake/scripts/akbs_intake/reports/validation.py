from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from android_framework_ops.knowledge_rules import find_company_project

from .render import REPORT_MISSING_CUSTOMER_VALUES, REPORT_MISSING_PROJECT_VALUES


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
WEEKLY_ALLOWED_SOURCES = {"客户需求文档", "TL指派", "Buglist", "测试反馈", "BSP配合", "需成员确认"}
WEEKLY_ALLOWED_REQUIREMENT_TYPES = {"纯定制", "Buglist", "混合", "需成员确认"}


def report_project_customer_errors(rel: str, rows: Any, label: str) -> list[str]:
    row_errors: list[str] = []
    if not isinstance(rows, list) or not rows:
        row_errors.append(f"{rel} payload.{label} 必须包含项目和客户信息")
        return row_errors
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            row_errors.append(f"{rel} payload.{label}[{index}] 必须是对象")
            continue
        project = str(row.get("project") or "").strip()
        if project in REPORT_MISSING_PROJECT_VALUES or not find_company_project(project):
            row_errors.append(
                f"{rel} payload.{label}[{index}].project 未识别到公司项目名，请按“项目名 客户名”补充，例如：TVE1086U 青鸾云"
            )
        customer = str(row.get("customer_name") or row.get("customer") or "").strip()
        if customer in REPORT_MISSING_CUSTOMER_VALUES:
            row_errors.append(
                f"{rel} payload.{label}[{index}].customer 缺少客户名，请按“项目名 客户名”补充，例如：TVE1086U 青鸾云"
            )
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
        errors.append("project_inference.project 未识别到公司项目名，请按“项目名 客户名”补充，例如：TVE1086U 青鸾云")
        if not isinstance(project_payload.get("checked_sources"), list) or not project_payload.get("checked_sources"):
            errors.append("unknown project_inference 必须记录 checked_sources")
        if not isinstance(project_payload.get("limits"), list) or not project_payload.get("limits"):
            errors.append("unknown project_inference 必须记录 limits")
    elif manifest.get("project") != project:
        errors.append("daily_trace manifest.project 必须等于 project_inference.project")
    customer = str(project_payload.get("customer_name") or "").strip()
    if project and project != "unknown" and customer in REPORT_MISSING_CUSTOMER_VALUES:
        errors.append("project_inference.customer_name 缺少客户名，请按“项目名 客户名”补充，例如：TVE1086U 青鸾云")


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


def validate_daily_report_view_project(rel: str, index: int, project: dict[str, Any], errors: list[str]) -> None:
    for field in ("today_topic", "current_result"):
        if not project.get(field):
            errors.append(f"{rel} payload.projects[{index}].{field} 必须提供")
    for field in ("work_items", "tomorrow_focus"):
        if not isinstance(project.get(field), list):
            errors.append(f"{rel} payload.projects[{index}].{field} 必须是数组")


def validate_weekly_report_view_project(rel: str, index: int, project: dict[str, Any], errors: list[str]) -> None:
    for field in (
        "week_summary",
        "received_date",
        "source",
        "requirement_type",
        "requirement_structure",
        "completed_this_week",
        "remaining",
        "expected_finish",
    ):
        if not project.get(field):
            errors.append(f"{rel} payload.projects[{index}].{field} 必须提供")
    if project.get("source") not in WEEKLY_ALLOWED_SOURCES:
        errors.append(f"{rel} payload.projects[{index}].source 非法: {project.get('source')}")
    if project.get("requirement_type") not in WEEKLY_ALLOWED_REQUIREMENT_TYPES:
        errors.append(f"{rel} payload.projects[{index}].requirement_type 非法: {project.get('requirement_type')}")
    for field in ("completed_items", "remaining_items", "risks", "dependencies", "next_week_plan"):
        if not isinstance(project.get(field), list):
            errors.append(f"{rel} payload.projects[{index}].{field} 必须是数组")


def validate_report_view_payload(
    *,
    rel: str,
    report_type: str,
    manifest: dict[str, Any],
    view: dict[str, Any],
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
        validate_report_view_payload(rel=rel, report_type=report_type, manifest=manifest, view=view, errors=errors)


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
    validate_work_findings(evidence_by_kind=evidence_by_kind, package_status_values=package_status_values, errors=errors)
    validate_report_display_files(
        package_dir=package_dir,
        files=files,
        manifest=manifest,
        report_type=report_type,
        require_file=require_file,
        read_referenced_json=read_referenced_json,
        errors=errors,
    )
