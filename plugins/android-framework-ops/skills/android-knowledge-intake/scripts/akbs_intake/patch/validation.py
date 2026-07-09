from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


RequireFile = Callable[[Any, str], Path | None]
ReadReferencedJson = Callable[[Path, str], dict[str, Any] | None]

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
