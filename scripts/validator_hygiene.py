#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
AKBS_ROOT = Path(os.environ.get("AKBS_ROOT", "").strip() or Path.home() / "akbs").expanduser().resolve()
OUTPUT_HELPER = Path(
    os.environ.get("AKBS_OUTPUTS_HELPER", "").strip()
    or AKBS_ROOT / "maintainer" / "scripts" / "akbs_outputs.py"
).expanduser().resolve()
if not OUTPUT_HELPER.is_file():
    raise RuntimeError(f"AKBS canonical outputs helper is unavailable: {OUTPUT_HELPER}")
if str(OUTPUT_HELPER.parent) not in sys.path:
    sys.path.insert(0, str(OUTPUT_HELPER.parent))

import akbs_outputs  # noqa: E402
from validator_path_guard import (  # noqa: E402
    ValidatorPathError,
    absolute_without_following,
    guard_write_path,
)

SCHEMA = "plugin-validator-owned-invocation-v2"
STATE_FILE = "validator-state.json"
INVOCATION_PREFIX = "akbs-plugin-validator-"
PURPOSE = "plugin validator invocation"
TASK_ID = "plugin"
CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
CACHE_FILE_NAMES = {".coverage"}
CACHE_FILE_SUFFIXES = {".pyc", ".pyo"}


def controlled_temp_root(*, create: bool = True) -> Path:
    base = akbs_outputs.category_root("tmp", AKBS_ROOT, create=create)
    expected = base / TASK_ID
    configured = os.environ.get("AKBS_PLUGIN_TMP_ROOT", "").strip()
    root = absolute_without_following(Path(configured)) if configured else expected
    if root != expected:
        raise RuntimeError(f"AKBS_PLUGIN_TMP_ROOT must match the canonical plugin temp root: {expected}")
    root = guard_write_path(
        root,
        authority=base,
        label="plugin validator task root",
        source_roots=(REPO_ROOT,),
        akbs_roots=(AKBS_ROOT,),
    )
    if create:
        root.mkdir(parents=True, mode=0o750, exist_ok=True)
    return root


