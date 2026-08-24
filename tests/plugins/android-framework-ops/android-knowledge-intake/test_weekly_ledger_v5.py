from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "android-framework-ops"
for path in (
    PLUGIN_ROOT / "lib",
    PLUGIN_ROOT / "skills" / "android-knowledge-intake" / "scripts",
):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from akbs_intake.reports import render
from akbs_intake.reports import validation
from akbs_intake.reports import weekly_facts as weekly


ZERO_PATCH = {"demand": 0, "migration": 0, "bug": 0}


def patch_counts(*, demand: int = 0, migration: int = 0, bug: int = 0) -> dict[str, int]:
    return {"demand": demand, "migration": migration, "bug": bug}


def changes(**overrides: dict[str, int]) -> dict[str, dict[str, int]]:
    result = {key: dict(ZERO_PATCH) for key in weekly.LEDGER_CHANGE_KEYS}
    result.update(overrides)
    return result


def main_patch(
    *,
    total: dict[str, int],
    completed: dict[str, int],
    remaining: dict[str, int],
    ledger: dict,
    project: str = "TVE8802M",
) -> dict:
    return {
        "project": project,
        "customer": "韩富友",
        "work_type": "Patch",
        "project_role": "主责",
        "week_summary": "本周推进项目问题收敛。",
        "requirement_date": "2026-08-20",
        "requirement_source": "TE",
        "requirement_structure": total,
        "completed_this_week": completed,
        "remaining": remaining,
        "completed_items": ["完成问题处理"] if sum(completed.values()) else [],
        "remaining_items": ["继续处理剩余问题"] if sum(remaining.values()) else [],
        "key_points": ["无"],
        "risks": [],
        "dependencies": [],
        "next_week_plan": ["继续处理剩余问题"] if sum(remaining.values()) else [],
        "ledger": ledger,
    }


def ledger(
    *,
    opening: bool,
    baseline_package_key: str = "",
    baseline_week_range: str = "",
    project_completed: dict[str, int] | None = None,
    change_counts: dict[str, dict[str, int]] | None = None,
    bsp_pending: dict[str, int] | None = None,
) -> dict:
    return {
        "schema": weekly.WEEKLY_LEDGER_SCHEMA,
        "opening": opening,
        "baseline_package_key": baseline_package_key,
        "baseline_week_range": baseline_week_range,
        "project_completed": project_completed or dict(ZERO_PATCH),
        "changes": change_counts or changes(),
        "bsp_pending": bsp_pending or dict(ZERO_PATCH),
    }


def write_facts(path: Path, project: dict, *, schema: str = weekly.WEEKLY_FACTS_SCHEMA) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": schema,
                "week_range": "20260817-20260823",
                "projects": [project],
                "documents": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def previous_scope(
    *,
    total: dict[str, int],
    remaining: dict[str, int],
    project: str = "TVE8802M",
    work_type: str = "Patch",
    app_name: str = "",
    work_total: int = 0,
    app_remaining: int = 0,
) -> dict[str, list[dict]]:
    raw = {
        "project": project,
        "customer": "韩富友",
        "work_type": work_type,
        "app_name": app_name,
        "project_role": "主责",
        "requirement_date": "2026-08-01",
        "requirement_source": "TE",
        "requirement_structure": total,
        "work_total": work_total,
        "completed_this_week": 0 if work_type == "App" else dict(ZERO_PATCH),
        "remaining": app_remaining if work_type == "App" else remaining,
        "completed_items": [],
        "remaining_items": ["上周剩余事项"] if (app_remaining or sum(remaining.values())) else [],
        "key_points": ["无"],
        "risks": [],
        "dependencies": [],
        "next_week_plan": [],
    }
    row = weekly._weekly_project_row(raw)
    row["_package_key"] = "20260816/member/current"
    row["_week_range"] = "20260810-20260816"
    return {project: [row]}


