from __future__ import annotations

from typing import Any

from android_framework_ops.knowledge_rules import parse_company_project


def project_inference_payload(
    project: str,
    basis: list[str],
    checked_sources: list[str],
    raw_inputs: list[str],
    limits: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "project": project,
        "recognized": project != "unknown",
        "basis": basis,
        "checked_sources": checked_sources,
        "raw_inputs": raw_inputs[:20],
        "limits": limits or [],
        "company_rule_match": False,
    }
    if project != "unknown":
        payload.update(parse_company_project(project))
    return payload
