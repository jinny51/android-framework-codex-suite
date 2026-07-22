from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
INTAKE_SCRIPTS = (
    REPO_ROOT
    / "plugins"
    / "android-framework-ops"
    / "skills"
    / "android-knowledge-intake"
    / "scripts"
)
if str(INTAKE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(INTAKE_SCRIPTS))

from akbs_intake import config as config_module
from akbs_intake.doctor import latest_pending
from akbs_intake.search_usage import load_search_usage_records


DIAGNOSTIC_PREFIX = "AKBS_LOCAL_INPUT_DIAGNOSTIC "


def diagnostics(stderr: str) -> list[dict[str, str]]:
    lines = [line for line in stderr.splitlines() if line]
    assert all(line.startswith(DIAGNOSTIC_PREFIX) for line in lines)
    payloads = [json.loads(line.removeprefix(DIAGNOSTIC_PREFIX)) for line in lines]
    assert all(set(payload) == {"code", "level", "path"} for payload in payloads)
    assert all(payload["level"] == "warning" for payload in payloads)
    return payloads


def write_search_record(path: Path, **overrides: object) -> None:
    payload: dict[str, object] = {
        "schema": "android-knowledge-search-usage",
        "date": "2026-07-22",
        "member_alias": "member01",
        "created_at": "2026-07-22T09:00:00+08:00",
        "query": "display policy",
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_search_usage_keeps_valid_records_without_diagnostics(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    record_dir = tmp_path / "search-usage" / "20260722"
    record_dir.mkdir(parents=True)
    record_path = record_dir / "valid.json"
    write_search_record(record_path)

    records = load_search_usage_records(
        {"out_dir": str(tmp_path), "member_alias": "member01"},
        dt.date(2026, 7, 22),
    )

    assert [record["query"] for record in records] == ["display policy"]
    assert records[0]["_record_path"] == str(record_path)
    assert capsys.readouterr().err == ""


def test_search_usage_reports_damaged_records_and_continues(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    record_dir = tmp_path / "search-usage" / "20260722"
    record_dir.mkdir(parents=True)
    invalid_json = record_dir / "invalid-json.json"
    invalid_json.write_text('{"token":"do-not-leak"', encoding="utf-8")
    invalid_object = record_dir / "invalid-object.json"
    invalid_object.write_text("[]", encoding="utf-8")
    unsupported_schema = record_dir / "unsupported-schema.json"
    write_search_record(unsupported_schema, schema="unknown-schema")
    valid = record_dir / "valid.json"
    write_search_record(valid)

    records = load_search_usage_records(
        {"out_dir": str(tmp_path), "member_alias": "member01"},
        dt.date(2026, 7, 22),
    )
    stderr = capsys.readouterr().err

    assert [record["_record_path"] for record in records] == [str(valid)]
    assert [item["code"] for item in diagnostics(stderr)] == [
        "search_usage_invalid_json",
        "search_usage_invalid_object",
        "search_usage_unsupported_schema",
    ]
    assert [item["path"] for item in diagnostics(stderr)] == [
        str(invalid_json),
        str(invalid_object),
        str(unsupported_schema),
    ]
    assert "do-not-leak" not in stderr


def test_search_usage_expected_filters_remain_silent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    record_dir = tmp_path / "search-usage" / "20260722"
    record_dir.mkdir(parents=True)
    write_search_record(record_dir / "other-member.json", member_alias="member02")
    write_search_record(record_dir / "other-date.json", date="2026-07-21")

    assert load_search_usage_records(
        {"out_dir": str(tmp_path), "member_alias": "member01"},
        dt.date(2026, 7, 22),
    ) == []
    assert capsys.readouterr().err == ""


def write_manifest(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_latest_pending_reports_damaged_manifests_and_uses_valid_candidate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pending = tmp_path / "pending" / "20260722" / "member01"
    invalid_json = pending / "000-invalid-json" / "manifest.json"
    invalid_json.parent.mkdir(parents=True)
    invalid_json.write_text('{"secret":"do-not-leak"', encoding="utf-8")
    invalid_object = pending / "001-invalid-object" / "manifest.json"
    write_manifest(invalid_object, [])
    valid = pending / "002-valid" / "manifest.json"
    write_manifest(
        valid,
        {
            "package_kind": "daily_trace",
            "member_alias": "member01",
            "date": "2026-07-22",
        },
    )

    selected = latest_pending(
        "daily",
        {"out_dir": str(tmp_path), "member_alias": "member01"},
        dt.date(2026, 7, 22),
    )
    stderr = capsys.readouterr().err

    assert selected == valid.parent
    assert [item["code"] for item in diagnostics(stderr)] == [
        "pending_manifest_invalid_json",
        "pending_manifest_invalid_object",
    ]
    assert [item["path"] for item in diagnostics(stderr)] == [str(invalid_json), str(invalid_object)]
    assert "do-not-leak" not in stderr


def test_latest_pending_preserves_missing_package_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    invalid = tmp_path / "pending" / "20260722" / "member01" / "invalid" / "manifest.json"
    invalid.parent.mkdir(parents=True)
    invalid.write_text("not-json", encoding="utf-8")

    with pytest.raises(SystemExit, match="没有找到 daily pending 工作包"):
        latest_pending("daily", {"out_dir": str(tmp_path), "member_alias": "member01"})

    assert diagnostics(capsys.readouterr().err) == [
        {"code": "pending_manifest_invalid_json", "level": "warning", "path": str(invalid)}
    ]


@pytest.mark.skipif(config_module.ZoneInfo is None, reason="zoneinfo unavailable")
def test_local_now_uses_configured_timezone_without_diagnostics(capsys: pytest.CaptureFixture[str]) -> None:
    value = config_module.local_now({"timezone": "UTC"})

    assert getattr(value.tzinfo, "key", None) == "UTC"
    assert capsys.readouterr().err == ""


@pytest.mark.skipif(config_module.ZoneInfo is None, reason="zoneinfo unavailable")
def test_local_now_reports_invalid_timezone_and_uses_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = config_module.local_now({"timezone": "Invalid/Do-Not-Leak"})
    stderr = capsys.readouterr().err

    assert getattr(value.tzinfo, "key", None) == "Asia/Shanghai"
    assert diagnostics(stderr) == [
        {"code": "timezone_invalid", "level": "warning", "path": "config.timezone"}
    ]
    assert "Invalid/Do-Not-Leak" not in stderr