def test_new_main_separates_bsp_ownership_from_bug_type(tmp_path: Path) -> None:
    project = main_patch(
        total=patch_counts(bug=3),
        completed=dict(ZERO_PATCH),
        remaining=patch_counts(bug=2),
        ledger=ledger(
            opening=True,
            change_counts=changes(transferred_to_bsp=patch_counts(bug=1)),
            bsp_pending=patch_counts(bug=1),
        ),
    )
    rows = weekly.load_explicit_facts(write_facts(tmp_path / "facts.json", project), "20260817-20260823")

    row = rows[0]
    assert row["requirement_structure_counts"]["bsp"] == 0
    assert row["remaining_counts"]["bsp"] == 0
    assert row["ledger"]["bsp_pending"] == patch_counts(bug=1)
    assert render.weekly_ledger_change_text(row) == "新项目建账、转 BSP 1 项（Bug 1）"
    assert render.weekly_bsp_pending_text(row) == "BSP 跟踪 1 项（Bug 1）"

    view = render.report_view_payload(
        "weekly",
        dt.date(2026, 8, 23),
        "20260817-20260823",
        {"member_alias": "member01", "member_name": "成员甲"},
        {},
        [],
        "",
        weekly_projects=rows,
    )["payload"]
    markdown = render.report_markdown_from_view(view)
    project_view = view["projects"][0]
    assert "- 本周变化：新项目建账、转 BSP 1 项（Bug 1）" in markdown
    assert "- BSP 跟踪 1 项（Bug 1）" in markdown
    assert project_view["ledger"]["schema"] == weekly.WEEKLY_LEDGER_SCHEMA
    assert project_view["project_change"] == "新项目建账、转 BSP 1 项（Bug 1）"
    assert project_view["bsp_pending"] == "BSP 跟踪 1 项（Bug 1）"
    errors: list[str] = []
    validation.validate_weekly_report_view_project("report_view.json", 0, project_view, errors)
    assert errors == []


def test_existing_main_must_bind_baseline_and_preserve_cumulative_total(tmp_path: Path) -> None:
    previous = previous_scope(total=patch_counts(demand=9, bug=10), remaining=patch_counts(demand=1))
    project = main_patch(
        total=patch_counts(bug=2),
        completed=patch_counts(demand=1, bug=2),
        remaining=dict(ZERO_PATCH),
        ledger=ledger(
            opening=False,
            baseline_package_key="20260816/member/current",
            baseline_week_range="20260810-20260816",
            project_completed=patch_counts(demand=1, bug=2),
        ),
    )

    with pytest.raises(SystemExit, match="requirement_structure 与上周总量和主责本周变化不一致"):
        weekly.load_explicit_facts(
            write_facts(tmp_path / "facts.json", project),
            "20260817-20260823",
            previous_projects=previous,
        )


def test_existing_main_change_formula_blocks_unexplained_remaining_gap(tmp_path: Path) -> None:
    previous = previous_scope(total=patch_counts(bug=10), remaining=patch_counts(bug=5))
    change_counts = changes(
        added=patch_counts(bug=3),
        closed_without_change=patch_counts(bug=1),
    )
    project = main_patch(
        total=patch_counts(bug=13),
        completed=patch_counts(bug=2),
        remaining=patch_counts(bug=4),
        ledger=ledger(
            opening=False,
            baseline_package_key="20260816/member/current",
            baseline_week_range="20260810-20260816",
            project_completed=patch_counts(bug=2),
            change_counts=change_counts,
        ),
    )

    with pytest.raises(SystemExit, match="remaining 与上周剩余和本周流转不一致"):
        weekly.load_explicit_facts(
            write_facts(tmp_path / "facts.json", project),
            "20260817-20260823",
            previous_projects=previous,
        )

    project["remaining"] = patch_counts(bug=5)
    rows = weekly.load_explicit_facts(
        write_facts(tmp_path / "facts.json", project),
        "20260817-20260823",
        previous_projects=previous,
    )
    assert rows[0]["remaining_total"] == 5


