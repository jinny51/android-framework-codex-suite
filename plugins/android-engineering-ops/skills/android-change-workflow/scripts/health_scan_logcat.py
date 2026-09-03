#!/usr/bin/env python3
"""Scan logcat text for Android framework health failure signatures."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path


PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from android_engineering_ops.text_io import read_text_lines as read_lines


PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("fatal_exception", re.compile(r"FATAL EXCEPTION|AndroidRuntime", re.I)),
    ("system_server_death", re.compile(r"system_server.*(died|crash|fatal)|SystemServer.*FATAL", re.I)),
    ("systemui_failure", re.compile(r"SystemUI.*(FATAL|crash|died|ANR)|com\.android\.systemui.*FATAL", re.I)),
    ("launcher_failure", re.compile(r"Launcher.*(FATAL|crash|died|ANR)|com\.android\.launcher.*FATAL", re.I)),
    ("watchdog", re.compile(r"Watchdog|WATCHDOG", re.I)),
    ("anr", re.compile(r"\bANR\b|Application Not Responding|Input dispatching timed out", re.I)),
    ("native_crash", re.compile(r"DEBUG\s+:|Fatal signal|tombstone", re.I)),
    ("boot_loop_hint", re.compile(r"BootReceiver|zygote.*(crash|died)|init.*restarting", re.I)),
    ("permission_denial", re.compile(r"Permission Denial|SecurityException", re.I)),
    ("resource_error", re.compile(r"Resources\$NotFoundException|Failed to inflate|Binary XML|overlay.*(failed|error)", re.I)),
    (
        "wm_atm_error",
        re.compile(
            r"\s[EWFS]\s+(WindowManager|ActivityTaskManager|ActivityManager)\s*:|"
            r"(WindowManager|ActivityTaskManager|ActivityManager).*(Exception|crash|fatal|ANR)",
            re.I,
        ),
    ),
    (
        "input_error",
        re.compile(
            r"\s[EWFS]\s+(InputDispatcher|InputReader)\s*:|"
            r"(InputDispatcher|InputReader|input dispatch).*(timeout|Exception|fatal|ANR|error)",
            re.I,
        ),
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", help="Logcat file path, or '-' for stdin")
    parser.add_argument("--max-lines", type=int, default=5, help="Example lines per category")
    parser.add_argument("--category", action="append", help="Only report a category")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    wanted = set(args.category or [])
    lines = read_lines(args.log)
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}

    for line in lines:
        for name, pattern in PATTERNS:
            if wanted and name not in wanted:
                continue
            if pattern.search(line):
                counts[name] += 1
                examples.setdefault(name, [])
                if len(examples[name]) < args.max_lines:
                    examples[name].append(line)

    if not counts:
        print("No configured health signatures found.")
        return 0

    print("Health signatures:")
    for name, count in counts.most_common():
        print(f"- {name}: {count}")
        for line in examples.get(name, []):
            print(f"  {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
