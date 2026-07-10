from __future__ import annotations

import sys
from pathlib import Path


def read_text_lines(path: str) -> list[str]:
    if path == "-":
        return sys.stdin.read().splitlines()
    return Path(path).read_text(errors="replace").splitlines()
