#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT_MARKERS = (
    Path("index") / "knowledge.sqlite",
    Path("index") / "patch-index.jsonl",
    Path("index") / "report-index.jsonl",
    Path("index") / "symbol-index.jsonl",
)


def expand_path(value: str | os.PathLike[str]) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(value)))).resolve()


def codex_home() -> Path:
    return expand_path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def is_knowledge_root(path: Path) -> bool:
    return path.is_dir() and any((path / marker).exists() for marker in ROOT_MARKERS)


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

    try:
        candidates.extend(parent_candidates(Path.cwd().resolve()))
    except OSError:
        pass

    home = codex_home()
    documents = Path("/mnt/c/Users/jinny/Documents/Codex")
    candidates.extend(
        [
            documents / "worktrees" / "knowledge-jinny",
            documents / "worktrees" / "knowledge",
            documents / "worktrees" / "knowledge-test",
            home / "knowledge",
            Path("/mnt/z/knowledge/worktree"),
            Path("/mnt/z/knowledge"),
            Path("/home/test35/work/knowledge/worktree"),
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
        "knowledge root not found. Pass --root <path> or set CODEX_KNOWLEDGE_ROOT. Checked:\n"
        + "\n".join(f" - {item}" for item in checked[:16])
    )


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


def parse_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


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


def sqlite_tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def evidence_row(item: dict[str, Any]) -> dict[str, Any]:
    row = dict(item)
    row["evidence_kind"] = row.pop("kind", "")
    row["payload"] = parse_json(row.get("payload"), {})
    row["kind"] = "evidence"
    return row


def load_from_sqlite(root: Path) -> list[dict[str, Any]]:
    db_path = root / "index" / "knowledge.sqlite"
    if not db_path.exists():
        return []
    tables = sqlite_tables(db_path)
    rows: list[dict[str, Any]] = []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if "patches" in tables:
            for item in conn.execute("SELECT * FROM patches"):
                row = dict(item)
                for key in (
                    "patch_files",
                    "modified_files",
                    "deleted_files",
                    "framework_log_keys",
                    "system_properties",
                    "settings_keys",
                    "strings",
                    "keywords",
                    "filename_parse_confidence",
                ):
                    row[key] = parse_json(row.get(key), [])
                rows.append({"kind": "patch", **row})

        if "reports" in tables:
            item_map: dict[str, list[dict[str, Any]]] = {}
            if "report_items" in tables:
                for item in conn.execute("SELECT * FROM report_items ORDER BY report_id, item_order"):
                    item_map.setdefault(item["report_id"], []).append(dict(item))
            for item in conn.execute("SELECT * FROM reports"):
                row = dict(item)
                row["items"] = item_map.get(row.get("id", ""), [])
                rows.append({"kind": "report", **row})

        if "symbols" in tables:
            for item in conn.execute("SELECT * FROM symbols"):
                rows.append({"kind": "symbol", **dict(item)})

        if "knowledge_events" in tables:
            for item in conn.execute("SELECT * FROM knowledge_events"):
                row = dict(item)
                row["payload"] = parse_json(row.get("payload"), {})
                rows.append({"kind": "event", **row})

        if "evidence" in tables:
            for item in conn.execute("SELECT * FROM evidence"):
                rows.append(evidence_row(dict(item)))
    finally:
        conn.close()
    return rows


def load_from_jsonl(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in read_jsonl(root / "index" / "patch-index.jsonl"):
        rows.append({"kind": "patch", **item})
    for item in read_jsonl(root / "index" / "report-index.jsonl"):
        rows.append({"kind": "report", **item})
    for item in read_jsonl(root / "index" / "symbol-index.jsonl"):
        rows.append({"kind": "symbol", **item})
    for item in read_jsonl(root / "index" / "knowledge-event-index.jsonl"):
        rows.append({"kind": "event", **item})
    for item in read_jsonl(root / "index" / "evidence-index.jsonl"):
        rows.append(evidence_row(item))
    return rows


def load_rows(root: Path) -> list[dict[str, Any]]:
    rows = load_from_sqlite(root)
    return rows if rows else load_from_jsonl(root)


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
        "title",
        "summary",
        "overview",
        "author",
        "project",
        "scope",
        "platform",
        "android_version",
        "repo_path",
        "feature_slug",
        "original_patch_name",
        "filename_quality",
        "module",
        "status",
        "quality",
        "channel",
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
        "framework_log_keys",
        "system_properties",
        "settings_keys",
        "strings",
        "keywords",
        "symbol",
        "path",
        "patch_id",
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
        (8, "feature_slug"),
        (8, "repo_path"),
        (8, "summary"),
        (7, "scope"),
        (7, "symbol"),
        (7, "quality"),
        (6, "modified_files"),
        (6, "payload"),
        (6, "system_properties"),
        (6, "settings_keys"),
        (5, "strings"),
        (5, "framework_log_keys"),
        (4, "overview"),
        (4, "items"),
        (3, "project"),
        (3, "original_patch_name"),
        (3, "id"),
        (2, "author"),
        (2, "status"),
        (2, "result"),
        (2, "channel"),
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


def result_date(row: dict[str, Any]) -> str:
    return str(row.get("date") or row.get("week_range") or "")


def search(rows: list[dict[str, Any]], q: str, result_type: str, limit: int, include_synthetic: bool) -> list[dict[str, Any]]:
    terms = query_terms(q)
    results: list[dict[str, Any]] = []
    kind_filter = "" if result_type == "all" else result_type
    for row in rows:
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
    results.sort(key=lambda item: (int(item.get("_score", 0)), result_date(item), str(item.get("id") or item.get("patch_id") or "")), reverse=True)
    return results[:limit]


def rel_or_empty(root: Path, value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    if text.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", text):
        return text
    return str(root / text)


def compact_list(value: Any, limit: int = 4) -> str:
    items = parse_json(value, value)
    if not isinstance(items, list):
        items = [items] if items else []
    text_items = [str(item) for item in items if str(item)]
    if len(text_items) > limit:
        return ", ".join(text_items[:limit]) + f" ... (+{len(text_items) - limit})"
    return ", ".join(text_items)


def format_patch(root: Path, row: dict[str, Any], index: int) -> str:
    title = row.get("title") or row.get("summary") or row.get("id") or "(untitled patch)"
    lines = [
        f"{index}. [patch] {title}",
        f"   - id: {row.get('id', '')}",
        f"   - author/date/status: {row.get('author', '')} / {result_date(row)} / {row.get('status', '') or 'unknown'}",
    ]
    if row.get("project"):
        lines.append(f"   - project: {row.get('project')}")
    if row.get("scope") or row.get("repo_path") or row.get("feature_slug"):
        lines.append(
            "   - scope/repo/feature: "
            f"{row.get('scope') or 'unknown'} / {row.get('repo_path') or 'unknown'} / {row.get('feature_slug') or 'unknown'}"
        )
    if row.get("filename_quality") or row.get("original_patch_name"):
        lines.append(f"   - filename: {row.get('filename_quality') or 'unknown'} / {row.get('original_patch_name') or ''}")
    if row.get("summary") and row.get("summary") != title:
        lines.append(f"   - summary: {row.get('summary')}")
    if row.get("modified_files"):
        lines.append(f"   - modified_files: {compact_list(row.get('modified_files'))}")
    symbols = compact_list(
        [
            *parse_json(row.get("system_properties"), []),
            *parse_json(row.get("settings_keys"), []),
            *parse_json(row.get("strings"), []),
            *parse_json(row.get("framework_log_keys"), []),
        ]
    )
    if symbols:
        lines.append(f"   - symbols: {symbols}")
    if row.get("readme"):
        lines.append(f"   - readme: {rel_or_empty(root, row.get('readme'))}")
    if row.get("patch_files"):
        patch_files = parse_json(row.get("patch_files"), [])
        if patch_files:
            lines.append(f"   - patch: {rel_or_empty(root, patch_files[0])}")
    if row.get("_matched_terms"):
        lines.append(f"   - matched: {', '.join(row.get('_matched_terms', []))}")
    return "\n".join(lines)


def format_report(root: Path, row: dict[str, Any], index: int) -> str:
    title = row.get("overview") or row.get("id") or "(report)"
    lines = [
        f"{index}. [report] {title}",
        f"   - id: {row.get('id', '')}",
        f"   - type/author/date: {row.get('type', '')} / {row.get('author', '')} / {result_date(row)}",
    ]
    items = row.get("items") or []
    if isinstance(items, list) and items:
        sample = []
        for item in items[:3]:
            sample.append(f"{item.get('project', '')}:{item.get('title', '')}".strip(":"))
        lines.append(f"   - items: {', '.join(sample)}")
    if row.get("report_path"):
        lines.append(f"   - report: {rel_or_empty(root, row.get('report_path'))}")
    if row.get("_matched_terms"):
        lines.append(f"   - matched: {', '.join(row.get('_matched_terms', []))}")
    return "\n".join(lines)


def format_symbol(root: Path, row: dict[str, Any], index: int) -> str:
    lines = [
        f"{index}. [symbol] {row.get('symbol', '')}",
        f"   - type/patch/author: {row.get('type', '')} / {row.get('patch_id', '')} / {row.get('author', '')}",
    ]
    if row.get("path"):
        lines.append(f"   - path: {rel_or_empty(root, row.get('path'))}")
    if row.get("_matched_terms"):
        lines.append(f"   - matched: {', '.join(row.get('_matched_terms', []))}")
    return "\n".join(lines)


def format_event(root: Path, row: dict[str, Any], index: int) -> str:
    title = row.get("summary") or row.get("id") or "(knowledge event)"
    lines = [
        f"{index}. [event] {title}",
        f"   - id: {row.get('id', '')}",
        f"   - kind/channel/quality: {row.get('package_kind', '')} / {row.get('channel', '')} / {row.get('quality', '')}",
        f"   - member/date/platform: {row.get('member', '')} / {result_date(row)} / {row.get('platform', '')}",
    ]
    if row.get("project"):
        lines.append(f"   - project: {row.get('project')}")
    if row.get("path"):
        lines.append(f"   - event: {rel_or_empty(root, row.get('path'))}")
    if row.get("_matched_terms"):
        lines.append(f"   - matched: {', '.join(row.get('_matched_terms', []))}")
    return "\n".join(lines)


def format_evidence(root: Path, row: dict[str, Any], index: int) -> str:
    title = row.get("summary") or row.get("id") or "(evidence)"
    lines = [
        f"{index}. [evidence] {title}",
        f"   - id: {row.get('id', '')}",
        f"   - event/kind/result: {row.get('event_id', '')} / {row.get('evidence_kind', '')} / {row.get('result', '')}",
    ]
    if row.get("quality") or row.get("project") or row.get("platform"):
        lines.append(f"   - context: {row.get('quality', '')} / {row.get('project', '')} / {row.get('platform', '')}")
    if row.get("path"):
        lines.append(f"   - evidence: {rel_or_empty(root, row.get('path'))}")
    if row.get("_matched_terms"):
        lines.append(f"   - matched: {', '.join(row.get('_matched_terms', []))}")
    return "\n".join(lines)


def format_markdown(root: Path, q: str, results: list[dict[str, Any]], refresh_status: str | None) -> str:
    lines = [
        "# 知识库搜索结果",
        "",
        f"- root: {root}",
        f"- query: {q or '(empty)'}",
        f"- results: {len(results)}",
    ]
    if refresh_status:
        lines.append(f"- refresh: {refresh_status}")
    lines.append("")
    if not results:
        lines.append("未找到匹配结果。可以换用类名、文件路径、属性名、Settings key、资源 key 或项目名再搜。")
        return "\n".join(lines)

    for index, row in enumerate(results, start=1):
        kind = row.get("kind")
        if kind == "patch":
            lines.append(format_patch(root, row, index))
        elif kind == "report":
            lines.append(format_report(root, row, index))
        elif kind == "symbol":
            lines.append(format_symbol(root, row, index))
        elif kind == "event":
            lines.append(format_event(root, row, index))
        elif kind == "evidence":
            lines.append(format_evidence(root, row, index))
        else:
            lines.append(f"{index}. [{kind}] {row.get('id') or row.get('title') or row.get('symbol')}")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search the Codex team knowledge repository.")
    parser.add_argument("query", nargs="*", help="Search terms. Use spaces to combine feature words, files, symbols, or project names.")
    parser.add_argument("--root", help="Knowledge repository worktree path.")
    parser.add_argument("--type", choices=["all", "patch", "report", "symbol", "event", "evidence"], default="all", help="Result type filter.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum result count.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--refresh", action="store_true", help="Run git pull --ff-only first when root is a clean Git worktree.")
    parser.add_argument("--include-synthetic", action="store_true", help="Include synthetic test data.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    query = " ".join(args.query).strip()
    root = find_root(args.root)
    refresh_status = refresh_root(root) if args.refresh else None
    rows = load_rows(root)
    results = search(rows, query, args.type, max(args.limit, 1), args.include_synthetic)

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "query": query,
                    "type": args.type,
                    "count": len(results),
                    "refresh": refresh_status,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(format_markdown(root, query, results, refresh_status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
