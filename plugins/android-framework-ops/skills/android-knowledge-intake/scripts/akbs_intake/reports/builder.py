from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any, Callable

from akbs_intake.config import expanded_path, local_now, parse_bool, require_config, require_safe_artifact_path
from akbs_intake.io_utils import materials_rel, write_json
from akbs_intake.report_sessions import SessionWork, synthetic_sessions
from akbs_intake.reports.common import ensure_report_date_allowed, ensure_report_not_duplicate, report_dates, report_identity, ymd
from akbs_intake.reports.identity import infer_report_project
from akbs_intake.reports.render import write_report, write_report_view
from akbs_intake.reports.session_summary import items_by_project, overview_text, work_findings_payload
from akbs_intake.search_usage import search_usage_payload
from akbs_intake.patch.assets import PatchInfo
from akbs_intake.patch.supplement import write_default_evidence

ValidatePackage = Callable[[Path], dict[str, Any]]
WritePackageSource = Callable[[Path, dict[str, str], str], dict[str, Any]]
ParseSessions = Callable[[dict[str, str], set[dt.date]], list[SessionWork]]
DiscoverPatches = Callable[[dict[str, str], list[SessionWork], dt.date, dt.date], list[PatchInfo]]


def synthetic_mode(config: dict[str, str]) -> bool:
    return parse_bool(config.get("synthetic_data", "false"))


def incoming_report_manifest(
    report_type: str,
    date: dt.date,
    week_key: str,
    config: dict[str, str],
    summary: str,
    source: dict[str, Any],
    run_id: str,
    schema_version: str,
    project: str = "",
    project_evidence_path: str = "",
    display_path: str = "",
) -> dict[str, Any]:
    report_name = f"{report_type}.md"
    package_kind = "daily_trace" if report_type == "daily" else "weekly_trace"
    manifest: dict[str, Any] = {
        "schema": "knowledge-incoming-package",
        "schema_version": schema_version,
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
                materials_rel("evidence", "source.json"),
                materials_rel("evidence", "codex_sessions.json"),
                materials_rel("evidence", "work_findings.json"),
            ],
            "display": [display_path or materials_rel("display", "report_view.json")],
        },
    }
    if report_type == "weekly":
        manifest["week_range"] = week_key
    if report_type == "daily" and project:
        manifest["project"] = project
    if project_evidence_path:
        manifest["files"]["evidence"].append(project_evidence_path)
    return manifest

def build_report_package(
    report_type: str,
    date: dt.date,
    config: dict[str, str],
    run_id: str | None = None,
    schema_version: str = "",
    replace_report_run_id: str = "",
    *,
    incoming_schema_version: str,
    validate_package_fn: ValidatePackage,
    write_package_source_fn: WritePackageSource,
    parse_sessions_fn: ParseSessions,
    discover_patches_fn: DiscoverPatches,
) -> Path:
    require_config(config)
    schema_version = schema_version or incoming_schema_version
    if schema_version != incoming_schema_version:
        raise SystemExit(f"incoming 只支持 schema_version={incoming_schema_version}")
    dates, start, end, week_key = report_dates(report_type, date)
    ensure_report_date_allowed(report_type, date, config)
    run_id = run_id or f"{ymd(date)}-{local_now(config):%H%M%S}"
    out_dir = require_safe_artifact_path(expanded_path(config["out_dir"]), purpose="out_dir")
    package_dir = require_safe_artifact_path(out_dir / "pending" / ymd(date) / config["member_alias"] / run_id, purpose="incoming package output")
    if package_dir.exists():
        raise SystemExit(f"工作包已存在: {package_dir}")
    report_duplicates: list[dict[str, str]] = []
    replace_report_run_id = str(replace_report_run_id or "").strip()
    if report_type in {"daily", "weekly"}:
        report_duplicates = ensure_report_not_duplicate(
            config,
            report_type,
            report_identity(report_type, date, week_key),
            run_id,
            replace_report_run_id,
        )
    package_dir.mkdir(parents=True)

    if synthetic_mode(config):
        sessions = synthetic_sessions(config, dates)
        patches = []
    else:
        sessions = parse_sessions_fn(config, dates)
        patches = discover_patches_fn(config, sessions, start, end)
    items = items_by_project(sessions, patches)
    summary = overview_text(report_type, items, patches)
    report_project, project_payload = infer_report_project(report_type, summary, items, sessions, patches)
    project_customers = {
        str(item.get("project")): str(item.get("customer_name"))
        for item in project_payload.get("project_customers", [])
        if isinstance(item, dict) and item.get("project") and item.get("customer_name")
    }
    write_report(package_dir, report_type, date, week_key, config, items, patches, project_customers)
    project_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "project_inference.json"),
        {
            "kind": "project_inference",
            "payload": project_payload,
        },
    )

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
    write_json(package_dir / materials_rel("evidence", "codex_sessions.json"), {"kind": "codex_sessions", "payload": evidence})
    write_json(package_dir / materials_rel("evidence", "work_findings.json"), {"kind": "work_findings", "payload": work_findings_payload(sessions, patches)})
    search_path = ""
    if report_type == "daily":
        member_search_payload = search_usage_payload(config, date)
        if member_search_payload:
            search_path = materials_rel("evidence", "search_before_change.json")
            write_json(package_dir / search_path, {"kind": "search_before_change", "payload": member_search_payload})
    reports_dir = package_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(package_dir / f"{report_type}.md"), reports_dir / f"{report_type}.md")
    source = write_package_source_fn(package_dir, config, "android-knowledge-intake")
    display_path = write_report_view(package_dir, report_type, date, week_key, config, items, patches, summary, project_customers)
    manifest = incoming_report_manifest(
        report_type,
        date,
        week_key,
        config,
        summary,
        source,
        run_id,
        incoming_schema_version,
        report_project,
        project_path,
        display_path,
    )
    if report_type in {"daily", "weekly"} and replace_report_run_id:
        replacement = next((item for item in report_duplicates if item["run_id"] == replace_report_run_id), {})
        manifest["replacement_for_run_id"] = replace_report_run_id
        manifest["supersedes"] = {
            "report_type": report_type,
            "run_id": replace_report_run_id,
            "date": date.isoformat(),
            "week_range": week_key if report_type == "weekly" else "",
            "identity": report_identity(report_type, date, week_key),
            "package_key": replacement.get("package_key", ""),
        }
    if search_path:
        manifest["files"]["evidence"].append(search_path)
    write_json(package_dir / "manifest.json", manifest)
    check = validate_package_fn(package_dir)
    write_json(package_dir / "local-check.json", check)
    return package_dir
