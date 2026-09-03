#!/usr/bin/env python3
"""Print the explicit Android engineering extension resolution as JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_LIB = PLUGIN_ROOT / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from android_engineering_ops.practices import (  # noqa: E402
    ExtensionResolutionError,
    resolve_extension,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve an explicit Android practices provider.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--codex-home")
    parser.add_argument("--workflow-action", required=True)
    parser.add_argument(
        "--component-layer",
        required=True,
        choices=("application", "platform", "native", "hal", "kernel", "device", "build"),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        resolution = resolve_extension(
            project_root=Path(args.project_root),
            codex_home=Path(args.codex_home) if args.codex_home else None,
        )
        print(
            json.dumps(
                resolution.evidence(
                    workflow_action=args.workflow_action,
                    component_layer=args.component_layer,
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except ExtensionResolutionError as exc:
        print(f"ANDROID_PRACTICES_PROVIDER_INVALID: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
