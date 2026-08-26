from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[4]
RUNTIME = (
    REPO_ROOT
    / "plugins"
    / "android-framework-ops"
    / "skills"
    / "android-remote-build-deploy"
    / "scripts"
    / "remote_build_runtime.sh"
)


def init_git(path: Path, files: dict[str, str]) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "fixture@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Fixture"], check=True)
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "baseline"], check=True)


def make_fake_repo(path: Path) -> Path:
    executable = path / "repo"
    executable.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            action="${1:-}"; shift || true
            projects=(frameworks/base packages/apps/Settings)
            case "$action" in
              status)
                for project in "${projects[@]}"; do
                  printf 'project %s\\n' "$project"
                  git -C "$project" status --short
                done
                ;;
              manifest)
                [ "${1:-}" = -r ] && [ "${2:-}" = -o ]
                printf '<manifest revision="fixture"/>\\n' >"$3"
                ;;
              forall)
                [ "${1:-}" = -c ]; command="$2"
                [ "${FAKE_REPO_FAIL_FORALL:-0}" != 1 ] || exit 23
                root="$PWD"
                for project in "${projects[@]}"; do
                  (cd "$root/$project" && REPO_PATH="$project" bash -c "$command")
                done
                ;;
              *) echo "unsupported fake repo action: $action" >&2; exit 64 ;;
            esac
            """
        ),
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


class RemoteRepoCheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.project = Path(self.tempdir.name) / "android-project"
        (self.project / ".repo").mkdir(parents=True)
        init_git(
            self.project / "frameworks/base",
            {"staged.txt": "base\n", "unstaged.txt": "base\n"},
        )
        init_git(self.project / "packages/apps/Settings", {"settings.txt": "base\n"})

        framework = self.project / "frameworks/base"
        (framework / "staged.txt").write_text("staged-change\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(framework), "add", "staged.txt"], check=True)
        (framework / "unstaged.txt").write_text("unstaged-change\n", encoding="utf-8")
        (framework / "new.bin").write_bytes(b"untracked\x00content")
        (self.project / "packages/apps/Settings/new.txt").write_text("settings-untracked\n")

        release = self.project / ".codex/remote-v2/releases/test-release"
        release.mkdir(parents=True)
        shutil.copy2(RUNTIME, release / "session.sh")
        (release / "session.sh").chmod(0o700)
        current = self.project / ".codex/remote-v2/current"
        current.symlink_to("releases/test-release", target_is_directory=True)

        fake_bin = Path(self.tempdir.name) / "bin"
        fake_bin.mkdir()
        make_fake_repo(fake_bin)
        self.env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}
        self.runtime = current / "session.sh"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_checkpoint(self, name: str, *, fail_forall: bool = False) -> subprocess.CompletedProcess[str]:
        env = dict(self.env)
        if fail_forall:
            env["FAKE_REPO_FAIL_FORALL"] = "1"
        return subprocess.run(
            ["bash", str(self.runtime), "checkpoint", "--name", name, "--purpose", "fixture"],
            cwd=self.project,
            env=env,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_repo_checkpoint_captures_staged_unstaged_and_untracked_content(self) -> None:
        result = self.run_checkpoint("repo-good")
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        checkpoint = self.project / ".codex/remote-v2/checkpoints/repo-good"
        self.assertTrue((checkpoint / "manifest.xml").is_file())
        self.assertTrue((checkpoint / "restore.sh").is_file())
        records = list((checkpoint / "repositories").iterdir())
        by_path = {
            (record / "repo_path.txt").read_text().strip(): record
            for record in records
        }
        framework = by_path["frameworks/base"]
        self.assertGreater((framework / "staged.patch").stat().st_size, 0)
        self.assertGreater((framework / "unstaged.patch").stat().st_size, 0)
        archive = subprocess.run(
            ["tar", "-tzf", str(framework / "untracked.tgz")],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.splitlines()
        self.assertIn("new.bin", archive)
        settings = by_path["packages/apps/Settings"]
        settings_archive = subprocess.run(
            ["tar", "-tzf", str(settings / "untracked.tgz")],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.splitlines()
        self.assertIn("new.txt", settings_archive)

    def test_repo_checkpoint_fails_closed_when_forall_is_incomplete(self) -> None:
        result = self.run_checkpoint("repo-fail", fail_forall=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.project / ".codex/remote-v2/checkpoints/repo-fail").exists())


if __name__ == "__main__":
    unittest.main()
