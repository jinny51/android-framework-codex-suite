from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
CORE_PLUGIN = REPO_ROOT / "plugins" / "android-framework-ops"
WORKFLOW_SKILL = CORE_PLUGIN / "skills" / "android-framework-change-workflow" / "SKILL.md"
CAPTURE_SKILL = CORE_PLUGIN / "skills" / "android-framework-patch-capture" / "SKILL.md"
BUILD_SKILL = CORE_PLUGIN / "skills" / "android-remote-build-deploy" / "SKILL.md"
PUSH_SCRIPT = CORE_PLUGIN / "skills" / "android-remote-build-deploy" / "scripts" / "push_artifacts.py"
MARKETPLACE = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"


def load_push_module():
    spec = importlib.util.spec_from_file_location("push_artifacts_under_test", PUSH_SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {PUSH_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_change_workflow_keeps_the_ordered_engineering_and_knowledge_loop() -> None:
    text = WORKFLOW_SKILL.read_text(encoding="utf-8")
    ordered_steps = (
        "## Gate 1: Requirement and Primary Domain",
        "## Gate 2: Knowledge and Source Authority",
        "## Gate 3: Policy and Change Plan",
        "## Gate 4: Implement and Verify by Domain",
        "## Gate 5: Capture and Submission",
        "## Final Report",
    )

    positions = [text.index(step) for step in ordered_steps]
    assert positions == sorted(positions)
    for skill in (
        "android-knowledge-search",
        "android-source-access",
        "android-remote-channel",
        "android-remote-build-deploy",
        "android-framework-patch-capture",
        "android-framework-patch-intake",
    ):
        assert skill in text
    assert "necessary evidence, not final acceptance" in text
    assert "Run final acceptance against the requirement contract" in text


def test_only_validated_capture_continues_to_patch_intake() -> None:
    workflow = WORKFLOW_SKILL.read_text(encoding="utf-8")
    capture = CAPTURE_SKILL.read_text(encoding="utf-8")

    assert "`framework`: a validated capture may continue" in workflow
    assert "every other domain: stop after a validated local `android_feature_patch`" in workflow
    assert "`candidate`, `draft`, `failed`, and `blocked` captures stay local or in report context." in capture
    assert "Only a `validated` Framework capture may continue to `android-framework-patch-intake`." in capture


def test_platform_plugins_only_own_source_access_while_core_owns_build_and_channel() -> None:
    marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    marketplace_names = {item["name"] for item in marketplace["plugins"]}
    assert {"android-framework-ops", "android-wsl-ops", "android-mac-ops"} <= marketplace_names

    core_skills = {path.name for path in (CORE_PLUGIN / "skills").iterdir() if path.is_dir()}
    wsl_skills = {
        path.name
        for path in (REPO_ROOT / "plugins" / "android-wsl-ops" / "skills").iterdir()
        if path.is_dir()
    }
    mac_skills = {
        path.name
        for path in (REPO_ROOT / "plugins" / "android-mac-ops" / "skills").iterdir()
        if path.is_dir()
    }

    assert {"android-remote-build-deploy", "android-remote-channel"} <= core_skills
    assert wsl_skills == {"android-source-access"}
    assert mac_skills == {"android-source-access"}
    assert "android-remote-build-deploy" not in wsl_skills | mac_skills


def test_missing_adb_fails_before_delivery_evidence_is_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    evidence = project / ".codex" / "evidence" / "latest-build-delivery.json"
    module = load_push_module()
    monkeypatch.setenv("ADB", str(tmp_path / "missing-adb"))
    with pytest.raises(SystemExit, match="adb not found"):
        module.adb_command()
    assert not evidence.exists()


def test_build_delivery_evidence_cannot_claim_unscoped_final_acceptance() -> None:
    module = load_push_module()
    args = argparse.Namespace(
        adb_serial="device-1",
        artifact_sha1=[],
        remote_artifact=[],
        reboot=False,
        wait_boot=False,
        dry_run=False,
        remote_build_host="builder-1",
        remote_source_root="/srv/android/project",
        remote_build_command="build framework-services",
        remote_build_profile="framework-services",
        artifact_transfer="mounted source output",
    )

    payload = module.delivery_evidence(
        args,
        [(Path("/tmp/services.jar"), "/system/framework/services.jar")],
        [],
    )
    delivery_scope = payload.get("scope") in {"delivery", "artifact_delivery", "build_delivery"}
    acceptance_unverified = payload.get("requirement_acceptance") in {False, "unverified", "not_verified"}
    ambiguous_final_acceptance = (
        payload.get("kind") == "verification_result"
        and payload.get("result") == "PASS"
        and payload.get("method") == "device"
        and not delivery_scope
        and not acceptance_unverified
    )

    assert not ambiguous_final_acceptance
