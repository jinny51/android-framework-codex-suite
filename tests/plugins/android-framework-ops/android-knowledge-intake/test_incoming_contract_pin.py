from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


SUITE_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_ROOT = SUITE_ROOT / "contracts" / "incoming" / "v1"


class IncomingContractPinTests(unittest.TestCase):
    def test_public_v1_artifacts_match_the_compatibility_pin(self) -> None:
        pin = json.loads((CONTRACT_ROOT / "contract-pin.json").read_text(encoding="utf-8"))
        self.assertEqual(pin["schema_version"], "1")
        self.assertEqual(pin["compatibility"], "exact-artifacts-and-reason-codes")
        for relative, expected in pin["artifacts"].items():
            path = CONTRACT_ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, relative)

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
