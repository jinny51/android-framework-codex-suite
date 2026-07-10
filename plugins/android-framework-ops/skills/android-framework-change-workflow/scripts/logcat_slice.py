#!/usr/bin/env python3
"""Slice Android logcat text by keyword, tag, pid, and optional time bounds."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from android_framework_ops.text_io import read_text_lines as read_lines


LOG_RE = re.compile(
    r"^(?P<date>\d{2}-\d{2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2}\.\d+)\s+"
    r"(?P<pid>\d+)\s+"
    r"(?P<tid>\d+)\s+"
    r"(?P<level>[VDIWEFS])\s+"
    r"(?P<tag>[^:]+):\s?"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", help="Logcat file path, or '-' for stdin")
    parser.add_argument("-k", "--keyword", action="append", default=[], help="Substring or regex to match")
    parser.add_argument("-t", "--tag", action="append", default=[], help="Exact logcat tag to include")
    parser.add_argument("--pid", action="append", default=[], help="PID to include")
    parser.add_argument("--start", help="Start time HH:MM:SS.mmm or MM-DD HH:MM:SS.mmm")
    parser.add_argument("--end", help="End time HH:MM:SS.mmm or MM-DD HH:MM:SS.mmm")
    parser.add_argument("-C", "--context", type=int, default=0, help="Context lines around matches")
    parser.add_argument("-i", "--ignore-case", action="store_true", help="Case-insensitive keyword matching")
    parser.add_argument("--regex", action="store_true", help="Treat keywords as regular expressions")
    return parser.parse_args()


def line_time_key(line: str) -> str | None:
    match = LOG_RE.match(line)
    if not match:
        return None
    return f"{match.group('date')} {match.group('time')}"


def normalize_bound(bound: str | None, sample_date: str | None) -> str | None:
    if not bound:
        return None
    if re.match(r"^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+", bound):
        return bound
    if sample_date and re.match(r"^\d{2}:\d{2}:\d{2}\.\d+", bound):
        return f"{sample_date} {bound}"
    return bound


def matches_keyword(line: str, keywords: list[str], regex: bool, flags: int) -> bool:
    if not keywords:
        return True
    if regex:
        return any(re.search(pattern, line, flags) for pattern in keywords)
    haystack = line.lower() if flags & re.IGNORECASE else line
    needles = [item.lower() for item in keywords] if flags & re.IGNORECASE else keywords
    return any(item in haystack for item in needles)


def line_selected(line: str, args: argparse.Namespace, start: str | None, end: str | None) -> bool:
    match = LOG_RE.match(line)
    key = line_time_key(line)
    if start and key and key < start:
        return False
    if end and key and key > end:
        return False
    if args.tag:
        if not match or match.group("tag").strip() not in set(args.tag):
            return False
    if args.pid:
        if not match or match.group("pid") not in set(args.pid):
            return False
    flags = re.IGNORECASE if args.ignore_case else 0
    return matches_keyword(line, args.keyword, args.regex, flags)


def main() -> int:
    args = parse_args()
    lines = read_lines(args.log)
    sample_date = None
    for line in lines:
        key = line_time_key(line)
        if key:
            sample_date = key.split()[0]
            break
    start = normalize_bound(args.start, sample_date)
    end = normalize_bound(args.end, sample_date)

    selected: set[int] = set()
    for idx, line in enumerate(lines):
        if line_selected(line, args, start, end):
            begin = max(0, idx - args.context)
            finish = min(len(lines), idx + args.context + 1)
            selected.update(range(begin, finish))

    for idx in sorted(selected):
        print(lines[idx])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
