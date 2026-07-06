from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "push-artifacts.sh"


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
                    str(SCRIPT),
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
            self.assertEqual(payload["local_delivery"]["local_artifacts"], [str(artifact)])
            self.assertIn("push", payload["local_delivery"]["adb_actions"][0])


if __name__ == "__main__":
    unittest.main()
