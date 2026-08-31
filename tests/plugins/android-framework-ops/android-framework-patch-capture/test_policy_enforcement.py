from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT = REPO_ROOT / "plugins/android-framework-ops"
PLUGIN_LIB = PLUGIN_ROOT / "lib"
CAPTURE_SCRIPT = (
    PLUGIN_ROOT
    / "skills/android-framework-patch-capture/scripts/capture_framework_patch.py"
)
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))


def load_capture_module():
    spec = importlib.util.spec_from_file_location(
        "capture_framework_patch_policy_test", CAPTURE_SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def diff_with(*added: str, removed: tuple[str, ...] = ()) -> str:
    lines = [
        "diff --git a/X.java b/X.java",
        "--- a/X.java",
        "+++ b/X.java",
        "@@ -1 +1 @@",
    ]
    lines.extend(f"-{line}" for line in removed)
    lines.extend(f"+{line}" for line in added)
    return "\n".join(lines) + "\n"


def capture_for(module, diff_text: str):
    return module.RepositoryCapture(
        source_root="/source",
        repo_path="frameworks/base",
        git_info={},
        diff_text=diff_text,
        facts=module.facts_from_diff(diff_text),
        module="frameworks-base",
        patch_name="rk14-frameworks-base@policy.patch",
        patch_rel="patches/rk14-frameworks-base@policy.patch",
    )


def arguments(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "workflow_contract": "current_codex_skill",
        "implementation_origin": "codex",
        "policy_member_alias": "member01",
        "policy_profile_name": "member01",
        "change_domain": "framework",
        "allow_missing_author_date": False,
        "allow_banned_logs": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_current_codex_capture_records_versioned_matching_policy_evidence() -> None:
    module = load_capture_module()
    patch = diff_with(
        "//member01 20260828@{",
        "customLogic();",
        "//member01 20260828@}",
    )
    result = module.coding_standard_check(arguments(), [capture_for(module, patch)])
    assert result["result"] == "PASS"
    assert result["policy_id"] == "android-change-policy"
    assert result["policy_version"] == "1.0.0"
    assert result["member_profile"] == "member01"
    repository = result["repositories"][0]
    assert repository["marker_contract"] == "paired-current"
    assert repository["marker_pair_count"] == 1
    assert repository["marker_aliases"] == ["member01"]


def test_current_codex_capture_rejects_legacy_wrong_or_removed_only_markers() -> None:
    module = load_capture_module()
    cases = (
        diff_with("//member01 20260828@ legacy marker", "customLogic();"),
        diff_with(
            "//someone_else 20260828@{",
            "customLogic();",
            "//someone_else 20260828@}",
        ),
        diff_with("customLogic();", removed=("//member01 20260828@ historical",)),
    )
    for patch in cases:
        result = module.coding_standard_check(arguments(), [capture_for(module, patch)])
        assert result["result"] == "FAIL"
        assert result["repositories"][0]["marker_errors"]


def test_historical_import_keeps_original_legacy_author() -> None:
    module = load_capture_module()
    patch = diff_with("//legacy_author 20251016@ historical change")
    result = module.coding_standard_check(
        arguments(
            workflow_contract="historical_import",
            implementation_origin="historical",
            policy_member_alias="",
            policy_profile_name="",
        ),
        [capture_for(module, patch)],
    )
    assert result["result"] == "PASS"
    repository = result["repositories"][0]
    assert repository["marker_contract"] == "legacy-compatible"
    assert repository["marker_aliases"] == ["legacy_author"]


def test_each_slash_comment_file_requires_its_own_marker() -> None:
    module = load_capture_module()
    patch = diff_with(
        "//member01 20260828@{",
        "firstChange();",
        "//member01 20260828@}",
    ) + "\n".join(
        (
            "diff --git a/Y.cpp b/Y.cpp",
            "--- a/Y.cpp",
            "+++ b/Y.cpp",
            "@@ -1 +1 @@",
            "+secondChange();",
            "",
        )
    )
    result = module.coding_standard_check(arguments(), [capture_for(module, patch)])
    assert result["result"] == "FAIL"
    repository = result["repositories"][0]
    assert len(repository["marker_files"]) == 2
    assert any("Y.cpp" in error for error in repository["marker_errors"])


def test_file_without_slash_comment_syntax_is_not_broken_by_policy() -> None:
    module = load_capture_module()
    patch = "\n".join(
        (
            "diff --git a/res/values/strings.xml b/res/values/strings.xml",
            "--- a/res/values/strings.xml",
            "+++ b/res/values/strings.xml",
            "@@ -1 +1 @@",
            "+<string name=\"policy\">Policy</string>",
            "",
        )
    )
    result = module.coding_standard_check(arguments(), [capture_for(module, patch)])
    assert result["result"] == "PASS"
    marker_file = result["repositories"][0]["marker_files"][0]
    assert marker_file["result"] == "NOT_APPLICABLE"
    assert marker_file["comment_adapter"] == "NOT_APPLICABLE_NO_ADAPTER"


def test_mixed_change_accepts_historical_marker_and_requires_current_pair() -> None:
    module = load_capture_module()
    patch = diff_with(
        "//legacy_author 20251016@ historical line",
        "//member01 20260828@{",
        "currentChange();",
        "//member01 20260828@}",
    )
    result = module.coding_standard_check(
        arguments(implementation_origin="mixed"),
        [capture_for(module, patch)],
    )
    assert result["result"] == "PASS"
    assert result["repositories"][0]["marker_aliases"] == [
        "legacy_author",
        "member01",
    ]


def test_missing_marker_exception_is_warn_only_for_legacy_import_draft() -> None:
    module = load_capture_module()
    result = module.coding_standard_check(
        arguments(
            workflow_contract="historical_import",
            implementation_origin="historical",
            policy_member_alias="",
            policy_profile_name="",
            allow_missing_author_date=True,
        ),
        [capture_for(module, diff_with("historicalChange();"))],
    )
    assert result["result"] == "WARN"
    repository = result["repositories"][0]
    assert repository["marker_exception"] == "missing_marker_import_draft"
    assert repository["marker_files"][0]["result"] == "WARN"
