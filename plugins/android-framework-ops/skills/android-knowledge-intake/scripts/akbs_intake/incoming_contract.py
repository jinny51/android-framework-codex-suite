from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


PUBLIC_CONTRACT_PATH = Path(__file__).resolve().parents[2] / "references" / "incoming-public-contract-v1.json"
ERROR_DETAIL_RE = re.compile(r"^incoming_contract_v1:([a-z0-9_]+):(?:\s|$)")


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
    return payload


def error_reason_codes() -> frozenset[str]:
    families = public_contract()["reason_code_families"]
    return frozenset(code for codes in families.values() for code in codes)


def success_reason_codes() -> tuple[str, ...]:
    return tuple(public_contract()["success_reason_codes"])


def server_error_reason_code(detail: Any) -> str:
    if not isinstance(detail, str):
        return ""
    match = ERROR_DETAIL_RE.match(detail)
    if not match:
        return ""
    code = match.group(1)
    if code not in error_reason_codes():
        raise RuntimeError(f"server returned undeclared incoming v1 reason code: {code}")
    return code


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
