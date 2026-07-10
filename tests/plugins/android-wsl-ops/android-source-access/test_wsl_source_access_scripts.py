from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_DIR = REPO_ROOT / "plugins" / "android-wsl-ops" / "skills" / "android-source-access"
SCRIPT_DIR = SKILL_DIR / "scripts"


def run_script(script: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [str(SCRIPT_DIR / script), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=merged_env,
    )


class WslSourceAccessScriptsTests(unittest.TestCase):
    def test_runtime_scripts_are_executable_and_bash_valid(self) -> None:
        for script in sorted(SCRIPT_DIR.glob("*.sh")):
            self.assertTrue(script.stat().st_mode & stat.S_IXUSR, script)
            result = subprocess.run(
                ["bash", "-n", str(script)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, f"{script}: {result.stderr}")

    def test_remote_path_does_not_invent_platform_or_project(self) -> None:
        result = run_script(
            "plan-from-remote-path.sh",
            "--remote-root",
            "/home/test55/work/unisoc/rk3576",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REMOTE_ROOT=/home/test55/work/unisoc/rk3576", result.stdout)
        self.assertIn("REMOTE_USER=test55", result.stdout)
        self.assertRegex(result.stdout, r"(?m)^PLATFORM=(?:''|)$")
        self.assertRegex(result.stdout, r"(?m)^SDK_NAME=(?:''|)$")

    def test_explicit_platform_and_project_define_wsl_work_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            result = run_script(
                "plan-from-remote-path.sh",
                "--remote-root",
                "/home/test55/work/unisoc/rk3576",
                "--local-platform",
                "rk",
                "--sdk-name",
                "TVA10A2R",
                env={"HOME": str(home)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PLATFORM=rk", result.stdout)
            self.assertIn("SDK_NAME=TVA10A2R", result.stdout)
            self.assertIn(f"LOCAL_PROJECT={home}/work/rk/TVA10A2R", result.stdout)

    def test_project_level_mount_is_default_and_conflicts_need_confirmation(self) -> None:
        ensure_help = run_script("ensure-samba-share.sh", "--help")
        mount_help = run_script("mount-from-remote-path.sh", "--help")
        invalid_accept = run_script(
            "inspect-android-sdk.sh",
            "--ssh-host",
            "dummy",
            "--remote-root",
            "/home/test55/work/unisoc/rk3576",
            "--accept-platform-conflict",
        )

        self.assertEqual(ensure_help.returncode, 0, ensure_help.stderr)
        self.assertIn("Default share plan:", ensure_help.stdout)
        self.assertIn("[rk3576] path = /home/test55/work/unisoc/rk3576", ensure_help.stdout)
        self.assertIn("Parent/platform shares are explicit exceptions", ensure_help.stdout)
        self.assertEqual(mount_help.returncode, 0, mount_help.stderr)
        self.assertIn("--accept-platform-conflict", mount_help.stdout)
        self.assertIn("--accept-sdk-name-conflict", mount_help.stdout)
        self.assertIn("This is the default", mount_help.stdout)
        self.assertEqual(invalid_accept.returncode, 2)
        self.assertIn("--accept-platform-conflict requires --platform", invalid_accept.stderr)

    def test_project_level_dry_run_targets_home_work_platform_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_mount = fake_bin / "mount.cifs"
            fake_mount.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            fake_mount.chmod(fake_mount.stat().st_mode | stat.S_IXUSR)
            target = root / "home" / "work" / "rk" / "TVA10A2R"

            result = run_script(
                "mount-platform.sh",
                "--platform",
                "rk",
                "--share",
                "//192.168.100.6/TVA10A2R",
                "--target",
                str(target),
                "--user",
                "test55",
                "--dry-run",
                env={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(target), result.stdout)
            self.assertIn("//192.168.100.6/TVA10A2R", result.stdout)

    def test_runtime_skill_has_no_embedded_test_or_stale_output_framework(self) -> None:
        stale_terms = (
            "initial platform mount",
            "SAMBA_PROJECT_URL is for reference",
            "share-or-sdk",
            "Use `SAMBA_SHARE_URL`",
            "Capability Capture Candidate",
            "Pattern:",
            "Store in:",
            "Persist?",
        )
        self.assertFalse((SCRIPT_DIR / "validate-skill.sh").exists())
        for path in SKILL_DIR.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for term in stale_terms:
                    self.assertNotIn(term, text, f"{path}: {term}")


if __name__ == "__main__":
    unittest.main()
