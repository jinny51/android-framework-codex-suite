#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
OPS_PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if OPS_PLUGIN_LIB.is_dir() and str(OPS_PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(OPS_PLUGIN_LIB))

from android_framework_ops.knowledge_rules import (
    aggregate_package_scope_errors,
    apply_platform_overrides,
    find_company_project,
    find_platform_tokens,
    has_uncontrolled_patch_asset_prefix,
    is_valid_android_version_value,
    is_valid_platform_value,
    normalize_android_version,
    parse_known_platform_token,
    parse_platform_token,
    parse_version_only_token,
    patch_asset_correction_source_errors,
    patch_upload_gate_errors,
    split_company_project,
    supplement_target_relation_errors,
    template_leak_errors,
    text_field_quality_errors,
)
PLUGIN_UPDATE_SKIP_ENV = "CODEX_REPORT_SKIP_PLUGIN_UPDATE_CHECK"
PLUGIN_UPDATE_REQUIRE_ENV = "CODEX_REPORT_REQUIRE_PLUGIN_UPDATE_CHECK"
PLUGIN_REEXEC_ATTEMPT_ENV = "CODEX_REPORT_PLUGIN_REEXEC_ATTEMPTED"
PLUGIN_REMOTE_MANIFEST_TIMEOUT = 6
PACKAGE_TYPES = {"daily", "weekly", "patch"}
INCOMING_KINDS = {"daily_trace", "weekly_trace", "framework_change"}
PACKAGE_STATUS_VALUES = {"validated", "candidate", "draft", "failed", "blocked"}
TRACE_REQUIRED_EVIDENCE_KINDS = {"source", "work_findings"}
FRAMEWORK_REQUIRED_EVIDENCE_KINDS = {
    "source",
    "patch_diff_facts",
    "patch_ai_facts",
    "project_inference",
    "patch_problem_summary",
    "risk_surface",
    "verification_result",
    "search_before_change",
}
FIELD_CORRECTION_REQUIRED_EVIDENCE_KINDS = {"source", "project_inference", "evidence_supplement", "field_correction"}
SUPPLEMENT_MODES = {"field_correction", "asset_correction"}
FIELD_CORRECTION_ALLOWED_FIELDS = {
    "project",
    "platform",
    "android_version",
}
FIELD_CORRECTION_MATERIAL_IDENTITY_FIELDS = {
    "material_name",
    "material_summary",
    "feature",
    "feature_name",
    "function_name",
    "display_title",
    "summary",
    "patch_view",
    "report_view",
}
FIELD_CORRECTION_FORBIDDEN_FIELDS = {
    "patch",
    "patches",
    "patch_assets",
    "patch_diff",
    "patch_diff_facts",
    "patch_ai_facts",
    "verification",
    "verification_result",
    "device_verification",
    "equivalent_verification",
    "build_result",
    "deploy_result",
    "search_before_change",
    "search_usage",
    "code_anchors",
    *FIELD_CORRECTION_MATERIAL_IDENTITY_FIELDS,
}
FIELD_CORRECTION_FORBIDDEN_EVIDENCE_KINDS = {
    "patch_diff_facts",
    "patch_ai_facts",
    "verification_result",
    "device_verification",
    "equivalent_verification",
    "build_result",
    "deploy_result",
    "search_before_change",
}
FRAMEWORK_OPTIONAL_EVIDENCE_KINDS = {"build_result", "deploy_result", "device_health"}
LEGACY_PATCH_PROBLEM_KIND = "patch_" + "problem_" + "inference"
DATE_KEY_RE = re.compile(r"^\d{8}$")
DATE_DISPLAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RUN_ID_RE = re.compile(r"^\d{8}-\d{6}(-[A-Za-z0-9_.-]+)?$")


LAST_PLUGIN_VERSION_GATE: dict[str, Any] | None = None


from akbs_intake import version_gate as _version_gate  # noqa: E402
from akbs_intake.version_gate import (  # noqa: E402
    LAST_PLUGIN_VERSION_GATE,
    auto_update_packaged_plugin,
    compare_versions,
    current_skill_cache_metadata,
    env_enabled,
    fetch_remote_plugin_manifest,
    github_raw_plugin_manifest_url,
    latest_installed_plugin_cache_metadata,
    packaged_plugin_freshness,
    plugin_freshness_check,
    plugin_install_metadata,
    plugin_manifest_path,
    plugin_update_unknown,
    plugin_version_gate_check,
    reexec_latest_plugin_script_after_update,
    run,
    updated_plugin_intake_script_path,
    version_parts,
)

_ORIGINAL_VERSION_GATE_RUN = getattr(_version_gate, "_AKBS_ORIGINAL_RUN", _version_gate.run)
_ORIGINAL_VERSION_GATE_FETCH_REMOTE_PLUGIN_MANIFEST = getattr(
    _version_gate,
    "_AKBS_ORIGINAL_FETCH_REMOTE_PLUGIN_MANIFEST",
    _version_gate.fetch_remote_plugin_manifest,
)
_version_gate._AKBS_ORIGINAL_RUN = _ORIGINAL_VERSION_GATE_RUN
_version_gate._AKBS_ORIGINAL_FETCH_REMOTE_PLUGIN_MANIFEST = _ORIGINAL_VERSION_GATE_FETCH_REMOTE_PLUGIN_MANIFEST
run = _ORIGINAL_VERSION_GATE_RUN
fetch_remote_plugin_manifest = _ORIGINAL_VERSION_GATE_FETCH_REMOTE_PLUGIN_MANIFEST


def _call_version_gate(callback):
    original_root = _version_gate.PLUGIN_ROOT
    original_run = _version_gate.run
    original_fetch_remote = _version_gate.fetch_remote_plugin_manifest
    _version_gate.PLUGIN_ROOT = PLUGIN_ROOT
    _version_gate.run = run
    _version_gate.fetch_remote_plugin_manifest = fetch_remote_plugin_manifest
    try:
        return callback()
    finally:
        _version_gate.PLUGIN_ROOT = original_root
        _version_gate.run = original_run
        _version_gate.fetch_remote_plugin_manifest = original_fetch_remote


def plugin_install_metadata() -> dict[str, str]:
    return _call_version_gate(_version_gate.plugin_install_metadata)


