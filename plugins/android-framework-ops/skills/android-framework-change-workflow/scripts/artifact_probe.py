#!/usr/bin/env python3
"""Locate common Android framework build artifacts under an out directory."""

from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_NAMES = [
    "framework.jar",
    "services.jar",
    "framework-res.apk",
    "SystemUI.apk",
    "Launcher3.apk",
    "Launcher3QuickStep.apk",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Build output root to search")
    parser.add_argument("--name", action="append", help="Artifact filename to search for")
    parser.add_argument("--max-results", type=int, default=80)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    names = set(args.name or DEFAULT_NAMES)
    if not root.exists():
        print(f"Root does not exist: {root}")
        return 2

    matches: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.name in names:
            matches.append(path)
            if len(matches) >= args.max_results:
                break

    if not matches:
        print("No matching artifacts found.")
        return 1

    for path in sorted(matches):
        try:
            stat = path.stat()
            print(f"{path}\t{stat.st_size} bytes")
        except OSError:
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
