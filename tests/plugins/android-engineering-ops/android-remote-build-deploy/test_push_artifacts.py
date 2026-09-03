from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = REPO_ROOT / "plugins" / "android-engineering-ops" / "skills" / "android-remote-build-deploy"
PUSH_SCRIPT = SKILL_ROOT / "scripts" / "push_artifacts.py"
MAPPING_SCRIPT = SKILL_ROOT / "scripts" / "resolve_remote_mapping.py"
DISCOVERY_SCRIPT = SKILL_ROOT / "scripts" / "discover-project.sh"
CHECKPOINT_SCRIPT = SKILL_ROOT / "scripts" / "create-checkpoint.sh"
FRAME_SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "android-engineering-ops"
    / "skills"
    / "android-change-workflow"
    / "scripts"
    / "extract_video_frames.py"
)
DIAGNOSTICS_SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "android-engineering-ops"
    / "skills"
    / "android-change-workflow"
    / "scripts"
    / "collect_diagnostics.sh"
)
INSTALLED_RUNTIME_ENTRYPOINTS = (
    "PUSH_SCRIPT",
    "MAPPING_SCRIPT",
    "DISCOVERY_SCRIPT",
    "CHECKPOINT_SCRIPT",
    "FRAME_SCRIPT",
    "DIAGNOSTICS_SCRIPT",
)
CANONICAL_OUTPUT_HELPER = REPO_ROOT.parent / "maintainer" / "scripts" / "akbs_outputs.py"
LIB_ROOT = REPO_ROOT / "plugins" / "android-engineering-ops" / "lib"
if str(LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(LIB_ROOT))

from android_engineering_ops.remote_artifact_manifest import create_remote_artifact_manifest


def write_artifact_manifest(
    root: Path,
    artifact: Path,
    *,
    profile: str = "framework-services",
    module: str = "services",
    workspace_id: str = "workspace-test",
    command_id: str = "build-test-001",
) -> Path:
    now = time.time_ns()
    started = now - 2_000_000_000
    mtime = now - 1_000_000_000
    os.utime(artifact, ns=(mtime, mtime))
    payload = create_remote_artifact_manifest(
        artifact,
        remote_root=root,
        module=module,
        profile=profile,
        workspace_id=workspace_id,
        command_id=command_id,
        build_started_ns=started,
        build_finished_ns=now,
    )
    path = root / f"{command_id}.manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def parse_shell_output(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            parsed = shlex.split(value)
            values[key] = parsed[0] if parsed else ""
    return values


