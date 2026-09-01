from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
CORE_PLUGIN = REPO_ROOT / "plugins/android-framework-ops"
CORE_LIB = CORE_PLUGIN / "lib"
if str(CORE_LIB) not in sys.path:
    sys.path.insert(0, str(CORE_LIB))

from android_engineering_ops.source_access import (  # noqa: E402
    ADAPTER_COMMANDS,
    UnsupportedSourceAccessHost,
    adapter_environment,
    adapter_root,
    detect_source_access_host,
    dispatch_adapter_command,
)


PLATFORM_PLUGINS = {
    "wsl": REPO_ROOT / "plugins/android-wsl-ops",
    "macos": REPO_ROOT / "plugins/android-mac-ops",
}
CORE_CLI = CORE_PLUGIN / "internal/android-source-access/scripts/android_source_access.py"


def test_host_detection_selects_wsl_or_macos_without_a_user_choice() -> None:
    wsl = detect_source_access_host(
        system="Linux",
        release="6.6.87.2-microsoft-standard-WSL2",
        version="#1 SMP",
        environ={},
    )
    assert wsl.host == "wsl"
    assert "linux-kernel-wsl-marker" in wsl.evidence
    macos = detect_source_access_host(
        system="Darwin",
        release="25.0.0",
        version="Darwin Kernel Version",
        environ={},
    )
    assert macos.host == "macos"


@pytest.mark.parametrize("system", ["Linux", "Windows", "FreeBSD", ""])
def test_unsupported_or_native_linux_hosts_fail_closed(system: str) -> None:
    with pytest.raises(UnsupportedSourceAccessHost, match="supports WSL and macOS only"):
        detect_source_access_host(
            system=system,
            release="6.8.0-generic",
            version="#1 SMP",
            environ={},
        )


