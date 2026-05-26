#!/usr/bin/env python3
"""Find temporary diagnostic logs and suspicious debug markers in source files."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


DEFAULT_EXTENSIONS = {
    ".java",
    ".kt",
    ".cc",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".aidl",
    ".xml",
    ".bp",
    ".mk",
}

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("temporary_marker", re.compile(r"TEMP_DIAG|TODO_DIAG|DEBUG_DIAG|REMOVE_BEFORE_SUBMIT")),
    ("println", re.compile(r"System\.out\.println|printStackTrace\s*\(")),
    ("android_log", re.compile(r"\bSlog\.(v|d|i|w|e)\b|\bLog\.(v|d|i|w|e)\b|ALOG[VDIWEF]\b")),
    ("todo_fixme", re.compile(r"\bTODO\b|\bFIXME\b")),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Source root or file to scan")
    parser.add_argument("--extension", action="append", help="Restrict to extension, e.g. .java")
    parser.add_argument("--include-logs", action="store_true", help="Report all Log/Slog/ALOG calls, not only marked diagnostics")
    return parser.parse_args()


def iter_files(root: Path, extensions: set[str]) -> list[Path]:
    if root.is_file():
        return [root]
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in extensions:
            files.append(path)
    return files


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    extensions = set(args.extension or DEFAULT_EXTENSIONS)
    findings: list[str] = []

    for path in iter_files(root, extensions):
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            for name, pattern in PATTERNS:
                if name == "android_log" and not args.include_logs:
                    if not re.search(r"TEMP_DIAG|TODO_DIAG|DEBUG_DIAG|REMOVE_BEFORE_SUBMIT", line):
                        continue
                if pattern.search(line):
                    findings.append(f"{path}:{lineno}: {name}: {line.strip()}")

    if not findings:
        print("No diagnostic markers found.")
        return 0

    print("Diagnostic audit findings:")
    for item in findings:
        print(item)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
