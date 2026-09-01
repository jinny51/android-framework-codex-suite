from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/validate_active_plugin_topology.py"
CONTRACT = ROOT / "contracts/plugin-topology/v1/active-topology.json"


def test_functional_split_contract_is_active() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["state"] == "active"
    assert contract["canonical_core"] == "android-framework-ops"
    assert contract["implementation_owners"]["android-source-access"] == (
        "android-framework-ops:internal"
    )
    assert contract["public_entries"]["android-source-access"] == {
        "wsl": "android-wsl-ops",
        "macos": "android-mac-ops",
    }
    assert [row["id"] for row in contract["plugins"]] == [
        "android-framework-ops",
        "android-wsl-ops",
        "android-mac-ops",
        "jinny-android-practices",
        "codex-workspace-care",
    ]


def test_active_topology_validator_passes_the_repository() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "Active plugin topology validation passed" in result.stdout
