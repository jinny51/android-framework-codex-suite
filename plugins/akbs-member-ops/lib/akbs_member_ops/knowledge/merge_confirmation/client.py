"""HTTP client for member merge-confirmation reads and explicit disputes."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from akbs_member_ops.knowledge.member import require_member_alias
from akbs_member_ops.http_client import (
    failure_result,
    invalid_success_response,
    request_json,
)
from akbs_member_ops.knowledge_search.config import member_merge_confirmations_url


def member_request_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "X-AKBS-User": require_member_alias(),
    }


def merge_api_error(exc: BaseException) -> str:
    return failure_result(exc).safe_summary("merge confirmation API unavailable")


def fetch_merge_confirmation_payload(
    confirmation_id: str = "",
    action: str = "",
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    request = urllib.request.Request(
        member_merge_confirmations_url(confirmation_id, action),
        headers=member_request_headers(),
        method="GET",
    )
    payload = request_json(request, timeout=timeout)
    returned_id = str(payload.get("confirmation_id") or "").strip()
    if confirmation_id and returned_id and returned_id != confirmation_id:
        raise invalid_success_response("merge confirmation response identity mismatch")
    return payload


def post_merge_dispute(
    confirmation_id: str,
    *,
    reason: str,
    member_assessment: str,
    evidence_refs: list[str],
    agent_notes: dict[str, Any],
    timeout: float = 3.0,
) -> dict[str, Any]:
    payload = {
        "reason": reason,
        "member_assessment": member_assessment,
        "evidence_refs": evidence_refs,
        "agent_notes": agent_notes,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = member_request_headers()
    headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        member_merge_confirmations_url(confirmation_id, "dispute"),
        data=data,
        headers=headers,
        method="POST",
    )
    result = request_json(request, timeout=timeout)
    returned_id = str(result.get("confirmation_id") or "").strip()
    if returned_id and returned_id != confirmation_id:
        raise invalid_success_response("merge dispute response confirmation identity mismatch")
    return result
