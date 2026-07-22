from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "android-framework-ops"
    / "skills"
    / "android-remote-channel"
    / "scripts"
    / "remote-channel.sh"
)


def make_fake_remote(root: Path) -> tuple[dict[str, str], Path]:
    fake_bin = root / "bin"
    fake_bin.mkdir()
    remote_home = root / "remote-home"
    remote_root = remote_home / "android"
    remote_root.mkdir(parents=True)
    ssh_log = root / "ssh.log"
    dispatch_log = root / "dispatch.log"

    ssh = fake_bin / "ssh"
    ssh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "command=''\n"
        "for argument in \"$@\"; do command=\"$argument\"; done\n"
        "printf '%s\\n' \"$command\" >> \"$FAKE_SSH_LOG\"\n"
        "HOME=\"$FAKE_REMOTE_HOME\" PATH=\"$FAKE_REMOTE_BIN:$FAKE_BASE_PATH\" "
        "bash -c \"$command\"\n",
        encoding="utf-8",
    )
    tmux = fake_bin / "tmux"
    tmux.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "state=\"$FAKE_REMOTE_HOME/.fake-tmux\"\n"
        "mkdir -p \"$state\"\n"
        "case \"${1:-}\" in\n"
        "  has-session) [ -f \"$state/session\" ] ;;\n"
        "  new-session) touch \"$state/session\" ;;\n"
        "  kill-session) rm -f \"$state/session\" ;;\n"
        "  send-keys)\n"
        "    literal=0\n"
        "    last=''\n"
        "    for argument in \"$@\"; do\n"
        "      [ \"$argument\" = -l ] && literal=1\n"
        "      last=\"$argument\"\n"
        "    done\n"
        "    if [ \"$literal\" -eq 1 ]; then\n"
        "      printf '%s' \"$last\" > \"$state/pending\"\n"
        "    else\n"
        "      pending=$(cat \"$state/pending\")\n"
        "      case \"$pending\" in\n"
        "        cd\\ *) : ;;\n"
        "        *)\n"
        "          [ \"${FAKE_TMUX_FAIL_COMMAND_SEND:-0}\" = 1 ] && exit 19\n"
        "          printf 'dispatch\\n' >> \"$FAKE_DISPATCH_LOG\"\n"
        "          if [ \"${FAKE_TMUX_EXECUTE_COMMAND:-0}\" = 1 ]; then\n"
        "            HOME=\"$FAKE_REMOTE_HOME\" PATH=\"$FAKE_REMOTE_BIN:$FAKE_BASE_PATH\" "
        "bash -c \"$pending\" || true\n"
        "          fi\n"
        "          ;;\n"
        "      esac\n"
        "    fi\n"
        "    ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    for path in (ssh, tmux):
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(root / "local-home"),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_REMOTE_HOME": str(remote_home),
            "FAKE_REMOTE_BIN": str(fake_bin),
            "FAKE_BASE_PATH": os.environ["PATH"],
            "FAKE_SSH_LOG": str(ssh_log),
            "FAKE_DISPATCH_LOG": str(dispatch_log),
            "CODEX_REMOTE_CHANNEL_SSH_MUX": "0",
        }
    )
    return env, remote_root


def run_channel(
    env: dict[str, str],
    remote_root: Path,
    command_id: str,
    *,
    no_wait: bool = True,
    command: str = "true",
    lock: str = "none",
) -> subprocess.CompletedProcess[str]:
    arguments = [
        str(SCRIPT),
        "--ssh-host",
        "fake-host",
        "--remote-root",
        str(remote_root),
        "run",
    ]
    if no_wait:
        arguments.append("--no-wait")
    if lock != "none":
        arguments.extend(["--lock", lock])
    arguments.extend(
        [
            "--command-id",
            command_id,
            "--",
            command,
        ]
    )
    return subprocess.run(
        arguments,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


class RemoteChannelTests(unittest.TestCase):
    def test_busy_claim_allows_only_one_concurrent_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env, remote_root = make_fake_remote(root)

            first = run_channel(env, remote_root, "command-one")
            second = run_channel(env, remote_root, "command-two")

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 3, second.stdout + second.stderr)
            self.assertIn("SESSION_BUSY", second.stderr)
            dispatches = (root / "dispatch.log").read_text(encoding="utf-8").splitlines()
            self.assertEqual(dispatches, ["dispatch"])
            busy_files = list((root / "remote-home" / ".codex" / "android-remote-sessions").glob("*/busy"))
            self.assertEqual(len(busy_files), 1)
            self.assertEqual(
                busy_files[0].read_text(encoding="utf-8"),
                f"command-one remote={remote_root}\n",
            )

    def test_failed_tmux_send_releases_owned_busy_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env, remote_root = make_fake_remote(root)
            env["FAKE_TMUX_FAIL_COMMAND_SEND"] = "1"

            result = run_channel(env, remote_root, "failed-command")

            self.assertEqual(result.returncode, 19, result.stdout + result.stderr)
            self.assertNotIn("COMMAND_STARTED", result.stdout)
            busy_files = list((root / "remote-home" / ".codex" / "android-remote-sessions").glob("*/busy"))
            self.assertEqual(busy_files, [])

    def test_completed_command_records_exit_and_releases_busy_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env, remote_root = make_fake_remote(root)
            env["FAKE_TMUX_EXECUTE_COMMAND"] = "1"

            result = run_channel(env, remote_root, "completed-command", no_wait=False)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("COMMAND_STARTED id=completed-command", result.stdout)
            self.assertIn("__CODEX_CMD_DONE id=completed-command rc=0", result.stdout)
            state_roots = list((root / "remote-home" / ".codex" / "android-remote-sessions").iterdir())
            self.assertEqual(len(state_roots), 1)
            self.assertFalse((state_roots[0] / "busy").exists())
            self.assertEqual(
                (state_roots[0] / "commands" / "completed-command.exit").read_text(encoding="utf-8"),
                "0\n",
            )

    def test_failed_command_records_exit_and_releases_busy_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env, remote_root = make_fake_remote(root)
            env["FAKE_TMUX_EXECUTE_COMMAND"] = "1"

            result = run_channel(
                env,
                remote_root,
                "failed-runtime-command",
                no_wait=False,
                command="false",
                lock="exclusive",
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("__CODEX_CMD_DONE id=failed-runtime-command rc=1", result.stdout)
            state_roots = list((root / "remote-home" / ".codex" / "android-remote-sessions").iterdir())
            self.assertEqual(len(state_roots), 1)
            self.assertFalse((state_roots[0] / "busy").exists())
            self.assertTrue((state_roots[0] / "project.lock").exists())
            self.assertEqual(
                (state_roots[0] / "commands" / "failed-runtime-command.exit").read_text(encoding="utf-8"),
                "1\n",
            )


if __name__ == "__main__":
    unittest.main()
