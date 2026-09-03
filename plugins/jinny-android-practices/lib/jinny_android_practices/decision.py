"""Bind provider decisions to the installed manifest and declared Skill."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


PROVIDER_RELATIVE = Path("contracts/android-practices-provider/v1/provider.json")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[2]


def provider_manifest_path() -> Path:
    return plugin_root() / PROVIDER_RELATIVE


def provider_manifest() -> tuple[dict[str, Any], str]:
    path = provider_manifest_path()
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    plugin = json.loads((plugin_root() / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("schema") != "android-practices-provider-v1"
        or value.get("provider_id") != plugin.get("name")
        or value.get("provider_version") != plugin.get("version")
    ):
        raise RuntimeError("Jinny provider identity differs from the installed plugin")
    interface = plugin.get("interface")
    capabilities = interface.get("capabilities") if isinstance(interface, dict) else None
    if not isinstance(capabilities, list) or "Write" in capabilities:
        raise RuntimeError("Jinny decision-only plugin must not declare Write")
    return value, hashlib.sha256(raw).hexdigest()


def require_sha256(value: str, *, field: str) -> str:
    if not SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be 64 lowercase hexadecimal characters")
    return value


def provider_binding(capability: str) -> dict[str, str]:
    provider, digest = provider_manifest()
    value = provider.get("capabilities", {}).get(capability)
    if not isinstance(value, dict):
        raise RuntimeError(f"Jinny provider does not declare {capability}")
    skill_root = plugin_root() / "skills" / str(value["skill_id"])
    content_paths = {
        "skill_sha256": skill_root / "SKILL.md",
        "agent_metadata_sha256": skill_root / "agents/openai.yaml",
        "decision_entrypoint_sha256": plugin_root() / str(value["decision_entrypoint_path"]),
    }
    for field, path in content_paths.items():
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise RuntimeError(f"Jinny declared provider content is unavailable: {path}") from exc
        if actual != value.get(field):
            raise RuntimeError(f"Jinny declared provider content hash differs: {field}")
    return {
        "provider_id": str(provider["provider_id"]),
        "provider_version": str(provider["provider_version"]),
        "provider_manifest_sha256": digest,
        "skill_id": str(value["skill_id"]),
        "skill_version": str(value["skill_version"]),
        "skill_sha256": str(value["skill_sha256"]),
        "agent_metadata_sha256": str(value["agent_metadata_sha256"]),
        "decision_entrypoint_sha256": str(value["decision_entrypoint_sha256"]),
    }
