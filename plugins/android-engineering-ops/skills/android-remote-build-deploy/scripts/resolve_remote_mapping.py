#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path


PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from android_engineering_ops.project_registry import resolve_project_mapping


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve a local Android source path to its registered remote build mapping."
    )
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--registry-dir", type=Path, default=Path.home() / ".servers" / "projects")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.project.is_absolute():
        raise SystemExit("--project must be an absolute path")
    mapping = resolve_project_mapping(args.project, args.registry_dir)
    if not mapping:
        raise SystemExit(f"no registered remote mapping for project: {args.project}")
    output_fields = (
        ("PROJECT_ID", "project_id"),
        ("SSH_HOST", "ssh_host"),
        ("REMOTE_ROOT", "remote_root"),
        ("PROJECT_ROOT", "project_root"),
        ("WORKING_SUBPATH", "working_subpath"),
        ("REMOTE_WORKING_PATH", "remote_working_path"),
        ("ARTIFACT_BRIDGE_PATH", "artifact_bridge_path"),
        ("MOUNT_TRANSPORT", "mount_transport"),
        ("PLATFORM", "platform"),
        ("SDK_NAME", "sdk_name"),
        ("MAPPING_REGISTRY", "registry_path"),
    )
    for output_name, field in output_fields:
        value = mapping.get(field, "")
        if value:
            print(f"{output_name}={shlex.quote(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
