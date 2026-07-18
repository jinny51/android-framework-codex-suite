from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PUBLIC_CONTRACT_PATH = Path(__file__).resolve().parents[2] / "references" / "incoming-public-contract-v1.json"

PATCH_PACKAGE_CONTRACT_SCHEMA = "akbs-patch-package-contract/v1"


@lru_cache(maxsize=1)
def public_contract() -> dict[str, Any]:
    payload = json.loads(PUBLIC_CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != "akbs-incoming-public-contract-v1":
        raise RuntimeError("packaged incoming public contract schema is invalid")
    families = payload.get("reason_code_families")
    success = payload.get("success_reason_codes")
    if not isinstance(families, dict) or not families or not isinstance(success, list) or not success:
        raise RuntimeError("packaged incoming public contract reason codes are missing")
    error_codes = [code for codes in families.values() if isinstance(codes, list) for code in codes]
    all_codes = [*error_codes, *success]
    if any(not isinstance(code, str) or not code for code in all_codes) or len(all_codes) != len(set(all_codes)):
        raise RuntimeError("packaged incoming public contract reason codes must be unique non-empty strings")
    completion = payload.get("patch_information_completion")
    if not isinstance(completion, dict) or completion.get("schema") != "akbs-patch-package-information-completion/v1":
        raise RuntimeError("packaged patch information completion contract is missing")
    fields = completion.get("fields")
    field_ids = [item.get("id") for item in fields or [] if isinstance(item, dict)]
    if (
        not isinstance(fields, list)
        or len(field_ids) != len(fields)
        or len(field_ids) != len(set(field_ids))
        or any(not isinstance(value, str) or not value for value in field_ids)
    ):
        raise RuntimeError("packaged patch information completion fields are invalid")
    attachment = completion.get("attachment")
    if (
        not isinstance(attachment, dict)
        or not isinstance(attachment.get("max_file_bytes"), int)
        or not isinstance(attachment.get("max_total_bytes"), int)
        or attachment.get("patch_assets_immutable") is not True
    ):
        raise RuntimeError("packaged patch information attachment boundary is invalid")
    _validate_patch_package_contract(payload.get("patch_package_contract"), families)
    return payload


def _validate_string_list(value: Any, *, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise RuntimeError(f"packaged patch package contract {label} is invalid")
    return tuple(value)


def _validate_patch_package_contract(value: Any, reason_families: dict[str, Any]) -> None:
    if not isinstance(value, dict) or value.get("schema") != PATCH_PACKAGE_CONTRACT_SCHEMA:
        raise RuntimeError("packaged patch package contract is missing")

    identity = value.get("business_identity")
    if (
        not isinstance(identity, dict)
        or identity.get("visible_package_type") != "patch_package"
        or identity.get("queue_identity") != "patch_package_heads.package_key"
        or identity.get("main_branch_identity") != "curation_units.unit_id"
        or identity.get("patch_assets_immutable") is not True
        or identity.get("non_patch_envelope_append_only") is not True
    ):
        raise RuntimeError("packaged patch package business identity is invalid")

    patch_set = value.get("patch_set")
    if (
        not isinstance(patch_set, dict)
        or patch_set.get("algorithm") != "sha256-canonical-json-v1"
        or patch_set.get("source") != "package_assets[asset_type=patch]"
        or patch_set.get("sort") != ["relative_path", "sha256"]
        or patch_set.get("fields") != ["relative_path", "sha256", "size_bytes"]
    ):
        raise RuntimeError("packaged patch-set identity contract is invalid")

    queue = value.get("queue")
    if not isinstance(queue, dict):
        raise RuntimeError("packaged patch queue contract is missing")
    states = _validate_string_list(queue.get("states"), label="queue states")
    expected_states = (
        "received",
        "information_requested",
        "information_submitted",
        "admitted",
        "rejected",
    )
    if states != expected_states:
        raise RuntimeError("packaged patch queue states drifted")
    terminal_states = _validate_string_list(queue.get("terminal_states"), label="terminal states")
    if terminal_states != ("admitted", "rejected"):
        raise RuntimeError("packaged patch queue terminal states drifted")
    transitions = queue.get("transitions")
    if not isinstance(transitions, list) or not transitions:
        raise RuntimeError("packaged patch queue transitions are missing")
    normalized_transitions: list[tuple[str, str, str]] = []
    for transition in transitions:
        if not isinstance(transition, dict) or set(transition) != {"from", "action", "to"}:
            raise RuntimeError("packaged patch queue transition is invalid")
        source = transition.get("from")
        action = transition.get("action")
        target = transition.get("to")
        if source not in states or target not in states or not isinstance(action, str) or not action:
            raise RuntimeError("packaged patch queue transition references an invalid state or action")
        normalized_transitions.append((source, action, target))
    if len(normalized_transitions) != len(set(normalized_transitions)):
        raise RuntimeError("packaged patch queue transitions must be unique")
    if not isinstance(queue.get("idempotency"), str) or not queue["idempotency"]:
        raise RuntimeError("packaged patch queue idempotency contract is missing")

    patch_queue_codes = _validate_string_list(reason_families.get("patch_queue"), label="reason codes")
    required_queue_codes = {
        "information_request_not_found",
        "information_request_closed",
        "patch_asset_immutable",
        "patch_set_proof_mismatch",
        "queue_state_closed",
        "queue_state_not_reviewable",
    }
    if not required_queue_codes.issubset(patch_queue_codes):
        raise RuntimeError("packaged patch queue reason codes are incomplete")

    curation = value.get("curation")
    if not isinstance(curation, dict):
        raise RuntimeError("packaged patch curation contract is missing")
    allowed_decisions = _validate_string_list(curation.get("allowed_decisions"), label="curation decisions")
    forbidden_decisions = _validate_string_list(
        curation.get("forbidden_decisions"), label="forbidden curation decisions"
    )
    if set(allowed_decisions) & set(forbidden_decisions):
        raise RuntimeError("packaged patch curation decisions overlap")
    _validate_string_list(curation.get("member_actions"), label="member actions")
    _validate_string_list(curation.get("forbidden_actions"), label="forbidden member actions")
    _validate_string_list(value.get("retired_business_fields"), label="retired fields")
    _validate_string_list(value.get("retired_business_values"), label="retired values")
    _validate_string_list(value.get("regenerate_when"), label="regeneration reasons")

    history = value.get("history")
    if (
        not isinstance(history, dict)
        or history.get("raw_rows") != "immutable_audit_only"
        or history.get("missing_parent_projection") != "history_compatible_patch_package"
        or history.get("inferred_relation_requires_audit_marker") is not True
    ):
        raise RuntimeError("packaged patch package history contract is invalid")
    public_source_roles = _validate_string_list(
        history.get("public_source_roles"), label="public history source roles"
    )
    if "source" not in public_source_roles or {"root_original", "supplement", "replacement"} & set(
        public_source_roles
    ):
        raise RuntimeError("packaged patch package public source roles are invalid")


def error_reason_codes() -> frozenset[str]:
    families = public_contract()["reason_code_families"]
    return frozenset(code for codes in families.values() for code in codes)


def success_reason_codes() -> tuple[str, ...]:
    return tuple(public_contract()["success_reason_codes"])


def patch_queue_reason_codes() -> frozenset[str]:
    return frozenset(public_contract()["reason_code_families"]["patch_queue"])


def patch_queue_states() -> tuple[str, ...]:
    return tuple(public_contract()["patch_package_contract"]["queue"]["states"])


def patch_queue_terminal_states() -> frozenset[str]:
    return frozenset(public_contract()["patch_package_contract"]["queue"]["terminal_states"])


def patch_information_completion_fields() -> frozenset[str]:
    return frozenset(
        str(item["id"]) for item in public_contract()["patch_information_completion"]["fields"]
    )


def patch_information_attachment_limits() -> tuple[int, int]:
    attachment = public_contract()["patch_information_completion"]["attachment"]
    return int(attachment["max_file_bytes"]), int(attachment["max_total_bytes"])


def validate_success_response(payload: dict[str, Any]) -> None:
    incoming = payload.get("agent_context", {}).get("incoming_contract")
    if not isinstance(incoming, dict):
        raise RuntimeError("server success response is missing incoming contract evidence")
    if str(incoming.get("version") or "") != str(public_contract()["schema_version"]):
        raise RuntimeError("server success response incoming contract version drifted")
    if incoming.get("authority") != "akbs-server":
        raise RuntimeError("server success response incoming contract authority is invalid")
    actual = incoming.get("reason_codes")
    if actual != list(success_reason_codes()):
        raise RuntimeError("server success response reason codes drifted from the public contract")
