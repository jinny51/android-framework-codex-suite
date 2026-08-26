from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Optional


REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_DIR = REPO_ROOT / "plugins" / "android-mac-ops" / "skills" / "android-source-access"
SCRIPT_DIR = SKILL_DIR / "scripts"
INSPECTION_HELPER = (
    REPO_ROOT / "plugins" / "android-framework-ops" / "lib" / "android_framework_ops" / "remote_source_inspection.py"
)


def run_script(
    script: str,
    *args: str,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
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


def make_fake_bin(root: Path) -> Path:
    fake_bin = root / "bin"
    fake_bin.mkdir()
    (fake_bin / "mount").write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$#\" -eq 0 ]; then\n"
        "  printf '%s' \"${FAKE_MOUNT_LIST:-}\"\n"
        "  [ ! -f \"$FAKE_MOUNT_STATE\" ] || cat \"$FAKE_MOUNT_STATE\"\n"
        "  exit 0\n"
        "fi\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_MOUNT_LOG\"\n"
        "if [ \"${1:-}\" = -t ] && [ \"${2:-}\" = smbfs ]; then\n"
        "  printf '%s on %s (smbfs, nodev, nosuid)\\n' \"$3\" \"$4\" > \"$FAKE_MOUNT_STATE\"\n"
        "fi\n",
        encoding="utf-8",
    )
    (fake_bin / "security").write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_SECURITY_LOG\"\n"
        "case \"$1\" in\n"
        "  add-generic-password|delete-generic-password) exit 0 ;;\n"
        "  find-generic-password)\n"
        "    [ \"${FAKE_SECURITY_MISSING:-0}\" = 1 ] && exit 44\n"
        "    printf '%s' 'stored-secret'; exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    for path in fake_bin.iterdir():
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return fake_bin


def script_env(root: Path, fake_bin: Path) -> Dict[str, str]:
    return {
        "HOME": str(root / "home"),
        "AKBS_ROOT": str(root / "home" / "akbs"),
        "ANDROID_WORK_ROOT": str(root / "home" / "work"),
        "CODEX_CREDENTIALS_DIR": str(root / "home" / ".servers" / "credentials"),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_MOUNT_LOG": str(root / "mount.log"),
        "FAKE_MOUNT_STATE": str(root / "mount.state"),
        "FAKE_SECURITY_LOG": str(root / "security.log"),
    }


def install_python_instrumentation(fake_bin: Path, prelude: str) -> None:
    python = fake_bin / "python3"
    python.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "script_arg = sys.argv[1]\n"
        "sys.argv = sys.argv[1:]\n"
        "if script_arg == '-':\n"
        "    source = sys.stdin.read()\n"
        "    filename = '<stdin>'\n"
        "else:\n"
        "    with open(script_arg, encoding='utf-8') as handle:\n"
        "        source = handle.read()\n"
        "    filename = script_arg\n"
        f"{prelude}\n"
        "namespace = {'__name__': '__main__', '__file__': filename}\n"
        "exec(compile(source, filename, 'exec'), namespace)\n",
        encoding="utf-8",
    )
    python.chmod(python.stat().st_mode | stat.S_IXUSR)


def make_fake_channel(root: Path, *, remote_root: str, platform: str, sdk_name: str) -> tuple[Path, Path]:
    channel = root / "fake-channel.py"
    log = root / "fake-channel.log"
    channel.write_text(
        f"#!{sys.executable}\n"
        "import os, pathlib, sys\n"
        "pathlib.Path(os.environ['FAKE_CHANNEL_LOG']).write_text('\\0'.join(sys.argv[1:]), encoding='utf-8')\n"
        "print('COMMAND_STARTED id=fake session=codex-android-0123456789abcdef')\n"
        f"print('REMOTE_ROOT={remote_root}')\n"
        f"print('PLATFORM={platform}')\n"
        f"print('SDK_NAME={sdk_name}')\n"
        f"print('SOURCE_PLATFORM={platform}')\n"
        f"print('SOURCE_SDK_NAME={sdk_name}')\n"
        "print('SOURCE_SDK_SOURCE=project_branch')\n",
        encoding="utf-8",
    )
    channel.chmod(0o755)
    return channel, log


