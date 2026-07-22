from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .history import ThreadRow


@dataclass(frozen=True)
class CleanupSelectionPlan:
    all_rows: tuple[ThreadRow, ...]
    parent_by_child: dict[str, str]
    keep_ids: frozenset[str]
    keep_ids_by_db: dict[Path, frozenset[str]]
    selected_by_db: dict[Path, tuple[ThreadRow, ...]]
    selected: tuple[ThreadRow, ...]


def validate_id_selectors(rows: Sequence[ThreadRow], args: Any) -> None:
    if not args.ids or args.allow_ambiguous_ids:
        return
    for term in args.ids:
        lowered = term.lower()
        matches = [row for row in rows if row.id.lower() == lowered or row.id.lower().startswith(lowered)]
        if len(matches) != 1:
            raise SystemExit(
                f"--ids term {term!r} matched {len(matches)} threads. Use a longer prefix or --allow-ambiguous-ids."
            )


def resolve_id_terms(
    rows: Sequence[ThreadRow],
    terms: Sequence[str],
    *,
    allow_ambiguous_ids: bool = False,
    allow_missing_full_ids: bool = False,
) -> set[str]:
    resolved: set[str] = set()
    for term in terms:
        lowered = term.lower()
        matches = [row.id for row in rows if row.id.lower() == lowered or row.id.lower().startswith(lowered)]
        if not matches:
            if allow_missing_full_ids and re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                lowered,
                re.IGNORECASE,
            ):
                resolved.add(term)
                continue
            raise SystemExit(f"--keep-ids term {term!r} matched 0 threads. Use a full visible thread ID.")
        if len(matches) > 1 and not allow_ambiguous_ids:
            raise SystemExit(
                f"--keep-ids term {term!r} matched {len(matches)} threads. Use a longer prefix or --allow-ambiguous-ids."
            )
        resolved.update(matches)
    return resolved


def expand_keep_ids_with_spawn_children(
    keep_ids: set[str],
    spawn_edges: Sequence[tuple[str, str]],
) -> set[str]:
    expanded = set(keep_ids)
    changed = True
    while changed:
        changed = False
        for parent, child in spawn_edges:
            if parent in expanded and child not in expanded:
                expanded.add(child)
                changed = True
    return expanded


def spawn_parent_map(
    spawn_edges_by_db: Mapping[Path, Sequence[tuple[str, str]]],
) -> dict[str, str]:
    parents: dict[str, str] = {}
    for edges in spawn_edges_by_db.values():
        for parent, child in edges:
            parents.setdefault(child, parent)
    return parents


def select_threads(
    rows: Sequence[ThreadRow],
    args: Any,
    keep_ids: set[str] | frozenset[str] | None = None,
) -> list[ThreadRow]:
    if args.delete_not_in_keep:
        keep = keep_ids or set()
        return [row for row in rows if row.id not in keep]

    selected: list[ThreadRow] = []
    id_terms = [term.lower() for term in args.ids]
    title_terms = [term.lower() for term in args.title_contains]
    current_id = (args.current_thread_id or "").lower()

    for row in rows:
        row_id = row.id.lower()
        title = row.title.lower()
        match = False
        if args.all_archived and row.archived:
            match = True
        if args.all_except_current and row_id != current_id:
            match = True
        if id_terms and any(row_id.startswith(term) or row_id == term for term in id_terms):
            match = True
        if title_terms and any(term in title for term in title_terms):
            match = True
        if match:
            selected.append(row)
    return selected


def build_selection_plan(
    db_rows: Mapping[Path, Sequence[ThreadRow]],
    spawn_edges_by_db: Mapping[Path, Sequence[tuple[str, str]]],
    args: Any,
) -> CleanupSelectionPlan:
    all_rows = tuple(row for rows in db_rows.values() for row in rows)
    validate_id_selectors(all_rows, args)

    keep_ids_all: set[str] = set()
    keep_ids_by_db: dict[Path, frozenset[str]] = {}
    if args.delete_not_in_keep:
        base_keep_ids = resolve_id_terms(
            all_rows,
            args.keep_ids,
            allow_ambiguous_ids=args.allow_ambiguous_ids,
            allow_missing_full_ids=True,
        )
        keep_ids_all.update(base_keep_ids)
        for db_path in db_rows:
            keep_ids = set(base_keep_ids)
            if not args.no_keep_spawn_children:
                keep_ids = expand_keep_ids_with_spawn_children(
                    keep_ids,
                    spawn_edges_by_db.get(db_path, ()),
                )
            frozen_keep_ids = frozenset(keep_ids)
            keep_ids_by_db[db_path] = frozen_keep_ids
            keep_ids_all.update(frozen_keep_ids)

    selected_by_db: dict[Path, tuple[ThreadRow, ...]] = {}
    selected_all: list[ThreadRow] = []
    for db_path, rows in db_rows.items():
        selected = tuple(select_threads(rows, args, keep_ids_by_db.get(db_path)))
        selected_by_db[db_path] = selected
        selected_all.extend(selected)

    return CleanupSelectionPlan(
        all_rows=all_rows,
        parent_by_child=spawn_parent_map(spawn_edges_by_db),
        keep_ids=frozenset(keep_ids_all),
        keep_ids_by_db=keep_ids_by_db,
        selected_by_db=selected_by_db,
        selected=tuple(selected_all),
    )
