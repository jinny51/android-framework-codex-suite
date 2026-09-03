"""Fail-closed handoff between a remote build and a mounted local artifact.

Creation is intended to run inside the canonical remote workspace after the
bound build command. Validation must receive workspace, command, module,
profile, and remote-root values from trusted command state rather than from the
manifest itself. Local delivery is allowed only after the mounted file is
re-hashed and matches the remote-computed facts.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
from typing import Any, Mapping


REMOTE_ARTIFACT_MANIFEST_SCHEMA = "android-remote-build-artifact-manifest-v1"
REMOTE_ARTIFACT_MANIFEST_VERSION = 1

_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "version",
        "remote_path",
        "module",
        "profile",
        "workspace_id",
        "command_id",
        "build_started_ns",
        "build_finished_ns",
        "size",
        "mtime_ns",
        "sha256",
    }
)
_CONTEXT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_HASH_CHUNK_SIZE = 1024 * 1024


class RemoteArtifactManifestError(ValueError):
    """The remote artifact manifest cannot be trusted for delivery."""


@dataclass(frozen=True)
class RemoteArtifactManifest:
    schema: str
    version: int
    remote_path: str
    module: str
    profile: str
    workspace_id: str
    command_id: str
    build_started_ns: int
    build_finished_ns: int
    size: int
    mtime_ns: int
    sha256: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "schema": self.schema,
            "version": self.version,
            "remote_path": self.remote_path,
            "module": self.module,
            "profile": self.profile,
            "workspace_id": self.workspace_id,
            "command_id": self.command_id,
            "build_started_ns": self.build_started_ns,
            "build_finished_ns": self.build_finished_ns,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class _FileFingerprint:
    size: int
    mtime_ns: int
    sha256: str


def _require_integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise RemoteArtifactManifestError(
            f"artifact manifest field {field!r} must be an integer >= {minimum}"
        )
    return value


def _require_context_value(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _CONTEXT_PATTERN.fullmatch(value):
        raise RemoteArtifactManifestError(
            f"artifact manifest field {field!r} has an invalid context identifier"
        )
    return value


def _require_canonical_remote_path(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or any(ord(character) < 32 for character in value)
    ):
        raise RemoteArtifactManifestError(
            f"artifact manifest field {field!r} must be a non-empty POSIX path"
        )
    if not value.startswith("/") or value.startswith("//"):
        raise RemoteArtifactManifestError(
            f"artifact manifest field {field!r} must be an absolute POSIX path"
        )
    if value != posixpath.normpath(value):
        raise RemoteArtifactManifestError(
            f"artifact manifest field {field!r} is not canonical: {value}"
        )
    return value


def _require_remote_descendant(remote_path: str, remote_root: str) -> PurePosixPath:
    path = PurePosixPath(remote_path)
    root = PurePosixPath(remote_root)
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise RemoteArtifactManifestError(
            f"remote artifact path is outside the expected workspace: {remote_path}"
        ) from exc
    if not relative.parts:
        raise RemoteArtifactManifestError("remote artifact path names the workspace itself")
    return relative


def _validate_time_window(
    *,
    build_started_ns: int,
    build_finished_ns: int,
    mtime_ns: int,
    mtime_slack_ns: int,
    now_ns: int | None,
    max_build_age_ns: int | None,
) -> None:
    slack = _require_integer(mtime_slack_ns, "mtime_slack_ns")
    if build_finished_ns < build_started_ns:
        raise RemoteArtifactManifestError("build finish precedes build start")
    if mtime_ns < max(0, build_started_ns - slack):
        raise RemoteArtifactManifestError(
            "remote artifact is stale: its mtime predates the bound build"
        )
    if mtime_ns > build_finished_ns + slack:
        raise RemoteArtifactManifestError(
            "remote artifact mtime is later than the bound build finish"
        )
    if max_build_age_ns is not None and now_ns is None:
        raise RemoteArtifactManifestError("max_build_age_ns requires now_ns")
    if now_ns is None:
        return
    current = _require_integer(now_ns, "now_ns")
    if build_finished_ns > current + slack:
        raise RemoteArtifactManifestError("bound build finish is in the future")
    if max_build_age_ns is not None:
        maximum_age = _require_integer(max_build_age_ns, "max_build_age_ns")
        if current - build_finished_ns > maximum_age:
            raise RemoteArtifactManifestError("bound build is older than the accepted age")


def _stable_file_fingerprint(path: Path, *, purpose: str) -> _FileFingerprint:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise RemoteArtifactManifestError(f"{purpose} does not exist: {path}") from exc

    digest = hashlib.sha256()
    try:
        with resolved.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise RemoteArtifactManifestError(f"{purpose} is not a regular file: {resolved}")
            while chunk := handle.read(_HASH_CHUNK_SIZE):
                digest.update(chunk)
            after = os.fstat(handle.fileno())
        final = resolved.stat()
    except RemoteArtifactManifestError:
        raise
    except OSError as exc:
        raise RemoteArtifactManifestError(f"cannot read {purpose}: {resolved}") from exc

    identity_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    before_identity = tuple(getattr(before, field) for field in identity_fields)
    after_identity = tuple(getattr(after, field) for field in identity_fields)
    final_identity = tuple(getattr(final, field) for field in identity_fields)
    if before_identity != after_identity or after_identity != final_identity:
        raise RemoteArtifactManifestError(f"{purpose} changed while it was being hashed")
    return _FileFingerprint(
        size=after.st_size,
        mtime_ns=after.st_mtime_ns,
        sha256=digest.hexdigest(),
    )


def _parse_manifest(
    payload: Mapping[str, Any],
    *,
    expected_module: str,
    expected_profile: str,
    expected_workspace_id: str,
    expected_command_id: str,
    expected_remote_root: str,
    now_ns: int | None,
    max_build_age_ns: int | None,
    mtime_slack_ns: int,
) -> RemoteArtifactManifest:
    if not isinstance(payload, Mapping):
        raise RemoteArtifactManifestError("artifact manifest must be a mapping")
    fields = frozenset(payload)
    if any(not isinstance(field, str) for field in fields):
        raise RemoteArtifactManifestError("artifact manifest field names must be strings")
    missing = sorted(_MANIFEST_FIELDS - fields)
    extra = sorted(fields - _MANIFEST_FIELDS)
    if missing:
        raise RemoteArtifactManifestError(
            f"artifact manifest is missing required fields: {', '.join(missing)}"
        )
    if extra:
        raise RemoteArtifactManifestError(
            f"artifact manifest contains unsupported fields: {', '.join(extra)}"
        )
    if payload["schema"] != REMOTE_ARTIFACT_MANIFEST_SCHEMA:
        raise RemoteArtifactManifestError("artifact manifest schema is not supported")
    if type(payload["version"]) is not int or payload["version"] != REMOTE_ARTIFACT_MANIFEST_VERSION:
        raise RemoteArtifactManifestError("artifact manifest version is not supported")

    remote_path = _require_canonical_remote_path(payload["remote_path"], "remote_path")
    remote_root = _require_canonical_remote_path(expected_remote_root, "expected_remote_root")
    _require_remote_descendant(remote_path, remote_root)

    expected_context = {
        "module": _require_context_value(expected_module, "expected_module"),
        "profile": _require_context_value(expected_profile, "expected_profile"),
        "workspace_id": _require_context_value(expected_workspace_id, "expected_workspace_id"),
        "command_id": _require_context_value(expected_command_id, "expected_command_id"),
    }
    actual_context = {
        field: _require_context_value(payload[field], field) for field in expected_context
    }
    for field, expected in expected_context.items():
        if actual_context[field] != expected:
            raise RemoteArtifactManifestError(
                f"artifact manifest {field} does not match the active build context"
            )

    build_started_ns = _require_integer(payload["build_started_ns"], "build_started_ns")
    build_finished_ns = _require_integer(payload["build_finished_ns"], "build_finished_ns")
    size = _require_integer(payload["size"], "size", minimum=1)
    mtime_ns = _require_integer(payload["mtime_ns"], "mtime_ns")
    sha256 = payload["sha256"]
    if not isinstance(sha256, str) or not _SHA256_PATTERN.fullmatch(sha256):
        raise RemoteArtifactManifestError("artifact manifest sha256 is invalid")
    _validate_time_window(
        build_started_ns=build_started_ns,
        build_finished_ns=build_finished_ns,
        mtime_ns=mtime_ns,
        mtime_slack_ns=mtime_slack_ns,
        now_ns=now_ns,
        max_build_age_ns=max_build_age_ns,
    )
    return RemoteArtifactManifest(
        schema=REMOTE_ARTIFACT_MANIFEST_SCHEMA,
        version=REMOTE_ARTIFACT_MANIFEST_VERSION,
        remote_path=remote_path,
        module=actual_context["module"],
        profile=actual_context["profile"],
        workspace_id=actual_context["workspace_id"],
        command_id=actual_context["command_id"],
        build_started_ns=build_started_ns,
        build_finished_ns=build_finished_ns,
        size=size,
        mtime_ns=mtime_ns,
        sha256=sha256,
    )


def create_remote_artifact_manifest(
    artifact_path: str | Path,
    *,
    remote_root: str | Path,
    module: str,
    profile: str,
    workspace_id: str,
    command_id: str,
    build_started_ns: int,
    build_finished_ns: int,
    mtime_slack_ns: int = 0,
) -> dict[str, str | int]:
    """Create a manifest from the remote file itself, never caller-supplied file facts."""

    try:
        canonical_root = Path(remote_root).expanduser().resolve(strict=True)
    except OSError as exc:
        raise RemoteArtifactManifestError(
            f"remote workspace does not exist: {remote_root}"
        ) from exc
    if not canonical_root.is_dir():
        raise RemoteArtifactManifestError(
            f"remote workspace is not a directory: {canonical_root}"
        )
    try:
        canonical_path = Path(artifact_path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise RemoteArtifactManifestError(
            f"remote build artifact does not exist: {artifact_path}"
        ) from exc
    canonical_remote_path = _require_canonical_remote_path(
        canonical_path.as_posix(),
        "remote_path",
    )
    canonical_remote_root = _require_canonical_remote_path(
        canonical_root.as_posix(),
        "remote_root",
    )
    _require_remote_descendant(canonical_remote_path, canonical_remote_root)
    fingerprint = _stable_file_fingerprint(canonical_path, purpose="remote build artifact")
    payload: dict[str, str | int] = {
        "schema": REMOTE_ARTIFACT_MANIFEST_SCHEMA,
        "version": REMOTE_ARTIFACT_MANIFEST_VERSION,
        "remote_path": canonical_remote_path,
        "module": module,
        "profile": profile,
        "workspace_id": workspace_id,
        "command_id": command_id,
        "build_started_ns": build_started_ns,
        "build_finished_ns": build_finished_ns,
        "size": fingerprint.size,
        "mtime_ns": fingerprint.mtime_ns,
        "sha256": fingerprint.sha256,
    }
    return _parse_manifest(
        payload,
        expected_module=module,
        expected_profile=profile,
        expected_workspace_id=workspace_id,
        expected_command_id=command_id,
        expected_remote_root=canonical_remote_root,
        now_ns=None,
        max_build_age_ns=None,
        mtime_slack_ns=mtime_slack_ns,
    ).to_dict()


def validate_remote_artifact_manifest(
    payload: Mapping[str, Any],
    *,
    expected_module: str,
    expected_profile: str,
    expected_workspace_id: str,
    expected_command_id: str,
    expected_remote_root: str,
    now_ns: int | None = None,
    max_build_age_ns: int | None = None,
    mtime_slack_ns: int = 0,
) -> RemoteArtifactManifest:
    """Validate a closed manifest against trusted build-transaction context."""

    return _parse_manifest(
        payload,
        expected_module=expected_module,
        expected_profile=expected_profile,
        expected_workspace_id=expected_workspace_id,
        expected_command_id=expected_command_id,
        expected_remote_root=expected_remote_root,
        now_ns=now_ns,
        max_build_age_ns=max_build_age_ns,
        mtime_slack_ns=mtime_slack_ns,
    )


def verify_mounted_artifact(
    payload: Mapping[str, Any],
    *,
    mounted_root: str | Path,
    remote_root: str,
    expected_module: str,
    expected_profile: str,
    expected_workspace_id: str,
    expected_command_id: str,
    now_ns: int | None = None,
    max_build_age_ns: int | None = None,
    mtime_slack_ns: int = 0,
) -> Path:
    """Map the trusted remote path into the mount and re-hash the local file."""

    manifest = validate_remote_artifact_manifest(
        payload,
        expected_module=expected_module,
        expected_profile=expected_profile,
        expected_workspace_id=expected_workspace_id,
        expected_command_id=expected_command_id,
        expected_remote_root=remote_root,
        now_ns=now_ns,
        max_build_age_ns=max_build_age_ns,
        mtime_slack_ns=mtime_slack_ns,
    )
    canonical_remote_root = _require_canonical_remote_path(remote_root, "remote_root")
    relative = _require_remote_descendant(manifest.remote_path, canonical_remote_root)
    try:
        mount = Path(mounted_root).expanduser().resolve(strict=True)
    except OSError as exc:
        raise RemoteArtifactManifestError(f"mounted artifact root does not exist: {mounted_root}") from exc
    if not mount.is_dir():
        raise RemoteArtifactManifestError(f"mounted artifact root is not a directory: {mount}")

    candidate = mount.joinpath(*relative.parts)
    try:
        local_path = candidate.resolve(strict=True)
        local_path.relative_to(mount)
    except (OSError, ValueError) as exc:
        raise RemoteArtifactManifestError(
            f"mounted artifact escapes or is missing from the expected root: {candidate}"
        ) from exc
    fingerprint = _stable_file_fingerprint(local_path, purpose="mounted build artifact")
    if fingerprint.size != manifest.size:
        raise RemoteArtifactManifestError("mounted artifact size does not match remote manifest")
    if fingerprint.sha256 != manifest.sha256:
        raise RemoteArtifactManifestError("mounted artifact sha256 does not match remote manifest")
    return local_path
