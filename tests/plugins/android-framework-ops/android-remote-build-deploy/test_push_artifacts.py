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


def parse_shell_output(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            parsed = shlex.split(value)
            values[key] = parsed[0] if parsed else ""
    return values


class PushArtifactsEvidenceTests(unittest.TestCase):
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
