#!/usr/bin/env python3
from __future__ import annotations

import json
import signal
import subprocess
import sys
import tempfile
from pathlib import Path


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

from validator_hygiene import RepositorySnapshot, other_files, residue_paths


def run_probe(mode: str) -> int:
    cache_dir = REPO_ROOT / "plugins" / "android-framework-ops" / "lib" / "android_framework_ops" / "__pycache__"
    generated = REPO_ROOT / f".validator-cleanup-{mode}.tmp"
    signal_line = ""
    if mode == "failure":
        signal_line = "false"
    elif mode == "sigint":
        signal_line = "kill -INT $$"
    elif mode == "sigterm":
        signal_line = "kill -TERM $$"
    script = "\n".join(
        [
            "set -euo pipefail",
            f"source {SCRIPTS_ROOT / 'validator_cleanup.sh'}",
            f"validator_cleanup_install {REPO_ROOT}",
            f"mkdir -p {cache_dir}",
            f"touch {cache_dir / (mode + '.pyc')}",
            f"touch {generated}",
            signal_line,
        ]
    )
    result = subprocess.run(["bash", "-c", script], check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if cache_dir.exists() or generated.exists():
        raise AssertionError(f"{mode} cleanup left generated artifacts")
    return result.returncode


def verify_preexisting_user_file_is_preserved() -> None:
    with tempfile.TemporaryDirectory(prefix="akbs-validator-user-file-") as temporary:
        root = Path(temporary)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        user_file = root / "user-notes.txt"
        user_file.write_text("keep me\n", encoding="utf-8")
        script = "\n".join(
            [
                "set -euo pipefail",
                f"source {SCRIPTS_ROOT / 'validator_cleanup.sh'}",
                f"validator_cleanup_install {root}",
                f"touch {root / 'generated.tmp'}",
                "false",
            ]
        )
        result = subprocess.run(["bash", "-c", script], check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            raise AssertionError("preexisting-user-file probe did not fail intentionally")
        if user_file.read_text(encoding="utf-8") != "keep me\n":
            raise AssertionError("cleanup modified or removed a preexisting user file")
        if (root / "generated.tmp").exists():
            raise AssertionError("cleanup left a generated non-allowed artifact")


def main() -> int:
    outer = RepositorySnapshot.capture(REPO_ROOT)
    if outer.residue:
        raise SystemExit("validator cleanup self-test requires a residue-free plugin source tree")
    try:
        results = {mode: run_probe(mode) for mode in ("success", "failure", "sigint", "sigterm")}
        if results["success"] != 0:
            raise AssertionError(f"success probe failed: {results['success']}")
        if results["failure"] == 0 or results["sigint"] == 0 or results["sigterm"] == 0:
            raise AssertionError(f"intentional failure/signal probes unexpectedly passed: {results}")
        verify_preexisting_user_file_is_preserved()
        if residue_paths(REPO_ROOT):
            raise AssertionError("cleanup self-test left cache or bytecode residue")
        if other_files(REPO_ROOT) != set(outer.other_files):
            raise AssertionError("cleanup self-test left a non-allowed untracked or ignored artifact")
        print(json.dumps({"status": "PASS", "probes": results, "preexisting_user_file": "preserved"}, sort_keys=True))
        return 0
    finally:
        outer.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