def test_main_confirms_project_completion_including_collaborators(tmp_path: Path) -> None:
    previous = previous_scope(total=patch_counts(bug=19), remaining=patch_counts(bug=1))
    project = main_patch(
        total=patch_counts(bug=31),
        completed=patch_counts(bug=2),
        remaining=dict(ZERO_PATCH),
        ledger=ledger(
            opening=False,
            baseline_package_key="20260816/member/current",
            baseline_week_range="20260810-20260816",
            project_completed=patch_counts(bug=13),
            change_counts=changes(added=patch_counts(bug=12)),
        ),
    )

    rows = weekly.load_explicit_facts(
        write_facts(tmp_path / "facts.json", project),
        "20260817-20260823",
        previous_projects=previous,
    )

    assert rows[0]["completed_this_week_counts"]["bug"] == 2
    assert rows[0]["ledger"]["project_completed"]["bug"] == 13
    assert rows[0]["ledger"]["baseline"]["android_remaining"]["bug"] == 1
    assert rows[0]["remaining_total"] == 0


def test_app_rework_must_be_declared_as_reopened(tmp_path: Path) -> None:
    previous = previous_scope(
        total=dict(ZERO_PATCH),
        remaining=dict(ZERO_PATCH),
        project="TVA10A2R",
        work_type="App",
        app_name="Updater",
        work_total=19,
        app_remaining=1,
    )
    project = {
        "project": "TVA10A2R",
        "customer": "韩富友",
        "work_type": "App",
        "app_name": "Updater",
        "project_role": "主责",
        "week_summary": "本周完成 OTA 返工。",
        "requirement_date": "2026-07-10",
        "requirement_source": "CR",
        "work_total": 19,
        "completed_this_week": 1,
        "remaining": 1,
        "completed_items": ["完成 OTA 返工"],
        "remaining_items": ["继续处理原剩余问题"],
        "key_points": ["无"],
        "risks": [],
        "dependencies": [],
        "next_week_plan": ["继续处理原剩余问题"],
        "ledger": {
            "schema": weekly.WEEKLY_LEDGER_SCHEMA,
            "opening": False,
            "baseline_package_key": "20260816/member/current",
            "baseline_week_range": "20260810-20260816",
            "project_completed": 1,
            "changes": {key: 0 for key in weekly.LEDGER_CHANGE_KEYS},
            "bsp_pending": 0,
        },
    }

    with pytest.raises(SystemExit, match="remaining 应为 0"):
        weekly.load_explicit_facts(
            write_facts(tmp_path / "facts.json", project),
            "20260817-20260823",
            previous_projects=previous,
        )

    project["ledger"]["changes"]["reopened"] = 1
    rows = weekly.load_explicit_facts(
        write_facts(tmp_path / "facts.json", project),
        "20260817-20260823",
        previous_projects=previous,
    )
    assert rows[0]["work_total"] == 19
    assert rows[0]["remaining_total"] == 1


def test_collaborator_cannot_change_project_ledger(tmp_path: Path) -> None:
    project = main_patch(
        total=patch_counts(bug=1),
        completed=patch_counts(bug=1),
        remaining=dict(ZERO_PATCH),
        ledger=ledger(
            opening=False,
            change_counts=changes(added=patch_counts(bug=1)),
        ),
    )
    project["project_role"] = "协作"
    project.pop("requirement_structure")

    with pytest.raises(SystemExit, match="只有主责可以新建项目或修改项目总量和流转"):
        weekly.load_explicit_facts(write_facts(tmp_path / "facts.json", project), "20260817-20260823")


def test_legacy_explicit_facts_cannot_override_existing_scope(tmp_path: Path) -> None:
    previous = previous_scope(total=patch_counts(bug=3), remaining=patch_counts(bug=1))
    project = main_patch(
        total=patch_counts(bug=2),
        completed=patch_counts(bug=2),
        remaining=dict(ZERO_PATCH),
        ledger={},
    )
    project.pop("ledger")

    with pytest.raises(SystemExit, match="旧显式事实不得绕过上周基线"):
        weekly.load_explicit_facts(
            write_facts(
                tmp_path / "facts.json",
                project,
                schema=weekly.PREVIOUS_WEEKLY_FACTS_SCHEMA,
            ),
            "20260817-20260823",
            previous_projects=previous,
        )


