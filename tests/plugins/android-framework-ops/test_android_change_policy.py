from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "plugins/android-framework-ops"
PLUGIN_LIB = PLUGIN_ROOT / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from android_engineering_ops.policy.patch_markers import (
    POLICY_ID,
    POLICY_VERSION,
    analyze_patch_markers,
    closing_marker,
    load_policy,
    opening_marker,
)
from android_engineering_ops.member.profile import MemberProfileError, load_member_profile
from android_framework_ops.patch_analysis import facts_from_diff


def test_policy_contract_is_the_canonical_three_layer_source() -> None:
    policy = load_policy()
    assert policy["authority"] == "canonical"
    assert policy["policy_id"] == POLICY_ID
    assert policy["version"] == POLICY_VERSION
    assert policy["attribution"]["identity_field"] == "member_alias"
    assert policy["attribution"]["identity_source"] == "current_member_profile"
    assert policy["attribution"]["free_form_identity_override"] == "forbidden"
    assert policy["attribution"]["generation_owner"] == "codex"
    assert policy["attribution"]["direct_marker_applicability"] == (
        "files_where_slash_line_comments_are_syntactically_valid"
    )
    assert policy["profiles"]["universal_patch_archive"]["mandatory"] is True
    assert policy["profiles"]["framework"]["mandatory_when_domain_is_framework"] is True
    assert policy["profiles"]["legacy_jinny_style"]["mandatory"] is False


def test_change_domain_contract_keeps_non_framework_submission_capability_gated() -> None:
    contract = json.loads(
        (PLUGIN_ROOT / "contracts/change-domain/v1/domain-profiles.json").read_text(encoding="utf-8")
    )
    assert contract["selection_semantics"] == "primary_ownership_build_and_verification_surface"
    assert contract["weak_title_or_filename_inference_forbidden"] is True
    assert set(contract["domains"]) == {
        "framework",
        "system_app",
        "app",
        "hal",
        "native",
        "vendor",
        "kernel",
        "driver",
        "device",
        "build",
    }
    assert contract["domains"]["framework"]["production_submission"] == "incoming_v1_framework_change"
    assert all(
        profile["production_submission"] == "capability_gated"
        for name, profile in contract["domains"].items()
        if name != "framework"
    )


def test_marker_format_uses_member_alias_and_real_calendar_date() -> None:
    assert opening_marker("member01", dt.date(2026, 8, 28)) == "//member01 20260828@{"
    assert closing_marker("member01", "20260828") == "//member01 20260828@}"
    with pytest.raises(ValueError, match="real calendar date"):
        opening_marker("member01", "20260230")
    with pytest.raises(ValueError, match="member_alias"):
        opening_marker("not a profile", "20260828")


def test_new_codex_change_requires_matching_paired_markers() -> None:
    source = "\n".join(
        (
            "//member01 20260828@{",
            "customLogic();",
            "//member01 20260828@}",
        )
    )
    analysis = analyze_patch_markers(
        source,
        expected_alias="member01",
        require_pairs=True,
    )
    assert analysis.valid
    assert analysis.aliases == ("member01",)
    assert analysis.dates == ("20260828",)


def test_wrong_profile_alias_and_unpaired_markers_fail_closed() -> None:
    wrong_alias = analyze_patch_markers(
        "//someone_else 20260828@{\ncustomLogic();\n//someone_else 20260828@}",
        expected_alias="member01",
        require_pairs=True,
    )
    assert not wrong_alias.valid
    assert any("current member_alias" in error for error in wrong_alias.errors)

    legacy = analyze_patch_markers(
        "//legacy_author 20251016@ historical change",
        require_pairs=True,
    )
    assert legacy.has_legacy_marker
    assert any("require paired" in error for error in legacy.errors)


def test_historical_marker_can_be_observed_without_rewriting_authorship() -> None:
    historical = analyze_patch_markers(
        "//legacy_author 20251016@ historical change",
        require_pairs=False,
    )
    assert historical.valid
    assert historical.aliases == ("legacy_author",)


def test_unbalanced_or_impossible_marker_pairs_are_rejected() -> None:
    mismatched = analyze_patch_markers(
        "//member01 20260828@{\ncustomLogic();\n//member02 20260828@}",
        require_pairs=True,
    )
    assert any("does not match opening marker" in error for error in mismatched.errors)

    impossible_date = analyze_patch_markers(
        "//member01 20260230@{\ncustomLogic();\n//member01 20260230@}",
        require_pairs=True,
    )
    assert any("not a real yyyyMMdd date" in error for error in impossible_date.errors)


def test_member_profile_is_the_only_policy_identity_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "android-knowledge-intake.toml").write_text(
        "default_profile = \"member01\"\n\n"
        "[profiles.member01]\n"
        "member_alias = \"member01\"\n"
        "member_name = \"Member 01\"\n"
        "timezone = \"Asia/Shanghai\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_REPORT_ALIAS", "someone_else")
    monkeypatch.setenv("CODEX_REPORT_MEMBER_ALIAS", "someone_else")
    monkeypatch.chdir(tmp_path)
    profile = load_member_profile("member01")
    assert profile.profile == "member01"
    assert profile.member_alias == "member01"
    assert profile.timezone == "Asia/Shanghai"

    with pytest.raises(MemberProfileError, match="does not exist"):
        load_member_profile("invented")


def test_member_profile_rejects_an_unsafe_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "android-knowledge-intake.toml").write_text(
        "default_profile = \"unsafe\"\n\n"
        "[profiles.unsafe]\n"
        "member_alias = \"not a comment-safe alias\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(MemberProfileError, match="unsafe member_alias"):
        load_member_profile("unsafe")


def test_patch_analysis_ignores_markers_outside_added_lines() -> None:
    removed_only = "\n".join(
        (
            "diff --git a/X.java b/X.java",
            "--- a/X.java",
            "+++ b/X.java",
            "@@ -1,2 +1,2 @@",
            "-//legacy_author 20251016@ historical marker",
            "+customLogic();",
        )
    )
    assert facts_from_diff(removed_only)["author_date_marker_present"] is False

    added = removed_only + "\n+//member01 20260828@ current marker"
    assert facts_from_diff(added)["author_date_marker_present"] is True
