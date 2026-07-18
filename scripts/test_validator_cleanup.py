#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

from validator_hygiene import (
    AKBS_ROOT,
    INVOCATION_PREFIX,
    RepositorySnapshot,
    ValidatorInvocation,
    cleanup_state_file,
    controlled_temp_root,
    other_files,
    residue_paths,
)
from validator_path_guard import (
    ABSOLUTE_ESCAPE,
    AKBS_ROOT_FORBIDDEN,
    AUTHORITY_ROOT_FORBIDDEN,
    GIT_SOURCE_FORBIDDEN,
    PARENT_ESCAPE,
    PRODUCTION_ROOT_FORBIDDEN,
    SYMLINK_ESCAPE,
    ValidatorPathError,
    guard_write_path,
)


def invocation_dirs(root: Path) -> set[Path]:
    return {path for path in root.glob(f"{INVOCATION_PREFIX}*") if path.exists() or path.is_symlink()}


def run_probe(mode: str, temp_root: Path, baseline_invocations: set[Path]) -> int:
    signal_line = ""
    if mode == "failure":
        signal_line = "false"
    elif mode == "sigint":
        signal_line = "kill -INT $$"
    elif mode == "sigterm":
        signal_line = "kill -TERM $$"
    elif mode == "sighup":
        signal_line = "kill -HUP $$"
    script = "\n".join(
        [
            "set -euo pipefail",
            f"source {SCRIPTS_ROOT / 'validator_cleanup.sh'}",
            f"validator_cleanup_install {REPO_ROOT}",
            'printf "invocation=%s\\n" "$VALIDATOR_CLEANUP_STATE_DIR"',
            'mkdir -p "$VALIDATOR_CLEANUP_TMPDIR/cache" "$VALIDATOR_CLEANUP_TMPDIR/partial-package"',
            f'touch "$VALIDATOR_CLEANUP_TMPDIR/cache/{mode}.pyc"',
            'touch "$VALIDATOR_CLEANUP_TMPDIR/partial-package/diagnostic.log"',
            f"python3 -m py_compile {SCRIPTS_ROOT / 'validator_hygiene.py'}",
            signal_line,
        ]
    )
    env = os.environ.copy()
    env["AKBS_PLUGIN_TMP_ROOT"] = str(temp_root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        ["bash", "-c", script],
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    invocation_line = next((line for line in result.stdout.splitlines() if line.startswith("invocation=")), "")
    if not invocation_line:
        raise AssertionError(f"{mode} probe did not report its invocation: {result.stderr}")
    invocation = Path(invocation_line.partition("=")[2])
    if invocation.exists() or invocation.is_symlink():
        raise AssertionError(f"{mode} cleanup left its owned invocation: {invocation}")
    if invocation_dirs(temp_root) != baseline_invocations:
        raise AssertionError(f"{mode} cleanup changed another invocation")
    return result.returncode


def verify_preexisting_and_concurrent_user_files_are_preserved(temp_root: Path) -> None:
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="akbs-validator-user-file-", dir=temp_root) as temporary:
        root = Path(temporary)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        user_file = root / "user-notes.txt"
        user_file.write_text("keep me\n", encoding="utf-8")
        generated = root / "concurrent-user-file.tmp"
        script = "\n".join(
            [
                "set -euo pipefail",
                f"source {SCRIPTS_ROOT / 'validator_cleanup.sh'}",
                f"validator_cleanup_install {root}",
                f"touch {generated}",
                "false",
            ]
        )
        env = os.environ.copy()
        env["AKBS_PLUGIN_TMP_ROOT"] = str(temp_root)
        result = subprocess.run(
            ["bash", "-c", script],
            env=env,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            raise AssertionError("unowned-file probe did not fail intentionally")
        if "cleanup refused" not in result.stderr:
            raise AssertionError(f"cleanup did not report the unowned repository path: {result.stderr}")
        if user_file.read_text(encoding="utf-8") != "keep me\n" or not generated.is_file():
            raise AssertionError("cleanup modified or deleted an unowned user file")
        generated.unlink()


def verify_path_guard_and_symlink_escape(temp_root: Path) -> None:
    temp_root.mkdir(parents=True, exist_ok=True)
    outside = temp_root / "not-the-configured-root" / f"{INVOCATION_PREFIX}outside"
    outside.mkdir(parents=True)
    outside_state = outside / "validator-state.json"
    outside_state.write_text("do not delete\n", encoding="utf-8")
    env = os.environ.copy()
    env["AKBS_PLUGIN_TMP_ROOT"] = str(temp_root)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_ROOT / "validator_hygiene.py"),
            "cleanup",
            "--state-file",
            str(outside_state),
        ],
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode == 0 or not outside_state.is_file():
        raise AssertionError("canonical path guard accepted or deleted an outside target")
    outside_state.unlink()
    outside.rmdir()
    outside.parent.rmdir()

    invocation = ValidatorInvocation.create(REPO_ROOT)
    saved = invocation.invocation_dir.with_name(f"saved-{invocation.token}")
    target = temp_root / f"symlink-target-{invocation.token}"
    target.mkdir()
    victim = target / "keep.txt"
    victim.write_text("keep\n", encoding="utf-8")
    invocation.invocation_dir.rename(saved)
    invocation.invocation_dir.symlink_to(target, target_is_directory=True)
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_ROOT / "validator_hygiene.py"),
                "cleanup",
                "--state-file",
                str(invocation.state_file),
            ],
            env=env,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0 or victim.read_text(encoding="utf-8") != "keep\n":
            raise AssertionError("symlink escape was accepted or changed its target")
    finally:
        invocation.invocation_dir.unlink(missing_ok=True)
        saved.rename(invocation.invocation_dir)
        cleanup_state_file(invocation.state_file)
        victim.unlink()
        target.rmdir()


