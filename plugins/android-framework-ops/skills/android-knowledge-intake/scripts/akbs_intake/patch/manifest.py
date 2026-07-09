from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from akbs_intake.io_utils import materials_rel, stable_slug_id, write_json


def framework_case_variant_ids(
    *,
    summary: str,
    platform: str,
    android_version: str,
    project: str,
    repo_paths: list[str],
) -> tuple[str, str]:
    case_id = "case-" + stable_slug_id(summary, "framework-change", 80)
    variant_seed = json.dumps(
        {
            "android_version": android_version,
            "case_id": case_id,
            "platform": platform,
            "project": project,
            "repo_paths": repo_paths,
            "summary": summary,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    variant_id = "variant-" + stable_slug_id("-".join([platform, android_version, project, summary]), "framework-change", 100, variant_seed)
    return case_id, variant_id


def case_payload(*, case_id: str, title: str, problem: str, solution_summary: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "title": title,
        "problem": problem,
        "solution_summary": solution_summary,
    }


def variant_payload(
    *,
    variant_id: str,
    case_id: str,
    platform: str,
    android_version: str,
    project: str,
    repo_paths: list[str],
    implementation_origins: list[str],
    capture_tools: list[str],
    package_status: str,
    related_report_run_ids: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "variant_id": variant_id,
        "case_id": case_id,
        "platform": platform,
        "android_version": android_version,
        "project": project,
        "repo_paths": repo_paths,
        "implementation_origins": implementation_origins,
        "capture_tools": capture_tools,
        "package_status": package_status,
    }
    if related_report_run_ids:
        payload["related_report_run_ids"] = related_report_run_ids
    return payload


def write_case_file(package_dir: Path, *, case_id: str, summary: str, case_problem: str, case_solution: str) -> str:
    case_path = materials_rel("case.json")
    write_json(
        package_dir / case_path,
        case_payload(
            case_id=case_id,
            title=summary,
            problem=case_problem,
            solution_summary=case_solution,
        ),
    )
    return case_path


def write_variant_file(
    package_dir: Path,
    *,
    variant_id: str,
    case_id: str,
    platform: str,
    android_version: str,
    project: str,
    repo_paths: list[str],
    implementation_origins: list[str],
    capture_tools: list[str],
    package_status: str,
    related_report_run_ids: list[str] | None = None,
) -> str:
    variant_path = materials_rel("variant.json")
    write_json(
        package_dir / variant_path,
        variant_payload(
            variant_id=variant_id,
            case_id=case_id,
            platform=platform,
            android_version=android_version,
            project=project,
            repo_paths=repo_paths,
            implementation_origins=implementation_origins,
            capture_tools=capture_tools,
            package_status=package_status,
            related_report_run_ids=related_report_run_ids,
        ),
    )
    return variant_path


def framework_change_manifest(
    *,
    schema_version: str,
    config: dict[str, str],
    date: dt.date,
    run_id: str,
    case_id: str,
    variant_id: str,
    package_status: str,
    platform: str,
    android_version: str,
    project: str,
    summary: str,
    implementation_origins: list[str],
    capture_tools: list[str],
    case_path: str,
    variant_path: str,
    feature_readme_rel: str,
    patch_rel_paths: list[str],
    patch_view_path: str,
    evidence_paths: list[str],
    related_report_run_ids: list[str] | None = None,
    supplement_for_package_key: str = "",
    supplement_reason: str = "",
    supplement_mode: str = "",
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema": "knowledge-incoming-package",
        "schema_version": schema_version,
        "package_kind": "framework_change",
        "member_alias": config["member_alias"],
        "member_name": config["member_name"],
        "date": date.isoformat(),
        "run_id": run_id,
        "tool": "android-knowledge-intake",
        "case_id": case_id,
        "variant_id": variant_id,
        "package_status": package_status,
        "platform": platform,
        "android_version": android_version,
        "project": project,
        "summary": summary,
        "implementation_origins": implementation_origins,
        "capture_tools": capture_tools,
        "files": {
            "case": case_path,
            "variant": variant_path,
            "readme": feature_readme_rel,
            "patches": patch_rel_paths,
            "display": [patch_view_path],
            "evidence": evidence_paths,
        },
    }
    if related_report_run_ids:
        manifest["related_report_run_ids"] = related_report_run_ids
    if supplement_for_package_key:
        manifest["supplement_for_package_key"] = supplement_for_package_key
        manifest["supplement_reason"] = supplement_reason
        manifest["material_identity"] = {
            "mode": "inherit_target_package",
            "target_package_key": supplement_for_package_key,
            "editable": False,
        }
        if supplement_mode:
            manifest["supplement_mode"] = supplement_mode
    return manifest
