from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


SUITE_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_ROOT = SUITE_ROOT / "contracts" / "incoming" / "v1"


class IncomingContractPinTests(unittest.TestCase):
    def test_public_contract_consumer_and_artifacts_match_the_compatibility_pin(self) -> None:
        pin = json.loads((CONTRACT_ROOT / "contract-pin.json").read_text(encoding="utf-8"))
        self.assertEqual(pin["schema_version"], "1")
        self.assertEqual(pin["compatibility"], "strict-public-contract-equality")
        self.assertEqual(pin["source_commit"], "340c16d0a738f4029b4ff80c1eed4b8e3a16cf4c")
        consumer_path = SUITE_ROOT / pin["public_contract"]["consumer_path"]
        consumer = json.loads(consumer_path.read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(consumer_path.read_bytes()).hexdigest(), pin["public_contract"]["sha256"])
        expected_artifacts = {
            consumer["manifest_schema"]["path"]: consumer["manifest_schema"]["sha256"],
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
        self.assertEqual(len(reason_codes), 48)
        self.assertEqual(pin["success_reason_codes"], consumer["success_reason_codes"])

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

    def test_four_golden_manifests_are_pinned_to_v1(self) -> None:
        expected = {
            "daily": "daily_trace",
            "weekly": "weekly_trace",
            "patch": "framework_change",
            "supplement": "framework_change",
        }
        for name, package_kind in expected.items():
            manifest = json.loads((CONTRACT_ROOT / "fixtures" / f"{name}.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "knowledge-incoming-package")
            self.assertEqual(manifest["schema_version"], "1")
            self.assertEqual(manifest["package_kind"], package_kind)
        supplement = json.loads((CONTRACT_ROOT / "fixtures" / "supplement.manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(supplement["supplement_for_package_key"])


if __name__ == "__main__":
    unittest.main()
