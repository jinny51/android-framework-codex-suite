from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "plugins" / "akbs-member-ops"
LIB = PLUGIN / "lib"
SCRIPT = PLUGIN / "skills" / "akbs-patch-submit" / "scripts" / "akbs_patch_submit.py"
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(PLUGIN / "internal" / "incoming-v1" / "scripts"))

from akbs_member_ops.incoming_v2.capture_adapter import preflight_capture  # noqa: E402
from akbs_member_ops.incoming_v2 import capture_adapter  # noqa: E402
from akbs_member_ops.incoming_v2 import validation  # noqa: E402
from akbs_member_ops.incoming_v2.validation import AndroidChangeV2Error  # noqa: E402


def write_json(path: Path, value: object) -> bytes:
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def refresh_inventory(package: Path, manifest: dict[str, object]) -> None:
    files = []
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.name == "manifest.json":
            continue
        raw = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(package).as_posix(),
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    manifest["file_inventory"] = {
        "algorithm": "sha256",
        "scope": "all_regular_package_files_except_manifest.json",
        "manifest_self_hash_excluded": True,
        "files": files,
    }
    write_json(package / "manifest.json", manifest)


def build_capture(package: Path) -> Path:
    package.mkdir(parents=True)
    (package / "README.md").write_text("# Feature\n", encoding="utf-8")
    patches = {
        "platform-patch": b"diff --git a/core.java b/core.java\n",
        "settings-patch": b"diff --git a/Settings.java b/Settings.java\n",
    }
    for patch_id, raw in patches.items():
        path = package / "patches" / f"{patch_id}.patch"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    package_check = {
        "status": "PASS",
        "errors": [],
        "warnings": [],
        "declared_package_status": "validated",
        "effective_package_status": "validated",
        "status_was_upgraded": False,
    }
    write_json(package / "evidence" / "package-check.json", package_check)
    write_json(package / "evidence" / "coding-standard-check.json", {"result": "PASS"})
    components = [
        {
            "id": "platform-core",
            "layer": "platform",
            "type": "framework",
            "partition": "system",
            "ownership": "aosp",
        },
        {
            "id": "settings-ui",
            "layer": "application",
            "type": "system_app",
            "partition": "system_ext",
            "ownership": "product",
        },
    ]
    repositories = [
        {
            "id": "repo-001",
            "repo_path": "frameworks/base",
            "root": "/source/frameworks/base",
            "component_ids": ["platform-core"],
            "git": {"head": "a" * 40, "branch": "feature"},
        },
        {
            "id": "repo-002",
            "repo_path": "packages/apps/Settings",
            "root": "/source/packages/apps/Settings",
            "component_ids": ["settings-ui"],
            "git": {"head": "b" * 40, "branch": "feature"},
        },
    ]
    patch_rows = []
    for patch_id, repository, component_id in (
        ("platform-patch", repositories[0], "platform-core"),
        ("settings-patch", repositories[1], "settings-ui"),
    ):
        raw = patches[patch_id]
        patch_rows.append(
            {
                "id": patch_id,
                "path": f"patches/{patch_id}.patch",
                "repository_id": repository["id"],
                "repo_path": repository["repo_path"],
                "component_ids": [component_id],
                "source_root": repository["root"],
                "content_sha1": hashlib.sha1(raw).hexdigest(),
                "status": "validated",
                "reuse_hint": True,
                "implementation_origin": "codex",
                "workflow_contract": "current_codex_skill",
                "captured_by": "codex",
                "project": "TVE8402M",
                "platform_token": "rk14",
                "platform": "rockchip",
                "android_version": "14",
                "facts": {"content_sha1": hashlib.sha1(raw).hexdigest()},
            }
        )
    evidence = [
        {
            "id": "package-check",
            "kind": "package_check",
            "path": "evidence/package-check.json",
            "result": "PASS",
            "scope": "feature",
            "summary": "local package checks",
            "component_ids": ["platform-core", "settings-ui"],
            "contract": "android-patch-capture-evidence-v1",
            "declared_claims": ["local_package_check_recorded"],
        },
        {
            "id": "coding-standard-check",
            "kind": "coding_standard_check",
            "path": "evidence/coding-standard-check.json",
            "result": "PASS",
            "scope": "feature",
            "summary": "local coding check",
            "component_ids": ["platform-core", "settings-ui"],
            "contract": "android-patch-capture-evidence-v1",
            "declared_claims": ["local_policy_check_recorded"],
        },
    ]
    manifest: dict[str, object] = {
        "schema": "android-patch-capture-package-v2",
        "schema_version": "2.0",
        "package_type": "android_change_capture",
        "components": components,
        "primary_component_id": "platform-core",
        "change_id": "cross-component-feature",
        "readme": "README.md",
        "project": "TVE8402M",
        "platform_token": "rk14",
        "platform": "rockchip",
        "android_version": "14",
        "summary": "cross component change",
        "status": "validated",
        "declared_status": "validated",
        "effective_status": "validated",
        "status_was_upgraded": False,
        "implementation_origin": "codex",
        "workflow_contract": "current_codex_skill",
        "captured_by": "codex",
        "authority": {
            "owner": "android-patch-capture",
            "local_capture_only": True,
            "can_confirm_or_downgrade_status_only": True,
            "can_upload": False,
            "can_allocate_server_package_id": False,
            "can_materialize_knowledge": False,
        },
        "server_submission": {
            "v2_writer": "disabled",
            "v2_submission_allowed": False,
            "server_qualified": False,
            "note": "writer off",
        },
        "coding_standard_check": {
            "required": True,
            "mode": "capture_gate",
            "path": "evidence/coding-standard-check.json",
            "result": "PASS",
        },
        "created_at": "2026-09-03T01:00:00",
        "related_report_run_ids": [],
        "source_roots": [item["root"] for item in repositories],
        "git_repositories": repositories,
        "project_inference": {"project": "TVE8402M", "basis": ["test fixture"]},
        "verification_chain": {
            "remote_build": True,
            "local_delivery": True,
            "device_verification": True,
        },
        "patches": patch_rows,
        "evidence": evidence,
        "qualification_bindings": [
            {
                "component_id": component_id,
                "repository_ids": [repository_id],
                "patch_ids": [patch_id],
                "evidence_ids": ["package-check", "coding-standard-check"],
                "contract": "android-patch-capture-local-qualification-v1",
                "declared_claims": [
                    "patch_bytes_captured",
                    "repository_component_mapping_declared",
                    "local_checks_recorded",
                ],
            }
            for component_id, repository_id, patch_id in (
                ("platform-core", "repo-001", "platform-patch"),
                ("settings-ui", "repo-002", "settings-patch"),
            )
        ],
    }
    refresh_inventory(package, manifest)
    return package


