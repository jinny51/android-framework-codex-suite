from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PUBLIC_CONTRACT_PATH = Path(__file__).resolve().parents[2] / "references" / "incoming-public-contract-v1.json"


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
    return payload


def error_reason_codes() -> frozenset[str]:
    families = public_contract()["reason_code_families"]
    return frozenset(code for codes in families.values() for code in codes)


def success_reason_codes() -> tuple[str, ...]:
    return tuple(public_contract()["success_reason_codes"])


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
