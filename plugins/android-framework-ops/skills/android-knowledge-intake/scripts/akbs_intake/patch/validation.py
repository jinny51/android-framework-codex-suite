from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Pattern


RequireFile = Callable[[Any, str], Path | None]
ReadReferencedJson = Callable[[Path, str], dict[str, Any] | None]
ReadJsonFile = Callable[[Path], dict[str, Any]]
LoadEvidence = Callable[[list[Any]], dict[str, dict[str, Any]]]
ValidatePatchReadme = Callable[[Path], list[str]]
HasUncontrolledPatchAssetPrefix = Callable[[Any], bool]
ValueValidator = Callable[[str], bool]
TextFieldQualityErrors = Callable[[dict[str, Any]], list[str]]


@dataclass
class FrameworkChangeValidationContext:
    manifest_platform: str
    manifest_android_version: str
    package_status: str
    supplement_target: str
    supplement_mode: str
    is_field_correction: bool
    is_asset_correction: bool
    files: dict[str, Any]
    case_path: Path | None
    variant_path: Path | None
    readme_path: Path | None
    patch_paths: list[Any]
    display_paths: list[Any]
    evidence_paths: list[Any]


@dataclass
class FrameworkChangeStructureContext:
    case_problem: str
    case_solution: str
    evidence_by_kind: dict[str, dict[str, Any]]


def validate_framework_change_manifest_and_files(
    *,
    package_dir: Path,
    manifest: dict[str, Any],
    package_status_values: set[str],
    supplement_modes: set[str],
    run_id_re: Pattern[str],
    require_file: RequireFile,
    validate_patch_readme: ValidatePatchReadme,
    has_uncontrolled_patch_asset_prefix: HasUncontrolledPatchAssetPrefix,
    is_valid_platform_value: ValueValidator,
    is_valid_android_version_value: ValueValidator,
    errors: list[str],
) -> FrameworkChangeValidationContext:
    for field in ("case_id", "variant_id", "package_status", "platform", "android_version", "project"):
        if not manifest.get(field):
            errors.append(f"framework_change 缺少 {field}")

    manifest_platform = str(manifest.get("platform") or "").strip().lower()
    manifest_android_version = str(manifest.get("android_version") or "").strip().lower()
    if manifest_platform and not is_valid_platform_value(manifest_platform):
        errors.append(f"framework_change platform 非法: {manifest_platform}；只能使用 mtk/rk/unisoc/unknown")
    if manifest_android_version and not is_valid_android_version_value(manifest_android_version):
        errors.append(f"framework_change android_version 非法: {manifest_android_version}")
    if "maturity" in manifest:
        errors.append("framework_change manifest 不允许使用 maturity；请使用 package_status")

    package_status = str(manifest.get("package_status", ""))
    if package_status not in package_status_values:
        errors.append(f"package_status 非法: {package_status}")

    supplement_target = str(manifest.get("supplement_for_package_key") or "").strip()
    supplement_mode = str(manifest.get("supplement_mode") or "").strip()
    if supplement_mode and supplement_mode not in supplement_modes:
        errors.append(f"supplement_mode 非法: {supplement_mode}")
    is_field_correction = supplement_mode == "field_correction"
    is_asset_correction = supplement_mode == "asset_correction"
    if is_field_correction and not supplement_target:
        errors.append("字段级补证（field_correction）必须提供 supplement_for_package_key")

    if "related_report_run_ids" in manifest:
        related = manifest.get("related_report_run_ids")
        if not isinstance(related, list):
            errors.append("related_report_run_ids 必须是数组")
        else:
            for item in related:
                if not run_id_re.fullmatch(str(item or "")):
                    errors.append(f"related_report_run_ids 包含非法 run_id: {item}")

    files = manifest.get("files")
    if not isinstance(files, dict):
        errors.append("framework_change files 必须是对象")
        files = {}

    case_path = require_file(files.get("case"), "files.case")
    variant_path = require_file(files.get("variant"), "files.variant")
    readme_path = require_file(files.get("readme"), "files.readme")
    patch_paths = files.get("patches", [])
    display_paths = files.get("display", [])
    evidence_paths = files.get("evidence", [])

    if not isinstance(patch_paths, list):
        errors.append("files.patches 必须是数组")
        patch_paths = []
    elif is_field_correction and patch_paths:
        errors.append("字段级补证（field_correction）不能携带 patch/diff 补丁资产")
    elif not is_field_correction and not patch_paths:
        errors.append("files.patches 必须是非空数组")
        patch_paths = []

    if not isinstance(display_paths, list) or not display_paths:
        errors.append("framework_change files.display 必须包含 materials/display/patch_view.json")
        display_paths = []
    if not isinstance(evidence_paths, list) or not evidence_paths:
        errors.append("files.evidence 必须是非空数组")
        evidence_paths = []

    for patch_path in patch_paths:
        path = require_file(patch_path, "patch")
        if path and path.suffix not in {".patch", ".diff"}:
            errors.append(f"patch 文件必须是 .patch 或 .diff: {patch_path}")
        if has_uncontrolled_patch_asset_prefix(patch_path):
            errors.append(
                f"补丁资产（patch asset）不能使用非受控前缀: {patch_path}；"
                "前缀必须是合法项目名（project）或 mtk/rk/unisoc 受控平台 Android 版本前缀。"
            )

    if readme_path and not is_field_correction:
        errors.extend(validate_patch_readme(readme_path))
    if not is_field_correction:
        for patch_readme_path in sorted((package_dir / "patches").glob("*.readme.md")):
            errors.extend(validate_patch_readme(patch_readme_path))

    return FrameworkChangeValidationContext(
        manifest_platform=manifest_platform,
        manifest_android_version=manifest_android_version,
        package_status=package_status,
        supplement_target=supplement_target,
        supplement_mode=supplement_mode,
        is_field_correction=is_field_correction,
        is_asset_correction=is_asset_correction,
        files=files,
        case_path=case_path,
        variant_path=variant_path,
        readme_path=readme_path,
        patch_paths=patch_paths,
        display_paths=display_paths,
        evidence_paths=evidence_paths,
    )


