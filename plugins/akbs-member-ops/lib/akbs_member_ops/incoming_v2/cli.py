"""Command-line surface for local Android change v2 handling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .capture_adapter import preflight_capture
from .validation import (
    AndroidChangeV2Error,
    check_package,
    prepare_package,
    read_package,
    writer_status,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="akbs_patch_submit.py android-change-v2",
        description=(
            "Read, strictly check, or byte-preserve an Android change v2 package, or "
            "preflight an android-patch-capture v2 package without materializing output. "
            "Adapter materialization and server submission remain fail-closed while their "
            "contracts are blocked."
        ),
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("read", "check", "prepare", "submit"):
        sub = subparsers.add_parser(action)
        sub.add_argument("package", type=Path, help="package directory or manifest.json")
    adapt = subparsers.add_parser(
        "adapt-capture",
        help="strictly preflight an android-patch-capture v2 package without writing output",
    )
    adapt.add_argument("capture", type=Path, help="capture package directory or manifest.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "read":
            result = read_package(args.package)
        elif args.action == "check":
            result = check_package(args.package)
        elif args.action == "prepare":
            result = prepare_package(args.package)
        elif args.action == "adapt-capture":
            result = preflight_capture(args.capture)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 1
        else:
            identity = read_package(args.package)
            result = {
                "status": "FAIL",
                "operation": "submit",
                "contract": identity["contract"],
                "source_package_key": identity["source_package_key"],
                "reason_code": "android_change_v2_writer_off",
                "message": (
                    "Android change v2 server writer is disabled by the bundled contract; "
                    "no network request, archive, receipt, or v1 fallback was attempted."
                ),
                "writer": writer_status(),
            }
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 1
    except AndroidChangeV2Error as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "operation": args.action,
                    "reason_code": (
                        "android_patch_capture_v2_invalid"
                        if args.action == "adapt-capture"
                        else "android_change_v2_payload_invalid"
                    ),
                    "message": str(exc),
                    "server_qualified": False,
                    "v1_fallback": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
