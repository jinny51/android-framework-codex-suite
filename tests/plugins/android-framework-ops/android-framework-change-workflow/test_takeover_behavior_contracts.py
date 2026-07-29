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
    core_contract = text.split("## Core Contract", 1)[1].split("## Load References As Needed", 1)[0]
    ordered_steps = (
        "android-knowledge-search\n  -> search prior cases",
        "android-source-access\n  -> access/recover/identify source tree handoff",
        "android-framework-change-workflow\n  -> specify requirement or diagnose issue",
        "android-remote-build-deploy\n  -> build -> push/deploy -> return delivery evidence",
        "android-framework-change-workflow\n  -> final acceptance verification",
        "android-framework-patch-capture\n  -> package accepted or stage-worthy changes",
        "android-framework-patch-intake\n  -> generate member-side incoming package",
    )

    positions = [core_contract.index(step) for step in ordered_steps]
    assert positions == sorted(positions)
    assert "Build/deploy evidence is necessary but not sufficient." in text
    assert "Do not treat delivery as final correctness." in text
    assert "final device verification performed by this workflow" in text


def test_only_validated_capture_continues_to_patch_intake() -> None:
    workflow = WORKFLOW_SKILL.read_text(encoding="utf-8")
    capture = CAPTURE_SKILL.read_text(encoding="utf-8")

    assert "Only when the capture status is `validated`, invoke `android-framework-patch-intake`" in workflow
    assert "`candidate`, `draft`, `failed`, and `blocked` captures stay local or in report context." in capture
    assert "Only a `validated` capture may continue to `android-framework-patch-intake`." in capture


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


def test_missing_adb_fails_before_delivery_evidence_is_written(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    artifact = project / "services.jar"
    artifact.write_text("jar", encoding="utf-8")
    evidence = project / ".codex" / "evidence" / "latest-build-delivery.json"
    env = os.environ.copy()
    env["ADB"] = str(tmp_path / "missing-adb")
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            str(PUSH_SCRIPT),
            "--artifact",
            str(artifact),
            "--dest",
            "/system/framework/services.jar",
            "--dry-run",
            "--evidence-out",
            str(evidence),
        ],
        cwd=project,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode != 0
    assert "adb not found" in result.stderr
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