def _validate_state_location(state_file: Path, *, allow_missing: bool) -> tuple[Path, Path]:
    raw_state = absolute_without_following(state_file)
    invocation_dir = raw_state.parent
    temp_root = controlled_temp_root(create=False)
    if raw_state.name != STATE_FILE:
        raise RuntimeError(f"invalid validator ownership file name: {raw_state}")
    if not invocation_dir.name.startswith(INVOCATION_PREFIX):
        raise RuntimeError(f"invalid validator invocation directory: {invocation_dir}")
    if invocation_dir.parent != temp_root:
        raise RuntimeError(f"validator invocation escaped controlled temp root: {invocation_dir}")
    if not invocation_dir.exists() and not invocation_dir.is_symlink():
        if allow_missing:
            return invocation_dir, temp_root
        raise RuntimeError(f"validator invocation does not exist: {invocation_dir}")
    guarded_invocation = guard_write_path(
        invocation_dir,
        authority=temp_root,
        label="plugin validator invocation",
        source_roots=(REPO_ROOT,),
        akbs_roots=(AKBS_ROOT,),
    )
    if invocation_dir.is_symlink() or not invocation_dir.is_dir():
        raise RuntimeError(f"validator invocation must be a real directory: {invocation_dir}")
    if raw_state.is_symlink() or not raw_state.is_file():
        raise RuntimeError(f"validator ownership file must be a real file: {raw_state}")
    guard_write_path(
        raw_state,
        authority=guarded_invocation,
        label="plugin validator state",
        source_roots=(REPO_ROOT,),
        akbs_roots=(AKBS_ROOT,),
    )
    return guarded_invocation, temp_root


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
        if not (resolved / ".git").is_dir():
            raise RuntimeError(f"validator cleanup root is not a Git worktree: {resolved}")
        return cls(
            root=resolved,
            other_files=frozenset(other_files(resolved)),
            directories=frozenset(directories(resolved)),
            residue=frozenset(residue_paths(resolved)),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "root": str(self.root),
            "other_files": sorted(self.other_files),
            "directories": sorted(self.directories),
            "residue": sorted(self.residue),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> RepositorySnapshot:
        return cls(
            root=Path(str(payload["root"])).resolve(),
            other_files=frozenset(str(value) for value in payload.get("other_files", [])),
            directories=frozenset(str(value) for value in payload.get("directories", [])),
            residue=frozenset(str(value) for value in payload.get("residue", [])),
        )

    def generated_paths(self) -> set[str]:
        return (other_files(self.root) - self.other_files) | (residue_paths(self.root) - self.residue)

    def assert_unchanged(self) -> None:
        generated = sorted(self.generated_paths())
        if generated:
            raise RuntimeError(
                "validator left unowned repository artifacts; cleanup refused: " + ", ".join(generated)
            )

    def cleanup(self) -> None:
        """Compatibility alias: audit only; never delete unowned repository paths."""
        self.assert_unchanged()


@dataclass(frozen=True)
class ValidatorInvocation:
    owned: Any
    state_file: Path
    work_dir: Path
    temp_root: Path
    snapshot: RepositorySnapshot

    @property
    def invocation_dir(self) -> Path:
        return self.owned.path

    @property
    def token(self) -> str:
        return self.owned.token

    @classmethod
    def create(cls, repo_root: Path) -> ValidatorInvocation:
        snapshot = RepositorySnapshot.capture(repo_root)
        if snapshot.residue:
            raise RuntimeError(
                "validator cleanup requires a residue-free plugin source tree: " + ", ".join(sorted(snapshot.residue))
            )
        temp_root = controlled_temp_root()
        run_id = f"{INVOCATION_PREFIX}{uuid.uuid4().hex}"
        expected_invocation = guard_write_path(
            Path(run_id),
            authority=temp_root,
            label="plugin validator invocation",
            source_roots=(snapshot.root,),
            akbs_roots=(AKBS_ROOT,),
        )
        owned = akbs_outputs.OwnedOutputDirectory.create(
            AKBS_ROOT,
            task_id=TASK_ID,
            run_id=run_id,
            purpose=PURPOSE,
        )
        if owned.path != expected_invocation:
            owned.cleanup()
            raise RuntimeError("canonical plugin validator temp root drifted")
        try:
            work_dir = guard_write_path(
                Path("work"),
                authority=owned.path,
                label="plugin validator work directory",
                source_roots=(snapshot.root,),
                akbs_roots=(AKBS_ROOT,),
            )
            work_dir.mkdir(mode=0o700)
            state_file = guard_write_path(
                Path(STATE_FILE),
                authority=owned.path,
                label="plugin validator state",
                source_roots=(snapshot.root,),
                akbs_roots=(AKBS_ROOT,),
            )
            payload = {
                "schema": SCHEMA,
                "token": owned.token,
                "temp_root": str(temp_root),
                "invocation_dir": str(owned.path),
                "work_dir": str(work_dir),
                "snapshot": snapshot.to_payload(),
            }
            with state_file.open("x", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.write("\n")
            state_file.chmod(0o600)
            return cls(owned, state_file, work_dir, temp_root, snapshot)
        except BaseException:
            owned.cleanup()
            raise

    @classmethod
    def load(cls, state_file: Path) -> ValidatorInvocation:
        invocation_dir, temp_root = _validate_state_location(state_file, allow_missing=False)
        raw_state = absolute_without_following(state_file)
        payload = json.loads(raw_state.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
            raise RuntimeError("invalid validator ownership schema")
        token = str(payload.get("token") or "")
        if len(token) != 32:
            raise RuntimeError("invalid validator ownership token")
        owned = akbs_outputs.OwnedOutputDirectory.load(
            AKBS_ROOT,
            task_id=TASK_ID,
            run_id=invocation_dir.name,
            token=token,
            purpose=PURPOSE,
        )
        if owned.committed:
            raise RuntimeError(f"validator invocation disappeared before cleanup: {invocation_dir}")
        if Path(str(payload.get("temp_root"))).resolve() != temp_root:
            raise RuntimeError("validator ownership temp root mismatch")
        if Path(str(payload.get("invocation_dir"))).resolve() != invocation_dir.resolve():
            raise RuntimeError("validator ownership invocation mismatch")
        work_dir = invocation_dir / "work"
        if Path(str(payload.get("work_dir"))).resolve() != work_dir.resolve():
            raise RuntimeError("validator ownership work directory mismatch")
        snapshot_payload = payload.get("snapshot")
        if not isinstance(snapshot_payload, dict):
            raise RuntimeError("invalid validator repository snapshot")
        snapshot = RepositorySnapshot.from_payload(snapshot_payload)
        return cls(owned, raw_state, work_dir, temp_root, snapshot)

    def cleanup(self) -> None:
        loaded = ValidatorInvocation.load(self.state_file)
        if loaded.token != self.token:
            raise RuntimeError("validator ownership token changed")
        try:
            loaded.snapshot.assert_unchanged()
        finally:
            loaded.owned.cleanup()


def cleanup_state_file(state_file: Path) -> None:
    invocation_dir, _temp_root = _validate_state_location(state_file, allow_missing=True)
    if not invocation_dir.exists():
        return
    ValidatorInvocation.load(state_file).cleanup()


@contextlib.contextmanager
def repository_cleanup(root: Path) -> Iterator[RepositorySnapshot]:
    invocation = ValidatorInvocation.create(root)
    previous_handlers: dict[int, object] = {}
    previous_tmpdir = os.environ.get("TMPDIR")
    previous_tempfile_dir = tempfile.tempdir

    def stop(signum: int, _frame: object) -> None:
        raise SystemExit(128 + signum)

    handled_signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        handled_signals.append(signal.SIGHUP)
    for signum in handled_signals:
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, stop)
    os.environ["TMPDIR"] = str(invocation.work_dir)
    tempfile.tempdir = str(invocation.work_dir)
    try:
        yield invocation.snapshot
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        if previous_tmpdir is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = previous_tmpdir
        tempfile.tempdir = previous_tempfile_dir
        invocation.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description="Own, clean, and audit plugin validator filesystem state.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--repo-root", type=Path, required=True)
    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--state-file", type=Path, required=True)
    pristine_parser = subparsers.add_parser("assert-pristine")
    pristine_parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "create":
        invocation = ValidatorInvocation.create(args.repo_root)
        print(invocation.invocation_dir)
        print(invocation.state_file)
        print(invocation.work_dir)
        return 0
    if args.command == "cleanup":
        cleanup_state_file(args.state_file)
        return 0
    residue = sorted(residue_paths(args.repo_root.resolve()))
    if residue:
        raise SystemExit("plugin source tree contains validator residue: " + ", ".join(residue))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (akbs_outputs.OutputContractError, RuntimeError, ValidatorPathError) as error:
        raise SystemExit(str(error)) from error