def register_args(
    env: Dict[str, str],
    registry_dir: Path,
    *,
    share: str,
    project: str,
) -> list[str]:
    mount_point = Path(env["ANDROID_WORK_ROOT"]) / "unisoc" / share
    return [
        "--server",
        "test61",
        "--server-ip",
        "192.168.100.23",
        "--smb-user",
        "test61",
        "--share",
        share,
        "--mount-point",
        str(mount_point),
        "--remote-share-path",
        f"/home/test61/unisoc/{share}",
        "--project",
        project,
        "--project-path",
        str(mount_point),
        "--platform",
        "unisoc",
        "--remote-project-path",
        f"/home/test61/unisoc/{share}",
        "--registry-dir",
        str(registry_dir),
    ]


class MacSourceAccessScriptsTests(unittest.TestCase):
    def test_register_failure_before_replace_preserves_previous_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = make_fake_bin(root)
            install_python_instrumentation(
                fake_bin,
                "import os\n"
                "def injected_replace_failure(*_args, **_kwargs):\n"
                "    raise OSError('injected replace failure')\n"
                "os.replace = injected_replace_failure",
            )
            env = script_env(root, fake_bin)
            registry_dir = root / "home" / ".servers" / "projects"
            registry_dir.mkdir(parents=True)
            registry_file = registry_dir / "test61.json"
            original = b'{"server":"test61","shares":{}}\n'
            registry_file.write_bytes(original)

            result = run_script(
                "register-project.sh",
                *register_args(env, registry_dir, share="TVE1088U", project="TVE1088U"),
                env=env,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(registry_file.read_bytes(), original)
            self.assertEqual(list(registry_dir.glob(".test61.json.tmp.*")), [])

    def test_concurrent_registers_do_not_lose_distinct_shares(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = make_fake_bin(root)
            install_python_instrumentation(
                fake_bin,
                "import json, os, time\n"
                "from pathlib import Path\n"
                "original_json_load = json.load\n"
                "def barrier_json_load(*args, **kwargs):\n"
                "    value = original_json_load(*args, **kwargs)\n"
                "    barrier = Path(os.environ['AKBS_STATE_TEST_BARRIER'])\n"
                "    barrier.mkdir(parents=True, exist_ok=True)\n"
                "    (barrier / str(os.getpid())).touch()\n"
                "    deadline = time.monotonic() + 1.0\n"
                "    while len(list(barrier.iterdir())) < 2 and time.monotonic() < deadline:\n"
                "        time.sleep(0.01)\n"
                "    return value\n"
                "json.load = barrier_json_load",
            )
            env = script_env(root, fake_bin)
            env["AKBS_STATE_TEST_BARRIER"] = str(root / "barrier")
            registry_dir = root / "home" / ".servers" / "projects"
            registry_dir.mkdir(parents=True)
            registry_file = registry_dir / "test61.json"
            registry_file.write_text(
                json.dumps(
                    {
                        "server": "test61",
                        "server_ip": "192.168.100.23",
                        "smb_user": "test61",
                        "shares": {},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            merged_env = os.environ.copy()
            merged_env.update(env)
            commands = [
                [
                    str(SCRIPT_DIR / "register-project.sh"),
                    *register_args(env, registry_dir, share=share, project=share),
                ]
                for share in ("TVE1088U", "TVA10A2R")
            ]

            processes = [
                subprocess.Popen(
                    command,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=merged_env,
                )
                for command in commands
            ]
            results = [process.communicate(timeout=10) for process in processes]

            self.assertEqual([process.returncode for process in processes], [0, 0], results)
            registry = json.loads(registry_file.read_text(encoding="utf-8"))
            self.assertEqual(set(registry["shares"]), {"TVE1088U", "TVA10A2R"})

    def test_keychain_reference_replace_failure_keeps_previous_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = make_fake_bin(root)
            install_python_instrumentation(
                fake_bin,
                "import os\n"
                "def injected_replace_failure(*_args, **_kwargs):\n"
                "    raise OSError('injected replace failure')\n"
                "os.replace = injected_replace_failure",
            )
            env = script_env(root, fake_bin)
            env["CODEX_TARGET_PASSWORD"] = "do-not-log-this-secret"
            reference = Path(env["CODEX_CREDENTIALS_DIR"]) / "local.keychain.env"
            reference.parent.mkdir(parents=True)
            original = b"LOCAL_USER=jinny\nLOCAL_SUDO_PASSWORD_STATE=stored\n"
            reference.write_bytes(original)

            result = run_script(
                "keychain-store.sh",
                "--role",
                "local",
                "--local-user",
                "jinny",
                env=env,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(reference.read_bytes(), original)
            self.assertNotIn("do-not-log-this-secret", result.stdout + result.stderr)

    def test_mount_share_saves_verified_credentials_with_real_script_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = make_fake_bin(root)
            env = script_env(root, fake_bin)
            env["TEST_SAMBA_PASSWORD"] = "secret"
            mount_point = Path(env["ANDROID_WORK_ROOT"]) / "unisoc" / "TVE1088U"

            result = run_script(
                "mount-share.sh",
                "--share",
                "//192.168.100.23/TVE1088U",
                "--mount-point",
                str(mount_point),
                "--user",
                "test61",
                "--remote-user",
                "test61",
                "--server",
                "192.168.100.23",
                "--password-env",
                "TEST_SAMBA_PASSWORD",
                "--save-credentials",
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("MOUNT_STATUS=mounted", result.stdout)
            credential_files = list(Path(env["CODEX_CREDENTIALS_DIR"]).glob("*.keychain.env"))
            self.assertEqual(len(credential_files), 1)
            self.assertIn("SMB_PASSWORD_STATE=stored", credential_files[0].read_text(encoding="utf-8"))
            self.assertEqual(stat.S_IMODE(credential_files[0].stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(credential_files[0].parent.stat().st_mode), 0o700)
            self.assertIn("add-generic-password", Path(env["FAKE_SECURITY_LOG"]).read_text(encoding="utf-8"))

    def test_local_keychain_reference_is_private(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = make_fake_bin(root)
            env = script_env(root, fake_bin)
            env["CODEX_TARGET_PASSWORD"] = "secret"

            result = run_script(
                "keychain-store.sh",
                "--role",
                "local",
                "--local-user",
                "jinny",
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            reference = Path(env["CODEX_CREDENTIALS_DIR"]) / "local.keychain.env"
            self.assertEqual(stat.S_IMODE(reference.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(reference.parent.stat().st_mode), 0o700)

    def test_mount_share_enforces_akbs_and_android_work_root_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = make_fake_bin(root)
            env = script_env(root, fake_bin)

            under_akbs = run_script(
                "mount-share.sh",
                "--share",
                "//server/share",
                "--mount-point",
                str(Path(env["AKBS_ROOT"]) / "source"),
                "--guest",
                env=env,
            )
            outside_work_root = run_script(
                "mount-share.sh",
                "--share",
                "//server/share",
                "--mount-point",
                str(root / "other"),
                "--guest",
                env=env,
            )

            self.assertEqual(under_akbs.returncode, 2)
            self.assertIn("不能挂到 AKBS_ROOT 下", under_akbs.stderr)
            self.assertNotIn("unbound variable", under_akbs.stderr)
            self.assertEqual(outside_work_root.returncode, 2)
            self.assertIn("必须位于 Android work root 下", outside_work_root.stderr)

    def test_register_and_restore_share_one_json_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = make_fake_bin(root)
            env = script_env(root, fake_bin)
            registry_dir = root / "home" / ".servers" / "projects"
            mount_point = Path(env["ANDROID_WORK_ROOT"]) / "unisoc" / "TVE1088U"
            project_path = mount_point

            register = run_script(
                "register-project.sh",
                "--server",
                "test61",
                "--server-ip",
                "192.168.100.23",
                "--smb-user",
                "test61",
                "--share",
                "TVE1088U",
                "--smb-path",
                "unisoc/huiwei_uis7885_5g",
                "--mount-point",
                str(mount_point),
                "--remote-share-path",
                "/home/test61/unisoc/huiwei_uis7885_5g",
                "--project",
                "TVE1088U",
                "--project-path",
                str(project_path),
                "--platform",
                "unisoc",
                "--remote-project-path",
                "/home/test61/unisoc/huiwei_uis7885_5g",
                "--registry-dir",
                str(registry_dir),
                env=env,
            )
            self.assertEqual(register.returncode, 0, register.stderr)
            registry = json.loads((registry_dir / "test61.json").read_text(encoding="utf-8"))
            self.assertEqual(registry["smb_user"], "test61")
            self.assertEqual(
                registry["shares"]["TVE1088U"]["mount_point"],
                "$HOME/work/unisoc/TVE1088U",
            )
            self.assertEqual(
                registry["shares"]["TVE1088U"]["projects"]["TVE1088U"]["local_path"],
                "$HOME/work/unisoc/TVE1088U",
            )
            self.assertEqual(
                registry["shares"]["TVE1088U"]["smb_path"],
                "unisoc/huiwei_uis7885_5g",
            )
            project_entry = registry["shares"]["TVE1088U"]["projects"]["TVE1088U"]
            self.assertEqual(registry["identity_schema"], "android-remote-project-identity-v1")
            self.assertEqual(project_entry["project_id"], "unisoc-TVE1088U")
            self.assertEqual(project_entry["ssh_host"], "test61")
            self.assertEqual(project_entry["remote_root"], "/home/test61/unisoc/huiwei_uis7885_5g")
            self.assertEqual(project_entry["mount_transport"], "smbfs")

            restore = run_script(
                "restore-mounts.sh",
                "--registry-dir",
                str(registry_dir),
                "--server",
                "test61",
                env=env,
            )
            self.assertEqual(restore.returncode, 0, restore.stderr)
            self.assertIn("RESTORE_STATUS=mounted server=test61 share=TVE1088U", restore.stdout)
            self.assertIn("source_verified=true", restore.stdout)
            self.assertIn("RESTORE_SUMMARY mounted=1", restore.stdout)
            mount_log = Path(env["FAKE_MOUNT_LOG"]).read_text(encoding="utf-8")
            self.assertIn(
                "//test61:stored-secret@192.168.100.23/unisoc/huiwei_uis7885_5g",
                mount_log,
            )

    def test_register_rejects_non_relative_smb_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = make_fake_bin(root)
            env = script_env(root, fake_bin)
            mount_point = Path(env["ANDROID_WORK_ROOT"]) / "mtk" / "TVE1065M_EG110"

            result = run_script(
                "register-project.sh",
                "--server",
                "test35",
                "--server-ip",
                "192.168.100.118",
                "--share",
                "TVE1065M_EG110",
                "--smb-path",
                "/work/mtk/u_mt8xxx_tablet",
                "--mount-point",
                str(mount_point),
                "--remote-share-path",
                "/home/test35/work/mtk/u_mt8xxx_tablet",
                "--project",
                "TVE1065M_EG110",
                "--project-path",
                str(mount_point),
                "--platform",
                "mtk",
                "--remote-project-path",
                "/home/test35/work/mtk/u_mt8xxx_tablet",
                env=env,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--smb-path 必须是相对服务器的 SMB 路径", result.stderr)

    def test_restore_rejects_existing_mount_from_different_smb_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = make_fake_bin(root)
            env = script_env(root, fake_bin)
            registry_dir = root / "projects"
            mount_point = Path(env["ANDROID_WORK_ROOT"]) / "unisoc" / "TVE1088U"
            register = run_script(
                "register-project.sh",
                *register_args(env, registry_dir, share="TVE1088U", project="TVE1088U"),
                env=env,
            )
            self.assertEqual(register.returncode, 0, register.stderr)
            env["FAKE_MOUNT_LIST"] = f"//other/share on {mount_point} (smbfs, nodev)\n"

            restore = run_script("restore-mounts.sh", "--registry-dir", str(registry_dir), env=env)

            self.assertEqual(restore.returncode, 4)
            self.assertIn("RESTORE_STATUS=failed", restore.stdout)
            self.assertIn("actual=//other/share", restore.stderr)

    def test_restore_does_not_report_success_without_json_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = make_fake_bin(root)
            env = script_env(root, fake_bin)
            registry_dir = root / "projects"
            registry_dir.mkdir()
            (registry_dir / "obsolete.env").write_text("PROJECT_PATHS=()\n", encoding="utf-8")

            result = run_script("restore-mounts.sh", "--registry-dir", str(registry_dir), env=env)

            self.assertEqual(result.returncode, 1)
            self.assertIn("entries=0", result.stdout)

    def test_restore_reports_missing_keychain_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = make_fake_bin(root)
            env = script_env(root, fake_bin)
            env["FAKE_SECURITY_MISSING"] = "1"
            registry_dir = root / "projects"
            mount_point = Path(env["ANDROID_WORK_ROOT"]) / "unisoc" / "TVE1088U"
            registry_dir.mkdir()
            register = run_script(
                "register-project.sh",
                *register_args(env, registry_dir, share="TVE1088U", project="TVE1088U"),
                env=env,
            )
            self.assertEqual(register.returncode, 0, register.stderr)

            result = run_script("restore-mounts.sh", "--registry-dir", str(registry_dir), env=env)

            self.assertEqual(result.returncode, 5)
            self.assertIn("RESTORE_STATUS=no_credentials", result.stdout)
            self.assertIn("no_credentials=1", result.stdout)

    def test_remote_inspection_uses_fake_channel_without_reading_mount(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mount_point = root / "human-mount"
            mount_point.mkdir()
            channel, channel_log = make_fake_channel(
                root,
                remote_root="/srv/android/TVA10A2R",
                platform="rk",
                sdk_name="TVA10A2R",
            )

            result = run_script(
                "detect-projects.sh",
                "--ssh-host",
                "builder",
                "--remote-root",
                "/srv/android/TVA10A2R",
                "--mount-point",
                str(mount_point),
                "--channel-script",
                str(channel),
                "--inspection-helper",
                str(INSPECTION_HELPER),
                env={"FAKE_CHANNEL_LOG": str(channel_log)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("INSPECTION_TRANSPORT=android-remote-channel-v2", result.stdout)
            self.assertIn("PLATFORM=rk", result.stdout)
            self.assertIn(f"ARTIFACT_BRIDGE_PATH={mount_point}", result.stdout)
            self.assertIn("run", channel_log.read_text(encoding="utf-8"))

    def test_project_level_remote_root_is_not_rederived_from_mount_basename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channel, channel_log = make_fake_channel(
                root,
                remote_root="/home/test35/work/mtk/u_mt8xxx_tablet",
                platform="mtk",
                sdk_name="TVE1065M",
            )

            result = run_script(
                "detect-projects.sh",
                "--ssh-host",
                "test35",
                "--remote-root",
                "/home/test35/work/mtk/u_mt8xxx_tablet",
                "--channel-script",
                str(channel),
                "--inspection-helper",
                str(INSPECTION_HELPER),
                env={"FAKE_CHANNEL_LOG": str(channel_log)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("REMOTE_ROOT=/home/test35/work/mtk/u_mt8xxx_tablet", result.stdout)
            self.assertNotIn("u_mt8xxx_tablet/TVE1065M", result.stdout)
            self.assertIn("PLATFORM=mtk", result.stdout)

    def test_scripts_and_docs_are_bash32_and_reference_consistent(self) -> None:
        forbidden = re.compile(r"\$\{[^}\n]*(?:\^\^|,,)[^}\n]*\}|\bmapfile\b|\bdeclare\s+-A\b")
        for script in sorted(SCRIPT_DIR.glob("*.sh")):
            text = script.read_text(encoding="utf-8")
            self.assertIsNone(forbidden.search(text), script)
            syntax = subprocess.run(
                ["/bin/bash", "-n", str(script)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(syntax.returncode, 0, f"{script}: {syntax.stderr}")

        detect_text = (SCRIPT_DIR / "detect-projects.sh").read_text(encoding="utf-8")
        self.assertNotIn("os.walk", detect_text)
        self.assertNotIn("/.repo", detect_text)
        self.assertNotRegex(detect_text, r"(?m)^\s*ssh\s")
        self.assertIn("ANDROID_REMOTE_CHANNEL_SCRIPT", detect_text)

        docs = [
            SKILL_DIR / "SKILL.md",
            REPO_ROOT / "docs" / "skills" / "android-mac-ops" / "android-source-access" / "README.md",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in docs)
        self.assertNotIn("save-credentials.sh", combined)
        self.assertNotIn(".codex/android-source-access", combined)
        self.assertNotIn("Work/Samba", combined)
        self.assertNotIn("/Users/jinny", combined)
        self.assertIn("~/.servers/projects/<server>.json", combined)
        for script_name in re.findall(r"scripts/([A-Za-z0-9_.-]+\.sh)", combined):
            self.assertTrue((SCRIPT_DIR / script_name).is_file(), script_name)


if __name__ == "__main__":
    unittest.main()
