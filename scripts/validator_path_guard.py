#!/usr/bin/env python3
"""Shared fail-closed path guard for AKBS validators and test helpers."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


sys.dont_write_bytecode = True

OWNER_FILE = ".akbs-validator-owner.json"
OWNER_SCHEMA = "akbs-validator-private-directory-v1"

ABSOLUTE_ESCAPE = "R41_ABSOLUTE_ESCAPE"
PARENT_ESCAPE = "R41_PARENT_ESCAPE"
SYMLINK_ESCAPE = "R41_SYMLINK_ESCAPE"
GIT_SOURCE_FORBIDDEN = "R41_GIT_SOURCE_FORBIDDEN"
AKBS_ROOT_FORBIDDEN = "R41_AKBS_ROOT_FORBIDDEN"
PRODUCTION_ROOT_FORBIDDEN = "R41_PRODUCTION_ROOT_FORBIDDEN"
AUTHORITY_ROOT_FORBIDDEN = "R41_AUTHORITY_ROOT_FORBIDDEN"
AUTHORITY_UNAVAILABLE = "R41_AUTHORITY_UNAVAILABLE"
OWNER_MISMATCH = "R41_OWNER_MISMATCH"
UNSAFE_NAME = "R41_UNSAFE_NAME"
OWNERSHIP_MISMATCH = "R41_OWNERSHIP_MISMATCH"


class ValidatorPathError(RuntimeError):
    """A stable validator path rejection with a machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"AKBS_VALIDATOR_GUARD[{code}]: {message}")
        self.code = code


