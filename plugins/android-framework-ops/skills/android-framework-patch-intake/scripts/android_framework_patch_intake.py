#!/usr/bin/env python3
"""Framework patch incoming v1 entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]
for path in (
    PLUGIN_ROOT / "lib",
    SKILL_ROOT.parent / "android-knowledge-intake" / "scripts",
):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from android_engineering_ops.incoming_v1.cli import route_arguments  # noqa: E402
from android_knowledge_intake import main as legacy_intake_main  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    return legacy_intake_main(route_arguments("patch", arguments))


if __name__ == "__main__":
    raise SystemExit(main())
