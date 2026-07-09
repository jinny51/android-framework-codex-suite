from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Callable

from android_framework_ops.knowledge_rules import (
    VALID_FRAMEWORK_PLATFORMS,
    is_valid_android_version_value,
    patch_asset_correction_source_errors,
)

from akbs_intake.config import expanded_path, local_now, require_safe_artifact_path
from akbs_intake.io_utils import materials_rel, stable_slug_id, write_json
from akbs_intake.patch.evidence import patch_view_payload
from akbs_intake.project_identity import project_inference_payload
from akbs_intake.report_sessions import ymd


ValidatePackage = Callable[[Path], dict[str, Any]]
BindFrameworkEvidence = Callable[[Path, str, str, str], None]
WritePackageSource = Callable[[Path, dict[str, str], str], dict[str, Any]]


def write_default_evidence(package_dir: Path, rel: str, payload: dict[str, Any]) -> str:
    write_json(package_dir / rel, payload)
    return rel


def write_evidence_supplement(
    package_dir: Path,
    *,
    date: dt.date,
    config: dict[str, str],
    run_id: str,
    case_id: str,
    variant_id: str,
    target_package_key: str,
    reason: str,
    project: str,
    platform: str,
    android_version: str,
    package_status: str,
    summary: str,
    supplement_mode: str,
    payload_extra: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "target_package_key": target_package_key,
        "reason": reason,
        "source_package_key": f"{ymd(date)}/{config['member_alias']}/{run_id}",
        "project": project,
        "platform": platform,
        "android_version": android_version,
        "package_status": package_status,
        "summary": summary,
        "supplement_mode": supplement_mode,
    }
    payload.update(payload_extra or {})
    return write_default_evidence(
        package_dir,
        materials_rel("evidence", "evidence_supplement.json"),
        {
            "kind": "evidence_supplement",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": payload,
        },
    )


