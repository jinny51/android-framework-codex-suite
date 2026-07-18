from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = REPO_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-remote-build-deploy"
PUSH_SCRIPT = SKILL_ROOT / "scripts" / "push_artifacts.py"
MAPPING_SCRIPT = SKILL_ROOT / "scripts" / "resolve_remote_mapping.py"
DISCOVERY_SCRIPT = SKILL_ROOT / "scripts" / "discover-project.sh"
CHECKPOINT_SCRIPT = SKILL_ROOT / "scripts" / "create-checkpoint.sh"
FRAME_SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "android-framework-ops"
    / "skills"
    / "android-framework-change-workflow"
    / "scripts"
    / "extract_video_frames.py"
)
DIAGNOSTICS_SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "android-framework-ops"
    / "skills"
    / "android-framework-change-workflow"
    / "scripts"
    / "collect_diagnostics.sh"
)
CANONICAL_OUTPUT_HELPER = REPO_ROOT.parent / "maintainer" / "scripts" / "akbs_outputs.py"


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
            manifests = list((outputs / "diagnostics" / "android-framework-change-workflow").glob("*/_manifest.json"))
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
                self.assertIn("不能写入", result.stderr)
                self.assertFalse(target.exists())

    def test_writes_remote_local_delivery_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "out" / "target" / "product" / "tve" / "system" / "framework" / "services.jar"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("jar", encoding="utf-8")
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
                    "--dest",
                    "/system/framework/services.jar",
                    "--adb-serial",
                    "ABC123",
                    "--dry-run",
                    "--evidence-out",
                    str(evidence),
                    "--remote-build-host",
                    "builder01",
                    "--remote-source-root",
                    "/build/android/TVE8402M",
                    "--remote-build-command",
                    "bash .codex/build-push.sh build --profile framework-services",
                    "--remote-build-profile",
                    "framework-services",
                    "--remote-artifact",
                    "/build/android/TVE8402M/out/target/product/tve/system/framework/services.jar",
                    "--artifact-sha1",
                    "0123456789abcdef0123456789abcdef01234567",
                    "--artifact-transfer",
                    "scp builder01:/build/android/TVE8402M/out/target/product/tve/system/framework/services.jar services.jar",
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
            self.assertEqual(payload["remote_build"]["host"], "builder01")
            self.assertEqual(payload["remote_build"]["artifacts"][0]["sha1"], "0123456789abcdef0123456789abcdef01234567")
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
            fake_adb = root / "adb"
            fake_adb.write_text("#!/usr/bin/env bash\necho adb \"$@\"\n", encoding="utf-8")
            fake_adb.chmod(0o755)
            destinations = root / ".codex" / "artifact-destinations.json"
            env = os.environ.copy()
            env["ADB"] = str(fake_adb)

            result = subprocess.run(
                [
                    sys.executable,
                    str(PUSH_SCRIPT),
                    "--artifact",
                    str(artifact),
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
            self.assertEqual(values["REMOTE_ROOT"], "/srv/android/TVE1086M/frameworks/base")
            self.assertEqual(values["SDK_NAME"], "TVE1086M")


if __name__ == "__main__":
    unittest.main()
