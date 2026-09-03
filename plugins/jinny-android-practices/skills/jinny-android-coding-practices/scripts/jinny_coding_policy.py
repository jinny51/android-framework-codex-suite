#!/usr/bin/env python3
"""Emit one decision-only Jinny coding recommendation document."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
DECISION_HELPER = PLUGIN_ROOT / "lib/jinny_android_practices/decision.py"
DECISION_HELPER_SHA256 = "a258f92fb138b87d673b66fca48ef43789fe9a0992f48ab69fd62b24bd78933c"


LAYERS = ("application", "platform", "native", "hal", "kernel", "device", "build")


def _decision_helpers() -> tuple[Callable[[str], dict[str, str]], Callable[..., str]]:
    """Load only the exact helper bytes bound by this hash-bound entrypoint."""
    try:
        raw = DECISION_HELPER.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"Jinny decision helper is unavailable: {DECISION_HELPER}") from exc
    if hashlib.sha256(raw).hexdigest() != DECISION_HELPER_SHA256:
        raise RuntimeError("Jinny decision helper SHA-256 differs")
    namespace: dict[str, Any] = {
        "__file__": str(DECISION_HELPER),
        "__name__": "_jinny_android_practices_decision",
    }
    exec(compile(raw, str(DECISION_HELPER), "exec"), namespace)
    return namespace["provider_binding"], namespace["require_sha256"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Return a Jinny coding policy decision.")
    parser.add_argument("--decision-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stage-id", required=True)
    parser.add_argument("--context-sha256", required=True)
    parser.add_argument("--core-policy-sha256", required=True)
    parser.add_argument("--component-layer", required=True, choices=LAYERS)
    parser.add_argument("--path-pattern", action="append", default=[])
    parser.add_argument("--language", action="append", default=[])
    parser.add_argument("--member-alias", default="")
    parser.add_argument("--legacy-jinny-style", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        provider_binding, require_sha256 = _decision_helpers()
        context_sha = require_sha256(args.context_sha256, field="context_sha256")
        core_sha = require_sha256(args.core_policy_sha256, field="core_policy_sha256")
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    statement = "Prefer clear, locally consistent helper and type names during implementation and review."
    if args.legacy_jinny_style:
        if not args.member_alias.strip():
            print("--legacy-jinny-style requires a controller-resolved member alias", file=sys.stderr)
            return 2
        statement = (
            "For newly introduced helpers only, prefer the explicitly resolved member-alias "
            "suffix and group multiple same-package helpers in an alias-derived Utils type when "
            "that remains consistent with project and core rules."
        )
    decision = {
        "schema": "coding-policy-decision-v1",
        "decision_id": args.decision_id,
        "run_id": args.run_id,
        "stage_id": args.stage_id,
        "context_sha256": context_sha,
        "core_policy_sha256": core_sha,
        "provider": provider_binding("coding"),
        "outcome": {
            "type": "applied",
            "rules": [
                {
                    "rule_id": "jinny-optional-naming-v1",
                    "effect": "recommend",
                    "statement": statement,
                    "scope": {
                        "component_layers": [args.component_layer],
                        "path_patterns": args.path_pattern or ["**/*"],
                        "languages": args.language or ["java", "kotlin", "cpp"],
                    },
                    "evidence_requirements": ["core-policy-remains-effective"],
                }
            ],
        },
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    print(json.dumps(decision, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
