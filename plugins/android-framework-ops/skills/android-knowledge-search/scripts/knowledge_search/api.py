from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from knowledge_search.config import (
    akbs_endpoint_env_value,
    member_merge_confirmations_url,
    member_search_endpoint_url,
    selected_member_alias,
)


def should_try_server(args: Any) -> bool:
    if args.source == "local":
        return False
    if args.source == "server":
        return True
    if akbs_endpoint_env_value("MEMBER_SEARCH_URL"):
        return True
    return not bool(args.root)


def server_search_url(args: Any, query: str) -> str:
    endpoint, _source = member_search_endpoint_url()
    separator = "&" if "?" in endpoint else "?"
    params = {
        "q": query,
        "limit": str(max(args.limit, 1)),
    }
    if args.type and args.type != "all":
        params["type"] = args.type
    return endpoint + separator + urllib.parse.urlencode(params)


def normalize_server_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_results = payload.get("results")
    if raw_results is None:
        raw_results = payload.get("items")
    if not isinstance(raw_results, list):
        raw_results = []
    normalized: list[dict[str, Any]] = []
    search_mode = str(payload.get("search_mode") or "hybrid")
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row.setdefault("kind", row.get("type") or "knowledge")
        row.setdefault("id", row.get("case_id") or row.get("package_id") or row.get("knowledge_id") or row.get("id") or "")
        row.setdefault("title", row.get("title") or row.get("material_title") or row.get("summary") or row.get("case_title") or "")
        row["source"] = "server_hybrid"
        row["search_mode"] = search_mode
        row["reuse_grade"] = str(row.get("reuse_grade") or "unknown")
        if not isinstance(row.get("matched_channels"), list):
            row["matched_channels"] = []
        if not isinstance(row.get("matched_anchors"), list):
            row["matched_anchors"] = []
        normalized.append(row)
    return normalized


def fetch_server_hybrid_results(args: Any, query: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    profile, member_alias = selected_member_alias()
    user = member_alias or profile or "unknown"
    request = urllib.request.Request(
        server_search_url(args, query),
        headers={
            "Accept": "application/json",
            "X-AKBS-User": user,
            "X-AKBS-Role": "member",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=args.server_timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("server hybrid search response is not a JSON object")
    if str(payload.get("schema") or "") != "akbs-member-knowledge-search-v1":
        raise RuntimeError("server hybrid search response schema mismatch")
    return normalize_server_results(payload), payload


def server_fallback_reason(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"server hybrid search HTTP {exc.code}: {exc.reason}"
    if isinstance(exc, urllib.error.URLError):
        return f"server hybrid search unavailable: {exc.reason}"
    return f"server hybrid search unavailable: {exc}"


def member_request_headers() -> dict[str, str]:
    profile, member_alias = selected_member_alias()
    return {
        "Accept": "application/json",
        "X-AKBS-User": member_alias or profile or "unknown",
        "X-AKBS-Role": "member",
    }


def merge_api_error(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"merge confirmation API HTTP {exc.code}: {exc.reason}"
    if isinstance(exc, urllib.error.URLError):
        return f"merge confirmation API unavailable: {exc.reason}"
    return f"merge confirmation API unavailable: {exc}"


def fetch_merge_confirmation_payload(identifier: str = "", action: str = "", *, timeout: float = 3.0) -> dict[str, Any]:
    request = urllib.request.Request(
        member_merge_confirmations_url(identifier, action),
        headers=member_request_headers(),
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("merge confirmation response is not a JSON object")
    return payload


def post_merge_dispute(
    identifier: str,
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
        member_merge_confirmations_url(identifier, "dispute"),
        data=data,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise RuntimeError("merge dispute response is not a JSON object")
    return result
