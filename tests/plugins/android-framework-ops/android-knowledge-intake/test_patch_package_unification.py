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
from akbs_intake import incoming_contract, submit
from akbs_intake.patch import information_completion


REQUEST_ID = "information-request-0123456789ab"
PATCH_SHA = "a" * 64
PATCH_PACKAGE_ID = "patch-package-01234567-89ab-5cde-8fab-0123456789ab"
SOURCE_PACKAGE_KEY = "20260701/wick/20260701-120000-patch"


def config() -> dict[str, str]:
    return {
        "member_alias": "wick",
        "submission_api_base_url": "https://akbs.invalid/akbs/api",
    }


def detail_payload() -> dict:
    return {
        "request_id": REQUEST_ID,
        "patch_package_id": PATCH_PACKAGE_ID,
        "package_key": SOURCE_PACKAGE_KEY,
        "queue_state": "information_required",
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
        self.assertEqual(matrix["patch_package_subject_v2"]["min_plugin_version"], "1.0.140")

    def test_framework_change_uses_patch_route_and_retired_protocol_has_one_boundary(self) -> None:
        self.assertEqual(submit.upload_type_for_manifest({"package_kind": "framework_change"}), "patch")
        legacy = {
            "package_kind": "framework_change",
            "package_status": "validated",
            "supplement_for_package_key": "20260701/wick/legacy",
        }
        with self.assertRaises(SystemExit) as raised:
            submit.upload_type_for_manifest(legacy)
        self.assertIn("legacy_patch_contract_not_supported", str(raised.exception))
        self.assertEqual(patch_upload_gate_errors(legacy), [])
        self.assertIn("legacy_patch_contract_not_supported", incoming_contract.legacy_patch_contract_error(legacy))

        for field in incoming_contract.retired_patch_business_fields():
            error = incoming_contract.legacy_patch_contract_error(
                {"package_kind": "framework_change", field: "legacy"}
            )
            self.assertIn(field, error)
        for value in incoming_contract.retired_patch_business_values():
            error = incoming_contract.legacy_patch_contract_error(
                {"package_kind": "framework_change", "business_state": value}
            )
            self.assertIn(value, error)

        nested = incoming_contract.legacy_patch_contract_error(
            {
                "package_kind": "framework_change",
                "metadata": {"logical_package_key": "legacy", "queue_state": "needs_evidence"},
            }
        )
        self.assertIn("logical_package_key", nested)
        self.assertIn("needs_evidence", nested)

        human_text = incoming_contract.legacy_patch_contract_error(
            {
                "package_kind": "framework_change",
                "summary": "supplement_package",
                "notes": "历史说明可以出现补证包一词。",
            }
        )
        self.assertEqual(human_text, "")

        ordinary_report = {
            "package_kind": "weekly_trace",
            "summary": "supplement_package",
            "notes": "Sessions are supplementary evidence only / session 只作补充证据",
        }
        self.assertEqual(incoming_contract.legacy_patch_contract_error(ordinary_report), "")

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
            self.assertNotIn("patch_package_id", body)
            self.assertNotIn("supplement_for_package_key", body)
            return {
                "request_id": REQUEST_ID,
                "patch_package_id": PATCH_PACKAGE_ID,
                "package_key": SOURCE_PACKAGE_KEY,
                "queue_state": "information_review",
                "envelope_revision": 2,
            }, {"request_id": "submit-request"}

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
        self.assertEqual(result["patch_package_id"], PATCH_PACKAGE_ID)
        self.assertEqual(result["queue_state"], "information_review")
        self.assertEqual([call.get_method() for call in calls], ["GET", "POST"])

    def test_completion_rejects_subject_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response = Path(tmp) / "response.json"
            response.write_text(
                json.dumps(
                    {
                        "schema": information_completion.COMPLETION_SCHEMA,
                        "request_id": REQUEST_ID,
                        "statement": "补充边界",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            responses = [
                (detail_payload(), {"request_id": "lookup-request"}),
                (
                    {
                        "request_id": REQUEST_ID,
                        "patch_package_id": "patch-package-drift",
                        "queue_state": "information_review",
                    },
                    {"request_id": "submit-request"},
                ),
            ]
            with patch.object(information_completion, "request_json_with_metadata", side_effect=responses):
                with self.assertRaises(SystemExit) as raised:
                    information_completion.complete_information_request(config(), response)
        self.assertIn("patch_package_identity_mismatch", str(raised.exception))

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

    def test_patch_upload_response_requires_business_subject_identity(self) -> None:
        payload = {"package": {"patch_package_id": PATCH_PACKAGE_ID, "package_key": SOURCE_PACKAGE_KEY}}
        self.assertEqual(incoming_contract.patch_package_id_from_upload_response(payload), PATCH_PACKAGE_ID)
        with self.assertRaises(RuntimeError):
            incoming_contract.patch_package_id_from_upload_response(
                {"package": {"package_key": SOURCE_PACKAGE_KEY}}
            )
        with self.assertRaises(RuntimeError):
            incoming_contract.patch_package_id_from_upload_response(
                {"package": {"patch_package_id": PATCH_PACKAGE_ID}}
            )
        with self.assertRaises(RuntimeError):
            incoming_contract.patch_package_id_from_upload_response(
                {"package": {"patch_package_id": PATCH_PACKAGE_ID, "package_key": PATCH_PACKAGE_ID}}
            )


if __name__ == "__main__":
    unittest.main()
