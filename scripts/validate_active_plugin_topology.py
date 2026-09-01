#!/usr/bin/env python3
"""Validate the active functional-split plugin topology."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/plugin-topology/v1/active-topology.json"
MARKETPLACE = ROOT / ".agents/plugins/marketplace.json"
SKILL_RE = re.compile(r'^name\s*=\s*"([^"]+)"\s*$', re.MULTILINE)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"topology JSON must be an object: {path}")
    return value


def manifest_skills(plugin: str) -> list[str]:
    path = ROOT / "manifests" / f"{plugin}.toml"
    return SKILL_RE.findall(path.read_text(encoding="utf-8"))


def main() -> int:
    contract = load_json(CONTRACT)
    marketplace = load_json(MARKETPLACE)
    if contract.get("schema") != "android-plugin-topology-v1":
        raise SystemExit("invalid plugin topology schema")
    if contract.get("state") != "active":
        raise SystemExit("plugin topology must be active")
    if contract.get("canonical_core") != "android-framework-ops":
        raise SystemExit("canonical core must be android-framework-ops")

    expected_marketplace = {
        row["id"] for row in contract["plugins"] if row.get("marketplace") is True
    }
    actual_marketplace = {row["name"] for row in marketplace.get("plugins", [])}
    if actual_marketplace != expected_marketplace:
        raise SystemExit(
            f"marketplace topology mismatch: expected={sorted(expected_marketplace)} "
            f"actual={sorted(actual_marketplace)}"
        )

    for row in contract["plugins"]:
        plugin = row["id"]
        plugin_root = ROOT / "plugins" / plugin
        if not plugin_root.is_dir():
            raise SystemExit(f"declared plugin source is missing: {plugin}")
        if row.get("role") == "independent_source":
            continue
        actual_skills = manifest_skills(plugin)
        if actual_skills != row["skills"]:
            raise SystemExit(
                f"manifest skills mismatch for {plugin}: "
                f"expected={row['skills']} actual={actual_skills}"
            )
        for skill in actual_skills:
            if not (plugin_root / "skills" / skill / "SKILL.md").is_file():
                raise SystemExit(f"declared Skill is missing: {plugin}:{skill}")

    core = ROOT / "plugins/android-framework-ops"
    if (core / "skills/android-source-access").exists():
        raise SystemExit("core must not expose a third public android-source-access Skill")
    if not (core / "internal/android-source-access/scripts/android_source_access.py").is_file():
        raise SystemExit("core internal source-access dispatcher is missing")
    for plugin in ("android-wsl-ops", "android-mac-ops"):
        scripts = ROOT / "plugins" / plugin / "skills/android-source-access/scripts"
        if not (scripts / "_core_source_access.py").is_file():
            raise SystemExit(f"source-access locator is missing: {plugin}")
        if not (scripts / "_platform_shim.sh").is_file():
            raise SystemExit(f"source-access shim is missing: {plugin}")

    print("Active plugin topology validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