def test_contract_has_one_internal_owner_and_current_platform_entries() -> None:
    contract = json.loads(
        (CORE_PLUGIN / "contracts/source-access/v1/adapter-contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["schema"] == "android-source-access-adapter-v1"
    assert contract["intent"] == "android-source-access"
    assert contract["implementation_owner"] == "android-framework-ops"
    assert contract["core_public_skill"] is False
    assert contract["public_entry_plugins"] == {
        "wsl": "android-wsl-ops",
        "macos": "android-mac-ops",
    }
    assert set(contract["adapters"]) == {"wsl", "macos"}


def test_core_does_not_expose_a_third_public_source_access_skill() -> None:
    assert not (CORE_PLUGIN / "skills/android-source-access").exists()
    manifest = (REPO_ROOT / "manifests/android-framework-ops.toml").read_text(
        encoding="utf-8"
    )
    plugin_json = (CORE_PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
    assert 'name = "android-source-access"' not in manifest
    assert "android-source-access" not in json.loads(plugin_json)["interface"]["defaultPrompt"]


@pytest.mark.parametrize("host", ["wsl", "macos"])
def test_core_adapter_contains_the_only_runtime_implementation(host: str) -> None:
    root = adapter_root(CORE_PLUGIN, host)
    assert (root / "lib/akbs_plugin_state/atomic.py").is_file()
    for command in ADAPTER_COMMANDS[host]:
        assert (root / "skills/android-source-access/scripts" / command).is_file()
    assert not (root / "skills/android-source-access/SKILL.md").exists()
    platform = PLATFORM_PLUGINS[host]
    assert not (platform / "lib/akbs_plugin_state").exists()


@pytest.mark.parametrize("host", ["wsl", "macos"])
def test_platform_commands_are_identical_thin_entries(host: str) -> None:
    scripts = PLATFORM_PLUGINS[host] / "skills/android-source-access/scripts"
    entry = (scripts / "_command_entry.sh").read_bytes()
    for command in ADAPTER_COMMANDS[host]:
        assert (scripts / command).read_bytes() == entry
    locator = (scripts / "_core_source_access.py").read_text(encoding="utf-8")
    assert "MIN_CORE_VERSION = (1, 0, 167)" in locator
    assert "os.execv(" in locator
    assert "plugins/cache" in locator
    assert "SOURCE_ACCESS_CORE_REQUIRED" in locator


def test_platform_locators_are_byte_identical() -> None:
    wsl = (
        PLATFORM_PLUGINS["wsl"]
        / "skills/android-source-access/scripts/_core_source_access.py"
    )
    mac = (
        PLATFORM_PLUGINS["macos"]
        / "skills/android-source-access/scripts/_core_source_access.py"
    )
    assert wsl.read_bytes() == mac.read_bytes()


def test_dispatch_preserves_command_arguments_and_injects_core_environment() -> None:
    host = detect_source_access_host(
        system="Linux",
        release="microsoft-standard-WSL2",
        version="#1",
        environ={},
    )
    calls: list[tuple[str, list[str], dict[str, str]]] = []

    def fake_execve(path: str, argv: list[str], env: dict[str, str]) -> object:
        calls.append((path, argv, env))
        return object()

    dispatch_adapter_command(
        CORE_PLUGIN,
        host,
        "restore-project-mount.sh",
        ["--list"],
        execve=fake_execve,
        base_environment={},
    )
    path, argv, env = calls[0]
    assert Path(path).name == "restore-project-mount.sh"
    assert argv[1:] == ["--list"]
    assert env["ANDROID_SOURCE_ACCESS_HOST"] == "wsl"
    assert env["ANDROID_SOURCE_ACCESS_ADAPTER_ROOT"].endswith(
        "adapters/source-access/wsl/skills/android-source-access"
    )


def test_expected_host_mismatch_fails_before_dispatch() -> None:
    env = os.environ.copy()
    env.update({"WSL_INTEROP": "/run/WSL/1_interop"})
    result = subprocess.run(
        [sys.executable, str(CORE_CLI), "--expected-host", "macos", "list-commands"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    assert result.returncode == 2
    assert "platform entry expects macos, detected wsl" in result.stderr
    assert result.stdout == ""


def test_current_wsl_public_entry_runs_core_and_macos_entry_fails_closed() -> None:
    env = os.environ.copy()
    env.update({"WSL_INTEROP": "/run/WSL/1_interop"})
    wsl_entry = (
        PLATFORM_PLUGINS["wsl"]
        / "skills/android-source-access/scripts/restore-project-mount.sh"
    )
    mac_entry = (
        PLATFORM_PLUGINS["macos"]
        / "skills/android-source-access/scripts/detect-projects.sh"
    )
    success = subprocess.run(
        [str(wsl_entry), "--help"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    assert success.returncode == 0, success.stderr
    assert "restore-project-mount.sh --list" in success.stdout

    wrong_host = subprocess.run(
        [str(mac_entry), "--help"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    assert wrong_host.returncode == 2
    assert "platform entry expects macos, detected wsl" in wrong_host.stderr
    assert wrong_host.stdout == ""


def test_versioned_plugin_cache_entry_reads_manifest_identity(tmp_path: Path) -> None:
    source = PLATFORM_PLUGINS["wsl"]
    manifest = json.loads(
        (source / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
    )
    installed = tmp_path / "android-wsl-ops" / manifest["version"]
    shutil.copytree(source, installed)
    entry = installed / "skills/android-source-access/scripts/restore-project-mount.sh"
    env = {
        **os.environ,
        "ANDROID_FRAMEWORK_OPS_ROOT": str(CORE_PLUGIN),
        "WSL_INTEROP": "/run/WSL/1_interop",
    }

    result = subprocess.run(
        [str(entry), "--help"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert "restore-project-mount.sh --list" in result.stdout


def test_internal_adapter_keeps_pseudo_plugin_relative_layout() -> None:
    for host, script in (
        ("wsl", "restore-project-mount.sh"),
        ("macos", "_keychain_helpers.sh"),
    ):
        scripts = adapter_root(CORE_PLUGIN, host) / "skills/android-source-access/scripts"
        atomic = (scripts / "../../../lib/akbs_plugin_state/atomic.py").resolve()
        assert atomic.is_file(), f"{host}/{script}: {atomic}"
        assert (scripts / script).is_file()
