from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Optional


REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_DIR = REPO_ROOT / "plugins" / "android-mac-ops" / "skills" / "android-source-access"
SCRIPT_DIR = SKILL_DIR / "scripts"


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
        "if [ \"$#\" -eq 0 ]; then printf '%s' \"${FAKE_MOUNT_LIST:-}\"; exit 0; fi\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_MOUNT_LOG\"\n",
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
        "FAKE_SECURITY_LOG": str(root / "security.log"),
    }


class MacSourceAccessScriptsTests(unittest.TestCase):
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
            self.assertIn("add-generic-password", Path(env["FAKE_SECURITY_LOG"]).read_text(encoding="utf-8"))

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
            (registry_dir / "test61.json").write_text(
                json.dumps(
                    {
                        "server": "test61",
                        "server_ip": "192.168.100.23",
                        "smb_user": "test61",
                        "shares": {"TVE1088U": {"mount_point": str(mount_point), "projects": {}}},
                    }
                ),
                encoding="utf-8",
            )

            result = run_script("restore-mounts.sh", "--registry-dir", str(registry_dir), env=env)

            self.assertEqual(result.returncode, 5)
            self.assertIn("RESTORE_STATUS=no_credentials", result.stdout)
            self.assertIn("no_credentials=1", result.stdout)

    def test_local_project_scan_works_without_gnu_find(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "share" / "TVA10A2R"
            (project / "build").mkdir(parents=True)
            (project / "frameworks").mkdir()
            (project / "device" / "rockchip").mkdir(parents=True)

            result = run_script(
                "detect-projects.sh",
                "--mount-point",
                str(root / "share"),
                "--max-depth",
                "2",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"PROJECT_PATH={project}", result.stdout)
            self.assertIn("PLATFORM=rk", result.stdout)

    def test_project_level_mount_root_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "work" / "mtk" / "TVE1065M"
            (project / "build").mkdir(parents=True)
            (project / "frameworks").mkdir()
            (project / "vendor" / "mediatek").mkdir(parents=True)

            result = run_script("detect-projects.sh", "--mount-point", str(project), "--max-depth", "1")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"PROJECT_PATH={project}", result.stdout)
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
        local_scan = detect_text.split("# ── 扫描项目目录 ──", 1)[1]
        self.assertNotIn("-maxdepth", local_scan)
        self.assertNotIn("-mindepth", local_scan)

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
