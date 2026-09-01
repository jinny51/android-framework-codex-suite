from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PLUGIN = ROOT / "plugins/android-framework-ops"
WORKFLOW = PLUGIN / "skills/android-framework-change-workflow"
CAPTURE = PLUGIN / "skills/android-framework-patch-capture"
BUILD_DEPLOY = PLUGIN / "skills/android-remote-build-deploy"


def test_current_skill_id_exposes_all_controlled_android_domains() -> None:
    skill = (WORKFLOW / "SKILL.md").read_text(encoding="utf-8")
    contract = json.loads(
        (PLUGIN / "contracts/change-domain/v1/domain-profiles.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {
        "framework",
        "system_app",
        "app",
        "hal",
        "native",
        "vendor",
        "kernel",
        "driver",
        "device",
        "build",
    }
    assert set(contract["domains"]) == expected
    assert "name: android-framework-change-workflow" in skill
    for label in ("SystemApp", "App", "HAL", "native", "vendor", "kernel", "driver", "device", "build"):
        assert label in skill
    assert (WORKFLOW / "references/domain-routing.md").is_file()
    assert (WORKFLOW / "references/framework-domain-workflow.md").is_file()


def test_submission_boundary_is_framework_v1_only() -> None:
    workflow = (WORKFLOW / "SKILL.md").read_text(encoding="utf-8")
    capture = (CAPTURE / "SKILL.md").read_text(encoding="utf-8")
    assert "android_feature_patch" in workflow
    assert "android_feature_patch" in capture
    assert "Framework incoming v1" in workflow
    assert "Only a validated `framework` capture" in capture
    assert "Never relabel" in workflow


def test_source_authority_and_build_routes_cover_remote_and_local_projects() -> None:
    workflow = (WORKFLOW / "SKILL.md").read_text(encoding="utf-8")
    routing = (WORKFLOW / "references/domain-routing.md").read_text(encoding="utf-8")
    build_deploy = (BUILD_DEPLOY / "SKILL.md").read_text(encoding="utf-8")

    for authority in ("registered_remote_tree", "local_project"):
        assert authority in workflow
        assert authority in routing
    for route in ("remote_profile", "remote_project_command", "local_project_command"):
        assert route in workflow
        assert route in routing
    assert "Never reclassify SMB/CIFS-mounted Android source" in workflow
    assert "not a generic Gradle" in build_deploy
    assert "Kbuild/kernel" in build_deploy


def test_manifest_publishes_the_active_skill_set() -> None:
    manifest = (ROOT / "manifests/android-framework-ops.toml").read_text(encoding="utf-8")
    assert [line for line in manifest.splitlines() if line.startswith("name = ")] == [
        'name = "android-change-policy"',
        'name = "android-framework-change-workflow"',
        'name = "android-framework-patch-capture"',
        'name = "android-framework-patch-intake"',
        'name = "android-daily-report-intake"',
        'name = "android-weekly-report-intake"',
        'name = "android-knowledge-search"',
        'name = "android-knowledge-merge-review"',
        'name = "android-knowledge-intake"',
        'name = "android-member-setup"',
        'name = "android-remote-channel"',
        'name = "android-remote-build-deploy"',
    ]