def parse_corrected_field_args(items: list[str] | None) -> dict[str, str]:
    corrected: dict[str, str] = {}
    for raw in items or []:
        item = str(raw or "").strip()
        if not item:
            continue
        if "=" not in item:
            raise SystemExit(f"--corrected-field 必须使用 field=value 格式: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise SystemExit(f"--corrected-field 字段名不能为空: {item}")
        corrected[key] = value
    return corrected


def normalize_corrected_fields(
    corrected_fields: dict[str, Any] | None,
    *,
    project: str = "",
    platform: str = "",
    android_version: str = "",
    material_identity_fields: set[str] | None = None,
) -> dict[str, str]:
    normalized = {
        str(key or "").strip(): str(value or "").strip()
        for key, value in (corrected_fields or {}).items()
        if str(key or "").strip() and str(value or "").strip()
    }
    identity_fields = sorted(set(normalized) & set(material_identity_fields or set()))
    if identity_fields:
        raise SystemExit(
            "字段级补证不能修正材料身份字段: "
            + ", ".join(identity_fields)
            + "；材料名或材料摘要错误时，请重新生成替换原始包。"
        )
    if project and project != "unknown":
        normalized.setdefault("project", project)
    if platform and platform != "unknown":
        normalized.setdefault("platform", platform)
    if android_version and android_version != "unknown":
        normalized.setdefault("android_version", android_version)
    return normalized


def infer_supplement_mode(
    explicit_mode: str,
    supplement_for_package_key: str,
    supplement_reason: str,
    corrected_fields: dict[str, Any] | None,
) -> str:
    mode = str(explicit_mode or "").strip()
    if mode:
        return mode
    if not str(supplement_for_package_key or "").strip():
        return ""
    if corrected_fields:
        return "field_correction"
    if patch_asset_correction_source_errors(
        {
            "package_kind": "framework_change",
            "supplement_for_package_key": supplement_for_package_key,
            "supplement_reason": supplement_reason,
        },
        {"capture_package_count": 0},
    ):
        return "asset_correction"
    return ""


def framework_package_status_from_patch_statuses(statuses: set[str], has_pass_verification: bool) -> str:
    clean = {item for item in statuses if item in {"validated", "candidate", "draft", "failed", "blocked"}}
    if has_pass_verification and "validated" in clean:
        return "validated"
    if "candidate" in clean or ("validated" in clean and not has_pass_verification):
        return "candidate"
    if "draft" in clean:
        return "draft"
    if "failed" in clean:
        return "failed"
    if "blocked" in clean:
        return "blocked"
    return "candidate"


def downgrade_validated_patch_entries(patch_entries: list[dict[str, Any]], note: str) -> None:
    for item in patch_entries:
        if item.get("status") == "validated":
            item["status"] = "candidate"
            item["reuse_hint"] = False
            previous_note = str(item.get("note") or "").strip()
            item["note"] = f"{previous_note}；{note}" if previous_note else note


def framework_metadata_is_traceable(project: str, platform: str, android_version: str) -> bool:
    return (
        project not in {"", "unknown"}
        and platform in VALID_FRAMEWORK_PLATFORMS
        and is_valid_android_version_value(android_version)
        and android_version != "unknown"
    )


def prepare_field_correction_package(
    date: dt.date,
    config: dict[str, str],
    run_id: str,
    *,
    project: str,
    platform: str,
    android_version: str,
    summary: str,
    schema_version: str,
    supplement_for_package_key: str,
    supplement_reason: str,
    corrected_fields: dict[str, str],
    correction_reason: str,
    validate_package_fn: ValidatePackage,
    bind_framework_evidence_fn: BindFrameworkEvidence,
    write_package_source_fn: WritePackageSource,
) -> Path:
    if not supplement_for_package_key:
        raise SystemExit("字段级补证必须提供 --supplement-for-package-key，且必须指向原始包。")
    out_dir = require_safe_artifact_path(expanded_path(config["out_dir"]), purpose="out_dir")
    package_dir = require_safe_artifact_path(out_dir / "pending" / ymd(date) / config["member_alias"] / run_id, purpose="incoming package output")
    if package_dir.exists():
        raise SystemExit(f"工作包已存在: {package_dir}")
    package_dir.mkdir(parents=True)

    source_path = materials_rel("evidence", "source.json")
    write_package_source_fn(package_dir, config, "android-knowledge-intake")
    case_id = "case-" + stable_slug_id(supplement_for_package_key, "field-correction", 80)
    variant_seed = json.dumps(
        {
            "target": supplement_for_package_key,
            "project": project,
            "platform": platform,
            "android_version": android_version,
            "corrected_fields": corrected_fields,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    variant_id = "variant-" + stable_slug_id(supplement_for_package_key, "field-correction", 100, variant_seed)
    case_path = materials_rel("case.json")
    variant_path = materials_rel("variant.json")
    readme_path = "README.md"
    package_status = "validated"

    readme_lines = [
        f"# {summary}",
        "",
        "## 补证类型",
        "",
        "字段级 / 展示级补证（field correction）。",
        "",
        "## 补证目标",
        "",
        supplement_for_package_key,
        "",
        "## 修正字段",
        "",
        *[f"- {key}: {value}" for key, value in sorted(corrected_fields.items())],
        "",
        "## 说明",
        "",
        correction_reason or supplement_reason or "补充原始包的结构化字段。",
        "",
        "本包不包含补丁 diff、验证结论、patch_ai_facts 或代码证据；这些核心证据缺口必须完整重采。",
        "",
    ]
    (package_dir / readme_path).write_text("\n".join(readme_lines), encoding="utf-8")
    write_json(
        package_dir / case_path,
        {
            "case_id": case_id,
            "title": summary,
            "problem": correction_reason or supplement_reason or summary,
            "solution_summary": "补充结构化字段和展示字段，不修改补丁资产或验证证据。",
        },
    )
    write_json(
        package_dir / variant_path,
        {
            "variant_id": variant_id,
            "case_id": case_id,
            "platform": platform,
            "android_version": android_version,
            "project": project,
            "repo_paths": [],
            "related_report_run_ids": [],
            "implementation_origins": [],
            "capture_tools": [],
            "package_status": package_status,
        },
    )

    project_payload = project_inference_payload(
        project,
        [f"字段补证 corrected_fields.project={project}"] if project != "unknown" else [],
        ["corrected_fields", "command_args"],
        [f"{key}: {value}" for key, value in sorted(corrected_fields.items())],
        [] if project != "unknown" else ["字段补证未提供可识别项目名"],
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
    expected_source_key = f"{ymd(date)}/{config['member_alias']}/{run_id}"
    correction_payload = {
        "target_package_key": supplement_for_package_key,
        "source_package_key": expected_source_key,
        "supplement_mode": "field_correction",
        "corrected_fields": corrected_fields,
        "correction_reason": correction_reason or supplement_reason,
        "corrected_by": {
            "member_alias": config["member_alias"],
            "member_name": config["member_name"],
        },
        "corrected_at": local_now(config).isoformat(),
        "notes": "字段级补证不携带补丁 diff、验证结论、patch_ai_facts 或代码证据。",
    }
    field_correction_path = write_default_evidence(
        package_dir,
        materials_rel("evidence", "field_correction.json"),
        {
            "kind": "field_correction",
            "case_id": case_id,
            "variant_id": variant_id,
            "payload": correction_payload,
        },
    )
    supplement_path = write_evidence_supplement(
        package_dir,
        date=date,
        config=config,
        run_id=run_id,
        case_id=case_id,
        variant_id=variant_id,
        target_package_key=supplement_for_package_key,
        reason=supplement_reason or correction_reason,
        project=project,
        platform=platform,
        android_version=android_version,
        package_status=package_status,
        summary=summary,
        supplement_mode="field_correction",
        payload_extra={
            "corrected_fields": corrected_fields,
            "correction_reason": correction_reason or supplement_reason,
            "corrected_by": correction_payload["corrected_by"],
            "corrected_at": correction_payload["corrected_at"],
        },
    )
    patch_view_path = materials_rel("display", "patch_view.json")
    manifest_context = {
        "summary": summary,
        "project": project,
        "platform": platform,
        "android_version": android_version,
        "member_alias": config["member_alias"],
        "member_name": config["member_name"],
    }
    write_json(
        package_dir / patch_view_path,
        patch_view_payload(
            manifest_context,
            case_problem=correction_reason or supplement_reason or summary,
            case_solution="补充结构化字段和展示字段，不修改补丁资产或验证证据。",
            verification_payload={"result": "INFO", "method": "field_correction", "summary": "字段级补证，不包含补丁 diff、验证结论或代码证据。"},
            risk_payload={"risk_areas": ["仅修正字段；核心证据缺口仍需完整重采。"]},
            patch_rel_paths=[],
            supplement_for_package_key=supplement_for_package_key,
            supplement_reason=supplement_reason or correction_reason,
            supplement_mode="field_correction",
            corrected_fields=corrected_fields,
        ),
    )
    manifest = {
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
        "implementation_origins": [],
        "capture_tools": [],
        "supplement_for_package_key": supplement_for_package_key,
        "supplement_reason": supplement_reason or correction_reason,
        "supplement_mode": "field_correction",
        "material_identity": {
            "mode": "inherit_target_package",
            "target_package_key": supplement_for_package_key,
            "editable": False,
        },
        "corrected_fields": corrected_fields,
        "correction_reason": correction_reason or supplement_reason,
        "files": {
            "case": case_path,
            "variant": variant_path,
            "readme": readme_path,
            "patches": [],
            "display": [patch_view_path],
            "evidence": [source_path, project_path, supplement_path, field_correction_path],
        },
    }
    for evidence_rel in manifest["files"]["evidence"]:
        bind_framework_evidence_fn(package_dir, evidence_rel, case_id, variant_id)
    write_json(package_dir / "manifest.json", manifest)
    check = validate_package_fn(package_dir)
    write_json(package_dir / "local-check.json", check)
    return package_dir
