#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_LIB = PLUGIN_ROOT / "lib"
if PLUGIN_LIB.is_dir() and str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from knowledge_search.config import (
    DEFAULT_AKBS_API_BASE_URL,
    ROOT_MARKERS,
    akbs_endpoint_env_value,
    codex_home,
    config_payloads,
    configured_roots,
    expand_path,
    member_merge_confirmations_url,
    member_search_endpoint_url,
    search_usage_root as configured_search_usage_root,
    selected_member_alias,
)
from knowledge_search.formatting import compact_list, format_markdown, parse_json, result_date


AI_DEFAULT_RESULT_KINDS = {"case", "variant", "patch", "symbol"}
AI_EVIDENCE_KINDS = {
    "patch_diff_facts",
    "patch_problem_summary",
    "project_inference",
    "risk_surface",
    "build_result",
    "verification_result",
    "search_before_change",
}
REUSE_DECISIONS = ("reuse", "adapt", "reference_only", "not_applicable", "not_found", "unknown")
REUSE_OUTCOMES = ("not_started", "reused_success", "adapted_success", "failed", "partial", "unverified", "not_applicable")


def search_usage_root() -> Path:
    return configured_search_usage_root(config_payloads_fn=config_payloads)


def result_id(row: dict[str, Any]) -> str:
    for key in ("case_id", "variant_id", "patch_id", "symbol", "evidence_id", "report_id", "event_id", "id"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def usage_result(row: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": row.get("kind", ""),
        "id": result_id(row),
    }
    title = row.get("title") or row.get("patch_name") or row.get("summary") or row.get("problem") or row.get("symbol")
    if isinstance(title, str) and title:
        payload["title"] = title
    path = row.get("path")
    if isinstance(path, str) and path:
        payload["path"] = path
    score = row.get("_score")
    if isinstance(score, (int, float)):
        payload["score"] = score
    for key in ("source", "search_mode", "reuse_grade", "matched_channels", "matched_anchors", "case_id", "package_id"):
        value = row.get(key)
        if value not in (None, "", []):
            payload[key] = value
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record_search_usage(
    args: argparse.Namespace,
    root: Path | None,
    query: str,
    results: list[dict[str, Any]],
    *,
    source: str,
    search_mode: str,
    fallback_reason: str = "",
) -> Path | None:
    if args.no_record_usage or not query:
        return None
    now = dt.datetime.now().astimezone()
    profile, member_alias = selected_member_alias()
    decision = args.reuse_decision or ("not_found" if not results else "unknown")
    result_payloads = [usage_result(item) for item in results]
    digest = hashlib.sha1(
        json.dumps(
            {
                "query": query,
                "created_at": now.isoformat(timespec="seconds"),
                "decision": decision,
                "results": result_payloads[:8],
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    payload = {
        "schema": "android-knowledge-search-usage",
        "schema_version": "1",
        "created_at": now.isoformat(timespec="seconds"),
        "date": now.date().isoformat(),
        "profile": profile,
        "member_alias": member_alias,
        "root": str(root) if root else "",
        "query": query,
        "type": args.type,
        "limit": max(args.limit, 1),
        "source": source,
        "search_mode": search_mode,
        "fallback_reason": fallback_reason,
        "reuse_grades": sorted({str(item.get("reuse_grade") or "") for item in results if item.get("reuse_grade")}),
        "searched": True,
        "decision": decision,
        "reuse_decision": decision,
        "targets": args.reuse_target or [],
        "match_points": args.reuse_match or [],
        "mismatch_points": args.reuse_mismatch or [],
        "reason": args.reuse_reason or "",
        "outcome": args.reuse_outcome or "not_started",
        "result_count": len(results),
        "results": result_payloads,
    }
    path = search_usage_root() / now.strftime("%Y%m%d") / f"{now.strftime('%Y%m%d-%H%M%S')}-{digest}.json"
    write_json(path, payload)
    return path


def codex_documents_roots() -> list[Path]:
    candidates: list[Path] = []
    if os.environ.get("CODEX_DOCUMENTS"):
        candidates.append(expand_path(os.environ["CODEX_DOCUMENTS"]))
    candidates.append(expand_path(Path.home() / "Documents" / "Codex"))

    windows_users = Path("/mnt/c/Users")
    if windows_users.is_dir():
        try:
            for user_dir in windows_users.iterdir():
                candidates.append(user_dir / "Documents" / "Codex")
        except OSError:
            pass

    result: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def is_knowledge_root(path: Path) -> bool:
    try:
        return path.is_dir() and any((path / marker).exists() for marker in ROOT_MARKERS)
    except OSError:
        return False


def parent_candidates(path: Path) -> list[Path]:
    candidates = [path]
    candidates.extend(path.parents)
    return candidates


def candidate_roots(explicit_root: str | None) -> list[Path]:
    candidates: list[Path] = []
    if explicit_root:
        candidates.append(expand_path(explicit_root))
    env_root = os.environ.get("CODEX_KNOWLEDGE_ROOT")
    if env_root:
        candidates.append(expand_path(env_root))
    candidates.extend(configured_roots())

    try:
        candidates.extend(parent_candidates(Path.cwd().resolve()))
    except OSError:
        pass

    home = codex_home()
    for documents in codex_documents_roots():
        candidates.extend(
            [
                documents / "worktrees" / "knowledge",
            ]
        )
    candidates.extend(
        [
            home / "worktrees" / "knowledge",
            Path("/mnt/z/knowledge/knowledge"),
        ]
    )

    result: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        try:
            resolved = item.resolve()
        except OSError:
            resolved = item
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def find_root(explicit_root: str | None) -> Path:
    checked: list[str] = []
    for root in candidate_roots(explicit_root):
        checked.append(str(root))
        if is_knowledge_root(root):
            return root
    raise SystemExit(
        "knowledge repository root not found. Pass --root <path>, set CODEX_KNOWLEDGE_ROOT, or configure knowledge_repo_worktree. Checked:\n"
        + "\n".join(f" - {item}" for item in checked[:16])
    )


def should_try_server(args: argparse.Namespace) -> bool:
    if args.source == "local":
        return False
    if args.source == "server":
        return True
    if akbs_endpoint_env_value("MEMBER_SEARCH_URL"):
        return True
    return not bool(args.root)


def server_search_url(args: argparse.Namespace, query: str) -> str:
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


def fetch_server_hybrid_results(args: argparse.Namespace, query: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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


def merge_identifier_from_payload(payload: dict[str, Any]) -> str:
    for key in ("review_id", "package_key", "id"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def text_or_unknown(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else "unknown"


def merge_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def merge_detail_from_payloads(detail: dict[str, Any], target: dict[str, Any], compare: dict[str, Any]) -> dict[str, Any]:
    merged = dict(detail)
    for key, value in target.items():
        if value not in (None, "", [], {}) and key not in merged:
            merged[key] = value
    for key, value in compare.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def compact_evidence_items(value: Any, limit: int = 5) -> list[str]:
    items = value if isinstance(value, list) else []
    lines: list[str] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            summary = item.get("summary") or item.get("title") or item.get("reason") or item.get("id") or item.get("kind")
            lines.append(str(summary or item))
        else:
            lines.append(str(item))
    return [line for line in lines if line]


def build_merge_analysis(detail: dict[str, Any], target: dict[str, Any], compare: dict[str, Any]) -> dict[str, Any]:
    combined = merge_detail_from_payloads(detail, target, compare)
    context = combined.get("member_agent_context") if isinstance(combined.get("member_agent_context"), dict) else {}
    target_knowledge = combined.get("target_knowledge") if isinstance(combined.get("target_knowledge"), dict) else {}
    if not target_knowledge and isinstance(context.get("target_case"), dict):
        target_knowledge = context["target_case"]
    supporting = compact_evidence_items(combined.get("merge_basis") or context.get("supporting_evidence"))
    counter = compact_evidence_items(combined.get("counter_evidence") or context.get("counter_evidence"))
    matched_anchors = combined.get("matched_anchors") or context.get("matched_anchors") or []
    code_anchors = context.get("code_anchors") if isinstance(context.get("code_anchors"), dict) else {}
    can_dispute = bool((combined.get("actions") if isinstance(combined.get("actions"), dict) else {}).get("can_submit_dispute"))
    has_counter = bool(counter)
    recommendation = "建议先核对反向证据；如目标知识与实际修改目标不一致，再发送异议。" if has_counter else "当前未看到明确反向证据；默认建议先确认合并依据，不自动提出异议。"
    if not can_dispute:
        recommendation = "当前状态不允许成员提交异议；只能作为只读分析材料。"
    draft = ""
    if can_dispute:
        title = target_knowledge.get("title") or combined.get("material_display_title") or merge_identifier_from_payload(combined)
        draft = f"我认为该材料不应合并到“{title}”。请复核目标知识、代码锚点和反向证据。"
        if counter:
            draft += " 反向证据：" + "；".join(counter[:3])
    return {
        "schema": "akbs-member-merge-confirmation-analysis-v1",
        "review_id": str(combined.get("review_id") or ""),
        "package_key": str(combined.get("package_key") or ""),
        "confirmation_status": str(combined.get("confirmation_status") or context.get("merge_status") or ""),
        "material_title": str(combined.get("material_display_title") or ""),
        "target_knowledge": target_knowledge,
        "why_merged": supporting,
        "matched_anchors": matched_anchors if isinstance(matched_anchors, list) else [],
        "code_anchors": code_anchors,
        "counter_evidence": counter,
        "can_submit_dispute": can_dispute,
        "recommendation": recommendation,
        "dispute_reason_draft": draft,
        "member_agent_context": context,
    }


def format_merge_list(payload: dict[str, Any]) -> str:
    items = merge_items(payload)
    lines = [
        "# 合并确认列表",
        "",
        f"- total: {payload.get('total', len(items))}",
        "- source: server_merge_confirmation",
        "",
    ]
    if not items:
        lines.append("暂无需要 Codex 分析的合并确认项。")
        return "\n".join(lines)
    for index, item in enumerate(items, start=1):
        target = item.get("target_knowledge") if isinstance(item.get("target_knowledge"), dict) else {}
        actions = item.get("actions") if isinstance(item.get("actions"), dict) else {}
        lines.extend(
            [
                f"{index}. {text_or_unknown(item.get('material_display_title'))}",
                f"   - review_id: {text_or_unknown(item.get('review_id'))}",
                f"   - package_key: {text_or_unknown(item.get('package_key'))}",
                f"   - 状态: {text_or_unknown(item.get('confirmation_status_label') or item.get('confirmation_status'))}",
                f"   - 目标知识: {text_or_unknown(target.get('case_id'))} / {text_or_unknown(target.get('title'))}",
                f"   - 可提交异议: {'yes' if actions.get('can_submit_dispute') else 'no'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def format_merge_payload(title: str, payload: dict[str, Any]) -> str:
    target = payload.get("target_knowledge") if isinstance(payload.get("target_knowledge"), dict) else {}
    context = payload.get("member_agent_context") if isinstance(payload.get("member_agent_context"), dict) else {}
    lines = [
        f"# {title}",
        "",
        f"- review_id: {text_or_unknown(payload.get('review_id'))}",
        f"- package_key: {text_or_unknown(payload.get('package_key'))}",
    ]
    if payload.get("dispute_id") or payload.get("state"):
        lines.append(f"- dispute/state: {text_or_unknown(payload.get('dispute_id'))} / {text_or_unknown(payload.get('state'))}")
    if payload.get("material_display_title"):
        lines.append(f"- 材料: {payload.get('material_display_title')}")
    if target:
        lines.append(f"- 目标知识: {text_or_unknown(target.get('case_id'))} / {text_or_unknown(target.get('title'))}")
        if target.get("summary"):
            lines.append(f"- 目标摘要: {target.get('summary')}")
    if payload.get("source_material"):
        source = payload.get("source_material") if isinstance(payload.get("source_material"), dict) else {}
        lines.append(f"- 来源材料: {text_or_unknown(source.get('title'))} / {text_or_unknown(source.get('package_key'))}")
    if payload.get("merge_basis"):
        lines.append("- 合并依据: " + "；".join(compact_evidence_items(payload.get("merge_basis"))))
    if payload.get("matched_anchors"):
        lines.append(f"- 相同锚点: {compact_list(payload.get('matched_anchors'), 8)}")
    if payload.get("counter_evidence"):
        lines.append("- 反向证据: " + "；".join(compact_evidence_items(payload.get("counter_evidence"))))
    if context:
        lines.append(f"- Codex 分析证据: schema={text_or_unknown(context.get('schema'))}, reuse_grade={text_or_unknown(context.get('reuse_grade'))}")
    return "\n".join(lines)


def format_merge_analysis(analysis: dict[str, Any]) -> str:
    target = analysis.get("target_knowledge") if isinstance(analysis.get("target_knowledge"), dict) else {}
    lines = [
        "# 合并确认 Codex 分析摘要",
        "",
        "## 人看摘要",
        "",
        f"- 材料: {text_or_unknown(analysis.get('material_title'))}",
        f"- review_id/package_key: {text_or_unknown(analysis.get('review_id'))} / {text_or_unknown(analysis.get('package_key'))}",
        f"- 当前状态: {text_or_unknown(analysis.get('confirmation_status'))}",
        f"- 目标知识: {text_or_unknown(target.get('case_id'))} / {text_or_unknown(target.get('title'))}",
        f"- 是否可提交异议: {'yes' if analysis.get('can_submit_dispute') else 'no'}",
        f"- 建议: {analysis.get('recommendation')}",
        "",
        "## Codex 分析证据",
        "",
    ]
    why_merged = analysis.get("why_merged") if isinstance(analysis.get("why_merged"), list) else []
    counter = analysis.get("counter_evidence") if isinstance(analysis.get("counter_evidence"), list) else []
    matched = analysis.get("matched_anchors") if isinstance(analysis.get("matched_anchors"), list) else []
    lines.append("- 合并依据: " + ("；".join(why_merged) if why_merged else "未返回结构化合并依据"))
    lines.append("- 相同锚点: " + (compact_list(matched, 8) if matched else "未返回结构化相同锚点"))
    lines.append("- 反向证据: " + ("；".join(counter) if counter else "未返回结构化反向证据"))
    lines.extend(["", "## 异议理由草稿", ""])
    lines.append(analysis.get("dispute_reason_draft") or "当前不生成异议理由草稿。")
    return "\n".join(lines)


def refresh_root(root: Path) -> str:
    if not (root / ".git").exists():
        return "skip: root is not a Git worktree"
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if status.returncode != 0:
        return f"skip: git status failed: {status.stderr.strip()}"
    if status.stdout.strip():
        return "skip: worktree is dirty"
    pull = subprocess.run(
        ["git", "-C", str(root), "pull", "--ff-only"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if pull.returncode != 0:
        return f"failed: {pull.stderr.strip() or pull.stdout.strip()}"
    return pull.stdout.strip() or "already up to date"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def object_status(value: Any) -> str:
    return str(value or "").strip().lower()


def is_retracted_object(item: dict[str, Any]) -> bool:
    validity = item.get("knowledge_validity") if isinstance(item.get("knowledge_validity"), dict) else {}
    return (
        bool(item.get("retracted"))
        or bool(validity.get("retracted"))
        or object_status(item.get("status")) == "retracted"
        or object_status(item.get("status_maturity")) == "retracted"
        or object_status(item.get("result")) == "retracted"
    )


def row_case_id(item: dict[str, Any]) -> str:
    return str(item.get("case_id") or "").strip()


def case_is_searchable(case_id: str, active_case_ids: set[str]) -> bool:
    return not active_case_ids or not case_id or case_id in active_case_ids


def append_token(tokens: set[str], value: Any) -> None:
    text = str(value or "").strip()
    if text:
        tokens.add(text)


def retracted_reference_tokens(index_rows: list[dict[str, Any]], patch_rows: list[dict[str, Any]]) -> set[str]:
    tokens: set[str] = set()
    for item in [*index_rows, *patch_rows]:
        if not is_retracted_object(item):
            continue
        append_token(tokens, item.get("case_id"))
        append_token(tokens, item.get("variant_id"))
        append_token(tokens, item.get("patch_id"))
        append_token(tokens, item.get("id"))
        for key in ("case_ids", "variant_ids", "patch_ids"):
            value = item.get(key)
            if isinstance(value, list):
                for entry in value:
                    append_token(tokens, entry)
    return tokens


def contains_retracted_reference(value: Any, tokens: set[str]) -> bool:
    if not tokens:
        return False
    return any(token and token in stringify(value) for token in tokens)


def redact_retracted_references(value: Any, tokens: set[str]) -> Any:
    if not tokens:
        return value
    if isinstance(value, list):
        return [
            redacted
            for item in value
            if not contains_retracted_reference(item, tokens)
            for redacted in [redact_retracted_references(item, tokens)]
        ]
    if isinstance(value, dict):
        return {key: redact_retracted_references(item, tokens) for key, item in value.items()}
    if contains_retracted_reference(value, tokens):
        return ""
    return value


def evidence_row(item: dict[str, Any]) -> dict[str, Any]:
    row = dict(item)
    row["evidence_kind"] = row.pop("kind", "")
    row["id"] = row.get("id") or row.get("evidence_id") or ""
    row["payload"] = parse_json(row.get("payload"), {})
    row["kind"] = "evidence"
    return row


def load_from_jsonl(root: Path, include_archive: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    case_index_rows = read_jsonl(root / "index" / "case-index.jsonl")
    variant_index_rows = read_jsonl(root / "index" / "variant-index.jsonl")
    evidence_index_rows = read_jsonl(root / "index" / "evidence-index.jsonl")
    symbol_index_rows = read_jsonl(root / "index" / "symbol-index.jsonl")
    patch_index_rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("patches/by-id/*/patch.json")):
        item = parse_json(path.read_text(encoding="utf-8", errors="ignore"), {})
        if isinstance(item, dict):
            patch_index_rows.append({**item, "path": str(path.relative_to(root))})
    retracted_tokens = retracted_reference_tokens([*case_index_rows, *variant_index_rows, *evidence_index_rows], patch_index_rows)
    search_docs = {str(item.get("case_id", "")): item for item in read_jsonl(root / "index" / "search-docs.jsonl")}
    active_case_ids = {
        case_id
        for case_id, item in search_docs.items()
        if case_id and (include_archive or not is_retracted_object(item))
    }
    rejected_patch_ids: set[str] = set()
    active_patch_ids: set[str] = set()
    for item in case_index_rows:
        case_id = str(item.get("case_id", ""))
        if not include_archive and (is_retracted_object(item) or not case_is_searchable(case_id, active_case_ids)):
            continue
        doc = search_docs.get(case_id, {})
        replacement_fields = {
            key: doc.get(key, item.get(key))
            for key in ("replacement_case_id", "replacement_title", "replaces_case_ids")
            if doc.get(key, item.get(key))
        }
        rows.append(
            {
                **item,
                "kind": "case",
                "id": case_id,
                "source_priority": doc.get("source_priority", item.get("source_priority", 0)),
                "text": doc.get("text", item.get("text", "")),
                "variant_ids": doc.get("variant_ids", item.get("variant_ids", [])),
                **replacement_fields,
            }
        )
    for item in variant_index_rows:
        case_id = row_case_id(item)
        if not include_archive and (is_retracted_object(item) or not case_is_searchable(case_id, active_case_ids)):
            continue
        rows.append({"kind": "variant", "id": item.get("variant_id", ""), **item})
    for item in evidence_index_rows:
        case_id = row_case_id(item)
        if not include_archive and (is_retracted_object(item) or not case_is_searchable(case_id, active_case_ids)):
            continue
        row = evidence_row(item)
        if not include_archive:
            row["payload"] = redact_retracted_references(row.get("payload"), retracted_tokens)
        rows.append(row)
    loaded_evidence_ids = {str(row.get("evidence_id") or row.get("id") or "") for row in rows if row.get("kind") == "evidence"}
    if include_archive:
        for path in sorted(root.glob("evidence/by-id/*.json")):
            item = parse_json(path.read_text(encoding="utf-8", errors="ignore"), {})
            evidence_id = str(item.get("evidence_id") or "")
            if isinstance(item, dict) and evidence_id not in loaded_evidence_ids:
                rows.append(evidence_row({**item, "path": str(path.relative_to(root))}))
    patch_rows: list[dict[str, Any]] = []
    for item in patch_index_rows:
        if isinstance(item, dict):
            patch_id = str(item.get("patch_id") or "")
            if not include_archive and (
                is_retracted_object(item) or not case_is_searchable(row_case_id(item), active_case_ids)
            ):
                if patch_id:
                    rejected_patch_ids.add(patch_id)
                continue
            if patch_id:
                active_patch_ids.add(patch_id)
            patch_rows.append({"kind": "patch", "id": patch_id, **item})
    for item in symbol_index_rows:
        case_id = row_case_id(item)
        patch_id = str(item.get("patch_id") or "")
        if not include_archive and (
            is_retracted_object(item)
            or not case_is_searchable(case_id, active_case_ids)
            or patch_id in rejected_patch_ids
            or (active_patch_ids and patch_id and patch_id not in active_patch_ids)
        ):
            continue
        rows.append({"kind": "symbol", "id": item.get("symbol_id", ""), "symbol": item.get("value", ""), **item})
    rows.extend(patch_rows)
    if include_archive:
        for path in sorted(root.glob("reports/by-id/*.json")):
            item = parse_json(path.read_text(encoding="utf-8", errors="ignore"), {})
            if isinstance(item, dict):
                rows.append({"kind": "report", "id": item.get("report_id", ""), "path": str(path.relative_to(root)), **item})
        for path in sorted(root.glob("events/by-id/*.json")):
            item = parse_json(path.read_text(encoding="utf-8", errors="ignore"), {})
            if isinstance(item, dict):
                rows.append({"kind": "event", "id": item.get("event_id", ""), "path": str(path.relative_to(root)), **item})
    return rows


def load_rows(root: Path, include_archive: bool = False) -> list[dict[str, Any]]:
    return load_from_jsonl(root, include_archive=include_archive)


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(stringify(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {stringify(item)}" for key, item in value.items())
    return str(value)


def row_text(row: dict[str, Any]) -> str:
    keys = [
        "id",
        "type",
        "case_id",
        "variant_id",
        "variant_ids",
        "report_ids",
        "title",
        "problem",
        "requirement_or_symptom",
        "solution_summary",
        "implementation_scope",
        "summary",
        "text",
        "overview",
        "author",
        "member_alias",
        "member_name",
        "project",
        "scope",
        "platform",
        "android_version",
        "repo_paths",
        "repo_path",
        "branch",
        "source_tree",
        "feature_slug",
        "original_patch_name",
        "patch_name",
        "patch_names",
        "content_sha1",
        "filename_confidence",
        "module",
        "status",
        "package_status",
        "reuse_hint",
        "package_kind",
        "validation_status",
        "result",
        "kind",
        "evidence_kind",
        "note",
        "source_package",
        "readme",
        "report_path",
        "patch_files",
        "modified_files",
        "modules",
        "symbols",
        "framework_log_keys",
        "system_properties",
        "settings_keys",
        "resource_keys",
        "strings",
        "keywords",
        "problem_summary",
        "solution_summary",
        "keywords",
        "inference_confidence",
        "inference_basis",
        "inference_limits",
        "risk_areas",
        "symbol",
        "path",
        "patch_id",
        "patch_ids",
        "items",
        "payload",
        "package_id",
        "event_id",
    ]
    return " ".join(stringify(row.get(key)) for key in keys)


def query_terms(query: str) -> list[str]:
    return [item.lower() for item in re.split(r"\s+", query.strip()) if item.strip()]


def score_row(row: dict[str, Any], terms: list[str]) -> tuple[int, list[str]]:
    if not terms:
        return 1, []
    weighted_fields = [
        (8, "title"),
        (8, "summary"),
        (8, "problem"),
        (8, "requirement_or_symptom"),
        (8, "solution_summary"),
        (8, "implementation_scope"),
        (8, "text"),
        (8, "feature_slug"),
        (8, "repo_path"),
        (8, "repo_paths"),
        (8, "summary"),
        (7, "scope"),
        (7, "symbol"),
        (7, "package_status"),
        (6, "modified_files"),
        (6, "patch_ids"),
        (6, "modules"),
        (6, "keywords"),
        (6, "problem_summary"),
        (6, "payload"),
        (6, "system_properties"),
        (6, "settings_keys"),
        (5, "risk_areas"),
        (5, "symbols"),
        (5, "strings"),
        (5, "framework_log_keys"),
        (4, "overview"),
        (4, "items"),
        (3, "project"),
        (3, "original_patch_name"),
        (3, "id"),
        (3, "case_id"),
        (3, "variant_id"),
        (2, "author"),
        (2, "status"),
        (2, "result"),
        (2, "package_kind"),
        (2, "evidence_kind"),
        (2, "note"),
        (1, "patch_files"),
        (1, "report_path"),
        (1, "path"),
    ]
    full_text = row_text(row).lower()
    score = 0
    matched: list[str] = []
    for term in terms:
        if term not in full_text:
            continue
        matched.append(term)
        score += 1
        for weight, field in weighted_fields:
            if term in stringify(row.get(field)).lower():
                score += weight
    return score, matched


def result_priority(row: dict[str, Any]) -> int:
    priority = 0
    try:
        priority += int(row.get("source_priority") or 0)
    except (TypeError, ValueError):
        pass
    status = str(row.get("package_status") or row.get("status") or "").lower()
    priority += {
        "validated": 50,
        "candidate": 30,
        "draft": 20,
        "failed": 10,
        "blocked": 5,
    }.get(status, 0)
    verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
    if str(verification.get("status", "")).lower() in {"pass", "passed"}:
        priority += 20
    return priority


def search(rows: list[dict[str, Any]], q: str, result_type: str, limit: int, include_synthetic: bool) -> list[dict[str, Any]]:
    terms = query_terms(q)
    results: list[dict[str, Any]] = []
    kind_filter = "" if result_type == "all" else result_type
    for row in rows:
        if result_type == "all" and not is_default_ai_result(row):
            continue
        if kind_filter and row.get("kind") != kind_filter:
            continue
        if not include_synthetic and bool(row.get("synthetic_data")):
            continue
        score, matched = score_row(row, terms)
        if score <= 0:
            continue
        normalized = dict(row)
        normalized["_score"] = score
        normalized["_matched_terms"] = matched
        results.append(normalized)
    results.sort(
        key=lambda item: (
            int(item.get("_score", 0)),
            result_priority(item),
            result_date(item),
            str(item.get("id") or item.get("case_id") or item.get("variant_id") or item.get("patch_id") or ""),
        ),
        reverse=True,
    )
    return results[:limit]


def is_default_ai_result(row: dict[str, Any]) -> bool:
    kind = str(row.get("kind") or "")
    if kind in AI_DEFAULT_RESULT_KINDS:
        return True
    if kind == "evidence":
        return str(row.get("evidence_kind") or "") in AI_EVIDENCE_KINDS
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search the Codex team knowledge repository.")
    parser.add_argument("query", nargs="*", help="Search terms. Use spaces to combine feature words, files, symbols, or project names.")
    parser.add_argument(
        "--merge-confirmation",
        choices=["list", "detail", "target", "compare", "analyze", "dispute"],
        help="Read or explicitly dispute member merge confirmations instead of running knowledge search.",
    )
    parser.add_argument("--merge-confirmation-id", help="review_id or package_key for merge confirmation detail, target, compare, analyze, or dispute.")
    parser.add_argument("--send-dispute", action="store_true", help="Actually POST a member merge dispute. Required with --merge-confirmation dispute.")
    parser.add_argument("--dispute-reason", default="", help="Human reason for a merge dispute. Only sent with --send-dispute.")
    parser.add_argument("--member-assessment", default="", help="Member/Codex assessment for a merge dispute. Only sent with --send-dispute.")
    parser.add_argument("--evidence-ref", action="append", default=[], help="Evidence reference to include when explicitly sending a merge dispute. Repeatable.")
    parser.add_argument("--root", help="Knowledge repository worktree path.")
    parser.add_argument("--type", choices=["all", "case", "variant", "patch", "report", "symbol", "event", "evidence"], default="all", help="Result type filter.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum result count.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--refresh", action="store_true", help="Run git pull --ff-only first when root is a clean Git worktree.")
    parser.add_argument("--include-synthetic", action="store_true", help="Include synthetic test data.")
    parser.add_argument("--no-record-usage", action="store_true", help="Do not write member-side search usage evidence.")
    parser.add_argument("--source", choices=["auto", "server", "local"], default="auto", help="Search source: auto prefers server hybrid search, server forbids fallback, local uses JSONL only.")
    parser.add_argument("--server-timeout", type=float, default=3.0, help="Server hybrid search timeout in seconds.")
    parser.add_argument("--reuse-decision", choices=REUSE_DECISIONS, help="Member-side use decision for this search.")
    parser.add_argument("--reuse-target", action="append", default=[], help="Matched case, variant, patch, or evidence id considered by this search. Repeatable.")
    parser.add_argument("--reuse-match", action="append", default=[], help="Why the matched knowledge may apply. Repeatable.")
    parser.add_argument("--reuse-mismatch", action="append", default=[], help="Why the matched knowledge may not directly apply. Repeatable.")
    parser.add_argument("--reuse-reason", default="", help="Reason for the reuse/adapt/reference/not-applicable decision.")
    parser.add_argument("--reuse-outcome", choices=REUSE_OUTCOMES, help="Outcome observed later for this search decision.")
    return parser


def handle_merge_confirmation_command(args: argparse.Namespace) -> int:
    action = args.merge_confirmation
    identifier = (args.merge_confirmation_id or " ".join(args.query)).strip()
    if action != "list" and not identifier:
        raise SystemExit("--merge-confirmation-id is required for this merge confirmation action")
    try:
        if action == "list":
            payload = fetch_merge_confirmation_payload(timeout=args.server_timeout)
            output = payload if args.json else format_merge_list(payload)
        elif action in {"detail", "target", "compare"}:
            endpoint_action = "" if action == "detail" else action
            payload = fetch_merge_confirmation_payload(identifier, endpoint_action, timeout=args.server_timeout)
            output = payload if args.json else format_merge_payload(f"合并确认 {action}", payload)
        elif action == "analyze":
            detail = fetch_merge_confirmation_payload(identifier, timeout=args.server_timeout)
            target = fetch_merge_confirmation_payload(identifier, "target", timeout=args.server_timeout)
            compare = fetch_merge_confirmation_payload(identifier, "compare", timeout=args.server_timeout)
            analysis = build_merge_analysis(detail, target, compare)
            output = analysis if args.json else format_merge_analysis(analysis)
        elif action == "dispute":
            if not args.send_dispute:
                raise SystemExit("--merge-confirmation dispute is read-only unless --send-dispute is also set")
            reason = args.dispute_reason.strip()
            assessment = args.member_assessment.strip()
            if not reason and not assessment:
                raise SystemExit("--dispute-reason or --member-assessment is required when sending a dispute")
            result = post_merge_dispute(
                identifier,
                reason=reason,
                member_assessment=assessment,
                evidence_refs=args.evidence_ref,
                agent_notes={"submitted_by": "android_knowledge_search.py"},
                timeout=args.server_timeout,
            )
            output = result if args.json else format_merge_payload("合并异议发送结果", result)
        else:
            raise SystemExit(f"unsupported merge confirmation action: {action}")
    except Exception as exc:
        raise SystemExit(merge_api_error(exc))

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(output)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.merge_confirmation:
        return handle_merge_confirmation_command(args)

    query = " ".join(args.query).strip()
    root: Path | None = None
    refresh_status = None
    fallback_reason = ""
    source = "server_hybrid"
    search_mode = "hybrid"
    results: list[dict[str, Any]] = []

    if should_try_server(args):
        try:
            results, server_payload = fetch_server_hybrid_results(args, query)
            search_mode = str(server_payload.get("search_mode") or "hybrid")
        except Exception as exc:
            fallback_reason = server_fallback_reason(exc)
            if args.source == "server":
                raise SystemExit(fallback_reason)
            source = "local_jsonl_fallback"
            search_mode = "local_jsonl"
    else:
        source = "local_jsonl_fallback"
        search_mode = "local_jsonl"

    if source == "local_jsonl_fallback":
        root = find_root(args.root)
        refresh_status = refresh_root(root) if args.refresh else None
        rows = load_rows(root, include_archive=args.type in {"report", "event", "evidence"})
        results = search(rows, query, args.type, max(args.limit, 1), args.include_synthetic)
        for item in results:
            item["source"] = "local_jsonl_fallback"
            item["search_mode"] = "local_jsonl"

    record_search_usage(args, root, query, results, source=source, search_mode=search_mode, fallback_reason=fallback_reason)

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root) if root else "",
                    "query": query,
                    "type": args.type,
                    "source": source,
                    "search_mode": search_mode,
                    "fallback_reason": fallback_reason,
                    "count": len(results),
                    "refresh": refresh_status,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            format_markdown(
                root,
                query,
                results,
                refresh_status,
                source=source,
                search_mode=search_mode,
                fallback_reason=fallback_reason,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
