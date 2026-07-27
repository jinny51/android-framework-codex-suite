from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "android-framework-ops"
CONTRACT_PATH = (
    PLUGIN_ROOT
    / "skills"
    / "android-knowledge-intake"
    / "references"
    / "verification-acceptance-v2.json"
)
LIB_ROOT = PLUGIN_ROOT / "lib"
if str(LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(LIB_ROOT))

from android_framework_ops.verification_evidence import (  # noqa: E402
    has_authoritative_requirement_result,
    load_verification_contract,
)


def test_versioned_contract_drives_every_conformance_case() -> None:
    contract = load_verification_contract()

    assert CONTRACT_PATH.is_file()
    assert contract == json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["schema"] == "akbs-verification-acceptance-contract-v2"
    assert contract["evidence_contract_version"] == "akbs-verification-evidence/v2"

    cases = {case["id"]: case for case in contract["conformance_cases"]}
    assert {
        "legacy_unscoped_pass",
        "build_delivery_unverified_pass",
        "incomplete_feature_accepted_pass",
        "complete_feature_device_accepted_pass",
        "complete_feature_equivalent_accepted_pass",
    } <= set(cases)

    for case in cases.values():
        expected = case["expected_authoritative_result"]
        payload = case["payload"]
        assert has_authoritative_requirement_result(
            payload,
            expected_result=expected or None,
        ) is bool(expected), case["id"]

