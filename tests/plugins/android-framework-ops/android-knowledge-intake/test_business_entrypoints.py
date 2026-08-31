from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT = REPO_ROOT / "plugins/android-framework-ops"
PLUGIN_LIB = PLUGIN_ROOT / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from android_engineering_ops.incoming_v1.cli import route_arguments


ENTRYPOINTS = {
    "daily": PLUGIN_ROOT
    / "skills/android-daily-report-intake/scripts/android_daily_report_intake.py",
    "weekly": PLUGIN_ROOT
    / "skills/android-weekly-report-intake/scripts/android_weekly_report_intake.py",
    "patch": PLUGIN_ROOT
    / "skills/android-framework-patch-intake/scripts/android_framework_patch_intake.py",
}


def load_entrypoint(mode: str):
    spec = importlib.util.spec_from_file_location(f"android_{mode}_entrypoint", ENTRYPOINTS[mode])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_route_arguments_places_profile_before_legacy_mode() -> None:
    assert route_arguments("daily", ["--prepare", "--profile", "member01"]) == [
        "--profile",
        "member01",
        "daily",
        "--prepare",
    ]
    assert route_arguments("weekly", ["--profile=member02", "--submit-latest"]) == [
        "--profile",
        "member02",
        "weekly",
        "--submit-latest",
    ]


def test_each_business_entrypoint_routes_to_one_legacy_mode() -> None:
    for mode in ("daily", "weekly", "patch"):
        module = load_entrypoint(mode)
        with patch.object(module, "legacy_intake_main", return_value=0) as legacy:
            result = module.main(["--profile", "member01", "--validate", "/tmp/package"])
        assert result == 0
        legacy.assert_called_once_with(
            ["--profile", "member01", mode, "--validate", "/tmp/package"]
        )


def test_route_arguments_rejects_missing_profile_value() -> None:
    try:
        route_arguments("patch", ["--profile"])
    except SystemExit as error:
        assert "requires a value" in str(error)
    else:  # pragma: no cover - explicit compatibility failure
        raise AssertionError("missing profile value was accepted")
