#!/usr/bin/env python3
"""Remote-only CLI for creating a closed build artifact manifest."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_LIB = SCRIPT_DIR.parents[3] / "lib"
for candidate in (SCRIPT_DIR, PLUGIN_LIB):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from android_framework_ops.remote_artifact_manifest import (  # noqa: E402
    RemoteArtifactManifestError,
    create_remote_artifact_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an android-remote-build-artifact-manifest-v1 from a remote file."
    )
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--remote-root", required=True, type=Path)
    parser.add_argument("--module", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--command-id", required=True)
    parser.add_argument("--build-started-ns", required=True, type=int)
    parser.add_argument("--build-finished-ns", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def atomic_write_json(path: Path, payload: dict[str, str | int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    try:
        payload = create_remote_artifact_manifest(
            args.artifact,
            remote_root=args.remote_root,
            module=args.module,
            profile=args.profile,
            workspace_id=args.workspace_id,
            command_id=args.command_id,
            build_started_ns=args.build_started_ns,
            build_finished_ns=args.build_finished_ns,
        )
    except RemoteArtifactManifestError as exc:
        raise SystemExit(f"REMOTE_ARTIFACT_MANIFEST_REJECTED {exc}") from exc
    atomic_write_json(args.out, payload)
    print(f"REMOTE_ARTIFACT_MANIFEST_OK path={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
