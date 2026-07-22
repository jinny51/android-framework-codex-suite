from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = REPO_ROOT / "shared" / "android_source_access" / "remote_inspector.sh"
RUNTIME_COPIES = (
    REPO_ROOT
    / "plugins"
    / "android-mac-ops"
    / "lib"
    / "android_source_access"
    / "remote_inspector.sh",
    REPO_ROOT
    / "plugins"
    / "android-wsl-ops"
    / "lib"
    / "android_source_access"
    / "remote_inspector.sh",
)
WSL_ENTRY = (
    REPO_ROOT
    / "plugins"
    / "android-wsl-ops"
    / "skills"
    / "android-source-access"
    / "scripts"
    / "inspect-android-sdk.sh"
)
MAC_ENTRY = (
    REPO_ROOT
    / "plugins"
    / "android-mac-ops"
    / "skills"
    / "android-source-access"
    / "scripts"
    / "detect-projects.sh"
)


def init_branch(path: Path, branch: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "init", "-q", "-b", branch, str(path)],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stderr


def run_inspector(
    script: Path,
    root: Path,
    *,
    platform: str = "",
    sdk_name: str = "",
    accept_platform_conflict: bool = False,
    accept_sdk_name_conflict: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            str(script),
            str(root),
            platform,
            sdk_name,
            "1" if accept_platform_conflict else "0",
            "1" if accept_sdk_name_conflict else "0",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def parse_simple_env(stdout: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in stdout.splitlines():
        key, value = line.split("=", 1)
        result[key] = value
    return result


def test_remote_inspector_runtime_copies_match_repository_owner() -> None:
    expected = CANONICAL.read_bytes()
    assert expected
    for runtime_copy in RUNTIME_COPIES:
        assert runtime_copy.read_bytes() == expected, runtime_copy


def test_platform_entries_are_thin_remote_inspector_adapters() -> None:
    wsl = WSL_ENTRY.read_text(encoding="utf-8")
    mac = MAC_ENTRY.read_text(encoding="utf-8")

    for source in (wsl, mac):
        assert "lib/android_source_access/remote_inspector.sh" in source
        assert "score_rk=0" not in source
        assert "first_assignment()" not in source
    assert "remote_script='" not in wsl


def test_mtk_alias_and_project_branch_have_one_identity(tmp_path: Path) -> None:
    root = tmp_path / "mtk-sdk"
    (root / "build").mkdir(parents=True)
    (root / "vendor").mkdir()
    (root / "hardware").mkdir()
    (root / "device" / "mtk" / "common").mkdir(parents=True)
    (root / "device" / "mtk" / "common" / "BoardConfig.mk").write_text(
        "TARGET_BOARD_PLATFORM := mt8775\n",
        encoding="utf-8",
    )
    init_branch(root / "frameworks" / "base", "TVE1097M")

    outputs = []
    for script in (CANONICAL, *RUNTIME_COPIES):
        result = run_inspector(script, root)
        assert result.returncode == 0, result.stderr
        outputs.append(parse_simple_env(result.stdout))

    assert outputs[0] == outputs[1] == outputs[2]
    assert outputs[0]["PLATFORM"] == "mtk"
    assert outputs[0]["SDK_NAME"] == "TVE1097M"
    assert outputs[0]["SOURCE_SDK_SOURCE"] == "project_branch"
    assert outputs[0]["TARGET_BOARD_PLATFORM"] == "mt8775"
    assert outputs[0]["PLATFORM_SCORE_MTK"] == "50"


def test_equal_platform_scores_keep_current_wsl_tie_break(tmp_path: Path) -> None:
    root = tmp_path / "tie-sdk"
    (root / "build").mkdir(parents=True)
    (root / "vendor").mkdir()
    (root / "hardware").mkdir()
    (root / "device" / "rockchip").mkdir(parents=True)
    (root / "device" / "sprd").mkdir(parents=True)
    (root / "device" / "rockchip" / "BoardConfig.mk").write_text(
        "BRANCH_BUILDTYPE := TIE-SDK\n",
        encoding="utf-8",
    )

    result = run_inspector(CANONICAL, root)

    assert result.returncode == 0, result.stderr
    values = parse_simple_env(result.stdout)
    assert values["PLATFORM"] == "rk"
    assert values["SDK_NAME"] == "TIE-SDK"
    assert values["PLATFORM_SCORE_RK"] == values["PLATFORM_SCORE_UNISOC"] == "30"


def test_explicit_platform_conflict_keeps_existing_exit_contract(tmp_path: Path) -> None:
    root = tmp_path / "rk-sdk"
    (root / "build").mkdir(parents=True)
    (root / "device" / "rockchip" / "rk3588").mkdir(parents=True)
    (root / "device" / "rockchip" / "rk3588" / "BoardConfig.mk").write_text(
        "TARGET_BOARD_PLATFORM := rk3588\nBRANCH_BUILDTYPE := TVA10A2R\n",
        encoding="utf-8",
    )

    rejected = run_inspector(CANONICAL, root, platform="unisoc")
    accepted = run_inspector(
        CANONICAL,
        root,
        platform="unisoc",
        sdk_name="TVA10A2R",
        accept_platform_conflict=True,
    )

    assert rejected.returncode == 7
    assert "PLATFORM_CONFLICT user_platform=unisoc source_platform=rk" in rejected.stderr
    assert accepted.returncode == 0, accepted.stderr
    assert parse_simple_env(accepted.stdout)["PLATFORM"] == "unisoc"


def test_missing_android_markers_and_sdk_name_fail_closed(tmp_path: Path) -> None:
    missing_markers = tmp_path / "not-android"
    missing_markers.mkdir()
    no_name = tmp_path / "no-name"
    (no_name / "build").mkdir(parents=True)
    (no_name / "vendor" / "sprd").mkdir(parents=True)

    marker_result = run_inspector(CANONICAL, missing_markers)
    name_result = run_inspector(CANONICAL, no_name)

    assert marker_result.returncode == 4
    assert "ANDROID_MARKERS_MISSING" in marker_result.stderr
    assert name_result.returncode == 6
    assert "SDK_NAME_REQUIRED" in name_result.stderr
