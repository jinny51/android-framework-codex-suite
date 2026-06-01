from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import android_knowledge_search as search


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


class AndroidKnowledgeSearchCurrentTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        index = root / "index"
        index.mkdir()
        conn = sqlite3.connect(index / "knowledge.sqlite")
        try:
            conn.executescript(
                """
                CREATE TABLE knowledge_events(
                  id TEXT PRIMARY KEY, package_id TEXT, package_kind TEXT, maturity TEXT,
                  member TEXT, date TEXT, project TEXT, platform TEXT, summary TEXT, path TEXT, payload TEXT
                );
                CREATE TABLE evidence(
                  id TEXT, event_id TEXT, kind TEXT, result TEXT, summary TEXT, path TEXT, payload TEXT
                );
                """
            )
            conn.execute(
                """
                INSERT INTO knowledge_events
                (id, package_id, package_kind, maturity, member, date, project, platform, summary, path, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "event-power",
                    "20260526/testuser/20260526-213000-framework-change",
                    "framework_change",
                    "validated",
                    "testuser",
                    "2026-05-26",
                    "TVE8402M",
                    "rk3576",
                    "修改电源键策略以满足产品需求",
                    "knowledge-events/20260526/testuser/event-power/event.json",
                    '{"scope":"services.jar"}',
                ),
            )
            conn.execute(
                """
                INSERT INTO evidence
                (id, event_id, kind, result, summary, path, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "verification-result",
                    "event-power",
                    "verification_result",
                    "PASS",
                    "rk3576 真机验证电源键行为通过",
                    "knowledge-events/20260526/testuser/event-power/evidence/verification-result.json",
                    '{"method":"device","device":"rk3576"}',
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return root

    def test_load_rows_includes_knowledge_events_and_evidence(self):
        root = self.make_root()

        rows = search.load_rows(root)

        kinds = {row["kind"] for row in rows}
        self.assertIn("event", kinds)
        self.assertIn("evidence", kinds)

    def test_search_can_filter_event_and_evidence(self):
        root = self.make_root()
        rows = search.load_rows(root)

        events = search.search(rows, "电源键 rk3576", "event", 5, include_synthetic=False)
        evidence = search.search(rows, "真机验证", "evidence", 5, include_synthetic=False)

        self.assertEqual(events[0]["id"], "event-power")
        self.assertEqual(evidence[0]["id"], "verification-result")

    def test_markdown_formats_event_and_evidence_results(self):
        root = self.make_root()
        rows = search.load_rows(root)
        results = search.search(rows, "电源键 真机验证", "all", 5, include_synthetic=False)

        text = search.format_markdown(root, "电源键 真机验证", results, None)

        self.assertIn("[event]", text)
        self.assertIn("[evidence]", text)

    def test_current_rebuild_case_and_variant_indexes_are_searchable(self):
        root = Path(tempfile.mkdtemp())
        write_jsonl(
            root / "index" / "case-index.jsonl",
            [
                {
                    "case_id": "case-volume-dialog",
                    "title": "通知音量弹窗位置适配",
                    "problem": "通知音量弹窗位置不符合项目要求",
                    "solution_summary": "调整 SystemUI 音量弹窗位置策略",
                    "variant_ids": ["variant-mtk15-tve8402m-volume-dialog"],
                    "source_priority": 100,
                }
            ],
        )
        write_jsonl(
            root / "index" / "variant-index.jsonl",
            [
                {
                    "variant_id": "variant-mtk15-tve8402m-volume-dialog",
                    "case_id": "case-volume-dialog",
                    "platform": "mtk",
                    "android_version": "15",
                    "project": "TVE8402M",
                    "repo_paths": ["vendor/mediatek/proprietary/packages/apps/SystemUI"],
                    "modified_files": ["src/com/android/systemui/volume/VolumeDialogImpl.java"],
                    "patch_ids": ["patch-abc"],
                    "report_ids": ["report-daily"],
                    "status": "candidate",
                    "verification": {"status": "missing", "method": "not_provided", "summary": "未提供验证证据"},
                }
            ],
        )
        write_jsonl(root / "index" / "evidence-index.jsonl", [])
        write_jsonl(root / "index" / "symbol-index.jsonl", [])
        write_json(
            root / "patches" / "by-id" / "patch-abc" / "patch.json",
            {
                "patch_id": "patch-abc",
                "case_id": "case-volume-dialog",
                "variant_id": "variant-mtk15-tve8402m-volume-dialog",
                "patch_name": "mtk15-systemui@volume-dialog-position.patch",
                "repo_paths": ["vendor/mediatek/proprietary/packages/apps/SystemUI"],
                "modified_files": ["src/com/android/systemui/volume/VolumeDialogImpl.java"],
                "status": "candidate",
            },
        )

        rows = search.load_rows(root)
        kinds = {row["kind"] for row in rows}
        self.assertIn("case", kinds)
        self.assertIn("variant", kinds)
        self.assertIn("patch", kinds)

        case_results = search.search(rows, "通知音量 SystemUI", "case", 5, include_synthetic=False)
        variant_results = search.search(rows, "TVE8402M VolumeDialogImpl", "variant", 5, include_synthetic=False)
        patch_results = search.search(rows, "volume-dialog-position", "patch", 5, include_synthetic=False)
        text = search.format_markdown(root, "TVE8402M VolumeDialogImpl", variant_results, None)

        self.assertEqual(case_results[0]["case_id"], "case-volume-dialog")
        self.assertEqual(variant_results[0]["variant_id"], "variant-mtk15-tve8402m-volume-dialog")
        self.assertEqual(patch_results[0]["patch_id"], "patch-abc")
        self.assertIn("[variant]", text)
        self.assertIn("平台/Android/项目", text)

    def test_patch_analysis_fields_are_searchable_and_formatted(self):
        root = Path(tempfile.mkdtemp())
        index = root / "index"
        index.mkdir()
        conn = sqlite3.connect(index / "knowledge.sqlite")
        try:
            conn.executescript(
                """
                CREATE TABLE patches(
                  id TEXT PRIMARY KEY, title TEXT, summary TEXT, modules TEXT, inferred_problem TEXT,
                  inferred_solution TEXT, inferred_keywords TEXT, inference_confidence TEXT,
                  inference_basis TEXT, inference_limits TEXT, risk_areas TEXT, modified_files TEXT,
                  patch_files TEXT, status TEXT
                );
                """
            )
            conn.execute(
                """
                INSERT INTO patches
                (id, title, summary, modules, inferred_problem, inferred_solution, inferred_keywords,
                 inference_confidence, inference_basis, inference_limits, risk_areas, modified_files, patch_files, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "patch-focus",
                    "Focus fix",
                    "",
                    '["WindowManager"]',
                    "Launcher launch may leave window focus stale",
                    "Adjust WindowManager focus update",
                    '["focus", "Launcher", "audio route/volume", "usb/device permission"]',
                    "medium",
                    '["patch modifies WindowState.java"]',
                    '["device verification is separate"]',
                    '["window focus", "audio route or volume behavior", "usb or device permission"]',
                    '["frameworks/base/services/core/java/com/android/server/wm/WindowState.java"]',
                    '["patches/by-id/patch-focus/patch.patch"]',
                    "candidate",
                ),
            )
            conn.execute(
                """
                INSERT INTO patches
                (id, title, summary, modules, inferred_problem, inferred_solution, inferred_keywords,
                 inference_confidence, inference_basis, inference_limits, risk_areas, modified_files, patch_files, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "patch-policy",
                    "Policy fix",
                    "",
                    '["Policy"]',
                    "Behavior in Policy may need correction",
                    "Patch changes Policy code paths and should be reviewed against the target requirement",
                    '["Policy"]',
                    "low",
                    '["patch modifies PhoneWindowManager.java"]',
                    '["device verification is separate"]',
                    '["power or policy behavior"]',
                    '["frameworks/base/services/core/java/com/android/server/policy/PhoneWindowManager.java"]',
                    '["patches/by-id/patch-policy/patch.patch"]',
                    "candidate",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        rows = search.load_rows(root)
        results = search.search(rows, "Launcher focus", "patch", 5, include_synthetic=False)
        text = search.format_markdown(root, "Launcher focus", results, None)

        self.assertEqual(results[0]["id"], "patch-focus")
        self.assertIn("补丁问题线索", text)
        self.assertIn("window focus", text)
        self.assertIn("音频路由/音量", text)
        self.assertIn("USB/设备权限", text)

        policy_results = search.search(rows, "Policy", "patch", 5, include_synthetic=False)
        policy_text = search.format_markdown(root, "Policy", policy_results, None)

        self.assertIn("Policy 相关行为需要核对和修正", policy_text)
        self.assertIn("补丁修改了 Policy 相关代码路径", policy_text)
        self.assertIn("按键/电源/策略行为", policy_text)


if __name__ == "__main__":
    unittest.main()
