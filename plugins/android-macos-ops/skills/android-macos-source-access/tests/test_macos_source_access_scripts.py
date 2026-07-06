from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


def run_script(script: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [str(SCRIPT_DIR / script), *args],
        check=False,
        text=True,
        capture_output=True,
        env=merged_env,
    )


def make_fake_bin(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "mount").write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$#\" -eq 0 ]; then exit 0; fi\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_MOUNT_LOG\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (fake_bin / "security").write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_SECURITY_LOG\"\n"
        "case \"$1\" in\n"
        "  add-generic-password) exit 0 ;;\n"
        "  find-generic-password) printf '%s' \"stored-secret\"; exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    for path in fake_bin.iterdir():
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return fake_bin


def test_mount_share_save_credentials_uses_keychain_store(tmp_path: Path) -> None:
    fake_bin = make_fake_bin(tmp_path)
    mount_point = tmp_path / "Samba" / "test61"
    security_log = tmp_path / "security.log"
    mount_log = tmp_path / "mount.log"

    result = run_script(
        "mount-share.sh",
        "--share",
        "//192.168.100.23/unisoc",
        "--mount-point",
        str(mount_point),
        "--user",
        "smb-user",
        "--remote-user",
        "smb-user",
        "--server",
        "192.168.100.23",
        "--password-env",
        "TEST_SAMBA_PASSWORD",
        "--save-credentials",
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "TEST_SAMBA_PASSWORD": "secret",
            "FAKE_MOUNT_LOG": str(mount_log),
            "FAKE_SECURITY_LOG": str(security_log),
            "CODEX_CREDENTIALS_DIR": str(tmp_path / "credentials"),
        },
    )

    assert result.returncode == 0, result.stderr
    assert "MOUNT_STATUS=mounted" in result.stdout
    assert "WARN: Keychain 保存失败" not in result.stderr
    assert "add-generic-password" in security_log.read_text(encoding="utf-8")
    env_files = list((tmp_path / "credentials").glob("*.keychain.env"))
    assert len(env_files) == 1
    assert "SMB_PASSWORD_STATE=stored" in env_files[0].read_text(encoding="utf-8")


def test_mount_share_default_state_dir_is_home_servers(tmp_path: Path) -> None:
    fake_bin = make_fake_bin(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    mount_point = tmp_path / "Samba" / "test61"
    security_log = tmp_path / "security.log"
    mount_log = tmp_path / "mount.log"

    result = run_script(
        "mount-share.sh",
        "--share",
        "//192.168.100.23/unisoc",
        "--mount-point",
        str(mount_point),
        "--user",
        "smb-user",
        "--remote-user",
        "smb-user",
        "--server",
        "192.168.100.23",
        "--password-env",
        "TEST_SAMBA_PASSWORD",
        "--save-credentials",
        env={
            "HOME": str(home),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "TEST_SAMBA_PASSWORD": "secret",
            "FAKE_MOUNT_LOG": str(mount_log),
            "FAKE_SECURITY_LOG": str(security_log),
        },
    )

    assert result.returncode == 0, result.stderr
    env_files = list((home / ".servers" / "credentials").glob("*.keychain.env"))
    assert len(env_files) == 1
    assert not (home / ".codex" / "android-macos-source-access-info").exists()


def test_migrate_state_dir_moves_old_codex_state_to_servers(tmp_path: Path) -> None:
    home = tmp_path / "home"
    old_credentials = home / ".codex" / "android-macos-source-access-info" / "credentials"
    old_projects = home / ".codex" / "android-macos-source-access-info" / "projects"
    old_credentials.mkdir(parents=True)
    old_projects.mkdir(parents=True)
    (old_credentials / "abc.keychain.env").write_text("SMB_PASSWORD_STATE=stored\n", encoding="utf-8")
    (old_projects / "test61.json").write_text('{"server":"test61"}\n', encoding="utf-8")

    result = run_script("migrate-state-dir.sh", env={"HOME": str(home)})

    assert result.returncode == 0, result.stderr
    assert "MIGRATION_STATUS=migrated" in result.stdout
    assert (home / ".servers" / "credentials" / "abc.keychain.env").is_file()
    assert (home / ".servers" / "projects" / "test61.json").is_file()
    assert not (home / ".codex" / "android-macos-source-access-info").exists()


def test_register_project_and_restore_mounts_use_same_json_registry(tmp_path: Path) -> None:
    fake_bin = make_fake_bin(tmp_path)
    registry_dir = tmp_path / "projects"
    mount_point = tmp_path / "Samba" / "test61"

    register = run_script(
        "register-project.sh",
        "--server",
        "test61",
        "--server-ip",
        "192.168.100.23",
        "--share",
        "unisoc",
        "--mount-point",
        str(mount_point),
        "--remote-share-path",
        "/home/test61/unisoc",
        "--project",
        "huiwei_uis7885_5g",
        "--project-path",
        str(mount_point / "huiwei_uis7885_5g"),
        "--platform",
        "unisoc",
        "--remote-project-path",
        "/home/test61/unisoc/huiwei_uis7885_5g",
        "--registry-dir",
        str(registry_dir),
    )
    assert register.returncode == 0, register.stderr
    registry = json.loads((registry_dir / "test61.json").read_text(encoding="utf-8"))
    assert registry["shares"]["unisoc"]["mount_point"] == str(mount_point)

    restore = run_script(
        "restore-mounts.sh",
        "--registry-dir",
        str(registry_dir),
        "--server",
        "test61",
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "FAKE_MOUNT_LOG": str(tmp_path / "mount.log"),
            "FAKE_SECURITY_LOG": str(tmp_path / "security.log"),
        },
    )

    assert restore.returncode == 0, restore.stderr
    assert "RESTORE_STATUS=mounted server=test61 share=unisoc" in restore.stdout
    assert "RESTORE_SUMMARY mounted=1" in restore.stdout
    assert "//test61:stored-secret@192.168.100.23/unisoc" in (tmp_path / "mount.log").read_text(
        encoding="utf-8"
    )