def test_explicit_builder_does_not_bypass_previous_week_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous_project = {
        "project": "TVE8802M",
        "customer": "韩富友",
        "work_type": "Patch",
        "project_role": "主责",
        "requirement_date": "2026-08-01",
        "requirement_source": "TE",
        "requirement_structure": "共 3 项：Bug 3",
        "completed_this_week": "本周完成 2 项：Bug 2",
        "remaining": "当前剩余 1 项：Bug 1",
        "completed_items": ["完成两个问题"],
        "remaining_items": ["上周剩余事项"],
        "key_points": ["无"],
        "risks": [],
        "dependencies": [],
        "next_week_plan": ["完成剩余事项"],
    }
    previous_item = {
        "package_key": "20260816/member/current",
        "package_kind": "weekly_trace",
        "week_range": "20260810-20260816",
        "standard_view": {"projects": [previous_project]},
    }
    provenance = {
        "source": "akbs_api",
        "api_errors": [],
        "daily_package_keys": [],
        "previous_weekly_package_keys": ["20260816/member/current"],
        "previous_week_range": "20260810-20260816",
    }
    monkeypatch.setattr(
        weekly,
        "load_history",
        lambda _config, _start, _end: ([], [previous_item], provenance),
    )
    legacy_project = main_patch(
        total=patch_counts(bug=2),
        completed=patch_counts(bug=2),
        remaining=dict(ZERO_PATCH),
        ledger={},
    )
    legacy_project.pop("ledger")
    facts = write_facts(
        tmp_path / "facts.json",
        legacy_project,
        schema=weekly.PREVIOUS_WEEKLY_FACTS_SCHEMA,
    )

    with pytest.raises(SystemExit, match="旧显式事实不得绕过上周基线"):
        weekly.build_weekly_facts(
            {},
            dt.date(2026, 8, 17),
            dt.date(2026, 8, 23),
            "20260817-20260823",
            explicit_path=str(facts),
        )


def test_v5_builder_binds_effective_previous_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous_project = {
        "project": "TVE8802M",
        "customer": "韩富友",
        "work_type": "Patch",
        "project_role": "主责",
        "requirement_date": "2026-08-01",
        "requirement_source": "TE",
        "requirement_structure": "共 3 项：Bug 3",
        "completed_this_week": "本周完成 2 项：Bug 2",
        "remaining": "当前剩余 1 项：Bug 1",
        "completed_items": ["完成两个问题"],
        "remaining_items": ["上周剩余事项"],
        "key_points": ["无"],
        "risks": [],
        "dependencies": [],
        "next_week_plan": ["完成剩余事项"],
    }
    previous_item = {
        "package_key": "20260816/member/current",
        "package_kind": "weekly_trace",
        "week_range": "20260810-20260816",
        "standard_view": {"projects": [previous_project]},
    }
    provenance = {
        "source": "akbs_api",
        "api_errors": [],
        "daily_package_keys": [],
        "previous_weekly_package_keys": ["20260816/member/current"],
        "previous_week_range": "20260810-20260816",
    }
    monkeypatch.setattr(
        weekly,
        "load_history",
        lambda _config, _start, _end: ([], [previous_item], provenance),
    )
    project = main_patch(
        total=patch_counts(bug=4),
        completed=patch_counts(bug=2),
        remaining=dict(ZERO_PATCH),
        ledger=ledger(
            opening=False,
            baseline_package_key="20260816/member/current",
            baseline_week_range="20260810-20260816",
            project_completed=patch_counts(bug=2),
            change_counts=changes(added=patch_counts(bug=1)),
        ),
    )
    project["completed_items"] = ["完成上周剩余事项", "完成本周新增问题"]
    project["remaining_items"] = []
    project["next_week_plan"] = []
    facts = write_facts(tmp_path / "facts.json", project)

    result = weekly.build_weekly_facts(
        {},
        dt.date(2026, 8, 17),
        dt.date(2026, 8, 23),
        "20260817-20260823",
        explicit_path=str(facts),
    )

    assert result.evidence["source"] == "explicit_weekly_facts"
    assert result.evidence["previous_weekly_package_keys"] == ["20260816/member/current"]
    assert result.projects[0]["requirement_structure_counts"]["bug"] == 4
    assert result.projects[0]["remaining_total"] == 0
