from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT = REPO_ROOT / "plugins/android-framework-ops"
PLUGIN_LIB = PLUGIN_ROOT / "lib"
INTAKE_SCRIPTS = PLUGIN_ROOT / "skills/android-knowledge-intake/scripts"

for path in (PLUGIN_LIB, INTAKE_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def test_legacy_and_neutral_imports_share_one_module_object() -> None:
    legacy = importlib.import_module("akbs_intake.incoming_contract")
    neutral = importlib.import_module("android_engineering_ops.incoming_v1.contract")

    assert legacy is neutral
    assert legacy.PUBLIC_CONTRACT_PATH == (
        PLUGIN_ROOT
        / "skills/android-knowledge-intake/references/incoming-public-contract-v1.json"
    )
    assert legacy.public_contract() == neutral.public_contract()


def test_legacy_monkeypatch_changes_canonical_contract_module(tmp_path: Path) -> None:
    legacy = importlib.import_module("akbs_intake.incoming_contract")
    neutral = importlib.import_module("android_engineering_ops.incoming_v1.contract")
    missing = tmp_path / "missing-public-contract.json"

    neutral.public_contract.cache_clear()
    try:
        with patch.object(legacy, "PUBLIC_CONTRACT_PATH", missing):
            assert neutral.PUBLIC_CONTRACT_PATH == missing
            try:
                neutral.public_contract()
            except FileNotFoundError:
                pass
            else:  # pragma: no cover - explicit compatibility failure
                raise AssertionError("legacy monkeypatch did not reach canonical module")
    finally:
        neutral.public_contract.cache_clear()
