from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Pattern


RequireFile = Callable[[Any, str], Path | None]
ReadReferencedJson = Callable[[Path, str], dict[str, Any] | None]
ValidatePatchReadme = Callable[[Path], list[str]]
HasUncontrolledPatchAssetPrefix = Callable[[Any], bool]
ValueValidator = Callable[[str], bool]


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
