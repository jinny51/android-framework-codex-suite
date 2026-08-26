from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "android-framework-ops"
PLUGIN_LIB = PLUGIN_ROOT / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from android_framework_ops.member_config import expand_codex_path, load_toml, parse_simple_toml
from android_framework_ops.patch_analysis import modules_from_files, semantic_flags, semantic_risk_areas
from android_framework_ops.project_registry import source_access_registry_clues


def test_member_config_helpers_share_toml_and_codex_path_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    assert expand_codex_path("${CODEX_HOME}/artifacts") == codex_home / "artifacts"
    assert expand_codex_path("$CODEX_HOME/report") == codex_home / "report"
    assert parse_simple_toml('[member]\nalias = "jinny"\nactive = true\ntags = ["a", "b"]\n') == {
        "member": {"alias": "jinny", "active": True, "tags": ["a", "b"]}
    }

    missing = tmp_path / "missing.toml"
    assert load_toml(missing) == {}
    with pytest.raises(ValueError):
        load_toml(missing, strict=True)


def test_project_registry_reads_current_wsl_env_contract(tmp_path: Path) -> None:
    registry = tmp_path / "projects"
    registry.mkdir()
    (registry / "test35-test35.env").write_text(
        "PROJECT_PATHS=('/home/jinny/work/rk/TVA10A2R')\n"
        "SAMBA_PROJECT_SHARES=('TVA10A2R')\n"
        "REMOTE_SSH_HOSTS=('test35')\n"
        "REMOTE_ROOTS=('/home/test35/rk/TVA10A2R')\n"
        "PLATFORMS=('rk')\n"
        "SDK_NAMES=('TVA10A2R')\n",
        encoding="utf-8",
    )

    clues = source_access_registry_clues(
        ["/home/jinny/work/rk/TVA10A2R/frameworks/base"],
        registry,
    )
    assert clues == [
        ("source-access registry project_id", "rk-TVA10A2R"),
        ("source-access registry sdk_name", "TVA10A2R"),
        ("source-access registry remote_root", "/home/test35/rk/TVA10A2R"),
        ("source-access registry share", "TVA10A2R"),
        ("source-access registry platform", "rk"),
        ("source-access registry ssh_host", "test35"),
    ]


def test_project_registry_reads_current_macos_json_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    registry = tmp_path / "projects"
    registry.mkdir()
    local_project = tmp_path / "work" / "mtk" / "TVE1065M_EG110"
    remote_project = "/home/test35/work/mtk/u_mt8xxx_tablet"
    (registry / "test35.json").write_text(
        json.dumps(
            {
                "server": "test35",
                "server_ip": "192.168.100.118",
                "smb_user": "test35",
                "shares": {
                    "work": {
                        "mount_point": "$HOME/work/mtk/TVE1065M_EG110",
                        "smb_path": "work/mtk/u_mt8xxx_tablet",
                        "remote_path": "/home/test35/work",
                        "projects": {
                            "TVE1065M_EG110": {
                                "platform": "mtk",
                                "local_path": "$HOME/work/mtk/TVE1065M_EG110",
                                "remote_path": remote_project,
                            }
                        },
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    for source_path in (local_project / "frameworks" / "base", Path(remote_project) / "frameworks" / "base"):
        clues = source_access_registry_clues([source_path], registry)
        assert ("source-access registry sdk_name", "TVE1065M_EG110") in clues
        assert ("source-access registry remote_root", remote_project) in clues
        assert ("source-access registry platform", "mtk") in clues
        assert ("source-access registry ssh_host", "test35") in clues


def test_member_entrypoints_do_not_reimplement_shared_parsers() -> None:
    paths = [
        PLUGIN_ROOT / "skills" / "android-framework-patch-capture" / "scripts" / "capture_framework_patch.py",
        PLUGIN_ROOT / "skills" / "android-knowledge-intake" / "scripts" / "akbs_intake" / "project_identity.py",
    ]
    assert all("def parse_shell_array" not in path.read_text(encoding="utf-8") for path in paths)

    config_paths = [
        PLUGIN_ROOT / "skills" / "android-knowledge-intake" / "scripts" / "akbs_intake" / "config.py",
        PLUGIN_ROOT / "skills" / "android-knowledge-search" / "scripts" / "knowledge_search" / "config.py",
    ]
    assert all("def parse_toml_scalar" not in path.read_text(encoding="utf-8") for path in config_paths)


def test_patch_analysis_is_shared_by_capture_and_intake() -> None:
    modules = modules_from_files(["frameworks/base/core/res/res/values/config.xml"])
    flags = semantic_flags("framework resource overlay", modules)
    assert modules == ["FrameworkResources"]
    assert "资源覆盖/配置优先级" in semantic_risk_areas(modules, flags)

    paths = [
        PLUGIN_ROOT / "skills" / "android-framework-patch-capture" / "scripts" / "capture_framework_patch.py",
        PLUGIN_ROOT / "skills" / "android-knowledge-intake" / "scripts" / "akbs_intake" / "patch" / "facts.py",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "def semantic_problem_solution" not in text
        assert "def semantic_risk_areas" not in text
