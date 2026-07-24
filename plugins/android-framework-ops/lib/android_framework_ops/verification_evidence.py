from __future__ import annotations

from typing import Any, Mapping


VERIFICATION_EVIDENCE_CONTRACT_VERSION = "akbs-verification-evidence/v2"
BUILD_DELIVERY_SCOPE = "build_delivery"
REQUIREMENT_SCOPE = "feature"
REQUIREMENT_ACCEPTED = "accepted"
REQUIREMENT_REJECTED = "rejected"
REQUIREMENT_UNVERIFIED = "unverified"


def build_delivery_contract_fields() -> dict[str, str]:
    return {
        "contract_version": VERIFICATION_EVIDENCE_CONTRACT_VERSION,
        "scope": BUILD_DELIVERY_SCOPE,
        "requirement_acceptance": REQUIREMENT_UNVERIFIED,
    }


def requirement_contract_fields(result: str) -> dict[str, str]:
    normalized = str(result or "").upper()
    if normalized == "PASS":
        acceptance = REQUIREMENT_ACCEPTED
    elif normalized == "FAIL":
        acceptance = REQUIREMENT_REJECTED
    else:
        acceptance = REQUIREMENT_UNVERIFIED
    return {
        "contract_version": VERIFICATION_EVIDENCE_CONTRACT_VERSION,
        "scope": REQUIREMENT_SCOPE,
        "requirement_acceptance": acceptance,
    }


def has_authoritative_requirement_result(
    payload: Mapping[str, Any],
    *,
    expected_result: str | None = None,
) -> bool:
    result = str(payload.get("result") or "").upper()
    if expected_result is not None and result != str(expected_result).upper():
        return False
    if payload.get("contract_version") != VERIFICATION_EVIDENCE_CONTRACT_VERSION:
        return False
    if payload.get("scope") != REQUIREMENT_SCOPE:
        return False
    expected_acceptance = {
        "PASS": REQUIREMENT_ACCEPTED,
        "FAIL": REQUIREMENT_REJECTED,
    }.get(result)
    if expected_acceptance is None or payload.get("requirement_acceptance") != expected_acceptance:
        return False
    method = payload.get("method")
    if method == "device":
        return bool(payload.get("build")) and bool(payload.get("steps"))
    if method == "equivalent":
        return bool(
            payload.get("equivalent_type")
            and payload.get("reason")
            and payload.get("coverage")
            and payload.get("remaining_risk")
        )
    return False
