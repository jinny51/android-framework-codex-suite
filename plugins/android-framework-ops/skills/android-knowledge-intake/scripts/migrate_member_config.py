#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any


SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from akbs_intake.config import default_codex_home, parse_bool, read_toml  # noqa: E402


ENDPOINT_SECTIONS = {"submission", "knowledge"}
ENDPOINT_FIELDS = {
    "server_profile",
    "knowledge_repo_url",
    "submission_method",
    "submission_ssh_host",
    "submission_command",
    "submission_api_base_url",
    "submission_session_cookie",
    "submission_api_token",
}


def default_config_path() -> Path:
    return Path(default_codex_home()) / "report" / "config.toml"


def toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_scalar(item) for item in value) + "]"
    text = str(value)
    return json.dumps(text, ensure_ascii=False)


def clean_mapping(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    cleaned: dict[str, Any] = {}
    removed: list[str] = []
    for key, value in payload.items():
        if key in ENDPOINT_SECTIONS:
            removed.append(key)
            continue
        if key in ENDPOINT_FIELDS:
            removed.append(key)
            continue
        if key == "profiles" and isinstance(value, dict):
            profiles: dict[str, Any] = {}
            for profile_name, profile_payload in value.items():
                if not isinstance(profile_payload, dict):
                    profiles[profile_name] = profile_payload
                    continue
                profile_cleaned = {}
                for profile_key, profile_value in profile_payload.items():
                    if profile_key in ENDPOINT_SECTIONS or profile_key in ENDPOINT_FIELDS:
                        removed.append(f"profiles.{profile_name}.{profile_key}")
                        continue
                    profile_cleaned[profile_key] = profile_value
                profiles[profile_name] = profile_cleaned
            cleaned[key] = profiles
            continue
        cleaned[key] = value
    return cleaned, sorted(dict.fromkeys(removed))


def render_config(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    root_keys = [key for key, value in payload.items() if not isinstance(value, dict)]
    for key in root_keys:
        lines.append(f"{key} = {toml_scalar(payload[key])}")
    for section_name, section_payload in payload.items():
        if not isinstance(section_payload, dict) or section_name == "profiles":
            continue
        if lines:
            lines.append("")
        lines.append(f"[{section_name}]")
        for key, value in section_payload.items():
            if not isinstance(value, dict):
                lines.append(f"{key} = {toml_scalar(value)}")
    profiles = payload.get("profiles")
    if isinstance(profiles, dict):
        for profile_name, profile_payload in profiles.items():
            if lines:
                lines.append("")
            lines.append(f"[profiles.{profile_name}]")
            if isinstance(profile_payload, dict):
                for key, value in profile_payload.items():
                    if not isinstance(value, dict):
                        lines.append(f"{key} = {toml_scalar(value)}")
    return "\n".join(lines).rstrip() + "\n"


def migrate_config(path: Path, dry_run: bool = False) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"配置文件不存在: {path}")
    payload = read_toml(path)
    cleaned, removed = clean_mapping(payload)
    rendered = render_config(cleaned)
    current = path.read_text(encoding="utf-8")
    changed = bool(removed) or rendered != current
    result: dict[str, Any] = {
        "status": "MIGRATED" if changed else "CURRENT",
        "config_path": str(path),
        "dry_run": dry_run,
        "removed_fields": removed,
    }
    if not changed or dry_run:
        return result
    backup = path.with_suffix(path.suffix + f".bak-{dt.datetime.now():%Y%m%d%H%M%S}")
    backup.write_text(current, encoding="utf-8")
    path.write_text(rendered, encoding="utf-8")
    result["backup_path"] = str(backup)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate AKBS member config to HTTP-only endpoint resolver.")
    parser.add_argument("--config", type=Path, default=default_config_path(), help="member config path")
    parser.add_argument("--dry-run", action="store_true", help="show migration result without writing")
    args = parser.parse_args()
    result = migrate_config(args.config.expanduser(), dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
