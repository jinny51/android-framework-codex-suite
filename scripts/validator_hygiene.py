#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


sys.dont_write_bytecode = True

CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
CACHE_FILE_NAMES = {".coverage"}
CACHE_FILE_SUFFIXES = {".pyc", ".pyo"}


def _inside(root: Path, relative: str) -> Path:
    candidate = Path(os.path.abspath(root / relative))
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"cleanup path escaped repository root: {relative}") from exc
    return candidate


def _git_paths(root: Path, *args: str) -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return {
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    }


def other_files(root: Path) -> set[str]:
    return _git_paths(root, "--others", "--exclude-standard") | _git_paths(
        root,
        "--others",
        "--ignored",
        "--exclude-standard",
    )


def directories(root: Path) -> set[str]:
    result: set[str] = set()
    for current, names, _files in os.walk(root, topdown=True):
        names[:] = [name for name in names if name != ".git"]
        current_path = Path(current)
        if current_path != root:
            result.add(current_path.relative_to(root).as_posix())
    return result


def residue_paths(root: Path) -> set[str]:
    result: set[str] = set()
    for current, names, files in os.walk(root, topdown=True):
        names[:] = [name for name in names if name != ".git"]
        current_path = Path(current)
        for name in names:
            if name in CACHE_DIR_NAMES:
                result.add((current_path / name).relative_to(root).as_posix())
        for name in files:
            path = current_path / name
            if name in CACHE_FILE_NAMES or path.suffix in CACHE_FILE_SUFFIXES:
                result.add(path.relative_to(root).as_posix())
    return result


@dataclass(frozen=True)
class RepositorySnapshot:
    root: Path
    other_files: frozenset[str]
    directories: frozenset[str]
    residue: frozenset[str]

    @classmethod
    def capture(cls, root: Path) -> RepositorySnapshot:
        resolved = root.resolve()
        if not (resolved / ".git").exists():
            raise RuntimeError(f"validator cleanup root is not a Git worktree: {resolved}")
        return cls(
            root=resolved,
            other_files=frozenset(other_files(resolved)),
            directories=frozenset(directories(resolved)),
            residue=frozenset(residue_paths(resolved)),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "plugin-validator-cleanup-snapshot-v1",
            "root": str(self.root),
            "other_files": sorted(self.other_files),
            "directories": sorted(self.directories),
            "residue": sorted(self.residue),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> RepositorySnapshot:
        if payload.get("schema") != "plugin-validator-cleanup-snapshot-v1":
            raise RuntimeError("invalid validator cleanup snapshot schema")
        return cls(
            root=Path(str(payload["root"])).resolve(),
            other_files=frozenset(str(value) for value in payload.get("other_files", [])),
            directories=frozenset(str(value) for value in payload.get("directories", [])),
            residue=frozenset(str(value) for value in payload.get("residue", [])),
        )

    def cleanup(self) -> None:
        current_other = other_files(self.root)
        current_residue = residue_paths(self.root)
        generated = (current_other - self.other_files) | (current_residue - self.residue)
        for relative in sorted(generated, key=lambda value: (value.count("/"), value), reverse=True):
            path = _inside(self.root, relative)
            if path.is_symlink() or path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                shutil.rmtree(path)

        generated_dirs = directories(self.root) - self.directories
        for relative in sorted(generated_dirs, key=lambda value: (value.count("/"), value), reverse=True):
            path = _inside(self.root, relative)
            if path.is_dir() and not path.is_symlink():
                with contextlib.suppress(OSError):
                    path.rmdir()

        remaining_other = other_files(self.root) - self.other_files
        remaining_residue = residue_paths(self.root) - self.residue
        if remaining_other or remaining_residue:
            remaining = sorted(remaining_other | remaining_residue)
            raise RuntimeError("validator cleanup left generated repository artifacts: " + ", ".join(remaining))


@contextlib.contextmanager
def repository_cleanup(root: Path) -> Iterator[RepositorySnapshot]:
    snapshot = RepositorySnapshot.capture(root)
    previous_handlers: dict[int, object] = {}

    def stop(signum: int, _frame: object) -> None:
        raise SystemExit(128 + signum)

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, stop)
    try:
        yield snapshot
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        snapshot.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot, clean, and audit plugin validator filesystem residue.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--repo-root", type=Path, required=True)
    snapshot_parser.add_argument("--state-file", type=Path, required=True)
    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--state-file", type=Path, required=True)
    pristine_parser = subparsers.add_parser("assert-pristine")
    pristine_parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "snapshot":
        snapshot = RepositorySnapshot.capture(args.repo_root)
        args.state_file.parent.mkdir(parents=True, exist_ok=True)
        args.state_file.write_text(json.dumps(snapshot.to_payload(), sort_keys=True) + "\n", encoding="utf-8")
        return 0
    if args.command == "cleanup":
        payload = json.loads(args.state_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit("invalid validator cleanup snapshot")
        RepositorySnapshot.from_payload(payload).cleanup()
        return 0
    residue = sorted(residue_paths(args.repo_root.resolve()))
    if residue:
        raise SystemExit("plugin source tree contains validator residue: " + ", ".join(residue))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
