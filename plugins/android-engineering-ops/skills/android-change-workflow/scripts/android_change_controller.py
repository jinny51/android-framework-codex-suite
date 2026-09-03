#!/usr/bin/env python3
"""Generate and validate installed android-change-workflow controller records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_LIB = PLUGIN_ROOT / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from android_engineering_ops.practices.schema import (  # noqa: E402
    ContractValidationError,
    load_json,
)
from android_engineering_ops.workflow import (  # noqa: E402
    ControllerValidationError,
    canonical_json_sha256,
    generate_stage_snapshot,
    generate_worker_assignment,
    generate_worker_result,
    stage_context_sha256,
    validate_stage_snapshot,
    validate_worker_assignment,
    validate_worker_result,
)


def _document(path: str, *, label: str) -> dict[str, Any]:
    value = load_json(Path(path))
    if not isinstance(value, dict):
        raise ControllerValidationError(f"{label} must be a JSON object")
    return value


def _rows(path: str, *, label: str) -> list[dict[str, Any]]:
    value = load_json(Path(path))
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ControllerValidationError(f"{label} must be a JSON array of objects")
    return value


def _expectations(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-stage-id", required=True)
    parser.add_argument("--expected-context-sha256", required=True)
    parser.add_argument("--expected-provider-resolution", required=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seal or validate Android change controller records."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("generate-stage", "generate-assignment", "generate-result"):
        current = commands.add_parser(name)
        current.add_argument("--input", required=True)
    for name in ("hash", "context-hash"):
        current = commands.add_parser(name)
        current.add_argument("--document", required=True)
    stage = commands.add_parser("validate-stage")
    stage.add_argument("--document", required=True)
    _expectations(stage)
    assignment = commands.add_parser("validate-assignment")
    assignment.add_argument("--document", required=True)
    assignment.add_argument("--snapshot", required=True)
    assignment.add_argument("--expected-worker-task-id", required=True)
    _expectations(assignment)
    result = commands.add_parser("validate-result")
    result.add_argument("--document", required=True)
    result.add_argument("--assignment", required=True)
    result.add_argument("--snapshot", required=True)
    result.add_argument("--expected-worker-task-id", required=True)
    result.add_argument("--expected-end-heads", required=True)
    result.add_argument("--expected-changes", required=True)
    result.add_argument("--expected-evidence", required=True)
    result.add_argument("--expected-checks", required=True)
    result.add_argument("--expected-commands", required=True)
    _expectations(result)
    return parser.parse_args(argv)


def _expected(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "expected_run_id": args.expected_run_id,
        "expected_stage_id": args.expected_stage_id,
        "expected_context_sha256": args.expected_context_sha256,
        "expected_provider_resolution": _document(
            args.expected_provider_resolution, label="expected provider resolution"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command.startswith("generate-"):
            payload = _document(args.input, label="generation payload")
            generators = {
                "generate-stage": generate_stage_snapshot,
                "generate-assignment": generate_worker_assignment,
                "generate-result": generate_worker_result,
            }
            output = generators[args.command](payload)
            print(json.dumps(output, ensure_ascii=False, sort_keys=True))
            return 0
        document = _document(args.document, label="workflow document")
        if args.command == "hash":
            print(canonical_json_sha256(document))
            return 0
        if args.command == "context-hash":
            print(stage_context_sha256(document))
            return 0
        expected = _expected(args)
        if args.command == "validate-stage":
            validate_stage_snapshot(document, **expected)
        elif args.command == "validate-assignment":
            validate_worker_assignment(
                document,
                source_snapshot=_document(args.snapshot, label="stage snapshot"),
                expected_worker_task_id=args.expected_worker_task_id,
                **expected,
            )
        else:
            validate_worker_result(
                document,
                assignment=_document(args.assignment, label="worker assignment"),
                source_snapshot=_document(args.snapshot, label="stage snapshot"),
                expected_worker_task_id=args.expected_worker_task_id,
                expected_end_heads=_document(
                    args.expected_end_heads, label="expected end-head readback"
                ),
                expected_changes=_rows(
                    args.expected_changes, label="expected change readback"
                ),
                expected_evidence=_rows(
                    args.expected_evidence, label="expected evidence readback"
                ),
                expected_checks=_rows(
                    args.expected_checks, label="expected check receipts"
                ),
                expected_commands=_rows(
                    args.expected_commands, label="expected command receipts"
                ),
                **expected,
            )
        print(json.dumps({"status": "valid", "schema": document.get("schema")}, sort_keys=True))
        return 0
    except (ControllerValidationError, ContractValidationError, OSError) as exc:
        print(f"ANDROID_CHANGE_CONTROLLER_INVALID: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
