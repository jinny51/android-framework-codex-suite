#!/usr/bin/env python3
"""Exec the canonical remote-snapshot entry without changing behavior."""

from __future__ import annotations

import os
import sys
from pathlib import Path


TARGET = (
    Path(__file__).resolve().parents[2]
    / "android-patch-capture"
    / "scripts"
    / "capture_remote_snapshot.py"
)


def main() -> int:
    if not TARGET.is_file():
        print(f"ANDROID_PATCH_CAPTURE_REQUIRED: {TARGET}", file=sys.stderr)
        return 2
    os.execv(sys.executable, [sys.executable, str(TARGET), *sys.argv[1:]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
