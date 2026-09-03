#!/usr/bin/env python3
"""Exec the canonical Android patch-capture CLI without changing behavior."""

from __future__ import annotations

import os
import sys
from pathlib import Path


TARGET = (
    Path(__file__).resolve().parents[2]
    / "android-patch-capture"
    / "scripts"
    / "capture_android_patch.py"
)


def main() -> int:
    if not TARGET.is_file():
        print(f"ANDROID_PATCH_CAPTURE_REQUIRED: {TARGET}", file=sys.stderr)
        return 2
    arguments = list(sys.argv[1:])
    if "--change-domain" not in arguments and "--component-layer" not in arguments:
        arguments.extend(["--change-domain", "framework"])
    os.execv(sys.executable, [sys.executable, str(TARGET), *arguments])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
