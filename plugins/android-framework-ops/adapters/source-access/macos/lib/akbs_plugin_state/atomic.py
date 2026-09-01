#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _mode(value: str) -> int:
    try:
        mode = int(value, 8)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid octal mode: {value}") from exc
    if mode < 0 or mode > 0o777:
        raise argparse.ArgumentTypeError(f"mode out of range: {value}")
    return mode


def _lock_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.lock")


@contextmanager
def stable_file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(_lock_path(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY)
        os.fsync(descriptor)
    except OSError:
        # Some filesystems do not support directory fsync. The file itself was
        # already synced before replace, so keep the replacement fail-safe.
        pass
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _replace_unlocked(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.tmp.",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def atomic_replace(path: Path, payload: bytes, mode: int = 0o600) -> None:
    with stable_file_lock(path):
        _replace_unlocked(path, payload, mode)


def update_json(
    path: Path,
    update: Callable[[Dict[str, Any]], None],
    mode: int = 0o600,
) -> bool:
    with stable_file_lock(path):
        existed = path.exists()
        data: Dict[str, Any] = {}
        if existed:
            with path.open(encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise ValueError(f"JSON state must be an object: {path}")
            data = loaded
        update(data)
        payload = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        _replace_unlocked(path, payload, mode)
        return existed


def _parse_assignment(value: str) -> Tuple[str, str]:
    key, separator, item = value.partition("=")
    if not separator or not ENV_KEY.fullmatch(key):
        raise ValueError(f"invalid environment assignment: {value!r}")
    if "\n" in item or "\r" in item:
        raise ValueError(f"environment assignment contains a newline: {key}")
    return key, item


def _replace_env_values(lines: List[str], updates: Iterable[Tuple[str, str]]) -> List[str]:
    for key, value in updates:
        prefix = f"{key}="
        found = False
        replaced: List[str] = []
        for line in lines:
            if line.startswith(prefix):
                replaced.append(f"{prefix}{value}")
                found = True
            else:
                replaced.append(line)
        if not found:
            if replaced and replaced[-1] != "":
                replaced.append("")
            replaced.append(f"{prefix}{value}")
        lines = replaced
    return lines


def update_env(
    path: Path,
    defaults: Sequence[Tuple[str, str]],
    updates: Sequence[Tuple[str, str]],
    mode: int = 0o600,
) -> None:
    with stable_file_lock(path):
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
        else:
            lines = [f"{key}={value}" for key, value in defaults]
        lines = _replace_env_values(lines, updates)
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        _replace_unlocked(path, payload, mode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Atomically maintain private plugin state files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    write = subparsers.add_parser("write")
    write.add_argument("--path", required=True, type=Path)
    write.add_argument("--mode", default=0o600, type=_mode)

    env = subparsers.add_parser("update-env")
    env.add_argument("--path", required=True, type=Path)
    env.add_argument("--mode", default=0o600, type=_mode)
    env.add_argument("--default", action="append", default=[])
    env.add_argument("--set", dest="updates", action="append", default=[])
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "write":
        atomic_replace(args.path, sys.stdin.buffer.read(), args.mode)
        return 0
    if args.command == "update-env":
        defaults = [_parse_assignment(value) for value in args.default]
        updates = [_parse_assignment(value) for value in args.updates]
        update_env(args.path, defaults, updates, args.mode)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