def verify_marker_and_idempotent_cleanup() -> None:
    invocation = ValidatorInvocation.create(REPO_ROOT)
    payload = json.loads(invocation.state_file.read_text(encoding="utf-8"))
    payload["token"] = "invalid"
    invocation.state_file.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    try:
        try:
            cleanup_state_file(invocation.state_file)
        except RuntimeError as exc:
            if "token" not in str(exc):
                raise
        else:
            raise AssertionError("ownership-token mismatch did not fail closed")
    finally:
        payload["token"] = invocation.token
        invocation.state_file.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        cleanup_state_file(invocation.state_file)
    cleanup_state_file(invocation.state_file)


def verify_shared_path_guard_matrix() -> dict[str, str]:
    invocation = ValidatorInvocation.create(REPO_ROOT)
    authority = guard_write_path(
        Path("guard-authority"),
        authority=invocation.work_dir,
        label="R41 plugin guard fixture authority",
        source_roots=(REPO_ROOT,),
        akbs_roots=(AKBS_ROOT,),
    )
    results: dict[str, str] = {}
    try:
        authority.mkdir(mode=0o700)
        normal = guard_write_path(
            Path("normal/result.json"),
            authority=authority,
            label="ordinary plugin validator output",
            source_roots=(REPO_ROOT,),
            akbs_roots=(AKBS_ROOT,),
        )
        if normal != authority / "normal/result.json":
            raise AssertionError("ordinary plugin path guard result drifted")
        results["ordinary"] = "allowed"
        outputs_task = guard_write_path(
            authority / "outputs-task-result.json",
            authority=authority,
            label="plugin outputs task result",
            source_roots=(REPO_ROOT,),
            akbs_roots=(AKBS_ROOT,),
        )
        if outputs_task != authority / "outputs-task-result.json":
            raise AssertionError("plugin outputs task path guard result drifted")
        results["outputs_task"] = "allowed"

        outside = guard_write_path(
            Path("outside"),
            authority=invocation.work_dir,
            label="plugin guard outside fixture",
            source_roots=(REPO_ROOT,),
            akbs_roots=(AKBS_ROOT,),
        )
        outside.mkdir(mode=0o700)
        target = guard_write_path(
            Path("target"),
            authority=outside,
            label="plugin guard symlink target fixture",
            source_roots=(REPO_ROOT,),
            akbs_roots=(AKBS_ROOT,),
        )
        target.mkdir()
        (authority / "escape-link").symlink_to(target, target_is_directory=True)
        cases = {
            "absolute": (outside / "absolute.txt", ABSOLUTE_ESCAPE),
            "parent": (Path("../parent.txt"), PARENT_ESCAPE),
            "symlink": (Path("escape-link/value.txt"), SYMLINK_ESCAPE),
            "git_source": (REPO_ROOT / "README.md", GIT_SOURCE_FORBIDDEN),
            "akbs_root": (AKBS_ROOT, AKBS_ROOT_FORBIDDEN),
            "runtime": (AKBS_ROOT / "runtime/probe", PRODUCTION_ROOT_FORBIDDEN),
            "data": (AKBS_ROOT / "data/probe", PRODUCTION_ROOT_FORBIDDEN),
            "backups": (AKBS_ROOT / "backups/probe", PRODUCTION_ROOT_FORBIDDEN),
            "authority": (Path("."), AUTHORITY_ROOT_FORBIDDEN),
        }
        for name, (candidate, expected_code) in cases.items():
            try:
                guard_write_path(
                    candidate,
                    authority=authority,
                    label=f"R41 plugin {name} probe",
                    source_roots=(REPO_ROOT,),
                    akbs_roots=(AKBS_ROOT,),
                )
            except ValidatorPathError as error:
                if error.code != expected_code:
                    raise AssertionError(f"{name} returned {error.code}, expected {expected_code}") from error
                results[name] = error.code
            else:
                raise AssertionError(f"plugin {name} path probe did not fail closed")
        return results
    finally:
        invocation.cleanup()


