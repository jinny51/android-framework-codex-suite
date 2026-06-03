from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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
        write_jsonl(root / "index" / "case-index.jsonl", [])
        write_jsonl(root / "index" / "variant-index.jsonl", [])
        write_jsonl(root / "index" / "symbol-index.jsonl", [])
        write_jsonl(root / "index" / "evidence-index.jsonl", [])
        write_json(
            root / "events" / "by-id" / "event-power.json",
            {
                "schema": "knowledge-event",
                "event_id": "event-power",
                "event_type": "incoming",
                "source_type": "incoming_package",
                "package_kind": "framework_change",
                "maturity": "validated",
                "member_alias": "testuser",
                "member_name": "测试成员",
                "date": "2026-05-26",
                "project": "TVE8402M",
                "platform": "rk3576",
                "summary": "修改电源键策略以满足产品需求",
            },
        )
        verification_evidence = {
            "schema": "knowledge-evidence",
            "evidence_id": "verification-result",
            "case_id": "case-power-key",
            "variant_id": "variant-rk3576-tve8402m-power-key",
            "kind": "verification_result",
            "result": "PASS",
            "summary": "rk3576 真机验证电源键行为通过",
            "payload": {"method": "device", "device": "rk3576"},
        }
        write_json(root / "evidence" / "by-id" / "verification-result.json", verification_evidence)
        write_jsonl(root / "index" / "evidence-index.jsonl", [verification_evidence])
        write_json(
            root / "evidence" / "by-id" / "source-evidence.json",
            {
                "schema": "knowledge-evidence",
                "evidence_id": "source-evidence",
                "event_id": "event-power",
                "kind": "source",
                "summary": "成员会话原始材料包含密码123等归档内容",
                "payload": {"raw_text": "密码123 电源键排查过程"},
            },
        )
        write_json(
            root / "reports" / "by-id" / "report-power.json",
            {
                "schema": "knowledge-report",
                "report_id": "report-power",
                "type": "daily",
                "author": "测试成员",
                "date": "2026-05-26",
                "overview": "密码123 电源键日报记录",
                "items": [{"title": "电源键调试", "project": "TVE8402M"}],
            },
        )
        return root

    def test_default_load_rows_excludes_archive_rows(self):
        root = self.make_root()

        rows = search.load_rows(root)

        kinds = {row["kind"] for row in rows}
        self.assertIn("evidence", kinds)
        self.assertNotIn("event", kinds)
        self.assertNotIn("report", kinds)
        self.assertNotIn("source-evidence", {row.get("id") for row in rows})

    def test_find_root_uses_configured_member_worktree_without_jinny_defaults(self):
        temp = Path(tempfile.mkdtemp())
        codex_home = temp / ".codex"
        knowledge_root = codex_home / "worktrees" / "knowledge-member01"
        (knowledge_root / "index").mkdir(parents=True)
        write_jsonl(knowledge_root / "index" / "case-index.jsonl", [])
        config_dir = codex_home / "report"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            """
            default_profile = "member01"

            [profiles.member01]
            member_alias = "member01"
            member_name = "成员一"
            repo_worktree = "$CODEX_HOME/worktrees/knowledge-member01"
            """,
            encoding="utf-8",
        )

        with patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(codex_home),
                "CODEX_REPORT_PROFILE": "member01",
                "CODEX_KNOWLEDGE_ROOT": "",
                "CODEX_REPORT_REPO_WORKTREE": "",
                "CODEX_REPORT_WORKTREE": "",
                "CODEX_WORK_REPORT_REPO_WORKTREE": "",
                "CODEX_WORK_REPORT_WORKTREE": "",
            },
        ):
            candidates = search.candidate_roots(None)
            root = search.find_root(None)

        candidate_text = "\n".join(str(item) for item in candidates)
        self.assertEqual(root, knowledge_root.resolve())
        self.assertNotIn("knowledge-" + "jinny", candidate_text)
        self.assertNotIn("knowledge-" + "test", candidate_text)

    def test_search_can_filter_event_and_evidence(self):
        root = self.make_root()
        rows = search.load_rows(root, include_archive=True)

        events = search.search(rows, "电源键 rk3576", "event", 5, include_synthetic=False)
        evidence = search.search(rows, "真机验证", "evidence", 5, include_synthetic=False)

        self.assertEqual(events[0]["id"], "event-power")
        self.assertEqual(evidence[0]["id"], "verification-result")

    def test_default_search_excludes_archive_rows_but_keeps_ai_evidence(self):
        root = self.make_root()
        rows = search.load_rows(root)
        results = search.search(rows, "电源键 真机验证", "all", 5, include_synthetic=False)

        text = search.format_markdown(root, "电源键 真机验证", results, None)

        self.assertIn("[evidence]", text)
        self.assertNotIn("[event]", text)
        self.assertNotIn("[report]", text)

        archive_results = search.search(rows, "密码123", "all", 5, include_synthetic=False)
        self.assertEqual(archive_results, [])

    def test_explicit_archive_filters_remain_available(self):
        root = self.make_root()
        rows = search.load_rows(root, include_archive=True)

        reports = search.search(rows, "密码123", "report", 5, include_synthetic=False)
        events = search.search(rows, "电源键 rk3576", "event", 5, include_synthetic=False)
        evidence = search.search(rows, "密码123", "evidence", 5, include_synthetic=False)

        self.assertEqual(reports[0]["id"], "report-power")
        self.assertEqual(events[0]["id"], "event-power")
        self.assertEqual(evidence[0]["id"], "source-evidence")

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
        write_jsonl(
            root / "index" / "search-docs.jsonl",
            [
                {
                    "type": "case",
                    "case_id": "case-volume-dialog",
                    "title": "通知音量弹窗位置适配",
                    "source_priority": 120,
                    "text": "通知音量弹窗位置适配\nSystemUI\nTVE8402M\nVolumeDialogImpl.java",
                    "variant_ids": ["variant-mtk15-tve8402m-volume-dialog"],
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
        case_by_variant_terms = search.search(rows, "TVE8402M VolumeDialogImpl", "case", 5, include_synthetic=False)
        text = search.format_markdown(root, "TVE8402M VolumeDialogImpl", variant_results, None)

        self.assertEqual(case_results[0]["case_id"], "case-volume-dialog")
        self.assertEqual(case_by_variant_terms[0]["case_id"], "case-volume-dialog")
        self.assertEqual(case_by_variant_terms[0]["source_priority"], 120)
        self.assertEqual(variant_results[0]["variant_id"], "variant-mtk15-tve8402m-volume-dialog")
        self.assertEqual(patch_results[0]["patch_id"], "patch-abc")
        self.assertIn("[variant]", text)
        self.assertIn("平台/Android/项目", text)

    def test_search_docs_priority_breaks_case_ties(self):
        root = Path(tempfile.mkdtemp())
        write_jsonl(
            root / "index" / "case-index.jsonl",
            [
                {"case_id": "case-low", "title": "音量弹窗位置适配", "problem": "通知音量弹窗位置不符合要求"},
                {"case_id": "case-high", "title": "音量弹窗位置适配", "problem": "通知音量弹窗位置不符合要求"},
            ],
        )
        write_jsonl(root / "index" / "variant-index.jsonl", [])
        write_jsonl(root / "index" / "symbol-index.jsonl", [])
        write_jsonl(root / "index" / "evidence-index.jsonl", [])
        write_jsonl(
            root / "index" / "search-docs.jsonl",
            [
                {
                    "type": "case",
                    "case_id": "case-low",
                    "title": "音量弹窗位置适配",
                    "source_priority": 30,
                    "text": "TVE8402M VolumeDialogImpl 通知音量",
                    "variant_ids": [],
                },
                {
                    "type": "case",
                    "case_id": "case-high",
                    "title": "音量弹窗位置适配",
                    "source_priority": 120,
                    "text": "TVE8402M VolumeDialogImpl 通知音量",
                    "variant_ids": [],
                },
            ],
        )

        rows = search.load_rows(root)
        results = search.search(rows, "TVE8402M VolumeDialogImpl", "case", 5, include_synthetic=False)

        self.assertEqual([item["case_id"] for item in results[:2]], ["case-high", "case-low"])

    def test_patch_analysis_fields_are_searchable_and_formatted(self):
        root = Path(tempfile.mkdtemp())
        write_jsonl(root / "index" / "case-index.jsonl", [])
        write_jsonl(root / "index" / "variant-index.jsonl", [])
        write_jsonl(root / "index" / "symbol-index.jsonl", [])
        write_jsonl(root / "index" / "evidence-index.jsonl", [])
        write_json(
            root / "patches" / "by-id" / "patch-focus" / "patch.json",
            {
                "patch_id": "patch-focus",
                "title": "Focus fix",
                "summary": "",
                "modules": ["WindowManager"],
                "problem_summary": "Launcher launch may leave window focus stale",
                "solution_summary": "Adjust WindowManager focus update",
                "keywords": ["focus", "Launcher", "audio route/volume", "usb/device permission"],
                "inference_confidence": "medium",
                "inference_basis": ["patch modifies WindowState.java"],
                "inference_limits": ["device verification is separate"],
                "risk_areas": ["window focus", "audio route or volume behavior", "usb or device permission"],
                "modified_files": ["frameworks/base/services/core/java/com/android/server/wm/WindowState.java"],
                "patch_files": ["patches/by-id/patch-focus/patch.patch"],
                "status": "candidate",
            },
        )
        write_json(
            root / "patches" / "by-id" / "patch-policy" / "patch.json",
            {
                "patch_id": "patch-policy",
                "title": "Policy fix",
                "summary": "",
                "modules": ["Policy"],
                "problem_summary": "Behavior in Policy may need correction",
                "solution_summary": "Patch changes Policy code paths and should be reviewed against the target requirement",
                "keywords": ["Policy"],
                "inference_confidence": "low",
                "inference_basis": ["patch modifies PhoneWindowManager.java"],
                "inference_limits": ["device verification is separate"],
                "risk_areas": ["power or policy behavior"],
                "modified_files": ["frameworks/base/services/core/java/com/android/server/policy/PhoneWindowManager.java"],
                "patch_files": ["patches/by-id/patch-policy/patch.patch"],
                "status": "candidate",
            },
        )

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
