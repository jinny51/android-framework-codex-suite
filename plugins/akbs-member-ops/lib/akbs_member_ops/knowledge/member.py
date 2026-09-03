"""Shared member identity boundary for knowledge HTTP clients."""

from __future__ import annotations

from akbs_member_ops.knowledge_search.config import selected_member_alias


def require_member_alias() -> str:
    _profile, member_alias = selected_member_alias()
    if not member_alias or member_alias == "unknown":
        raise ValueError("member_alias is required before a member API request")
    return member_alias