def current_skill_cache_metadata() -> dict[str, str]:
    return _call_version_gate(_version_gate.current_skill_cache_metadata)


def latest_installed_plugin_cache_metadata(plugin_name: str = "android-framework-ops") -> dict[str, str]:
    return _call_version_gate(lambda: _version_gate.latest_installed_plugin_cache_metadata(plugin_name))


def plugin_freshness_check(fetch: bool = True, require: bool = False) -> dict[str, Any]:
    return _call_version_gate(lambda: _version_gate.plugin_freshness_check(fetch=fetch, require=require))


def plugin_version_gate_check(config: dict[str, str] | None = None, fetch: bool = True, require: bool = True) -> dict[str, Any]:
    global LAST_PLUGIN_VERSION_GATE
    gate = _call_version_gate(lambda: _version_gate.plugin_version_gate_check(config=config, fetch=fetch, require=require))
    LAST_PLUGIN_VERSION_GATE = gate
    return gate


def synthetic_mode(config: dict[str, str]) -> bool:
    return parse_bool(config.get("synthetic_data", "false"))


from akbs_intake.config import (  # noqa: E402
    AKBS_ENDPOINT_DEFAULTS,
    AKBS_ENDPOINT_ENV_PREFIXES,
    CONFIG_DEFAULTS,
    DEFAULT_KNOWLEDGE_REPO_URL,
    DEFAULT_SUBMISSION_API_BASE_URL,
    DEFAULT_SUBMISSION_API_TOKEN,
    DEFAULT_SUBMISSION_SESSION_COOKIE,
    ENV_PREFIXES,
    INCOMING_SCHEMA_VERSION,
    LEGACY_TEST35_ENDPOINT_VALUES,
    akbs_endpoint_env_value,
    allowed_modes,
    apply_env_overrides,
    artifact_path_guard_error,
    configured_endpoint_fields,
    default_codex_home,
    enforce_mode_allowed,
    endpoint_migration_report,
    expanded_path,
    find_project_report_config,
    flatten_config_payload,
    knowledge_repo_url,
    knowledge_repo_worktree,
    load_config,
    local_now,
    parse_bool,
    parse_date_arg,
    parse_simple_toml,
    parse_toml_scalar,
    profile_configs,
    profile_from_env,
    read_toml,
    require_config,
    require_safe_artifact_path,
    resolve_akbs_endpoint,
    stringify_config_value,
    submission_api_base_url,
    submission_api_token,
    submission_session_cookie,
)
from akbs_intake.report_sessions import (  # noqa: E402
    SessionWork,
    git_branch_or_name as _report_git_branch_or_name,
    git_root as _report_git_root,
    parse_sessions as _parse_sessions,
    report_customer_for_project,
    synthetic_sessions,
    week_bounds,
    ymd,
)
from akbs_intake.io_utils import (  # noqa: E402
    MATERIALS_DIR,
    list_string_values,
    materials_rel,
    read_referenced_json,
    reference_path,
    read_json_file,
    read_optional_json_object,
    safe_id,
    unique_strings,
    write_json,
)
from akbs_intake.project_identity import (  # noqa: E402
    infer_project as _infer_project,
)
from akbs_intake.patch.assets import (  # noqa: E402
    PatchInfo,
    copy_patch_assets,
    discover_patches_from_cwd,
    paired_readme,
    patch_infos_from_paths,
    patch_readme_template,
    patch_readme_usable_for_inference,
    synthetic_patch_info,
    validate_patch_file,
    validate_patch_readme,
    write_feature_readme_from_patch_entries,
)
from akbs_intake.patch.capture_import import (  # noqa: E402
    copy_patch_capture_packages,
    patch_capture_package_scope_errors,
)
from akbs_intake.patch.evidence import (  # noqa: E402
    aggregate_patch_diff_facts,
    ensure_patch_analysis_evidence,
    ensure_required_patch_explanation_evidence,
    incoming_patch_item,
    select_search_before_change_payload,
    verification_payload_or_missing,
    write_patch_view_and_ai_facts,
)
from akbs_intake.patch.facts import patch_facts_from_text, patch_modules_from_files, patch_problem_and_risk_payloads  # noqa: E402
from akbs_intake.patch.metadata import (  # noqa: E402
    evidence_text_values,
    first_evidence_path,
    first_evidence_payload,
    infer_platform_metadata,
    repo_paths_from_files,
)
from akbs_intake.patch.manifest import (  # noqa: E402
    framework_case_variant_ids,
    framework_change_manifest,
    write_case_file,
    write_variant_file,
)
from akbs_intake.patch.supplement import (  # noqa: E402
    downgrade_validated_patch_entries,
    framework_metadata_is_traceable,
    framework_package_status_from_patch_statuses,
    infer_supplement_mode,
    normalize_corrected_fields as _normalize_corrected_fields,
    parse_corrected_field_args,
    prepare_field_correction_package,
    write_evidence_supplement,
    write_default_evidence,
)
from akbs_intake.doctor import (  # noqa: E402
    doctor as _intake_doctor,
    doctor_strict_checks as _intake_doctor_strict_checks,
    git_run as _intake_git_run,
    latest_pending as _intake_latest_pending,
    nearest_existing_parent,
)


def git_root(path: str) -> Path | None:
    return _report_git_root(path, run)


def git_branch_or_name(path: str) -> str:
    return _report_git_branch_or_name(path, run)


def parse_sessions(config: dict[str, str], dates: set[dt.date]) -> list[SessionWork]:
    return _parse_sessions(config, dates, run)


def discover_patches(config: dict[str, str], sessions: list[SessionWork], start: dt.date, end: dt.date) -> list[PatchInfo]:
    return _report_discover_patches(
        config,
        sessions,
        start,
        end,
        git_root=git_root,
        git_branch_or_name=git_branch_or_name,
        patch_info_factory=lambda path, name, project: PatchInfo(path=path, name=name, project=project),
    )


def report_dates(report_type: str, date: dt.date) -> tuple[set[dt.date], dt.date, dt.date, str]:
    if report_type in {"daily", "patch"}:
        return {date}, date, date, ymd(date)
    start, end = week_bounds(date)
    days = {start + dt.timedelta(days=offset) for offset in range((end - start).days + 1)}
    return days, start, end, f"{ymd(start)}-{ymd(end)}"