def absolute_without_following(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _is_descendant_or_same(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _contains_parent_reference(path: Path) -> bool:
    return any(part == ".." for part in path.parts)


def _assert_no_symlink_components(path: Path, *, label: str) -> None:
    raw = absolute_without_following(path)
    current = Path(raw.anchor)
    for part in raw.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValidatorPathError(
                SYMLINK_ESCAPE,
                f"{label} contains a symlink component: {current}",
            )


def _assert_authority(authority: Path, *, allow_shared_authority: bool, label: str) -> Path:
    raw = absolute_without_following(authority)
    _assert_no_symlink_components(raw, label=f"{label} authority")
    if not raw.is_dir():
        raise ValidatorPathError(
            AUTHORITY_UNAVAILABLE,
            f"{label} authority must be an existing real directory: {raw}",
        )
    metadata = raw.stat()
    if metadata.st_uid == os.geteuid():
        return raw.resolve(strict=True)
    shared_sticky = bool(metadata.st_mode & stat.S_ISVTX) and bool(metadata.st_mode & stat.S_IWOTH)
    if allow_shared_authority and shared_sticky:
        return raw.resolve(strict=True)
    raise ValidatorPathError(
        OWNER_MISMATCH,
        f"{label} authority is not owned by uid {os.geteuid()}: {raw}",
    )


def _nearest_git_worktree(path: Path) -> Path | None:
    current = path if path.is_dir() else path.parent
    while True:
        marker = current / ".git"
        if marker.exists() or marker.is_symlink():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _assert_not_protected(
    path: Path,
    *,
    source_roots: Iterable[Path],
    akbs_roots: Iterable[Path],
    label: str,
) -> None:
    raw = absolute_without_following(path)
    for root in akbs_roots:
        akbs_root = absolute_without_following(root)
        if raw == akbs_root:
            raise ValidatorPathError(
                AKBS_ROOT_FORBIDDEN,
                f"{label} must not target an AKBS root: {raw}",
            )
        for name in ("runtime", "data", "backups"):
            protected = akbs_root / name
            if _is_descendant_or_same(raw, protected):
                raise ValidatorPathError(
                    PRODUCTION_ROOT_FORBIDDEN,
                    f"{label} must not target production {name}: {raw}",
                )
    for root in source_roots:
        source_root = absolute_without_following(root)
        if _is_descendant_or_same(raw, source_root):
            raise ValidatorPathError(
                GIT_SOURCE_FORBIDDEN,
                f"{label} must not target a Git source tree: {raw}",
            )
    worktree = _nearest_git_worktree(raw)
    if worktree is not None:
        raise ValidatorPathError(
            GIT_SOURCE_FORBIDDEN,
            f"{label} must not target a Git source tree: {worktree}",
        )


def guard_write_path(
    candidate: Path,
    *,
    authority: Path,
    label: str,
    source_roots: Iterable[Path] = (),
    akbs_roots: Iterable[Path] = (),
    allow_authority_root: bool = False,
    allow_shared_authority: bool = False,
) -> Path:
    """Resolve a write target only when it stays below one audited authority."""

    candidate = candidate.expanduser()
    if _contains_parent_reference(candidate):
        raise ValidatorPathError(
            PARENT_ESCAPE,
            f"{label} contains a parent traversal: {candidate}",
        )
    authority_real = _assert_authority(
        authority,
        allow_shared_authority=allow_shared_authority,
        label=label,
    )
    raw = absolute_without_following(candidate if candidate.is_absolute() else authority_real / candidate)
    _assert_not_protected(
        raw,
        source_roots=source_roots,
        akbs_roots=akbs_roots,
        label=label,
    )
    if not _is_descendant_or_same(raw, authority_real):
        raise ValidatorPathError(
            ABSOLUTE_ESCAPE,
            f"{label} escaped its write authority: {raw}",
        )
    if raw == authority_real and not allow_authority_root:
        raise ValidatorPathError(
            AUTHORITY_ROOT_FORBIDDEN,
            f"{label} must be below its write authority: {raw}",
        )
    _assert_no_symlink_components(raw, label=label)
    resolved = raw.resolve(strict=False)
    if not _is_descendant_or_same(resolved, authority_real):
        raise ValidatorPathError(
            SYMLINK_ESCAPE,
            f"{label} resolved outside its write authority: {resolved}",
        )
    if raw.exists() and raw.stat().st_uid != os.geteuid():
        raise ValidatorPathError(
            OWNER_MISMATCH,
            f"{label} is not owned by uid {os.geteuid()}: {raw}",
        )
    return resolved


def nearest_existing_parent(path: Path) -> Path:
    current = absolute_without_following(path)
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


def guard_external_write_path(
    candidate: Path,
    *,
    label: str,
    source_roots: Iterable[Path] = (),
    akbs_roots: Iterable[Path] = (),
) -> Path:
    """Guard an explicit normal-directory output outside protected AKBS roots."""

    if _contains_parent_reference(candidate.expanduser()):
        raise ValidatorPathError(
            PARENT_ESCAPE,
            f"{label} contains a parent traversal: {candidate}",
        )
    raw = absolute_without_following(candidate)
    authority = nearest_existing_parent(raw.parent)
    return guard_write_path(
        raw,
        authority=authority,
        label=label,
        source_roots=source_roots,
        akbs_roots=akbs_roots,
        allow_shared_authority=True,
    )


@dataclass(frozen=True)
class PrivateDirectory:
    authority: Path
    path: Path
    token: str
    purpose: str

    @property
    def marker(self) -> Path:
        return self.path / OWNER_FILE

    @classmethod
    def create(
        cls,
        authority: Path,
        *,
        prefix: str,
        purpose: str,
        source_roots: Iterable[Path] = (),
        akbs_roots: Iterable[Path] = (),
        allow_shared_authority: bool = False,
    ) -> "PrivateDirectory":
        if not prefix or "/" in prefix or "\\" in prefix or _contains_parent_reference(Path(prefix)):
            raise ValidatorPathError(UNSAFE_NAME, f"unsafe private directory prefix: {prefix!r}")
        authority_real = _assert_authority(
            authority,
            allow_shared_authority=allow_shared_authority,
            label=purpose,
        )
        token = uuid.uuid4().hex
        path = guard_write_path(
            Path(f"{prefix}{token}"),
            authority=authority_real,
            label=purpose,
            source_roots=source_roots,
            akbs_roots=akbs_roots,
            allow_shared_authority=allow_shared_authority,
        )
        created = False
        try:
            path.mkdir(mode=0o700)
            created = True
            payload = {
                "schema": OWNER_SCHEMA,
                "token": token,
                "path": str(path.resolve(strict=True)),
                "purpose": purpose,
                "uid": os.geteuid(),
            }
            with (path / OWNER_FILE).open("x", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.write("\n")
            (path / OWNER_FILE).chmod(0o600)
        except BaseException:
            if created:
                shutil.rmtree(path, ignore_errors=True)
            raise
        return cls(authority_real, path, token, purpose)

    @classmethod
    def load(
        cls,
        authority: Path,
        path: Path,
        *,
        token: str,
        purpose: str,
        source_roots: Iterable[Path] = (),
        akbs_roots: Iterable[Path] = (),
        allow_shared_authority: bool = False,
        allow_missing: bool = False,
    ) -> "PrivateDirectory | None":
        authority_real = _assert_authority(
            authority,
            allow_shared_authority=allow_shared_authority,
            label=purpose,
        )
        raw = absolute_without_following(path)
        if not raw.exists() and not raw.is_symlink():
            if allow_missing:
                return None
            raise ValidatorPathError(AUTHORITY_UNAVAILABLE, f"owned private directory is missing: {raw}")
        guarded = guard_write_path(
            raw,
            authority=authority_real,
            label=purpose,
            source_roots=source_roots,
            akbs_roots=akbs_roots,
            allow_shared_authority=allow_shared_authority,
        )
        marker = guarded / OWNER_FILE
        if marker.is_symlink() or not marker.is_file():
            raise ValidatorPathError(OWNERSHIP_MISMATCH, f"private directory marker is missing: {guarded}")
        payload = json.loads(marker.read_text(encoding="utf-8"))
        expected = {
            "schema": OWNER_SCHEMA,
            "token": token,
            "path": str(guarded.resolve(strict=True)),
            "purpose": purpose,
            "uid": os.geteuid(),
        }
        if payload != expected or guarded.stat().st_uid != os.geteuid():
            raise ValidatorPathError(OWNERSHIP_MISMATCH, f"private directory ownership mismatch: {guarded}")
        return cls(authority_real, guarded, token, purpose)

    def cleanup(
        self,
        *,
        source_roots: Iterable[Path] = (),
        akbs_roots: Iterable[Path] = (),
        allow_shared_authority: bool = False,
    ) -> None:
        loaded = self.load(
            self.authority,
            self.path,
            token=self.token,
            purpose=self.purpose,
            source_roots=source_roots,
            akbs_roots=akbs_roots,
            allow_shared_authority=allow_shared_authority,
            allow_missing=True,
        )
        if loaded is not None:
            shutil.rmtree(loaded.path)


def _paths(values: list[str]) -> list[Path]:
    return [Path(value) for value in values]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("guard", "create-private", "cleanup-private"):
        command = subparsers.add_parser(name)
        command.add_argument("--authority", type=Path, required=True)
        command.add_argument("--source-root", action="append", default=[])
        command.add_argument("--akbs-root", action="append", default=[])
        command.add_argument("--allow-shared-authority", action="store_true")
        if name == "guard":
            command.add_argument("--path", type=Path, required=True)
            command.add_argument("--label", required=True)
            command.add_argument("--allow-authority-root", action="store_true")
        elif name == "create-private":
            command.add_argument("--prefix", required=True)
            command.add_argument("--purpose", required=True)
        else:
            command.add_argument("--path", type=Path, required=True)
            command.add_argument("--token", required=True)
            command.add_argument("--purpose", required=True)
    args = parser.parse_args()
    common = {
        "source_roots": _paths(args.source_root),
        "akbs_roots": _paths(args.akbs_root),
        "allow_shared_authority": args.allow_shared_authority,
    }
    try:
        if args.command == "guard":
            path = guard_write_path(
                args.path,
                authority=args.authority,
                label=args.label,
                allow_authority_root=args.allow_authority_root,
                **common,
            )
            print(path)
        elif args.command == "create-private":
            owned = PrivateDirectory.create(
                args.authority,
                prefix=args.prefix,
                purpose=args.purpose,
                **common,
            )
            print(f"{owned.path}\t{owned.token}")
        else:
            loaded = PrivateDirectory.load(
                args.authority,
                args.path,
                token=args.token,
                purpose=args.purpose,
                allow_missing=True,
                **common,
            )
            if loaded is not None:
                loaded.cleanup(**common)
    except (OSError, ValueError, json.JSONDecodeError, ValidatorPathError) as error:
        print(str(error), file=sys.stderr)
        return 78
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
