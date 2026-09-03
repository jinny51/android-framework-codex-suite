#!/usr/bin/env python3
"""Deprecated wrapper for akbs-patch-submit."""

from __future__ import annotations

import sys
from pathlib import Path


TARGET_SCRIPTS = Path(__file__).resolve().parents[2] / "akbs-patch-submit" / "scripts"
if str(TARGET_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TARGET_SCRIPTS))

from akbs_patch_submit import main as target_main  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    print("DEPRECATED: android-framework-patch-intake; use akbs-patch-submit.", file=sys.stderr)
    return target_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