class PushArtifactsEvidenceTests(unittest.TestCase):
    def test_default_diagnostics_promote_with_manifest_and_catalog(self) -> None:
        if not CANONICAL_OUTPUT_HELPER.is_file():
            self.skipTest("aggregate AKBS canonical outputs helper is not available")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            akbs_root = root / "akbs"
            outputs = akbs_root / "outputs"
            akbs_root.mkdir()

            fake_adb = root / "adb"
            fake_adb.write_text("#!/usr/bin/env bash\nprintf 'adb %s\\n' \"$*\"\n", encoding="utf-8")
            fake_adb.chmod(0o755)
            env = os.environ.copy()
            env["AKBS_ROOT"] = str(akbs_root)
            env["AKBS_OUTPUTS_HELPER"] = str(CANONICAL_OUTPUT_HELPER)
            env["PATH"] = f"{root}:{env.get('PATH', '')}"

            result = subprocess.run(
                [str(DIAGNOSTICS_SCRIPT)],
                env=env,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            manifests = list((outputs / "diagnostics" / "android-change-workflow").glob("*/_manifest.json"))
            self.assertEqual(len(manifests), 1)
            payload = json.loads(manifests[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "akbs-output-item-manifest-v1")
            self.assertEqual(payload["category"], "diagnostics")
            self.assertEqual(payload["retention"], {"mode": "ttl", "days": 14})
            self.assertEqual(payload["authority_root"], str(akbs_root.resolve()))
            self.assertFalse((manifests[0].parent / ".akbs-plugin-owner.json").exists())
            self.assertEqual(list((outputs / "tmp").iterdir()), [])
            catalog = [
                json.loads(line)
                for line in (outputs / "manifests" / "catalog.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(catalog), 1)
            self.assertEqual(catalog[0]["item_id"], payload["item_id"])
            self.assertEqual(catalog[0]["tree_sha256"], payload["tree_sha256"])

    def test_diagnostics_guard_success_and_interruption_cleanup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="akbs-external-diagnostics-") as tmp:
            root = Path(tmp)
            fake_adb = root / "adb"
            fake_adb.write_text("#!/usr/bin/env bash\nprintf 'adb %s\\n' \"$*\"\n", encoding="utf-8")
            fake_adb.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{root}:{env.get('PATH', '')}"

            forbidden = REPO_ROOT / "forbidden-diagnostics"
            result = subprocess.run(
                [str(DIAGNOSTICS_SCRIPT), "--out", str(forbidden)],
                env=env,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("不能写入", result.stderr)
            self.assertFalse(forbidden.exists())

            completed = root / "completed-diagnostics"
            result = subprocess.run(
                [str(DIAGNOSTICS_SCRIPT), "--out", str(completed)],
                env=env,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertTrue((completed / "getprop.txt").is_file())
            self.assertFalse((completed / ".akbs-plugin-owner.json").exists())

            fake_adb.write_text(
                "#!/usr/bin/env bash\nkill -TERM \"$PPID\"\nsleep 0.1\nexit 143\n",
                encoding="utf-8",
            )
            interrupted = root / "interrupted-diagnostics"
            result = subprocess.run(
                [str(DIAGNOSTICS_SCRIPT), "--out", str(interrupted)],
                env=env,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(interrupted.exists())

    def test_explicit_outputs_reject_plugin_source_and_cache_targets_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            targets = [
                REPO_ROOT / "forbidden-build-evidence.json",
                Path(tmp) / "codex-home" / "plugins" / "cache" / "suite" / "plugin" / "1.0.0" / "evidence.json",
            ]
            artifact = Path(tmp) / "services.jar"
            artifact.write_text("jar", encoding="utf-8")
            for target in targets:
                with self.subTest(target=target):
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(PUSH_SCRIPT),
                            "--artifact",
                            str(artifact),
                            "--dest",
                            "/system/framework/services.jar",
                            "--dry-run",
                            "--compat-unverified",
                            "--evidence-out",
                            str(target),
                        ],
                        check=False,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("不能写入", result.stderr)
                    self.assertFalse(target.exists())

    def test_akbs_output_symlink_escape_is_rejected_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            akbs_root = root / "akbs"
            outputs = akbs_root / "outputs"
            outside = root / "outside"
            outputs.mkdir(parents=True)
            outside.mkdir()
            (outputs / "artifacts").symlink_to(outside, target_is_directory=True)
            target = outputs / "artifacts" / "task-a" / "run-a" / "delivery.json"
            artifact = root / "services.jar"
            artifact.write_text("jar", encoding="utf-8")
            fake_adb = root / "adb"
            fake_adb.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            fake_adb.chmod(0o755)
            env = os.environ.copy()
            env["AKBS_ROOT"] = str(akbs_root)
            env["ADB"] = str(fake_adb)

            result = subprocess.run(
                [
                    sys.executable,
                    str(PUSH_SCRIPT),
                    "--artifact",
                    str(artifact),
                    "--dest",
                    "/system/framework/services.jar",
                    "--dry-run",
                    "--compat-unverified",
                    "--evidence-out",
                    str(target),
                ],
                env=env,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("符号链接", result.stderr)
            self.assertFalse((outside / "task-a" / "run-a" / "delivery.json").exists())

    def test_direct_akbs_output_write_requires_the_canonical_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            akbs_root = root / "akbs"
            target = akbs_root / "outputs" / "artifacts" / "task-a" / "run-a" / "delivery.json"
            artifact = root / "services.jar"
            artifact.write_text("jar", encoding="utf-8")
            fake_adb = root / "adb"
            fake_adb.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            fake_adb.chmod(0o755)
            env = os.environ.copy()
            env["AKBS_ROOT"] = str(akbs_root)
            env["ADB"] = str(fake_adb)

            result = subprocess.run(
                [
                    sys.executable,
                    str(PUSH_SCRIPT),
                    "--artifact",
                    str(artifact),
                    "--dest",
                    "/system/framework/services.jar",
                    "--dry-run",
                    "--compat-unverified",
                    "--evidence-out",
                    str(target),
                ],
                env=env,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("默认受控输出流程", result.stderr)
            self.assertFalse(target.exists())

    def test_akbs_outputs_root_symlink_is_rejected_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            akbs_root = root / "akbs"
            outside = root / "outside"
            akbs_root.mkdir()
            outside.mkdir()
            (akbs_root / "outputs").symlink_to(outside, target_is_directory=True)
            target = akbs_root / "outputs" / "artifacts" / "task-a" / "run-a" / "delivery.json"
            artifact = root / "services.jar"
            artifact.write_text("jar", encoding="utf-8")
            fake_adb = root / "adb"
            fake_adb.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            fake_adb.chmod(0o755)
            env = os.environ.copy()
            env["AKBS_ROOT"] = str(akbs_root)
            env["ADB"] = str(fake_adb)

            result = subprocess.run(
                [
                    sys.executable,
                    str(PUSH_SCRIPT),
                    "--artifact",
                    str(artifact),
                    "--dest",
                    "/system/framework/services.jar",
                    "--dry-run",
                    "--compat-unverified",
                    "--evidence-out",
                    str(target),
                ],
                env=env,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("符号链接", result.stderr)
            self.assertFalse((outside / "artifacts" / "task-a" / "run-a" / "delivery.json").exists())

    def test_shell_and_frame_output_flags_reject_plugin_source_before_external_work(self) -> None:
        target = REPO_ROOT / "forbidden-output.txt"
        commands = [
            [str(DISCOVERY_SCRIPT), "--ssh-host", "invalid", "--remote-root", "/tmp/android", "--output", str(target)],
            [str(CHECKPOINT_SCRIPT), "--ssh-host", "invalid", "--remote-root", "/tmp/android", "--output", str(target)],
            [sys.executable, str(FRAME_SCRIPT), "/missing/video.mp4", "--out", str(target)],
        ]
        for command in commands:
            with self.subTest(command=command[0]):
                result = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertNotEqual(result.returncode, 0)
                if command[0] in {str(DISCOVERY_SCRIPT), str(CHECKPOINT_SCRIPT)}:
                    self.assertIn("remote-v2", result.stderr)
                else:
                    self.assertIn("不能写入", result.stderr)
                self.assertFalse(target.exists())

    def test_frame_prefix_rejects_path_escape_before_ffmpeg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "video.mp4"
            video.write_bytes(b"fixture")
            marker = root / "ffmpeg-called"
            ffmpeg = root / "ffmpeg"
            ffmpeg.write_text(
                f"#!/bin/sh\ntouch {marker}\nexit 0\n", encoding="utf-8"
            )
            ffmpeg.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{root}{os.pathsep}{env.get('PATH', '')}"
            for prefix in ("../../escape", "/absolute", "..\\escape", "bad.name"):
                with self.subTest(prefix=prefix):
                    output = root / f"frames-{len(prefix)}"
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(FRAME_SCRIPT),
                            str(video),
                            "--out",
                            str(output),
                            "--prefix",
                            prefix,
                        ],
                        env=env,
                        check=False,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("--prefix must be", result.stderr)
                    self.assertFalse(output.exists())
                    self.assertFalse(marker.exists())

    def test_writes_remote_local_delivery_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "out" / "target" / "product" / "tve" / "system" / "framework" / "services.jar"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("jar", encoding="utf-8")
            manifest = write_artifact_manifest(root, artifact)
            fake_adb = root / "adb"
            fake_adb.write_text("#!/usr/bin/env bash\necho adb \"$@\"\n", encoding="utf-8")
            fake_adb.chmod(0o755)
            evidence = root / ".codex" / "evidence" / "latest-build-delivery.json"
            env = os.environ.copy()
            env["ADB"] = str(fake_adb)

            result = subprocess.run(
                [
                    sys.executable,
                    str(PUSH_SCRIPT),
                    "--artifact",
                    str(artifact),
                    "--artifact-manifest",
                    str(manifest),
                    "--artifact-bridge-root",
                    str(root),
                    "--expected-module",
                    "services",
                    "--expected-workspace-id",
                    "workspace-test",
                    "--expected-command-id",
                    "build-test-001",
                    "--remote-source-root",
                    str(root.resolve()),
                    "--remote-build-profile",
                    "framework-services",
                    "--dest",
                    "/system/framework/services.jar",
                    "--adb-serial",
                    "ABC123",
                    "--dry-run",
                    "--evidence-out",
                    str(evidence),
                    "--remote-build-host",
                    "builder01",
                    "--remote-build-command",
                    "bash .codex/build-push.sh build --profile framework-services",
                    "--artifact-transfer",
                    "registered artifact bridge",
                ],
                cwd=str(root),
                env=env,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(payload["kind"], "verification_result")
            self.assertEqual(payload["result"], "INFO")
            self.assertEqual(payload["contract_version"], "akbs-verification-evidence/v2")
            self.assertEqual(payload["scope"], "build_delivery")
            self.assertEqual(payload["requirement_acceptance"], "unverified")
            self.assertEqual(payload["remote_build"]["host"], "builder01")
            self.assertTrue(payload["remote_build"]["manifest_verified"])
            self.assertEqual(payload["remote_build"]["artifacts"][0]["module"], "services")
            self.assertEqual(payload["local_delivery"]["adb_serial"], "ABC123")
            self.assertEqual(payload["local_delivery"]["local_artifacts"], [str(artifact.resolve())])
            self.assertIn("push", payload["local_delivery"]["adb_actions"][0])

    def test_destination_memory_uses_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product_out = root / "out" / "target" / "product" / "tve"
            artifact = product_out / "system" / "framework" / "services.jar"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("jar", encoding="utf-8")
            manifest = write_artifact_manifest(root, artifact)
            fake_adb = root / "adb"
            fake_adb.write_text(
                "#!/usr/bin/env bash\nprintf 'adb %s\\n' \"$*\" >> \"$ADB_TEST_LOG\"\n",
                encoding="utf-8",
            )
            fake_adb.chmod(0o755)
            adb_log = root / "adb.log"
            destinations = root / ".codex" / "artifact-destinations.json"
            env = os.environ.copy()
            env["ADB"] = str(fake_adb)
            env["ADB_TEST_LOG"] = str(adb_log)

            result = subprocess.run(
                [
                    sys.executable,
                    str(PUSH_SCRIPT),
                    "--artifact",
                    str(artifact),
                    "--artifact-manifest",
                    str(manifest),
                    "--artifact-bridge-root",
                    str(root),
                    "--expected-module",
                    "services",
                    "--expected-workspace-id",
                    "workspace-test",
                    "--expected-command-id",
                    "build-test-001",
                    "--remote-source-root",
                    str(root.resolve()),
                    "--remote-build-profile",
                    "framework-services",
                    "--product-out",
                    str(product_out),
                    "--destinations-file",
                    str(destinations),
                    "--learn-destinations",
                ],
                env=env,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertEqual(
                json.loads(destinations.read_text(encoding="utf-8")),
                {"system/framework/services.jar": "/system/framework/services.jar"},
            )
            push_lines = [line for line in adb_log.read_text().splitlines() if " push " in line]
            self.assertEqual(len(push_lines), 1)
            self.assertIn("codex-verified-artifacts-", push_lines[0])
            self.assertNotIn(str(artifact), push_lines[0])


class RemoteMappingTests(unittest.TestCase):
    def run_resolver(self, project: Path, registry: Path) -> dict[str, str]:
        result = subprocess.run(
            [
                sys.executable,
                str(MAPPING_SCRIPT),
                "--project",
                str(project),
                "--registry-dir",
                str(registry),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return parse_shell_output(result.stdout)

    def test_resolves_wsl_env_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "work" / "rk" / "TVA10A2R"
            project.mkdir(parents=True)
            registry = root / "registry"
            registry.mkdir()
            (registry / "builder.env").write_text(
                "\n".join(
                    [
                        f"PROJECT_PATHS=({shlex.quote(str(project))})",
                        "SAMBA_PROJECT_SHARES=(work)",
                        "REMOTE_SSH_HOSTS=(builder01)",
                        "REMOTE_ROOTS=(/srv/android/TVA10A2R)",
                        "PLATFORMS=(rk)",
                        "SDK_NAMES=(TVA10A2R)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            values = self.run_resolver(project, registry)

            self.assertEqual(values["SSH_HOST"], "builder01")
            self.assertEqual(values["REMOTE_ROOT"], "/srv/android/TVA10A2R")
            self.assertEqual(values["PROJECT_ROOT"], "/srv/android/TVA10A2R")
            self.assertEqual(values["REMOTE_WORKING_PATH"], "/srv/android/TVA10A2R")
            self.assertEqual(values["WORKING_SUBPATH"], ".")
            self.assertEqual(values["PROJECT_ID"], "rk-TVA10A2R")
            self.assertEqual(Path(values["ARTIFACT_BRIDGE_PATH"]), project.resolve())
            self.assertEqual(values["MOUNT_TRANSPORT"], "cifs")
            self.assertEqual(values["PLATFORM"], "rk")

    def test_resolves_macos_json_registry_and_nested_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "work" / "mtk" / "TVE1086M"
            nested = project / "frameworks" / "base"
            nested.mkdir(parents=True)
            registry = root / "registry"
            registry.mkdir()
            (registry / "builder02.json").write_text(
                json.dumps(
                    {
                        "server": "builder02",
                        "shares": {
                            "android": {
                                "mount_point": str(root / "work"),
                                "remote_path": "/srv/android",
                                "projects": {
                                    "TVE1086M": {
                                        "local_path": str(project),
                                        "remote_path": "/srv/android/TVE1086M",
                                        "platform": "mtk",
                                    }
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            values = self.run_resolver(nested, registry)

            self.assertEqual(values["SSH_HOST"], "builder02")
            self.assertEqual(values["REMOTE_ROOT"], "/srv/android/TVE1086M")
            self.assertEqual(values["PROJECT_ROOT"], "/srv/android/TVE1086M")
            self.assertEqual(values["WORKING_SUBPATH"], "frameworks/base")
            self.assertEqual(
                values["REMOTE_WORKING_PATH"],
                "/srv/android/TVE1086M/frameworks/base",
            )
            self.assertEqual(values["PROJECT_ID"], "mtk-TVE1086M")
            self.assertEqual(Path(values["ARTIFACT_BRIDGE_PATH"]), project.resolve())
            self.assertEqual(values["MOUNT_TRANSPORT"], "smbfs")
            self.assertEqual(values["SDK_NAME"], "TVE1086M")


if __name__ == "__main__":
    unittest.main()
