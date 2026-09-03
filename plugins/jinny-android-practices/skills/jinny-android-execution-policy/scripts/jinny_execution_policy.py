#!/usr/bin/env python3
"""Emit a bounded Jinny execution policy decision; never dispatch work."""

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


TASK_CLASSES = ("analysis", "diagnosis", "implementation", "review", "verification", "bounded_operation")
EFFECTS = ("read_only", "workspace_mutation", "controlled_operation")
EFFECT_ORDER = {name: index for index, name in enumerate(EFFECTS)}


def _decision_helpers() -> tuple[
    Callable[[str], dict[str, str]],
    Callable[[], tuple[dict[str, Any], str]],
    Callable[..., str],
]:
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
    return (
        namespace["provider_binding"],
        namespace["provider_manifest"],
        namespace["require_sha256"],
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Return a Jinny execution policy decision.")
    parser.add_argument("--decision-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stage-id", required=True)
    parser.add_argument("--context-sha256", required=True)
    parser.add_argument("--task-class", required=True, choices=TASK_CLASSES)
    parser.add_argument("--requested-effect", required=True, choices=EFFECTS)
    parser.add_argument(
        "--rollout-effect-ceiling",
        choices=EFFECTS,
        default="read_only",
        help="Controller-owned rollout ceiling. Phase 2 defaults to read_only.",
    )
    parser.add_argument("--risk-level", choices=("low", "medium", "high"), default="medium")
    parser.add_argument("--shape", choices=("narrow", "normal", "architecture"), default="normal")
    parser.add_argument(
        "--ambiguity",
        choices=("low", "medium", "high"),
        default="medium",
        help="Controller assessment of ambiguity in the bounded task.",
    )
    parser.add_argument(
        "--code-judgment",
        choices=("none", "ordinary", "architecture"),
        default="ordinary",
        help="Whether the task needs no, ordinary, or architecture-level code judgment.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        provider_binding, provider_manifest, require_sha256 = _decision_helpers()
        context_sha = require_sha256(args.context_sha256, field="context_sha256")
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    provider, _ = provider_manifest()
    profiles = provider["capabilities"]["execution"]["worker_profiles"]
    high_judgment = (
        args.risk_level == "high"
        or args.shape == "architecture"
        or args.ambiguity == "high"
        or args.code_judgment == "architecture"
    )
    narrow_mechanical = (
        args.shape == "narrow"
        and args.ambiguity == "low"
        and args.code_judgment == "none"
        and args.requested_effect == "read_only"
    )
    if args.task_class in {"verification", "bounded_operation"}:
        profile_id = "luna-verification-operation"
        route_reason = "verification-or-bounded-operation"
    elif args.task_class == "review" or high_judgment:
        profile_id = "sol-analysis-review"
        route_reason = "architecture-high-risk-or-final-review"
    elif args.task_class in {"analysis", "diagnosis"} and narrow_mechanical:
        profile_id = "luna-verification-operation"
        route_reason = "explicit-repeated-or-narrow-extraction"
    else:
        profile_id = "terra-implementation"
        route_reason = (
            "workspace-bounded-implementation"
            if args.task_class == "implementation"
            else "source-exploration-log-diagnosis-or-ordinary-solution"
        )
    profile = profiles.get(profile_id)
    reason_codes: list[str] = []
    if not isinstance(profile, dict) or args.task_class not in profile.get("task_classes", []):
        reason_codes.append("declared-worker-profile-mismatch")
    elif EFFECT_ORDER[args.requested_effect] > EFFECT_ORDER[profile["effect_ceiling"]]:
        reason_codes.append("worker-profile-effect-ceiling-exceeded")
    if EFFECT_ORDER[args.requested_effect] > EFFECT_ORDER[args.rollout_effect_ceiling]:
        reason_codes.append("rollout-effect-ceiling-exceeded")
    if reason_codes:
        outcome = {"type": "blocked", "reason_codes": reason_codes}
    else:
        outcome = {
            "type": "delegate",
            "worker_profile_id": profile_id,
            "task_class": args.task_class,
            "requested_effect": args.requested_effect,
            "reason_codes": [route_reason],
            "independent_review_requested": args.task_class == "review",
        }
    decision = {
        "schema": "execution-policy-decision-v1",
        "decision_id": args.decision_id,
        "run_id": args.run_id,
        "stage_id": args.stage_id,
        "context_sha256": context_sha,
        "provider": provider_binding("execution"),
        "outcome": outcome,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    print(json.dumps(decision, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