def evidence_payload(evidence: dict[str, Any]) -> dict[str, Any]:
    payload = evidence.get("payload")
    return payload if isinstance(payload, dict) else evidence


from akbs_intake import validation as _validation  # noqa: E402


def validate_package(package_dir: Path) -> dict[str, Any]:
    return _validation.validate_package(
        package_dir,
        incoming_schema_version=INCOMING_SCHEMA_VERSION,
        validate_incoming_package_fn=validate_incoming_package,
    )


from akbs_intake.search_usage import (  # noqa: E402
    implementation_origins_require_pre_change_search,
    patch_search_feature_tokens,
    search_payload_has_member_decision,
    search_payload_missing_required_pre_change_search,
    search_payload_needs_closed_decision,
    search_usage_payload,
)


from akbs_intake import source_metadata as _source_metadata  # noqa: E402


def source_metadata(config: dict[str, str], skill: str) -> dict[str, Any]:
    return _source_metadata.source_metadata(
        config,
        skill,
        plugin_root=PLUGIN_ROOT,
        run_command=run,
        plugin_install_metadata_fn=plugin_install_metadata,
        plugin_version_gate_check_fn=lambda gate_config, fetch, require: plugin_version_gate_check(
            gate_config,
            fetch=fetch,
            require=require,
        ),
        last_plugin_version_gate=LAST_PLUGIN_VERSION_GATE,
    )


def write_package_source(package_dir: Path, config: dict[str, str], skill: str) -> dict[str, Any]:
    source = source_metadata(config, skill)
    write_json(package_dir / materials_rel("evidence", "source.json"), {"kind": "source", "payload": source})
    return source


def bind_framework_evidence(package_dir: Path, rel: str, case_id: str, variant_id: str) -> None:
    path = package_dir / rel
    if not path.is_file():
        return
    payload = read_json_file(path)
    payload["case_id"] = case_id
    payload["variant_id"] = variant_id
    if payload.get("kind") == "source":
        source_payload = payload.get("payload")
        if not isinstance(source_payload, dict):
            source_payload = {}
        payload["payload"] = source_payload
    write_json(path, payload)