def validate_framework_change_structure(
    *,
    package_dir: Path,
    manifest: dict[str, Any],
    package_status: str,
    is_field_correction: bool,
    supplement_target: str,
    case_path: Path | None,
    variant_path: Path | None,
    evidence_paths: list[Any],
    load_evidence: LoadEvidence,
    read_json_file: ReadJsonFile,
    read_referenced_json: ReadReferencedJson,
    text_field_quality_errors: TextFieldQualityErrors,
    is_valid_platform_value: ValueValidator,
    is_valid_android_version_value: ValueValidator,
    legacy_patch_problem_kind: str,
    framework_required_evidence_kinds: set[str],
    field_correction_required_evidence_kinds: set[str],
    field_correction_forbidden_evidence_kinds: set[str],
    field_correction_allowed_fields: set[str],
    field_correction_forbidden_fields: set[str],
    errors: list[str],
) -> FrameworkChangeStructureContext:
    case_problem = ""
    case_solution = ""
    if case_path:
        case = read_json_file(case_path)
        if case.get("case_id") != manifest.get("case_id"):
            errors.append("case_id 不一致")
        for field in ("title", "problem", "solution_summary"):
            if not case.get(field):
                errors.append(f"case 缺少 {field}")
        errors.extend(
            text_field_quality_errors(
                {
                    "case.title": case.get("title"),
                    "case.problem": case.get("problem"),
                    "case.solution_summary": case.get("solution_summary"),
                }
            )
        )
        case_problem = str(case.get("problem") or "")
        case_solution = str(case.get("solution_summary") or "")

    if variant_path:
        variant = read_json_file(variant_path)
        if variant.get("variant_id") != manifest.get("variant_id"):
            errors.append("variant_id 不一致")
        if "status" in variant:
            errors.append("variant 不允许使用 status；请使用 package_status")
        if variant.get("package_status") != package_status:
            errors.append("variant.package_status 必须等于 manifest.package_status")
        required_variant_fields = (
            ("platform", "android_version", "project", "package_status")
            if is_field_correction
            else ("platform", "android_version", "project", "repo_paths", "package_status")
        )
        for field in required_variant_fields:
            if not variant.get(field):
                errors.append(f"variant 缺少 {field}")
        variant_platform = str(variant.get("platform") or "").strip().lower()
        variant_android_version = str(variant.get("android_version") or "").strip().lower()
        if variant_platform and not is_valid_platform_value(variant_platform):
            errors.append(f"variant.platform 非法: {variant_platform}；只能使用 mtk/rk/unisoc/unknown")
        if variant_android_version and not is_valid_android_version_value(variant_android_version):
            errors.append(f"variant.android_version 非法: {variant_android_version}")
        if variant.get("platform") != manifest.get("platform"):
            errors.append("variant.platform 必须等于 manifest.platform")
        if variant.get("android_version") != manifest.get("android_version"):
            errors.append("variant.android_version 必须等于 manifest.android_version")
        if variant.get("project") != manifest.get("project"):
            errors.append("variant.project 必须等于 manifest.project")

    evidence_by_kind = load_evidence(evidence_paths)
    for rel in evidence_paths:
        if not isinstance(rel, str):
            continue
        evidence = read_referenced_json(package_dir, rel)
        if not isinstance(evidence, dict):
            continue
        if evidence.get("kind") == legacy_patch_problem_kind:
            errors.append(f"{rel} 使用了残留补丁问题证据类型；请改用 patch_problem_summary")
        if evidence.get("case_id") != manifest.get("case_id"):
            errors.append(f"{rel} evidence.case_id 必须等于 manifest.case_id")
        if evidence.get("variant_id") != manifest.get("variant_id"):
            errors.append(f"{rel} evidence.variant_id 必须等于 manifest.variant_id")
        if evidence.get("kind") == "patch_problem_summary":
            payload = evidence
            if "payload" in payload:
                errors.append(f"{rel} 必须直接使用顶层字段，不能再包一层 payload")
            if not payload.get("problem_summary") or not payload.get("solution_summary"):
                errors.append(f"{rel} 必须包含 problem_summary 和 solution_summary")
            if not isinstance(payload.get("basis"), list) or not payload.get("basis"):
                errors.append(f"{rel} basis 必须是非空数组")
            if not isinstance(payload.get("limits"), list):
                errors.append(f"{rel} limits 必须是数组")

    required_evidence_kinds = (
        field_correction_required_evidence_kinds
        if is_field_correction
        else framework_required_evidence_kinds
    )
    for kind in required_evidence_kinds:
        if kind not in evidence_by_kind:
            errors.append(f"framework_change 缺少 {kind} evidence")

    if is_field_correction:
        forbidden_evidence = sorted(field_correction_forbidden_evidence_kinds & set(evidence_by_kind))
        if forbidden_evidence:
            errors.append(
                "字段级补证不能携带核心证据 evidence: "
                + ", ".join(forbidden_evidence)
                + "；缺这些内容时必须完整重采。"
            )
        corrected_fields = manifest.get("corrected_fields")
        if not isinstance(corrected_fields, dict) or not corrected_fields:
            errors.append("字段级补证必须提供非空 corrected_fields")
            corrected_fields = {}
        forbidden_fields = sorted(field_correction_forbidden_fields & {str(field) for field in corrected_fields})
        if forbidden_fields:
            errors.append(
                "字段级补证不能补核心证据字段: "
                + ", ".join(forbidden_fields)
                + "；缺验证、补丁资产、patch_ai_facts 或搜索证据时必须完整重采。"
            )
        unknown_fields = sorted(
            set(str(field) for field in corrected_fields)
            - field_correction_allowed_fields
            - field_correction_forbidden_fields
        )
        if unknown_fields:
            errors.append("字段级补证 corrected_fields 包含未知字段: " + ", ".join(unknown_fields))
        field_correction = evidence_by_kind.get("field_correction", {})
        field_payload = field_correction.get("payload", field_correction) if isinstance(field_correction, dict) else {}
        if not isinstance(field_payload, dict):
            field_payload = {}
        if field_payload.get("target_package_key") != supplement_target:
            errors.append("field_correction.target_package_key 必须等于 manifest.supplement_for_package_key")
        if field_payload.get("corrected_fields") != corrected_fields:
            errors.append("field_correction.corrected_fields 必须等于 manifest.corrected_fields")
        if field_payload.get("supplement_mode") != "field_correction":
            errors.append("field_correction.supplement_mode 必须是 field_correction")
        if not field_payload.get("correction_reason"):
            errors.append("field_correction.correction_reason 必须提供")
        corrected_by = field_payload.get("corrected_by")
        if not isinstance(corrected_by, dict) or corrected_by.get("member_alias") != manifest.get("member_alias"):
            errors.append("field_correction.corrected_by.member_alias 必须等于 manifest.member_alias")

    return FrameworkChangeStructureContext(
        case_problem=case_problem,
        case_solution=case_solution,
        evidence_by_kind=evidence_by_kind,
    )


