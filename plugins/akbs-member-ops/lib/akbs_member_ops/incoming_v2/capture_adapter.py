"""Strict, read-only preflight for android-patch-capture v2 packages.

Phase 2 deliberately stops before materializing an AKBS Android change v2
package.  The evidence-group adapter input contracts and server writers are not
frozen, so a structurally valid capture produces a hash-bound diagnostic with a
BLOCKED result, never a synthetic adapter PASS document.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any

from .schema import DRAFT_2020_12_SCHEMA, SchemaError, load_json_bytes, validate_document
from .validation import (
    AndroidChangeV2Error,
    PROFILE_PATH,
    _load_contract,
    _required_groups,
    _validate_profile_registry,
    canonical_json_sha256,
    writer_status,
)


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
CAPTURE_SCHEMA_PATH = (
    PLUGIN_ROOT / "contracts" / "android-patch-capture" / "v2" / "capture-package.schema.json"
)
CAPTURE_IDENTITY = ("android-patch-capture-package-v2", "2.0", "android_change_capture")
CAPTURE_LAYERS = {"application", "platform", "native", "hal", "kernel", "device", "build"}
TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,255}$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES = 16 * 1024 * 1024
BUILTIN_EVIDENCE = {
    "changed-files": ("changed_files", "evidence/changed-files.json"),
    "verification-result": ("verification_result", "evidence/verification-result.json"),
    "patch-diff-facts": ("patch_diff_facts", "evidence/patch-diff-facts.json"),
    "patch-problem-summary": ("patch_problem_summary", "evidence/patch-problem-summary.json"),
    "risk-surface": ("risk_surface", "evidence/risk-surface.json"),
    "coding-standard-check": ("coding_standard_check", "evidence/coding-standard-check.json"),
    "search-before-change": ("search_before_change", "evidence/search-before-change.json"),
    "package-check": ("package_check", "evidence/package-check.json"),
    "remote-source-snapshot": ("remote_source_snapshot", "evidence/remote-source-snapshot.json"),
}


def _capture_error(message: str) -> None:
    raise AndroidChangeV2Error(f"android-patch-capture v2 preflight: {message}")


def _capture_root(value: Path) -> Path:
    supplied = value.expanduser()
    if supplied.is_symlink():
        _capture_error(f"input cannot be a symbolic link: {supplied}")
    if supplied.is_dir():
        root = supplied
    else:
        if supplied.name != "manifest.json":
            _capture_error("input must be a capture package directory or manifest.json")
        if supplied.is_symlink() or not supplied.is_file():
            _capture_error(f"manifest is not a regular file: {supplied}")
        root = supplied.parent
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        _capture_error(f"cannot resolve package root: {exc}")
    if not resolved.is_dir():
        _capture_error("package root is not a directory")
    return resolved


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _file_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)


def _require_descriptor_support() -> None:
    if (
        not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or any(function not in os.supports_dir_fd for function in (os.open, os.stat))
    ):
        _capture_error("no-follow directory-descriptor reads are unavailable")


def _normalized_path(value: object) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        _capture_error("archive path is empty, absolute, or uses a backslash")
    path = PurePosixPath(value)
    normalized = path.as_posix()
    if (
        value != normalized
        or value in {".", ".."}
        or any(part in {"", ".", ".."} for part in path.parts)
        or any("\x00" in part for part in path.parts)
    ):
        _capture_error(f"archive path is not canonical: {value!r}")
    return normalized


def _same_file(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        os.path.samestat(before, after)
        and before.st_size == after.st_size
        and before.st_mtime_ns == after.st_mtime_ns
        and before.st_ctime_ns == after.st_ctime_ns
    )


def _digest_open_file(fd: int, expected: os.stat_result, relative: str) -> dict[str, Any]:
    if not stat.S_ISREG(expected.st_mode):
        _capture_error(f"archive entry is not a regular file: {relative}")
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    size = 0
    try:
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            sha1.update(chunk)
            sha256.update(chunk)
        after = os.fstat(fd)
    except OSError as exc:
        _capture_error(f"cannot hash archive entry {relative}: {exc}")
    if not _same_file(expected, after) or size != expected.st_size:
        _capture_error(f"archive entry changed while hashing: {relative}")
    return {"sha1": sha1.hexdigest(), "sha256": sha256.hexdigest(), "size_bytes": size}


def _scan_directory(
    directory_fd: int,
    prefix: PurePosixPath,
    inventory: dict[str, dict[str, Any]],
) -> None:
    before = os.fstat(directory_fd)
    try:
        names = sorted(os.listdir(directory_fd))
    except OSError as exc:
        _capture_error(f"cannot enumerate capture directory: {exc}")
    for name in names:
        relative = _normalized_path((prefix / name).as_posix())
        try:
            entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            _capture_error(f"cannot stat archive entry {relative}: {exc}")
        if stat.S_ISLNK(entry.st_mode):
            _capture_error(f"archive contains a symbolic link: {relative}")
        if stat.S_ISDIR(entry.st_mode):
            try:
                child_fd = os.open(name, _directory_flags(), dir_fd=directory_fd)
            except OSError as exc:
                _capture_error(f"cannot securely open archive directory {relative}: {exc}")
            try:
                opened = os.fstat(child_fd)
                if not os.path.samestat(entry, opened):
                    _capture_error(f"archive directory changed while opening: {relative}")
                _scan_directory(child_fd, PurePosixPath(relative), inventory)
                rebound = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if not os.path.samestat(opened, rebound) or not stat.S_ISDIR(rebound.st_mode):
                    _capture_error(f"archive directory changed while scanning: {relative}")
            finally:
                os.close(child_fd)
            continue
        if not stat.S_ISREG(entry.st_mode):
            _capture_error(f"archive contains a special file: {relative}")
        try:
            file_fd = os.open(name, _file_flags(), dir_fd=directory_fd)
        except OSError as exc:
            _capture_error(f"cannot securely open archive entry {relative}: {exc}")
        try:
            opened = os.fstat(file_fd)
            if not os.path.samestat(entry, opened):
                _capture_error(f"archive entry changed while opening: {relative}")
            if relative in inventory:
                _capture_error(f"archive path is duplicated: {relative}")
            inventory[relative] = _digest_open_file(file_fd, opened, relative)
            rebound = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if not os.path.samestat(opened, rebound) or not stat.S_ISREG(rebound.st_mode):
                _capture_error(f"archive entry changed while scanning: {relative}")
        finally:
            os.close(file_fd)
    after = os.fstat(directory_fd)
    if not os.path.samestat(before, after) or before.st_mtime_ns != after.st_mtime_ns:
        _capture_error(f"archive directory changed while scanning: {prefix.as_posix()}")


def _open_root_view(root_fd: int) -> int:
    try:
        view_fd = os.open(".", _directory_flags(), dir_fd=root_fd)
    except OSError as exc:
        _capture_error(f"cannot reopen pinned package root: {exc}")
    if not os.path.samestat(os.fstat(root_fd), os.fstat(view_fd)):
        os.close(view_fd)
        _capture_error("pinned package root identity changed")
    return view_fd


def _assert_root_binding(root: Path, expected: os.stat_result) -> None:
    try:
        observed = os.stat(root, follow_symlinks=False)
    except OSError as exc:
        _capture_error(f"package root pathname no longer resolves: {exc}")
    if not stat.S_ISDIR(observed.st_mode) or not os.path.samestat(expected, observed):
        _capture_error("package root pathname changed during preflight")


def _archive_inventory(root_fd: int) -> dict[str, dict[str, Any]]:
    view_fd = _open_root_view(root_fd)
    try:
        inventory: dict[str, dict[str, Any]] = {}
        _scan_directory(view_fd, PurePosixPath(), inventory)
        return inventory
    finally:
        os.close(view_fd)


def _read_regular(root_fd: int, relative: str, *, max_bytes: int = MAX_JSON_BYTES) -> bytes:
    normalized = _normalized_path(relative)
    parts = PurePosixPath(normalized).parts
    parent_fd = _open_root_view(root_fd)
    opened_directories = [parent_fd]
    try:
        for part in parts[:-1]:
            try:
                child_fd = os.open(part, _directory_flags(), dir_fd=parent_fd)
            except OSError as exc:
                _capture_error(f"cannot securely open parent of {normalized}: {exc}")
            opened_directories.append(child_fd)
            parent_fd = child_fd
        try:
            file_fd = os.open(parts[-1], _file_flags(), dir_fd=parent_fd)
        except OSError as exc:
            _capture_error(f"cannot securely open {normalized}: {exc}")
        try:
            opened = os.fstat(file_fd)
            if not stat.S_ISREG(opened.st_mode):
                _capture_error(f"archive entry is not a regular file: {normalized}")
            if opened.st_size > max_bytes:
                _capture_error(f"JSON input exceeds {max_bytes} bytes: {normalized}")
            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = os.read(file_fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > max_bytes:
                    _capture_error(f"JSON input exceeds {max_bytes} bytes: {normalized}")
            after = os.fstat(file_fd)
            rebound = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            if not _same_file(opened, after) or not os.path.samestat(opened, rebound):
                _capture_error(f"archive entry changed while reading: {normalized}")
            return b"".join(chunks)
        finally:
            os.close(file_fd)
    finally:
        for directory_fd in reversed(opened_directories):
            os.close(directory_fd)


def _strict_json(root_fd: int, display_root: Path, relative: str) -> tuple[bytes, dict[str, Any]]:
    raw = _read_regular(root_fd, relative)
    try:
        return raw, load_json_bytes(raw, label=str(display_root / relative))
    except SchemaError as exc:
        _capture_error(str(exc))
    raise AssertionError("unreachable")


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _capture_error(f"{label} must be an object")
    return value


def _require_nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _capture_error(f"{label} must be non-empty text")
    return value


def _require_token(value: Any, label: str) -> str:
    text = _require_nonempty_text(value, label)
    if not TOKEN_RE.fullmatch(text):
        _capture_error(f"{label} must be a controlled token")
    return text


def _require_id(value: Any, label: str) -> str:
    text = _require_nonempty_text(value, label)
    if not ID_RE.fullmatch(text):
        _capture_error(f"{label} must be a controlled ID")
    return text


def _unique_rows(value: Any, label: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(value, list) or not value or any(not isinstance(item, dict) for item in value):
        _capture_error(f"{label} must be a non-empty array of objects")
    identifiers = [_require_id(item.get("id"), f"{label}[].id") for item in value]
    if len(identifiers) != len(set(identifiers)):
        _capture_error(f"{label} IDs must be unique")
    return value, {item["id"]: item for item in value}


def _component_ids(value: Any, known: set[str], label: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
        _capture_error(f"{label} must be a non-empty component ID array")
    if len(value) != len(set(value)) or not set(value).issubset(known):
        _capture_error(f"{label} contains duplicate or unknown component IDs")
    return value


def _declared_inventory(manifest: dict[str, Any]) -> dict[str, tuple[str, int]]:
    declaration = _require_object(manifest.get("file_inventory"), "file_inventory")
    if (
        declaration.get("algorithm") != "sha256"
        or declaration.get("scope") != "all_regular_package_files_except_manifest.json"
        or declaration.get("manifest_self_hash_excluded") is not True
    ):
        _capture_error("file_inventory algorithm/scope/self-hash declaration differs")
    rows = declaration.get("files")
    if not isinstance(rows, list) or not rows or any(not isinstance(item, dict) for item in rows):
        _capture_error("file_inventory.files must be a non-empty object array")
    declared: dict[str, tuple[str, int]] = {}
    for row in rows:
        if set(row) != {"path", "size_bytes", "sha256"}:
            _capture_error("file_inventory row fields differ")
        path = _normalized_path(row.get("path"))
        sha256 = row.get("sha256")
        size = row.get("size_bytes")
        if path == "manifest.json" or path in declared:
            _capture_error("file_inventory contains manifest.json or a duplicate path")
        if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
            _capture_error(f"file_inventory SHA-256 is malformed: {path}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            _capture_error(f"file_inventory size is malformed: {path}")
        declared[path] = (sha256, size)
    return declared


def _validate_identity_status_authority(manifest: dict[str, Any]) -> None:
    identity = (manifest.get("schema"), manifest.get("schema_version"), manifest.get("package_type"))
    if identity != CAPTURE_IDENTITY:
        _capture_error(
            "package identity is not android-patch-capture-package-v2/2.0/android_change_capture; "
            "legacy/v1 fallback is forbidden"
        )
    if "change_domain" in manifest:
        _capture_error("legacy change_domain is not a canonical capture facet")
    for field in (
        "change_id",
        "readme",
        "project",
        "platform_token",
        "platform",
        "android_version",
        "summary",
        "implementation_origin",
        "workflow_contract",
        "captured_by",
        "created_at",
    ):
        _require_nonempty_text(manifest.get(field), field)
    if _normalized_path(manifest.get("readme")) != "README.md":
        _capture_error("readme must be the root README.md")
    if (
        manifest.get("status") != "validated"
        or manifest.get("declared_status") != "validated"
        or manifest.get("effective_status") != "validated"
        or manifest.get("status_was_upgraded") is not False
    ):
        _capture_error("capture must be honestly validated without status promotion")
    authority = _require_object(manifest.get("authority"), "authority")
    expected_authority = {
        "owner": "android-patch-capture",
        "local_capture_only": True,
        "can_confirm_or_downgrade_status_only": True,
        "can_upload": False,
        "can_allocate_server_package_id": False,
        "can_materialize_knowledge": False,
    }
    if authority != expected_authority:
        _capture_error("capture authority differs from the local-only contract")
    submission = _require_object(manifest.get("server_submission"), "server_submission")
    if (
        submission.get("v2_writer") != "disabled"
        or submission.get("v2_submission_allowed") is not False
        or submission.get("server_qualified") is not False
    ):
        _capture_error("capture server_submission authority is not writer-off")


def _validate_components_and_payloads(
    manifest: dict[str, Any],
    inventory: dict[str, dict[str, Any]],
    root_fd: int,
    display_root: Path,
) -> dict[str, Any]:
    component_rows, components = _unique_rows(manifest.get("components"), "components")
    component_ids = set(components)
    for component in component_rows:
        allowed = {"id", "layer", "type", "partition", "ownership", "display_name", "qualifiers"}
        required = {"id", "layer", "type", "partition", "ownership"}
        if not required.issubset(component) or set(component) - allowed:
            _capture_error(f"component fields differ: {component.get('id')!r}")
        _require_token(component.get("id"), "component.id")
        if component.get("layer") not in CAPTURE_LAYERS:
            _capture_error(f"component layer is unsupported: {component.get('id')!r}")
        for facet in ("type", "partition", "ownership"):
            _require_token(component.get(facet), f"component {component['id']}.{facet}")
        qualifiers = component.get("qualifiers", [])
        if (
            not isinstance(qualifiers, list)
            or len(qualifiers) != len(set(qualifiers))
            or any(not isinstance(item, str) or not TOKEN_RE.fullmatch(item) for item in qualifiers)
        ):
            _capture_error(f"component qualifiers differ: {component['id']}")
    primary = manifest.get("primary_component_id")
    if primary not in components:
        _capture_error("primary_component_id does not resolve to components[]")
    compatibility_component = manifest.get("component")
    if compatibility_component is not None:
        primary_facets = {
            key: components[primary][key] for key in ("layer", "type", "partition", "ownership")
        }
        if len(component_rows) != 1 or compatibility_component != primary_facets:
            _capture_error("single-component compatibility projection differs from components[]")

    repository_rows, repositories = _unique_rows(manifest.get("git_repositories"), "git_repositories")
    repository_paths: set[str] = set()
    for repository in repository_rows:
        _require_nonempty_text(repository.get("repo_path"), f"repository {repository['id']}.repo_path")
        if repository["repo_path"] in repository_paths:
            _capture_error("git_repositories repo_path values must be unique")
        repository_paths.add(repository["repo_path"])
        _require_nonempty_text(repository.get("root"), f"repository {repository['id']}.root")
        _component_ids(repository.get("component_ids"), component_ids, f"repository {repository['id']}.component_ids")
        _require_object(repository.get("git"), f"repository {repository['id']}.git")

    patch_rows, patches = _unique_rows(manifest.get("patches"), "patches")
    patch_paths: set[str] = set()
    changed_components: set[str] = set()
    for patch in patch_rows:
        if "change_domain" in patch:
            _capture_error(f"patch contains legacy change_domain: {patch['id']}")
        path = _normalized_path(patch.get("path"))
        if path in patch_paths or not path.startswith("patches/"):
            _capture_error("patch path is duplicate or outside patches/")
        patch_paths.add(path)
        repository_id = patch.get("repository_id")
        if repository_id not in repositories:
            _capture_error(f"patch repository_id is unresolved: {patch['id']}")
        repository = repositories[repository_id]
        if patch.get("repo_path") != repository.get("repo_path"):
            _capture_error(f"patch repo_path differs from its repository: {patch['id']}")
        ids = _component_ids(patch.get("component_ids"), component_ids, f"patch {patch['id']}.component_ids")
        if set(ids) != set(repository["component_ids"]):
            _capture_error(f"patch component_ids differ from its explicit repository mapping: {patch['id']}")
        changed_components.update(ids)
        declared_sha1 = patch.get("content_sha1")
        actual = inventory.get(path)
        if not isinstance(declared_sha1, str) or not SHA1_RE.fullmatch(declared_sha1):
            _capture_error(f"patch content_sha1 is malformed: {patch['id']}")
        if actual is None or actual["sha1"] != declared_sha1:
            _capture_error(f"patch content_sha1 differs from bytes: {patch['id']}")
        if patch.get("status") != "validated":
            _capture_error(f"patch status is not validated: {patch['id']}")
        compatibility_patch_component = patch.get("component")
        if compatibility_patch_component is not None:
            expected_component = {
                key: components[ids[0]][key]
                for key in ("layer", "type", "partition", "ownership")
            }
            if len(component_rows) != 1 or len(ids) != 1 or compatibility_patch_component != expected_component:
                _capture_error(f"patch compatibility component differs: {patch['id']}")
        facts = patch.get("facts")
        if isinstance(facts, dict) and facts.get("content_sha1") not in {None, "", declared_sha1}:
            _capture_error(f"patch facts.content_sha1 differs: {patch['id']}")
    if changed_components != component_ids:
        _capture_error("every component must bind at least one patch")

    evidence_rows, evidence = _unique_rows(manifest.get("evidence"), "evidence")
    evidence_paths: set[str] = set()
    evidence_payloads: dict[str, dict[str, Any]] = {}
    for item in evidence_rows:
        path = _normalized_path(item.get("path"))
        if path in evidence_paths:
            _capture_error("evidence paths must be unique")
        evidence_paths.add(path)
        if path not in inventory or not path.startswith("evidence/") or not path.endswith(".json"):
            _capture_error(f"evidence path is missing or outside evidence/: {item['id']}")
        _component_ids(item.get("component_ids"), component_ids, f"evidence {item['id']}.component_ids")
        _require_nonempty_text(item.get("contract"), f"evidence {item['id']}.contract")
        claims = item.get("declared_claims")
        if (
            not isinstance(claims, list)
            or not claims
            or len(claims) != len(set(claims))
            or any(not isinstance(claim, str) or not claim.strip() for claim in claims)
        ):
            _capture_error(f"evidence declared_claims differ: {item['id']}")
        raw, payload = _strict_json(root_fd, display_root, path)
        observed = inventory[path]
        if (
            len(raw) != observed["size_bytes"]
            or hashlib.sha256(raw).hexdigest() != observed["sha256"]
        ):
            _capture_error(f"evidence bytes differ from the pinned archive inventory: {item['id']}")
        evidence_payloads[item["id"]] = payload
        expected_builtin = BUILTIN_EVIDENCE.get(item["id"])
        if expected_builtin is not None and (item.get("kind"), path) != expected_builtin:
            _capture_error(f"built-in evidence kind/path differs: {item['id']}")
        payload_kind = payload.get("kind")
        if payload_kind is not None and payload_kind != item.get("kind"):
            _capture_error(f"evidence manifest kind differs from JSON payload: {item['id']}")
        if expected_builtin is None and payload_kind is None:
            _capture_error(f"external evidence JSON does not bind its kind: {item['id']}")
        payload_result = (
            payload.get("status") if item.get("kind") == "package_check" else payload.get("result")
        )
        if payload_result is None:
            if item.get("result") != "INFO":
                _capture_error(f"evidence result is not bound by its JSON payload: {item['id']}")
        elif payload_result != item.get("result"):
            _capture_error(f"evidence manifest result differs from JSON payload: {item['id']}")

    binding_rows = manifest.get("qualification_bindings")
    if not isinstance(binding_rows, list) or not binding_rows or any(not isinstance(item, dict) for item in binding_rows):
        _capture_error("qualification_bindings must be a non-empty object array")
    bindings: dict[str, dict[str, Any]] = {}
    for binding in binding_rows:
        component_id = binding.get("component_id")
        if component_id not in components or component_id in bindings:
            _capture_error("qualification_bindings component IDs must cover components uniquely")
        if binding.get("contract") != "android-patch-capture-local-qualification-v1":
            _capture_error(f"capture qualification contract differs: {component_id}")
        expected_repositories = {
            row["id"] for row in repository_rows if component_id in row["component_ids"]
        }
        expected_patches = {row["id"] for row in patch_rows if component_id in row["component_ids"]}
        repository_ids = binding.get("repository_ids")
        patch_ids = binding.get("patch_ids")
        evidence_ids = binding.get("evidence_ids")
        if (
            not isinstance(repository_ids, list)
            or any(not isinstance(item, str) for item in repository_ids)
            or len(repository_ids) != len(set(repository_ids))
            or set(repository_ids) != expected_repositories
        ):
            _capture_error(f"qualification repository binding differs: {component_id}")
        if (
            not isinstance(patch_ids, list)
            or any(not isinstance(item, str) for item in patch_ids)
            or len(patch_ids) != len(set(patch_ids))
            or set(patch_ids) != expected_patches
        ):
            _capture_error(f"qualification patch binding differs: {component_id}")
        if (
            not isinstance(evidence_ids, list)
            or not evidence_ids
            or any(not isinstance(item, str) for item in evidence_ids)
            or len(evidence_ids) != len(set(evidence_ids))
            or not set(evidence_ids).issubset(evidence)
            or any(component_id not in evidence[evidence_id]["component_ids"] for evidence_id in evidence_ids)
        ):
            _capture_error(f"qualification evidence binding differs: {component_id}")
        claims = binding.get("declared_claims")
        if (
            not isinstance(claims, list)
            or not claims
            or any(not isinstance(item, str) or not item.strip() for item in claims)
            or len(claims) != len(set(claims))
        ):
            _capture_error(f"qualification declared claims differ: {component_id}")
        bindings[component_id] = binding
    if set(bindings) != component_ids:
        _capture_error("qualification_bindings must cover every component exactly once")

    coding = _require_object(manifest.get("coding_standard_check"), "coding_standard_check")
    coding_path = _normalized_path(coding.get("path"))
    coding_rows = [item for item in evidence_rows if item.get("kind") == "coding_standard_check"]
    if (
        len(coding_rows) != 1
        or coding_rows[0]["id"] != "coding-standard-check"
        or coding_path != coding_rows[0]["path"]
        or coding_path not in inventory
        or coding.get("result") != "PASS"
        or evidence_payloads["coding-standard-check"].get("result") != "PASS"
    ):
        _capture_error("validated capture requires hash-bound PASS coding-standard-check evidence")
    package_checks = [item for item in evidence_rows if item.get("kind") == "package_check"]
    if (
        len(package_checks) != 1
        or package_checks[0]["id"] != "package-check"
        or package_checks[0].get("result") != "PASS"
    ):
        _capture_error("validated capture requires exactly one PASS package_check evidence row")
    package_check_path = _normalized_path(package_checks[0].get("path"))
    package_check = evidence_payloads["package-check"]
    if (
        package_check.get("status") != "PASS"
        or package_check.get("errors") != []
        or package_check.get("declared_package_status") != "validated"
        or package_check.get("effective_package_status") != "validated"
        or package_check.get("status_was_upgraded") is not False
    ):
        _capture_error("package_check evidence does not prove an honest validated capture")

    return {
        "components": component_rows,
        "primary_component_id": primary,
        "repositories": repository_rows,
        "patches": [
            {
                "id": item["id"],
                "path": item["path"],
                "repository_id": item["repository_id"],
                "component_ids": item["component_ids"],
                "content_sha1": item["content_sha1"],
            }
            for item in patch_rows
        ],
        "evidence_count": len(evidence_rows),
    }


def _preflight_capture_from_fd(
    root: Path,
    root_fd: int,
    root_identity: os.stat_result,
) -> dict[str, Any]:
    """Validate through one pinned directory identity."""
    manifest_raw, manifest = _strict_json(root_fd, root, "manifest.json")
    try:
        validate_document(manifest, _load_contract(CAPTURE_SCHEMA_PATH))
    except SchemaError as exc:
        _capture_error(f"capture manifest schema violation: {exc}")
    _validate_identity_status_authority(manifest)
    _assert_root_binding(root, root_identity)

    first_inventory = _archive_inventory(root_fd)
    _assert_root_binding(root, root_identity)
    declared = _declared_inventory(manifest)
    actual_declared = {
        path: (facts["sha256"], facts["size_bytes"])
        for path, facts in first_inventory.items()
        if path != "manifest.json"
    }
    if declared != actual_declared:
        _capture_error("file_inventory does not exactly bind every non-manifest regular file")
    details = _validate_components_and_payloads(
        manifest,
        first_inventory,
        root_fd,
        root,
    )
    _assert_root_binding(root, root_identity)

    # Re-read all entries after semantic validation so a concurrent mutation is
    # never accepted as one coherent capture snapshot.
    second_inventory = _archive_inventory(root_fd)
    final_manifest_raw = _read_regular(root_fd, "manifest.json")
    if first_inventory != second_inventory or manifest_raw != final_manifest_raw:
        _capture_error("capture package changed during preflight")
    _assert_root_binding(root, root_identity)

    profiles = _load_contract(PROFILE_PATH)
    _validate_profile_registry(profiles)
    workflow = manifest["workflow_contract"]
    if workflow not in profiles.get("workflow_requirements", {}):
        _capture_error(f"workflow_contract has no Android change v2 profile: {workflow}")
    required_groups: dict[str, list[str]] = {
        component["id"]: sorted(_required_groups(component, workflow, profiles))
        for component in details["components"]
    }
    registry = profiles["evidence_group_registry"]["groups"]
    group_ids = sorted({group for groups in required_groups.values() for group in groups})
    unresolved_facets = [
        f"{component['id']}.{facet}"
        for component in details["components"]
        for facet in ("type", "partition", "ownership")
        if component.get(facet) == "unknown"
    ]
    activation = profiles["writer_activation"]
    gaps: list[dict[str, Any]] = [
        {
            "code": "versioned_evidence_group_adapter_input_contracts_missing",
            "message": activation["block_reason"],
            "required_per_group": activation["required_per_group"],
            "groups": [
                {
                    "group_id": group_id,
                    "adapter_contract": registry[group_id]["adapter_contract"],
                    "adapter_version": registry[group_id]["adapter_version"],
                }
                for group_id in group_ids
            ],
        }
    ]
    if unresolved_facets:
        gaps.append(
            {
                "code": "canonical_component_facets_unresolved",
                "message": "legacy capture hints left canonical component facets unknown; no value was inferred",
                "fields": unresolved_facets,
            }
        )

    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    inventory_binding = [
        [path, facts["sha256"], facts["size_bytes"]]
        for path, facts in sorted(first_inventory.items())
    ]
    result = {
        "status": "BLOCKED",
        "operation": "adapt-capture",
        "reason_code": "android_change_v2_adapter_contracts_unavailable",
        "message": (
            "Capture preflight succeeded, but Phase 2 cannot create a canonical Android change v2 "
            "artifact until the per-evidence-group versioned adapter input contracts are activated."
        ),
        "capture": {
            "contract": "android-patch-capture-package-v2/2.0/android_change_capture",
            "schema": manifest["schema"],
            "schema_version": manifest["schema_version"],
            "package_type": manifest["package_type"],
            "package": str(root),
            "root_identity": {
                "st_dev": root_identity.st_dev,
                "st_ino": root_identity.st_ino,
            },
            "manifest_sha256": manifest_sha256,
            "archive_inventory_sha256": canonical_json_sha256(inventory_binding),
            "status": manifest["effective_status"],
            "change_id": manifest["change_id"],
            "components": details["components"],
            "primary_component_id": details["primary_component_id"],
            "repositories": [
                {
                    "id": item["id"],
                    "repo_path": item["repo_path"],
                    "component_ids": item["component_ids"],
                }
                for item in details["repositories"]
            ],
            "patches": details["patches"],
            "evidence_count": details["evidence_count"],
        },
        "preflight": {
            "schema_dialect": DRAFT_2020_12_SCHEMA,
            "schema_identity_valid": True,
            "structural_contract_valid": True,
            "validated_status_chain_valid": True,
            "local_authority_valid": True,
            "file_safety_valid": True,
            "archive_inventory_binding_valid": True,
            "patch_hash_binding_valid": True,
            "component_binding_valid": True,
            "required_groups_by_component": required_groups,
        },
        "gaps": gaps,
        "adapter": {
            "state": "blocked",
            "output_created": False,
            "client_adapter_outputs_created": False,
            "canonical_package_created": False,
            "server_qualified": False,
            "activation_phase": "Phase 4",
        },
        "writer": writer_status(),
    }
    _assert_root_binding(root, root_identity)
    return result


def preflight_capture(value: Path) -> dict[str, Any]:
    """Validate a capture fully, then return the intentional Phase-2 gap."""
    _require_descriptor_support()
    root = _capture_root(value)
    try:
        root_fd = os.open(root, _directory_flags())
    except OSError as exc:
        _capture_error(f"cannot securely open package root: {exc}")
    try:
        root_identity = os.fstat(root_fd)
        if not stat.S_ISDIR(root_identity.st_mode):
            _capture_error("opened package root is not a directory")
        _assert_root_binding(root, root_identity)
        return _preflight_capture_from_fd(root, root_fd, root_identity)
    finally:
        os.close(root_fd)
