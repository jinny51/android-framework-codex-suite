from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SUITE_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_ROOT = SUITE_ROOT / "contracts" / "incoming" / "v1"
INTAKE_SCRIPTS = (
    SUITE_ROOT
    / "plugins"
    / "android-framework-ops"
    / "skills"
    / "android-knowledge-intake"
    / "scripts"
)
if str(INTAKE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(INTAKE_SCRIPTS))

from akbs_intake.incoming_contract import (  # noqa: E402
    patch_queue_reason_codes,
    patch_queue_states,
    patch_queue_terminal_states,
)
from akbs_intake import incoming_contract  # noqa: E402


class IncomingContractPinTests(unittest.TestCase):
    def test_public_contract_consumer_and_artifacts_match_the_compatibility_pin(self) -> None:
        pin = json.loads((CONTRACT_ROOT / "contract-pin.json").read_text(encoding="utf-8"))
        self.assertEqual(pin["schema_version"], "1")
        self.assertEqual(pin["compatibility"], "strict-content-hash-equality")
        self.assertEqual(
            pin["source_provenance"]["commit"],
            "c13d827d718bd487611bcc59924e58fb094d7944",
        )
        self.assertFalse(pin["source_provenance"]["compatibility_condition"])
        consumer_path = SUITE_ROOT / pin["public_contract"]["consumer_path"]
        consumer = json.loads(consumer_path.read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(consumer_path.read_bytes()).hexdigest(), pin["public_contract"]["sha256"])
        expected_artifacts = {
            consumer["manifest_schema"]["path"]: consumer["manifest_schema"]["sha256"],
            consumer["verification_acceptance"]["path"]: consumer[
                "verification_acceptance"
            ]["sha256"],
            **{
                declaration["path"]: declaration["sha256"]
                for declaration in consumer["golden_fixtures"].values()
            },
        }
        self.assertEqual(pin["artifact_sha256"], expected_artifacts)
        for relative, expected in pin["artifact_sha256"].items():
            path = CONTRACT_ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, relative)
        reason_codes = sorted(
            code
            for codes in consumer["reason_code_families"].values()
            for code in codes
        )
        self.assertEqual(pin["reason_codes"], reason_codes)
        self.assertEqual(len(reason_codes), 96)
        self.assertEqual(pin["success_reason_codes"], consumer["success_reason_codes"])
        evaluator = pin["verification_reference_evaluator"]
        source_evaluator = SUITE_ROOT / evaluator["source_path"]
        self.assertEqual(
            hashlib.sha256(source_evaluator.read_bytes()).hexdigest(),
            evaluator["sha256"],
        )
        completion = consumer["patch_information_completion"]
        self.assertEqual(
            [item["id"] for item in completion["fields"]],
            [
                "project", "projects", "platform", "android_version", "title", "summary",
                "feature_name", "problem", "solution", "result", "risk_or_gap", "code_anchors",
                "verification", "applicability",
            ],
        )
        self.assertEqual(completion["attachment"]["max_file_bytes"], 2 * 1024 * 1024)
        self.assertEqual(completion["attachment"]["max_total_bytes"], 8 * 1024 * 1024)
        self.assertTrue(completion["attachment"]["patch_assets_immutable"])
        patch_contract = consumer["patch_package_contract"]
        self.assertEqual(patch_contract["schema"], "akbs-patch-package-contract/v2")
        self.assertEqual(patch_contract["business_identity"]["visible_package_type"], "patch_package")
        self.assertEqual(patch_contract["business_identity"]["identity_field"], "patch_package_id")
        self.assertEqual(
            patch_contract["business_identity"]["canonical_identity"],
            "patch_packages.patch_package_id",
        )
        self.assertEqual(
            patch_contract["business_identity"]["queue_identity"],
            "patch_packages.patch_package_id",
        )
        self.assertEqual(
            patch_contract["business_identity"]["main_branch_identity"],
            "patch_packages.patch_package_id",
        )
        self.assertEqual(patch_contract["business_identity"]["source_identity_field"], "package_key")
        self.assertEqual(patch_contract["business_identity"]["source_identity_role"], "source_only")
        self.assertTrue(patch_contract["business_identity"]["patch_assets_immutable"])
        self.assertEqual(
            patch_queue_states(),
            ("received", "under_review", "information_required", "information_review", "closed"),
        )
        self.assertEqual(patch_queue_terminal_states(), {"closed"})
        self.assertEqual(patch_contract["queue"]["branch"], "queue")
        self.assertEqual(
            patch_contract["queue"]["admission_target"],
            {"branch": "main", "stage": "under_review"},
        )
        self.assertEqual(patch_contract["curation"]["branch"], "main")
        self.assertEqual(
            patch_contract["curation"]["stages"],
            ["under_review", "pending_merge_confirmation", "dispute_open", "closed"],
        )
        self.assertEqual(
            patch_contract["history"]["retired_business_vocabulary"],
            "history_audit_only",
        )
        self.assertEqual(patch_queue_reason_codes(), set(consumer["reason_code_families"]["patch_queue"]))
        error_contract = SUITE_ROOT / pin["error_envelope"]["consumer_path"]
        self.assertEqual(hashlib.sha256(error_contract.read_bytes()).hexdigest(), pin["error_envelope"]["sha256"])

    def test_duplicate_identity_semantics_are_consumed_from_the_public_contract(self) -> None:
        pin = json.loads((CONTRACT_ROOT / "contract-pin.json").read_text(encoding="utf-8"))
        consumer = json.loads((SUITE_ROOT / pin["public_contract"]["consumer_path"]).read_text(encoding="utf-8"))
        duplicate = consumer["duplicate_package_identity"]
        self.assertEqual(duplicate["same_file_tree_sha256"]["http_status"], 200)
        self.assertEqual(duplicate["same_file_tree_sha256"]["outcome"], "idempotent_replay")
        self.assertFalse(duplicate["same_file_tree_sha256"]["creates_new_fact"])
        self.assertEqual(duplicate["different_file_tree_sha256"]["http_status"], 409)
        self.assertEqual(duplicate["different_file_tree_sha256"]["reason_code"], "package_already_exists")
        self.assertFalse(duplicate["different_file_tree_sha256"]["creates_new_fact"])

    def test_queue_contract_state_or_reason_code_drift_fails_closed(self) -> None:
        source = (
            SUITE_ROOT
            / "plugins"
            / "android-framework-ops"
            / "skills"
            / "android-knowledge-intake"
            / "references"
            / "incoming-public-contract-v1.json"
        )
        baseline = json.loads(source.read_text(encoding="utf-8"))
        mutations = []
        invalid_state = json.loads(json.dumps(baseline))
        invalid_state["patch_package_contract"]["queue"]["states"].append("legacy_supplement_review")
        mutations.append(invalid_state)
        incomplete_codes = json.loads(json.dumps(baseline))
        incomplete_codes["reason_code_families"]["patch_queue"].remove("patch_asset_immutable")
        mutations.append(incomplete_codes)
        extra_transition = json.loads(json.dumps(baseline))
        extra_transition["patch_package_contract"]["queue"]["transitions"].append(
            {
                "from_branch": "queue",
                "from": "under_review",
                "action": "review_restarted",
                "to_branch": "queue",
                "to": "under_review",
            }
        )
        mutations.append(extra_transition)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "public-contract.json"
            for payload in mutations:
                path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                incoming_contract.public_contract.cache_clear()
                with patch.object(incoming_contract, "PUBLIC_CONTRACT_PATH", path):
                    with self.assertRaises(RuntimeError):
                        incoming_contract.public_contract()
        incoming_contract.public_contract.cache_clear()

    def test_three_current_golden_manifests_are_pinned_to_v1(self) -> None:
        expected = {
            "daily": "daily_trace",
            "weekly": "weekly_trace",
            "patch": "framework_change",
        }
        for name, package_kind in expected.items():
            manifest = json.loads((CONTRACT_ROOT / "fixtures" / f"{name}.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "knowledge-incoming-package")
            self.assertEqual(manifest["schema_version"], "1")
            self.assertEqual(manifest["package_kind"], package_kind)
        consumer = json.loads(
            (SUITE_ROOT / "plugins/android-framework-ops/skills/android-knowledge-intake/references/incoming-public-contract-v1.json")
            .read_text(encoding="utf-8")
        )
        self.assertNotIn("retired_routes", consumer)


if __name__ == "__main__":
    unittest.main()