class CaptureAdapterPreflightTest(unittest.TestCase):
    def test_capture_schema_is_byte_identical_and_hash_pinned(self) -> None:
        engineering_schema = (
            ROOT
            / "plugins"
            / "android-engineering-ops"
            / "contracts"
            / "android-patch-capture"
            / "v2"
            / "capture-package.schema.json"
        )
        member_schema = capture_adapter.CAPTURE_SCHEMA_PATH
        raw = member_schema.read_bytes()
        self.assertEqual(raw, engineering_schema.read_bytes())
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            validation.CONTRACT_SHA256["capture-package.schema.json"],
        )
        self.assertEqual(
            json.loads(raw)["$schema"],
            capture_adapter.DRAFT_2020_12_SCHEMA,
        )

    def test_draft_2020_schema_validation_runs_before_semantic_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            capture = build_capture(Path(temporary) / "capture")
            manifest = json.loads((capture / "manifest.json").read_text(encoding="utf-8"))
            manifest["unknown_field"] = "must fail structurally"
            write_json(capture / "manifest.json", manifest)
            with mock.patch.object(
                capture_adapter, "_validate_identity_status_authority"
            ) as semantic:
                with self.assertRaisesRegex(AndroidChangeV2Error, "additional properties"):
                    preflight_capture(capture)
            semantic.assert_not_called()

        with tempfile.TemporaryDirectory() as temporary:
            capture = build_capture(Path(temporary) / "capture")
            schema = validation._load_contract(capture_adapter.CAPTURE_SCHEMA_PATH)
            schema["$schema"] = "https://json-schema.org/draft/2019-09/schema"
            with mock.patch.object(capture_adapter, "_load_contract", return_value=schema), mock.patch.object(
                capture_adapter, "_validate_identity_status_authority"
            ) as semantic:
                with self.assertRaisesRegex(AndroidChangeV2Error, "does not declare Draft 2020-12"):
                    preflight_capture(capture)
            semantic.assert_not_called()

    def test_capture_schema_rejects_unknown_authority_shaped_fields(self) -> None:
        mutations = (
            ("top-level", lambda manifest: manifest.__setitem__("server_package_id", "fake")),
            (
                "repository",
                lambda manifest: manifest["git_repositories"][0].__setitem__(
                    "server_repository_id", "fake"
                ),
            ),
            (
                "patch",
                lambda manifest: manifest["patches"][0].__setitem__(
                    "server_patch_id", "fake"
                ),
            ),
            (
                "evidence",
                lambda manifest: manifest["evidence"][0].__setitem__(
                    "server_qualified", True
                ),
            ),
            (
                "qualification",
                lambda manifest: manifest["qualification_bindings"][0].__setitem__(
                    "server_qualification_id", "fake"
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                capture = build_capture(Path(temporary) / "capture")
                manifest = json.loads((capture / "manifest.json").read_text(encoding="utf-8"))
                mutate(manifest)
                write_json(capture / "manifest.json", manifest)
                with self.assertRaisesRegex(AndroidChangeV2Error, "additional properties"):
                    preflight_capture(capture)

    def test_valid_multi_component_capture_reports_only_blocked_gap_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            capture = build_capture(workspace / "capture")
            before = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for path in workspace.rglob("*")
                if path.is_file()
            }
            result = preflight_capture(capture)
            after = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for path in workspace.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(
                result["reason_code"], "android_change_v2_adapter_contracts_unavailable"
            )
            self.assertEqual(result["capture"]["change_id"], "cross-component-feature")
            self.assertEqual(result["capture"]["package_type"], "android_change_capture")
            self.assertEqual(result["capture"]["schema"], "android-patch-capture-package-v2")
            self.assertEqual(result["capture"]["schema_version"], "2.0")
            self.assertEqual(
                result["preflight"]["schema_dialect"],
                capture_adapter.DRAFT_2020_12_SCHEMA,
            )
            self.assertEqual(result["capture"]["primary_component_id"], "platform-core")
            self.assertEqual(
                [item["id"] for item in result["capture"]["components"]],
                ["platform-core", "settings-ui"],
            )
            self.assertEqual(
                result["capture"]["patches"][1]["component_ids"], ["settings-ui"]
            )
            self.assertFalse(result["adapter"]["canonical_package_created"])
            self.assertFalse(result["adapter"]["client_adapter_outputs_created"])
            self.assertFalse(result["writer"]["v1_fallback"])
            self.assertEqual(result["writer"]["network_requests"], 0)
            self.assertEqual(result["writer"]["files_written"], 0)
            gap = result["gaps"][0]
            self.assertEqual(
                gap["code"], "versioned_evidence_group_adapter_input_contracts_missing"
            )
            self.assertTrue(gap["groups"])

    def test_schema_status_authority_and_component_bindings_fail_closed(self) -> None:
        mutations = (
            ("schema", lambda manifest: manifest.__setitem__("schema_version", "1.0")),
            ("status", lambda manifest: manifest.__setitem__("effective_status", "candidate")),
            (
                "authority",
                lambda manifest: manifest["authority"].__setitem__("can_upload", True),
            ),
            (
                "component",
                lambda manifest: manifest["patches"][1].__setitem__(
                    "component_ids", ["platform-core"]
                ),
            ),
            ("top-change-domain", lambda manifest: manifest.__setitem__("change_domain", "framework")),
            (
                "patch-change-domain",
                lambda manifest: manifest["patches"][0].__setitem__("change_domain", "framework"),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                capture = build_capture(Path(temporary) / "capture")
                manifest = json.loads((capture / "manifest.json").read_text(encoding="utf-8"))
                mutate(manifest)
                write_json(capture / "manifest.json", manifest)
                with self.assertRaises(AndroidChangeV2Error):
                    preflight_capture(capture)

    def test_full_inventory_patch_hash_and_symlink_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            capture = build_capture(Path(temporary) / "capture")
            (capture / "unexpected.txt").write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(AndroidChangeV2Error, "file_inventory"):
                preflight_capture(capture)

        with tempfile.TemporaryDirectory() as temporary:
            capture = build_capture(Path(temporary) / "capture")
            patch = capture / "patches" / "platform-patch.patch"
            patch.write_text("different bytes", encoding="utf-8")
            manifest = json.loads((capture / "manifest.json").read_text(encoding="utf-8"))
            refresh_inventory(capture, manifest)
            with self.assertRaisesRegex(AndroidChangeV2Error, "content_sha1 differs"):
                preflight_capture(capture)

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            capture = build_capture(workspace / "capture")
            outside = workspace / "outside.json"
            outside.write_text('{"result":"PASS"}\n', encoding="utf-8")
            evidence = capture / "evidence" / "coding-standard-check.json"
            evidence.unlink()
            evidence.symlink_to(outside)
            with self.assertRaisesRegex(AndroidChangeV2Error, "symbolic link"):
                preflight_capture(capture)

    def test_evidence_component_result_and_path_bindings_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            capture = build_capture(Path(temporary) / "capture")
            manifest = json.loads((capture / "manifest.json").read_text(encoding="utf-8"))
            for evidence in manifest["evidence"]:
                evidence["component_ids"] = ["platform-core"]
            write_json(capture / "manifest.json", manifest)
            with self.assertRaisesRegex(AndroidChangeV2Error, "qualification evidence binding"):
                preflight_capture(capture)

        with tempfile.TemporaryDirectory() as temporary:
            capture = build_capture(Path(temporary) / "capture")
            write_json(capture / "evidence" / "coding-standard-check.json", {"result": "FAIL"})
            manifest = json.loads((capture / "manifest.json").read_text(encoding="utf-8"))
            refresh_inventory(capture, manifest)
            with self.assertRaisesRegex(AndroidChangeV2Error, "manifest result differs"):
                preflight_capture(capture)

        with tempfile.TemporaryDirectory() as temporary:
            capture = build_capture(Path(temporary) / "capture")
            manifest = json.loads((capture / "manifest.json").read_text(encoding="utf-8"))
            manifest["evidence"][1]["path"] = manifest["evidence"][0]["path"]
            write_json(capture / "manifest.json", manifest)
            with self.assertRaisesRegex(AndroidChangeV2Error, "paths must be unique"):
                preflight_capture(capture)

    def test_root_directory_swap_is_detected_while_pinned_inode_remains_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            capture = build_capture(workspace / "capture")
            displaced = workspace / "capture-displaced"
            replacement_sentinel = workspace / "capture" / "replacement-sentinel"
            original_inventory = capture_adapter._archive_inventory
            calls = 0

            def inventory_then_swap(root_fd: int) -> dict[str, dict[str, object]]:
                nonlocal calls
                result = original_inventory(root_fd)
                calls += 1
                if calls == 1:
                    capture.rename(displaced)
                    capture.mkdir()
                    replacement_sentinel.write_text("replacement", encoding="utf-8")
                return result

            with mock.patch.object(
                capture_adapter,
                "_archive_inventory",
                side_effect=inventory_then_swap,
            ):
                with self.assertRaisesRegex(AndroidChangeV2Error, "root pathname changed"):
                    preflight_capture(capture)
            self.assertEqual(replacement_sentinel.read_text(encoding="utf-8"), "replacement")
            self.assertTrue((displaced / "manifest.json").is_file())

    def test_semantic_evidence_read_is_bound_to_the_first_archive_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            capture = build_capture(Path(temporary) / "capture")
            original_read = capture_adapter._read_regular

            def substitute_after_inventory(
                root_fd: int,
                relative: str,
                *,
                max_bytes: int = capture_adapter.MAX_JSON_BYTES,
            ) -> bytes:
                if relative == "evidence/coding-standard-check.json":
                    return b'{"result":"FAIL"}\n'
                return original_read(root_fd, relative, max_bytes=max_bytes)

            with mock.patch.object(
                capture_adapter,
                "_read_regular",
                side_effect=substitute_after_inventory,
            ):
                with self.assertRaisesRegex(AndroidChangeV2Error, "pinned archive inventory"):
                    preflight_capture(capture)

    def test_cli_preflight_has_zero_network_write_or_v1_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            capture = build_capture(workspace / "capture")
            before = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for path in workspace.rglob("*")
                if path.is_file()
            }
            spec = importlib.util.spec_from_file_location("akbs_patch_submit_capture_test", SCRIPT)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            output = io.StringIO()
            with (
                mock.patch.object(
                    module,
                    "installed_plugin_family_status",
                    return_value={"status": "PASS", "blocking": False},
                ),
                mock.patch.object(module, "incoming_main") as v1_main,
                mock.patch.object(module, "route_arguments") as v1_router,
                mock.patch.object(urllib.request, "urlopen") as urlopen,
                mock.patch.object(Path, "write_bytes", side_effect=AssertionError("unexpected write")),
                mock.patch.object(Path, "write_text", side_effect=AssertionError("unexpected write")),
                mock.patch.object(Path, "mkdir", side_effect=AssertionError("unexpected mkdir")),
                contextlib.redirect_stdout(output),
            ):
                result = module.main(["android-change-v2", "adapt-capture", str(capture)])
            self.assertEqual(result, 1)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["status"], "BLOCKED")
            self.assertFalse(payload["adapter"]["output_created"])
            v1_main.assert_not_called()
            v1_router.assert_not_called()
            urlopen.assert_not_called()
            after = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for path in workspace.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
