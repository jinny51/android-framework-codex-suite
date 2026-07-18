from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_ROOT = REPO_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "scripts"
PLUGIN_LIB = REPO_ROOT / "plugins" / "android-framework-ops" / "lib"
for root in (SCRIPTS_ROOT, PLUGIN_LIB):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from android_framework_ops.knowledge_rules import patch_upload_gate_errors, source_version_compatibility_matrix
from akbs_intake import submit
from akbs_intake.patch import information_completion


REQUEST_ID = "information-request-0123456789ab"
PATCH_SHA = "a" * 64


def config() -> dict[str, str]:
    return {
        "member_alias": "wick",
        "submission_api_base_url": "https://akbs.invalid/akbs/api",
    }


def detail_payload() -> dict:
    return {
        "information_request": {
            "request_id": REQUEST_ID,
            "patch_set_sha256": PATCH_SHA,
            "state": "open",
        },
        "human_visible": {"package_type": "补丁包"},
    }


class PatchPackageUnificationTests(unittest.TestCase):
    def test_source_capabilities_publish_unified_package_and_same_package_completion(self) -> None:
        matrix = source_version_compatibility_matrix()
        self.assertEqual(matrix["patch_package_unification_v1"]["min_plugin_version"], "1.0.139")
        self.assertEqual(matrix["queue_information_completion_v1"]["min_plugin_version"], "1.0.139")

    def test_framework_change_always_uses_patch_route_and_legacy_supplement_fails_closed(self) -> None:
        self.assertEqual(submit.upload_type_for_manifest({"package_kind": "framework_change"}), "patch")
        legacy = {
            "package_kind": "framework_change",
            "package_status": "validated",
            "supplement_for_package_key": "20260701/wick/legacy",
        }
        with self.assertRaises(SystemExit) as raised:
            submit.upload_type_for_manifest(legacy)
        self.assertIn("legacy_patch_contract_not_supported", str(raised.exception))
        self.assertEqual(len(patch_upload_gate_errors(legacy)), 1)
        self.assertIn("legacy_patch_contract_not_supported", patch_upload_gate_errors(legacy)[0])

    def test_completion_reloads_authoritative_patch_hash_and_sends_only_same_package_envelope(self) -> None:
        calls: list[object] = []

        def request_fn(request, **_kwargs):
            calls.append(request)
            if request.get_method() == "GET":
                return detail_payload(), {"request_id": "lookup-request"}
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(body["patch_set_sha256"], PATCH_SHA)
            self.assertEqual(body["statement"], "补充适用边界")
            self.assertEqual(body["fields"], {"applicability": "default_display"})
            self.assertEqual(len(body["attachments"]), 1)
            self.assertEqual(body["attachments"][0]["relative_path"], "materials/requirements/boundary.txt")
            self.assertNotIn("package_key", body)
            self.assertNotIn("supplement_for_package_key", body)
            return {"queue_state": "information_submitted", "envelope_revision": 2}, {"request_id": "submit-request"}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "boundary.txt").write_text("需求边界", encoding="utf-8")
            response = root / "response.json"
            response.write_text(
                json.dumps(
                    {
                        "schema": information_completion.COMPLETION_SCHEMA,
                        "request_id": REQUEST_ID,
                        "statement": "补充适用边界",
                        "fields": {"applicability": "default_display"},
                        "attachments": [
                            {
                                "relative_path": "materials/requirements/boundary.txt",
                                "source_path": "boundary.txt",
                            }
                        ],
                        "patch_set_sha256": "caller-must-not-control-this",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.object(information_completion, "request_json_with_metadata", side_effect=request_fn):
                result = information_completion.complete_information_request(config(), response)
        self.assertEqual(result["queue_state"], "information_submitted")
        self.assertEqual([call.get_method() for call in calls], ["GET", "POST"])

    def test_completion_rejects_patch_attachment_before_http(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "extra.patch").write_text("diff", encoding="utf-8")
            response = root / "response.json"
            response.write_text(
                json.dumps(
                    {
                        "schema": information_completion.COMPLETION_SCHEMA,
                        "request_id": REQUEST_ID,
                        "attachments": [
                            {"relative_path": "patches/extra.patch", "source_path": "extra.patch"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(
                information_completion,
                "request_json_with_metadata",
                return_value=(detail_payload(), {"request_id": "lookup-request"}),
            ) as request_fn:
                with self.assertRaises(SystemExit) as raised:
                    information_completion.complete_information_request(config(), response)
        self.assertIn("patch_asset_immutable", str(raised.exception))
        request_fn.assert_called_once()

    def test_completion_preserves_structured_non_patch_fields(self) -> None:
        fields = information_completion.completion_fields(
            {
                "projects": ["TVE1086U", "TVE1088U"],
                "code_anchors": {"files": ["frameworks/base/WindowManager.java"]},
                "summary": "  HDMI 边界  ",
                "title": "  ",
            }
        )
        self.assertEqual(fields["projects"], ["TVE1086U", "TVE1088U"])
        self.assertEqual(
            fields["code_anchors"],
            {"files": ["frameworks/base/WindowManager.java"]},
        )
        self.assertEqual(fields["summary"], "HDMI 边界")
        self.assertNotIn("title", fields)

    def test_completion_rejects_fields_outside_the_public_contract(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            information_completion.completion_fields({"supplement_mode": "field_correction"})
        self.assertIn("information_fields_unsupported", str(raised.exception))

    def test_completion_rejects_diff_and_empty_attachment_paths(self) -> None:
        with self.assertRaises(SystemExit) as diff_error:
            information_completion.safe_relative_path("materials/changed.diff")
        self.assertIn("patch_asset_immutable", str(diff_error.exception))
        with self.assertRaises(SystemExit) as empty_error:
            information_completion.safe_relative_path(".")
        self.assertIn("路径不安全", str(empty_error.exception))


if __name__ == "__main__":
    unittest.main()
