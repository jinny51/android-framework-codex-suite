#!/usr/bin/env python3
"""Validate the released topology and declaration-only AKBS 2 contracts."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CURRENT_CONTRACT = ROOT / "contracts/plugin-topology/v1/active-topology.json"
MIGRATION_CONTRACT = ROOT / "contracts/plugin-topology/v2/migration-topology.json"
COMPATIBILITY_MATRIX = ROOT / "contracts/plugin-topology/v2/compatibility-matrix.json"
MARKETPLACE = ROOT / ".agents/plugins/marketplace.json"
SKILL_RE = re.compile(r'^name\s*=\s*"([^"]+)"\s*$', re.MULTILINE)
STATES = ("current", "migration", "target")
TARGET_PLUGINS = {
    "akbs-member-ops": (
        "akbs-member-setup", "akbs-knowledge-search", "akbs-knowledge-merge-review",
        "akbs-daily-report", "akbs-weekly-report", "akbs-patch-submit",
    ),
    "android-engineering-ops": (
        "android-change-policy", "android-change-workflow", "android-source-access",
        "android-remote-channel", "android-remote-build-deploy", "android-patch-capture",
    ),
    "jinny-android-practices": (
        "jinny-android-coding-practices", "jinny-android-execution-policy",
    ),
}
CHANGED_LEGACY_SKILLS = {
    "android-member-setup", "android-knowledge-search", "android-knowledge-merge-review",
    "android-daily-report-intake", "android-weekly-report-intake",
    "android-framework-patch-intake", "android-knowledge-intake", "android-change-policy",
    "android-framework-change-workflow", "android-framework-patch-capture",
    "android-source-access", "android-remote-channel", "android-remote-build-deploy",
    "jinny-framework-coding-standards",
}
REQUIRED_BEHAVIORS = {
    "read", "write", "default", "fallback", "activation", "deprecation", "removal", "test",
}
DEFAULT_FAMILY_KEYS = {
    "current": {"legacy_current"},
    "migration": {"legacy_rollback", "target_candidate"},
    "target": {"target_only"},
}
ALLOWED_DEFAULT_OWNERS = {
    "akbs-member-ops", "akbs-member-ops-config", "android-engineering-ops",
    "android-framework-ops", "android-knowledge-intake", "android-patch-capture",
    "capability-gated-v2", "core-direct", "framework-change-v1", "host-command-family",
    "host-specific-entry", "legacy-capture", "legacy-cli-family", "legacy-config",
    "legacy-engineering-cli", "legacy-install-family", "legacy-root", "legacy-source-access",
    "role-selected-target", "server-policy", "target-cli-family", "target-engineering-cli",
    "target-install-family", "target-root", "target-source-access",
    "target-source-command-family",
}
ALLOWED_COINSTALL_REFERENCES = {
    "akbs-member-ops", "android-engineering-ops", "android-framework-ops",
    "android-mac-ops", "android-wsl-ops", "legacy_and_target_source_access",
    "legacy_install_family", "target_install_family",
}
SURFACE_DEFAULT_BINDINGS = {
    "plugin.akbs-member-ops": (("android-framework-ops",), ("android-framework-ops",), ("akbs-member-ops",), ("akbs-member-ops",)),
    "plugin.android-engineering-ops": (("android-framework-ops",), ("android-framework-ops",), ("android-engineering-ops",), ("android-engineering-ops",)),
    "plugin.jinny-android-practices": ((), (), (), ()),
    "plugin.legacy-android-ops": (("android-framework-ops",), ("android-framework-ops",), (), ()),
    "plugin.codex-workspace-care": ((), (), (), ()),
    "skill.akbs-member-family": (("android-framework-ops",), ("android-framework-ops",), ("akbs-member-ops",), ("akbs-member-ops",)),
    "skill.android-engineering-family": (("android-framework-ops",), ("android-framework-ops",), ("android-engineering-ops",), ("android-engineering-ops",)),
    "skill.android-source-access": (("host-specific-entry",), ("host-specific-entry",), ("android-engineering-ops",), ("android-engineering-ops",)),
    "skill.jinny-provider-family": ((), (), (), ()),
    "skill.android-knowledge-intake": (("android-knowledge-intake",), ("android-knowledge-intake",), (), ()),
    "cli.akbs-member": (("legacy-cli-family",), ("legacy-cli-family",), ("target-cli-family",), ("target-cli-family",)),
    "cli.android-engineering": (("legacy-engineering-cli",), ("legacy-engineering-cli",), ("target-engineering-cli",), ("target-engineering-cli",)),
    "cli.source-access": (("host-command-family",), ("host-command-family",), ("target-source-command-family",), ("target-source-command-family",)),
    "config.member-profile": (("legacy-config",), ("legacy-config",), ("akbs-member-ops-config",), ("akbs-member-ops-config",)),
    "config.android-engineering-extension": (("core-direct",), ("core-direct",), ("core-direct",), ("core-direct",)),
    "state.source-access": (("legacy-source-access",), ("legacy-source-access",), ("target-source-access",), ("target-source-access",)),
    "artifact.akbs-member": (("legacy-root",), ("legacy-root",), ("target-root",), ("target-root",)),
    "artifact.android-patch-capture": (("legacy-capture",), ("legacy-capture",), ("android-patch-capture",), ("android-patch-capture",)),
    "artifact.android-remote-build-deploy": (("android-framework-ops",), ("android-framework-ops",), ("android-engineering-ops",), ("android-engineering-ops",)),
    "package.framework-change-v1": (("framework-change-v1",), ("framework-change-v1",), ("framework-change-v1",), ("server-policy",)),
    "package.android-change-v2": ((), (), (), ("capability-gated-v2",)),
    "cache.legacy-installations": (("legacy-install-family",), ("legacy-install-family",), ("target-install-family",), ("target-install-family",)),
    "marketplace.entries": (("android-framework-ops",), ("android-framework-ops",), ("role-selected-target",), ("role-selected-target",)),
}
SURFACE_COINSTALL_BINDINGS = {
    "plugin.akbs-member-ops": ("android-framework-ops",),
    "plugin.android-engineering-ops": ("android-framework-ops", "android-wsl-ops", "android-mac-ops"),
    "plugin.jinny-android-practices": (),
    "plugin.legacy-android-ops": ("akbs-member-ops", "android-engineering-ops"),
    "plugin.codex-workspace-care": (),
    "skill.akbs-member-family": ("android-framework-ops",),
    "skill.android-engineering-family": ("android-framework-ops",),
    "skill.android-source-access": ("android-wsl-ops", "android-mac-ops", "android-framework-ops"),
    "skill.jinny-provider-family": (),
    "skill.android-knowledge-intake": (),
    "cli.akbs-member": ("android-framework-ops",),
    "cli.android-engineering": ("android-framework-ops",),
    "cli.source-access": ("android-wsl-ops", "android-mac-ops", "android-framework-ops"),
    "config.member-profile": (),
    "config.android-engineering-extension": (),
    "state.source-access": ("legacy_and_target_source_access",),
    "artifact.akbs-member": (),
    "artifact.android-patch-capture": ("android-framework-ops",),
    "artifact.android-remote-build-deploy": ("android-framework-ops",),
    "package.framework-change-v1": (),
    "package.android-change-v2": (),
    "cache.legacy-installations": ("legacy_install_family", "target_install_family"),
    "marketplace.entries": ("legacy_install_family", "target_install_family"),
}
SURFACE_REMOVAL_BINDINGS = {
    "plugin.akbs-member-ops": ("per_plugin_surface_adoption_zero", "rollback_drill_passed"),
    "plugin.android-engineering-ops": ("per_plugin_surface_adoption_zero", "wsl_pilot", "macos_pilot", "rollback_drill_passed"),
    "plugin.jinny-android-practices": ("per_legacy_skill_adoption_zero",),
    "plugin.legacy-android-ops": ("per_surface_adoption_zero", "target_only_receipt", "rollback_drill_passed"),
    "plugin.codex-workspace-care": ("separate_user_decision",),
    "skill.akbs-member-family": ("per_skill_adoption_zero",),
    "skill.android-engineering-family": ("per_skill_adoption_zero", "rollback_drill_passed"),
    "skill.android-source-access": ("wsl_adoption_zero", "macos_adoption_zero"),
    "skill.jinny-provider-family": ("per_legacy_skill_adoption_zero",),
    "skill.android-knowledge-intake": ("per_legacy_cli_adoption_zero",),
    "cli.akbs-member": ("per_cli_adoption_zero",),
    "cli.android-engineering": ("per_cli_adoption_zero",),
    "cli.source-access": ("per_host_cli_adoption_zero",),
    "config.member-profile": ("writer_adoption_zero",),
    "config.android-engineering-extension": ("separate_contract_revision",),
    "state.source-access": ("never_delete_credentials_automatically",),
    "artifact.akbs-member": ("never_delete_historical_artifacts",),
    "artifact.android-patch-capture": ("never_delete_historical_captures",),
    "artifact.android-remote-build-deploy": ("never_delete_historical_artifacts",),
    "package.framework-change-v1": ("v1_read_is_permanent",),
    "package.android-change-v2": ("separate_contract_revision",),
    "cache.legacy-installations": ("member_target_only_receipt", "rollback_available"),
    "marketplace.entries": ("per_entry_adoption_zero", "rollback_drill_passed"),
}


class TopologyError(ValueError):
    """A released or declaration-only topology contract is inconsistent."""


def load_json_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise TopologyError(f"duplicate JSON key: {label}: {key}")
            value[key] = item
        return value

    def reject_constant(value: str) -> None:
        raise TopologyError(f"non-finite JSON number: {label}: {value}")

    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=strict_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TopologyError(f"strict JSON parse failed: {label}") from error
    if not isinstance(value, dict):
        raise TopologyError(f"JSON contract must be an object: {label}")
    return value


def load_json(path: Path) -> dict[str, Any]:
    return load_json_bytes(path.read_bytes(), label=str(path))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_skills(root: Path, plugin: str) -> list[str]:
    path = root / "manifests" / f"{plugin}.toml"
    return SKILL_RE.findall(path.read_text(encoding="utf-8"))


def _state_map(topology: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = topology.get("states")
    if not isinstance(rows, list):
        raise TopologyError("migration topology states must be a list")
    result = {str(row.get("id")): row for row in rows if isinstance(row, dict)}
    if tuple(result) != STATES or len(result) != len(rows):
        raise TopologyError("migration topology states must be ordered current/migration/target")
    return result


def _coverage(topology: dict[str, Any]) -> set[str]:
    groups = topology.get("compatibility_coverage")
    if not isinstance(groups, dict):
        raise TopologyError("compatibility coverage must be grouped by surface kind")
    values: list[str] = []
    for rows in groups.values():
        if not isinstance(rows, list) or not all(isinstance(row, str) and row for row in rows):
            raise TopologyError("compatibility coverage group is invalid")
        values.extend(rows)
    if len(values) != len(set(values)):
        raise TopologyError("compatibility coverage surface IDs must be unique")
    return set(values)


def _default_families(value: Any, *, surface_id: str) -> None:
    if not isinstance(value, dict) or set(value) != set(STATES):
        raise TopologyError(f"{surface_id} default behavior must cover all states")
    for state, families in value.items():
        if (
            not isinstance(families, dict)
            or set(families) != DEFAULT_FAMILY_KEYS[state]
        ):
            raise TopologyError(f"{surface_id} default families are missing for {state}")
        for owners in families.values():
            if (
                not isinstance(owners, list)
                or len(owners) > 1
                or not all(isinstance(owner, str) and owner for owner in owners)
                or not set(owners).issubset(ALLOWED_DEFAULT_OWNERS)
            ):
                raise TopologyError(f"{surface_id} has duplicate default owners in one install family")


def validate_contract_documents(
    current: dict[str, Any],
    topology: dict[str, Any],
    matrix: dict[str, Any],
    *,
    current_sha256: str,
) -> None:
    if current.get("schema") != "android-plugin-topology-v1" or current.get("state") != "active":
        raise TopologyError("released topology v1 is not the active authority")
    if topology.get("schema") != "android-plugin-topology-migration-v2":
        raise TopologyError("migration topology schema is invalid")
    if topology.get("contract_id") != "akbs2-three-plugin-topology-v1":
        raise TopologyError("migration topology contract ID is invalid")
    if topology.get("phase") != "phase0_contract_freeze":
        raise TopologyError("migration topology phase is not declaration-only Phase 0")
    if tuple(topology.get("state_order") or ()) != STATES:
        raise TopologyError("migration topology state order differs")
    expected_policy = {
        "default_state": "current",
        "materialized_states": ["current"],
        "declaration_only_states": ["migration", "target"],
        "current_authority": "contracts/plugin-topology/v1/active-topology.json",
        "current_authority_sha256": current_sha256,
        "undeclared_mixed_behavior": "reject",
    }
    if topology.get("physical_policy") != expected_policy:
        raise TopologyError("Phase 0 physical topology policy differs")
    states = _state_map(topology)
    if topology.get("system_identity") != {
        "brand": "AKBS",
        "official_name": "Android Knowledge Base System",
        "rejected_expression": "Android Framework 知识库",
    }:
        raise TopologyError("AKBS system identity differs")
    current_plugins = [row["id"] for row in current.get("plugins", [])]
    current_marketplace = [row["id"] for row in current.get("plugins", []) if row.get("marketplace") is True]
    if states["current"].get("source_plugins") != current_plugins:
        raise TopologyError("current fixture differs from released source plugins")
    if set(states["current"].get("marketplace_plugins") or []) != set(current_marketplace):
        raise TopologyError("current fixture differs from released marketplace plugins")
    if states["current"].get("mode") != "physical_default":
        raise TopologyError("current fixture is not the physical default")
    expected_catalog = {
        "akbs-member-ops", "android-engineering-ops", "jinny-android-practices",
        "android-framework-ops", "android-wsl-ops", "android-mac-ops",
    }
    if set(states["migration"].get("catalog_plugins") or []) != expected_catalog:
        raise TopologyError("migration catalog plugin set differs")
    if states["migration"].get("mode") != "declaration_fixture":
        raise TopologyError("migration fixture mode differs")
    legacy_entries = {
        item["id"]: item["mode"]
        for item in states["migration"].get("legacy_entries", [])
    }
    if legacy_entries != {
        "android-framework-ops": "compatibility_surface_only",
        "android-wsl-ops": "platform_wrapper_or_deprecation_notice_only",
        "android-mac-ops": "platform_wrapper_or_deprecation_notice_only",
    }:
        raise TopologyError("migration legacy plugin roles differ")
    migration_targets = {
        row["id"]: tuple(row["skills"])
        for row in states["migration"].get("canonical_plugins", [])
    }
    target_rows = {
        row["id"]: tuple(row.get("skills") or ())
        for row in states["target"].get("plugins", [])
    }
    if migration_targets != TARGET_PLUGINS:
        raise TopologyError("migration target plugins differ from the reviewed baseline")
    migration_aliases = {
        row["id"]: tuple(row.get("compatibility_skills") or ())
        for row in states["migration"].get("canonical_plugins", [])
    }
    if migration_aliases != {
        "akbs-member-ops": (
            "android-member-setup", "android-knowledge-search",
            "android-knowledge-merge-review", "android-daily-report-intake",
            "android-weekly-report-intake", "android-framework-patch-intake",
            "android-knowledge-intake",
        ),
        "android-engineering-ops": (
            "android-framework-change-workflow", "android-framework-patch-capture",
        ),
        "jinny-android-practices": ("jinny-framework-coding-standards",),
    }:
        raise TopologyError("migration compatibility Skill ownership differs")
    if {key: target_rows[key] for key in TARGET_PLUGINS} != TARGET_PLUGINS:
        raise TopologyError("target fixture differs from the reviewed three-plugin baseline")
    if (
        states["target"].get("mode") != "declaration_fixture"
        or states["target"].get("source_plugins")
        != ["akbs-member-ops", "android-engineering-ops", "jinny-android-practices", "codex-workspace-care"]
        or states["target"].get("marketplace_plugins")
        != ["akbs-member-ops", "android-engineering-ops", "jinny-android-practices"]
    ):
        raise TopologyError("target source or marketplace plugin set differs")
    target_roles = {
        item["id"]: item.get("role") for item in states["target"].get("plugins", [])
    }
    if target_roles != {
        "akbs-member-ops": "akbs_member_client",
        "android-engineering-ops": "android_engineering_controller_and_tools",
        "jinny-android-practices": "optional_practices_provider",
        "codex-workspace-care": "independent_source",
    }:
        raise TopologyError("target plugin roles differ")
    if target_rows.get("codex-workspace-care") != (
        "codex-chat-history-cleaner", "codex-chat-history-context-extractor",
    ):
        raise TopologyError("codex-workspace-care is not preserved independently")
    families = states["migration"].get("installation_families") or {}
    if (
        families.get("legacy_rollback", {}).get("coinstall_with_target") is not False
        or families.get("target_candidate", {}).get("coinstall_with_legacy") is not False
    ):
        raise TopologyError("legacy and target install families must be mutually exclusive")
    if matrix.get("schema") != "android-plugin-compatibility-matrix-v2":
        raise TopologyError("compatibility matrix schema is invalid")
    if matrix.get("topology_contract") != {
        "path": "migration-topology.json", "contract_id": topology["contract_id"],
    }:
        raise TopologyError("compatibility matrix topology binding differs")
    if tuple(matrix.get("state_order") or ()) != STATES:
        raise TopologyError("compatibility matrix state order differs")
    if set(matrix.get("required_behavior_keys") or ()) != REQUIRED_BEHAVIORS:
        raise TopologyError("compatibility matrix behavior contract differs")
    rows = matrix.get("rows")
    if not isinstance(rows, list):
        raise TopologyError("compatibility matrix rows must be a list")
    row_ids = [str(row.get("surface_id")) for row in rows if isinstance(row, dict)]
    if len(row_ids) != len(rows) or len(row_ids) != len(set(row_ids)):
        raise TopologyError("compatibility matrix surface IDs must be unique")
    if set(row_ids) != _coverage(topology):
        raise TopologyError("compatibility matrix rows do not exactly cover declared surfaces")
    if not (
        set(row_ids) == set(SURFACE_DEFAULT_BINDINGS)
        == set(SURFACE_COINSTALL_BINDINGS)
        == set(SURFACE_REMOVAL_BINDINGS)
    ):
        raise TopologyError("compatibility matrix semantic binding registry differs")
    allowed_kinds = {
        "plugin_identity", "skill_id", "cli_entrypoint_family", "config_path", "state_path",
        "artifact_root", "package_contract", "installed_cache_identity", "marketplace_entry",
    }
    fixed_keys = {"surface_id", "kind", "intent", "legacy", "target"}
    covered_names: set[str] = set()
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        surface_id = str(row["surface_id"])
        by_id[surface_id] = row
        if set(row) != fixed_keys | REQUIRED_BEHAVIORS:
            raise TopologyError(f"{surface_id} compatibility fields differ")
        if row.get("kind") not in allowed_kinds or not str(row.get("intent") or ""):
            raise TopologyError(f"{surface_id} kind or intent is invalid")
        for side in ("legacy", "target"):
            names = row.get(side)
            if not isinstance(names, list) or not all(isinstance(item, str) for item in names):
                raise TopologyError(f"{surface_id} {side} surface list is invalid")
            covered_names.update(names)
        for behavior in ("read", "write"):
            value = row.get(behavior)
            if not isinstance(value, dict) or set(value) != set(STATES):
                raise TopologyError(f"{surface_id} {behavior} behavior must cover all states")
            if not all(isinstance(text, str) and text.strip() for text in value.values()):
                raise TopologyError(f"{surface_id} {behavior} state values must be text")
        _default_families(row.get("default"), surface_id=surface_id)
        actual_defaults = (
            tuple(row["default"]["current"]["legacy_current"]),
            tuple(row["default"]["migration"]["legacy_rollback"]),
            tuple(row["default"]["migration"]["target_candidate"]),
            tuple(row["default"]["target"]["target_only"]),
        )
        if actual_defaults != SURFACE_DEFAULT_BINDINGS[surface_id]:
            raise TopologyError(f"{surface_id} default owner binding differs")
        if (
            not isinstance(row.get("fallback"), dict)
            or set(row["fallback"]) != {"allowed", "mode", "fail_closed_when"}
            or not isinstance(row["fallback"]["allowed"], bool)
            or not isinstance(row["fallback"]["mode"], str)
            or not row["fallback"]["mode"].strip()
            or not isinstance(row["fallback"]["fail_closed_when"], list)
            or not all(
                isinstance(item, str) and item.strip()
                for item in row["fallback"]["fail_closed_when"]
            )
            or len(row["fallback"]["fail_closed_when"])
            != len(set(row["fallback"]["fail_closed_when"]))
            or (
                row["fallback"]["allowed"] is True
                and not row["fallback"]["fail_closed_when"]
            )
        ):
            raise TopologyError(f"{surface_id} fallback fields differ")
        if (
            not isinstance(row.get("activation"), dict)
            or set(row["activation"]) != {"phase", "gates", "ordered_actions", "forbidden_coinstall"}
            or not isinstance(row["activation"]["phase"], str)
            or not row["activation"]["phase"].strip()
            or any(not isinstance(row["activation"][field], list) for field in ("gates", "ordered_actions", "forbidden_coinstall"))
        ):
            raise TopologyError(f"{surface_id} activation fields differ")
        for field in ("gates", "ordered_actions", "forbidden_coinstall"):
            values = row["activation"][field]
            if (
                len(values) != len(set(values))
                or not all(isinstance(item, str) and item.strip() for item in values)
            ):
                raise TopologyError(f"{surface_id} activation {field} values differ")
        if not set(row["activation"]["forbidden_coinstall"]).issubset(
            ALLOWED_COINSTALL_REFERENCES
        ):
            raise TopologyError(f"{surface_id} coinstall reference is unknown")
        if tuple(row["activation"]["forbidden_coinstall"]) != SURFACE_COINSTALL_BINDINGS[surface_id]:
            raise TopologyError(f"{surface_id} coinstall binding differs")
        if (
            not isinstance(row.get("deprecation"), dict)
            or set(row["deprecation"]) != {"starts", "behavior", "notice_required"}
            or not isinstance(row["deprecation"]["notice_required"], bool)
            or not all(
                isinstance(row["deprecation"][field], str)
                and row["deprecation"][field].strip()
                for field in ("starts", "behavior")
            )
        ):
            raise TopologyError(f"{surface_id} deprecation fields differ")
        if (
            not isinstance(row.get("removal"), dict)
            or set(row["removal"]) != {"gates", "legacy_reader_retention", "history_rewrite"}
            or not isinstance(row["removal"]["gates"], list)
            or not isinstance(row["removal"]["history_rewrite"], bool)
            or not isinstance(row["removal"]["legacy_reader_retention"], str)
            or not row["removal"]["legacy_reader_retention"].strip()
            or not row["removal"]["gates"]
            or len(row["removal"]["gates"]) != len(set(row["removal"]["gates"]))
            or not all(
                isinstance(item, str) and item.strip()
                for item in row["removal"]["gates"]
            )
        ):
            raise TopologyError(f"{surface_id} removal fields differ")
        if tuple(row["removal"]["gates"]) != SURFACE_REMOVAL_BINDINGS[surface_id]:
            raise TopologyError(f"{surface_id} removal binding differs")
        tests = row.get("test")
        if not isinstance(tests, dict) or set(tests) != {"required_ids", "negative_ids"} or not tests["required_ids"] or not tests["negative_ids"]:
            raise TopologyError(f"{surface_id} test contract is incomplete")
        for field in ("required_ids", "negative_ids"):
            if (
                len(tests[field]) != len(set(tests[field]))
                or not all(isinstance(item, str) and item.strip() for item in tests[field])
            ):
                raise TopologyError(f"{surface_id} test IDs differ")
        if (
            row["kind"] in {"skill_id", "cli_entrypoint_family"}
            and len(set(row["legacy"] + row["target"])) > 1
            and not any(gate.startswith("per_") for gate in row["removal"]["gates"])
        ):
            raise TopologyError(f"{surface_id} lacks individual removal resolution")
    target_skills = {skill for skills in TARGET_PLUGINS.values() for skill in skills}
    if not target_skills.issubset(covered_names):
        raise TopologyError("target Skill IDs are not covered by compatibility rows")
    if not CHANGED_LEGACY_SKILLS.issubset(covered_names):
        raise TopologyError("changed legacy Skill IDs are not covered by compatibility rows")
    source_access = by_id["skill.android-source-access"]
    if set(source_access["activation"]["forbidden_coinstall"]) != {
        "android-framework-ops", "android-wsl-ops", "android-mac-ops",
    }:
        raise TopologyError("source-access mixed install is not fail-closed")
    legacy_v1 = by_id["package.framework-change-v1"]
    if legacy_v1["removal"]["legacy_reader_retention"] != "permanent" or legacy_v1["removal"]["history_rewrite"] is not False:
        raise TopologyError("Framework v1 permanent-read contract differs")
    android_v2 = by_id["package.android-change-v2"]
    if android_v2["write"] != {
        "current": "disabled",
        "migration": "feature flag default off",
        "target": "capability and per-layer pilot gated",
    }:
        raise TopologyError("Android change v2 writer is not default-off")
    if not {
        "client_output_hash_binding",
        "complete_server_adapter_input_contracts",
        "server_adapter_recalculation",
    }.issubset(android_v2["activation"]["gates"]):
        raise TopologyError("Android change v2 qualification activation gates differ")
    if not {
        "client-output-cross-package-replay",
        "client-output-source-hash-mismatch",
        "server-recalculation-mismatch",
    }.issubset(android_v2["test"]["negative_ids"]):
        raise TopologyError("Android change v2 qualification negative tests differ")


def validate_materialized_plugin_ids(
    source_plugins: set[str], marketplace_plugins: set[str], topology: dict[str, Any],
) -> None:
    current = _state_map(topology)["current"]
    if source_plugins != set(current["source_plugins"]):
        raise TopologyError("undeclared mixed plugin topology: source plugin IDs differ")
    if marketplace_plugins != set(current["marketplace_plugins"]):
        raise TopologyError("undeclared mixed plugin topology: marketplace IDs differ")


def _property_names(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict):
            names.update(properties)
        for child in value.values():
            names.update(_property_names(child))
    elif isinstance(value, list):
        for child in value:
            names.update(_property_names(child))
    return names


def _all_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(map(str, value))
        for child in value.values():
            keys.update(_all_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_all_keys(child))
    return keys


def _json_integer(value: Any, *, minimum: int | None = None) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return minimum is None or value >= minimum
    if isinstance(value, float):
        return (
            math.isfinite(value)
            and value.is_integer()
            and (minimum is None or value >= minimum)
        )
    return False


def validate_provider_execution_decision(
    provider: dict[str, Any],
    provider_manifest_sha256: str,
    decision: dict[str, Any],
    *,
    rollout_effect_ceiling: str,
) -> None:
    authority = provider.get("authority") or {}
    forbidden_authority = {
        "can_spawn", "can_write_source", "can_acquire_lock",
        "can_execute_side_effects", "can_upload", "can_accept_gate",
        "can_final_accept",
    }
    if (
        provider.get("schema") != "android-practices-provider-v1"
        or not isinstance(authority, dict)
        or set(authority) != {"decision_only"} | forbidden_authority
        or authority.get("decision_only") is not True
        or any(authority.get(field) is not False for field in forbidden_authority)
    ):
        raise TopologyError("selected provider manifest is invalid or over-authorized")
    execution = (provider.get("capabilities") or {}).get("execution")
    if not isinstance(execution, dict):
        raise TopologyError("selected provider does not declare execution capability")
    binding = decision.get("provider") or {}
    if (
        decision.get("schema") != "execution-policy-decision-v1"
        or binding.get("provider_id") != provider.get("provider_id")
        or binding.get("provider_version") != provider.get("provider_version")
        or binding.get("provider_manifest_sha256") != provider_manifest_sha256
        or binding.get("skill_id") != execution.get("skill_id")
        or binding.get("skill_version") != execution.get("skill_version")
    ):
        raise TopologyError("execution decision provider binding differs")
    forbidden = {
        "model", "model_id", "spawn", "assignment", "workspace_path", "lock", "lease",
        "raw_command", "upload", "write_authorized", "gate_acceptance", "final_acceptance",
    }
    if _all_keys(decision) & forbidden:
        raise TopologyError("execution decision contains controller authority fields")
    outcome = decision.get("outcome") or {}
    if outcome.get("type") != "delegate":
        if outcome.get("type") not in {"core_direct", "blocked"}:
            raise TopologyError("execution decision outcome is invalid")
        return
    profiles = execution.get("worker_profiles") or {}
    profile = profiles.get(outcome.get("worker_profile_id"))
    if not isinstance(profile, dict):
        raise TopologyError("execution decision references an unknown worker profile")
    if outcome.get("task_class") not in set(profile.get("task_classes") or ()):
        raise TopologyError("execution decision task class exceeds the worker profile")
    effects = {"read_only": 0, "workspace_mutation": 1, "controlled_operation": 2}
    requested = outcome.get("requested_effect")
    if requested not in effects or effects[requested] > effects.get(profile.get("effect_ceiling"), -1):
        raise TopologyError("execution decision effect exceeds the worker profile")
    if effects[requested] > effects.get(rollout_effect_ceiling, -1):
        raise TopologyError("execution decision effect exceeds the rollout ceiling")
    escalation = outcome.get("escalation_request")
    if escalation and escalation.get("worker_profile_id") not in profiles:
        raise TopologyError("execution decision escalation profile is unknown")


def validate_assignment_semantics(assignment: dict[str, Any]) -> None:
    if assignment.get("schema") != "worker-assignment-v1":
        raise TopologyError("worker assignment schema is invalid")
    if not _json_integer(assignment.get("attempt"), minimum=1):
        raise TopologyError("worker assignment attempt is invalid")
    permissions = assignment.get("permissions") or {}
    permission_fields = {
        "may_acquire_authority", "may_expand_scope", "may_upload",
        "may_accept_gate", "may_final_accept",
    }
    if (
        not isinstance(permissions, dict)
        or set(permissions) != permission_fields
        or any(permissions.get(field) is not False for field in permission_fields)
    ):
        raise TopologyError("worker assignment permissions exceed worker authority")
    constraints = assignment.get("constraints") or {}
    escalations = constraints.get("max_automatic_escalations")
    if (
        not _json_integer(escalations, minimum=1)
        or escalations != 1
        or constraints.get("environment_failure_escalates_model") is not False
    ):
        raise TopologyError("worker assignment escalation contract differs")
    scope = assignment.get("scope") or {}
    repositories = scope.get("repositories") or []
    paths = scope.get("paths") or []
    if not repositories or not paths:
        raise TopologyError("worker assignment scope must be non-empty")
    if {item.get("repository_id") for item in paths} != set(repositories):
        raise TopologyError("worker assignment path repositories differ from scope")
    effect = assignment.get("effect")
    if effect == "read_only":
        if any(key in constraints for key in ("authority_ref", "workspace_bindings", "controlled_operation")):
            raise TopologyError("read-only assignment contains mutation authority")
    elif effect == "workspace_mutation":
        bindings = constraints.get("workspace_bindings") or []
        if not constraints.get("authority_ref") or not bindings:
            raise TopologyError("mutation assignment lacks authority or workspace bindings")
        binding_repositories = [item.get("repository_id") for item in bindings]
        if (
            len(binding_repositories) != len(set(binding_repositories))
            or set(binding_repositories) != set(repositories)
        ):
            raise TopologyError("mutation workspace repositories differ from assignment scope")
        scope_by_repository = {
            repository: {
                (item.get("kind"), item.get("path"))
                for item in paths if item.get("repository_id") == repository
            }
            for repository in repositories
        }
        for binding in bindings:
            repository = binding.get("repository_id")
            binding_paths = set()
            for item in binding.get("paths") or []:
                if item.get("repository_id") != repository:
                    raise TopologyError("mutation workspace path belongs to another repository")
                binding_paths.add((item.get("kind"), item.get("path")))
            if (
                binding.get("authority_ref") != constraints.get("authority_ref")
                or binding_paths != scope_by_repository.get(repository)
            ):
                raise TopologyError("mutation workspace authority or path scope differs")
    elif effect == "controlled_operation":
        if not constraints.get("authority_ref") or not constraints.get("controlled_operation"):
            raise TopologyError("controlled operation lacks frozen authority bindings")
    else:
        raise TopologyError("worker assignment effect is invalid")


def validate_stage_snapshot_semantics(snapshot: dict[str, Any]) -> None:
    if snapshot.get("schema") != "stage-snapshot-v1":
        raise TopologyError("stage snapshot schema is invalid")
    sequence = snapshot.get("sequence")
    previous = snapshot.get("previous_snapshot_sha256")
    if sequence == 1 and previous is not None:
        raise TopologyError("first stage snapshot cannot have a previous hash")
    if (
        not _json_integer(sequence, minimum=1)
        or sequence < 1
        or (sequence > 1 and not previous)
    ):
        raise TopologyError("stage snapshot hash chain is incomplete")
    reason = snapshot.get("snapshot_reason")
    event = snapshot.get("event") or {}
    if reason == "delegating_worker" and (
        event.get("type") != "assignment_planned" or not event.get("planned_assignment_id")
    ):
        raise TopologyError("delegating snapshot lacks its planned assignment ID")
    if reason == "gate_transition" and event.get("type") != "gate_changed":
        raise TopologyError("gate-transition snapshot event differs")
    if snapshot.get("requirement_disposition") is not None and reason != "gate_transition":
        raise TopologyError("requirement disposition belongs only to a gate transition")
    disposition = snapshot.get("requirement_disposition")
    stage_state = (snapshot.get("stage") or {}).get("state")
    if (
        disposition in {"accepted", "rejected"} and stage_state != "completed"
    ) or (disposition == "blocked" and stage_state != "blocked"):
        raise TopologyError("requirement disposition and stage state differ")
    if reason == "entering_high_risk_mutation" and (
        (snapshot.get("stage") or {}).get("risk_level") != "high"
        or not snapshot.get("workspace_bindings")
        or event.get("type") != "mutation_authority_bound"
    ):
        raise TopologyError("high-risk mutation snapshot lacks authority bindings")
    if reason == "cross_session_handoff" and event.get("type") != "handoff":
        raise TopologyError("cross-session handoff snapshot event differs")
    if reason == "pause_resume":
        state = (snapshot.get("stage") or {}).get("state")
        if (event.get("type"), state) not in {("paused", "paused"), ("resumed", "active")}:
            raise TopologyError("pause/resume snapshot state differs")
    resolution = snapshot.get("provider_resolution") or {}
    mode = resolution.get("selection_mode")
    for capability in ("coding", "execution"):
        value = resolution.get(capability) or {}
        source = value.get("source")
        reason_value = value.get("reason")
        if source == "provider" and reason_value != "provider_capability":
            raise TopologyError("provider capability resolution reason differs")
        if source == "core" and reason_value not in {
            "mode_none", "capability_absent", "applicability_miss",
        }:
            raise TopologyError("core capability resolution reason differs")
    provider_fields = (
        resolution.get("provider_id"), resolution.get("provider_version"),
        resolution.get("provider_manifest_sha256"),
    )
    if mode == "none":
        if any(provider_fields) or any(
            resolution.get(item) != {"source": "core", "reason": "mode_none"}
            for item in ("coding", "execution")
        ):
            raise TopologyError("mode none cannot resolve a provider")
    elif mode in {"jinny", "custom"}:
        if not all(provider_fields):
            raise TopologyError("selected provider identity is incomplete")
        if mode == "jinny" and resolution.get("provider_id") != "jinny-android-practices":
            raise TopologyError("jinny mode must bind the Jinny provider")
        if mode == "custom" and resolution.get("provider_id") == "jinny-android-practices":
            raise TopologyError("custom mode cannot impersonate the Jinny provider")
    else:
        raise TopologyError("provider selection mode is invalid")


def validate_worker_result_semantics(
    result: dict[str, Any], assignment: dict[str, Any], *, assignment_sha256: str,
) -> None:
    result_attempt = result.get("attempt")
    assignment_attempt = assignment.get("attempt")
    if (
        result.get("schema") != "worker-result-v1"
        or result.get("assignment_id") != assignment.get("assignment_id")
        or result.get("assignment_sha256") != assignment_sha256
        or result.get("run_id") != assignment.get("run_id")
        or not _json_integer(result_attempt, minimum=1)
        or not _json_integer(assignment_attempt, minimum=1)
        or result_attempt != assignment_attempt
        or (result.get("worker_binding") or {}).get("worker_profile_id")
        != (assignment.get("assignee") or {}).get("worker_profile_id")
    ):
        raise TopologyError("worker result does not bind the exact assignment")
    if result.get("reported_scope_deviations"):
        raise TopologyError("worker result reports a scope deviation")
    required_evidence = set(assignment.get("required_evidence") or [])
    reported_evidence = {
        item.get("kind") for item in result.get("evidence") or []
    }
    if not required_evidence.issubset(reported_evidence):
        raise TopologyError("worker result lacks assignment-required evidence")
    if result.get("outcome") == "completed" and (
        not result.get("checks") or not result.get("evidence")
    ):
        raise TopologyError("completed worker result lacks checks or evidence")
    if assignment.get("effect") == "workspace_mutation" and (
        not result.get("observed_workspaces") or not result.get("reported_changes")
    ):
        raise TopologyError("mutation result lacks workspace or change facts")
    if assignment.get("effect") == "read_only":
        if result.get("reported_changes") or any(
            item.get("start_head") != item.get("end_head")
            for item in result.get("observed_workspaces") or []
        ):
            raise TopologyError("read-only worker result reports repository mutation")
    if assignment.get("effect") == "workspace_mutation":
        constraints = assignment.get("constraints") or {}
        bindings = {
            item["repository_id"]: item
            for item in constraints.get("workspace_bindings") or []
        }
        observed_rows = result.get("observed_workspaces") or []
        observed = {item.get("repository_id"): item for item in observed_rows}
        if len(observed) != len(observed_rows) or set(observed) != set(bindings):
            raise TopologyError("worker result workspace repositories differ")
        for repository, binding in bindings.items():
            actual = observed[repository]
            if (
                actual.get("workspace_id") != binding.get("workspace_id")
                or actual.get("base_revision") != binding.get("base_revision")
                or actual.get("start_head") != binding.get("base_revision")
            ):
                raise TopologyError("worker result workspace/base binding differs")
        scopes = assignment.get("scope", {}).get("paths") or []

        def allowed(repository: str, path: str) -> bool:
            for scope in scopes:
                if scope.get("repository_id") != repository:
                    continue
                selected = str(scope.get("path") or "")
                if scope.get("kind") == "file" and path == selected:
                    return True
                if scope.get("kind") == "tree" and (path == selected or path.startswith(selected + "/")):
                    return True
            return False

        for change in result.get("reported_changes") or []:
            repository = change.get("repository_id")
            if not allowed(repository, str(change.get("path") or "")):
                raise TopologyError("worker result change escapes assignment scope")
            if change.get("rename_from") and not allowed(repository, change["rename_from"]):
                raise TopologyError("worker result rename source escapes assignment scope")
    if assignment.get("effect") == "controlled_operation":
        expected_command = (
            assignment.get("constraints", {}).get("controlled_operation") or {}
        ).get("command_id")
        command_ids = [item.get("command_id") for item in result.get("commands") or []]
        if command_ids != [expected_command]:
            raise TopologyError("controlled operation result command receipt differs")
    for change in result.get("reported_changes") or []:
        operation = change.get("operation")
        before, after = change.get("before_sha256"), change.get("after_sha256")
        if (
            (operation == "add" and (before is not None or after is None))
            or (operation == "delete" and (before is None or after is not None))
            or (operation in {"modify", "rename"} and (before is None or after is None))
            or (operation == "rename" and not change.get("rename_from"))
        ):
            raise TopologyError("worker result change hash semantics differ")
    for check in result.get("checks") or []:
        receipt = check.get("receipt_sha256")
        if (check.get("status") == "not_run") != (receipt is None):
            raise TopologyError("worker result check receipt semantics differ")


def validate_evidence_profile_registry(profiles: dict[str, Any]) -> None:
    registry = profiles.get("evidence_group_registry") or {}
    groups = registry.get("groups") or {}
    referenced = set(profiles.get("common_required_groups") or [])
    for values in (profiles.get("workflow_requirements") or {}).values():
        referenced.update(values)
    for layer in (profiles.get("layers") or {}).values():
        referenced.update(layer.get("required_groups") or [])
        for values in (layer.get("conditional_groups") or {}).values():
            referenced.update(values)
    if set(groups) != referenced:
        raise TopologyError("evidence group registry does not exactly cover profile groups")
    claims: set[str] = set()
    for group_id, group in groups.items():
        expected = {
            "adapter_contract", "adapter_version", "claim",
            "allowed_adapter_results", "not_applicable",
        }
        if set(group) != expected or not group["allowed_adapter_results"]:
            raise TopologyError(f"evidence group adapter contract differs: {group_id}")
        if (
            not all(
                isinstance(group[field], str) and group[field].strip()
                for field in ("adapter_contract", "adapter_version", "claim")
            )
            or len(group["allowed_adapter_results"]) != len(set(group["allowed_adapter_results"]))
            or not set(group["allowed_adapter_results"]).issubset({"PASS", "INFO", "NOT_APPLICABLE"})
            or not set(group["allowed_adapter_results"]) & {"PASS", "INFO"}
        ):
            raise TopologyError(f"evidence group adapter result contract differs: {group_id}")
        if group["claim"] in claims:
            raise TopologyError("evidence group client claims must be unique")
        claims.add(group["claim"])
        has_na = "NOT_APPLICABLE" in group["allowed_adapter_results"]
        if has_na != (group["not_applicable"] is True):
            raise TopologyError(f"evidence group N/A contract differs: {group_id}")
        if group_id in {"change_diff_facts", "risk_surface", "pre_change_search"}:
            expected_results = ["PASS", "INFO"]
        elif group["not_applicable"] is True:
            expected_results = ["PASS", "NOT_APPLICABLE"]
        else:
            expected_results = ["PASS"]
        if group["allowed_adapter_results"] != expected_results:
            raise TopologyError(f"evidence group result binding differs: {group_id}")

    predicate_ids = {
        f"{layer_id}.{predicate_id}"
        for layer_id, layer in (profiles.get("layers") or {}).items()
        for predicate_id in (layer.get("conditional_groups") or {})
    }
    if set(profiles.get("conditional_predicates") or {}) != predicate_ids:
        raise TopologyError("evidence conditional predicates do not exactly cover profile conditions")
    output_contract = profiles.get("client_adapter_output_contract") or {}
    document_contract = profiles.get("client_adapter_outputs_document_contract") or {}
    server_boundary = profiles.get("server_qualification_boundary") or {}
    archive_integrity = profiles.get("archive_integrity") or {}
    writer_activation = profiles.get("writer_activation") or {}
    qualification_hash = document_contract.get("qualification_input_hash") or {}
    server_decision = server_boundary.get("server_decision_contract") or {}
    expected_server_bindings = [
        "source_package_key", "authenticated_actor", "manifest_sha256",
        "directory_payload_sha256", "qualification_input_sha256",
        "client_adapter_outputs_file_sha256", "profile_id",
        "profile_artifact_sha256", "adapter_registry_sha256",
        "component_group_results", "reason_codes", "validator_version",
    ]
    expected_writer_group_fields = [
        "versioned input schema", "evidence authority and source",
        "deterministic derivation", "allowed result and not-applicable rules",
        "adapter contract artifact SHA", "server implementation",
    ]
    if (
        registry.get("adapter_output_schema") != "akbs-client-adapter-output-v1"
        or set(registry.get("required_adapter_binding_fields") or ())
        != {"adapter_contract", "adapter_version", "source_evidence_sha256", "claim", "adapter_result"}
        or set(output_contract)
        != {
            "schema", "required_fields", "additional_fields",
            "additional_properties", "hash_binding",
        }
        or output_contract.get("schema") != "akbs-client-adapter-output-v1"
        or output_contract.get("additional_properties") is not False
        or output_contract.get("hash_binding") != "manifest_declared_metadata_file_sha256"
        or output_contract.get("required_fields")
        != [
            "schema", "component_id", "group_id", "source_evidence_id",
            "source_evidence_sha256", "adapter_contract", "adapter_version",
            "claim", "adapter_result",
        ]
        or output_contract.get("additional_fields") != ["not_applicable_basis"]
        or set(document_contract)
        != {
            "schema", "authority", "manifest_binding", "file_role", "media_type",
            "profile_id_binding", "profile_artifact_hash_binding",
            "declared_status_binding", "source_package_key_binding",
            "qualification_input_hash",
        }
        or document_contract.get("schema") != "akbs-client-adapter-outputs-v1"
        or document_contract.get("authority") != "untrusted_client_input"
        or document_contract.get("manifest_binding")
        != "qualification.client_adapter_outputs_file_id"
        or document_contract.get("profile_artifact_hash_binding")
        != "qualification.profile_artifact_sha256"
        or document_contract.get("source_package_key_binding")
        != "manifest_identity_member_alias_and_run_id"
        or document_contract.get("file_role") != "metadata"
        or document_contract.get("media_type") != "application/json"
        or document_contract.get("declared_status_binding") != "manifest.package_status"
        or set(qualification_hash)
        != {
            "field", "algorithm_id", "algorithm", "encoding", "ensure_ascii",
            "object_key_order", "separators", "trailing_newline",
            "unicode_normalization", "numeric_domain", "non_finite_numbers",
            "input", "exclude",
        }
        or qualification_hash.get("field") != "qualification_input_sha256"
        or qualification_hash.get("algorithm_id") != "akbs-canonical-json-sha256-v1"
        or qualification_hash.get("algorithm") != "sha256"
        or qualification_hash.get("encoding") != "UTF-8"
        or qualification_hash.get("ensure_ascii") is not False
        or qualification_hash.get("object_key_order") != "unicode_code_point_ascending"
        or qualification_hash.get("separators") != [",", ":"]
        or qualification_hash.get("trailing_newline") is not False
        or qualification_hash.get("unicode_normalization") != "none_exact_code_points"
        or qualification_hash.get("numeric_domain")
        != "JSON integers only; floating-point values are forbidden"
        or qualification_hash.get("non_finite_numbers") != "forbidden"
        or qualification_hash.get("input") != "complete_manifest_semantics"
        or qualification_hash.get("exclude")
        != [
            "the files row named by qualification.client_adapter_outputs_file_id",
            "server-owned submit envelope and receipt fields",
        ]
        or set(server_boundary)
        != {
            "client_outputs_trust", "server_must_recalculate",
            "server_decision_contract", "member_archive_rewrite",
            "curation_consumes", "server_must_not_upgrade_declared_package_status",
            "writer_activation_requires_complete_adapter_input_contracts",
            "deterministic_recalculation_scope",
        }
        or server_boundary.get("client_outputs_trust") != "untrusted_input"
        or server_boundary.get("server_must_recalculate") is not True
        or server_boundary.get("member_archive_rewrite") is not False
        or server_boundary.get("curation_consumes") != "server_decision_only"
        or server_boundary.get("server_must_not_upgrade_declared_package_status") is not True
        or server_boundary.get("writer_activation_requires_complete_adapter_input_contracts")
        is not True
        or server_boundary.get("deterministic_recalculation_scope")
        != "evidence_acceptance_contracts_only_not_build_device_or_ai_reexecution"
        or set(server_decision)
        != {"schema", "authority", "authority_scope", "decision", "required_bindings"}
        or server_decision.get("schema") != "akbs-server-qualification-decision-v1"
        or server_decision.get("authority") != "server_authoritative"
        or server_decision.get("authority_scope") != "incoming_contract_qualification"
        or server_decision.get("decision") != ["accept", "reject"]
        or server_decision.get("required_bindings") != expected_server_bindings
        or set(archive_integrity)
        != {
            "actual_paths_equal", "manifest_in_files",
            "file_id_and_normalized_path_unique", "declared_sha256_and_size_match_bytes",
            "directory_payload_hash", "strict_json_for", "strict_json_rejects",
        }
        or archive_integrity.get("actual_paths_equal")
        != "manifest.json plus every manifest.files path exactly once"
        or archive_integrity.get("manifest_in_files") is not False
        or archive_integrity.get("file_id_and_normalized_path_unique") is not True
        or archive_integrity.get("declared_sha256_and_size_match_bytes") is not True
        or archive_integrity.get("directory_payload_hash")
        != "sha256_of_sorted_normalized_path_sha256_size_tuples"
        or set(archive_integrity.get("strict_json_for") or ())
        != {"manifest", "client adapter outputs", "declared JSON evidence"}
        or set(archive_integrity.get("strict_json_rejects") or ())
        != {"duplicate keys", "NaN", "Infinity"}
        or writer_activation.get("phase1_state") != "blocked"
        or set(writer_activation) != {"phase1_state", "block_reason", "required_per_group"}
        or writer_activation.get("block_reason")
        != "versioned adapter input contracts and complete server implementations are not yet frozen"
        or writer_activation.get("required_per_group") != expected_writer_group_fields
    ):
        raise TopologyError("client/server evidence qualification boundary differs")


def _predicate_matches(
    predicate: dict[str, Any], component: dict[str, Any],
) -> bool:
    if predicate.get("always") is True:
        return True
    if "type_in" in predicate:
        return component.get("type") in set(predicate["type_in"])
    if "qualifier_contains" in predicate:
        return predicate["qualifier_contains"] in set(component.get("qualifiers") or [])
    raise TopologyError("unknown evidence conditional predicate")


def required_evidence_groups(
    component: dict[str, Any], workflow_contract: str, profiles: dict[str, Any],
) -> set[str]:
    layer_id = component.get("layer")
    layer = (profiles.get("layers") or {}).get(layer_id)
    if not isinstance(layer, dict):
        raise TopologyError("component layer has no evidence profile")
    groups = set(profiles.get("common_required_groups") or [])
    groups.update((profiles.get("workflow_requirements") or {}).get(workflow_contract) or [])
    groups.update(layer.get("required_groups") or [])
    predicates = profiles.get("conditional_predicates") or {}
    for predicate_id, conditional_groups in (layer.get("conditional_groups") or {}).items():
        predicate = predicates.get(f"{layer_id}.{predicate_id}")
        if not isinstance(predicate, dict):
            raise TopologyError("component evidence predicate is missing")
        if _predicate_matches(predicate, component):
            groups.update(conditional_groups)
    return groups


def _require_canonical_json_v1_domain(value: Any, *, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        raise TopologyError(f"AKBS canonical JSON v1 forbids floating-point numbers: {path}")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _require_canonical_json_v1_domain(item, path=f"{path}/{index}")
        return
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TopologyError(f"AKBS canonical JSON v1 requires text object keys: {path}")
        for key, item in value.items():
            _require_canonical_json_v1_domain(item, path=f"{path}/{key}")
        return
    raise TopologyError(f"AKBS canonical JSON v1 unsupported value: {path}")


def canonical_json_sha256_v1(value: Any) -> str:
    _require_canonical_json_v1_domain(value)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def qualification_input_sha256(package: dict[str, Any]) -> str:
    candidate = copy.deepcopy(package)
    qualification = candidate.get("qualification") or {}
    output_file_id = qualification.get("client_adapter_outputs_file_id")
    files = candidate.get("files")
    if not isinstance(output_file_id, str) or not isinstance(files, list):
        raise TopologyError("Android change v2 client output binding is missing")
    retained = [row for row in files if row.get("id") != output_file_id]
    if len(retained) != len(files) - 1:
        raise TopologyError("Android change v2 client output file must resolve exactly once")
    candidate["files"] = retained
    return canonical_json_sha256_v1(candidate)


def normalized_archive_path(value: object) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise TopologyError("Android change v2 archive path is unsafe")
    path = PurePosixPath(value)
    normalized = path.as_posix()
    if (
        value != normalized
        or value in {".", ".."}
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise TopologyError("Android change v2 archive path is not canonical")
    return normalized


def archive_inventory(
    entries: list[tuple[str, str, int]],
) -> dict[str, tuple[str, int]]:
    if not isinstance(entries, list) or not entries:
        raise TopologyError("Android change v2 archive inventory is missing")
    result: dict[str, tuple[str, int]] = {}
    for entry in entries:
        if not isinstance(entry, tuple) or len(entry) != 3:
            raise TopologyError("Android change v2 archive inventory entry differs")
        path = normalized_archive_path(entry[0])
        sha256 = entry[1]
        size_bytes = entry[2]
        if (
            path in result
            or not isinstance(sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", sha256)
            or not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes < 0
        ):
            raise TopologyError("Android change v2 archive inventory entry differs")
        result[path] = (sha256, size_bytes)
    return result


def source_package_key(package: dict[str, Any]) -> str:
    identity = package.get("identity") or {}
    member_alias = identity.get("member_alias")
    run_id = identity.get("run_id")
    if (
        not isinstance(member_alias, str)
        or not isinstance(run_id, str)
        or not re.fullmatch(r"[0-9]{8}-[0-9]{6}(?:-[A-Za-z0-9_.-]+)?", run_id)
    ):
        raise TopologyError("Android change v2 source package identity differs")
    return f"{run_id[:8]}/{member_alias}/{run_id}"


def validate_client_patch_package_semantics(
    manifest_bytes: bytes,
    profile_artifact_bytes: bytes,
    client_adapter_outputs_bytes: bytes,
    *,
    archive_entries: list[tuple[str, str, int]],
) -> dict[str, Any]:
    """Validate untrusted client package coherence, never server qualification."""

    if not all(
        isinstance(value, bytes)
        for value in (manifest_bytes, profile_artifact_bytes, client_adapter_outputs_bytes)
    ):
        raise TopologyError("Android change v2 client validator requires exact artifact bytes")
    package = load_json_bytes(manifest_bytes, label="manifest.json")
    profiles = load_json_bytes(
        profile_artifact_bytes, label="component-evidence-profiles.json"
    )
    client_adapter_outputs = load_json_bytes(
        client_adapter_outputs_bytes, label="client-adapter-outputs.json"
    )
    profile_artifact_sha256 = hashlib.sha256(profile_artifact_bytes).hexdigest()
    client_adapter_outputs_file_sha256 = hashlib.sha256(
        client_adapter_outputs_bytes
    ).hexdigest()
    client_adapter_outputs_size_bytes = len(client_adapter_outputs_bytes)
    if (
        package.get("schema") != "akbs-android-change-package-v2"
        or package.get("schema_version") != "2"
        or package.get("package_kind") != "android_change"
        or package.get("package_status") != "validated"
    ):
        raise TopologyError("Android change v2 package identity differs")
    if profiles.get("schema") != "akbs-component-evidence-profiles-v1":
        raise TopologyError("Android change v2 evidence profile identity differs")
    validate_evidence_profile_registry(profiles)
    collections: dict[str, list[dict[str, Any]]] = {}
    for name in ("components", "sources", "files", "changes", "evidence"):
        rows = package.get(name)
        if not isinstance(rows, list) or not rows:
            raise TopologyError(f"Android change v2 {name} must be non-empty")
        identifiers = [row.get("id") for row in rows if isinstance(row, dict)]
        if len(identifiers) != len(rows) or len(identifiers) != len(set(identifiers)):
            raise TopologyError(f"Android change v2 {name} IDs must be unique")
        collections[name] = rows
    components = {row["id"]: row for row in collections["components"]}
    sources = {row["id"]: row for row in collections["sources"]}
    files = {row["id"]: row for row in collections["files"]}
    evidence = {row["id"]: row for row in collections["evidence"]}
    if (package.get("subject") or {}).get("primary_component_id") not in components:
        raise TopologyError("Android change v2 primary component is unresolved")
    for source in sources.values():
        path = source.get("repo_path")
        if path != "." and (
            not isinstance(path, str) or path.startswith("/") or "\\" in path
            or ".." in Path(path).parts
        ):
            raise TopologyError("Android change v2 source path is unsafe")
    declared_paths: set[str] = set()
    for file_row in files.values():
        path = normalized_archive_path(file_row.get("path"))
        if path == "manifest.json" or path in declared_paths:
            raise TopologyError("Android change v2 file path is unsafe or duplicated")
        declared_paths.add(path)
    changed_components: set[str] = set()
    for change in collections["changes"]:
        component_ids = set(change.get("component_ids") or [])
        if (
            not component_ids
            or not component_ids.issubset(components)
            or change.get("source_id") not in sources
            or change.get("file_id") not in files
            or files[change["file_id"]].get("role") != "patch"
        ):
            raise TopologyError("Android change v2 change references differ")
        changed_components.update(component_ids)
    for item in evidence.values():
        component_ids = set(item.get("component_ids") or [])
        if (
            not component_ids
            or not component_ids.issubset(components)
            or item.get("file_id") not in files
            or files[item["file_id"]].get("role") != "evidence"
        ):
            raise TopologyError("Android change v2 evidence references differ")
        if item.get("result") == "NOT_APPLICABLE" and not item.get("not_applicable_basis"):
            raise TopologyError("Android change v2 N/A evidence lacks basis and limits")
    qualification = package.get("qualification") or {}
    if (
        qualification.get("profile_id") != profiles.get("schema")
        or qualification.get("profile_artifact_sha256") != profile_artifact_sha256
        or not re.fullmatch(r"[0-9a-f]{64}", profile_artifact_sha256)
    ):
        raise TopologyError("Android change v2 qualification profile differs")
    output_file_id = qualification.get("client_adapter_outputs_file_id")
    output_file = files.get(output_file_id)
    if (
        not isinstance(output_file, dict)
        or output_file.get("role") != "metadata"
        or output_file.get("media_type") != "application/json"
        or output_file.get("sha256") != client_adapter_outputs_file_sha256
        or output_file.get("size_bytes") != client_adapter_outputs_size_bytes
        or not re.fullmatch(r"[0-9a-f]{64}", client_adapter_outputs_file_sha256)
        or not isinstance(client_adapter_outputs_size_bytes, int)
        or isinstance(client_adapter_outputs_size_bytes, bool)
        or client_adapter_outputs_size_bytes < 1
    ):
        raise TopologyError("Android change v2 client adapter output file binding differs")
    bindings = qualification.get("component_evidence_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise TopologyError("Android change v2 qualification bindings are missing")
    bound_components: set[str] = set()
    binding_evidence: dict[str, set[str]] = {}
    for binding in bindings:
        component_id = binding.get("component_id")
        evidence_ids = set(binding.get("evidence_ids") or [])
        if (
            component_id not in components or component_id in bound_components
            or not evidence_ids or not evidence_ids.issubset(evidence)
            or any(component_id not in evidence[item]["component_ids"] for item in evidence_ids)
        ):
            raise TopologyError("Android change v2 qualification references differ")
        bound_components.add(component_id)
        binding_evidence[component_id] = evidence_ids
    if changed_components != set(components) or bound_components != set(components):
        raise TopologyError("every Android change v2 component must be changed and qualified")
    registry = profiles["evidence_group_registry"]["groups"]
    output_contract = profiles["client_adapter_output_contract"]
    required_fields = set(output_contract["required_fields"])
    allowed_fields = required_fields | set(output_contract.get("additional_fields") or [])
    workflow_contract = (package.get("workflow") or {}).get("contract")
    expected_document_fields = {
        "schema", "authority", "source_package_key", "qualification_input_sha256",
        "profile_id", "profile_artifact_sha256", "declared_package_status", "components",
    }
    if not isinstance(client_adapter_outputs, dict):
        raise TopologyError("Android change v2 client adapter output document must be an object")
    document_components = client_adapter_outputs.get("components")
    if (
        set(client_adapter_outputs) != expected_document_fields
        or client_adapter_outputs.get("schema") != "akbs-client-adapter-outputs-v1"
        or client_adapter_outputs.get("authority") != "untrusted_client_input"
        or client_adapter_outputs.get("source_package_key") != source_package_key(package)
        or client_adapter_outputs.get("qualification_input_sha256")
        != qualification_input_sha256(package)
        or client_adapter_outputs.get("profile_id") != profiles.get("schema")
        or client_adapter_outputs.get("profile_artifact_sha256") != profile_artifact_sha256
        or client_adapter_outputs.get("declared_package_status") != package.get("package_status")
        or not isinstance(document_components, list)
        or not document_components
    ):
        raise TopologyError("Android change v2 client adapter output document differs")
    client_outputs_by_component: dict[str, list[dict[str, Any]]] = {}
    for item in document_components:
        if (
            not isinstance(item, dict)
            or set(item) != {"component_id", "outputs"}
            or not isinstance(item.get("component_id"), str)
            or item.get("component_id") in client_outputs_by_component
            or not isinstance(item.get("outputs"), list)
            or not item["outputs"]
        ):
            raise TopologyError("Android change v2 client component outputs differ")
        client_outputs_by_component[item["component_id"]] = item["outputs"]
    if set(client_outputs_by_component) != set(components):
        raise TopologyError("client adapter outputs must cover every component exactly")
    for component_id, component in components.items():
        outputs = client_outputs_by_component.get(component_id)
        if not isinstance(outputs, list) or not outputs:
            raise TopologyError("client adapter outputs are missing")
        if any(not isinstance(item, dict) for item in outputs):
            raise TopologyError("client adapter output fields differ")
        groups = [item.get("group_id") for item in outputs]
        expected_groups = required_evidence_groups(component, workflow_contract, profiles)
        if len(groups) != len(set(groups)) or set(groups) != expected_groups:
            raise TopologyError("client adapter output groups do not satisfy the component profile")
        for output in outputs:
            if (
                not isinstance(output, dict)
                or set(output) - allowed_fields
                or not required_fields.issubset(output)
            ):
                raise TopologyError("client adapter output fields differ")
            if (
                output.get("schema") != output_contract["schema"]
                or output.get("component_id") != component_id
                or output.get("source_evidence_id") not in binding_evidence[component_id]
            ):
                raise TopologyError("client adapter output binding differs")
            source = evidence[output["source_evidence_id"]]
            source_file = files[source["file_id"]]
            group = registry.get(output.get("group_id"))
            if not isinstance(group, dict) or (
                output.get("source_evidence_sha256") != source_file.get("sha256")
                or output.get("claim") not in set(source.get("declared_claims") or ())
                or output.get("adapter_contract") != group["adapter_contract"]
                or output.get("adapter_version") != group["adapter_version"]
                or output.get("claim") != group["claim"]
                or output.get("adapter_result") not in group["allowed_adapter_results"]
            ):
                raise TopologyError("client evidence adapter output differs")
            is_na = output.get("adapter_result") == "NOT_APPLICABLE"
            basis = output.get("not_applicable_basis")
            valid_basis = (
                isinstance(basis, dict)
                and set(basis) == {"basis", "limits"}
                and all(isinstance(basis[key], str) and basis[key].strip() for key in basis)
            )
            if is_na != valid_basis or (is_na and not group["not_applicable"]):
                raise TopologyError("client evidence N/A output differs")
    expected = {
        "manifest.json": (hashlib.sha256(manifest_bytes).hexdigest(), len(manifest_bytes)),
        **{
            row["path"]: (row.get("sha256"), row.get("size_bytes"))
            for row in files.values()
        },
    }
    if archive_inventory(archive_entries) != expected:
        raise TopologyError("Android change v2 archive inventory or file integrity differs")
    return {
        "schema": "akbs-client-package-coherence-v1",
        "authority": "untrusted_client_input",
        "client_semantic_coherence_valid": True,
        "schema_validation_required": True,
        "archive_inventory_binding_valid": True,
        "archive_extractor_validation_required": True,
        "server_qualified": False,
        "server_decision_required": "akbs-server-qualification-decision-v1",
        "profile_artifact_sha256": profile_artifact_sha256,
        "client_adapter_outputs_file_sha256": client_adapter_outputs_file_sha256,
        "qualification_input_sha256": qualification_input_sha256(package),
    }


def validate_phase0_schema_documents(root: Path) -> None:
    expected = {
        "contracts/android-practices-provider/v1/provider.schema.json": "android-practices-provider-v1",
        "contracts/android-practices-provider/v1/coding-policy-decision.schema.json": "coding-policy-decision-v1",
        "contracts/android-practices-provider/v1/execution-policy-decision.schema.json": "execution-policy-decision-v1",
        "contracts/android-change-workflow/v1/stage-snapshot.schema.json": "stage-snapshot-v1",
        "contracts/android-change-workflow/v1/worker-assignment.schema.json": "worker-assignment-v1",
        "contracts/android-change-workflow/v1/worker-result.schema.json": "worker-result-v1",
        "contracts/incoming/v2/akbs-android-change-package.schema.json": "akbs-android-change-package-v2",
        "contracts/incoming/v2/client-adapter-outputs.schema.json": "akbs-client-adapter-outputs-v1",
    }
    documents: dict[str, dict[str, Any]] = {}
    for relative, schema_name in expected.items():
        value = load_json(root / relative)
        documents[relative] = value
        if (
            value.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
            or value.get("type") != "object"
            or value.get("additionalProperties") is not False
            or value.get("properties", {}).get("schema", {}).get("const") != schema_name
            or "schema" not in value.get("required", [])
        ):
            raise TopologyError(f"Phase 0 schema boundary differs: {relative}")
    provider = documents["contracts/android-practices-provider/v1/provider.schema.json"]
    authority = provider["properties"]["authority"]["properties"]
    if authority["decision_only"].get("const") is not True:
        raise TopologyError("provider is not decision-only")
    for field in (
        "can_spawn", "can_write_source", "can_acquire_lock", "can_execute_side_effects",
        "can_upload", "can_accept_gate", "can_final_accept",
    ):
        if authority[field].get("const") is not False:
            raise TopologyError(f"provider authority is too broad: {field}")
    forbidden = {
        "model", "model_id", "spawn", "assignment", "workspace_path", "lock", "lease",
        "raw_command", "upload", "write_authorized", "gate_acceptance", "final_acceptance",
    }
    execution = documents["contracts/android-practices-provider/v1/execution-policy-decision.schema.json"]
    if _property_names(execution) & forbidden:
        raise TopologyError("execution policy decision contains controller authority fields")
    assignment = documents["contracts/android-change-workflow/v1/worker-assignment.schema.json"]
    permissions = assignment["properties"]["permissions"]["properties"]
    if any(value.get("const") is not False for value in permissions.values()):
        raise TopologyError("worker assignment grants controller authority")
    result = documents["contracts/android-change-workflow/v1/worker-result.schema.json"]
    if set(result["properties"]["outcome"]["enum"]) != {"completed", "partial", "blocked", "failed"}:
        raise TopologyError("worker result outcome can impersonate acceptance")
    package = documents["contracts/incoming/v2/akbs-android-change-package.schema.json"]
    qualification_required = set(package["$defs"]["qualification"]["required"])
    if (
        package["properties"]["schema_version"].get("const") != "2"
        or package["properties"]["package_kind"].get("const") != "android_change"
        or package["properties"]["package_status"].get("const") != "validated"
        or set(package["$defs"]["component"]["properties"]["layer"]["enum"])
        != {"application", "platform", "native", "hal", "kernel", "device", "build"}
        or qualification_required
        != {
            "profile_id", "profile_artifact_sha256",
            "client_adapter_outputs_file_id", "component_evidence_bindings",
        }
    ):
        raise TopologyError("Android change v2 package identity or layers differ")
    client_outputs = documents["contracts/incoming/v2/client-adapter-outputs.schema.json"]
    if (
        client_outputs["properties"]["authority"].get("const") != "untrusted_client_input"
        or client_outputs["properties"]["schema"].get("const")
        != "akbs-client-adapter-outputs-v1"
        or client_outputs["$defs"]["adapterOutput"]["properties"]["schema"].get("const")
        != "akbs-client-adapter-output-v1"
    ):
        raise TopologyError("client adapter output schema authority differs")
    profiles = load_json(root / "contracts/incoming/v2/component-evidence-profiles.json")
    if (
        profiles.get("schema") != "akbs-component-evidence-profiles-v1"
        or profiles.get("client_output_source")
        != "client_contract_adapter_output_file_untrusted_until_server_recalculation"
        or set(profiles.get("layers", {}))
        != {"application", "platform", "native", "hal", "kernel", "device", "build"}
        or profiles.get("legacy_v1", {}).get("read_compatibility") != "permanent"
        or profiles.get("legacy_v1", {}).get("history_rewrite") is not False
        or profiles.get("writer_activation", {}).get("phase1_state") != "blocked"
    ):
        raise TopologyError("component evidence profile or v1 compatibility differs")
    validate_evidence_profile_registry(profiles)
    legacy_read = profiles["legacy_v1"].get("normalized_read_projection") or {}
    facets = (legacy_read.get("component_fields") or {})
    if (
        legacy_read.get("schema") != "akbs-normalized-component-read-v1"
        or facets.get("partition", {}).get("nullable") is not True
        or facets.get("ownership", {}).get("nullable") is not True
        or legacy_read.get("write_back") is not False
    ):
        raise TopologyError("legacy v1 normalized read projection differs")
    core_contracts = [
        value for path, value in documents.items()
        if path.startswith("contracts/android-practices-provider")
        or path.startswith("contracts/android-change-workflow")
    ]
    text = "\n".join(json.dumps(value, ensure_ascii=False, sort_keys=True).lower() for value in core_contracts)
    if re.search(r"(?<![a-z0-9])(?:sol|terra|luna)(?![a-z0-9])", text):
        raise TopologyError("core provider/workflow contracts contain provider-specific model names")


def validate_repository(root: Path = ROOT) -> None:
    current_path = root / CURRENT_CONTRACT.relative_to(ROOT)
    current = load_json(current_path)
    topology = load_json(root / MIGRATION_CONTRACT.relative_to(ROOT))
    matrix = load_json(root / COMPATIBILITY_MATRIX.relative_to(ROOT))
    validate_contract_documents(
        current, topology, matrix, current_sha256=file_sha256(current_path),
    )
    marketplace = load_json(root / MARKETPLACE.relative_to(ROOT))
    source_plugins = {
        path.parent.parent.name
        for path in (root / "plugins").glob("*/.codex-plugin/plugin.json")
    }
    source_plugins.add("codex-workspace-care")
    marketplace_plugins = {row["name"] for row in marketplace.get("plugins", [])}
    validate_materialized_plugin_ids(source_plugins, marketplace_plugins, topology)
    expected_marketplace = {
        row["id"] for row in current["plugins"] if row.get("marketplace") is True
    }
    if marketplace_plugins != expected_marketplace:
        raise TopologyError("released marketplace topology differs")
    for row in current["plugins"]:
        plugin = row["id"]
        plugin_root = root / "plugins" / plugin
        if not plugin_root.is_dir():
            raise TopologyError(f"declared plugin source is missing: {plugin}")
        if row.get("role") == "independent_source":
            continue
        actual_skills = manifest_skills(root, plugin)
        if actual_skills != row["skills"]:
            raise TopologyError(f"manifest skills mismatch for {plugin}")
        for skill in actual_skills:
            if not (plugin_root / "skills" / skill / "SKILL.md").is_file():
                raise TopologyError(f"declared Skill is missing: {plugin}:{skill}")
    core = root / "plugins/android-framework-ops"
    if (core / "skills/android-source-access").exists():
        raise TopologyError("core must not expose a third public android-source-access Skill")
    if not (core / "internal/android-source-access/scripts/android_source_access.py").is_file():
        raise TopologyError("core internal source-access dispatcher is missing")
    for plugin in ("android-wsl-ops", "android-mac-ops"):
        scripts = root / "plugins" / plugin / "skills/android-source-access/scripts"
        if not (scripts / "_core_source_access.py").is_file():
            raise TopologyError(f"source-access locator is missing: {plugin}")
        if not (scripts / "_platform_shim.sh").is_file():
            raise TopologyError(f"source-access shim is missing: {plugin}")
    validate_phase0_schema_documents(root)


def main() -> int:
    try:
        validate_repository(ROOT)
    except (OSError, json.JSONDecodeError, TopologyError) as error:
        raise SystemExit(str(error)) from error
    print("Active plugin topology validation passed")
    print("AKBS 2 Phase 0 declaration-only contracts validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
