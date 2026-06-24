from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SEMVER_RE = re.compile(r"^\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9_.-]+)?$")
VALID_FRAMEWORK_PLATFORMS = {"mtk", "rk", "unisoc"}
PLATFORM_PREFIX_ALIASES = {
    "mtk": "mtk",
    "rk": "rk",
    "unisoc": "unisoc",
    "sprd": "unisoc",
    "u": "unisoc",
}
PLATFORM_TOKEN_RE = re.compile(r"^(mtk|rk|unisoc|sprd|u)(\d{1,2})(?:-|$)", re.I)
PLATFORM_ARG_TOKEN_RE = re.compile(r"^(mtk|rk|unisoc|sprd|u)(\d{1,2})$", re.I)
PLATFORM_TOKEN_SEARCH_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:platform\s*[:=]\s*)?(mtk|rk|unisoc|sprd|u)(\d{1,2})(?![A-Za-z0-9])",
    re.I,
)
VERSION_ONLY_TOKEN_RE = re.compile(r"^(?:android|app)(\d{1,2})(?:-|$)", re.I)
UNCONTROLLED_APP_PATCH_ASSET_RE = re.compile(r"^app\d+(?:[-_@.]|$)", re.I)

PROJECT_MODEL_RE = re.compile(
    r"(?<![A-Z0-9])(?P<base>TV[DEAI]\d{2}[A-Z0-9]{2}[MRU]\d?|TVE8402)"
    r"(?P<branch_suffix>(?:_[A-Z0-9]+)*)(?![A-Z0-9_])",
    re.I,
)
PROJECT_FIELD_RE = re.compile(r"TV[DEAI]\d{2}[A-Z0-9]{2}[MRU]\d?", re.I)
PROJECT_ANCHOR_RE = PROJECT_MODEL_RE
PROJECT_ALIASES = {"TVE8402": "TVE8402M"}

DAILY_BUNDLE_SUMMARY_RE = re.compile(
    r"(?:今日|本日|当天)补丁|补丁合集|(?:今日|本日|当天).*?(?:\d+\s*(?:个|项|份)|多个|若干).*?补丁"
)
MULTI_FEATURE_COLLECTION_RE = re.compile(
    r"(?:多功能混包|多个独立(?:功能|需求|补丁)|多个(?:功能|需求|补丁).*?(?:合集|汇总|整理)|"
    r"[两二三四五六七八九十]\s*项功能|\d+\s*项功能|\d+\s*个独立(?:功能|需求|补丁))"
)
LISTED_FEATURE_PACKAGE_RE = re.compile(r"[^，。；\n]+、[^，。；\n]+(?:，)?(?:以及|和)[^，。；\n]+补丁包")

REUSE_DECISIONS = {"reuse", "adapt", "reference_only", "not_applicable", "not_found", "unknown"}
CODEX_IMPLEMENTATION_ORIGINS = {"codex"}


def normalize_android_version(platform: str, version: str) -> str:
    platform = str(platform or "").strip().lower()
    version = str(version or "").strip().lower()
    if platform == "rk" and version in {"71", "90"}:
        return {"71": "7.1", "90": "9.0"}[version]
    return version.lstrip("0") or version


def is_valid_platform_value(value: str) -> bool:
    value = str(value or "").strip().lower()
    return value in VALID_FRAMEWORK_PLATFORMS or value == "unknown"


def valid_framework_platform(value: str) -> bool:
    return str(value or "").strip().lower() in VALID_FRAMEWORK_PLATFORMS


def has_uncontrolled_app_patch_asset_prefix(value: Any) -> bool:
    return bool(UNCONTROLLED_APP_PATCH_ASSET_RE.match(Path(str(value or "")).name))


def is_valid_android_version_value(value: str) -> bool:
    value = str(value or "").strip().lower()
    return value == "unknown" or bool(re.fullmatch(r"\d+(?:\.\d+)?", value))


def valid_android_version(value: str) -> bool:
    value = str(value or "").strip().lower()
    return value not in {"", "unknown"} and bool(re.fullmatch(r"\d+(?:\.\d+)?", value))


def parse_known_platform_token(value: str) -> tuple[str, str]:
    token = Path(str(value or "")).name.lower()
    match = PLATFORM_TOKEN_RE.match(token)
    if not match:
        return "", ""
    prefix, raw_version = match.groups()
    platform = PLATFORM_PREFIX_ALIASES[prefix.lower()]
    return platform, normalize_android_version(platform, raw_version)


def find_platform_tokens(value: Any) -> list[tuple[str, str]]:
    text = str(value or "")
    tokens: list[tuple[str, str]] = []
    for match in PLATFORM_TOKEN_SEARCH_RE.finditer(text):
        prefix, raw_version = match.groups()
        platform = PLATFORM_PREFIX_ALIASES[prefix.lower()]
        token = (platform, normalize_android_version(platform, raw_version))
        if token not in tokens:
            tokens.append(token)
    return tokens


