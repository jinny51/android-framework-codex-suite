from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = (
    REPO_ROOT
    / "plugins/android-framework-ops/skills/android-member-setup/"
    "scripts/android_member_setup.py"
)


def load_entrypoint():
    spec = importlib.util.spec_from_file_location("android_member_setup", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_member_setup_maps_strict_doctor_to_legacy_kernel() -> None:
    module = load_entrypoint()
    with patch.object(module, "legacy_intake_main", return_value=0) as legacy:
        result = module.main(
            ["doctor", "--profile", "member01", "--strict", "--check-remote"]
        )
    assert result == 0
    legacy.assert_called_once_with(
        ["--profile", "member01", "doctor", "--strict", "--check-remote"]
    )


def test_member_setup_prints_the_canonical_legacy_prompt(capsys) -> None:
    module = load_entrypoint()
    result = module.main(["print-setup-prompt"])
    output = capsys.readouterr().out
    assert result == 0
    assert "成员首次启用提示词" in output
    assert "member_alias" in output
