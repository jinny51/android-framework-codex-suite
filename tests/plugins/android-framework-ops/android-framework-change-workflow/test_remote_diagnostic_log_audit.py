from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "plugins/android-framework-ops/skills/android-framework-change-workflow/scripts/diagnostic_log_audit.py"


class RemoteDiagnosticAuditTests(unittest.TestCase):
    def make_fake_channel(self, root: Path, *, result: int = 0) -> tuple[Path, Path]:
        log = root / "channel-args.json"
        channel = root / "remote-channel"
        channel.write_text(
            "#!" + sys.executable + "\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['CHANNEL_LOG']).write_text(json.dumps(sys.argv[1:]))\n"
            f"raise SystemExit({result})\n",
            encoding="utf-8",
        )
        channel.chmod(channel.stat().st_mode | stat.S_IXUSR)
        return channel, log

    def run_audit(self, channel: Path, log: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHANNEL_LOG"] = str(log)
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--ssh-host",
                "builder",
                "--remote-root",
                "/srv/android/project",
                "--channel-script",
                str(channel),
                *extra,
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

    def test_routes_bounded_scan_through_nonexclusive_channel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel, log = self.make_fake_channel(root)
            result = self.run_audit(
                channel,
                log,
                "--path",
                "frameworks/base/services/core/java/Test.java",
                "--include-logs",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = json.loads(log.read_text(encoding="utf-8"))
            self.assertEqual(arguments[:4], ["--ssh-host", "builder", "--remote-root", "/srv/android/project"])
            self.assertIn("run", arguments)
            self.assertEqual(arguments[arguments.index("--lock") + 1], "none")
            self.assertRegex(arguments[arguments.index("--command-id") + 1], r"^diagnostic-audit-")
            payload = arguments[-1]
            self.assertIn("frameworks/base/services/core/java/Test.java", payload)
            self.assertIn("include_logs = sys.argv[2] == \"1\"", payload)

    def test_rejects_absolute_and_parent_paths_before_channel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel, log = self.make_fake_channel(root)
            for value in ("/etc/passwd", "../frameworks/base", "frameworks/../base"):
                with self.subTest(value=value):
                    result = self.run_audit(channel, log, "--path", value)
                    self.assertNotEqual(result.returncode, 0)
            self.assertFalse(log.exists())

    def test_propagates_remote_audit_finding_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel, log = self.make_fake_channel(root, result=1)
            result = self.run_audit(channel, log, "--path", "frameworks/base/Test.java")
            self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