def test_resolve_akbs_root_defaults_and_env_override(tmp_path: Path) -> None:
    default = run_script("resolve-akbs-root.sh")
    assert default.returncode == 0
    assert "AKBS_ROOT=/Users/jinny/Work/AKBS" in default.stdout

    override = tmp_path / "AKBS"
    result = run_script("resolve-akbs-root.sh", env={"AKBS_ROOT": str(override)})
    assert result.returncode == 0
    assert f"AKBS_ROOT={override}" in result.stdout

    samba_default = run_script("resolve-samba-root.sh")
    assert samba_default.returncode == 0
    assert "SAMBA_SOURCE_ROOT=/Users/jinny/Work/Samba" in samba_default.stdout

    samba_override = tmp_path / "Samba"
    samba_result = run_script("resolve-samba-root.sh", env={"SAMBA_SOURCE_ROOT": str(samba_override)})
    assert samba_result.returncode == 0
    assert f"SAMBA_SOURCE_ROOT={samba_override}" in samba_result.stdout


def test_mount_share_rejects_mounting_sources_under_akbs_root(tmp_path: Path) -> None:
    result = run_script(
        "mount-share.sh",
        "--share",
        "//192.168.100.23/unisoc",
        "--mount-point",
        str(tmp_path / "AKBS" / "source"),
        "--guest",
        env={"AKBS_ROOT": str(tmp_path / "AKBS"), "SAMBA_SOURCE_ROOT": str(tmp_path / "Samba")},
    )

    assert result.returncode == 2
    assert "不能挂到 AKBS_ROOT 下" in result.stderr
    assert "unbound variable" not in result.stderr


def test_mount_share_akbs_root_error_is_bash32_safe(tmp_path: Path) -> None:
    script = f"""
set -eu
mount_point={str(tmp_path / "AKBS" / "source")!r}
akbs_root={str(tmp_path / "AKBS")!r}
samba_root={str(tmp_path / "Samba")!r}
die() {{ echo "ERROR: $*" >&2; exit "$1"; }}
case "$mount_point" in
  "$akbs_root"|"$akbs_root"/*)
    die 2 "SMB/Samba 源码不能挂到 AKBS_ROOT 下: ${{mount_point}}；请使用 Samba source root: ${{samba_root}}"
    ;;
esac
"""
    result = subprocess.run(["bash", "-c", script], check=False, text=True, capture_output=True)

    assert result.returncode == 2
    assert "不能挂到 AKBS_ROOT 下" in result.stderr
    assert "unbound variable" not in result.stderr
