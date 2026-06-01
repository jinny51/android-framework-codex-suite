from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import android_knowledge_search as search


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
                    "Android Framework",
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