def incoming_report_manifest(
    report_type: str,
    date: dt.date,
    week_key: str,
    config: dict[str, str],
    summary: str,
    source: dict[str, Any],
    run_id: str,
    project: str = "",
    project_evidence_path: str = "",
    display_path: str = "",
) -> dict[str, Any]:
    report_name = f"{report_type}.md"
    package_kind = "daily_trace" if report_type == "daily" else "weekly_trace"
    manifest: dict[str, Any] = {
        "schema": "knowledge-incoming-package",
        "schema_version": INCOMING_SCHEMA_VERSION,
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


from akbs_intake.reports.common import (  # noqa: E402
    ensure_report_date_allowed,
    ensure_report_not_duplicate,
    format_report_duplicate_message,
    iter_local_manifests,
    local_report_packages,
    package_key_from_manifest,
    replacement_run_id,
    report_dates,
    report_duplicate_label,
    report_identity,
    report_identity_from_manifest,
    report_replace_option,
    report_type_from_manifest,
)
from akbs_intake.reports.identity import (  # noqa: E402
    infer_report_project,
    related_report_project_clues,
    same_day_daily_report_run_ids,
)
from akbs_intake.reports.render import (  # noqa: E402
    project_ledger_rows,
    write_report,
    write_report_view,
)
from akbs_intake.reports.session_summary import (  # noqa: E402
    discover_patches as _report_discover_patches,
    items_by_project,
    overview_text,
    work_findings_payload,
)
from akbs_intake.reports.validation import validate_report_trace_package  # noqa: E402


def validate_incoming_package(package_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    def require_file(rel: Any, label: str) -> Path | None:
        if not isinstance(rel, str) or not rel:
            errors.append(f"{label} path 必须提供")
            return None
        try:
            path = reference_path(package_dir, rel)
        except ValueError as exc:
            errors.append(str(exc))
            return None
        if not path.is_file():
            errors.append(f"{label} 文件不存在: {rel}")
            return None
        return path

    def load_evidence(paths: list[Any]) -> dict[str, dict[str, Any]]:
        by_kind: dict[str, dict[str, Any]] = {}
        for rel in paths:
            path = require_file(rel, "evidence")
            if not path:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"{rel} 解析失败: {exc}")
                continue
            if not isinstance(payload, dict):
                errors.append(f"{rel} evidence 必须是对象")
                continue
            kind = payload.get("kind")
            if not kind:
                errors.append(f"{rel} evidence.kind 必须提供")
                continue
            by_kind[str(kind)] = payload
        return by_kind

    required = {
        "schema",
        "schema_version",
        "package_kind",
        "member_alias",
        "member_name",
        "date",
        "run_id",
        "tool",
        "summary",
    }
    for field in sorted(required - set(manifest)):
        errors.append(f"manifest 缺少必填字段: {field}")
    if manifest.get("schema") != "knowledge-incoming-package":
        errors.append("schema 必须是 knowledge-incoming-package")
    if manifest.get("schema_version") != INCOMING_SCHEMA_VERSION:
        errors.append(f"schema_version 必须是 {INCOMING_SCHEMA_VERSION}")
    if not DATE_DISPLAY_RE.fullmatch(str(manifest.get("date") or "")):
        errors.append("manifest.date 必须是 YYYY-MM-DD")
    if not RUN_ID_RE.fullmatch(str(manifest.get("run_id") or "")):
        errors.append("manifest.run_id 必须是 YYYYMMDD-HHMMSS 或 YYYYMMDD-HHMMSS-suffix")
    errors.extend(
        text_field_quality_errors(
            {
                "manifest.summary": manifest.get("summary"),
                "manifest.supplement_reason": manifest.get("supplement_reason"),
            }
        )
    )
    package_kind = manifest.get("package_kind")
    if package_kind not in INCOMING_KINDS:
        errors.append(f"package_kind 非法: {package_kind}")

    if package_kind in {"daily_trace", "weekly_trace"}:
        validate_report_trace_package(
            package_dir=package_dir,
            manifest=manifest,
            trace_required_evidence_kinds=TRACE_REQUIRED_EVIDENCE_KINDS,
            package_status_values=PACKAGE_STATUS_VALUES,
            require_file=require_file,
            load_evidence=load_evidence,
            read_referenced_json=read_referenced_json,
            errors=errors,
        )

    if package_kind == "framework_change":
        patch_context = validate_framework_change_manifest_and_files(
            package_dir=package_dir,
            manifest=manifest,
            package_status_values=PACKAGE_STATUS_VALUES,
            supplement_modes=SUPPLEMENT_MODES,
            run_id_re=RUN_ID_RE,
            require_file=require_file,
            validate_patch_readme=validate_patch_readme,
            has_uncontrolled_patch_asset_prefix=has_uncontrolled_patch_asset_prefix,
            is_valid_platform_value=is_valid_platform_value,
            is_valid_android_version_value=is_valid_android_version_value,
            errors=errors,
        )
        manifest_platform = patch_context.manifest_platform
        manifest_android_version = patch_context.manifest_android_version
        package_status = patch_context.package_status
        supplement_target = patch_context.supplement_target
        is_field_correction = patch_context.is_field_correction
        is_asset_correction = patch_context.is_asset_correction
        case_path = patch_context.case_path
        variant_path = patch_context.variant_path
        readme_path = patch_context.readme_path
        patch_paths = patch_context.patch_paths
        display_paths = patch_context.display_paths
        evidence_paths = patch_context.evidence_paths
        validate_patch_display_files(
            package_dir=package_dir,
            display_paths=display_paths,
            manifest=manifest,
            supplement_target=supplement_target,
            require_file=require_file,
            read_referenced_json=read_referenced_json,
            errors=errors,
        )
        structure_context = validate_framework_change_structure(
            package_dir=package_dir,
            manifest=manifest,
            package_status=package_status,
            is_field_correction=is_field_correction,
            supplement_target=supplement_target,
            case_path=case_path,
            variant_path=variant_path,
            evidence_paths=evidence_paths,
            load_evidence=load_evidence,
            read_json_file=read_json_file,
            read_referenced_json=read_referenced_json,
            text_field_quality_errors=text_field_quality_errors,
            is_valid_platform_value=is_valid_platform_value,
            is_valid_android_version_value=is_valid_android_version_value,
            legacy_patch_problem_kind=LEGACY_PATCH_PROBLEM_KIND,
            framework_required_evidence_kinds=FRAMEWORK_REQUIRED_EVIDENCE_KINDS,
            field_correction_required_evidence_kinds=FIELD_CORRECTION_REQUIRED_EVIDENCE_KINDS,
            field_correction_forbidden_evidence_kinds=FIELD_CORRECTION_FORBIDDEN_EVIDENCE_KINDS,
            field_correction_allowed_fields=FIELD_CORRECTION_ALLOWED_FIELDS,
            field_correction_forbidden_fields=FIELD_CORRECTION_FORBIDDEN_FIELDS,
            errors=errors,
        )
        case_problem = structure_context.case_problem
        case_solution = structure_context.case_solution
        evidence_by_kind = structure_context.evidence_by_kind
        ai_context = validate_patch_ai_facts_and_diff(
            evidence_by_kind=evidence_by_kind,
            is_field_correction=is_field_correction,
            evidence_payload=evidence_payload,
            list_string_values=list_string_values,
            unique_strings=unique_strings,
            errors=errors,
        )
        modified_files = ai_context.modified_files
        if not is_field_correction:
            validate_patch_template_leaks(
                package_dir=package_dir,
                manifest=manifest,
                evidence_paths=evidence_paths,
                case_problem=case_problem,
                case_solution=case_solution,
                patch_paths=patch_paths,
                modified_files=modified_files,
                read_referenced_json=read_referenced_json,
                template_leak_errors=template_leak_errors,
                errors=errors,
            )
            errors.extend(
                validate_framework_function_scope(
                    package_dir=package_dir,
                    manifest=manifest,
                    readme_path=readme_path,
                    patch_paths=patch_paths,
                    evidence_by_kind=evidence_by_kind,
                    list_string_values=list_string_values,
                    aggregate_package_scope_errors=aggregate_package_scope_errors,
                )
            )
        framework_change_summary = read_optional_json_object(package_dir / materials_rel("evidence", "framework_change_summary.json"))
        validate_patch_supplement_basics(
            manifest=manifest,
            evidence_by_kind=evidence_by_kind,
            supplement_target=supplement_target,
            is_field_correction=is_field_correction,
            is_asset_correction=is_asset_correction,
            manifest_platform=manifest_platform,
            manifest_android_version=manifest_android_version,
            framework_change_summary=framework_change_summary,
            supplement_target_relation_errors=supplement_target_relation_errors,
            patch_asset_correction_source_errors=patch_asset_correction_source_errors,
            split_company_project=split_company_project,
            errors=errors,
        )
        validate_patch_verification_result(
            evidence_by_kind=evidence_by_kind,
            package_status=package_status,
            is_field_correction=is_field_correction,
            errors=errors,
        )
        validate_patch_pre_change_search(
            manifest=manifest,
            evidence_by_kind=evidence_by_kind,
            package_status=package_status,
            is_field_correction=is_field_correction,
            list_string_values=list_string_values,
            implementation_origins_require_pre_change_search=implementation_origins_require_pre_change_search,
            search_payload_missing_required_pre_change_search=search_payload_missing_required_pre_change_search,
            search_payload_needs_closed_decision=search_payload_needs_closed_decision,
            errors=errors,
            warnings=warnings,
        )
        validate_patch_supplement_verification_closure(
            package_dir=package_dir,
            manifest=manifest,
            supplement_target=supplement_target,
            is_field_correction=is_field_correction,
            errors=errors,
        )
    return {"status": "FAIL" if errors else "PASS", "errors": errors, "warnings": warnings}


from akbs_intake.patch.validation import (  # noqa: E402
    validate_framework_change_manifest_and_files,
    validate_framework_change_structure,
    validate_framework_function_scope,
    validate_patch_display_files,
    validate_patch_ai_facts_and_diff,
    validate_patch_template_leaks,
    validate_patch_verification_result,
    validate_patch_pre_change_search,
    validate_patch_supplement_basics,
    validate_patch_supplement_verification_closure,
)


def prepare_package(
    report_type: str,
    date: dt.date,
    config: dict[str, str],
    run_id: str | None = None,
    schema_version: str = INCOMING_SCHEMA_VERSION,
    replace_report_run_id: str = "",
) -> Path:
    require_config(config)
    if schema_version != INCOMING_SCHEMA_VERSION:
        raise SystemExit(f"incoming 只支持 schema_version={INCOMING_SCHEMA_VERSION}")
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
        sessions = parse_sessions(config, dates)
        patches = discover_patches(config, sessions, start, end)
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
    source = write_package_source(package_dir, config, "android-knowledge-intake")
    display_path = write_report_view(package_dir, report_type, date, week_key, config, items, patches, summary, project_customers)
    manifest = incoming_report_manifest(
        report_type,
        date,
        week_key,
        config,
        summary,
        source,
        run_id,
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
    check = validate_package(package_dir)
    write_json(package_dir / "local-check.json", check)
    return package_dir


def infer_project(
    explicit_project: str,
    patch_entries: list[dict[str, Any]],
    patch_sources: list[dict[str, Any]],
    summary: str,
    package_dir: Path | None = None,
    source_contexts: list[dict[str, Any]] | None = None,
    related_report_clues: list[tuple[str, str]] | None = None,
    trusted_platform: str = "",
) -> tuple[str, dict[str, Any]]:
    return _infer_project(
        explicit_project,
        patch_entries,
        patch_sources,
        summary,
        package_dir=package_dir,
        source_contexts=source_contexts,
        related_report_clues=related_report_clues,
        trusted_platform=trusted_platform,
        readme_usable_for_inference=patch_readme_usable_for_inference,
    )


def normalize_corrected_fields(
    corrected_fields: dict[str, Any] | None,
    *,
    project: str = "",
    platform: str = "",
    android_version: str = "",
) -> dict[str, str]:
    return _normalize_corrected_fields(
        corrected_fields,
        project=project,
        platform=platform,
        android_version=android_version,
        material_identity_fields=FIELD_CORRECTION_MATERIAL_IDENTITY_FIELDS,
    )


def prepare_patch_package(
    date: dt.date,
    config: dict[str, str],
    run_id: str | None = None,
    patch_paths: list[str] | None = None,
    patch_package_paths: list[str] | None = None,
    project: str = "unknown",
    summary: str = "管理员手动归档补丁",
    status: str = "validated",
    schema_version: str = INCOMING_SCHEMA_VERSION,
    related_report_run_ids: list[str] | None = None,
    supplement_for_package_key: str = "",
    supplement_reason: str = "",
    platform_override: str = "",
    android_version_override: str = "",
    supplement_mode: str = "",
    corrected_fields: dict[str, Any] | None = None,
    correction_reason: str = "",
) -> Path:
    require_config(config)
    if schema_version != INCOMING_SCHEMA_VERSION:
        raise SystemExit(f"incoming 只支持 schema_version={INCOMING_SCHEMA_VERSION}")
    supplement_for_package_key = str(supplement_for_package_key or "").strip()
    supplement_reason = str(supplement_reason or "").strip()
    inferred_mode = infer_supplement_mode(supplement_mode, supplement_for_package_key, supplement_reason, corrected_fields)
    if inferred_mode and inferred_mode not in SUPPLEMENT_MODES:
        raise SystemExit(f"supplement_mode 非法: {inferred_mode}")
    if inferred_mode == "field_correction":
        run_id = run_id or f"{ymd(date)}-{local_now(config):%H%M%S}-field-supplement"
        platform, android_version = apply_platform_overrides(
            "unknown",
            "unknown",
            platform_override=platform_override or str((corrected_fields or {}).get("platform") or ""),
            android_version_override=android_version_override or str((corrected_fields or {}).get("android_version") or ""),
        )
        normalized_fields = normalize_corrected_fields(
            corrected_fields,
            project=project,
            platform=platform,
            android_version=android_version,
        )
        return prepare_field_correction_package(
            date,
            config,
            run_id,
            project=project if project else normalized_fields.get("project", "unknown"),
            platform=platform,
            android_version=android_version,
            summary=summary,
            schema_version=schema_version,
            supplement_for_package_key=supplement_for_package_key,
            supplement_reason=supplement_reason,
            corrected_fields=normalized_fields,
            correction_reason=correction_reason,
            validate_package_fn=validate_package,
            bind_framework_evidence_fn=bind_framework_evidence,
            write_package_source_fn=write_package_source,
        )
    if patch_paths and len(patch_paths) > 1:
        raise SystemExit(
            "直接 --patch 只允许单个独立补丁。多个补丁必须先用补丁采集技能（android-framework-patch-capture）"
            "按功能生成补丁包（patch package）；一个补丁包只能对应一个功能。"
        )
    run_id = run_id or f"{ymd(date)}-{local_now(config):%H%M%S}-patch"
    scope_errors = patch_capture_package_scope_errors(patch_package_paths, summary, run_id)
    if scope_errors:
        raise SystemExit("\n".join(scope_errors))
    out_dir = require_safe_artifact_path(expanded_path(config["out_dir"]), purpose="out_dir")
    package_dir = require_safe_artifact_path(out_dir / "pending" / ymd(date) / config["member_alias"] / run_id, purpose="incoming package output")
    if package_dir.exists():
        raise SystemExit(f"工作包已存在: {package_dir}")
    package_dir.mkdir(parents=True)

    patch_entries: list[dict[str, Any]] = []
    capture_evidence_entries: list[dict[str, Any]] = []
    patch_sources: list[dict[str, Any]] = []
    source_contexts: list[dict[str, Any]] = []
    has_pass_verification = False
    all_related_report_run_ids = list_string_values(related_report_run_ids)
    feature_readme_rel = ""

    if patch_package_paths:
        (
            capture_entries,
            evidence_entries,
            source_entries,
            capture_has_pass,
            capture_related_report_run_ids,
            capture_source_contexts,
            capture_feature_readme_rel,
        ) = copy_patch_capture_packages(
            package_dir,
            patch_package_paths,
            project,
            status,
        )
        patch_entries.extend(capture_entries)
        capture_evidence_entries.extend(evidence_entries)
        patch_sources.extend(source_entries)
        source_contexts.extend(capture_source_contexts)
        has_pass_verification = has_pass_verification or capture_has_pass
        all_related_report_run_ids.extend(capture_related_report_run_ids)
        feature_readme_rel = capture_feature_readme_rel

    if patch_paths:
        patches = patch_infos_from_paths(patch_paths, project)
    elif synthetic_mode(config):
        patches = [synthetic_patch_info(package_dir, date, project, config)]
        summary = summary if summary != "管理员手动归档补丁" else "合成测试补丁包"
        status = "candidate" if status == "validated" else status
    elif not patch_entries:
        patches = discover_patches_from_cwd(project, date)
    else:
        patches = []
    if not patches:
        if not patch_entries:
            raise SystemExit("patch 模式未找到补丁，请使用 --patch/--patch-package 指定，或在当前目录/patches 下放置当天修改的 .patch 文件。")
    else:
        patch_entries.extend(copy_patch_assets(package_dir, patches, config, status=status, reuse_hint=status == "validated", note="管理员手动归档补丁"))
        patch_sources.extend([{"name": item.name, "source": str(item.path), "project": item.project} for item in patches])
    if not feature_readme_rel:
        feature_readme_rel = write_feature_readme_from_patch_entries(package_dir, summary, patch_entries)
    write_json(
        package_dir / materials_rel("evidence", "framework_change_summary.json"),
        {
            "source": "android-knowledge-intake",
            "mode": "patch",
            "synthetic_data": synthetic_mode(config),
            "patch_count": len(patch_entries),
            "patches": patch_sources,
            "capture_package_count": len(patch_package_paths or []),
            "supplement_mode": inferred_mode,
            "implementation_origins": unique_strings(
                str(item.get("implementation_origin") or "")
                for item in patch_entries
                if str(item.get("implementation_origin") or "").strip()
            ),
            "capture_tools": unique_strings(str(item.get("captured_by") or "") for item in patch_entries if str(item.get("captured_by") or "").strip()),
        },
    )
    ensure_patch_analysis_evidence(package_dir, patch_entries, capture_evidence_entries, summary)
    if not has_pass_verification:
        downgrade_validated_patch_entries(patch_entries, "未携带 PASS 设备验证或合格等价验证，已按 candidate 提交")
    for item in patch_entries:
        if item.get("status") in {"failed", "blocked"}:
            item["reuse_hint"] = False

    platform, android_version = apply_platform_overrides(
        *infer_platform_metadata(patch_entries, capture_evidence_entries, package_dir),
        platform_override=platform_override,
        android_version_override=android_version_override,
    )
    auto_related_report_run_ids: list[str] = []
    if not all_related_report_run_ids:
        auto_related_report_run_ids = same_day_daily_report_run_ids(config, date)
        all_related_report_run_ids.extend(auto_related_report_run_ids)
    related_project_clues = related_report_project_clues(
        config,
        all_related_report_run_ids,
        daily_label_prefix="自动关联同日日报" if auto_related_report_run_ids else "关联日报",
    )
    project, project_payload = infer_project(
        project,
        patch_entries,
        patch_sources,
        summary,
        package_dir,
        source_contexts,
        related_project_clues,
        trusted_platform=platform,
    )
    if not framework_metadata_is_traceable(project, platform, android_version):
        downgrade_validated_patch_entries(
            patch_entries,
            "项目（project）、平台（platform）或 Android 版本（Android version）缺少可追溯元数据，已按 candidate 提交",
        )
    statuses = {str(item.get("status", "")) for item in patch_entries}
    source_path = materials_rel("evidence", "source.json")
    source = write_package_source(package_dir, config, "android-knowledge-intake")
    package_status = framework_package_status_from_patch_statuses(statuses, has_pass_verification)
    all_patch_items = [incoming_patch_item(package_dir, item) for item in patch_entries]
    implementation_origins = unique_strings(
        str(item.get("implementation_origin") or "")
        for item in all_patch_items
        if str(item.get("implementation_origin") or "").strip()
    )
    if implementation_origins:
        source["implementation_origins"] = implementation_origins
        if len(implementation_origins) == 1:
            source["implementation_origin"] = implementation_origins[0]
        write_json(package_dir / source_path, {"kind": "source", "payload": source})
    capture_tools = unique_strings(str(item.get("captured_by") or "") for item in all_patch_items if str(item.get("captured_by") or "").strip())
    modified_files = sorted(
        {
            file
            for item in all_patch_items
            for file in item.get("facts", {}).get("modified_files", [])
            if isinstance(file, str) and file
        }
    )
    repo_paths = sorted(
        {
            str(item.get("repo_path") or "").strip("/")
            for item in all_patch_items
            if str(item.get("repo_path") or "").strip("/")
        }
    ) or repo_paths_from_files(modified_files)
    patch_rel_paths = [str(item["path"]) for item in all_patch_items]
    all_related_report_run_ids = unique_strings(all_related_report_run_ids)
    case_id, variant_id = framework_case_variant_ids(
        summary=summary,
        platform=platform,
        android_version=android_version,
        project=project,
        repo_paths=repo_paths,
    )
    patch_problem_payload = first_evidence_payload(package_dir, capture_evidence_entries, "patch_problem_summary")
    case_problem = str(patch_problem_payload.get("problem_summary") or summary)
    case_solution = str(patch_problem_payload.get("solution_summary") or summary)

    case_path = write_case_file(
        package_dir,
        case_id=case_id,
        summary=summary,
        case_problem=case_problem,
        case_solution=case_solution,
    )
    variant_path = write_variant_file(
        package_dir,
        variant_id=variant_id,
        case_id=case_id,
        platform=platform,
        android_version=android_version,
        project=project,
        repo_paths=repo_paths,
        implementation_origins=implementation_origins,
        capture_tools=capture_tools,
        package_status=package_status,
    )

    project_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "project_inference.json"),
        {
            "kind": "project_inference",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": project_payload,
        },
    )

    verification_payload = verification_payload_or_missing(
        first_evidence_payload(package_dir, capture_evidence_entries, "verification_result")
    )
    verification_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "verification_result.json"),
        {
            "kind": "verification_result",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": verification_payload,
        },
    )
    if package_status == "validated" and str(verification_payload.get("result", "")).upper() != "PASS":
        package_status = "candidate"

    capture_search_payload = first_evidence_payload(package_dir, capture_evidence_entries, "search_before_change")
    member_search_payload = search_usage_payload(config, date, feature_tokens=patch_search_feature_tokens(summary, all_patch_items, modified_files))
    search_payload = select_search_before_change_payload(
        capture_search_payload=capture_search_payload,
        member_search_payload=member_search_payload,
        capture_has_member_decision=search_payload_has_member_decision(capture_search_payload),
    )
    search_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "search_before_change.json"),
        {
            "kind": "search_before_change",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": search_payload,
        },
    )
    optional_evidence_paths = [
        rel
        for kind in sorted(FRAMEWORK_OPTIONAL_EVIDENCE_KINDS)
        for rel in [first_evidence_path(capture_evidence_entries, kind)]
        if rel
    ]

    patch_diff_payload = aggregate_patch_diff_facts(all_patch_items)
    patch_diff_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "patch_diff_facts.json"),
        {
            "kind": "patch_diff_facts",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": patch_diff_payload,
        },
    )
    patch_problem_path = first_evidence_path(capture_evidence_entries, "patch_problem_summary")
    risk_path = first_evidence_path(capture_evidence_entries, "risk_surface")
    required_generated = {
        "patch_diff_facts": patch_diff_path,
        "patch_problem_summary": patch_problem_path,
        "risk_surface": risk_path,
    }
    required_generated = ensure_required_patch_explanation_evidence(
        package_dir,
        required_generated=required_generated,
        case_id=case_id,
        variant_id=variant_id,
        summary=summary,
    )

    supplement_for_package_key = str(supplement_for_package_key or "").strip()
    supplement_reason = str(supplement_reason or "").strip()
    supplement_path = ""
    if supplement_for_package_key:
        if not supplement_reason:
            supplement_reason = "补充原始上传包的沉淀证据。"
        supplement_path = write_evidence_supplement(
            package_dir,
            date=date,
            config=config,
            run_id=run_id,
            case_id=case_id,
            variant_id=variant_id,
            target_package_key=supplement_for_package_key,
            reason=supplement_reason,
            project=project,
            platform=platform,
            android_version=android_version,
            package_status=package_status,
            summary=summary,
            supplement_mode=inferred_mode,
        )

    manifest_context = {
        "summary": summary,
        "project": project,
        "platform": platform,
        "android_version": android_version,
        "member_alias": config["member_alias"],
        "member_name": config["member_name"],
    }
    patch_view_path, patch_ai_facts_path = write_patch_view_and_ai_facts(
        package_dir,
        manifest_context=manifest_context,
        case_id=case_id,
        variant_id=variant_id,
        case_problem=case_problem,
        case_solution=case_solution,
        verification_payload=verification_payload,
        risk_payload=first_evidence_payload(package_dir, capture_evidence_entries, "risk_surface"),
        patch_rel_paths=patch_rel_paths,
        supplement_for_package_key=supplement_for_package_key,
        supplement_reason=supplement_reason,
        patch_diff_payload=patch_diff_payload,
        search_payload=search_payload,
        plugin_version=plugin_install_metadata().get("plugin_version", ""),
    )

    write_variant_file(
        package_dir,
        variant_id=variant_id,
        case_id=case_id,
        platform=platform,
        android_version=android_version,
        project=project,
        repo_paths=repo_paths,
        implementation_origins=implementation_origins,
        capture_tools=capture_tools,
        package_status=package_status,
        related_report_run_ids=all_related_report_run_ids,
    )
    manifest = framework_change_manifest(
        schema_version=INCOMING_SCHEMA_VERSION,
        config=config,
        date=date,
        run_id=run_id,
        case_id=case_id,
        variant_id=variant_id,
        package_status=package_status,
        platform=platform,
        android_version=android_version,
        project=project,
        summary=summary,
        implementation_origins=implementation_origins,
        capture_tools=capture_tools,
        case_path=case_path,
        variant_path=variant_path,
        feature_readme_rel=feature_readme_rel,
        patch_rel_paths=patch_rel_paths,
        patch_view_path=patch_view_path,
        evidence_paths=[
            source_path,
            required_generated["patch_diff_facts"],
            patch_ai_facts_path,
            project_path,
            required_generated["patch_problem_summary"],
            required_generated["risk_surface"],
            verification_path,
            search_path,
            *([supplement_path] if supplement_path else []),
            *optional_evidence_paths,
        ],
        related_report_run_ids=all_related_report_run_ids,
        supplement_for_package_key=supplement_for_package_key,
        supplement_reason=supplement_reason,
        supplement_mode=inferred_mode,
    )
    for evidence_rel in manifest["files"]["evidence"]:
        bind_framework_evidence(package_dir, evidence_rel, case_id, variant_id)
    write_json(package_dir / "manifest.json", manifest)
    check = validate_package(package_dir)
    write_json(package_dir / "local-check.json", check)
    return package_dir



