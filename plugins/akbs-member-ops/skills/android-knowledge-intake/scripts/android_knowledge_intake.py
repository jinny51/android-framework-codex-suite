#!/usr/bin/env python3
"""Deprecated compatibility router for the internal incoming v1 kernel."""

from __future__ import annotations

import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
for path in (PLUGIN_ROOT / "lib", PLUGIN_ROOT / "internal" / "incoming-v1" / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from akbs_member_intake import main as target_main  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    print(
        "DEPRECATED: android-knowledge-intake; use the matching canonical akbs-* business CLI.",
        file=sys.stderr,
    )
    return target_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
