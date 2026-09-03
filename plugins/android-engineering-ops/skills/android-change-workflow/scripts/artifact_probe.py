#!/usr/bin/env python3
"""Retired local artifact basename scanner."""

from __future__ import annotations

import sys


MIGRATION_MESSAGE = (
    "artifact_probe.py is retired: local recursive basename scans of mounted Android output "
    "are forbidden. Resolve an exact artifact path from the remote build profile and "
    "validated remote artifact manifest."
)


def main() -> int:
    print(MIGRATION_MESSAGE, file=sys.stderr)
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
