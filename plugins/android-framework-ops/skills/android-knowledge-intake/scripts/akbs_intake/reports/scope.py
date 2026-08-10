from __future__ import annotations

from typing import Any


ALLOWED_WORK_TYPES = {"Patch", "App"}


def clean_scope_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def report_scope_key(row: dict[str, Any]) -> tuple[str, str, str]:
    work_type = clean_scope_text(row.get("work_type"))
    app_name = clean_scope_text(row.get("app_name")).casefold() if work_type == "App" else ""
    return clean_scope_text(row.get("project")).upper(), work_type, app_name


def report_scope_suffix(row: dict[str, Any]) -> str:
    if clean_scope_text(row.get("work_type")) == "App":
        return f"App：{clean_scope_text(row.get('app_name')) or '需成员确认'}"
    return clean_scope_text(row.get("work_type")) or "需成员确认"
