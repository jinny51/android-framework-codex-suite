#!/usr/bin/env python3
"""Locate the installed core plugin and execute its internal source-access dispatcher."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


CORE_PLUGIN = "android-framework-ops"
MARKETPLACE = "android-framework-codex-suite"
MIN_CORE_VERSION = (1, 0, 167)
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def version_tuple(value: str) -> tuple[int, int, int] | None:
    match = VERSION_RE.fullmatch(value.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def validate_core(root: Path) -> tuple[tuple[int, int, int], Path] | None:
    try:
        manifest = json.loads((root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        contract = json.loads(
            (root / "contracts/source-access/v1/adapter-contract.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    version = version_tuple(str(manifest.get("version") or ""))
    cli = root / "internal/android-source-access/scripts/android_source_access.py"
    if (
        manifest.get("name") != CORE_PLUGIN
        or version is None
        or version < MIN_CORE_VERSION
        or contract.get("schema") != "android-source-access-adapter-v1"
        or contract.get("implementation_owner") != CORE_PLUGIN
        or not cli.is_file()
    ):
        return None
    try:
        cli.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return version, cli


def candidate_roots() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("ANDROID_FRAMEWORK_OPS_ROOT", "").strip()
    if override:
        candidates.append(Path(override).expanduser())

    script = Path(__file__).resolve()
    for ancestor in script.parents:
        if ancestor.name == MARKETPLACE:
            installed_core = ancestor / CORE_PLUGIN
            if installed_core.is_dir():
                candidates.extend(path for path in installed_core.iterdir() if path.is_dir())
            break
    for ancestor in script.parents:
        if ancestor.name == "plugins":
            candidates.append(ancestor / CORE_PLUGIN)
            break

    codex_home = Path(os.environ.get("CODEX_HOME", "").strip() or Path.home() / ".codex")
    cache_root = codex_home / "plugins/cache" / MARKETPLACE / CORE_PLUGIN
    if cache_root.is_dir():
        candidates.extend(path for path in cache_root.iterdir() if path.is_dir())
    return candidates


def resolve_core_cli() -> Path:
    valid: list[tuple[tuple[int, int, int], Path]] = []
    seen: set[Path] = set()
    for root in candidate_roots():
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        candidate = validate_core(resolved)
        if candidate:
            valid.append(candidate)
    if not valid:
        minimum = ".".join(str(part) for part in MIN_CORE_VERSION)
        raise SystemExit(
            f"SOURCE_ACCESS_CORE_REQUIRED: update {CORE_PLUGIN} to {minimum} or newer before source access"
        )
    return max(valid, key=lambda item: item[0])[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--expected-host", required=True, choices=("wsl", "macos"))
    parser.add_argument("--command", required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    arguments = list(args.arguments)
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    cli = resolve_core_cli()
    os.execv(
        sys.executable,
        [
            sys.executable,
            str(cli),
            "--expected-host",
            args.expected_host,
            "run",
            args.command,
            "--",
            *arguments,
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
