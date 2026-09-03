#!/usr/bin/env python3
"""Deprecated wrapper for akbs-daily-report."""

from __future__ import annotations

import sys
from pathlib import Path


TARGET_SCRIPTS = Path(__file__).resolve().parents[2] / "akbs-daily-report" / "scripts"
if str(TARGET_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TARGET_SCRIPTS))

from akbs_daily_report import main as target_main  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    print("DEPRECATED: android-daily-report-intake; use akbs-daily-report.", file=sys.stderr)
    return target_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