PATCH_VIEW_REQUIRED_FIELDS = (
    "material_kind_label",
    "display_title",
    "problem_summary",
    "solution_summary",
    "result_summary",
    "project",
    "platform",
    "android_version",
    "member_alias",
    "member_name",
    "ui_card",
    "detail_sections",
)
PATCH_VIEW_FORBIDDEN_TITLE_MARKERS = (
    "case-",
    "variant-",
    "merge_case_add_variant",
    "target_case_id",
    "source_package_keys",
)


def validate_patch_view_payload(
    *,
    rel: str,
    manifest: dict[str, Any],
    view: dict[str, Any],
    supplement_target: str,
    errors: list[str],
) -> None:
    for field in PATCH_VIEW_REQUIRED_FIELDS:
        if not view.get(field):
            errors.append(f"{rel} payload.{field} 必须提供")
    if view.get("project") != manifest.get("project"):
        errors.append(f"{rel} payload.project 必须等于 manifest.project")
    if view.get("platform") != manifest.get("platform"):
        errors.append(f"{rel} payload.platform 必须等于 manifest.platform")
    if view.get("android_version") != manifest.get("android_version"):
        errors.append(f"{rel} payload.android_version 必须等于 manifest.android_version")
    if supplement_target and view.get("supplement_for_package_key") != supplement_target:
        errors.append(f"{rel} payload.supplement_for_package_key 必须等于 manifest.supplement_for_package_key")
    title_text = " ".join(
        [
            str(view.get("display_title") or ""),
            str(view.get("ui_card", {}).get("title") if isinstance(view.get("ui_card"), dict) else ""),
        ]
    )
    for forbidden in PATCH_VIEW_FORBIDDEN_TITLE_MARKERS:
        if forbidden in title_text:
            errors.append(f"{rel} 主展示标题不能包含内部字段或机器锚点: {forbidden}")


def validate_patch_display_files(
    *,
    package_dir: Path,
    display_paths: list[Any],
    manifest: dict[str, Any],
    supplement_target: str,
    require_file: RequireFile,
    read_referenced_json: ReadReferencedJson,
    errors: list[str],
) -> None:
    for rel in display_paths:
        path = require_file(rel, "display")
        if not path:
            continue
        patch_view = read_referenced_json(package_dir, rel)
        if not isinstance(patch_view, dict):
            continue
        if patch_view.get("kind") != "patch_view":
            errors.append(f"{rel} kind 必须是 patch_view")
            continue
        view = patch_view.get("payload", {})
        if not isinstance(view, dict):
            errors.append(f"{rel} payload 必须是对象")
            continue
        validate_patch_view_payload(
            rel=rel,
            manifest=manifest,
            view=view,
            supplement_target=supplement_target,
            errors=errors,
        )
