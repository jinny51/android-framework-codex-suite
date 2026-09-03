from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
CAPTURE_PATH = (
    ROOT
    / "plugins/android-engineering-ops/skills/android-patch-capture/scripts/capture_android_patch.py"
)
LEGACY_READER_PATH = (
    ROOT
    / "plugins/android-engineering-ops/skills/android-patch-capture/scripts/read_legacy_capture.py"
)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_component_model_supports_all_layers_and_orthogonal_overrides() -> None:
    capture = load(CAPTURE_PATH, "capture_v2_component_test")
    assert set(capture.COMPONENT_LAYERS) == {
        "application", "platform", "native", "hal", "kernel", "device", "build"
    }
    framework = capture.resolve_component(
        argparse.Namespace(
            change_domain="framework",
            component_layer="",
            component_type="",
            component_partition="",
            component_ownership="",
        )
    )
    assert framework == {
        "layer": "platform",
        "type": "framework",
        "partition": "unknown",
        "ownership": "unknown",
    }
    explicit = capture.resolve_component(
        argparse.Namespace(
            change_domain="",
            component_layer="hal",
            component_type="hidl_hal",
            component_partition="odm",
            component_ownership="soc_vendor",
        )
    )
    assert explicit == {
        "layer": "hal",
        "type": "hidl_hal",
        "partition": "odm",
        "ownership": "soc_vendor",
    }
    with pytest.raises(SystemExit, match="vendor is an ownership/partition facet"):
        capture.resolve_component(
            argparse.Namespace(
                change_domain="vendor",
                component_layer="",
                component_type="",
                component_partition="vendor",
                component_ownership="vendor",
            )
        )


def test_change_id_is_canonical_and_legacy_feature_conflict_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = load(CAPTURE_PATH, "capture_v2_change_id_test")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(CAPTURE_PATH),
            "--platform", "rk14",
            "--change-id", "fix-policy",
            "--summary", "Fix policy behavior",
            "--workflow-contract", "manual_import",
        ],
    )
    canonical = capture.parse_args()
    assert canonical.change_id == "fix-policy"
    assert canonical.legacy_feature is None

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(CAPTURE_PATH),
            "--platform", "rk14",
            "--change-id", "fix-policy",
            "--feature", "different-feature",
            "--summary", "Fix policy behavior",
            "--workflow-contract", "manual_import",
        ],
    )
    with pytest.raises(SystemExit):
        capture.parse_args()


def test_multi_component_capture_requires_primary_and_exact_repo_mappings() -> None:
    capture = load(CAPTURE_PATH, "capture_v2_multi_component_test")
    args = argparse.Namespace(
        component_specs=[
            "platform-core:platform:framework:system:aosp",
            "settings-ui:application:system_app:system_ext:product",
        ],
        primary_component_id="platform-core",
        change_domain="",
        component_layer="",
        component_type="",
        component_partition="",
        component_ownership="",
        repo_component=[
            "frameworks/base=platform-core",
            "packages/apps/Settings=settings-ui,platform-core",
        ],
    )
    components, primary = capture.resolve_components(args)
    assert primary == "platform-core"
    captures = [
        capture.RepositoryCapture(
            source_root="/src/frameworks/base",
            repo_path="frameworks/base",
            git_info={},
            diff_text="diff --git a/a b/a\n",
            facts={"content_sha1": "1"},
            module="frameworks-base",
            patch_name="rk14-frameworks-base@feature.patch",
            patch_rel="patches/rk14-frameworks-base@feature.patch",
        ),
        capture.RepositoryCapture(
            source_root="/src/packages/apps/Settings",
            repo_path="packages/apps/Settings",
            git_info={},
            diff_text="diff --git a/b b/b\n",
            facts={"content_sha1": "2"},
            module="settings",
            patch_name="rk14-settings@feature.patch",
            patch_rel="patches/rk14-settings@feature.patch",
        ),
    ]
    capture.bind_repository_components(args, captures, components)
    assert [(item.repository_id, item.component_ids) for item in captures] == [
        ("repo-001", ("platform-core",)),
        ("repo-002", ("settings-ui", "platform-core")),
    ]
    missing = argparse.Namespace(**{**vars(args), "repo_component": args.repo_component[:1]})
    with pytest.raises(SystemExit, match="every captured repository"):
        capture.bind_repository_components(missing, captures, components)
    unused = argparse.Namespace(
        **{
            **vars(args),
            "repo_component": [
                "frameworks/base=platform-core",
                "packages/apps/Settings=platform-core",
            ],
        }
    )
    with pytest.raises(SystemExit, match="every declared component"):
        capture.bind_repository_components(unused, captures, components)


