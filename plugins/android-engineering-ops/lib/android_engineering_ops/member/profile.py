"""Resolve policy identity without importing the AKBS member plugin.

The engineering core only reads the stable target and legacy member-profile files.  It
does not own setup, migration, or writes to those files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from android_engineering_ops.policy.patch_markers import require_valid_alias
from android_engineering_ops.configuration import (
    EngineeringConfigError,
    parse_engineering_config,
)
from android_engineering_ops.member_config import (
    default_codex_home,
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
    source: str


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


def _present(path: Path) -> bool:
    """Treat even a dangling symlink as a present, invalid authority."""
    return path.exists() or path.is_symlink()


def _legacy_config_paths() -> list[Path]:
    codex_home = Path(default_codex_home())
    return [
        codex_home / "android-knowledge-intake.toml",
        codex_home / "android-knowledge-search.toml",
        codex_home / "report" / "config.toml",
    ]


def _load_payload(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise MemberProfileError(f"member profile config must not be a symlink: {path}")
    try:
        return load_toml(path, strict=True)
    except ValueError as exc:
        raise MemberProfileError(f"failed to read member profile config {path}: {exc}") from exc


def _valid_alias(alias: str, *, label: str) -> str:
    value = alias.strip()
    if not value or value in {"member_alias", "admin_alias", "unknown"}:
        raise MemberProfileError(f"{label} has no usable member_alias")
    try:
        return require_valid_alias(value)
    except ValueError as exc:
        raise MemberProfileError(f"{label} has an unsafe member_alias") from exc


def _selected_identity(
    payload: dict[str, Any],
    selected: str,
) -> dict[str, str]:
    value = dict(DEFAULTS)
    value.update(_flatten(payload))
    if selected:
        profile = _profiles(payload).get(selected)
        if profile is not None:
            value.update(profile)
    return value


def _standalone_identity(path: Path) -> str:
    try:
        before = path.lstat()
        if path.is_symlink() or not path.is_file():
            raise MemberProfileError(
                f"standalone engineering identity must be a regular non-symlink file: {path}"
            )
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise MemberProfileError(f"failed to read standalone engineering identity {path}: {exc}") from exc
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    if identity(before) != identity(after):
        raise MemberProfileError(f"standalone engineering identity changed while read: {path}")
    try:
        payload = parse_engineering_config(
            raw, allow_identity=True, require_extension=False
        )
    except EngineeringConfigError as exc:
        raise MemberProfileError(f"failed to read standalone engineering identity {path}: {exc}") from exc
    values = payload.get("identity")
    if values is None:
        return ""
    return _valid_alias(values.get("member_alias", ""), label="standalone identity")


def load_member_profile(profile_override: str | None = None) -> MemberProfile:
    codex_home = Path(default_codex_home())
    target = codex_home / "akbs-member-ops.toml"
    legacy_paths = _legacy_config_paths()
    engineering = codex_home / "android-engineering-ops.toml"
    loaded: list[Path] = []
    requested = (profile_override or "").strip() or _profile_from_env()
    selected = ""
    alias = ""
    member_name = ""
    timezone = DEFAULTS["timezone"]
    source = ""

    legacy_payloads: dict[Path, dict[str, Any]] = {}
    if _present(target):
        target_payload = _load_payload(target)
        loaded.append(target)
        selected = requested or _flatten(target_payload).get("default_profile", "").strip()
        profiles = _profiles(target_payload)
        if not selected:
            raise MemberProfileError(
                "authoritative akbs-member-ops.toml has no selected profile"
            )
        if selected not in profiles:
            raise MemberProfileError(
                f"authoritative member profile does not exist: {selected}"
            )
        config = _selected_identity(target_payload, selected)
        alias = _valid_alias(config["member_alias"], label=f"member profile {selected}")
        member_name = config["member_name"].strip()
        timezone = config["timezone"].strip() or DEFAULTS["timezone"]
        source = "akbs-member-ops"
    else:
        for path in legacy_paths:
            if _present(path):
                legacy_payloads[path] = _load_payload(path)
                loaded.append(path)
        defaults = {
            _flatten(payload).get("default_profile", "").strip()
            for payload in legacy_payloads.values()
            if _flatten(payload).get("default_profile", "").strip()
        }
        if not requested and len(defaults) > 1:
            raise MemberProfileError("legacy member configs select conflicting profiles")
        selected = requested or (next(iter(defaults)) if defaults else "")
        aliases: dict[str, list[Path]] = {}
        selected_values: list[dict[str, str]] = []
        for path, payload in legacy_payloads.items():
            values = _selected_identity(payload, selected)
            candidate = values["member_alias"].strip()
            if candidate and candidate not in {"member_alias", "admin_alias", "unknown"}:
                normalized = _valid_alias(candidate, label=f"legacy identity {path}")
                aliases.setdefault(normalized, []).append(path)
                selected_values.append(values)
        if len(aliases) > 1:
            raise MemberProfileError("legacy member configs contain conflicting member_alias values")
        if aliases:
            alias = next(iter(aliases))
            source = "legacy-member-profile"
            if selected_values:
                member_name = next(
                    (value["member_name"].strip() for value in selected_values if value["member_name"].strip()),
                    "",
                )
                timezone = next(
                    (value["timezone"].strip() for value in selected_values if value["timezone"].strip()),
                    DEFAULTS["timezone"],
                )

    standalone_alias = ""
    if _present(engineering):
        standalone_alias = _standalone_identity(engineering)
        if engineering not in loaded:
            loaded.append(engineering)
    if alias and standalone_alias and alias != standalone_alias:
        raise MemberProfileError("AKBS and standalone engineering member_alias conflict")
    if not alias:
        if requested:
            if legacy_payloads:
                raise MemberProfileError(f"member profile does not exist: {requested}")
            raise MemberProfileError(
                "--profile/environment profile may select only an existing AKBS profile"
            )
        if not standalone_alias:
            raise MemberProfileError(
                "current Android change requires an AKBS profile or "
                "$CODEX_HOME/android-engineering-ops.toml [identity].member_alias"
            )
        alias = standalone_alias
        selected = "standalone"
        source = "android-engineering-ops-identity"

    return MemberProfile(
        profile=selected,
        member_alias=alias,
        member_name=member_name,
        timezone=timezone,
        loaded_paths=tuple(loaded),
        source=source,
    )