def parse_version_only_token(value: str) -> str:
    token = Path(str(value or "")).name.lower()
    match = VERSION_ONLY_TOKEN_RE.match(token)
    if not match:
        return ""
    raw_version = match.group(1)
    return raw_version.lstrip("0") or raw_version


def parse_platform_token(patch_entries: list[dict[str, Any]]) -> tuple[str, str]:
    explicit: list[tuple[str, str]] = []
    filename_tokens: list[tuple[str, str]] = []
    version_only: list[str] = []
    for item in patch_entries:
        platform = str(item.get("platform") or "").strip().lower()
        android_version = str(item.get("android_version") or "").strip().lower()
        if platform in VALID_FRAMEWORK_PLATFORMS and is_valid_android_version_value(android_version) and android_version != "unknown":
            explicit.append((platform, android_version))
        for key in ("platform_token", "path", "id", "name"):
            parsed = parse_known_platform_token(str(item.get(key) or ""))
            if parsed != ("", ""):
                filename_tokens.append(parsed)
        for key in ("path", "id", "name"):
            version = parse_version_only_token(str(item.get(key) or ""))
            if version:
                version_only.append(version)

    for candidates in (explicit, filename_tokens):
        unique = sorted(set(candidates))
        if len(unique) == 1:
            return unique[0]
        if len(unique) > 1:
            return "unknown", "unknown"

    unique_versions = sorted(set(version_only))
    if len(unique_versions) == 1:
        return "unknown", unique_versions[0]
    return "unknown", "unknown"


def parse_platform_arg(value: str) -> tuple[str, str, str]:
    token = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip().lower())
    token = re.sub(r"-+", "-", token).strip("-._")
    match = PLATFORM_ARG_TOKEN_RE.fullmatch(token)
    if not match:
        return "", "", ""
    prefix, raw_version = match.groups()
    platform = PLATFORM_PREFIX_ALIASES[prefix.lower()]
    android_version = normalize_android_version(platform, raw_version)
    filename_version = raw_version.lstrip("0") or raw_version
    return f"{platform}{filename_version}", platform, android_version


def apply_platform_overrides(
    inferred_platform: str,
    inferred_android_version: str,
    platform_override: str = "",
    android_version_override: str = "",
) -> tuple[str, str]:
    platform = str(inferred_platform or "unknown").strip().lower() or "unknown"
    android_version = str(inferred_android_version or "unknown").strip().lower() or "unknown"
    explicit_platform = str(platform_override or "").strip().lower()
    explicit_android_version = str(android_version_override or "").strip().lower()
    if explicit_platform:
        if not is_valid_platform_value(explicit_platform):
            raise SystemExit(f"--platform 只能使用 mtk/rk/unisoc/unknown，当前为: {explicit_platform}")
        platform = explicit_platform
    if explicit_android_version:
        android_version = normalize_android_version(platform, explicit_android_version)
        if not is_valid_android_version_value(android_version):
            raise SystemExit(f"--android-version 必须是明确数字版本或 unknown，当前为: {explicit_android_version}")
    return platform, android_version


def canonical_company_project(value: str) -> str:
    project = str(value or "").strip().upper()
    return PROJECT_ALIASES.get(project, project)


def split_company_project(value: str) -> tuple[str, str]:
    project = str(value or "").strip().upper()
    match = PROJECT_FIELD_RE.fullmatch(project)
    if not match:
        return "", ""
    return match.group(0).upper(), ""


def valid_project_model(value: str) -> bool:
    base, _suffix = split_company_project(value)
    return bool(base)


def parse_company_project(value: str) -> dict[str, Any]:
    base, suffix = split_company_project(value)
    soc_code = base[7:8] if base else ""
    extension_code = base[8:] if len(base) > 8 else ""
    return {
        "base_model": base,
        "product_prefix": base[:2],
        "form_code": base[2:3],
        "mold_code": base[3:7],
        "soc_code": soc_code,
        "extension_code": extension_code,
        "suffix": suffix,
        "recognition_scope": "TVD/TVE/TVA/TVI",
        "company_rule_match": bool(base),
    }


def find_company_project(text: str) -> str:
    match = PROJECT_MODEL_RE.search(str(text or "").upper())
    return canonical_company_project(match.group("base")) if match else ""


def find_company_projects(text: str) -> list[str]:
    return sorted(
        dict.fromkeys(canonical_company_project(match.group("base")) for match in PROJECT_MODEL_RE.finditer(str(text or "").upper()))
    )


def project_model_parts(project: str) -> dict[str, str]:
    parsed = parse_company_project(project)
    if not parsed.get("base_model"):
        return {"base_model": "", "suffix": ""}
    return {
        "base_model": str(parsed["base_model"]),
        "suffix": str(parsed.get("suffix") or ""),
    }