def test_multi_component_generated_evidence_requires_exact_explicit_scope() -> None:
    capture = load(CAPTURE_PATH, "capture_v2_evidence_scope_test")
    components = [{"id": "platform-core"}, {"id": "settings-ui"}]
    items = [
        {"id": "changed-files"},
        {"id": "verification-result"},
        {"id": "rollback-plan"},
        {"id": "search-before-change"},
        {"id": "build-result", "component_ids": ["settings-ui"]},
    ]
    with pytest.raises(SystemExit, match="explicit --evidence-component"):
        capture.bind_generated_evidence_components(items, components, [])

    scoped = copy.deepcopy(items)
    capture.bind_generated_evidence_components(
        scoped,
        components,
        [
            "verification-result:platform-core",
            "rollback-plan:settings-ui",
            "search-before-change:settings-ui",
        ],
    )
    by_id = {item["id"]: item["component_ids"] for item in scoped}
    assert by_id["changed-files"] == ["platform-core", "settings-ui"]
    assert by_id["verification-result"] == ["platform-core"]
    assert by_id["rollback-plan"] == ["settings-ui"]
    assert by_id["search-before-change"] == ["settings-ui"]
    assert by_id["build-result"] == ["settings-ui"]


def test_component_assertion_contract_is_producer_owned_and_closed(tmp_path: Path) -> None:
    capture = load(CAPTURE_PATH, "capture_v2_component_assertion_test")
    source = tmp_path / "component-assertion.json"
    valid = {
        "kind": "component_assertion",
        "result": "INFO",
        "component_ids": ["platform-core", "settings-ui"],
        "assertions": [
            {
                "component_id": "platform-core",
                "assertion_id": "api_resource_compatibility",
                "result": "INFO",
                "observations": ["API surface inspected"],
            },
            {
                "component_id": "settings-ui",
                "assertion_id": "permission_signing_compatibility",
                "result": "FAIL",
                "observations": ["signature differs"],
            },
        ],
    }
    capture.validate_component_assertion_payload(
        valid,
        valid["component_ids"],
        source,
    )

    consumer_group = copy.deepcopy(valid)
    consumer_group["assertions"][0]["group_id"] = "api_or_resource_compatibility"
    with pytest.raises(SystemExit, match="observations"):
        capture.validate_component_assertion_payload(
            consumer_group,
            consumer_group["component_ids"],
            source,
        )
    naked_pass = copy.deepcopy(valid)
    naked_pass["assertions"][0].update(result="PASS")
    naked_pass["assertions"][0].pop("observations")
    with pytest.raises(SystemExit, match="observations"):
        capture.validate_component_assertion_payload(
            naked_pass,
            naked_pass["component_ids"],
            source,
        )
    outer_pass = copy.deepcopy(valid)
    outer_pass["result"] = "PASS"
    with pytest.raises(SystemExit, match="result=INFO"):
        capture.validate_component_assertion_payload(
            outer_pass,
            outer_pass["component_ids"],
            source,
        )
    incomplete_union = copy.deepcopy(valid)
    incomplete_union["assertions"] = incomplete_union["assertions"][:1]
    with pytest.raises(SystemExit, match="精确覆盖"):
        capture.validate_component_assertion_payload(
            incomplete_union,
            incomplete_union["component_ids"],
            source,
        )