def main() -> int:
    outer = RepositorySnapshot.capture(REPO_ROOT)
    if outer.residue:
        raise SystemExit("validator cleanup self-test requires a residue-free plugin source tree")
    temp_root = controlled_temp_root()
    baseline_invocations = invocation_dirs(temp_root)
    try:
        results = {
            mode: run_probe(mode, temp_root, baseline_invocations)
            for mode in ("success", "failure", "sigint", "sigterm", "sighup")
        }
        if results["success"] != 0:
            raise AssertionError(f"success probe failed: {results['success']}")
        if any(results[mode] == 0 for mode in ("failure", "sigint", "sigterm", "sighup")):
            raise AssertionError(f"intentional failure/signal probes unexpectedly passed: {results}")
        verify_preexisting_and_concurrent_user_files_are_preserved(temp_root)
        verify_path_guard_and_symlink_escape(temp_root)
        verify_marker_and_idempotent_cleanup()
        path_guard = verify_shared_path_guard_matrix()
        if residue_paths(REPO_ROOT):
            raise AssertionError("cleanup self-test left cache or bytecode residue")
        if other_files(REPO_ROOT) != set(outer.other_files):
            raise AssertionError("cleanup self-test left a non-allowed repository artifact")
        if invocation_dirs(temp_root) != baseline_invocations:
            raise AssertionError("cleanup self-test left an owned invocation")
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "probes": results,
                    "path_guard": path_guard,
                    "preexisting_and_concurrent_user_files": "preserved",
                    "path_escape": "refused",
                    "symlink_escape": "refused",
                    "idempotent_cleanup": "pass",
                    "python_cache_redirect": "pass",
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        if invocation_dirs(temp_root) != baseline_invocations:
            raise RuntimeError("validator cleanup self-test changed invocation ownership state")
        outer.assert_unchanged()


if __name__ == "__main__":
    raise SystemExit(main())
