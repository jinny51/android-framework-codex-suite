#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PLUGIN_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from android_framework_ops.json_io import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Push remote Android build artifacts with local adb.")
    parser.add_argument("--artifact", action="append", type=Path, required=True)
    parser.add_argument("--dest", action="append", default=[])
    parser.add_argument("--product-out", type=Path)
    parser.add_argument("--destinations-file", type=Path)
    parser.add_argument("--learn-destinations", action="store_true")
    parser.add_argument("--adb-serial", default="")
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--remote-build-host", default="")
    parser.add_argument("--remote-source-root", default="")
    parser.add_argument("--remote-build-command", default="")
    parser.add_argument("--remote-build-profile", default="")
    parser.add_argument("--remote-artifact", action="append", default=[])
    parser.add_argument("--artifact-sha1", action="append", default=[])
    parser.add_argument("--artifact-transfer", default="")
    parser.add_argument("--reboot", action="store_true")
    parser.add_argument("--wait-boot", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def read_destination_memory(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in payload.items()
        if str(key).strip() and str(value).strip()
    }


def artifact_relative_path(artifact: Path, product_out: Path | None) -> str:
    if product_out is None:
        return ""
    try:
        return artifact.resolve().relative_to(product_out.resolve()).as_posix()
    except (OSError, ValueError):
        return ""


def infer_destination(artifact: Path, product_out: Path | None, memory: dict[str, str]) -> str:
    relative = artifact_relative_path(artifact, product_out)
    if not relative:
        return ""
    if relative in memory:
        return memory[relative]
    partition = relative.split("/", 1)[0]
    if partition in {"system", "system_ext", "product", "vendor", "odm"}:
        return "/" + relative
    return ""


def adb_command() -> list[str]:
    value = os.environ.get("ADB", "adb").strip()
    command = shlex.split(value) if value else ["adb"]
    executable = command[0]
    if not (Path(executable).is_file() or shutil.which(executable)):
        raise SystemExit("adb not found; set ADB to the local adb executable")
    return command


def path_for_adb(path: Path, command: list[str]) -> str:
    if command[0].lower().endswith(".exe") and shutil.which("wslpath"):
        converted = subprocess.run(
            ["wslpath", "-w", str(path)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        return converted
    return str(path)


def run_adb(command: list[str], serial: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    full = [*command]
    if serial:
        full.extend(["-s", serial])
    full.extend(args)
    return subprocess.run(full, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def default_evidence_path(args: argparse.Namespace) -> Path | None:
    if args.evidence_out:
        return args.evidence_out
    configured = os.environ.get("CODEX_BUILD_DELIVERY_EVIDENCE", "").strip()
    if configured:
        return Path(configured).expanduser()
    if args.destinations_file and ".codex" in args.destinations_file.parts:
        index = args.destinations_file.parts.index(".codex")
        root = Path(*args.destinations_file.parts[:index])
        return root / ".codex" / "evidence" / "latest-build-delivery.json"
    if (Path.cwd() / ".codex").is_dir():
        return Path.cwd() / ".codex" / "evidence" / "latest-build-delivery.json"
    return None


def delivery_evidence(
    args: argparse.Namespace,
    pairs: list[tuple[Path, str]],
) -> dict[str, Any]:
    adb_prefix = f"adb -s {args.adb_serial}" if args.adb_serial else "adb"
    remote_artifacts = [
        {
            "path": path,
            "sha1": args.artifact_sha1[index] if index < len(args.artifact_sha1) else "",
        }
        for index, path in enumerate(args.remote_artifact)
    ]
    adb_actions = [f"{adb_prefix} push {artifact} {dest}" for artifact, dest in pairs]
    device_restarts: list[str] = []
    if args.reboot:
        device_restarts.append(f"{adb_prefix} reboot")
    if args.wait_boot:
        device_restarts.append(f"{adb_prefix} wait-for-device")
    return {
        "kind": "verification_result",
        "result": "INFO" if args.dry_run else "PASS",
        "method": "device",
        "summary": (
            "dry-run remote build artifact delivery evidence"
            if args.dry_run
            else "remote build artifact delivered to local adb device"
        ),
        "build": [],
        "device": args.adb_serial,
        "steps": [*adb_actions, *device_restarts],
        "remote_build": {
            "host": args.remote_build_host,
            "source_root": args.remote_source_root,
            "command": args.remote_build_command,
            "profile": args.remote_build_profile,
            "artifacts": remote_artifacts,
        },
        "local_delivery": {
            "transfer": args.artifact_transfer,
            "local_artifacts": [str(artifact) for artifact, _ in pairs],
            "adb_serial": args.adb_serial,
            "adb_actions": adb_actions,
            "device_restarts": device_restarts,
        },
    }


def main() -> int:
    args = parse_args()
    if args.learn_destinations and args.destinations_file is None:
        raise SystemExit("--learn-destinations requires --destinations-file")
    memory = read_destination_memory(args.destinations_file)
    pairs: list[tuple[Path, str]] = []
    for index, artifact in enumerate(args.artifact):
        if not artifact.is_file():
            raise SystemExit(f"artifact not found: {artifact}")
        destination = args.dest[index] if index < len(args.dest) else ""
        destination = destination or infer_destination(artifact, args.product_out, memory)
        if not destination:
            raise SystemExit(f"cannot infer destination for {artifact}; provide --dest")
        pairs.append((artifact.resolve(), destination))

    command = adb_command()
    if args.dry_run:
        for artifact, destination in pairs:
            print(f"ADB push {artifact} {destination}")
    else:
        run_adb(command, args.adb_serial, "wait-for-device")
        run_adb(command, args.adb_serial, "root", check=False)
        run_adb(command, args.adb_serial, "remount")
        for artifact, destination in pairs:
            print(f"PUSH {artifact} -> {destination}")
            run_adb(command, args.adb_serial, "push", path_for_adb(artifact, command), destination)
            relative = artifact_relative_path(artifact, args.product_out)
            if args.learn_destinations and relative:
                memory[relative] = destination
        run_adb(command, args.adb_serial, "shell", "sync", check=False)
        if args.reboot:
            run_adb(command, args.adb_serial, "reboot")
        if args.wait_boot:
            run_adb(command, args.adb_serial, "wait-for-device")
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                result = run_adb(command, args.adb_serial, "shell", "getprop", "sys.boot_completed", check=False)
                if result.stdout.strip().replace("\r", "") == "1":
                    print("BOOT_OK")
                    break
                time.sleep(1)
            else:
                raise SystemExit("device did not finish booting within 300 seconds")

    if args.learn_destinations and not args.dry_run:
        write_json(args.destinations_file, memory)
        print(f"DESTINATION_MEMORY file={args.destinations_file}")

    evidence_path = default_evidence_path(args)
    if evidence_path:
        write_json(evidence_path, delivery_evidence(args, pairs))
        print(f"EVIDENCE {evidence_path}")
    print(f"PUSH_OK count={len(pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