@pytest.mark.parametrize(
    ("legacy", "layer", "component_type"),
    [
        ("system_app", "application", "system_app"),
        ("app", "application", "app"),
        ("hal", "hal", "hal"),
        ("native", "native", "native"),
        ("kernel", "kernel", "kernel"),
        ("driver", "kernel", "driver"),
        ("device", "device", "device"),
        ("build", "build", "build"),
    ],
)
def test_legacy_routes_never_invent_partition_or_ownership(
    legacy: str, layer: str, component_type: str,
) -> None:
    capture = load(CAPTURE_PATH, f"capture_legacy_hint_{legacy}")
    result = capture.resolve_component(
        argparse.Namespace(
            change_domain=legacy,
            component_layer="",
            component_type="",
            component_partition="",
            component_ownership="",
        )
    )
    assert result == {
        "layer": layer,
        "type": component_type,
        "partition": "unknown",
        "ownership": "unknown",
    }
    assert result["partition"] not in {"system", "system_ext", "data", "vendor", "boot"}
    assert result["ownership"] not in {"aosp", "product", "vendor"}


@pytest.mark.parametrize("status", ["draft", "candidate", "failed", "blocked"])
def test_capture_never_promotes_declared_status(status: str) -> None:
    capture = load(CAPTURE_PATH, f"capture_v2_status_{status}")
    assert capture.effective_capture_status(status, []) == status
    assert capture.effective_capture_status(status, ["qualification failed"]) == status
    assert capture.effective_capture_status("validated", ["qualification failed"]) == "candidate"


def test_new_writes_are_confined_to_canonical_root(tmp_path: Path, monkeypatch) -> None:
    capture = load(CAPTURE_PATH, "capture_v2_root_test")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    root = tmp_path / "codex/artifacts/android-patch-capture/packages"
    assert capture.require_canonical_package_root(root / "nested") == root / "nested"
    with pytest.raises(SystemExit, match="android-patch-capture/packages"):
        capture.require_canonical_package_root(tmp_path / "elsewhere")
    assert capture.validate_run_id("20260903-android_feature.patch") == (
        "20260903-android_feature.patch"
    )
    for unsafe in ("../escaped", "nested/package", "/absolute", ".", "", "x" * 129):
        with pytest.raises(SystemExit, match="safe 1..128 character token"):
            capture.validate_run_id(unsafe)


def test_legacy_import_is_read_only_and_never_pretends_v2_write(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    package = (
        tmp_path
        / "codex/artifacts/android-framework-patch-capture/packages/legacy-1"
    )
    package.mkdir(parents=True)
    (package / "manifest.json").write_text(
        json.dumps({"schema_version": "1.0", "status": "candidate"}) + "\n",
        encoding="utf-8",
    )
    (package / "README.md").write_text("legacy facts\n", encoding="utf-8")
    before = {
        path.relative_to(package).as_posix(): (path.read_bytes(), path.stat().st_mode)
        for path in package.rglob("*")
        if path.is_file()
    }
    reader = load(LEGACY_READER_PATH, "capture_legacy_reader_test")
    result = reader.inspect_legacy_package(package)
    after = {
        path.relative_to(package).as_posix(): (path.read_bytes(), path.stat().st_mode)
        for path in package.rglob("*")
        if path.is_file()
    }
    assert before == after
    assert result["normalized_component"]["layer"] == "platform"
    assert result["normalized_component"]["type"] == "framework"
    assert result["normalized_component"]["partition"] is None
    assert result["normalized_component"]["ownership"] is None
    assert result["read_only"] is True
    assert result["history_rewritten"] is False
    assert result["copied_to_new_root"] is False
    assert result["server_v2_writer"] == "disabled"
    assert not (tmp_path / "codex/artifacts/android-patch-capture").exists()