def git_run(repo: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return _intake_git_run(repo, args, run, check=check)


def submit_package(package_dir: Path, config: dict[str, str]) -> dict[str, Any]:
    return _submit_package(
        package_dir,
        config,
        validate_package_fn=validate_package,
        write_json_fn=write_json,
        patch_upload_gate_errors_fn=patch_upload_gate_errors,
    )


from akbs_intake.submit import (  # noqa: E402
    http_submit_package,
    package_tar_gz_bytes,
    server_submit_package,
    submit_package as _submit_package,
    upload_type_for_manifest,
)


def latest_pending(report_type: str, config: dict[str, str], date: dt.date | None = None) -> Path:
    return _intake_latest_pending(report_type, config, date)


def doctor_strict_checks(
    config: dict[str, str],
    loaded: list[Path],
    check_remote: bool,
    allow_synthetic: bool,
) -> dict[str, Any]:
    return _intake_doctor_strict_checks(
        config,
        loaded,
        check_remote,
        allow_synthetic,
        run_command=run,
        plugin_gate_check=plugin_version_gate_check,
    )


def doctor(
    config: dict[str, str],
    loaded: list[Path],
    strict: bool = False,
    check_remote: bool = False,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    return _intake_doctor(
        config,
        loaded,
        strict,
        check_remote,
        allow_synthetic,
        plugin_root=PLUGIN_ROOT,
        run_command=run,
        plugin_gate_check=plugin_version_gate_check,
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and submit Codex team knowledge incoming packages.")
    parser.add_argument("--profile", help="profile name from config, for example admin_alias or member_alias")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--strict", action="store_true", help="fail when the selected profile is unsafe for member-side automation")
    doctor_parser.add_argument("--check-remote", action="store_true", help="also verify plugin freshness and optional local knowledge fallback reachability")
    doctor_parser.add_argument("--allow-synthetic", action="store_true", help="allow synthetic_data=true for protocol or gray-flow testing")
    doctor_parser.set_defaults(report_type="")

    for report_type in ("daily", "weekly", "patch"):
        sub = subparsers.add_parser(report_type)
        sub.set_defaults(report_type=report_type)
        sub.add_argument("--date", help="YYYY-MM-DD, defaults to today")
        sub.add_argument("--run-id", help="override run id, format YYYYMMDD-HHMMSS[-suffix]")
        sub.add_argument("--schema-version", choices=[INCOMING_SCHEMA_VERSION], default="", help="incoming package schema version")
        if report_type == "patch":
            sub.add_argument("--patch", dest="patches", action="append", default=[], help="patch file to include; repeatable")
            sub.add_argument("--patch-package", dest="patch_packages", action="append", default=[], help="android-framework-patch-capture package directory to include; repeatable")
            sub.add_argument("--project", default="unknown", help="project name for framework_change incoming")
            sub.add_argument("--platform", default="", help="explicit platform for framework_change incoming: mtk, rk, unisoc, or unknown")
            sub.add_argument("--android-version", default="", help="explicit Android version for framework_change incoming, for example 14, 16, or 9.0")
            sub.add_argument("--summary", default="Framework 修改沉淀", help="summary for framework_change incoming")
            sub.add_argument("--related-report-run-id", dest="related_report_run_ids", action="append", default=[], help="daily/weekly incoming run_id related to this framework_change; repeatable")
            sub.add_argument("--supplement-for-package-key", default="", help="original incoming package key that this framework_change package supplements")
            sub.add_argument("--supplement-reason", default="", help="why this package supplements the original incoming package")
            sub.add_argument("--supplement-mode", choices=["field_correction", "asset_correction"], default="", help="field_correction for project/platform/Android version metadata supplements, asset_correction for full patch asset recapture")
            sub.add_argument("--corrected-field", dest="corrected_fields", action="append", default=[], help="field=value correction for field_correction supplements; repeatable")
            sub.add_argument("--correction-reason", default="", help="audit reason for field_correction supplements")
            sub.add_argument(
                "--status",
                choices=["draft", "candidate", "validated", "failed", "blocked"],
                default="validated",
                help="patch package status",
            )
        if report_type == "weekly":
            sub.add_argument(
                "--replace-weekly-run-id",
                default="",
                help="explicitly regenerate a weekly package for an existing week_range and write supersedes metadata",
            )
        if report_type == "daily":
            sub.add_argument(
                "--replace-daily-run-id",
                default="",
                help="explicitly regenerate a daily package for an existing report date and write supersedes metadata",
            )
        action = sub.add_mutually_exclusive_group(required=True)
        action.add_argument("--prepare", action="store_true", help="generate pending package only")
        action.add_argument("--submit-latest", action="store_true", help="submit latest pending package")
        action.add_argument("--upload", action="store_true", help="prepare then submit")
        action.add_argument("--validate", metavar="PACKAGE_DIR", help="validate an existing package")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    config, loaded = load_config(args.profile)

    if args.command == "doctor":
        result = doctor(config, loaded, args.strict, args.check_remote, args.allow_synthetic)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not args.strict or result.get("status") == "PASS" else 1

    if args.command in PACKAGE_TYPES and not args.validate and (args.prepare or args.submit_latest or args.upload):
        freshness = plugin_version_gate_check(config, fetch=True, require=True)
        if freshness.get("blocking"):
            reexec_error = reexec_latest_plugin_script_after_update(freshness)
            if reexec_error:
                freshness["reexec_error"] = reexec_error
            print(
                json.dumps(
                    {
                        "status": "FAIL",
                        "message": freshness.get("reexec_error") or freshness.get("message") or "插件更新检查失败。",
                        "plugin_freshness": freshness,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1

    date = parse_date_arg(args.date, config)
    if args.validate:
        result = validate_package(Path(args.validate))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PASS" else 1
    if args.prepare or args.submit_latest or args.upload:
        enforce_mode_allowed(config, args.report_type)
    if args.prepare:
        schema_version = args.schema_version or config.get("incoming_schema_version", INCOMING_SCHEMA_VERSION)
        if args.report_type == "patch":
            package_dir = prepare_patch_package(
                date,
                config,
                args.run_id,
                args.patches,
                args.patch_packages,
                args.project,
                args.summary,
                args.status,
                schema_version,
                args.related_report_run_ids,
                args.supplement_for_package_key,
                args.supplement_reason,
                args.platform,
                args.android_version,
                args.supplement_mode,
                parse_corrected_field_args(args.corrected_fields),
                args.correction_reason,
            )
        else:
            package_dir = prepare_package(
                args.report_type,
                date,
                config,
                args.run_id,
                schema_version,
                getattr(args, "replace_daily_run_id", "") or getattr(args, "replace_weekly_run_id", ""),
            )
        result = json.loads((package_dir / "local-check.json").read_text(encoding="utf-8"))
        print(json.dumps({"package": str(package_dir), "local_check": result}, ensure_ascii=False, indent=2))
        if args.report_type in {"daily", "weekly"}:
            return 0
        return 0 if result["status"] == "PASS" else 1
    if args.submit_latest:
        package_dir = latest_pending(args.report_type, config, date if args.date else None)
        result = submit_package(package_dir, config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.upload:
        schema_version = args.schema_version or config.get("incoming_schema_version", INCOMING_SCHEMA_VERSION)
        if args.report_type == "patch":
            package_dir = prepare_patch_package(
                date,
                config,
                args.run_id,
                args.patches,
                args.patch_packages,
                args.project,
                args.summary,
                args.status,
                schema_version,
                args.related_report_run_ids,
                args.supplement_for_package_key,
                args.supplement_reason,
                args.platform,
                args.android_version,
                args.supplement_mode,
                parse_corrected_field_args(args.corrected_fields),
                args.correction_reason,
            )
        else:
            package_dir = prepare_package(
                args.report_type,
                date,
                config,
                args.run_id,
                schema_version,
                getattr(args, "replace_daily_run_id", "") or getattr(args, "replace_weekly_run_id", ""),
            )
        result = submit_package(package_dir, config)
        print(json.dumps({"package": str(package_dir), "submit": result}, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
