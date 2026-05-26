from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import android_knowledge_search as search


class AndroidKnowledgeSearchV2Tests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        index = root / "index"
        index.mkdir()
        conn = sqlite3.connect(index / "knowledge.sqlite")
        try:
            conn.executescript(
                """
                CREATE TABLE knowledge_events(
                  id TEXT PRIMARY KEY, package_id TEXT, package_kind TEXT, channel TEXT, quality TEXT,
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
                (id, package_id, package_kind, channel, quality, member, date, project, platform, summary, path, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "event-power",
                    "20260526/testuser/20260526-213000-framework-change",
                    "framework_change",
                    "strict",
                    "validated",
                    "testuser",
                    "2026-05-26",
                    "Android Framework",
                    "rk3576",
                    "修改电源键策略以满足产品需求",
                    "knowledge-events/20260526/testuser/event-power/event.json",
                    '{"quality_claims":{"scope":"services.jar"}}',
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


if __name__ == "__main__":
    unittest.main()
