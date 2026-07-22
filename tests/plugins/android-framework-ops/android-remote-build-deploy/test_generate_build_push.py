from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[4]
GENERATOR = (
    REPO_ROOT
    / "plugins"
    / "android-framework-ops"
    / "skills"
    / "android-remote-build-deploy"
    / "scripts"
    / "generate-build-push.sh"
)


class GeneratedBuildPushContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repo = self.root / "repo"
        self.remote = self.root / "remote"
        self.repo.mkdir()
        (self.remote / "build").mkdir(parents=True)
        (self.remote / "build" / "envsetup.sh").write_text(
            """\
lunch() {
  printf 'FAKE_LUNCH %s\\n' "$1"
}
m() {
  printf 'FAKE_BUILD %s\\n' "$*"
  if [[ "${FAKE_BUILD_RC:-0}" != 0 ]]; then
    printf 'error: synthetic build failure rc=%s\\n' "$FAKE_BUILD_RC" >&2
    return "$FAKE_BUILD_RC"
  fi
}
""",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "bash",
                str(GENERATOR),
                "--repo",
                str(self.repo),
                "--ssh-host",
                "build-host",
                "--remote-root",
                str(self.remote),
                "--lunch",
                "test-userdebug",
                "--product-out",
                "out/target/product/test",
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.codex = self.repo / ".codex"
        self.foreground = self.codex / "build-push.sh"
        self.sourceable = self.codex / "build-session.sh"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_foreground(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.foreground), *args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **(env or {})},
        )

    def run_sourceable(self, command: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", f'source "$1"; {command}', "bash", str(self.sourceable)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **(env or {})},
        )

    def test_profile_and_direct_plan_contracts_match(self) -> None:
        profiles = {
            "services": ("services", "services.jar"),
            "framework": ("framework-minus-apex", "framework.jar"),
            "framework-res": ("framework-res", "framework-res.apk"),
        }
        for profile, (modules, artifact) in profiles.items():
            with self.subTest(profile=profile):
                foreground = self.run_foreground("plan", "--profile", profile)
                sourceable = self.run_sourceable(f"codex_session_plan --profile {profile}")
                self.assertEqual(foreground.returncode, 0, foreground.stderr)
                self.assertEqual(sourceable.returncode, 0, sourceable.stderr)
                self.assertEqual(foreground.stdout, sourceable.stdout)
                self.assertIn(f"MODULES={modules}", foreground.stdout)
                self.assertIn("ARTIFACT none_found_yet", foreground.stdout)
                self.assertNotIn(artifact + "\n", foreground.stdout)

        direct_args = (
            "--modules",
            "SystemUI Settings",
            "--artifacts",
            "SystemUI.apk Settings.apk",
        )
        foreground = self.run_foreground("plan", *direct_args)
        sourceable = self.run_sourceable(
            "codex_session_plan --modules 'SystemUI Settings' --artifacts 'SystemUI.apk Settings.apk'"
        )
        self.assertEqual(foreground.returncode, 0, foreground.stderr)
        self.assertEqual(sourceable.returncode, 0, sourceable.stderr)
        self.assertEqual(foreground.stdout, sourceable.stdout)
        self.assertIn("MODULES=SystemUI Settings", foreground.stdout)

        custom = subprocess.run(
            [
                "bash",
                str(GENERATOR),
                "--repo",
                str(self.repo),
                "--only-profile",
                "--profile",
                "systemui",
                "--modules",
                "SystemUI",
                "--artifacts",
                "SystemUI.apk",
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(custom.returncode, 0, custom.stderr or custom.stdout)
        foreground = self.run_foreground("plan", "--profile", "systemui")
        sourceable = self.run_sourceable("codex_session_plan --profile systemui")
        self.assertEqual(foreground.returncode, 0, foreground.stderr)
        self.assertEqual(sourceable.returncode, 0, sourceable.stderr)
        self.assertEqual(foreground.stdout, sourceable.stdout)
        self.assertIn("MODULES=SystemUI", foreground.stdout)

    def test_generated_wrapper_shell_syntax(self) -> None:
        for wrapper in (self.foreground, self.sourceable):
            with self.subTest(wrapper=wrapper.name):
                result = subprocess.run(
                    ["bash", "-n", str(wrapper)],
                    check=False,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_mode_specific_unknown_profile_and_lifecycle_contracts(self) -> None:
        foreground = self.run_foreground("plan", "--profile", "missing")
        sourceable = self.run_sourceable("codex_session_plan --profile missing; exit $?")

        self.assertEqual(foreground.returncode, 1)
        self.assertEqual(sourceable.returncode, 2)
        expected = "ERROR: Unknown profile: missing. Add it to .codex/build-push.profiles.sh first."
        self.assertIn(expected, foreground.stderr)
        self.assertIn(expected, sourceable.stderr)
        self.assertIn("exit \"$build_rc\"", self.foreground.read_text(encoding="utf-8"))
        self.assertIn("return \"$build_rc\"", self.sourceable.read_text(encoding="utf-8"))

        foreground = self.run_foreground("plan")
        sourceable = self.run_sourceable("codex_session_plan; exit $?")
        self.assertEqual(foreground.returncode, 1)
        self.assertEqual(sourceable.returncode, 2)
        self.assertIn("ERROR: --profile or --modules is required", foreground.stderr)
        self.assertIn("ERROR: --profile or --modules is required", sourceable.stderr)

    def test_success_memory_artifacts_and_shell_options(self) -> None:
        artifact = self.remote / "out" / "target" / "product" / "test" / "system" / "framework" / "services.jar"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("jar", encoding="utf-8")

        foreground = self.run_foreground("build", "--profile", "services", "-j", "3")
        self.assertEqual(foreground.returncode, 0, foreground.stderr or foreground.stdout)
        self.assertIn("BUILD_OK profile=services", foreground.stdout)
        self.assertIn(f"ARTIFACT {artifact}", foreground.stdout)
        self.assertIn("ARTIFACT_REL system/framework/services.jar", foreground.stdout)

        memory = self.run_sourceable(
            "source \"$SCRIPT_DIR/build-push.memory.sh\"; "
            "printf '%s|%s|%s\\n' \"${BUILD_PROFILE_LAST_MODULES[services]}\" "
            "\"${BUILD_PROFILE_LAST_ARTIFACTS[services]}\" "
            "\"${BUILD_PROFILE_LAST_LUNCH[services]}\""
        )
        self.assertEqual(memory.returncode, 0, memory.stderr)
        self.assertEqual(memory.stdout, "services|services.jar|test-userdebug\n")

        sourceable = self.run_sourceable(
            "set -eu; codex_session_build --profile services -j 3; "
            "case $- in *e*u*) printf 'OPTIONS_RESTORED\\n' ;; *) exit 91 ;; esac"
        )
        self.assertEqual(sourceable.returncode, 0, sourceable.stderr or sourceable.stdout)
        self.assertIn("SESSION_BUILD_ENV_OK", sourceable.stdout)
        self.assertIn("BUILD_OK profile=services", sourceable.stdout)
        self.assertIn("OPTIONS_RESTORED", sourceable.stdout)

        sourceable = self.run_sourceable(
            "set +eu; codex_session_build --profile services -j 3; "
            "case $- in *e*|*u*) exit 92 ;; *) printf 'OPTIONS_REMAIN_DISABLED\\n' ;; esac"
        )
        self.assertEqual(sourceable.returncode, 0, sourceable.stderr or sourceable.stdout)
        self.assertIn("OPTIONS_REMAIN_DISABLED", sourceable.stdout)

    def test_failure_key_errors_and_missing_artifact_contracts(self) -> None:
        env = {"FAKE_BUILD_RC": "17"}
        foreground = self.run_foreground("build", "--profile", "services", env=env)
        sourceable = self.run_sourceable(
            "codex_session_build --profile services; exit $?", env=env
        )
        for result in (foreground, sourceable):
            self.assertEqual(result.returncode, 17)
            self.assertIn("BUILD_FAIL rc=17 profile=services", result.stdout)
            self.assertIn("KEY_ERRORS_BEGIN", result.stdout)
            self.assertIn("error: synthetic build failure rc=17", result.stdout)
            self.assertIn("KEY_ERRORS_END", result.stdout)

        missing = self.run_foreground("plan", "--profile", "services")
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertIn("ARTIFACT none_found_yet", missing.stdout)

    def test_common_pure_helpers_have_one_generator_template_owner(self) -> None:
        generator = GENERATOR.read_text(encoding="utf-8")
        foreground = self.foreground.read_text(encoding="utf-8")
        sourceable = self.sourceable.read_text(encoding="utf-8")
        marker = "# BEGIN shared build-push pure helpers"

        self.assertEqual(generator.count(marker), 1)
        self.assertEqual(foreground.count(marker), 1)
        self.assertEqual(sourceable.count(marker), 1)


if __name__ == "__main__":
    unittest.main()
