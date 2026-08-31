"""Resolve policy identity from the existing member profile configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from android_engineering_ops.policy.patch_markers import require_valid_alias
from android_framework_ops.member_config import (
    default_codex_home,
    find_project_report_config,
    load_toml,
)


ENV_PREFIXES = ("CODEX_REPORT_", "CODEX_WORK_REPORT_")
PROFILE_FIELDS = {"member_alias", "member_name", "timezone"}
DEFAULTS = {
    "default_profile": "",
    "member_alias": "",
    "member_name": "",
    "timezone": "Asia/Shanghai",
}


class MemberProfileError(ValueError):
    """The selected member profile cannot provide a safe policy identity."""


@dataclass(frozen=True)
class MemberProfile:
    profile: str
    member_alias: str
    member_name: str
    timezone: str
    loaded_paths: tuple[Path, ...]


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _flatten(payload: dict[str, Any]) -> dict[str, str]:
    flattened: dict[str, str] = {}
    for key, value in payload.items():
        if key == "profiles" or isinstance(value, dict):
            if key == "member" and isinstance(value, dict):
                if "alias" in value:
                    flattened["member_alias"] = _stringify(value["alias"])
                if "name" in value:
                    flattened["member_name"] = _stringify(value["name"])
            continue
        normalized = {
            "alias": "member_alias",
            "person": "member_name",
            "name": "member_name",
        }.get(str(key), str(key))
        if normalized in {*PROFILE_FIELDS, "default_profile"}:
            flattened[normalized] = _stringify(value)
    return flattened


def _profiles(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    rows = payload.get("profiles")
    if not isinstance(rows, dict):
        return {}
    return {
        str(name): _flatten(values)
        for name, values in rows.items()
        if isinstance(values, dict)
    }


def _profile_from_env() -> str:
    for prefix in ENV_PREFIXES:
        value = os.environ.get(f"{prefix}PROFILE", "").strip()
        if value:
            return value
    return ""


def _config_paths() -> list[Path]:
    plugin_root = Path(__file__).resolve().parents[3]
    codex_home = Path(default_codex_home())
    paths = [
        plugin_root / "skills" / "android-knowledge-intake" / "config.toml",
        codex_home / "android-knowledge-intake.toml",
        codex_home / "report" / "config.toml",
    ]
    project_config = find_project_report_config()
    if project_config:
        paths.append(project_config)
    return paths


def load_member_profile(profile_override: str | None = None) -> MemberProfile:
    config = dict(DEFAULTS)
    loaded: list[Path] = []
    profiles: dict[str, dict[str, str]] = {}
    for path in _config_paths():
        if not path.exists():
            continue
        try:
            payload = load_toml(path, strict=True)
        except ValueError as exc:
            raise MemberProfileError(f"failed to read member profile config {path}: {exc}") from exc
        loaded.append(path)
        config.update(_flatten(payload))
        for name, values in _profiles(payload).items():
            profiles.setdefault(name, {}).update(values)

    selected = (
        (profile_override or "").strip()
        or _profile_from_env()
        or config["default_profile"].strip()
    )
    if not selected:
        raise MemberProfileError(
            "current Android change requires a selected member profile; use --profile or configure default_profile"
        )
    if selected not in profiles:
        raise MemberProfileError(f"member profile does not exist: {selected}")
    config.update(profiles[selected])

    alias = config["member_alias"].strip()
    if not alias or alias in {"member_alias", "admin_alias", "unknown"}:
        raise MemberProfileError(f"member profile {selected} has no usable member_alias")
    try:
        alias = require_valid_alias(alias)
    except ValueError as exc:
        raise MemberProfileError(f"member profile {selected} has an unsafe member_alias") from exc
    return MemberProfile(
        profile=selected,
        member_alias=alias,
        member_name=config["member_name"].strip(),
        timezone=config["timezone"].strip() or DEFAULTS["timezone"],
        loaded_paths=tuple(loaded),
    )