def project_mentions_in_text(text: str) -> list[str]:
    return find_company_projects(text)


def framework_applicability_gaps(anchors: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    project = str(anchors.get("project") or "").strip()
    platform = str(anchors.get("platform") or "").strip()
    android_version = str(anchors.get("android_version") or "").strip()
    if project in {"", "unknown"} or not valid_project_model(project):
        gaps.append("project")
    if not valid_framework_platform(platform):
        gaps.append("platform")
    if not valid_android_version(android_version):
        gaps.append("android_version")
    if anchors.get("project_traceability_issue") and "project" not in gaps:
        gaps.append("project")
    return gaps


def aggregate_package_scope_errors(text: str, patch_count: int = 0) -> list[str]:
    if not (
        DAILY_BUNDLE_SUMMARY_RE.search(text)
        or MULTI_FEATURE_COLLECTION_RE.search(text)
        or LISTED_FEATURE_PACKAGE_RE.search(text)
    ):
        return []
    count = f"当前约 {patch_count} 个补丁。" if patch_count else ""
    return [
        f"补丁包（patch package）不能是无共同目标的聚合包（aggregate package）。{count}"
        "请用补丁采集技能（android-framework-patch-capture）按功能拆分（function split）为多个普通补丁包；"
        "一个补丁包只能对应一个功能。"
    ]


def normalize_reuse_decision(value: Any) -> str:
    decision = str(value or "").strip().lower()
    return decision if decision in REUSE_DECISIONS else "unknown"


def implementation_requires_pre_change_search(implementation_origin: str) -> bool:
    origin = str(implementation_origin or "").strip().lower()
    return origin in CODEX_IMPLEMENTATION_ORIGINS


def search_results_need_usage_decision(results: Any) -> bool:
    if not isinstance(results, list) or not any(str(item).strip() for item in results):
        return False
    text = "\n".join(str(item) for item in results).lower()
    return not any(token in text for token in ("未发现", "未命中", "no reuse", "no candidate", "not found"))


def classify_pre_change_search(
    search_payload: dict[str, Any] | None,
    *,
    implementation_origin: str = "",
    package_status: str = "",
) -> dict[str, Any]:
    payload = search_payload if isinstance(search_payload, dict) else {}
    decision = normalize_reuse_decision(payload.get("reuse_decision") or payload.get("decision") or "")
    searched = bool(payload.get("searched"))
    results = payload.get("results")
    has_results = search_results_need_usage_decision(results)
    requires_search = implementation_requires_pre_change_search(implementation_origin)
    can_supplement = requires_search and searched and has_results and decision == "unknown"
    requires_overlap = not searched or not requires_search
    return {
        "searched": searched,
        "decision": decision,
        "has_results": has_results,
        "requires_pre_change_search": requires_search,
        "member_can_supplement": can_supplement,
        "missing_field": "search_usage" if can_supplement else "",
        "requires_post_change_overlap_check": requires_overlap,
        "validity_score_effect": "search_loop_score_possible" if searched and decision != "unknown" else "no_search_loop_score",
        "package_status": str(package_status or "").strip().lower(),
    }


def manifest_has_uncontrolled_app_patch_asset(manifest: dict[str, Any]) -> bool:
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    patches = files.get("patches") if isinstance(files.get("patches"), list) else []
    for rel in patches:
        if has_uncontrolled_app_patch_asset_prefix(rel):
            return True
    return False


def current_plugin_version() -> str:
    manifest_path = Path(__file__).resolve().parents[2] / ".codex-plugin" / "plugin.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("version") or "").strip()


def source_version_errors(payload: dict[str, Any] | None, *, expected_version: str | None = None) -> list[str]:
    source = payload if isinstance(payload, dict) else {}
    plugin_name = str(source.get("plugin_name") or "").strip()
    plugin_version = str(source.get("plugin_version") or "").strip()
    skill_version = str(source.get("skill_version") or "").strip()
    current_version = str(expected_version if expected_version is not None else current_plugin_version()).strip()
    errors: list[str] = []
    if plugin_name != "android-framework-ops":
        errors.append("source evidence plugin_name must be android-framework-ops")
    if not SEMVER_RE.fullmatch(plugin_version):
        errors.append("source evidence plugin_version is required for strict new uploads")
    if not SEMVER_RE.fullmatch(skill_version):
        errors.append("source evidence skill_version is required for strict new uploads")
    if current_version:
        if plugin_version and plugin_version != current_version:
            errors.append(f"source evidence plugin_version must match current plugin version {current_version}")
        if skill_version and skill_version != current_version:
            errors.append(f"source evidence skill_version must match current plugin version {current_version}")
    else:
        errors.append("current plugin version is unavailable; server upload entry cannot verify latest plugin")
    return errors
