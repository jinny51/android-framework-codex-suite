from __future__ import annotations

import urllib.parse
import urllib.request
from typing import Any

from android_engineering_ops.knowledge.member import require_member_alias
from android_engineering_ops.knowledge.merge_confirmation.client import (
    fetch_merge_confirmation_payload,
    member_request_headers,
    merge_api_error,
    post_merge_dispute,
)
from android_framework_ops.http_client import (
    failure_result,
    invalid_success_response,
    request_json,
)

from knowledge_search.config import (
    akbs_endpoint_env_value,
    member_search_endpoint_url,
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
    search_mode = str(payload.get("search_mode") or "unknown")
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row.setdefault("kind", row.get("type") or "knowledge")
        row.setdefault("id", row.get("case_id") or row.get("package_id") or row.get("knowledge_id") or row.get("id") or "")
        row.setdefault("title", row.get("title") or row.get("material_title") or row.get("summary") or row.get("case_title") or "")
        row["source"] = "server_api"
        row["search_mode"] = search_mode
        row["reuse_grade"] = str(row.get("reuse_grade") or "unknown")
        if not isinstance(row.get("matched_channels"), list):
            row["matched_channels"] = []
        if not isinstance(row.get("matched_anchors"), list):
            row["matched_anchors"] = []
        normalized.append(row)
    return normalized


def fetch_server_results(args: Any, query: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    user = require_member_alias()
    request = urllib.request.Request(
        server_search_url(args, query),
        headers={
            "Accept": "application/json",
            "X-AKBS-User": user,
        },
        method="GET",
    )
    payload = request_json(request, timeout=args.server_timeout)
    if str(payload.get("schema") or "") != "akbs-member-knowledge-search-v1":
        raise invalid_success_response("server search response schema mismatch")
    return normalize_server_results(payload), payload


def server_fallback_reason(exc: BaseException) -> str:
    return failure_result(exc).safe_summary("server search unavailable")
